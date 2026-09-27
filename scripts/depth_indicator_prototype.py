#!/usr/bin/env python
"""PROTOTYPE — géométrie 0-liquidation sur le micro-drift d'imbalance.

PROTOTYPE 4,3-4,7 j (NON-MATURE) : le garde-fou du harnais (backtest_depth.py)
exige 14 j de fenêtre. Ce script refuse de tourner au-delà de l'aperçu sans
--force, et TOUT résultat est marqué NON-MATURE. Rejouer tel quel au 06-07/10.

La question : un drift de +0,009 %/5 min est mort à 20x (coûts taker), mais
la règle 0-liq (levier <= 100/(MAE+0.5)) autorise un levier énorme aux
micro-horizons SI le MAE 5-60 min est assez petit. On mesure :
  - grille : seuil imbalance {p70, p80, p90} (quantiles TRAIN 70 % par temps),
    horizon {5, 15, 30, 60} min, direction = AVEC l'imbalance ;
  - par cellule : drift médian, WR, MAE (p50/p90/max) => levier 0-liq max
    = 100/(MAE_max+0.5) => marge nette/trade = (drift - coût) x levier,
    annualisée (fréquence observée ET plafond séquentiel 1440/H trades/j) ;
  - variante maker (GTX 0 bps si fillé) : borne haute théorique — la loi
    d'exécution dit que les limites sélectionnent À L'ENVERS (elles ne fillent
    que quand le prix va contre toi) : à traiter comme optimum inaccessible.

  .venv/bin/python scripts/depth_indicator_prototype.py            (aperçu)
  .venv/bin/python scripts/depth_indicator_prototype.py --force    (idem)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "depth.db"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "ASTERUSDT"]  # les 3 plus couverts
BAND = 0.5                # ± % du mid pour compter la liquidité (harnais)
HORIZONS = (5, 15, 30, 60)          # minutes
QUANTILES = (0.70, 0.80, 0.90)      # seuils d'imbalance (quantiles TRAIN)
TRAIN_FRAC = 0.70                   # split train/val PAR LE TEMPS
COST_TAKER = 0.18   # % notionnel RT (frais 0.045x2 + slippage) — harnais
COST_MAKER = 0.04   # % notionnel RT si GTX fillé — BORNE HAUTE théorique
GUARD = 0.5         # marge anti-liq de la règle 100/(MAE+0.5)


def load_symbol(con: sqlite3.Connection, sym: str):
    mids = pd.read_sql_query(
        "SELECT ts, mid FROM depth_meta WHERE symbol = ? ORDER BY ts",
        con, params=(sym,))
    if len(mids) < 500:
        return None
    mid_of = dict(zip(mids.ts.values, mids.mid.values))
    ts_lo = int(mids.ts.iloc[0])
    liq_bid: dict[int, float] = {}
    liq_ask: dict[int, float] = {}
    for chunk in pd.read_sql_query(
            "SELECT ts, side, bin_price, qty FROM depth_bins WHERE symbol = ?",
            con, params=(sym,), chunksize=2_000_000):
        m = chunk.ts.map(mid_of)
        ok = m.notna() & ((chunk.bin_price - m).abs() / m <= BAND / 100)
        c = chunk[ok.values]
        m = m[ok.values]
        notion = (c.bin_price * c.qty).values
        is_bid = (c.side == "bid").values
        for t, n, b in zip(c.ts.values, notion, is_bid):
            if b:
                liq_bid[t] = liq_bid.get(t, 0.0) + n
            else:
                liq_ask[t] = liq_ask.get(t, 0.0) + n
    imb = {}
    for t in mids.ts.values:
        if t in liq_bid and t in liq_ask:
            tot = liq_bid[t] + liq_ask[t]
            if tot > 0:
                imb[t] = (liq_bid[t] - liq_ask[t]) / tot
    mids = mids[mids.ts.isin(imb.keys())].reset_index(drop=True)
    mids["imb"] = mids.ts.map(imb)
    return mids


def forward(mids: pd.DataFrame, horizon_min: int, poll_s: float):
    """drift/MAE long et short sur la fenêtre [t, t+H] (granularité snapshot).

    MAE = excursion la plus adverse du mid, sens du trade inclus. La fenêtre
    min/max déborde d'au plus 1 poll après H : MAE légèrement surestimé => levier prudent.
    """
    ts = mids.ts.values.astype(np.int64)
    mid = mids.mid.values
    h = horizon_min * 60
    k = max(2, int(round(h / poll_s)) + 1)
    j = np.searchsorted(ts, ts + h, side="right") - 1
    valid = (j > np.arange(len(ts))) & (ts[j] - ts <= int(h * 1.5))
    s = pd.Series(mid)
    roll_min = s.rolling(k, min_periods=1).min().shift(-(k - 1)).values
    roll_max = s.rolling(k, min_periods=1).max().shift(-(k - 1)).values
    drift = (mid[j] / mid - 1) * 100                      # sens long
    mae_long = np.clip((mid - roll_min) / mid * 100, 0, None)
    mae_short = np.clip((roll_max - mid) / mid * 100, 0, None)
    drift = np.where(valid, drift, np.nan)
    for a in (mae_long, mae_short):
        a[~valid] = np.nan
    return drift, mae_long, mae_short


def stats(sub: pd.DataFrame, cost: float) -> dict:
    n = len(sub)
    if n < 30:
        return {}
    med = sub.drift.median()
    wr = (sub.drift > 0).mean() * 100
    mae_max = sub.mae.max()
    lev = 100.0 / (mae_max + GUARD)
    net = (med - cost) * lev
    return dict(n=n, med=med, wr=wr, mae50=sub.mae.quantile(.5),
                mae90=sub.mae.quantile(.9), mae_max=mae_max, lev=lev, net=net)


def cell_rows(sym, mids, q, horizon, drift, mae_long, mae_short, freq_cap,
              span_days):
    imb = mids.imb.values
    n_tr = int(len(mids) * TRAIN_FRAC)
    thr_long = np.nanquantile(imb[:n_tr], q)
    thr_short = np.nanquantile(imb[:n_tr], 1 - q)
    rows = []
    for side, mask in (("long", imb >= thr_long), ("short", imb <= thr_short)):
        mae = mae_long if side == "long" else mae_short
        d = drift[mask]
        a = mae[mask]
        split = np.arange(len(mids))[mask] < n_tr
        for tag, sl in (("train", split), ("val", ~split)):
            sub = pd.DataFrame({"drift": d[sl], "mae": a[sl]}).dropna()
            st = stats(sub, COST_TAKER)
            if not st:
                continue
            st.update(symbol=sym, side=side, q=q, h=horizon, tag=tag,
                      thr=thr_long if side == "long" else thr_short,
                      net_maker=(st["med"] - COST_MAKER) * st["lev"],
                      ann_obs=st["net"] * st["n"] / span_days * 365,
                      ann_seq=st["net"] * min(st["n"] / span_days, freq_cap) * 365)
            rows.append(st)
    return rows


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    all_rows, mae_glob = [], []
    for sym in SYMBOLS:
        mids = load_symbol(con, sym)
        if mids is None:
            print(f"[proto] {sym} : pas assez de snapshots", file=sys.stderr)
            continue
        span_d = (mids.ts.iloc[-1] - mids.ts.iloc[0]) / 86400
        if span_d < 14:
            print(f"[proto] {sym} : fenêtre {span_d:.1f} j / 14 — NON-MATURE "
                  f"(aperçu --force)", file=sys.stderr)
        poll_s = float(np.median(np.diff(mids.ts.values)))
        for h in HORIZONS:
            drift, ml, ms = forward(mids, h, poll_s)
            imbs = mids.imb.values
            base = pd.DataFrame({
                "drift": np.where(imbs >= 0, drift, -drift),
                "mae": np.where(imbs >= 0, ml, ms),
            }).dropna()
            mae_glob.append((sym, h, base.mae.quantile(.5),
                             base.mae.quantile(.9), base.mae.max()))
            freq_cap = 1440.0 / h
            for q in QUANTILES:
                all_rows += cell_rows(sym, mids, q, h, drift, ml, ms,
                                      1440.0 / h, span_d)
    con.close()

    df = pd.DataFrame(all_rows)
    pd.set_option("display.width", 200)
    print("\n=== PROTOTYPE NON-MATURE (~4,7 j) — imbalance -> micro-drift, "
          "géométrie 0-liq ===")
    print("coûts taker 0.18 % RT notionnel ; levier 0-liq = 100/(MAE_max+0.5) ; "
          "marge nette = (drift_med - coût) x levier\n")
    print("--- MAE par horizon, TOUS snapshots (p50/p90/max, %) ---")
    for sym, h, p50, p90, mx in mae_glob:
        print(f"  {sym:11s} {h:2d} min : p50 {p50:.3f}  p90 {p90:.3f}  "
              f"max {mx:.3f}")
    val = df[df.tag == "val"].sort_values("ann_seq", ascending=False)
    cols = ["symbol", "side", "q", "h", "n", "med", "wr", "mae90", "mae_max",
            "lev", "net", "net_maker", "ann_obs", "ann_seq"]
    hdr = (f"{'sym':10s} {'side':5s} {'q':4s} {'H':3s} {'n':>5s} "
           f"{'drift%':>8s} {'WR%':>6s} {'MAE90':>6s} {'MAEmax':>7s} "
           f"{'lev0liq':>7s} {'net%/tr':>8s} {'netMK':>7s} {'an(obs)':>9s} "
           f"{'an(seq)':>9s}")
    print("\n--- VAL (30 % finaux, seuils figés sur TRAIN) — top 15 par an(seq) ---")
    print(hdr)
    for r in val.head(15).itertuples():
        print(f"{r.symbol:10s} {r.side:5s} p{int(r.q*100):<3d} {r.h:3d} "
              f"{r.n:5d} {r.med:+8.4f} {r.wr:6.1f} {r.mae90:6.3f} "
              f"{r.mae_max:7.3f} {r.lev:7.1f} {r.net:+8.2f} {r.net_maker:+7.2f} "
              f"{r.ann_obs:+9.0f} {r.ann_seq:+9.0f}")
    print("\n--- TRAIN (70 % initiaux, mêmes seuils) — top 10 ---")
    print(hdr)
    trn = df[df.tag == "train"].sort_values("ann_seq", ascending=False)
    for r in trn.head(10).itertuples():
        print(f"{r.symbol:10s} {r.side:5s} p{int(r.q*100):<3d} {r.h:3d} "
              f"{r.n:5d} {r.med:+8.4f} {r.wr:6.1f} {r.mae90:6.3f} "
              f"{r.mae_max:7.3f} {r.lev:7.1f} {r.net:+8.2f} {r.net_maker:+7.2f} "
              f"{r.ann_obs:+9.0f} {r.ann_seq:+9.0f}")
    df.to_csv(ROOT / "reports" / "depth-proto-cells-2026-09-27.csv", index=False)
    print(f"\n[proto] cellules -> reports/depth-proto-cells-2026-09-27.csv "
          f"({len(df)} lignes). NON-MATURE : rejouer au 06-07/10 sur 14 j.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
