#!/usr/bin/env python
"""Flux pondéré par la COMPÉTENCE des baleines — l'indicateur propriétaire.

Depuis fomo.db : le flux frais (positions NOUVELLES vs le snapshot précédent)
de chaque ticker, pondéré par le winrate réalisé de chaque baleine
(fomo_closed : unipcs 24/24 pèse plus qu'un joueur moyen). Personne d'autre
n'a cette donnée : les positions réelles des baleines fomo + leur
compétence prouvée. Accumulé chaque nuit → forward tracking.

  .venv/bin/python scripts/whale_flow.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomo" / "fomo.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS whale_flow (
        ticker TEXT NOT NULL, buy_skill_weighted REAL, sell_skill_weighted REAL,
        n_whales INTEGER, captured_at REAL NOT NULL,
        PRIMARY KEY (ticker, captured_at))""")

    # le snapshot le plus récent et le précédent
    latest = con.execute("SELECT MAX(captured_at) FROM fomo_positions").fetchone()[0]
    prev = con.execute(
        "SELECT MAX(captured_at) FROM fomo_positions WHERE captured_at < ?",
        (latest,)).fetchone()[0]
    if not latest or not prev:
        print("[flow] pas assez de snapshots", file=sys.stderr)
        return 1

    # skill par handle (winrate réalisé sur les positions closed)
    skill: dict[str, float] = {}
    for h, w, n in con.execute(
            "SELECT handle, SUM(dir='▲'), COUNT(*) FROM fomo_closed GROUP BY handle"):
        if n >= 5:
            skill[h] = 0.5 + 0.5 * (w / n)  # 0.5 (moyen) → 1.0 (parfait)

    # positions du snapshot actuel vs précédent → les NOUVELLES
    prev_set = set(con.execute(
        "SELECT handle, ticker FROM fomo_positions WHERE captured_at = ?", (prev,)))
    flow: dict[str, dict] = defaultdict(lambda: {"buy": 0.0, "sell": 0.0, "w": set()})
    for h, t, val, d in con.execute(
            "SELECT handle, ticker, value_usd, dir FROM fomo_positions "
            "WHERE captured_at = ?", (latest,)):
        if (h, t) in prev_set or not val:
            continue
        w = skill.get(h, 0.5)
        key = "buy" if d == "▲" else "sell"
        flow[t][key] += val * w
        flow[t]["w"].add(h)

    now = time.time()
    for t, f in flow.items():
        con.execute("INSERT OR REPLACE INTO whale_flow VALUES (?,?,?,?,?)",
                    (t, round(f["buy"], 2), round(f["sell"], 2),
                     len(f["w"]), now))
    con.commit()
    top = con.execute(
        "SELECT ticker, buy_skill_weighted, sell_skill_weighted, n_whales "
        "FROM whale_flow WHERE captured_at = ? ORDER BY buy_skill_weighted "
        "DESC LIMIT 8", (now,)).fetchall()
    print(f"[whale-flow] {len(flow)} tickers avec flux frais :")
    for t, b, s, w in top:
        print(f"  {t}: achat pondéré ${b:,.0f} / vente ${s:,.0f} ({w} baleines)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
