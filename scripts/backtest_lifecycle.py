#!/usr/bin/env python
"""La CARTE DE CYCLE DE VIE — l'indicateur propriétaire 2D (âge × drawdown).

Personne ne backteste ça parce que personne ne pose la question : OÙ en est
ce coin dans SA vie ? Deux coordonnées d'état, reconstruites historiquement
sur 1 an de klines :
  - ÂGE : jours depuis la première bougie du symbole
  - DRAWDOWN : % sous son plus-haut absolu à cet instant
La grille 4×4 = 16 états de vie. Pour chaque état : les rendements futurs
(72h) blind LONG et blind SHORT, coûts réels. La carte dit où chaque type
de trade marche et où il meurt — l'état-machine complète du memecoin.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df, COST_PCT  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
H = 72  # horizon de mesure : 72h


def cell_label(age_d: float, dd: float) -> str:
    ab = "0-7j" if age_d < 7 else "7-30j" if age_d < 30 else "30-90j" if age_d < 90 else "90j+"
    db = "<20 %" if dd < 20 else "20-50 %" if dd < 50 else "50-80 %" if dd < 80 else ">80 %"
    return f"{ab} / {db}"


def main() -> int:
    con = sqlite3.connect(KDB)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]

    # grid[cell] = {"long": [rets], "short": [rets]}
    grid: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"long": [], "short": []})
    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close = df["close"]
        ath = close.cummax()
        drawdown = (1 - close / ath) * 100
        birth = df.index[0]
        age_d = (df.index - birth).total_seconds() / 86400
        closes, opens = close.values, df["open"].values
        idx = df.index
        for i in range(0, len(idx) - H, 12):  # pas de 12h, non-chevauchant à 72h
            cell = cell_label(age_d[i], drawdown.values[i])
            e, x = opens[i], closes[min(i + H, len(idx) - 1)]
            rl = (x - e) / e * 100 - COST_PCT
            rs = -rl
            grid[cell]["long"].append(rl)
            grid[cell]["short"].append(rs)

    con = sqlite3.connect(KDB)
    con.execute("""CREATE TABLE IF NOT EXISTS lifecycle_map (
        cell TEXT PRIMARY KEY, age_bucket TEXT, dd_bucket TEXT,
        n INTEGER, wr_long REAL, wr_short REAL,
        med_long REAL, med_short REAL, captured_at REAL NOT NULL)""")
    now = datetime.now(timezone.utc).timestamp()

    lines = [
        "# 🗺️ LA CARTE DE CYCLE DE VIE — âge × drawdown × rendement futur 72h",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — 1 an, "
        f"coûts {COST_PCT} %, pas 12h. L'état-machine du memecoin.", "",
        "| État de vie (âge / drawdown) | N | LONG 72h | SHORT 72h | Lecture |",
        "|---|---|---|---|---|",
    ]
    order = ["0-7j", "7-30j", "30-90j", "90j+"]
    dd_order = ["<20 %", "20-50 %", "50-80 %", ">80 %"]
    best_cells = []
    for ab in order:
        for db in dd_order:
            cell = f"{ab} / {db}"
            g = grid.get(cell)
            if not g or len(g["long"]) < 25:
                continue
            L, S = g["long"], g["short"]
            n = len(L)
            wl = sum(1 for x in L if x > 0) / n * 100
            ws = sum(1 for x in S if x > 0) / n * 100
            ml = sorted(L)[n // 2]
            ms = sorted(S)[n // 2]
            # la lecture : quelle jambe domine et de combien
            if wl >= 55 and wl - ws >= 8:
                lecture = "**TERRAIN LONG**"
                best_cells.append((cell, "LONG", wl, n))
            elif ws >= 55 and ws - wl >= 8:
                lecture = "**TERRAIN SHORT**"
                best_cells.append((cell, "SHORT", ws, n))
            else:
                lecture = "neutre"
            lines.append(f"| {cell} | {n} | {wl:.1f} % | {ws:.1f} % | {lecture} |")
            con.execute("INSERT OR REPLACE INTO lifecycle_map VALUES (?,?,?,?,?,?,?,?,?)",
                        (cell, ab, db, n, round(wl, 2), round(ws, 2),
                         round(ml, 2), round(ms, 2), now))
    con.commit()
    con.close()

    lines += ["", "## Les terrains de chasse (écart ≥ 8 pts, N ≥ 25)", ""]
    if best_cells:
        for cell, side, wr, n in sorted(best_cells, key=lambda x: -x[2]):
            lines.append(f"- **{cell}** → {side} ({wr:.1f} %, n={n})")
    else:
        lines.append("- aucun terrain avec un écart ≥ 8 pts — la carte est plate")

    out = REPORTS / f"lifecycle-map-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[lifecycle] {len(grid)} états évalués -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
