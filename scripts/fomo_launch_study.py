#!/usr/bin/env python
"""L'ÉTUDE DES LANCEMENTS fomo — la coupe transversale des vies complètes.

Chaque token fomo a sa vie complète en bougies 1m/5m/15m/1h dans
fomo_ohlcv (le live + le backfill GT). L'étude mesure, token par token :
  - la vie (première → dernière bougie)
  - le pic vs l'entrée (le multiple max)
  - le drawdown de fin (l'état actuel vs le pic)
  - les retours à +1h/+6h/+24h depuis la première bougie
Et la coupe transversale : la distribution des destins
  (les pumps, les morts-nés, les survivants).

C'est LA base du backtest fomo : connaître la distribution des vies
pour construire les entrées/sorties qui la monétisent.

  .venv/bin/python scripts/fomo_launch_study.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomo" / "fomo.db"
REPORTS = ROOT / "reports"


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    assets = [r[0] for r in con.execute(
        "SELECT DISTINCT asset FROM fomo_ohlcv WHERE period='1m'")]
    rows_out = []
    for mint in assets:
        rows = con.execute(
            "SELECT time, open, high, low, close FROM fomo_ohlcv "
            "WHERE asset=? AND period='1m' ORDER BY time", (mint,)).fetchall()
        if len(rows) < 20:
            continue
        t0 = rows[0][0]
        o = rows[0][1]
        peak = max(r[2] for r in rows)
        last = rows[-1][4]
        last_t = rows[-1][0]
        # les retours depuis la première bougie
        def ret_at(hours):
            target = t0 + hours * 3600 * 1000
            best = min(rows, key=lambda r: abs(r[0] - target))
            return (best[4] - o) / o * 100 if o > 0 else np.nan
        r1h, r6h, r24h = ret_at(1), ret_at(6), ret_at(24)
        mult_peak = (peak - o) / o * 100 if o > 0 else np.nan
        from_peak = (last - peak) / peak * 100 if peak > 0 else np.nan
        life_h = (last_t - t0) / 3600 * 1000 / 1000 / 3600
        tk = con.execute("SELECT ticker FROM fomo_tokens WHERE mint=?",
                         (mint,)).fetchone()
        rows_out.append({
            "ticker": tk[0] if tk else mint[:10], "mint": mint[:12],
            "candles": len(rows),
            "life_h": (last_t - t0) / 3.6e9,
            "peak_mult": mult_peak, "from_peak": from_peak,
            "r1h": r1h, "r6h": r6h, "r24h": r24h,
            "first": datetime.fromtimestamp(t0 / 1000, tz=timezone.utc),
        })
    con.close()

    if not rows_out:
        print("[launch] pas assez de tokens avec une vie 1m — patiente")
        return 1

    peaks = np.array([r["peak_mult"] for r in rows_out], dtype=float)
    r24 = np.array([r["r24h"] for r in rows_out], dtype=float)
    r1h = np.array([r["r1h"] for r in rows_out], dtype=float)

    lines = [
        "# L'ÉTUDE DES LANCEMENTS fomo — la coupe transversale des vies",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(rows_out)} tokens avec une vie 1m complète.", "",
        "| Token | Vie (h) | Bougies | Pic vs entrée | Fin vs pic | +1h | +24h |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in sorted(rows_out, key=lambda x: -x["peak_mult"])[:18]:
        lines.append(
            f"| {r['ticker']} | {r['life_h']:.1f} | {r['candles']} "
            f"| {r['peak_mult']:+.0f} % | {r['from_peak']:+.1f} % "
            f"| {r['r1h']:+.1f} % | {r['r24h']:+.1f} % |")
    ok = np.isfinite(peaks)
    if ok.sum() >= 5:
        lines += ["", "## LA DISTRIBUTION DES DESTINS", "",
                  f"- Pic médian vs entrée : **{np.nanmedian(peaks):+.0f} %** "
                  f"(moyenne {np.nanmean(peaks):+.0f} %)",
                  f"- Les pics > 100 % : {int((peaks > 100).sum())}/{int(ok.sum())} "
                  f"tokens ({(peaks > 100).sum()/ok.sum()*100:.0f} %)",
                  f"- Les pics > 300 % : {int((peaks > 300).sum())} tokens",
                  f"- +1h médian : {np.nanmedian(r1h):+.1f} % | "
                  f"+24h médian : {np.nanmedian(r24):+.1f} %", "",
                  "## LA LECTURE", "",
                  "- la distribution des pics = LA matière première des entrées",
                  "  fomo : où se situe le token qu'on regarde dans cette",
                  "  distribution détermine le trade.",
                  "- les entries/sorties se construisent sur cette coupe,",
                  "  pas sur un seul token."]
    out = REPORTS / f"launch-study-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[launch] {len(rows_out)} tokens étudiés | pic médian "
          f"{np.nanmedian(peaks):+.0f} % | pics >100 % : "
          f"{int((peaks > 100).sum())}/{int(ok.sum())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
