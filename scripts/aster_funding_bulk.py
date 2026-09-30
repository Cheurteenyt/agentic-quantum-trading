#!/usr/bin/env python3
"""LE BULK FUNDING ASTER (P6, 30/09) — l'API INTERNE de l'UI (docs/24).

Endpoint : bapi/futures/v1/public/future/common/real-time-funding-rate =
764 symboles en 1 appel (lastFundingRate, fundingIntervalHours,
fundingFeeCap/Floor ±0,02, estimatedSettlePrice, nextFundingTime).
curl_cffi impersonate=chrome131 requis (pattern aster_ui_replay) : pas
d'auth, pas de Cloudflare. Header X-MBX-USED-WEIGHT-1M ABSENT sur bapi →
note_weight l'avale (None) : bapi ne semble pas compter sur le budget fapi
2 400/min (l'état aster_rate_state.json le confirmera).

Stockage : klines.db:funding_meta — la META (dernier état par symbole,
INSERT OR REPLACE assumé : ce n'est PAS une série de verdicts) :
    symbol TEXT PRIMARY KEY, interval_hours INTEGER NOT NULL,
    fee_cap REAL, fee_floor REAL, rate REAL, settle_price REAL,
    captured_at_ms INTEGER NOT NULL
La précision que funding_fade attend : l'intervalle PAR SYMBOLE (30/09 :
356×4 h, 312×8 h, 93×1 h, 3×2 h — un « 8 h » global fausserait tout).

Usage :
  .venv/bin/python scripts/aster_funding_bulk.py   # 1 tir = 1 commit
"""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import aster_rate  # le compteur de poids X-MBX-USED-WEIGHT-1M (docs/24)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
URL = ("https://www.asterdex.com"
       "/bapi/futures/v1/public/future/common/real-time-funding-rate")
TIMEOUT = 30.0

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS funding_meta (
    symbol          TEXT    PRIMARY KEY,
    interval_hours  INTEGER NOT NULL CHECK (interval_hours > 0),
    fee_cap         REAL,
    fee_floor       REAL,
    rate            REAL,
    settle_price    REAL,
    captured_at_ms  INTEGER NOT NULL CHECK (captured_at_ms > 0)
);
"""

_SESSION = None  # session curl_cffi paresseuse (chrome131)


def bapi_get(url: str, timeout: float) -> object:
    global _SESSION
    if _SESSION is None:
        try:
            from curl_cffi import requests as cffi
        except ImportError as exc:
            raise RuntimeError(
                "curl_cffi absent du venv (uv pip install curl_cffi)") from exc
        _SESSION = cffi.Session(impersonate="chrome131")
    try:
        resp = _SESSION.get(url, timeout=timeout, headers={
            "Referer": "https://www.asterdex.com/en/trade/pro/futures/BTCUSDT",
            "Origin": "https://www.asterdex.com",
            "Accept": "application/json, text/plain, */*"})
        aster_rate.note_weight(dict(resp.headers), "funding_bulk")
        return resp.json()
    except Exception as exc:
        raise RuntimeError(f"bapi indisponible: {str(exc)[:80]}") from exc


def main() -> int:
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA busy_timeout = 10000")
        con.execute(CREATE_SQL)
        j = bapi_get(URL, TIMEOUT)
        data = j.get("data") if isinstance(j, dict) else None
        if not isinstance(data, list) or not data:
            raise RuntimeError(
                f"enveloppe inattendue ({type(j).__name__}) : "
                f"{str(j)[:120]}")
        now_ms = int(time.time() * 1000)
        rows, skipped = [], 0
        for x in data:
            try:
                sym = str(x["symbol"]).upper()
                iv = int(x["fundingIntervalHours"])
                cap_ms = int(x.get("time") or now_ms)
                rate = float(x["lastFundingRate"])
                settle = float(x["estimatedSettlePrice"])
                fee_cap = float(x["fundingFeeCap"])
                fee_floor = float(x["fundingFeeFloor"])
            except (KeyError, TypeError, ValueError):
                skipped += 1
                continue
            if iv <= 0:
                skipped += 1
                continue
            rows.append((sym, iv, fee_cap, fee_floor, rate, settle, cap_ms))
        if not rows:
            raise RuntimeError("0 ligne exploitable dans la reponse bulk")
        cur = con.executemany(
            "INSERT OR REPLACE INTO funding_meta "
            "(symbol, interval_hours, fee_cap, fee_floor, rate, settle_price, "
            "captured_at_ms) VALUES (?,?,?,?,?,?,?)", rows)
        con.commit()  # commit explicite : un tir = une transaction
        histo = dict(con.execute(
            "SELECT interval_hours, COUNT(*) FROM funding_meta "
            "GROUP BY interval_hours ORDER BY interval_hours").fetchall())
        print(f"[funding-bulk] {len(data)} syms recus -> {cur.rowcount} upserts, "
              f"echecs={skipped} | table funding_meta: "
              f"{con.execute('SELECT COUNT(*) FROM funding_meta').fetchone()[0]}"
              f" symboles | intervalles: {histo}", flush=True)
        return 0
    except RuntimeError as exc:
        print(f"[funding-bulk] ECHEC : {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        try:
            con.commit()
        except Exception:
            pass
        con.close()


if __name__ == "__main__":
    sys.exit(main())
