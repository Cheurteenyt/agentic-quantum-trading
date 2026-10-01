#!/usr/bin/env python
"""T20 — Régimes d'ordre-flow sur le tape Aster 90 j (BTC/ETH aggTrades).

DB : data/warehouse/klines.db en LECTURE SEULE (aster_tape + klines 1m).
Écrit : reports/aster_orderflow_regimes_raw.json + reports/aster_orderflow_regimes_days.csv.

Piège T17 : 0,02 % des prints ont un recul ts_ms (ids par workers) → tri par
(ts_ms, agg_id) AVANT toute mesure d'ordre. Lecture triée par agg_id (index PK),
puis np.lexsort((agg_id, ts_ms)) = ordre (ts_ms, agg_id) exact.

Split temporel : jours pleins 07-04..09-30 (89 j) → train = 60 premiers (07-04..09-01),
val = 29 derniers (09-02..09-30). Seuils de régime choisis sur TRAIN uniquement.
4 définitions (multiplicité comptée) :
  D1  binaire 1 j > médiane(train)
  D2  binaire 3 j > médiane(train)   [principale, mission]
  D3  binaire 3 j > p25(train)       [variabilité en val]
  Z   z-score continu 3 j (mu/sigma train)
Verdict direction : AUC(régime → ret_fwd 24 h > 0), règle x501 train>=0.60 ET val>=0.60.
"""
import json
import datetime as dt
import sqlite3

import numpy as np
import pandas as pd

ROOT = "/run/media/cheurteen/Jeux SSD/trading-agent"
DB = f"file:{ROOT}/data/warehouse/klines.db?mode=ro"
DAY = 86_400_000
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
OUT_JSON = f"{ROOT}/reports/aster_orderflow_regimes_raw.json"
OUT_CSV = f"{ROOT}/reports/aster_orderflow_regimes_days.csv"
N_TRAIN = 60


def rankdata_avg(x):
    """Rangs moyens (ties averaged), sans scipy."""
    x = np.asarray(x, dtype=np.float64)
    sorter = np.argsort(x, kind="mergesort")
    inv = np.empty_like(sorter)
    inv[sorter] = np.arange(len(x))
    xs = x[sorter]
    obs = np.r_[True, xs[1:] != xs[:-1]]
    dense = obs.cumsum()[inv]
    count = np.r_[np.nonzero(obs)[0], len(obs)]
    return 0.5 * (count[dense] + count[dense - 1] + 1)


def auc(score, y):
    """AUC par rangs (Mann-Whitney). score continu ou binaire, y en {0,1}."""
    score = np.asarray(score, dtype=np.float64)
    y = np.asarray(y).astype(bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    r = rankdata_avg(score)
    return float((r[y].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def pearson(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a, b):
    return pearson(rankdata_avg(a), rankdata_avg(b))


def load_tape(con, sym):
    """Lecture par index PK (symbol, agg_id), chunkée, puis tri (ts_ms, agg_id)."""
    cur = con.execute(
        "SELECT agg_id, ts_ms, price, qty, is_buyer_maker FROM aster_tape "
        "WHERE symbol=? ORDER BY agg_id",
        (sym,),
    )
    cols = [[], [], [], [], []]
    while True:
        rows = cur.fetchmany(500_000)
        if not rows:
            break
        for c, vals in zip(cols, zip(*rows)):
            c.extend(vals)
    agg_id = np.asarray(cols[0], dtype=np.int64)
    ts = np.asarray(cols[1], dtype=np.int64)
    price = np.asarray(cols[2], dtype=np.float64)
    qty = np.asarray(cols[3], dtype=np.float64)
    ibm = np.asarray(cols[4], dtype=np.int8)
    n_recul = int((np.diff(ts) < 0).sum())  # propriété source (ids par workers)
    order = np.lexsort((agg_id, ts))  # tri (ts_ms, agg_id) exact
    ts, price, qty, ibm = ts[order], price[order], qty[order], ibm[order]
    assert np.all(np.diff(ts) >= 0), "tri (ts_ms, agg_id) non monotone"
    return ts, price, qty, ibm, n_recul


def daily_from_tape(ts, price, qty, ibm):
    d0, d1 = int(ts[0] // DAY), int(ts[-1] // DAY)
    di = (ts // DAY) - d0
    n = d1 - d0 + 1
    buy = np.bincount(di, weights=qty * (1 - ibm), minlength=n)
    sell = np.bincount(di, weights=qty * ibm, minlength=n)
    dates = [
        dt.datetime.fromtimestamp((d0 + i) * DAY / 1000, dt.UTC).date().isoformat()
        for i in range(n)
    ]
    return pd.DataFrame(
        {
            "date": dates,
            "prints": np.bincount(di, minlength=n).astype(np.int64),
            "buy_vol": buy,
            "sell_vol": sell,
            "notional": np.bincount(di, weights=qty * price, minlength=n),
            "cvd": buy - sell,
        }
    )


def daily_closes_1m(con, sym, t0_ms, t1_ms):
    q = (
        "SELECT open_time, close FROM klines WHERE symbol=? AND interval='1m' "
        "AND open_time>=? AND open_time<?"
    )
    k = pd.read_sql_query(q, con, params=(sym, t0_ms, t1_ms + DAY))
    k["d"] = k["open_time"] // DAY
    g = k.groupby("d")["close"]
    closes = g.last()
    bars = g.size()
    dates = [
        dt.datetime.fromtimestamp(d * DAY / 1000, dt.UTC).date().isoformat()
        for d in closes.index
    ]
    out = pd.DataFrame({"date": dates, "close": closes.values, "bars_1m": bars.values})
    out["ret"] = out["close"].pct_change()
    out["fwd"] = out["close"].shift(-1) / out["close"] - 1.0
    return out


def runs(regime_bool, dates):
    """Runs contigus du régime True (=HIGH)."""
    out, cur = [], None
    for r, d in zip(regime_bool, dates):
        if r:
            if cur is None:
                cur = [d, d, 1]
            else:
                cur[1], cur[2] = d, cur[2] + 1
        elif cur is not None:
            out.append(tuple(cur))
            cur = None
    if cur is not None:
        out.append(tuple(cur))
    return out


def main():
    con = sqlite3.connect(DB, uri=True)
    results, day_frames = {}, []

    for sym in SYMBOLS:
        ts, price, qty, ibm, n_recul = load_tape(con, sym)
        d = daily_from_tape(ts, price, qty, ibm)
        d["speed_pm"] = d["prints"] / 1440.0
        d["buy_ratio"] = d["buy_vol"] / (d["buy_vol"] + d["sell_vol"])

        t0 = int(ts[0] // DAY) * DAY
        t1 = int(ts[-1] // DAY) * DAY
        k = daily_closes_1m(con, sym, t0, t1)
        d = d.merge(k, on="date", how="left")
        d["abs_ret"] = d["ret"].abs()
        d["abs_fwd"] = d["fwd"].abs()

        # Jours pleins (on retire le 1er et le dernier jour du tape, partiels)
        d_full = d.iloc[1:-1].reset_index(drop=True).copy()
        d_full["dens3"] = d_full["prints"].rolling(3).mean()

        # Seuils sur TRAIN uniquement (60 premiers jours pleins)
        tr = d_full.iloc[:N_TRAIN]
        va = d_full.iloc[N_TRAIN:]
        med = float(tr["prints"].median())
        p25 = float(tr["prints"].quantile(0.25))
        mu, sd = float(tr["dens3"].mean()), float(tr["dens3"].std())

        d_full["D1"] = (d_full["prints"] > med).astype(int)
        d_full["D2"] = (d_full["dens3"] > med).astype(int)
        d_full["D3"] = (d_full["dens3"] > p25).astype(int)
        d_full["Z"] = (d_full["dens3"] - mu) / sd
        d_full["split"] = np.where(
            np.arange(len(d_full)) < N_TRAIN, "train", "val"
        )
        d_full["symbol"] = sym
        day_frames.append(d_full)

        r = {
            "n_rows": int(len(ts)),
            "n_ts_recul": n_recul,
            "span": [d["date"].iloc[0], d["date"].iloc[-1]],
            "thresholds_train": {"median_1j": med, "p25_3j": p25,
                                 "dens3_mu": mu, "dens3_sd": sd},
            "train_days": [tr["date"].iloc[0], tr["date"].iloc[-1]],
            "val_days": [va["date"].iloc[0], va["date"].iloc[-1]],
            "mean_prints_per_day": {
                "train": float(tr["prints"].mean()),
                "val": float(va["prints"].mean()),
                "last7": float(d_full["prints"].tail(7).mean()),
            },
            "corr_density_absret": {
                "train_pearson": pearson(tr["prints"], tr["abs_ret"]),
                "train_spearman": spearman(tr["prints"], tr["abs_ret"]),
                "val_pearson": pearson(va["prints"], va["abs_ret"]),
                "val_spearman": spearman(va["prints"], va["abs_ret"]),
                "train_spearman_speed": spearman(tr["speed_pm"], tr["abs_ret"]),
            },
            "flow_by_regime_D2": {},
            "prediction": {},
        }

        # Flux par régime D2 (agressivité, vitesse, CVD) — par split
        for sp, sub in d_full.dropna(subset=["dens3"]).groupby("split"):
            for reg, g in sub.groupby("D2"):
                r["flow_by_regime_D2"][f"{sp}_{'HIGH' if reg else 'LOW'}"] = {
                    "n_days": int(len(g)),
                    "prints_per_day": float(g["prints"].mean()),
                    "speed_prints_per_min": float(g["speed_pm"].mean()),
                    "buy_ratio_vol": float(
                        g["buy_vol"].sum() / (g["buy_vol"].sum() + g["sell_vol"].sum())
                    ),
                    "cvd_day_mean_coins": float(g["cvd"].mean()),
                    "cvd_day_pct_of_vol": float(
                        (g["cvd"] / (g["buy_vol"] + g["sell_vol"])).mean()
                    ),
                    "abs_ret_mean": float(g["abs_ret"].mean()),
                    "abs_fwd_mean": float(g["abs_fwd"].mean()),
                }

        # Prédiction : régime courant → ret_fwd 24 h
        p = d_full.dropna(subset=["fwd", "dens3"]).copy()
        ptr = p[p["split"] == "train"]
        pva = p[p["split"] == "val"]
        for name, score_col in [("D1", "D1"), ("D2", "D2"), ("D3", "D3"), ("Z", "Z")]:
            entry = {}
            for sp, sub in [("train", ptr), ("val", pva)]:
                s = sub[score_col].to_numpy()
                y = (sub["fwd"].to_numpy() > 0).astype(int)
                e = {
                    "n": int(len(sub)),
                    "auc_dir": auc(s, y),
                    "auc_vol": auc(np.abs(sub["fwd"].to_numpy()), (s > 0).astype(int)),
                    "spearman_fwd": spearman(s, sub["fwd"].to_numpy()),
                    "spearman_absfwd": spearman(s, np.abs(sub["fwd"].to_numpy())),
                    "score_std": float(np.std(s)),
                }
                entry[sp] = e
            entry["x501_ok"] = bool(
                entry["train"]["auc_dir"] is not None
                and entry["val"]["auc_dir"] is not None
                and entry["train"]["auc_dir"] >= 0.60
                and entry["val"]["auc_dir"] >= 0.60
            )
            r["prediction"][name] = entry

        r["runs_D2"] = [
            {"start": a, "end": b, "n_days": n}
            for a, b, n in runs(
                d_full["dens3"].notna() & (d_full["D2"] == 1),
                list(d_full["date"]),
            )
        ]
        results[sym] = r

        print(f"\n=== {sym} === rows={r['n_rows']} recul_ts={n_recul}")
        print(
            f"train {r['train_days']} mean={r['mean_prints_per_day']['train']:.0f} prints/j | "
            f"val {r['val_days']} mean={r['mean_prints_per_day']['val']:.0f} | "
            f"last7={r['mean_prints_per_day']['last7']:.0f}"
        )
        print(f"seuils train: median={med:.0f} p25_3j={p25:.0f} mu3j={mu:.0f} sd={sd:.0f}")
        for kk, vv in r["flow_by_regime_D2"].items():
            print(
                f"  {kk:11s} n={vv['n_days']:3d} {vv['prints_per_day']:8.0f} p/j "
                f"buy%={vv['buy_ratio_vol']*100:.2f} cvd/vol={vv['cvd_day_pct_of_vol']*100:+.2f}% "
                f"|ret|={vv['abs_ret_mean']*100:.2f}% |fwd|={vv['abs_fwd_mean']*100:.2f}%"
            )
        for name, e in r["prediction"].items():
            at, av = e["train"]["auc_dir"], e["val"]["auc_dir"]
            print(
                f"  {name}: AUC_dir train={at:.3f} val={av if av is None else round(av,3)} "
                f"n={e['train']['n']}/{e['val']['n']} x501={e['x501_ok']} "
                f"AUC_vol train={e['train']['auc_vol']:.3f} val="
                f"{e['val']['auc_vol'] if e['val']['auc_vol'] is None else round(e['val']['auc_vol'],3)}"
            )
        print(
            f"  corr dens×|ret| train sp={r['corr_density_absret']['train_spearman']:.3f} "
            f"val sp={r['corr_density_absret']['val_spearman']:.3f}"
        )
        print("  runs D2:", r["runs_D2"])

    pd.concat(day_frames, ignore_index=True).to_csv(OUT_CSV, index=False)
    with open(OUT_JSON, "w") as f:
        json.dump(results, f, indent=1, default=float)
    print(f"\nOK -> {OUT_JSON}\nOK -> {OUT_CSV}")


if __name__ == "__main__":
    main()
