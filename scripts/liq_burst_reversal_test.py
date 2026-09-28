#!/usr/bin/env python3
"""Les bursts de liquidations → rebond d'épuisement ? (28/09, 6 j de
liq_events) — l'hypothèse : une burst de longs liquidés épuise les
vendeurs → le rebond. VERDICT MESURÉ : l'INVERSE (continuation) —
re-test à 14 j de couverture."""
import sys, sqlite3
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
con = sqlite3.connect(str(Path(__file__).resolve().parents[1] / "data" / "warehouse" / "klines.db"))

bursts = con.execute("""SELECT symbol, MAX(event_time) as last_ts, COUNT(*), SUM(notional)
                        FROM liq_events WHERE side='SELL'
                        GROUP BY symbol, CAST(event_time/3600000 AS INTEGER)
                        HAVING COUNT(*) >= 3 AND SUM(notional) >= 20000""").fetchall()
print(f"bursts (≥3 SELL/1h, ≥$20k) : {len(bursts)}")

prices = {}
for s in set(b[0] for b in bursts):
    rows = con.execute("SELECT open_time, close FROM klines WHERE symbol=? AND interval='1h' ORDER BY open_time", (s,)).fetchall()
    prices[s] = (np.array([r[0] for r in rows]), np.array([r[1] for r in rows]))

def fwd(sym, ts_ms, hours):
    ot, cl = prices.get(sym, (None, None))
    if ot is None or not len(ot): return None
    i = int(np.searchsorted(ot, ts_ms, side="right")) - 1
    j = i + hours
    if j >= len(cl) or i < 0: return None
    return (cl[j] / cl[i] - 1) * 100

res, edges = {1: [], 4: [], 24: []}, {1: [], 4: [], 24: []}
for sym, last_ts, n, notional in bursts:
    base_h = None
    if sym in prices and len(prices[sym][1]) > 1:
        ot, cl = prices[sym]
        rets = (cl[1:] / cl[:-1] - 1) * 100
        base_h = float(np.mean(rets))
    for h in (1, 4, 24):
        f = fwd(sym, last_ts, h)
        if f is None: continue
        res[h].append(f)
        edges[h].append(f - (base_h * h) if base_h is not None else f)

print("\nh    |  n  | ret post-burst | edge vs calme")
for h in (1, 4, 24):
    v, ed = res[h], edges[h]
    if v:
        print(f"+{h:2d}h | {len(v):3d} | {np.mean(v):+.3f} % | {np.mean(ed):+.3f} pts | "
              f"{'REBOND' if np.mean(ed) > 0 else 'CONTINUATION'}")
for nmin, nm in ((5, "≥5"), (8, "≥8")):
    b2 = [b for b in bursts if b[2] >= nmin]
    v2 = [f for b in b2 for h in [4] if (f := fwd(b[0], b[1], 4)) is not None]
    if v2:
        print(f"bursts {nm} SELL (n={len(v2)}) : ret +4h {np.mean(v2):+.3f} %")
