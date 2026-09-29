#!/usr/bin/env python3
"""parking_backfill.py — le chargeur du parking WS (le fix de la fuite).

fomo_dom_worker.FrameListener parque chaque frame WS de la page dans
data/fomo/ws_frame_parking.jsonl sans jamais la persister. Ce one-shot :
  1. parse le JSONL (tolérant : les lignes tronquées/corrompues sont
     comptées et rejetées dans data/fomo/ws_parking_rejects.jsonl) ;
  2. insère les bougies (toutes périodes présentes : 30s, 1m natives)
     dans fomo_ohlcv (INSERT OR REPLACE, time MS d'origine préservé,
     captured_at = maintenant) ;
  3. insère les token_details dans fomo_token_details (fomo.db, DDL
     ensure-style, PK (mint, timestamp, frame_ts) = idempotent) ;
  4. après SUCCÈS complet : rotation — le parking est renommé en
     .bak-<horodatage> (sauvegarde intacte), le worker recrée le sien au
     prochain append (open "a").

Ré-exécutable sans doublon (OR REPLACE + rotation). Écritures en petits
lots (commit par lot) avec busy_timeout 30 s — le ws-daemon reste actif.

Usage :
  .venv/bin/python scripts/studies/parking_backfill.py [--dry-run]
      [--no-rotate] [--batch 2500] [--parking PATH] [--db PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PARKING = ROOT / "data" / "fomo" / "ws_frame_parking.jsonl"
DEFAULT_DB = ROOT / "data" / "fomo" / "fomo.db"
REJECTS_F = ROOT / "data" / "fomo" / "ws_parking_rejects.jsonl"

DDL_TOKEN_DETAILS = """
CREATE TABLE IF NOT EXISTS fomo_token_details (
    mint TEXT NOT NULL,
    timestamp INTEGER,
    frame_ts INTEGER,
    change1m REAL, change5m REAL, change1h REAL, change4h REAL,
    change6h REAL, change12h REAL, change24h REAL,
    buys5min INTEGER, buys1h INTEGER, buys4h INTEGER, buys24h INTEGER,
    sells5min INTEGER, sells1h INTEGER, sells4h INTEGER, sells24h INTEGER,
    volumeBuy5minUSD REAL, volumeBuy1hUSD REAL, volumeBuy4hUSD REAL,
    volumeBuy24hUSD REAL,
    volumeSell5minUSD REAL, volumeSell1hUSD REAL, volumeSell4hUSD REAL,
    volumeSell24hUSD REAL,
    buyers5min INTEGER, buyers1h INTEGER, buyers4h INTEGER, buyers24h INTEGER,
    sellers5min INTEGER, sellers1h INTEGER, sellers4h INTEGER, sellers24h INTEGER,
    captured_at REAL NOT NULL,
    payload TEXT,
    PRIMARY KEY (mint, timestamp, frame_ts)
)"""
IDX_TOKEN_DETAILS = ("CREATE INDEX IF NOT EXISTS idx_ftd_mint "
                     "ON fomo_token_details(mint, timestamp DESC)")

TD_FIELDS = ["change1m", "change5m", "change1h", "change4h", "change6h",
             "change12h", "change24h",
             "buys5min", "buys1h", "buys4h", "buys24h",
             "sells5min", "sells1h", "sells4h", "sells24h",
             "volumeBuy5minUSD", "volumeBuy1hUSD", "volumeBuy4hUSD",
             "volumeBuy24hUSD",
             "volumeSell5minUSD", "volumeSell1hUSD", "volumeSell4hUSD",
             "volumeSell24hUSD",
             "buyers5min", "buyers1h", "buyers4h", "buyers24h",
             "sellers5min", "sellers1h", "sellers4h", "sellers24h"]

SQL_OHLCV = ("INSERT OR REPLACE INTO fomo_ohlcv "
             "(asset, period, time, open, high, low, close, volume, captured_at) "
             "VALUES (?,?,?,?,?,?,?,?,?)")
SQL_TD = (f"INSERT OR REPLACE INTO fomo_token_details "
          f"(mint, timestamp, frame_ts, {', '.join(TD_FIELDS)}, captured_at, payload) "
          f"VALUES ({', '.join(['?'] * (3 + len(TD_FIELDS) + 2))})")


def parse_parking(path: Path):
    """Retourne (ohlcv_rows, td_rows, stats). Tolérant aux lignes mortes."""
    ohlcv, tdetail = [], []
    stats = Counter()
    rejects = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                outer = json.loads(raw)
            except Exception:
                stats["reject_outer_json"] += 1
                rejects.append((ln, "outer_json", raw[:400]))
                continue
            tt = outer.get("topicType")
            ts = outer.get("ts")
            payload = outer.get("payload")
            try:
                pl = json.loads(payload) if isinstance(payload, str) else payload
            except Exception:
                stats[f"reject_payload_{tt}"] += 1
                rejects.append((ln, f"payload_{tt}", raw[:400]))
                continue
            if tt == "ohlcv":
                asset, t, per = pl.get("asset"), pl.get("time"), pl.get("period")
                if not asset or not t or not per:
                    stats["reject_ohlcv_fields"] += 1
                    rejects.append((ln, "ohlcv_fields", raw[:400]))
                    continue
                ohlcv.append((asset, per, int(t), pl.get("open"), pl.get("high"),
                              pl.get("low"), pl.get("close"), pl.get("volume"),
                              None))  # captured_at à l'insertion
                stats[f"ohlcv_{per}"] += 1
            elif tt == "token_details":
                tid = pl.get("topicId", "")
                mint = tid.rsplit(":", 1)[0] if tid else None
                inner = pl.get("payload") or {}
                if not mint:
                    stats["reject_td_mint"] += 1
                    rejects.append((ln, "td_mint", raw[:400]))
                    continue
                row = [mint, inner.get("timestamp"), ts]
                row += [inner.get(f) for f in TD_FIELDS]
                row += [None, json.dumps(inner, ensure_ascii=False)]
                tdetail.append(tuple(row))
                stats["token_details"] += 1
            else:
                stats[f"skip_{tt}"] += 1
    return ohlcv, tdetail, stats, rejects


def stamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parking", type=Path, default=DEFAULT_PARKING)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--batch", type=int, default=2500)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-rotate", action="store_true")
    args = ap.parse_args()

    if not args.parking.exists():
        print(f"PARKING ABSENT : {args.parking}")
        return 1
    size = args.parking.stat().st_size
    print(f"parking : {args.parking} ({size/1e6:.1f} Mo)")

    ohlcv, tdetail, stats, rejects = parse_parking(args.parking)
    print(f"parsé : {dict(stats)}")
    print(f"bougies={len(ohlcv)} token_details={len(tdetail)} rejetées={len(rejects)}")
    if args.dry_run:
        print("DRY-RUN — rien écrit.")
        return 0

    now = time.time()
    con = sqlite3.connect(args.db, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute(DDL_TOKEN_DETAILS)
    con.execute(IDX_TOKEN_DETAILS)
    con.commit()

    n_ins_ohlc = n_ins_td = 0
    try:
        rows = [(a, p, t, o, h, l, c, v, now) for (a, p, t, o, h, l, c, v, _) in ohlcv]
        for i in range(0, len(rows), args.batch):
            con.executemany(SQL_OHLCV, rows[i:i + args.batch])
            con.commit()
            n_ins_ohlc += len(rows[i:i + args.batch])
        for i in range(0, len(tdetail), args.batch):
            chunk = tdetail[i:i + args.batch]
            chunk = [r[:-2] + (now, r[-1]) for r in chunk]
            con.executemany(SQL_TD, chunk)
            con.commit()
            n_ins_td += len(chunk)
    except sqlite3.OperationalError as e:
        con.rollback()
        print(f"ÉCHEC SQLITE (rollback des lots non commités) : {e}")
        return 2
    finally:
        con.close()
    print(f"inséré : fomo_ohlcv={n_ins_ohlc} fomo_token_details={n_ins_td}")

    if rejects:
        with open(REJECTS_F, "a", encoding="utf-8") as fh:
            for ln, why, raw in rejects:
                fh.write(json.dumps({"line": ln, "why": why, "raw": raw}) + "\n")
        print(f"rejets consignés : {REJECTS_F}")

    if args.no_rotate:
        print("rotation désactivée — le parking est conservé tel quel.")
        return 0
    bak = args.parking.with_name(f"{args.parking.name}.bak-{stamp()}")
    os.replace(args.parking, bak)  # atomique : le worker recrée le sien en "a"
    print(f"rotation : parking → {bak.name} ({size/1e6:.1f} Mo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
