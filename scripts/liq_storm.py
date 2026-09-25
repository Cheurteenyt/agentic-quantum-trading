#!/usr/bin/env python
"""L'INDICATEUR LIQ-STORM — la tempête de liquidations en direct.

Aster ne donne PAS d'historique de liquidations — notre collecteur 24/7
(liq_collector.py via forceOrder WS) construit la série propriétaire.
Cet indicateur la lit et produit la lecture du jour :

  - le ratio long/short des liquidations 24h (qui souffre ?)
  - le notional liquidé par symbole sur 24h
  - le flag STORM : la bouffée de 4h qui dépasse le p90 de la série

Usage stratégique (l'oracle l'a démontré) : les liquidations sont LA
variable qui sépare le réel du plafond. Une tempête de longs liquidés
confirme les shorts ; une tempête de shorts liquides = squeeze = on
relâche les shorts (l'AL Score la détecterait côté risque).

Pour l'instant la série a ~2 jours (collecteur démarré le 21/09) :
lecture DESCRIPTIVE. Le backtest des tempêtes sera possible à ~3-4
semaines d'accumulation — la nuit l'alimente.

  .venv/bin/python scripts/liq_storm.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"


def main() -> int:
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=5)
    try:
        rows = con.execute(
            "SELECT symbol, side, event_time, notional FROM liq_events "
            "ORDER BY event_time").fetchall()
    finally:
        con.close()
    if len(rows) < 20:
        print(f"[liq-storm] seulement {len(rows)} événements — série trop "
              f"jeune, rien à lire")
        return 0

    now_ms = rows[-1][2]
    day_ms = 86400 * 1000
    win_24h = [r for r in rows if r[2] >= now_ms - day_ms]
    win_4h = [r for r in rows if r[2] >= now_ms - 4 * 3600 * 1000]

    # le ratio long/short (SELL = un long liquidé, BUY = un short liquidé)
    sell_24 = sum(r[3] for r in win_24h if r[1] == "SELL")
    buy_24 = sum(r[3] for r in win_24h if r[1] == "BUY")
    ratio = sell_24 / max(buy_24, 1)

    # par symbole 24h
    per_sym: dict[str, float] = {}
    for sym, side, _, notional in win_24h:
        if side == "SELL":
            per_sym[sym] = per_sym.get(sym, 0.0) + notional
    top = sorted(per_sym.items(), key=lambda kv: -kv[1])[:8]

    # le flag STORM : notional 4h vs la distribution des bouffées 4h
    buckets: list[float] = []
    start = rows[0][2]
    t = start
    while t < now_ms:
        nxt = t + 4 * 3600 * 1000
        buckets.append(sum(r[3] for r in rows if t <= r[2] < nxt))
        t = nxt
    p90 = float(np.quantile(buckets, 0.9)) if len(buckets) >= 10 else 0.0
    cur_4h = sum(r[3] for r in win_4h)
    storm = cur_4h > p90 and p90 > 0

    lines = [
        "# LIQ-STORM — la lecture des liquidations Aster",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(rows)} événements accumulés (collecte depuis "
        f"{datetime.fromtimestamp(start/1000, tz=timezone.utc):%d/%m %H:%M}).",
        "",
        "| Lecture | Valeur |", "|---|---|",
        f"| Notional longs liquidés 24h | ${sell_24:,.0f} |",
        f"| Notional shorts liquidés 24h | ${buy_24:,.0f} |",
        f"| **Ratio long/short liquidé** | **{ratio:.1f}×** "
        f"{'(marché long = tailwind short)' if ratio > 1.5 else '(équilibré)'} |",
        f"| Bouffée 4h courante | ${cur_4h:,.0f} "
        f"(p90 série : ${p90:,.0f}) |",
        f"| **STORM** | **{'⚠ OUI — tempête en cours' if storm else 'non'}** |",
        "",
        "## Top longs liquidés 24h (les shorts profitent)", "",
        "| Symbole | Notional liquidé |", "|---|---|",
    ] + [f"| {s} | ${v:,.0f} |" for s, v in top] + [
        "",
        "La série grandit chaque nuit — backtest des tempêtes à 3-4 semaines.",
    ]
    out = REPORTS / f"liq-storm-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[liq-storm] ratio long/short {ratio:.1f}×, bouffée 4h ${cur_4h:,.0f} "
          f"(p90 ${p90:,.0f}), storm={'OUI' if storm else 'non'} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
