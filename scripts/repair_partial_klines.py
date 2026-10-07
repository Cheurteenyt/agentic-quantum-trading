#!/usr/bin/env python3
"""PR-170 (P0 collecteurs) — purge ONE-SHOT des barres partielles figées.

La dernière bougie API est EN COURS : l'ancien store_klines l'écrivait
partielle puis INSERT OR IGNORE refusait le re-fetch correctif — preuve
prod : 1839 barres close/volume figés sur 933/964 séries (HUSDT close
−6 %, volume ÷50). Le fix store_klines n'écrit plus que des bougies
closes ; ce script PURGE les barres partielles déjà en base pour que le
fetch suivant les ré-écrive justes.

PÉRIMÈTRE : uniquement les séries ACTIVES (dernier fetch < --max-age
jours, défaut 3) — elles seront re-fetchées par le nightly (fenêtre
3000 barres ≈ 125 j). Les barres partielles des séries mortes restent :
un trou serait pire qu'une barre figée sans source de re-fetch.

    python scripts/repair_partial_klines.py            # dry-run
    python scripts/repair_partial_klines.py --apply    # purge
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KDB = ROOT / "data" / "warehouse" / "klines.db"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-age", type=int, default=3,
                    help="jours depuis le dernier fetch (défaut 3)")
    a = ap.parse_args()
    con = sqlite3.connect(KDB, timeout=60)
    cutoff = time.time() - a.max_age * 86400
    rows = con.execute(
        "SELECT symbol, interval, COUNT(*), MIN(open_time) FROM klines "
        "WHERE close_time IS NOT NULL AND close_time > fetched_at*1000 "
        "AND (symbol, interval) IN (SELECT symbol, interval FROM klines "
        "GROUP BY symbol, interval HAVING MAX(fetched_at) >= ?) "
        "GROUP BY symbol, interval", (cutoff,)).fetchall()
    total = sum(r[2] for r in rows)
    print(f"{len(rows)} série(s) active(s) touchée(s), {total} barre(s) "
          f"partielle(s) à purger")
    if not a.apply:
        for sym, itv, n, lo in rows[:10]:
            print(f"  [dry] {sym} {itv} : {n} barre(s) "
                  f"(depuis {lo})")
        print("dry-run (--apply pour purger)")
        return 0
    cur = con.execute(
        "DELETE FROM klines WHERE close_time IS NOT NULL "
        "AND close_time > fetched_at*1000 AND (symbol, interval) IN "
        "(SELECT symbol, interval FROM klines GROUP BY symbol, interval "
        "HAVING MAX(fetched_at) >= ?)", (cutoff,))
    con.commit()
    con.close()
    print(f"APPLY : {cur.rowcount} barre(s) partielle(s) purgée(s) — "
          "le fetch suivant les ré-écrit closes (nightly ou manuel)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
