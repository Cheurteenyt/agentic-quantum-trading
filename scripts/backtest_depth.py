#!/usr/bin/env python
"""L'INDICATEUR DE MICRO-STRUCTURE — le déséquilibre du carnet d'ordres.

L'idée (standard en HFT, jamais testée sur Aster faute de données) : quand
les bids proches du mid pèsent beaucoup plus que les asks, les vendeurs
doivent « traverser » plus de liquidité pour faire baisser le prix → le mid
monte plus facilement. L'imbalance prédit le DRIFT des minutes suivantes.

Données : NOS carnets collectés 24/7 (depth.db — 4,4 M de niveaux).
Imbalance ∈ [-1, +1] = (bids − asks) / (bids + asks) dans ±0,5 % du mid.
Le drift mesuré : le changement de mid sur les N snapshots suivants.

La viabilité levier : un drift prédit de δ % à levier L = δ×L de marge,
contre les coûts — ET le MAE des minutes (la liquidation à 20x frappe à
2,5 % adverse sur les majeurs : les holds en minutes passent rarement ce
seuil — C'EST ça qui rend le 20x possible en micro-structure).

  .venv/bin/python scripts/backtest_depth.py --symbol BTCUSDT --minutes 5
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "warehouse" / "depth.db"
LEV = 20
COST_NOTIONAL = 0.18  # % notionnel RT (taker) — la version maker = 0.04
BAND = 0.5            # ± % du mid pour compter la liquidité


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--minutes", type=int, default=5)
    ap.add_argument("--lev", type=int, default=LEV)
    ap.add_argument("--force", action="store_true",
                    help="tourner même si la fenêtre < 14 j (aperçu)")
    args = ap.parse_args()

    con = sqlite3.connect(DB)
    mids = con.execute("SELECT ts, mid FROM depth_meta WHERE symbol = ? "
                       "ORDER BY ts", (args.symbol,)).fetchall()
    if len(mids) < 200:
        print(f"[depth] {args.symbol} : seulement {len(mids)} snapshots",
              file=sys.stderr)
        return 1
    mids_d = {t: m for t, m in mids}
    # le garde-fou fenêtre : le gisement est mûr à 14 jours glissants
    # (docs/21 P4) — en dessous, l'aperçu est indicatif seulement
    span_days = (mids[-1][0] - mids[0][0]) / 86400
    if span_days < 14 and not args.force:
        print(f"[depth] fenêtre {span_days:.1f} j / 14 — PAS MÛRE "
              f"(mûr ~06-07/10). --force pour l'aperçu indicatif.")
        return 0
    ts_list = [t for t, _ in mids]
    ts_pos_map = {t: i for i, t in enumerate(ts_list)}
    ts_set = set(ts_list)

    # imbalance par snapshot : liquidité ±BAND % autour du mid, par côté
    imb: dict[int, float] = {}
    rows = con.execute("SELECT ts, side, bin_price, qty FROM depth_bins "
                       "WHERE symbol = ? AND ts > ?",
                       (args.symbol, ts_list[0])).fetchall()
    con.close()
    liq_by = defaultdict(lambda: {"bid": 0.0, "ask": 0.0})
    for t, side, price, qty in rows:
        if t not in mids_d:
            continue
        mid = mids_d[t]
        if mid <= 0 or abs(price - mid) / mid > BAND / 100:
            continue
        notional = price * qty
        liq_by[t][side] += notional
    for t in ts_list:
        if t in liq_by:
            b, a = liq_by[t]["bid"], liq_by[t]["ask"]
            tot = b + a
            if tot > 0:
                imb[t] = (b - a) / tot

    # le drift forward : le mid N snapshots plus tard (1 snapshot ≈ POLL_SEC)
    poll_s = (ts_list[10] - ts_list[0]) / 10 if len(ts_list) > 10 else 10
    steps = max(1, int(args.minutes * 60 / poll_s))
    pairs: list[tuple[float, float]] = []
    ts_sorted = sorted(imb)
    for t in ts_sorted:
        i = ts_pos_map.get(t)
        if i is None:
            continue
        j = i + steps
        if j >= len(ts_list):
            continue
        t2 = ts_list[j]
        if t2 not in mids_d:
            continue
        drift = (mids_d[t2] / mids_d[t] - 1) * 100
        pairs.append((imb[t], drift))

    # les déciles d'imbalance → le drift moyen
    pairs.sort()
    n = len(pairs)
    dec = max(1, n // 10)
    print(f"=== {args.symbol} : imbalance → drift {args.minutes} min "
          f"(poll {poll_s:.0f}s, {n} snapshots) ===")
    print(f"{'Imbalance':16s} {'Drift moyen':>12s} {'WR drift':>10s}")
    decile_stats = []
    for d in range(10):
        chunk = pairs[d * dec: (d + 1) * dec]
        if not chunk:
            continue
        mean_imb = sum(i for i, _ in chunk) / len(chunk)
        mean_drift = sum(dr for _, dr in chunk) / len(chunk)
        wr = sum(1 for _, dr in chunk if dr > 0) / len(chunk) * 100
        decile_stats.append((mean_imb, mean_drift, wr, len(chunk)))
        print(f"{mean_imb:+8.3f}       {mean_drift:+9.4f} % {wr:9.1f} %")

    # la viabilité 20x : le décile extrême court vs le drift inverse
    if decile_stats:
        top = decile_stats[-1]
        bot = decile_stats[0]
        print(f"\nViabilité {args.lev}x (coûts taker {COST_NOTIONAL} % notionnel "
              f"= {COST_NOTIONAL*args.lev:.1f} % marge/RT) :")
        print(f"  décile haut : drift {top[1]:+.4f} % → marge {top[1]*args.lev:+.1f} % "
              f"(net {top[1]*args.lev - COST_NOTIONAL*args.lev:+.1f} %)")
        print(f"  décile bas  : drift {bot[1]:+.4f} % → marge {bot[1]*args.lev:+.1f} %")
        print(f"  MAE typique en {args.minutes} min : voir les bougies 15m "
              f"(le seuil de liquidation 20x = 2,5 % adverse sur les majeurs)")
        # la corrélation imbalance → drift (la force du signal)
        import statistics
        imbs = [i for i, _ in pairs]
        drs = [dr for _, dr in pairs]
        mi, md = sum(imbs)/n, sum(drs)/n
        cov = sum((a-mi)*(b-md) for a, b in zip(imbs, drs)) / n
        si = (sum((a-mi)**2 for a in imbs)/n) ** 0.5
        sd = (sum((b-md)**2 for b in drs)/n) ** 0.5
        if si > 0 and sd > 0:
            print(f"  corrélation imbalance→drift : {cov/(si*sd):+.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
