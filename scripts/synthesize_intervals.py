#!/usr/bin/env python3
"""Synthetise des intervalles composes (3h, 5h...) depuis les bougies 1h.

L'API Aster n'expose pas 3h/5h — l'legacy les construisait en synthe­tique.
Regle corrigee du legacy (working-map 2026-06) : alignement par TIMESTAMP
epoch, pas par paquets arbitraires de bougies, et une bougie synthetique
incomplete est REJETEE (pas de bougie fausse dans le warehouse).

    python scripts/synthesize_intervals.py --symbols LABUSDT,HYPEUSDT \
        --targets 3h,5h [--base 1h]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fetch_klines import DB_PATH, init_db, load_bars  # noqa: E402


def _bucket_ms(hours: int) -> int:
    return hours * 3_600_000


def synthesize(con, symbol: str, base: str, hours: int) -> int:
    target = f"{hours}h"
    bars = load_bars(con, symbol, base)
    if not bars:
        print(f"[synth] {symbol} {base} : aucune bougie source")
        return 0
    step = _bucket_ms(1)
    need = hours
    buckets: dict[int, list] = {}
    for b in bars:
        key = (b.ts // _bucket_ms(hours)) * _bucket_ms(hours)
        buckets.setdefault(key, []).append(b)
    interval_ms = _bucket_ms(hours)
    inserted = 0
    now_s = time.time()
    src_symbol = symbol
    for key in sorted(buckets):
        candles = buckets[key]
        if len(candles) < need:
            continue  # bougie incomplete -> rejetee (trou ou bord de serie)
        if key + interval_ms > now_s * 1000 + interval_ms:
            continue
        first, last = candles[0], candles[-1]
        close_time = last.ts + step - 1
        con.execute(
            """
            INSERT OR REPLACE INTO klines
              (symbol, interval, open_time, open, high, low, close, volume,
               close_time, snapshot_id, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol, target, key, first.open,
                max(c.high for c in candles),
                min(c.low for c in candles),
                last.close,
                sum(c.volume for c in candles),
                close_time,
                f"synth-{base}-{target}",
                f"synth_{base}_{src_symbol}",
                now_s,
            ),
        )
        inserted += 1
    con.commit()
    print(f"[synth] {symbol} {base}->{target} : {inserted} bougies completes")
    return inserted


def main() -> int:
    ap = argparse.ArgumentParser(description="Intervalles synthetiques 3h/5h depuis 1h")
    ap.add_argument("--symbols", required=True, help="symboles separes par des virgules")
    ap.add_argument("--targets", default="3h,5h")
    ap.add_argument("--base", default="1h")
    args = ap.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    con = init_db(DB_PATH)
    total = 0
    for sym in symbols:
        for t in targets:
            hours = int(t[:-1]) if t.endswith("h") else 0
            if hours <= 0:
                print(f"[synth] cible non horaire ignoree : {t}", file=sys.stderr)
                continue
            total += synthesize(con, sym, args.base, hours)
    con.close()
    print(f"[synth] total insere : {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
