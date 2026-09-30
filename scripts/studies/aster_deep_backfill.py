#!/usr/bin/env python3
"""T6 — BACKFILL PROFOND des klines Aster vers la genèse (2021-09).

Suite de T4 (klines SANS TROU jusqu'à 2021-09, pagination 1500/page) : ce
one-shot page EN ARRIÈRE depuis la plus vieille bougie de klines.db (le
curseur de reprise = MIN(open_time) en DB) jusqu'à la genèse de chaque
symbole, et écrit INSERT OR REPLACE, batch de 1500, COMMIT PAR BATCH
(règle anti-txn-fantôme : jamais de write-lock tenu pendant les appels réseau).

  .venv/bin/python scripts/studies/aster_deep_backfill.py --phase all
  .venv/bin/python scripts/studies/aster_deep_backfill.py --phase 1m --symbols BTCUSDT

Pacing : 0,5 req/s (SLEEP_S=2.0) → klines poids 5/page = 150 poids/min
sur un budget X-MBX-USED-WEIGHT-1M de 2400/min (marge ×16). Le poids réel
est noté dans data/warehouse/aster_rate_state.json via aster_rate.note_weight.
Piège T4 : un 400 consomme du poids — traité comme fin d'historique, jamais
replayé en boucle. 429 → backoff 65 s. Reprise : relancer, le curseur repart
de MIN(open_time), l'état accumulé vit dans deep_backfill_state.json.
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
import fetch_klines as fk  # noqa: E402  parse_kline_row/interval_ms/init_db (validation identique)
from curl_cffi import requests as creq  # noqa: E402  impersonate chrome131

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
STATE_PATH = ROOT / "data" / "warehouse" / "deep_backfill_state.json"
BASE = "https://fapi.asterdex.com"
SOURCE = "aster_public_klines_fapi_v3"
SLEEP_S = 2.0          # 0,5 req/s = 150 poids/min (klines poids 5/page)
MAX_LIMIT = 1500       # poids 5 par page klines
DAY_MS = 86_400_000

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ASTERUSDT"]
# Genèses attendues (T4) — plancher d'arrêt avec marge 3 jours.
GENESIS_EXPECTED = {
    "BTCUSDT": 1630444800000,    # 2021-09-01
    "ETHUSDT": 1630963200000,    # 2021-09-07
    "SOLUSDT": 1631136000000,    # 2021-09-09
    "ASTERUSDT": 1758153600000,  # 2025-09-18
}
FLOOR_MARGIN_MS = 3 * DAY_MS
FUNDING_START = 1757980800000   # 2025-09-16 00:00 UTC (mission)
FUNDING_WINDOW_MS = 29 * DAY_MS  # fenêtre < 30 j OBLIGATOIRE (piège T4)


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


def api_get(path: str, params: dict) -> tuple[int, object, str | None]:
    """GET curl_cffi chrome131 avec retries. Retourne (status, json|None, err).
    Le poids est noté via aster_rate.note_weight sur CHAQUE réponse."""
    url = f"{BASE}{path}?{urlencode(params)}"
    err: str | None = None
    for attempt in range(5):
        if attempt:
            backoff = min(65.0, 5.0 * (2 ** (attempt - 1)))
            log(f"  .. retry {attempt + 1}/5 dans {backoff:.0f}s ({err})")
            time.sleep(backoff)
        try:
            r = creq.get(url, impersonate="chrome131", timeout=20)
        except Exception as exc:  # réseau : on retente
            err = f"réseau: {type(exc).__name__}: {str(exc)[:80]}"
            continue
        aster_rate.note_weight(r.headers, "aster_deep_backfill")
        if r.status_code == 429:
            err = "HTTP 429 (budget poids)"
            time.sleep(65)
            continue
        if r.status_code >= 500:
            err = f"HTTP {r.status_code}"
            continue
        if r.status_code != 200:
            # 400/418 : piège T4 (un 400 consomme le poids et ne rend rien)
            return r.status_code, None, f"HTTP {r.status_code}: {r.text[:100]}"
        try:
            return 200, r.json(), None
        except Exception as exc:
            err = f"non-JSON: {exc}"
    return 0, None, err or "échec après 5 essais"


def backfill_series(con: sqlite3.Connection, symbol: str, interval: str,
                    max_pages: int | None, force: bool) -> bool:
    """Pagine en ARRIÈRE de MIN(open_time) en DB vers la genèse. True = fait."""
    step = fk.interval_ms(interval)
    floor = GENESIS_EXPECTED[symbol] - FLOOR_MARGIN_MS
    key = f"{symbol}|{interval}"
    state = load_state()
    prev = state.get(key) or {}
    if prev.get("done") and not force:
        log(f"[skip] {key} déjà fait (genèse {prev.get('oldest_ts')}) — --force pour rejouer")
        return True

    row = con.execute(
        "SELECT MIN(open_time) FROM klines WHERE symbol = ? AND interval = ?",
        (symbol, interval)).fetchone()
    anchor = int(row[0]) if row and row[0] is not None else int(time.time() * 1000)
    cursor = anchor - 1
    est_pages = max(1, (anchor - floor) // (MAX_LIMIT * step))
    log(f"=== {symbol} {interval} — curseur {anchor} → plancher {floor} (~{est_pages} pages) ===")

    pages = int(prev.get("pages") or 0)
    stored = int(prev.get("stored") or 0)
    t0 = time.time()
    done, status = False, "interrompu"
    while cursor > floor:
        if max_pages is not None and pages - int(prev.get("pages") or 0) >= max_pages:
            status = f"cap --max-pages {max_pages} (reprise possible)"
            break
        status_code, page, err = api_get("/fapi/v3/klines", {
            "symbol": symbol, "interval": interval,
            "endTime": cursor, "limit": MAX_LIMIT})
        time.sleep(SLEEP_S)  # pacing systématique, même après erreur
        if err is not None:
            if status_code == 400:
                done, status = True, "fin d'historique (HTTP 400)"
                break
            log(f"  !! {key}: {err} — série abandonnée (relançable, curseur en DB)")
            status = err
            break
        if not page:
            done, status = True, "genèse atteinte (page vide)"
            break
        try:
            parsed = [fk.parse_kline_row(k, i) for i, k in enumerate(page)]
        except fk.KlineParseError as exc:
            log(f"  !! {key}: kline malformée ({exc}) — série abandonnée, rien commité")
            status = f"kline malformée: {exc}"
            break

        min_ts = min(p[0] for p in parsed)
        max_ts = max(p[0] for p in parsed)
        snap = f"deep-backfill-{symbol}-{interval}-{min_ts}-{max_ts}-{len(parsed)}"
        now = time.time()
        con.executemany(
            "INSERT OR REPLACE INTO klines (symbol, interval, open_time, open, "
            "high, low, close, volume, taker_buy_volume, quote_volume, close_time, "
            "snapshot_id, source, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(symbol, interval, p[0], p[1], p[2], p[3], p[4], p[5], p[7], p[8],
              p[6], snap, SOURCE, now) for p in parsed])
        safe_commit(con)  # batch de 1500 committé AVANT l'appel réseau suivant

        pages += 1
        stored += len(parsed)
        cursor = min_ts - 1
        if pages % 20 == 0:
            rate = (pages - int(prev.get("pages") or 0)) / max(1e-9, time.time() - t0)
            eta_min = ((cursor - floor) / (MAX_LIMIT * step)) / max(rate, 1e-9) / 60
            log(f"  {key} page {pages} | curseur {min_ts} | +{stored} bougies | ETA {eta_min:.0f} min")
        if len(page) < MAX_LIMIT:
            done, status = True, "genèse atteinte (page incomplète)"
            break
        if min_ts <= floor:
            done, status = True, "plancher de genèse atteint"
            break

    state[key] = {"pages": pages, "stored": stored, "done": done, "status": status,
                  "oldest_ts": cursor + 1 if done else int(prev.get("oldest_ts") or 0),
                  "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save_state(state)
    log(f"=== {key} FIN: {status} | {pages} pages cumulées | {stored} bougies | "
        f"{time.time() - t0:.0f}s (ce run) ===")
    return done


def verify_series(con: sqlite3.Connection, symbol: str, interval: str) -> dict:
    """COUNT, continuité (trous > 2× l'intervalle) et cohérence genèse T4."""
    step = fk.interval_ms(interval)
    row = con.execute(
        "SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM klines "
        "WHERE symbol = ? AND interval = ?", (symbol, interval)).fetchone()
    n, lo, hi = int(row[0]), row[1], row[2]
    gaps2, worst = [], 0
    prev = None
    for (ts,) in con.execute(
            "SELECT open_time FROM klines WHERE symbol = ? AND interval = ? "
            "ORDER BY open_time ASC", (symbol, interval)):
        if prev is not None and ts - prev > 2 * step:
            gaps2.append((prev, ts))
            worst = max(worst, ts - prev)
        prev = ts
    expected = GENESIS_EXPECTED[symbol]
    ok_genesis = lo is not None and lo <= expected + 2 * DAY_MS
    return {"symbol": symbol, "interval": interval, "count": n, "min_ts": lo,
            "max_ts": hi, "gaps_gt_2step": len(gaps2), "worst_gap_ms": worst,
            "genesis_expected": expected, "genesis_ok": ok_genesis,
            "examples": gaps2[:5]}


def backfill_funding(con: sqlite3.Connection) -> dict:
    """Funding ASTERUSDT depuis 2025-09-16, fenêtres ≤ 29 j (piège T4)."""
    log(f"=== FUNDING ASTERUSDT depuis {FUNDING_START} (fenêtres 29 j) ===")
    start, now_ms = FUNDING_START, int(time.time() * 1000)
    windows, rows, t0 = 0, 0, time.time()
    while start < now_ms:
        end = min(start + FUNDING_WINDOW_MS - 1, now_ms)
        status_code, data, err = api_get("/fapi/v1/fundingRate", {
            "symbol": "ASTERUSDT", "startTime": start, "endTime": end, "limit": 1000})
        time.sleep(SLEEP_S)
        if err is not None:
            log(f"  !! funding fenêtre {start}: {err} — abandon (relançable)")
            break
        con.executemany(
            "INSERT OR REPLACE INTO funding_history (symbol, funding_time, rate, fetched_at) "
            "VALUES (?,?,?,?)",
            [(d["symbol"], int(d["fundingTime"]), float(d["fundingRate"]), time.time())
             for d in data])
        safe_commit(con)
        windows += 1
        rows += len(data)
        start = end + 1
    log(f"=== FUNDING FIN: {windows} fenêtres, {rows} lignes, {time.time() - t0:.0f}s ===")
    return {"windows": windows, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    global SLEEP_S
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", default="all",
                    choices=["all", "1h", "15m", "1m", "funding", "verify"])
    ap.add_argument("--symbols", default=",".join(SYMBOLS))
    ap.add_argument("--max-pages", type=int, default=None,
                    help="Cap de pages PAR série (smoke test / reprise partielle).")
    ap.add_argument("--force", action="store_true", help="Rejouer les séries 'done'.")
    ap.add_argument("--sleep", type=float, default=SLEEP_S)
    ap.add_argument("--skip-verify", action="store_true",
                    help="Passer le scan de continuité final (chunks courts).")
    args = ap.parse_args(argv)
    SLEEP_S = max(0.5, args.sleep)

    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    con = fk.init_db(DB_PATH)
    ok = True
    try:
        if args.phase == "verify":
            for itv in ["1h", "15m", "1m"]:
                for sym in syms:
                    print(json.dumps(verify_series(con, sym, itv), default=str))
            return 0
        if args.phase in ("all", "funding"):
            backfill_funding(con)
        for itv in ["1h", "15m", "1m"]:
            if args.phase not in ("all", itv):
                continue
            for sym in syms:
                if not backfill_series(con, sym, itv, args.max_pages, args.force):
                    ok = False
        log("--- VÉRIFICATION ---")
        if args.skip_verify:
            log("  (skip --skip-verify)")
        else:
            for itv in ["1h", "15m", "1m"]:
                for sym in syms:
                    v = verify_series(con, sym, itv)
                    log(f"  {sym} {itv}: {v['count']} bougies [{v['min_ts']} → {v['max_ts']}] "
                        f"trous>2x: {v['gaps_gt_2step']} genèse_OK: {v['genesis_ok']}")
        st = load_state()
        log("--- ÉTAT POIDS (aster_rate_state.json) ---")
        log(json.dumps(aster_rate._read().get("max_recent") or {}, indent=1))
        log(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "status"}
                        for k, v in st.items() if isinstance(v, dict)}, indent=1))
    finally:
        con.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
