#!/usr/bin/env python3
"""La lecture structurelle précoce de l'OI (28/09, ~2 j de snapshots 15 min)
— la géographie + la corrélation instantanée ΔOI×Δprix. Le tir H4/H5
(les quadrants 90 min) reste le test décisif de jeudi."""
import sys, sqlite3
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
con = sqlite3.connect(str(Path(__file__).resolve().parents[1] / "data" / "warehouse" / "klines.db"), timeout=60)

print("=== GÉOGRAPHIE OI (top 10 par OI moyen) ===")
for r in con.execute("""SELECT symbol, AVG(open_interest), COUNT(*) FROM oi_history
                        GROUP BY symbol ORDER BY 2 DESC LIMIT 10"""):
    print(f"  {r[0]:<14} OI moyen {r[1]:,.0f}  ({r[2]} snaps)")

print("\n=== CORRÉLATION ΔOI × ΔPRIX (15 min) ===")
corrs = {}
for (s,) in con.execute("SELECT DISTINCT symbol FROM oi_history").fetchall():
    rows = con.execute("""SELECT captured_at_ms, open_interest, price FROM oi_history
                          WHERE symbol=? ORDER BY captured_at_ms""", (s,)).fetchall()
    if len(rows) < 20:
        continue
    oi = np.array([r[1] for r in rows]); px = np.array([r[2] for r in rows])
    d_oi = np.diff(oi) / oi[:-1] * 100; d_px = np.diff(px) / px[:-1] * 100
    if len(d_oi) > 15 and np.std(d_oi) > 0 and np.std(d_px) > 0:
        corrs[s] = float(np.corrcoef(d_oi, d_px)[0, 1])
for s, c in sorted(corrs.items(), key=lambda x: -abs(x[1]))[:8]:
    print(f"  {s:<14} corr {c:+.3f}")
if corrs:
    print(f"\nmoyenne : {np.mean(list(corrs.values())):+.3f} — 0 = le positionnement ne bouge pas avec le prix à 15 min")
