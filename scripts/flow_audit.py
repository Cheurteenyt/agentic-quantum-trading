#!/usr/bin/env python
"""Audit lecture-seule de la couche flow du warehouse (klines.db).

Inventorie flow_events / flow_snapshots / signal_events / lifecycle_map /
basis_snapshots / oi_history : fraicheur, distributions, saneament ts_ms.
Aucune ecriture. Usage : .venv/bin/python scripts/flow_audit.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "warehouse" / "klines.db"


def ro() -> sqlite3.Connection:
    """Connexion lecture-seule (mode=ro) — JAMAIS d'ecriture ici."""
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)


def ts(epoch: float | None) -> str:
    if not epoch:
        return "-"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ts_ms(ms: float | None) -> str:
    if not ms:
        return "-"
    return ts(ms / 1000.0)


def one(c: sqlite3.Connection, sql: str, args=()):
    row = c.execute(sql, args).fetchone()
    return row[0] if row else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    c = ro()
    out: dict = {"db": str(DB)}

    # ---- flow_events ----
    fe = {
        "total": one(c, "SELECT COUNT(*) FROM flow_events"),
        "first_captured": ts(one(c, "SELECT MIN(captured_at) FROM flow_events")),
        "last_captured": ts(one(c, "SELECT MAX(captured_at) FROM flow_events")),
        "last_bar": ts(one(c, "SELECT MAX(bar_time) FROM flow_events")),
        "by_kind": [
            dict(zip(("kind", "n", "avg_delta", "max_abs_delta", "avg_depth_atr"), r))
            for r in c.execute(
                "SELECT kind, COUNT(*), ROUND(AVG(delta),1),"
                " ROUND(MAX(ABS(delta)),1), ROUND(AVG(depth_atr),3)"
                " FROM flow_events GROUP BY kind ORDER BY kind"
            )
        ],
        "by_symbol": [
            dict(zip(("symbol", "interval", "n"), r))
            for r in c.execute(
                "SELECT symbol, interval, COUNT(*) FROM flow_events"
                " GROUP BY symbol, interval ORDER BY 3 DESC"
            )
        ],
        "extremes": [
            dict(zip(("symbol", "kind", "bar", "close", "delta"), r))
            for r in c.execute(
                "SELECT symbol, kind, datetime(bar_time,'unixepoch'),"
                " ROUND(close,4), ROUND(delta,0) FROM flow_events"
                " WHERE kind LIKE 'absorption%' ORDER BY ABS(delta) DESC LIMIT 5"
            )
        ],
    }
    out["flow_events"] = fe

    # ---- flow_snapshots ----
    out["flow_snapshots"] = {
        "total": one(c, "SELECT COUNT(*) FROM flow_snapshots"),
        "last_captured": ts(one(c, "SELECT MAX(captured_at) FROM flow_snapshots")),
    }

    # ---- signal_events (ts_ms : verifier l'unite ! lecon nanosecondes) ----
    mn, mx = c.execute("SELECT MIN(ts_ms), MAX(ts_ms) FROM signal_events").fetchone()
    span_s = (mx - mn) / 1000.0 if mx and mn else 0
    # heuristique unite : epochs plausibles en ms => 13 chiffres
    unit = "ms" if mx and mx > 10**12 and mx < 10**14 else ("s" if mx and mx < 10**11 else "suspect")
    out["signal_events"] = {
        "total": one(c, "SELECT COUNT(*) FROM signal_events"),
        "unit_detected": unit,
        "first": ts_ms(mn),
        "last": ts_ms(mx),
        "span_days": round(span_s / 86400, 1),
        "top_signals": [
            dict(zip(("signal", "n"), r))
            for r in c.execute(
                "SELECT signal, COUNT(*) FROM signal_events"
                " GROUP BY signal ORDER BY 2 DESC LIMIT 8"
            )
        ],
        "symbols": one(c, "SELECT COUNT(DISTINCT symbol) FROM signal_events"),
    }

    # ---- lifecycle_map ----
    out["lifecycle_map"] = {
        "total": one(c, "SELECT COUNT(*) FROM lifecycle_map"),
        "last_captured": ts(one(c, "SELECT MAX(captured_at) FROM lifecycle_map")),
        "cells_sample": [
            dict(zip(("cell", "age", "dd", "n", "wr_long", "wr_short"), r))
            for r in c.execute(
                "SELECT cell, age_bucket, dd_bucket, n, wr_long, wr_short"
                " FROM lifecycle_map ORDER BY n DESC LIMIT 4"
            )
        ],
    }

    # ---- basis_snapshots ----
    out["basis_snapshots"] = {
        "total": one(c, "SELECT COUNT(*) FROM basis_snapshots"),
        "last_captured": ts(one(c, "SELECT MAX(captured_at) FROM basis_snapshots")),
        "symbols": one(c, "SELECT COUNT(DISTINCT symbol) FROM basis_snapshots"),
    }

    # ---- oi_history ----
    out["oi_history"] = {
        "total": one(c, "SELECT COUNT(*) FROM oi_history"),
        "last_captured": ts(one(c, "SELECT MAX(captured_at) FROM oi_history")),
        "symbols": one(c, "SELECT COUNT(DISTINCT symbol) FROM oi_history"),
        "sparsest": [
            dict(zip(("symbol", "n", "min_oi", "max_oi"), r))
            for r in c.execute(
                "SELECT symbol, COUNT(*), ROUND(MIN(open_interest),0),"
                " ROUND(MAX(open_interest),0) FROM oi_history"
                " GROUP BY symbol ORDER BY 2 ASC LIMIT 4"
            )
        ],
    }

    c.close()
    if a.json:
        print(json.dumps(out, indent=1, ensure_ascii=False))
    else:
        for k, v in out.items():
            print(f"== {k}")
            print(json.dumps(v, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
