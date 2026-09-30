#!/usr/bin/env python
"""Moteur de carnet Aster diff-depth (EN PRODUCTION depuis le cutover 30/09,
docs/24) — le collecteur REST depth_collector est DÉSACTIVÉ, ce moteur est
l'unique écrivain de depth.db.

Maintient le carnet 24/7 via WebSocket (`<sym>@depth@500ms`) + resync snapshot
REST (fapi/v3/depth?limit=1000, poids 20), et l'échantillonne toutes les
SAMPLE_SEC s dans les tables réelles depth_bins / depth_meta de depth.db
(même schéma que l'ancien collecteur — le downstream wall_detector ne voit
aucune différence, sauf la fraîcheur : le carnet est maintenu en continu).

Protocole (docs asterdex/api-docs, compatible Binance futures) :
  1. snapshot REST -> lastUpdateId ;  2. jeter les diffs u <= lastUpdateId ;
  3. 1er diff appliqué : U <= lastUpdateId+1 <= u ;  4. ensuite pu == dernier u ;
  5. trou -> resync snapshot immédiat ;  qty 0 = suppression du niveau.

Débit : 10 msg/s PAR connexion -> 5 symboles max/connexion -> 3 connexions
(round-robin sur SYMBOLS de depth_collector). Reconnexion volontaire à 23 h,
décalée par connexion ; TOUTE reconnexion = resync snapshot complet du groupe.
Resyncs via aster_rate.note_weight (poids 20/snapshot) : périodique 1×/h/symbole
max + sur trou ; min 10 s entre deux tentatives par symbole.

Survie (copié de depth_collector) : watchdog 300 s sans write = os._exit(1)
(hang DNS inclus), prune 30 j avec index ts, _in_prune, logs [depth-engine].
SQLite : UNE seule connexion dans le process, un seul thread écrivain
(les tasks asyncio) ; le watchdog ne fait que lire des globals + os._exit.

Tests d'acceptation embarqués : à T+10 min puis T+20 min, snapshot REST frais
par symbole comparé au carnet maintenu (top-20 prix/qty à ±1 niveau, mid
< 0,05 %) -> data/warehouse/depth_ws_acceptance.json + tableau en log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sqlite3
import statistics
import sys
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

import websockets

import aster_rate
from depth_collector import BIN_FRAC, SYMBOLS, bin_levels  # compatibilité totale

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "depth.db"
ACCEPT_PATH = ROOT / "data" / "warehouse" / "depth_ws_acceptance.json"

WS_BASE = "wss://fstream.asterdex.com/stream?streams="
REST_DEPTH = "https://fapi.asterdex.com/fapi/v3/depth"

N_CONNS = 3                # 15 symboles / 5 par connexion (10 msg/s max/connexion)
SAMPLE_SEC = 30            # cadence d'échantillonnage = celle de depth_collector
RESYNC_MIN_GAP = 10        # s min entre deux tentatives de resync d'un symbole
PERIODIC_RESYNC = 3600     # resync de sécurité : 1×/h/symbole max
CONN_LIFETIME = 23 * 3600  # reconnexion volontaire ~23 h (fenêtres Aster)
CONN_STAGGER = 900         # +15 min par index de connexion
STALL_LIMIT_SEC = 300      # watchdog : 5 min sans write = exit(1)
RETENTION_DAYS = 30
ACCEPT_OFFSETS = (600, 1200)   # T+10 min, T+20 min
MID_TOL = 0.0005          # mid : < 0,05 %
QTY_TOL = 0.35            # qty d'un niveau top-20 (le marché bouge)
TOP_N = 20

SHADOW_DDL = """
CREATE TABLE IF NOT EXISTS depth_bins (
    symbol    TEXT    NOT NULL,
    ts        INTEGER NOT NULL,
    side      TEXT    NOT NULL,
    bin_price REAL    NOT NULL,
    qty       REAL    NOT NULL,
    PRIMARY KEY (symbol, ts, side, bin_price)
);
CREATE TABLE IF NOT EXISTS depth_meta (
    symbol TEXT    NOT NULL,
    ts     INTEGER NOT NULL,
    mid    REAL    NOT NULL,
    PRIMARY KEY (symbol, ts)
);
"""

_running = True
_last_progress = time.time()
_in_prune = False


class GapError(Exception):
    """Trou de séquence : pu != dernier u appliqué -> resync."""


class BookState:
    """Carnet d'un symbole : niveaux absolus + machine à états diff-depth."""

    __slots__ = ("symbol", "bids", "asks", "last_u", "synced", "buffer",
                 "needs_resync", "last_resync_attempt", "last_resync_done",
                 "awaiting_anchor")

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.bids: dict[str, float] = {}
        self.asks: dict[str, float] = {}
        self.last_u = 0            # dernier u appliqué (= lastUpdateId au snapshot)
        self.synced = False
        self.buffer: deque = deque(maxlen=400)  # diffs en attente de snapshot
        self.needs_resync = False
        self.last_resync_attempt = 0.0
        self.last_resync_done = 0.0
        self.awaiting_anchor = False  # 1er diff post-snapshot doit chevaucher

    def mid(self) -> float | None:
        if not self.bids or not self.asks:
            return None
        return (max(float(p) for p in self.bids)
                + min(float(p) for p in self.asks)) / 2.0


def apply_levels(st: BookState, ev: dict) -> None:
    """Applique b[]/a[] d'un diff : qty 0 = suppression, sinon niveau absolu."""
    for price_s, qty_s in ev.get("b") or []:
        q = float(qty_s)
        if q <= 0:
            st.bids.pop(price_s, None)
        else:
            st.bids[price_s] = q
    for price_s, qty_s in ev.get("a") or []:
        q = float(qty_s)
        if q <= 0:
            st.asks.pop(price_s, None)
        else:
            st.asks[price_s] = q


def apply_live(st: BookState, ev: dict) -> None:
    """Diff en régime établi : pu doit chaîner sur le dernier u appliqué.
    Exception : le PREMIER diff après un snapshot ancre la reprise. Sur Aster
    le lastUpdateId du snapshot est EN AVANT du flux WS (compteur global non
    contigu par symbole : preuve 30/09, TRUMPUSDT snapshot ...348085 puis
    event U=...56211) — la fenêtre Binance « U <= lastUpdateId+1 <= u » n'y
    est donc pas applicable ; l'ancre Aster est simplement u > last_u (le
    snapshot incorpore tous les u <= L, les niveaux sont absolus)."""
    if int(ev["u"]) <= st.last_u:
        return  # doublon / pré-snapshot
    if st.awaiting_anchor:
        st.awaiting_anchor = False
    elif int(ev.get("pu") or 0) != st.last_u:
        raise GapError(f"{st.symbol}: pu={ev.get('pu')} != last_u={st.last_u}")
    apply_levels(st, ev)
    st.last_u = int(ev["u"])


def drain_buffer(st: BookState) -> bool:
    """Applique le buffer après un snapshot. False = trou -> resync à refaire.

    Contrat Aster : sauter u <= lastUpdateId (pré-snapshot, déjà incorporés) ;
    le 1er diff gardé ANCRE (u > last_u, sans contrôle pu/U — compteur global
    non contigu) ; les suivants doivent chaîner (pu == u préc.)."""
    applied_any = False
    for ev in st.buffer:
        if int(ev["u"]) <= st.last_u:
            continue
        if applied_any and int(ev.get("pu") or 0) != st.last_u:
            return False
        apply_levels(st, ev)
        st.last_u = int(ev["u"])
        applied_any = True
    if applied_any:
        st.buffer.clear()
        st.awaiting_anchor = False  # la chaîne est (re)établie
    else:
        st.awaiting_anchor = True   # rien à rattacher : le 1er diff live ancre
    return True


def fetch_snapshot(symbol: str, source: str = "depth_engine") -> dict | None:
    """Snapshot REST limit=1000 (poids 20) — thread dédié, jamais la boucle."""
    url = f"{REST_DEPTH}?symbol={symbol}&limit=1000"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-agent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            aster_rate.note_weight(getattr(resp, "headers", None), source)
            return json.load(resp)
    except Exception as exc:  # noqa: BLE001
        print(f"[depth-engine] snapshot {symbol}: {exc}", file=sys.stderr, flush=True)
        return None


def _side_stats(rest_levels: list[tuple[float, float]], book: dict,
                mid_ref: float) -> tuple[int, int, float]:
    """Stats d'un côté : (niveaux REST présents dans le carnet à ±1 niveau,
    matches qty stricts (tol QTY_TOL), médiane qty_book/qty_rest au prix
    le plus proche — détecteur de bug d'unité, robuste au churn).
    Preuve 30/09 (REST vs REST, 1,2 s) : la qty PAR NIVEAU bouge au-delà de
    toute tolérance fixe (BTC 15/20, FARTCOIN 10/20 stricts ; somme top-20
    x0.52..x1.64) -> le verdict ne peut pas reposer sur la qty par niveau."""
    top = rest_levels[:TOP_N]
    diffs = [abs(top[i + 1][0] - top[i][0]) for i in range(len(top) - 1)
             if top[i + 1][0] != top[i][0]]
    tick = statistics.median(diffs) if diffs else mid_ref * 1e-6
    present = strict = 0
    ratios: list[float] = []
    for p, q in top:
        near = [(bp, bq) for bp, bq in book.items() if abs(float(bp) - p) <= tick * 1.5]
        if not near:
            continue
        present += 1
        bq_close = min(near, key=lambda x: abs(float(x[0]) - p))[1]
        if q > 0:
            ratios.append(bq_close / q)
        if near and min(abs(bq - q) / max(q, 1e-12) for _, bq in near) <= QTY_TOL:
            strict += 1
    return present, strict, (statistics.median(ratios) if ratios else 0.0)


QTY_RATIO_OK = (0.25, 4.0)   # médiane qty_book/qty_rest (bug d'unité = x10+)


def compare_book(st: BookState, snap: dict | None) -> dict:
    """Acceptation : mid < MID_TOL, top-20 REST présent dans le carnet à
    ±1 niveau (>= 19/20, plafonné par la taille réelle du carnet), médiane
    des ratios qty dans QTY_RATIO_OK. Colonne 'strict' (qty à ±1 niveau,
    tol 0.35) informatif : le plancher de churn du marché est PIRE (voir
    _side_stats)."""
    row = {"symbol": st.symbol, "synced": st.synced}
    try:
        rb = [(float(p), float(q)) for p, q in (snap or {}).get("bids") or []]
        ra = [(float(p), float(q)) for p, q in (snap or {}).get("asks") or []]
    except Exception:  # noqa: BLE001
        rb, ra = [], []
    if not rb or not ra:
        row.update(verdict="MISMATCH", reason="snapshot REST invalide")
        return row
    if not st.synced or not st.bids or not st.asks:
        row.update(verdict="MISMATCH", reason="carnet non synchronisé")
        return row
    mid_rest = (rb[0][0] + ra[0][0]) / 2.0
    mid_ws = st.mid() or 0.0
    mid_rel = abs(mid_ws - mid_rest) / mid_rest if mid_rest else 1.0
    pb, sb, rb_med = _side_stats(rb, st.bids, mid_rest)
    pa, sa, ra_med = _side_stats(ra, st.asks, mid_rest)
    need_b = max(0, min(TOP_N - 1, len(rb[:TOP_N]) - 1))
    need_a = max(0, min(TOP_N - 1, len(ra[:TOP_N]) - 1))
    ok = (mid_rel < MID_TOL and pb >= need_b and pa >= need_a
          and QTY_RATIO_OK[0] <= rb_med <= QTY_RATIO_OK[1]
          and QTY_RATIO_OK[0] <= ra_med <= QTY_RATIO_OK[1])
    row.update(verdict="MATCH" if ok else "MISMATCH",
               mid_ws=round(mid_ws, 8), mid_rest=round(mid_rest, 8),
               mid_rel_pct=round(mid_rel * 100, 4),
               bids_present=f"{pb}/{len(rb[:TOP_N])}", asks_present=f"{pa}/{len(ra[:TOP_N])}",
               bids_strict=f"{sb}/{len(rb[:TOP_N])}", asks_strict=f"{sa}/{len(ra[:TOP_N])}",
               qty_ratio=f"{rb_med:.2f}/{ra_med:.2f}")
    return row


def _stop(signum, frame):  # noqa: ARG001
    global _running
    _running = False


def _stalled(now: float | None = None) -> bool:
    if _in_prune:
        return False
    now = time.time() if now is None else now
    return (now - _last_progress) > STALL_LIMIT_SEC


def _watchdog() -> None:
    """Copié de depth_collector : muet >300 s (hang DNS, socket morte, suspend)
    = exit(1), systemd relance. Avance au wall clock (réveil de suspend)."""
    while _running:
        time.sleep(20)
        if _stalled():
            age = time.time() - _last_progress
            print(f"[watchdog] aucun write réussi depuis >{STALL_LIMIT_SEC}s "
                  f"(dernier progrès il y a {age:.0f}s) -> exit(1)", file=sys.stderr, flush=True)
            os._exit(1)


def prune_old(con: sqlite3.Connection) -> int:
    """Prune 30 j des tables OMBRE (les tables de prod restent à depth_collector)."""
    global _in_prune, _last_progress
    _in_prune = True
    cur = None
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_depth_bins_ts ON depth_bins(ts)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_depth_meta_ts ON depth_meta(ts)")
        cutoff = int(time.time()) - RETENTION_DAYS * 86400
        cur = con.execute("DELETE FROM depth_bins WHERE ts < ?", (cutoff,))
        con.execute("DELETE FROM depth_meta WHERE ts < ?", (cutoff,))
        con.commit()
    finally:
        _in_prune = False
        _last_progress = time.time()
    return cur.rowcount if cur is not None else 0


class Engine:
    def __init__(self, con: sqlite3.Connection, accept_offsets: tuple[int, ...]):
        self.con = con
        self.accept_offsets = accept_offsets
        self.states: dict[str, BookState] = {s: BookState(s) for s in SYMBOLS}
        self.groups: list[list[str]] = [SYMBOLS[i::N_CONNS] for i in range(N_CONNS)]
        self.t0 = time.time()

    # ---- WebSocket -------------------------------------------------------
    async def run_connection(self, idx: int) -> None:
        syms = self.groups[idx]
        streams = "/".join(f"{s.lower()}@depth@500ms" for s in syms)
        url = WS_BASE + streams
        backoff = 5.0
        while _running:
            deadline = time.time() + CONN_LIFETIME + idx * CONN_STAGGER
            try:
                async with websockets.connect(url, ping_interval=20,
                                              open_timeout=15) as ws:
                    backoff = 5.0
                    print(f"[depth-engine] conn#{idx} connectée : {syms}", flush=True)
                    for s in syms:  # toute (re)connexion = resync complet du groupe
                        st = self.states[s]
                        st.synced = False
                        st.needs_resync = True
                        st.buffer.clear()
                    async for raw in ws:
                        if not _running or time.time() > deadline:
                            break
                        self.handle_message(raw)
                if _running and time.time() > deadline:
                    print(f"[depth-engine] conn#{idx} : 23 h atteintes, "
                          "reconnexion + resync", flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                if _running:
                    print(f"[depth-engine] conn#{idx} : {exc}", file=sys.stderr, flush=True)
            if not _running:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60.0)

    def handle_message(self, raw) -> None:
        try:
            msg = json.loads(raw)
            data = msg.get("data") if isinstance(msg, dict) else None
            if not isinstance(data, dict) or data.get("e") != "depthUpdate":
                return
            st = self.states.get(data.get("s"))
            if st is None:
                return
        except Exception as exc:  # noqa: BLE001
            print(f"[depth-engine] frame illisible : {exc}", file=sys.stderr, flush=True)
            return
        if not st.synced:
            st.buffer.append(data)
            return
        try:
            apply_live(st, data)
        except GapError as exc:
            print(f"[depth-engine] {exc} -> resync", file=sys.stderr, flush=True)
            st.synced = False
            st.needs_resync = True

    # ---- Resync ----------------------------------------------------------
    async def resync_symbol(self, sym: str) -> bool:
        st = self.states[sym]
        st.last_resync_attempt = time.time()
        st.synced = False
        for _ in range(3):
            snap = await asyncio.to_thread(fetch_snapshot, sym)
            if _running is False:
                return False
            if snap and snap.get("bids") and snap.get("asks"):
                st.bids = {p: float(q) for p, q in snap["bids"] if float(q) > 0}
                st.asks = {p: float(q) for p, q in snap["asks"] if float(q) > 0}
                st.last_u = int(snap["lastUpdateId"])
                if drain_buffer(st):
                    st.synced = True
                    st.needs_resync = False
                    st.last_resync_done = time.time()
                    print(f"[resync] {sym} ok (lastUpdateId={st.last_u}, "
                          f"{len(st.bids)} bids / {len(st.asks)} asks)", flush=True)
                    return True
                await asyncio.sleep(1)  # trou juste après le snapshot : on reprend
        print(f"[resync] {sym} ÉCHOUÉ (3 essais)", file=sys.stderr, flush=True)
        st.needs_resync = True
        return False

    async def resync_coordinator(self) -> None:
        """Urgent (trou, (re)connexion) d'abord, puis resync périodique 1×/h."""
        while _running:
            await asyncio.sleep(5)
            now = time.time()
            urgent = [s for s, st in self.states.items()
                      if (st.needs_resync or not st.synced)
                      and now - st.last_resync_attempt >= RESYNC_MIN_GAP]
            for sym in urgent:
                if not _running:
                    return
                await self.resync_symbol(sym)
            now = time.time()
            periodic = [s for s, st in self.states.items()
                        if st.synced and not st.needs_resync
                        and st.last_resync_done
                        and now - st.last_resync_done >= PERIODIC_RESYNC]
            for sym in periodic[:2]:  # poids étalé : max 2 snapshots/sweep
                if not _running:
                    return
                print(f"[resync] {sym} : sécurité 1×/h", flush=True)
                await self.resync_symbol(sym)

    # ---- Échantillonnage -------------------------------------------------
    async def sampler(self) -> None:
        global _last_progress
        while _running:
            await asyncio.sleep(SAMPLE_SEC)
            ts = int(time.time())
            rows, metas, n = [], [], 0
            for st in self.states.values():
                if not st.synced or not st.bids or not st.asks:
                    continue
                mid = st.mid()
                if mid is None or mid <= 0:
                    continue
                grid = mid * BIN_FRAC
                for side, book in (("bid", st.bids), ("ask", st.asks)):
                    for b, q in bin_levels([[p, q] for p, q in book.items()], grid).items():
                        rows.append((st.symbol, ts, side, b, q))
                metas.append((st.symbol, ts, mid))
                n += 1
            if rows:
                self.con.executemany(
                    "INSERT OR REPLACE INTO depth_bins "
                    "(symbol, ts, side, bin_price, qty) VALUES (?, ?, ?, ?, ?)", rows)
                self.con.executemany(
                    "INSERT OR REPLACE INTO depth_meta (symbol, ts, mid) "
                    "VALUES (?, ?, ?)", metas)
                self.con.commit()
                _last_progress = time.time()
                print(f"[depth-engine] échantillon ts={ts} : {n}/{len(SYMBOLS)} "
                      f"symboles, {len(rows)} lignes", flush=True)

    # ---- Acceptation -----------------------------------------------------
    async def acceptance(self) -> None:
        for offset in self.accept_offsets:
            target = self.t0 + offset
            while _running and time.time() < target:
                await asyncio.sleep(min(10, max(0.5, target - time.time())))
            if not _running:
                return
            rows = []
            for sym in SYMBOLS:
                snap = await asyncio.to_thread(fetch_snapshot, sym, "depth_engine_accept")
                rows.append(compare_book(self.states[sym], snap))
            # plancher de churn marché : 2 snapshots REST consécutifs (1 s) du
            # symbole de référence, comparés ENTRE EUX (aucun moteur impliqué)
            churn = None
            ra_ = await asyncio.to_thread(fetch_snapshot, "BTCUSDT", "depth_engine_accept")
            if ra_:
                await asyncio.sleep(1)
                rb_ = await asyncio.to_thread(fetch_snapshot, "BTCUSDT", "depth_engine_accept")
                if rb_:
                    try:
                        lb = {p: float(q) for p, q in ra_["bids"]}
                        la = {p: float(q) for p, q in ra_["asks"]}
                        bl = [(float(p), float(q)) for p, q in rb_["bids"]]
                        al = [(float(p), float(q)) for p, q in rb_["asks"]]
                        mid = (float(rb_["bids"][0][0]) + float(rb_["asks"][0][0])) / 2
                        pb, sb, _ = _side_stats(bl, lb, mid)
                        pa, sa, _ = _side_stats(al, la, mid)
                        churn = {"ref": "BTCUSDT REST-vs-REST (1 s)",
                                 "bids_present": f"{pb}/20", "asks_present": f"{pa}/20",
                                 "bids_strict": f"{sb}/20", "asks_strict": f"{sa}/20"}
                    except Exception:  # noqa: BLE001
                        churn = None
            matched = sum(1 for r in rows if r["verdict"] == "MATCH")
            out = {"pass": f"T+{offset // 60}min", "generated_at": int(time.time()),
                   "matched": matched, "total": len(SYMBOLS), "churn_ref": churn,
                   "rows": rows}
            try:
                ACCEPT_PATH.write_text(json.dumps(out, indent=1))
            except Exception as exc:  # noqa: BLE001
                print(f"[acceptance] écriture rapport: {exc}", file=sys.stderr, flush=True)
            print(f"[acceptance] {out['pass']} : {matched}/{len(SYMBOLS)} MATCH "
                  f"(churn REST-vs-REST BTC: {churn['bids_strict'] if churn else '?'}) "
                  f"-> {ACCEPT_PATH.name}", flush=True)
            for r in rows:
                if "mid_rel_pct" in r:
                    extra = (f" mid={r['mid_rel_pct']}% pres={r['bids_present']}/"
                             f"{r['asks_present']} strict={r['bids_strict']}/"
                             f"{r['asks_strict']} ratio_qty={r['qty_ratio']}")
                else:
                    extra = f" raison={r.get('reason')}"
                print(f"[acceptance]   {r['symbol']:<13} {r['verdict']:<8}{extra}",
                      flush=True)

    # ---- Prune -----------------------------------------------------------
    async def pruner(self) -> None:
        last_day = -1
        while _running:
            await asyncio.sleep(300)
            day = int(time.time() // 86400)
            if day != last_day:
                removed = await asyncio.to_thread(prune_old, self.con)
                last_day = day
                if removed:
                    print(f"[prune] {removed} lignes ombre > {RETENTION_DAYS}j", flush=True)


async def main_async(accept_offsets: tuple[int, ...]) -> int:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _stop, sig, None)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.executescript(SHADOW_DDL)
    eng = Engine(con, accept_offsets)
    print(f"[depth-engine] démarré : {len(SYMBOLS)} symboles, {N_CONNS} connexions, "
          f"échantillonnage {SAMPLE_SEC}s -> {DB_PATH} (tables ombre _ws)", flush=True)
    threading.Thread(target=_watchdog, name="watchdog", daemon=True).start()
    tasks = [asyncio.create_task(eng.run_connection(i)) for i in range(N_CONNS)]
    tasks += [asyncio.create_task(eng.resync_coordinator()),
              asyncio.create_task(eng.sampler()),
              asyncio.create_task(eng.acceptance()),
              asyncio.create_task(eng.pruner())]
    while _running:
        await asyncio.sleep(0.5)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    con.close()
    print("[depth-engine] arrêt propre", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--acceptance-at", default="600,1200",
                    help="offsets (s) des passes d'acceptation après le démarrage")
    args = ap.parse_args()
    offsets = tuple(int(x) for x in str(args.acceptance_at).split(",") if x.strip())
    return asyncio.run(main_async(offsets))


if __name__ == "__main__":
    raise SystemExit(main())
