#!/usr/bin/env python3
"""x501 — BASELINE 6 ANS v29 : mesure de la base économique sur l'horizon max.
Entrées (om_v27.db): bn_kline_1h_deep (9 sym, 2019-09→2026-10), bb_kline_1h_deep
(12 sym, planchers Bybit), bn_funding_deep (ts secondes).
Sorties: scripts/x501_v21_results/baseline_6y_v29.json

Métriques par symbole et par année civile:
  - f24  : move forward 24 h en bps (close[t+24]/close[t]-1) — E, MED
  - MFE48: max(high[t..t+47])/close[t]-1 ; MAE48: min(low[t..t+47])/close[t]-1
  - vol realised annualisée
  - funding APR (somme des rates × 1095)  [Binance]
  - buy&hold annuel (contexte régime)
Agrégats: split 60/40 chrono GLOBAL (stationnarité de E[f24]), cohérence
cross-venue BB vs BN (bps, overlap), trous de données horaires.
Aucune décision de signal ici — baseline DIAG, protocole v27 inchangé.
"""
import sqlite3, json, numpy as np, pandas as pd, datetime as dt

DB = "scripts/x501_v21_results/om_v27.db"
OUT = "scripts/x501_v21_results/baseline_6y_v29.json"
BN = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LINKUSDT",
      "DOGEUSDT", "SOLUSDT", "AVAXUSDT"]
BB12 = ["1000PEPEUSDT", "ADAUSDT", "APTUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT",
        "DOGEUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT"]

db = sqlite3.connect(DB)

def year_of(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).year

def per_year_metrics(sym, df):
    """df: index ts (ms asc), colonnes close, high, low."""
    out = {}
    c = df["close"]
    f24 = (c.shift(-24) / c - 1) * 10_000          # bps
    mfe48 = (df["high"].rolling(48).max().shift(-48) / c - 1) * 100  # %
    mae48 = (df["low"].rolling(48).min().shift(-48) / c - 1) * 100   # %
    ret1h = c.pct_change()
    years = df.index.map(year_of)
    df2 = pd.DataFrame({"y": years, "f24": f24.values, "mfe": mfe48.values,
                        "mae": mae48.values, "r1": ret1h.values}, index=df.index)
    for y, g in df2.groupby("y"):
        g = g.dropna(subset=["f24"])
        if len(g) < 500:
            continue
        vol = float(np.nanstd(g["r1"]) * np.sqrt(24 * 365) * 100)
        out[str(y)] = {
            "n_hours": int(len(g)),
            "f24_mean_bps": round(float(g["f24"].mean()), 1),
            "f24_med_bps": round(float(g["f24"].median()), 1),
            "mfe48_med_pct": round(float(g["mfe"].median()), 2),
            "mae48_med_pct": round(float(g["mae"].median()), 2),
            "bh_pct": round(float((c[g.index[-1]] / c[g.index[0]] - 1) * 100), 1) if g.index[-1] in c.index else None,
            "vol_ann_pct": round(vol, 1),
        }
    return out

def funding_per_year(sym):
    rows = db.execute("SELECT ts, rate FROM bn_funding_deep WHERE symbol=? ORDER BY ts", (sym,)).fetchall()
    out = {}
    if not rows:
        return out
    d = pd.DataFrame(rows, columns=["ts", "rate"])
    d["y"] = d["ts"].map(lambda s: dt.datetime.fromtimestamp(s, dt.timezone.utc).year)
    for y, g in d.groupby("y"):
        if len(g) < 30:
            continue
        # 3 fundings/jour -> APR = moyenne × 1095
        out[str(y)] = {"n": int(len(g)), "apr_pct": round(float(g["rate"].mean()) * 1095 * 100, 1),
                       "med_bps_8h": round(float(g["rate"].median()) * 10_000, 2)}
    return out

def main():
    res = {"symbols_binance_6y": {}, "symbols_bybit": {}, "cross_venue": {}, "gaps": {}}

    # ---- 1) Baseline par année — Binance deep (6-7 ans)
    for sym in BN:
        rows = db.execute("SELECT ts, open, high, low, close FROM bn_kline_1h_deep WHERE symbol=? ORDER BY ts", (sym,)).fetchall()
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"]).set_index("ts")
        res["symbols_binance_6y"][sym] = {
            "n": len(df),
            "from": dt.datetime.fromtimestamp(df.index[0] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
            "to": dt.datetime.fromtimestamp(df.index[-1] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
            "years": per_year_metrics(sym, df),
            "funding_years": funding_per_year(sym),
        }
        print(f"BN {sym} {len(df)} barres", flush=True)

    # ---- 2) Bybit 12 symboles (fenêtre commune 3,42 ans)
    for sym in BB12:
        rows = db.execute("SELECT ts, open, high, low, close FROM bb_kline_1h_deep WHERE symbol=? ORDER BY ts", (sym,)).fetchall()
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"]).set_index("ts")
        res["symbols_bybit"][sym] = {
            "n": len(df),
            "from": dt.datetime.fromtimestamp(df.index[0] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
            "to": dt.datetime.fromtimestamp(df.index[-1] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
            "years": per_year_metrics(sym, df),
        }
        print(f"BB {sym} {len(df)} barres", flush=True)

    # ---- 3) Stationnarité: split 60/40 chrono GLOBAL (pool BN 9 symboles empilés puis tri ts)
    frames = []
    for sym in BN:
        rows = db.execute("SELECT ts, close FROM bn_kline_1h_deep WHERE symbol=? ORDER BY ts", (sym,)).fetchall()
        d = pd.DataFrame(rows, columns=["ts", "close"])
        d["f24"] = (d["close"].shift(-24) / d["close"] - 1) * 10_000
        d["sym"] = sym
        frames.append(d.dropna())
    pool = pd.concat(frames).sort_values("ts").reset_index(drop=True)
    k = int(len(pool) * 0.6)
    tr, te = pool.iloc[:k], pool.iloc[k:]
    res["stationarity_f24"] = {
        "n_total": int(len(pool)),
        "train": {"n": int(len(tr)), "f24_mean_bps": round(float(tr["f24"].mean()), 1),
                  "cut": dt.datetime.fromtimestamp(tr["ts"].iloc[-1] / 1000, dt.timezone.utc).strftime("%Y-%m-%d")},
        "test": {"n": int(len(te)), "f24_mean_bps": round(float(te["f24"].mean()), 1),
                 "from": dt.datetime.fromtimestamp(te["ts"].iloc[0] / 1000, dt.timezone.utc).strftime("%Y-%m-%d")},
        "med_total_bps": round(float(pool["f24"].median()), 1),
    }

    # ---- 4) Cohérence cross-venue (overlap BB vs BN, close)
    diffs = []
    for sym in BN:
        a = {r[0]: r[1] for r in db.execute("SELECT ts, close FROM bn_kline_1h_deep WHERE symbol=?", (sym,))}
        b = db.execute("SELECT ts, close FROM bb_kline_1h_deep WHERE symbol=?", (sym,)).fetchall()
        dd = [abs(a[t] - c) / c * 10_000 for t, c in b if t in a]
        if dd:
            diffs.append({"sym": sym, "n": len(dd), "med_bps": round(float(np.median(dd)), 1),
                          "p99_bps": round(float(np.percentile(dd, 99)), 1)})
    res["cross_venue"] = diffs

    # ---- 5) Trous horaires (klines) par table
    for tab, syms in (("bn_kline_1h_deep", BN), ("bb_kline_1h_deep", BB12)):
        g = {}
        for sym in syms:
            ts = [r[0] for r in db.execute(f"SELECT ts FROM {tab} WHERE symbol=? ORDER BY ts", (sym,))]
            arr = np.diff(np.array(ts)) / 3_600_000
            holes = int((arr > 1.5).sum())
            max_hole = float(arr.max()) if len(arr) else 0.0
            if holes or max_hole > 2:
                g[sym] = {"n_holes": holes, "max_hole_h": round(max_hole, 1)}
        res["gaps"][tab] = g

    json.dump(res, open(OUT, "w"), indent=1)
    print("OK ->", OUT)
    print("Stationnarité f24:", res["stationarity_f24"])

if __name__ == "__main__":
    main()
