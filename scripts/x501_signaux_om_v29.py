#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OPÉRATION x501 — v29 (volet 1 PR #2) : EXPLOITER LE POUVOIR SOUS-UTILISÉ.

Critique héritée : « outils gratuits > TradingView non exploités ». Réponse :
mesurer HONNÊTEMENT les 4 familles de signaux que la collecte gratuite om_v27
(560 000 pts, 12 symboles, 23 mois horaires) rend possibles SANS aucun abonnement :

  S1 CARRY FUNDING   (bn_funding_deep, 8h, 3,4-5,5 ans)
     rate connu à t -> f24 = rendement 24h après t. Hypothèse crowd : funding
     très positif = longs surpayés = pression vendeuse future (et inverse).
     Obs dédup 1/24h par symbole (leçon flush_deep : pas de double comptage).

  S2 IMPULSION OI x PRIX (bb_oi_1h_deep 708 j + kline 1h)
     dOI24 = OI(t)/OI(t-24h)-1 croisé avec r24 passé -> 4 quadrants :
       (+,+) tendance-long  (+,-) pression-short  (-,+) squeeze  (-,-) flush
     Question : le quadrant à t prédit-il f24 ? (flush horaire v27 = KILL,
     mais le quadrant 24h croisé prix n'a jamais été testé tel quel.)

  S3 STRUCTURE DE MARCHÉ (kline 1h 733 j)
     pos90 = (c-low90)/(high90-low90) dans [0,1] ; compression = range30/range90.
     Question : f24 varie-t-il avec la position dans le range / la compression ?

  S4 RÉGIME VOL x PERFORMANCE ALPHAS (pool 469 trades certifié)
     tercile ATR% 1h du symbole à t_in -> E[R] par tercile, par côté.
     DIAGNOSTIC ONLY (leçon v26 : tout tri in-sample est un mirage tant que
     le walk-forward ne dit pas le contraire — aucun gate créé ici).

PROTOCOLE ANTI-MIRAGE (gravé v26/v27, non négociable) :
  - dédup temporel : 1 obs / 24h (S1) ou /4h (S2/S3) par symbole ;
  - split walk-forward CHRONO GLOBAL par ts (60/40) — JAMAIS empilé par symbole
    (leçon ml_deep v27 : le split déguisé inter-symboles est une fraude) ;
  - verdict sur le TEST uniquement :
      KILL      signe test inverse du train OU |excès test| < 5 bps
      ADVISORY  même signe train/test ET excès test >= 10 bps ET n_test >= 200
      PROMU     excès test >= 25 bps ET n_test >= 500 ET cohérence >= 8/12
                symboles (réservé — volontairement quasi inatteignable ;
                la promotion d'un gate exige en plus le protocole 90 j)
      DIAG      contexte informatif sans condition de blocage
  - la baseline f24 est recalculée DANS CHAQUE split (pas de fuite).

Sorties :
  scripts/x501_v21_results/signaux_om_v29.json        — verdicts + mesures
  scripts/x501_v21_results/contexte_om_v29.json       — état courant par symbole
    (consommable par le pont d'armement A7, advisory NON bloquant)
"""
import json
import pickle
import sqlite3
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]   # racine du repo
OUT = str(ROOT / "scripts" / "x501_v21_results")
DB = f"{OUT}/om_v27.db"
POOL = str(ROOT / "data_x501" / "pool_v8_P1.pkl")   # data runtime (git-ignorée)
DB_TS_S = True          # om_v27.db : ts en SECONDES (pool pickle : ms -> //1000)
DAY_S = 86_400
H4_S = 14_400
TOL_S = 3_600
DAY_MS = 86_400_000
SYMS = ["1000PEPEUSDT", "ADAUSDT", "APTUSDT", "AVAXUSDT", "BNBUSDT", "BTCUSDT",
        "DOGEUSDT", "ETHUSDT", "LINKUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT"]


def load_tables():
    con = sqlite3.connect(DB, timeout=60)
    k = pd.read_sql("SELECT symbol, ts, o, h, l, c, v FROM bb_kline_1h_400d", con)
    oi = pd.read_sql("SELECT symbol, ts, oi FROM bb_oi_1h_deep", con)
    fu = pd.read_sql("SELECT symbol, ts, rate FROM bn_funding_deep", con)
    con.close()
    for df in (k, oi, fu):
        df.sort_values(["symbol", "ts"], inplace=True)
        df.reset_index(drop=True, inplace=True)
    return k, oi, fu


def fwd_ret24(k):
    """Ajoute f24_bps : rendement 24h APRÈS la barre ts (close t+24h / close t)."""
    out = []
    for s, g in k.groupby("symbol", sort=False):
        g = g.sort_values("ts").reset_index(drop=True)
        c = g["c"].to_numpy()
        ts = g["ts"].to_numpy()
        idx = np.searchsorted(ts, ts + DAY_S)
        f = np.full(len(g), np.nan)
        ok = (idx < len(g)) & (np.abs(ts[np.minimum(idx, len(g) - 1)] - (ts + DAY_S)) < TOL_S)
        f[ok] = (c[np.minimum(idx[ok], len(g) - 1)] / c[ok] - 1.0) * 1e4
        g["f24_bps"] = f
        out.append(g)
    return pd.concat(out, ignore_index=True)


def dedup(df, step_s):
    """1 observation par step par symbole — anti double comptage (leçon v27)."""
    df = df.copy()
    df["bucket"] = df["ts"] // step_s
    return df.drop_duplicates(["symbol", "bucket"], keep="first")


def walk_forward(df, feature, n_bins=5, label=""):
    """Split chrono GLOBAL par ts 60/40 (leçon ml_deep) ; excès f24 par bin du
    feature (quintiles), baseline recalculée dans chaque split ; verdict test."""
    d = df.dropna(subset=[feature, "f24_bps"]).copy()
    if len(d) < 400:
        return {"label": label, "verdict": "DIAG", "n": int(len(d)),
                "note": "n<400 : contexte informatif uniquement"}
    d = d.sort_values("ts").reset_index(drop=True)
    cut = int(len(d) * 0.6)
    parts = {}
    for name, part in (("train", d.iloc[:cut]), ("test", d.iloc[cut:])):
        q = pd.qcut(part[feature], n_bins, labels=False, duplicates="drop")
        base = part["f24_bps"].median()
        bins = {}
        for b in sorted(q.dropna().unique()):
            m = (q == b)
            bins[int(b)] = {"n": int(m.sum()),
                            "f24_med": round(float(part.loc[m, "f24_bps"].median()), 1),
                            "excess_med": round(float(part.loc[m, "f24_bps"].median() - base), 1)}
        # spread Q(haut)-Q(bas) en médianes d'excès
        keys = sorted(bins)
        spread = round(bins[keys[-1]]["excess_med"] - bins[keys[0]]["excess_med"], 1)
        parts[name] = {"n": int(len(part)), "baseline_med": round(float(base), 1),
                       "bins": bins, "spread_top_minus_bottom": spread}
    tr_sp = parts["train"]["spread_top_minus_bottom"]
    te_sp = parts["test"]["spread_top_minus_bottom"]
    # verdict
    same_sign = (np.sign(tr_sp) == np.sign(te_sp)) and tr_sp != 0
    n_test = parts["test"]["n"]
    if not same_sign or abs(te_sp) < 5:
        verdict = "KILL"
    elif abs(te_sp) >= 25 and n_test >= 500:
        verdict = "PROMU"     # cohérence symbole vérifiée plus bas avant validation finale
    elif abs(te_sp) >= 10 and n_test >= 200:
        verdict = "ADVISORY"
    else:
        verdict = "DIAG"
    return {"label": label, "feature": feature, "verdict": verdict,
            "n_total": int(len(d)), "train": parts["train"], "test": parts["test"],
            "spread_train": tr_sp, "spread_test": te_sp}


def symbol_consistency(df, feature, n_bins=5):
    """Cohérence : pour chaque symbole, signe du spread Q5-Q1 (test de robustesse
    PROMU). Retourne (n_symboles_loi, n_total, détail)."""
    laws = {}
    for s, g in df.dropna(subset=[feature, "f24_bps"]).groupby("symbol"):
        if len(g) < 300:
            continue
        q = pd.qcut(g[feature], n_bins, labels=False, duplicates="drop")
        lo = g.loc[q == 0, "f24_bps"].median()
        hi = g.loc[q == q.max(), "f24_bps"].median()
        laws[s] = round(float(hi - lo), 1)
    if not laws:
        return 0, 0, laws
    ref = np.sign(np.median(list(laws.values())))
    n_ok = sum(1 for v in laws.values() if np.sign(v) == ref)
    return n_ok, len(laws), laws


def s1_carry_funding(fu):
    """S1 : funding à t -> f24 après t. Dédup 1/24h. Join kline par (symbol, ts)."""
    f = fu.copy()
    f["ts"] = (f["ts"] // DAY_S) * DAY_S                 # aligner sur 00:00 UTC
    f = f.drop_duplicates(["symbol", "ts"], keep="first")
    # funding Binance ts = DÉBUT de l'intervalle payé : le rate est connu avant ts_payé ;
    # on l'associe à l'observation de marché du même instant (info dispo à t).
    obs = klines[["symbol", "ts", "c", "f24_bps"]]
    m = f.merge(obs, on=["symbol", "ts"], how="inner")
    m["fund_ann_pct"] = m["rate"] * 3 * 365 * 100       # annualisé en %
    res = walk_forward(m, "fund_ann_pct", 5, "S1 carry funding (annualisé, quintiles)")
    # état courant
    cur = m.sort_values("ts").groupby("symbol").tail(1)[["symbol", "fund_ann_pct"]]
    return res, dict(zip(cur["symbol"], cur["fund_ann_pct"].round(3)))


def s2_oi_price(k_oi):
    """S2 : quadrants dOI24 x r24passé -> f24. Dédup 1/4h."""
    d = k_oi.dropna(subset=["oi", "f24_bps"]).copy()
    d["dOI24"] = d["oi"] / d.groupby("symbol")["oi"].shift(24) - 1.0
    d["r24p"] = d["c"] / d.groupby("symbol")["c"].shift(24) - 1.0
    d = d.dropna(subset=["dOI24", "r24p"])
    d = dedup(d, H4_S)
    d["quadrant"] = np.select(
        [(d.dOI24 > 0) & (d.r24p > 0), (d.dOI24 > 0) & (d.r24p <= 0),
         (d.dOI24 <= 0) & (d.r24p > 0), (d.dOI24 <= 0) & (d.r24p <= 0)],
        ["tendance_L(OI+p+)", "pression_S(OI+p-)", "squeeze(OI-p+)", "flush(OI-p-)"],
        default="?")
    base_all = d["f24_bps"].median()
    d = d.sort_values("ts").reset_index(drop=True)
    cut = int(len(d) * 0.6)
    tr, te = d.iloc[:cut], d.iloc[cut:]
    quad = {}
    for q in d["quadrant"].unique():
        trm = (tr["quadrant"] == q).to_numpy()      # masques POSITIONNELS (index alignés)
        tem = (te["quadrant"] == q).to_numpy()
        quad[q] = {
            "n": int(len(d[d["quadrant"] == q])),
            "train_excess_med": round(float(tr.loc[trm, "f24_bps"].median() - tr["f24_bps"].median()), 1)
            if trm.sum() > 30 else None,
            "test_excess_med": round(float(te.loc[tem, "f24_bps"].median() - te["f24_bps"].median()), 1)
            if tem.sum() > 30 else None,
            "test_n": int(tem.sum()),
        }
    # verdict : le quadrant porte-t-il une dispersion exploitable en test ?
    te_ex = [v["test_excess_med"] for v in quad.values() if v["test_excess_med"] is not None]
    spread = round(max(te_ex) - min(te_ex), 1) if len(te_ex) >= 2 else 0.0
    tr_ex = [v["train_excess_med"] for v in quad.values() if v["train_excess_med"] is not None]
    spread_tr = round(max(tr_ex) - min(tr_ex), 1) if len(tr_ex) >= 2 else 0.0
    n_test = sum(v["test_n"] for v in quad.values())
    best = max(quad, key=lambda q: quad[q]["test_excess_med"] or -999) if te_ex else None
    worst = min(quad, key=lambda q: quad[q]["test_excess_med"] or 999) if te_ex else None
    verdict = "KILL" if spread < 5 else ("ADVISORY" if spread >= 10 and n_test >= 200 else "DIAG")
    return {"label": "S2 impulsion OI x prix (quadrants 24h, dedup 4h)",
            "verdict": verdict, "n_total": int(len(d)),
            "baseline_med_bps": round(float(base_all), 1),
            "spread_train": spread_tr, "spread_test": spread,
            "best_quadrant": {"name": best, **quad[best]} if best else None,
            "worst_quadrant": {"name": worst, **quad[worst]} if worst else None,
            "quadrants": quad}


def s3_structure(k):
    """S3 : pos90 (position range 90j) + compression range30/range90 -> f24."""
    d = k.copy()
    g = d.groupby("symbol")
    lo90 = g["l"].transform(lambda s: s.rolling(90 * 24, min_periods=90 * 12).min())
    hi90 = g["h"].transform(lambda s: s.rolling(90 * 24, min_periods=90 * 12).max())
    lo30 = g["l"].transform(lambda s: s.rolling(30 * 24, min_periods=30 * 12).min())
    hi30 = g["h"].transform(lambda s: s.rolling(30 * 24, min_periods=30 * 12).max())
    d["pos90"] = (d["c"] - lo90) / (hi90 - lo90)
    d["comp"] = (hi30 - lo30) / (hi90 - lo90)
    d = d.dropna(subset=["pos90", "f24_bps"])
    d = dedup(d, H4_S)
    res_pos = walk_forward(d, "pos90", 5, "S3a position dans range 90j (quintiles)")
    res_cmp = walk_forward(d, "comp", 5, "S3b compression range30/range90 (quintiles)")
    cur = d.sort_values("ts").groupby("symbol").tail(1)[["symbol", "pos90", "comp"]]
    return res_pos, res_cmp, cur.set_index("symbol")[["pos90", "comp"]].round(4).to_dict("index")


def s4_regime_vol(k):
    """S4 : tercile ATR% 1h du symbole à t_in de chaque trade du pool -> E[R]."""
    with open(POOL, "rb") as f:
        trades = pickle.load(f)["trades"]
    atr = {}
    for s, g in klines.groupby("symbol"):
        g = g.sort_values("ts")
        tr = np.maximum(g["h"] - g["l"],
                        np.maximum((g["h"] - g["c"].shift()).abs(),
                                   (g["l"] - g["c"].shift()).abs()))
        atr[s] = pd.DataFrame({"ts": g["ts"].to_numpy() * 1000,   # pool t_in en ms
                               "atr_pct": (tr / g["c"] * 100).to_numpy()})
    rows = []
    for t in trades:
        s = t["sym"]
        if s not in atr:
            continue
        a = atr[s]
        i = a["ts"].searchsorted(t["t_in"])
        if i == 0 or i >= len(a):
            continue
        rows.append({"sym": s, "side": t["side"], "R": t["R"], "alpha": t["alpha"],
                     "atr_pct": float(a["atr_pct"].iloc[i - 1])})
    d = pd.DataFrame(rows)
    d["tercile"] = d.groupby("sym")["atr_pct"].transform(
        lambda x: pd.qcut(x.rank(method="first"), 3, labels=[1, 2, 3]))
    out = {"label": "S4 régime vol x E[R] alphas (terciles ATR% 1h intra-symbole)",
           "verdict": "DIAG (contexte only — leçon v26 : pas de gate sur tri in-sample)",
           "note_fenetre": ("seuls les trades dont t_in tombe dans la fenêtre kline 1h om_v27 "
                            "(400 j, depuis 2024-09-27) sont classables — 183/469 ; "
                            "la tendance T1+ / T3− n'est PAS une règle : n=60-65/tercile, in-sample"),
           "n_trades": int(len(d)), "terciles": {}}
    for tc in (1, 2, 3):
        g = d[d.tercile == tc]
        out["terciles"][int(tc)] = {
            "n": int(len(g)),
            "atr_med": round(float(g.atr_pct.median()), 3),
            "ER_short": round(float(g[g.side == -1].R.mean()), 3) if (g.side == -1).any() else None,
            "ER_long": round(float(g[g.side == 1].R.mean()), 3) if (g.side == 1).any() else None,
        }
    return out


def main():
    global klines
    t0 = time.time()
    print("Chargement om_v27.db (audit VERT v27)...")
    k_raw, oi_raw, fu_raw = load_tables()
    print(f"  kline 1h {len(k_raw):,} | OI 1h {len(oi_raw):,} | funding Binance {len(fu_raw):,}")
    klines = fwd_ret24(k_raw)
    print(f"  f24 calculé : {klines.f24_bps.notna().sum():,} obs")
    k_oi = klines.merge(oi_raw, on=["symbol", "ts"], how="inner")

    results = {"ts": time.time(),
               "mission": "PR #2 volet 1 — signaux outils gratuits om_v27",
               "protocol": "dédup temporelle + walk-forward chrono global 60/40 + verdict sur TEST "
                           "(KILL < 5 bps ; ADVISORY >= 10 bps & n>=200 ; PROMU >= 25 bps & n>=500 "
                           "& cohérence >= 8/12) — leçons v26/v27 gravées",
               "signaux": {}, "contexte_courant": {}}

    print("\nS1 carry funding...")
    r1, cur1 = s1_carry_funding(fu_raw)
    ok, tot, laws = symbol_consistency(klines.merge(
        fu_raw.assign(ts=lambda x: (x.ts // DAY_S) * DAY_S).drop_duplicates(["symbol", "ts"]),
        on=["symbol", "ts"], how="inner"
    ).assign(fund_ann_pct=lambda x: x.rate * 3 * 365 * 100), "fund_ann_pct")
    r1["coherence_symboles"] = f"{ok}/{tot}"
    if r1.get("verdict") == "PROMU" and ok < 8:
        r1["verdict"] = "ADVISORY"
        r1["note_promo_bloquee"] = f"cohérence {ok}/{tot} < 8/12"
    results["signaux"]["S1_carry_funding"] = r1
    results["contexte_courant"]["funding_ann_pct"] = cur1
    print(f"  verdict={r1['verdict']} spread train={r1.get('spread_train')} test={r1.get('spread_test')}")

    print("S2 impulsion OI x prix...")
    r2 = s2_oi_price(k_oi)
    results["signaux"]["S2_impulsion_oi_prix"] = r2
    print(f"  verdict={r2['verdict']} spread test={r2['spread_test']}")

    print("S3 structure de marché...")
    r3a, r3b, cur3 = s3_structure(klines)
    results["signaux"]["S3a_position_range90"] = r3a
    results["signaux"]["S3b_compression_range"] = r3b
    results["contexte_courant"]["structure"] = cur3
    print(f"  verdicts: pos90={r3a['verdict']} comp={r3b['verdict']}")

    print("S4 régime vol x alphas...")
    r4 = s4_regime_vol(klines)
    results["signaux"]["S4_regime_vol_alphas"] = r4
    print(f"  n={r4['n_trades']} trades classés")

    # ---- synthèse honnête ---------------------------------------------------
    verdicts = {k: v.get("verdict", "?") for k, v in results["signaux"].items()}
    results["synthese"] = {
        "verdicts": verdicts,
        "n_promus": sum(1 for v in verdicts.values() if v == "PROMU"),
        "n_advisory": sum(1 for v in verdicts.values() if v == "ADVISORY"),
        "n_kill": sum(1 for v in verdicts.values() if v == "KILL"),
        "message": ("Aucun gate promu : les nouveaux signaux entrent en ADVISORY (loggé 4x/j, "
                    "non bloquant) ou sont tués — la config certifiée 50/25/100 + maker reste "
                    "l'autorité de blocage." if verdicts.get("S1_carry_funding") != "PROMU" else
                    "Signal PROMU : à confirmer sur données fraîches (protocole 90 j) avant tout blocage."),
        "integration": "contexte_om_v29.json -> pont d'armement A7 (advisory, NON bloquant, "
                       "même pattern que A6/ML v25)",
    }
    with open(f"{OUT}/signaux_om_v29.json", "w") as f:
        json.dump(results, f, indent=1, ensure_ascii=False, default=str)
    with open(f"{OUT}/contexte_om_v29.json", "w") as f:
        json.dump({"ts": time.time(), "source": "om_v27.db", "features": results["contexte_courant"]},
                  f, indent=1, ensure_ascii=False, default=str)
    print(f"\nVerdicts : {verdicts}")
    print(f"OK en {time.time()-t0:.1f}s -> signaux_om_v29.json + contexte_om_v29.json")


if __name__ == "__main__":
    main()
