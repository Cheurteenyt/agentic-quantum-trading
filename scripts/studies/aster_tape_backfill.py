#!/usr/bin/env python3
"""T16bis — BACKFILL du TAPE MICROSTRUCTURE Aster (aggTrades BTC/ETH, J-N).

One-shot : pagination /fapi/v1/aggTrades par fromId CROISSANTE, batchs de
2000 rows, COMMIT PAR BATCH (règle anti-txn-fantôme), reprise exacte au
crash (curseur = MAX(agg_id) en DB, pattern T6). Le poids est noté à
CHAQUE réponse via aster_rate.note_weight (budget IP 2400/min) ; pacing
0,5 req/s = 600 poids/min pile (aggTrades poids 20/page de 1000) ; garde
blocktrades : poids lu >= 1500 → pause jusqu'à la minute suivante.

  .venv/bin/python scripts/studies/aster_tape_backfill.py --phase estimate
  .venv/bin/python scripts/studies/aster_tape_backfill.py --phase backfill \
      --symbols BTCUSDT,ETHUSDT --window-days 180
  .venv/bin/python scripts/studies/aster_tape_backfill.py --phase verify

DÉVIATION DE SCHÉMA (preuve 30/09-01/10) : les ids aggTrades sont PAR
SYMBOLE (BTC et ETH commencent tous deux à a=1 — sonde fromId=1), donc le
schéma littéral « agg_id INTEGER PRIMARY KEY » ferait collider les 48,2 M
d'ids ETH dans les 88,1 M de BTC (perte silencieuse d'ETH). Schéma retenu :
PRIMARY KEY (symbol, agg_id) — mêmes colonnes, unicité par symbole.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

STUDIES_DIR = Path(__file__).resolve().parent
ROOT = STUDIES_DIR.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import aster_rate  # noqa: E402  compteur X-MBX-USED-WEIGHT-1M (audit docs/24)
from curl_cffi import requests as creq  # noqa: E402  impersonate chrome131

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
STATE_PATH = ROOT / "data" / "warehouse" / "tape_backfill_state.json"
BASE = "https://fapi.asterdex.com"
SOURCE = "aster_public_tape_fapi_v1"
SLEEP_S = 2.0            # 0,5 req/s = 600 poids/min (aggTrades poids 20/page)
PAGE_LIMIT = 1000        # poids 20 par page <= 1000 trades
BATCH_ROWS = 2000        # 2 pages par batch, commit par batch
GUARD_WEIGHT = 1500      # garde blocktrades : pause jusqu'à la minute suivante
DAY_MS = 86_400_000
BYTES_PER_ROW_EST = 70   # estimation pré-vol ; mesurée en phase verify
PAGES_PER_MIN = 60.0 / SLEEP_S          # 30
PRINTS_PER_MIN = PAGES_PER_MIN * PAGE_LIMIT  # 30 000

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
GUARD_DAYS = {"BTCUSDT": 365, "ETHUSDT": 365}  # bornes mission (J-365)


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc):%m-%d %H:%M:%S}] {msg}", flush=True)


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1, sort_keys=True))


def safe_commit(con: sqlite3.Connection) -> None:
    """Commit ; en échec → rollback AVANT de remonter (pas de txn fantôme
    qui tiendrait le write-lock pendant les appels réseau suivants)."""
    try:
        con.commit()
    except sqlite3.Error:
        con.rollback()
        raise


def sleep_to_next_minute() -> None:
    now = time.time()
    time.sleep(60.0 - (now % 60.0) + 1.0)


def api_get(path: str, params: dict) -> tuple[int, object, str | None]:
    """GET curl_cffi chrome131 avec retries + garde poids. Retourne
    (status, json|None, err). note_weight sur CHAQUE réponse HTTP reçue."""
    url = f"{BASE}{path}?{urlencode(params)}"
    err: str | None = None
    for attempt in range(5):
        if attempt:
            backoff = min(65.0, 5.0 * (2 ** (attempt - 1)))
            log(f"  .. retry {attempt + 1}/5 dans {backoff:.0f}s ({err})")
            time.sleep(backoff)
        try:
            r = creq.get(url, impersonate="chrome131", timeout=20)
        except Exception as exc:
            err = f"réseau: {type(exc).__name__}: {str(exc)[:80]}"
            continue
        w = aster_rate.note_weight(r.headers, "aster_tape_backfill")
        if w is not None and w >= GUARD_WEIGHT:
            log(f"  .. poids lu {w} >= {GUARD_WEIGHT} — pause jusqu'à la minute suivante")
            sleep_to_next_minute()
        if r.status_code == 429:
            err = "HTTP 429 (budget poids)"
            time.sleep(65)
            continue
        if r.status_code >= 500:
            err = f"HTTP {r.status_code}"
            continue
        if r.status_code != 200:
            return r.status_code, None, f"HTTP {r.status_code}: {r.text[:100]}"
        try:
            return 200, r.json(), None
        except Exception as exc:
            err = f"non-JSON: {exc}"
        time.sleep(SLEEP_S)
    return 0, None, err or "échec après 5 essais"


def fetch_page(symbol: str, from_id: int) -> list | None:
    """Une page aggTrades (id >= from_id, <= 1000). None = erreur fatale."""
    code, page, err = api_get("/fapi/v1/aggTrades",
                              {"symbol": symbol, "fromId": from_id,
                               "limit": PAGE_LIMIT})
    time.sleep(SLEEP_S)  # pacing systématique, même après erreur
    if err is not None:
        return None
    return page


def latest_page(symbol: str) -> list | None:
    code, page, err = api_get("/fapi/v1/aggTrades",
                              {"symbol": symbol, "limit": PAGE_LIMIT})
    time.sleep(SLEEP_S)
    return page if err is None else None


def first_id_at(symbol: str, ts_target: int, last_id: int) -> int:
    """Binaire : plus petit agg_id dont le trade a T >= ts_target.
    ~27 sondes × poids 20 sur [1, last_id]."""
    lo, hi = 1, last_id + 1
    while lo < hi:
        mid = (lo + hi) // 2
        page = fetch_page(symbol, mid)
        if not page:
            # id inexistant / trou : avancer d'une page réelle si possible
            page2 = fetch_page(symbol, mid + 1) if mid < last_id else []
            if not page2:
                raise RuntimeError(f"sonde vide à fromId={mid} ({symbol})")
            page = page2
        t0 = int(page[0]["T"])
        if t0 < ts_target:
            lo = int(page[-1]["a"]) + 1
        else:
            hi = int(page[0]["a"])
    return lo


def init_table(con: sqlite3.Connection) -> None:
    con.execute(
        "CREATE TABLE IF NOT EXISTS aster_tape ("
        "agg_id INTEGER NOT NULL, "
        "symbol TEXT NOT NULL, "
        "ts_ms INTEGER NOT NULL, "
        "price REAL NOT NULL, "
        "qty REAL NOT NULL, "
        "is_buyer_maker INTEGER NOT NULL, "
        "PRIMARY KEY (symbol, agg_id))")
    safe_commit(con)


# ----------------------------------------------------------------- ESTIMATE
def phase_estimate(con: sqlite3.Connection, symbols: list[str]) -> None:
    log("=== ESTIMATION (sondes bornées, poids 20/sonde) ===")
    est = {}
    for sym in symbols:
        page = latest_page(sym)
        if not page:
            log(f"!! {sym}: dernière page indisponible — symbole sauté")
            continue
        last_id = max(int(t["a"]) for t in page)
        span_recent = int(page[-1]["T"]) - int(page[0]["T"])
        dens_now = len(page) / max(1e-9, span_recent / 1000.0)  # prints/s
        res = {"last_id": last_id,
               "last_ts": int(page[-1]["T"]),
               "density_now_per_day": int(dens_now * 86400)}
        for days in (365, 180, 90):
            t_start = int(page[-1]["T"]) - days * DAY_MS
            fid = first_id_at(sym, t_start, last_id)
            prints = last_id - fid + 1
            res[f"first_id_{days}d"] = fid
            res[f"prints_{days}d"] = prints
            res[f"size_mb_{days}d"] = round(prints * BYTES_PER_ROW_EST / 1e6, 1)
            res[f"hours_{days}d"] = round(prints / PRINTS_PER_MIN / 60.0, 2)
        est[sym] = res
        log(f"{sym}: last_id={last_id} | J-365: {res['prints_365d']:,} prints "
            f"≈ {res['size_mb_365d']} Mo, {res['hours_365d']} h | "
            f"J-180: {res['prints_180d']:,} ({res['hours_180d']} h) | "
            f"J-90: {res['prints_90d']:,} ({res['hours_90d']} h) | "
            f"densité now ≈ {res['density_now_per_day']:,}/j")
        st = load_state()
        st["estimate"] = est
        st["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_state(st)
    tot365 = sum(e["size_mb_365d"] for e in est.values())
    tot180 = sum(e["size_mb_180d"] for e in est.values())
    log(f"TOTAL projeté — J-365: {tot365 / 1024:.1f} Go, "
        f"J-180: {tot180 / 1024:.1f} Go (seuil NO-GO stockage 8 Go, "
        f"temps 4 h → {4 * 60 * PRINTS_PER_MIN:,} prints max)")
    return


# ----------------------------------------------------------------- BACKFILL
def phase_backfill(con: sqlite3.Connection, symbols: list[str],
                   window_days: int, max_minutes: float | None) -> None:
    init_table(con)
    state = load_state()
    budget_deadline = time.time() + max_minutes * 60 if max_minutes else None
    summary = {}
    for sym in symbols:
        if window_days > GUARD_DAYS.get(sym, 365):
            log(f"!! {sym}: fenêtre {window_days} j > garde {GUARD_DAYS[sym]} j — cap")
            window_days = GUARD_DAYS[sym]
        key = f"{sym}|{window_days}"
        prev = state.get(key) or {}
        if prev.get("done"):
            log(f"[skip] {key} déjà fait ({prev.get('rows'):,} rows) — --force pour rejouer")
            continue
        n_db = con.execute("SELECT COUNT(*), MAX(agg_id) FROM aster_tape "
                           "WHERE symbol = ?", (sym,)).fetchone()
        page = latest_page(sym)
        if not page:
            log(f"!! {sym}: dernière page indisponible — symbole sauté")
            continue
        last_id = max(int(t["a"]) for t in page)
        end_ts = int(page[-1]["T"])  # frontière haute figée au lancement
        t_start = end_ts - window_days * DAY_MS
        if n_db[0]:
            db_max = int(n_db[1])
            db_min = int(con.execute(
                "SELECT MIN(agg_id) FROM aster_tape WHERE symbol = ?",
                (sym,)).fetchone()[0])
            fid = first_id_at(sym, t_start, last_id)
            if db_min <= fid:
                cursor = db_max + 1  # reprise exacte : le départ de fenêtre est couvert
                log(f"=== {sym} REPRISE: curseur {cursor:,} (MAX DB) ===")
            else:
                cursor = fid  # fenêtre élargie : combler le trou côté passé
                log(f"=== {sym} ÉLARGISSEMENT: départ {fid:,} "
                    f"(MIN DB {db_min:,} > début de fenêtre) ===")
        else:
            fid = first_id_at(sym, t_start, last_id)
            cursor = fid
            log(f"=== {sym} DÉPART: fenêtre J-{window_days}, first_id {fid} "
                f"(ts {datetime.fromtimestamp(t_start / 1000, timezone.utc):%Y-%m-%d}) "
                f"→ last_id {last_id} ≈ {(last_id - fid + 1):,} prints ===")
        pages, rows, t0 = 0, 0, time.time()
        batch: list[tuple] = []
        status = "interrompu"
        while cursor <= last_id:
            if budget_deadline and time.time() > budget_deadline:
                status = f"cap --max-minutes atteint (reprise au curseur {cursor})"
                break
            pg = fetch_page(sym, cursor)
            if pg is None:
                status = "erreur réseau persistante — reprise possible"
                break
            if not pg:
                status = "fin (page vide)"
                break
            parsed = [(int(t["a"]), sym, int(t["T"]), float(t["p"]),
                       float(t["q"]), int(bool(t["m"]))) for t in pg]
            batch.extend(parsed)
            last_a = int(pg[-1]["a"])
            cursor = last_a + 1
            pages += 1
            if len(batch) >= BATCH_ROWS or cursor > last_id:
                con.executemany(
                    "INSERT OR IGNORE INTO aster_tape (agg_id, symbol, ts_ms, "
                    "price, qty, is_buyer_maker) VALUES (?,?,?,?,?,?)", batch)
                safe_commit(con)  # batch committé AVANT l'appel réseau suivant
                rows += len(batch)
                batch = []
                st = load_state()
                st[key] = {"window_days": window_days, "pages": pages,
                           "rows": rows, "done": False, "status": "en cours",
                           "last_id": last_a, "updated_at": datetime.now(
                               timezone.utc).isoformat(timespec="seconds")}
                save_state(st)  # checkpoint léger par batch (le vrai curseur = MAX en DB)
            if pages % 50 == 0:
                rate = pages / max(1e-9, time.time() - t0) * PAGE_LIMIT  # prints/s
                eta_min = (last_id - cursor + 1) / max(rate, 1e-9) / 60.0
                log(f"  {sym} page {pages} | id {last_a:,} | +{rows:,} rows "
                    f"| {rate:,.0f} prints/s ({rate * 60:,.0f}/min) | ETA {eta_min:.0f} min")
        if batch:
            con.executemany(
                "INSERT OR IGNORE INTO aster_tape (agg_id, symbol, ts_ms, "
                "price, qty, is_buyer_maker) VALUES (?,?,?,?,?,?)", batch)
            safe_commit(con)
            rows += len(batch)
        if status == "interrompu" and cursor > last_id:
            status = "fenêtre complète"
        state[key] = {"window_days": window_days, "pages": pages,
                      "rows": rows, "done": status not in ("interrompu",),
                      "status": status,
                      "last_id": cursor - 1,
                      "updated_at": datetime.now(timezone.utc)
                                    .isoformat(timespec="seconds")}
        save_state(state)
        dt = time.time() - t0
        summary[sym] = {"pages": pages, "rows": rows, "seconds": round(dt),
                        "status": status}
        log(f"=== {sym} FIN: {status} | {pages} pages | {rows:,} rows | "
            f"{dt / 60:.1f} min ===")
    return


# ------------------------------------------------------------------- VERIFY
def phase_verify(con: sqlite3.Connection, symbols: list[str]) -> None:
    log("=== VÉRIFICATION aster_tape ===")
    out = {}
    for sym in symbols:
        row = con.execute(
            "SELECT COUNT(*), MIN(agg_id), MAX(agg_id), MIN(ts_ms), MAX(ts_ms) "
            "FROM aster_tape WHERE symbol = ?", (sym,)).fetchone()
        n, amin, amax, tmin, tmax = (int(row[0]), row[1], row[2], row[3], row[4])
        gaps = (amax - amin + 1) - n if n else 0
        mono_bad = con.execute(
            "WITH x AS (SELECT ts_ms, LAG(ts_ms) OVER (ORDER BY agg_id) prev "
            "FROM aster_tape WHERE symbol = ?) "
            "SELECT COUNT(*) FROM x WHERE prev IS NOT NULL AND ts_ms < prev",
            (sym,)).fetchone()[0]
        days = (tmax - tmin) / DAY_MS if n else 0
        daily = n / days if days > 0 else 0
        out[sym] = {"rows": n, "id_min": amin, "id_max": amax,
                    "id_gaps": gaps, "ts_min": tmin, "ts_max": tmax,
                    "ts_non_monotone": mono_bad, "days_covered": round(days, 1),
                    "prints_per_day_avg": int(daily)}
        log(f"  {sym}: {n:,} rows | ids [{amin:,} → {amax:,}] | trous {gaps:,} "
            f"| ts non-monotone {mono_bad} | {days:.1f} j | {daily:,.0f} prints/j")
    # densité récente (7 derniers jours couverts) vs moyenne
    for sym in symbols:
        v = out.get(sym) or {}
        if not v.get("rows"):
            continue
        cut = v["ts_max"] - 7 * DAY_MS
        r = con.execute("SELECT COUNT(*) FROM aster_tape WHERE symbol = ? "
                        "AND ts_ms > ?", (sym, cut)).fetchone()[0]
        v["prints_last7d"] = int(r)
        v["prints_per_day_last7d"] = int(r / 7)
        log(f"  {sym}: 7 derniers jours {r:,} prints ({v['prints_per_day_last7d']:,}/j) "
            f"vs moyenne fenêtre {v['prints_per_day_avg']:,}/j")
    st = aster_rate._read()
    w = (st.get("max_recent") or {}).get("aster_tape_backfill")
    log(f"--- POIDS: max vu aster_tape_backfill = {w} / budget 2400 "
        f"(garde {GUARD_WEIGHT}) ---")
    print(json.dumps(out, indent=1, default=str))
    return


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", default="estimate",
                    choices=["estimate", "backfill", "verify"])
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="Cap de durée du backfill (reprise exacte ensuite).")
    ap.add_argument("--force", action="store_true",
                    help="Rejouer les séries 'done'.")
    args = ap.parse_args(argv)
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    con = sqlite3.connect(DB_PATH, timeout=30)
    try:
        if args.phase == "estimate":
            phase_estimate(con, syms)
        elif args.phase == "backfill":
            if args.force:
                st = load_state()
                for k in list(st):
                    if k.split("|")[0] in syms:
                        st.pop(k, None)
                save_state(st)
            phase_backfill(con, syms, args.window_days, args.max_minutes)
        else:
            phase_verify(con, syms)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
