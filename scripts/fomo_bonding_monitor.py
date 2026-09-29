#!/usr/bin/env python
"""LE MONITEUR DE PRÉ-GRADUATION — prédire les migrations fomo → DEX.

Le catalyste des pumps fomo : la GRADUATION — quand la courbe de bonding
est pleine, le token migre vers un DEX (pumpswap) et le listing déclenche
le mouvement. Le champ bonding_pct (le % de courbe consommée) est capturé
à chaque scan nocturne — ce moniteur :
  1. reconstruit la VÉLOCITÉ de chaque token (les points bonding_pct vs temps)
  2. calcule l'ETA de graduation : (100 - pct) / vélocité
  3. produit la watchlist : les tokens dont l'ETA ≤ 3 jours

L'hypothèse de trade : se positionner AVANT la graduation (le listing
déclenche le pump — la loi 0-7j/près-ATH de la carte de cycle de vie).

  .venv/bin/python scripts/fomo_bonding_monitor.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomo" / "fomo.db"
REPORTS = ROOT / "reports"


def main() -> int:
    # MIGRATION REST (29/09) : fomo_new_coins mort → snapshot REST bonding
    # (fomo_rest.db, endpoint='bonding_snapshot') ; upsert = 1 point/mint.
    con = sqlite3.connect(
        f"file:{ROOT / 'data' / 'fomo' / 'fomo_rest.db'}?mode=ro",
        uri=True, timeout=10)
    # les snapshots bonding_pct par ticker : (ticker, captured_at, bonding_pct, mc)
    rows = []
    for mint, raw, cap in con.execute(
            "SELECT entity_id, data, captured_at FROM fomo_rest_snapshots "
            "WHERE endpoint='bonding_snapshot'").fetchall():
        d = json.loads(raw)
        tok = d.get("token") or {}
        pct = (tok.get("launchpad") or {}).get("graduationPercent")
        if pct is None:
            continue
        rows.append((tok.get("symbol") or mint[:8], cap, float(pct),
                     d.get("marketCap")))
    con.close()

    by_ticker: dict[str, list] = {}
    for tk, cap, pct, mc in rows:
        try:
            p = float(pct)
            if 0 <= p <= 100:
                by_ticker.setdefault(tk, []).append((float(cap), p, fnum := mc))
        except (TypeError, ValueError):
            continue

    now = time.time()
    watchlist: list[dict] = []
    for tk, points in by_ticker.items():
        if len(points) < 2:
            continue
        # la vélocité : les pts de bonding par jour (le fit simple entre le 1er et le dernier)
        (t0, p0, mc0), (t1, p1, mc1) = points[0], points[-1]
        days = (t1 - t0) / 86400
        if days <= 0 or p1 <= p0:
            continue
        velocity = (p1 - p0) / days          # les pts de bonding par jour
        remaining = 100 - p1
        if velocity <= 0 or remaining <= 0:
            continue
        eta_days = remaining / velocity
        latest_mc = mc1
        watchlist.append({
            "ticker": tk, "pct": p1, "velocity": velocity,
            "eta_days": eta_days, "mc": latest_mc,
            "scans": len(points),
        })

    watchlist.sort(key=lambda x: x["eta_days"])
    imminent = [w for w in watchlist if w["eta_days"] <= 3]

    lines = [
        "# LE MONITEUR DE PRÉ-GRADUATION — les migrations fomo → DEX",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(by_ticker)} tokens suivis, {len(watchlist)} avec une vélocité "
        f"mesurable.", "",
        "## LA WATCHLIST — les graduations imminentes (ETA ≤ 3 jours)", "",
    ]
    if imminent:
        lines.append("| Token | Bonding % | Vélocité (pts/j) | ETA (jours) | MC |")
        lines.append("|---|---|---|---|---|")
        for w in sorted(imminent, key=lambda x: x["eta_days"]):
            lines.append(
                f"| **{w['ticker']}** | {w['pct']:.0f} % | "
                f"{w['velocity']:+.1f} pts/j | **{w['eta_days']:.1f} j** | "
                f"${w['mc'] or 0:,.0f} |")
        lines += ["", "## LA LECTURE", "",
                  "- l'hypothèse de trade : se positionner spot AVANT la",
                  "    graduation (le listing DEX déclenche le mouvement —",
                  "    la loi 0-7j de la carte de cycle de vie).",
                  "- le forward : chaque graduation passée = un point de",
                  "    mesure du pump réel pré/post-migration."]
    else:
        lines.append("- Aucune graduation imminente — la watchlist se remplit "
                     "quand les tokens progressent sur leurs courbes.")

    lines += ["", "## LES VELOCITÉS (tous les tokens en progression)", ""]
    for w in sorted(watchlist, key=lambda x: x["eta_days"])[:14]:
        lines.append(f"- {w['ticker']} : bonding {w['pct']:.0f} %, "
                     f"vélocité {w['velocity']:+.1f} pts/j, "
                     f"ETA {w['eta_days']:.1f} j")

    out = REPORTS / f"bonding-monitor-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[bonding] {len(by_ticker)} tokens suivis, "
          f"{len(imminent)} graduations imminentes (ETA ≤ 3 j)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
