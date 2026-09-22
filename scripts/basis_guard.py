#!/usr/bin/env python
"""Garde-fou de divergence Aster <-> Binance (le « basis »).

Rappel fondateur (incident MEME, basis +4521 %) : le prix d'un même perp n'est
PAS le même sur Aster et sur Binance, surtout sur les petites caps. Toute
lecture de contexte Binance (MMT ou autre) doit donc être pondérée par la
divergence mesurée du moment. Ce script la mesure, l'accumule et la signale.

Usage :
  .venv/bin/python scripts/basis_guard.py                    # rapport console
  .venv/bin/python scripts/basis_guard.py --record           # + snapshot en DB
  .venv/bin/python scripts/basis_guard.py --json --threshold 0.3
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "klines.db"

ASTER_TICKER = "https://fapi.asterdex.com/fapi/v1/ticker/price"
BINANCE_TICKER = "https://fapi.binance.com/fapi/v1/ticker/price"

BASIS_DDL = """
CREATE TABLE IF NOT EXISTS basis_snapshots (
    symbol        TEXT    NOT NULL,
    aster_price   REAL    NOT NULL,
    binance_price REAL    NOT NULL,
    basis_pct     REAL    NOT NULL,
    captured_at   REAL    NOT NULL,
    PRIMARY KEY (symbol, captured_at)
);
"""


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-agent/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def last_price(base: str, symbol: str) -> float:
    data = _get_json(f"{base}?symbol={symbol}")
    return float(data["price"])


def basis_pct(aster: float, binance: float) -> float:
    """Divergence en % ; positive = Aster au-dessus de Binance."""
    if binance == 0:
        raise ValueError("prix Binance nul")
    return (aster - binance) / binance * 100.0


def init_db(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.execute(BASIS_DDL)
    con.commit()
    return con


def record_snapshots(rows: list[dict], db_path: Path | str = DB_PATH) -> int:
    if not rows:
        return 0
    con = init_db(db_path)
    try:
        cur = con.executemany(
            "INSERT OR IGNORE INTO basis_snapshots "
            "(symbol, aster_price, binance_price, basis_pct, captured_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [(r["symbol"], r["aster_price"], r["binance_price"], r["basis_pct"], r["captured_at"])
             for r in rows],
        )
        con.commit()
        return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    finally:
        con.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Divergence Aster vs Binance par symbole")
    p.add_argument("--symbol", default="BTCUSDT,ETHUSDT,SOLUSDT,ASTERUSDT")
    p.add_argument("--threshold", type=float, default=0.5, help="alerte si |basis| >= x %%")
    p.add_argument("--record", action="store_true")
    p.add_argument("--db", default=str(DB_PATH))
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    rows: list[dict] = []
    flags: list[str] = []
    for sym in [s.strip().upper() for s in args.symbol.split(",") if s.strip()]:
        try:
            aster = last_price(ASTER_TICKER, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Aster {sym}: {exc}", file=sys.stderr)
            continue
        try:
            binance = last_price(BINANCE_TICKER, sym)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Binance {sym}: {exc} (Binance indisponible, basis non mesurable)", file=sys.stderr)
            continue
        b = basis_pct(aster, binance)
        rows.append({
            "symbol": sym,
            "aster_price": aster,
            "binance_price": binance,
            "basis_pct": round(b, 4),
            "captured_at": time.time(),
        })
        if abs(b) >= args.threshold:
            flags.append(sym)

    if args.record:
        inserted = record_snapshots(rows, args.db)
        print(f"[record] {inserted} snapshots -> {args.db}")

    if args.json:
        print(json.dumps(rows, indent=1))
    elif rows:
        print(f"{'SYMBOLE':<12} {'ASTER':>12} {'BINANCE':>12} {'BASIS %':>9}  ALERTE")
        print("-" * 56)
        for r in rows:
            alert = "  <<< DIVERGENCE" if abs(r["basis_pct"]) >= args.threshold else ""
            print(f"{r['symbol']:<12} {r['aster_price']:>12.4f} {r['binance_price']:>12.4f} "
                  f"{r['basis_pct']:>9.4f}{alert}")
    else:
        print("Aucune mesure (réseaux indisponibles ?).", file=sys.stderr)
        return 1

    if flags:
        print(f"\n! Divergence >= {args.threshold}%% sur : {', '.join(flags)}"
              " — le contexte Binance (MMT) est FAUSSÉ pour ces symboles, priorité aux données Aster.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
