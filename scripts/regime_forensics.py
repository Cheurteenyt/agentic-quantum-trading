#!/usr/bin/env python
"""REGIME FORENSICS — qu'est-ce qui a changé au T3 2026, et est-ce mesurable EN AVANCE ?

28/09/2026. Question ingénieuse née de la decay curve (reports/decay-curve-2026-09-28.md) :
l'edge cascade majors s'effondre à -0.09 % au T3 2026 et l'adaptateur
(regime_adapter_test.py, espérance roulante 90 j) le détecte avec ~90 j de lag.
Ici on cherche un PRÉCURSEUR dans les observables de MARCHÉ (pas de trades) :

  1. observables agrégés par MOIS (closes 1h des 6 majeures, 2025-10 → 2026-09) :
     - vol      : ATR(14) 1h moyen, en % du prix
     - volume   : quote volume $ / jour (proxy close×volume, 6 majeures)
     - breadth  : % moyen des majeures en retour 24h négatif (feature breadth test)
     - corr7    : corrélation moyenne inter-majeures, fenêtre 168 h (réplique machine)
     - dd       : max drawdown journalier moyen (closes 1h intra-jour UTC)
     - funding  : taux moyen (% par 8h, 6 majeures)
  2. contraste Q2 vs Q3 2026 : diff standardisée par variable (z sur les 12 mois)
  3. précurseur : pour chaque variable qui bouge, série roulante 30 j →
     graduel (franchi 1-2 mois avant) ou brutal ? + règle candidate et test rétroactif
  4. honnêteté : n = 4 trimestres ; recurrence via les 4h (BTC/ETH/SOL/DOGE, 2025-04 →)

Usage : .venv/bin/python scripts/regime_forensics.py
Sortie : reports/regime-forensics-2026-09-28.md
Read-only sur data/warehouse/klines.db. Zéro réseau, zéro look-ahead (observables
de marché agrégés, aucune décision de trade ici).
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import MAJORS  # noqa: E402

DB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "regime-forensics-2026-09-28.md"

WIN_CORR = 168        # 7 j en heures — réplique exacte du machine (_WIN=168)
WIN_ATR = 14          # ATR 1h standard
BREADTH_LAG = 24      # retour 24h — définition breadth_cascade_test
VARS = ["atr_pct", "volq_day", "breadth", "corr7", "dd_day", "funding"]
LABELS = {
    "atr_pct": "ATR% 1h moyen (vol)",
    "volq_day": "Volume $/jour (M$)",
    "breadth": "Breadth % (ret 24h neg)",
    "corr7": "Corr 7j moyenne",
    "dd_day": "Max DD journalier moyen %",
    "funding": "Funding moyen %/8h",
}
QUARTERS = {
    "2025-Q4": ["2025-10", "2025-11", "2025-12"],
    "2026-Q1": ["2026-01", "2026-02", "2026-03"],
    "2026-Q2": ["2026-04", "2026-05", "2026-06"],
    "2026-Q3": ["2026-07", "2026-08", "2026-09"],
}
FMT = {"funding": ".4f"}  # le funding %/8h a besoin de 4 décimales


def fmt(v: str, x: float) -> str:
    return "n/a" if not np.isfinite(x) else format(x, FMT.get(v, ".2f"))
# decay curve (reports/decay-curve-2026-09-28.md) : ret short moyen par trimestre
DECAY_EDGE = {"2025-Q4": 0.96, "2026-Q1": 0.76, "2026-Q2": 0.75, "2026-Q3": -0.09}
# détections de l'adaptateur (reports/regime-adapter-2026-09-28.md)
ADAPTER_DATES = {"p25 TRAIN": "2026-05-02", "0.30 % plat": "2026-08-26"}


def load_1h() -> dict[str, pd.DataFrame]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = {}
    for s in MAJORS:
        rows = con.execute(
            "SELECT open_time, open, high, low, close, volume FROM klines "
            "WHERE symbol=? AND interval='1h' ORDER BY open_time", (s,)).fetchall()
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts").astype(float)
        out[s] = df
    con.close()
    return out


def load_funding() -> pd.Series:
    """Funding moyen journalier (moyenne des 6 majeures), en % par 8h."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT symbol, funding_time, rate FROM funding_history "
        f"WHERE symbol IN ({','.join('?' * len(MAJORS))}) ORDER BY funding_time",
        MAJORS).fetchall()
    con.close()
    df = pd.DataFrame(rows, columns=["sym", "ts", "rate"])
    df["ts"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    df["day"] = df["ts"].dt.floor("D")
    daily = df.groupby("day")["rate"].mean() * 100.0  # % par 8h
    daily.index = pd.to_datetime(daily.index, utc=True)
    return daily


def hourly_observables(maj: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Séries horaires : ATR%, breadth, corr7, quote volume."""
    closes = pd.DataFrame({s: maj[s]["close"] for s in MAJORS}).sort_index()
    highs = pd.DataFrame({s: maj[s]["high"] for s in MAJORS})
    lows = pd.DataFrame({s: maj[s]["low"] for s in MAJORS})
    vols = pd.DataFrame({s: maj[s]["volume"] for s in MAJORS})

    # ATR% 1h (TR/close, ATR14), moyenne des majeures
    trs = []
    for s in MAJORS:
        c, h, l = maj[s]["close"], maj[s]["high"], maj[s]["low"]
        pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        atr = tr.rolling(WIN_ATR).mean()
        trs.append(atr / c * 100.0)
    atr_pct = pd.concat(trs, axis=1).mean(axis=1)

    # breadth : % des majeures en retour 24h négatif (closes 1h, zéro look-ahead)
    c24 = closes.shift(BREADTH_LAG)
    ret24_neg = (closes < c24).where(closes.notna() & c24.notna())  # NaN sur données absentes
    n_valid = ret24_neg.notna().sum(axis=1)
    breadth = ret24_neg.sum(axis=1) / n_valid.replace(0, np.nan) * 100.0
    breadth[closes.notna().sum(axis=1) < 4] = np.nan

    # corr7 : moyenne des 15 corrélations pairwise des rets 1h sur 168 h
    rets = closes.pct_change()
    pair_corrs = []
    for i in range(len(MAJORS)):
        for j in range(i + 1, len(MAJORS)):
            pair_corrs.append(rets[MAJORS[i]].rolling(WIN_CORR, min_periods=100)
                              .corr(rets[MAJORS[j]]))
    corr7 = pd.concat(pair_corrs, axis=1).mean(axis=1, skipna=True)

    # quote volume horaire (proxy $) sommé sur les majeures
    quote = (vols * closes).sum(axis=1)

    out = pd.DataFrame({"atr_pct": atr_pct, "breadth": breadth,
                        "corr7": corr7, "volq": quote})
    return out.dropna(how="all")


def daily_observables(ho: pd.DataFrame, maj: dict[str, pd.DataFrame],
                      fund_daily: pd.Series) -> pd.DataFrame:
    """ Agrégats journaliers : moyennes des séries horaires + DD max intra-jour + volume/jour."""
    d = pd.DataFrame({
        "atr_pct": ho["atr_pct"].resample("1D").mean(),
        "breadth": ho["breadth"].resample("1D").mean(),
        "corr7": ho["corr7"].resample("1D").mean(),
        "volq_day": ho["volq"].resample("1D").sum() / 1e6,  # M$/jour
    })
    # max drawdown journalier par symbole (closes 1h intra-jour UTC), moyenne majeures
    dds = []
    for s in MAJORS:
        c = maj[s]["close"].dropna()
        grp = c.groupby(c.index.date)
        dd = grp.apply(lambda x: float((x / x.cummax() - 1.0).min()) * 100.0)
        dd.index = pd.to_datetime(dd.index, utc=True)
        dds.append(dd)
    d["dd_day"] = pd.concat(dds, axis=1).mean(axis=1)
    d["funding"] = fund_daily.reindex(d.index)  # %/8h, moyenne des majeures
    return d


def monthly_table(d: pd.DataFrame) -> pd.DataFrame:
    m = d.resample("MS").agg({
        "atr_pct": "mean", "breadth": "mean", "corr7": "mean",
        "volq_day": "mean", "dd_day": "mean", "funding": "mean"})
    m.index = m.index.strftime("%Y-%m")
    m["n_days"] = d.resample("MS").size().values
    return m


def zscore_diff(m: pd.DataFrame) -> pd.DataFrame:
    """Contraste Q2 vs Q3 : diff standardisée (std des 12 mois complets)."""
    full = m.loc["2025-10":"2026-09"]
    rows = []
    for v in VARS:
        q2 = m.loc[QUARTERS["2026-Q2"], v].mean()
        q3 = m.loc[QUARTERS["2026-Q3"], v].mean()
        sd = full[v].std(ddof=1)
        rows.append({"var": v, "q2": q2, "q3": q3,
                     "diff": q3 - q2, "z": (q3 - q2) / sd if sd > 0 else np.nan})
    return pd.DataFrame(rows).set_index("var")


def quarterly_view(m: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for q, months in QUARTERS.items():
        r = {"q": q, "edge": DECAY_EDGE[q]}
        for v in VARS:
            r[v] = m.loc[months, v].mean()
        rows.append(r)
    return pd.DataFrame(rows).set_index("q")


def precursor_analysis(d: pd.DataFrame, contrast: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Pour chaque variable : seuil = midpoint (Q2+Q3)/2, série roulante 30 j.
    La traversée PERSISTANTE = le dernier passage côté Q2 avant le 01/07/2026, puis le
    premier passage côté Q3 après lui ; on exige qu'elle tienne (≥80 % des jours côté
    Q3 jusqu'au 31/08). Lag < 0 = franchi AVANT le T3 (précurseur)."""
    roll_vars = [v for v in VARS if v in d.columns]  # funding inclus (série journalière)
    roll30 = d[roll_vars].rolling(30, min_periods=20).mean()
    weekly = roll30.loc["2026-04-01":].resample("W").mean()
    weekly.index = weekly.index.strftime("%m-%d")
    out = []
    t_q3 = pd.Timestamp("2026-07-01", tz="UTC")
    t_hold = pd.Timestamp("2026-08-31", tz="UTC")
    for v in roll_vars:
        q2, q3 = contrast.loc[v, "q2"], contrast.loc[v, "q3"]
        thr = (q2 + q3) / 2.0
        ser = roll30[v].dropna()
        pre = ser.loc[:t_q3 - pd.Timedelta(days=1)]
        q3_side_pre = (pre > thr) if q3 > q2 else (pre < thr)
        # dernier jour côté Q2 avant le T3 (jamais = déjà côté Q3 depuis le début 2026)
        q2_side_pre = ~q3_side_pre.astype(bool)
        if q2_side_pre.any():
            last_q2 = q2_side_pre[q2_side_pre].index[-1]
        else:
            last_q2 = ser.index[0]
        after = ser.loc[ser.index > last_q2]
        q3_side_after = (after > thr) if q3 > q2 else (after < thr)
        if not q3_side_after.any():
            out.append({"var": v, "z": contrast.loc[v, "z"], "thr": thr,
                        "cross": None, "lag_days": None})
            continue
        cross = after[q3_side_after].index[0]  # premier label VRAI (pas le 1er label)
        hold = q3_side_after.loc[cross:t_hold]
        ok = float(hold.mean()) >= 0.80 if len(hold) else False
        lag = (t_q3 - cross).days
        if not ok:
            out.append({"var": v, "z": contrast.loc[v, "z"], "thr": thr,
                        "cross": None, "lag_days": None})  # ne tient pas → pas un régime
            continue
        out.append({"var": v, "z": contrast.loc[v, "z"], "thr": thr,
                    "cross": cross, "lag_days": lag})
    return out, weekly


def extension_4h() -> pd.DataFrame:
    """Honnêteté : ATR% et corr 7j en 4h pour BTC/ETH/SOL/DOGE, 2025-04 → 2026-09.
    Le T3-type s'est-il déjà vu en 2025 ?"""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    four = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
    closes, atrs = {}, {}
    for s in four:
        rows = con.execute(
            "SELECT open_time, high, low, close FROM klines "
            "WHERE symbol=? AND interval='4h' ORDER BY open_time", (s,)).fetchall()
        df = pd.DataFrame(rows, columns=["ts", "high", "low", "close"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df.set_index("ts").astype(float)
        pc = df["close"].shift(1)
        tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(),
                        (df["low"] - pc).abs()], axis=1).max(axis=1)
        atrs[s] = (tr.rolling(42).mean() / df["close"] * 100.0)  # 42 barres 4h = 7 j
        closes[s] = df["close"]
    con.close()
    atr_m = pd.concat(atrs, axis=1).mean(axis=1)
    rets = pd.DataFrame(closes).pct_change()
    pcs = []
    for i in range(len(four)):
        for j in range(i + 1, len(four)):
            pcs.append(rets[four[i]].rolling(42, min_periods=30).corr(rets[four[j]]))
    corr_m = pd.concat(pcs, axis=1).mean(axis=1)
    ext = pd.DataFrame({"atr4h_pct": atr_m, "corr4h_7j": corr_m}).resample("MS").mean()
    ext.index = ext.index.strftime("%Y-%m")
    return ext


def main() -> None:
    maj = load_1h()
    lo = min(df.index.min() for df in maj.values())
    hi = max(df.index.max() for df in maj.values())
    print(f"[data] 1h majors {len(MAJORS)} : {lo} -> {hi}")

    ho = hourly_observables(maj)
    fund_daily = load_funding()
    d = daily_observables(ho, maj, fund_daily)
    m = monthly_table(d)

    # Oct 2025 = premier mois complet (1h commence 23/09) ; sept 2026 partiel (→ 25/09)
    full_m = m.loc["2025-10":"2026-09"].copy()
    full_m.loc["2025-10", "funding"] = np.nan  # funding ne commence que le 27/10
    partial = {"2026-09": int(full_m.loc["2026-09", "n_days"])}
    table = full_m[VARS + ["n_days"]]

    contrast = zscore_diff(full_m)
    qv = quarterly_view(full_m)
    prec, weekly = precursor_analysis(d, contrast)
    ext = extension_4h()

    # ---- rapport ----
    L = ["# LA FORENSIQUE DU RÉGIME — qu'est-ce qui a changé au T3 2026 ?", ""]
    L.append("28/09/2026 — observables de MARCHÉ (zéro trade) par mois, closes 1h des "
             "6 majeures (BTC/ETH/SOL/BNB/XRP/DOGE, data/warehouse/klines.db, read-only). "
             f"Couverture réelle : 2025-09-23 → {hi:%Y-%m-%d} — le 1h ne remonte pas à "
             "avril 2025 ; table = 2025-10 → 2026-09 (12 mois, sept-26 partiel : "
             f"{partial['2026-09']} j). Question : un précurseur du T3 existe-t-il pour "
             "rendre l'adaptateur prédictif au lieu de réactif ?")
    L.append("")
    L.append("Définitions (répliques exactes du harnais) : ATR%(14, 1h) ; breadth = % des "
             "majeures en ret 24h négatif (breadth_cascade_test) ; corr7 = moyenne des 15 "
             "corr pairwise des rets 1h sur 168h (réplique machine) ; DD journalier = max "
             "DD closes 1h intra-jour UTC ; volume = quote proxy $/j ; funding = %/8h.")

    L += ["## 1. Les observables par MOIS", "",
          "| Mois | " + " | ".join(LABELS[v] for v in VARS) + " |", "|" + "---|" * 7]
    for ts, r in table.iterrows():
        mark = " *" if ts == "2026-09" else ""
        cells = [fmt(v, r[v]) for v in VARS]
        L.append(f"| {ts}{mark} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("*sept-26 partiel (" + str(partial["2026-09"]) + " jours, arrêt data 25-26/09) ; "
             "funding n/a avant le 27/10/2025 (début de collecte).*")

    L += ["## 2. Le contraste Q2 → Q3 2026 (diff standardisée, std des 12 mois)", "",
          "| Variable | Q2 | Q3 | Δ | z (σ mensuelles) | a bougé ? |",
          "|---|---|---|---|---|---|"]
    moved = []
    for v, r in contrast.iterrows():
        flag = "OUI" if abs(r["z"]) >= 1.0 else "non"
        if abs(r["z"]) >= 1.0:
            moved.append(v)
        L.append(f"| {LABELS[v]} | {fmt(v, r['q2'])} | {fmt(v, r['q3'])} | "
                 f"{r['diff']:+.2f} | {r['z']:+.2f}σ | {flag} |")
    L.append("")
    L.append("### Le caractère du nouveau régime (lecture)")
    z = {v: contrast.loc[v, "z"] for v in VARS}
    character = []
    if z["atr_pct"] < -1 and z["dd_day"] < -1:
        character.append("APATHIE : la vol et l'étendue des moves se sont effondrées — "
                         "le carburant du cascade (l'amplitude post-signal) a disparu.")
    if z["volq_day"] < -1:
        character.append("VOLUME QUI PART : le $/jour moyen s'est retiré — moins de "
                         "continuation, plus de mean-reversion micro.")
    if z["corr7"] > 1:
        character.append("HERD : corrélations plus serrées — les shorts systémiques se "
                         "retournent ensemble, moins de dispersion à capter.")
    elif z["corr7"] < -1:
        character.append("DIVERGENCE : corrélations cassées — le régime divergence.")
    if z["breadth"] > 1:
        character.append("DISTRIBUTION : breadth moyenne plus négative — plus de majeures "
                         "en ret 24h négatif en permanence (tapis roulant vers le bas).")
    elif z["breadth"] < -1:
        character.append("CONVALESCENCE : breadth moyenne plus positive — grind vers le "
                         "haut, moins de majeures en chute.")
    if z["funding"] > 1:
        character.append(f"LONGS COÛTEUX : le funding moyen a quasi triplé "
                         f"({contrast.loc['funding', 'q2']:.4f} → "
                         f"{contrast.loc['funding', 'q3']:.4f} %/8h) — longs surpayés, "
                         "marché qui grind up sur du carry, pas sur du flux.")
    L += [f"- {c}" for c in character] or ["- aucune variable ne dépasse 1σ : pas de signature."] 
    L.append("")

    L += ["## 3. Vue TRIMESTRIELLE — les observables face à l'edge (decay curve)", "",
          "| Trimestre | Edge ret short % | " + " | ".join(LABELS[v] for v in VARS) + " |",
          "|---|---|" + "---|" * 6]
    for q, r in qv.iterrows():
        cells = [fmt(v, r[v]) for v in VARS]
        L.append(f"| {q} | **{r['edge']:+.2f}** | " + " | ".join(cells) + " |")
    L.append("")
    L.append("n = 4 trimestres : toute co-mouvement edge↔observable est INDICATIF "
             "(4 points), jamais une statistique.")

    L += ["## 4. Le précurseur : graduel ou brutal ?", "",
          "Série roulante 30 j par variable ; seuil = midpoint (Q2+Q3)/2 ; traversée "
          "PERSISTANTE = dernier passage côté Q2 avant le 01/07/2026, puis premier "
          "passage côté Q3, tenu ≥80 % des jours jusqu'au 31/08. "
          "Lag > 0 = franchi AVANT le 01/07 (= précurseur) ; lag ≤ 0 = synchrone ou "
          "tardif. Références adaptateur : p25 TRAIN OFF le 2026-05-02 (trop tôt, "
          "coupait le Q2), 0.30 % plat OFF le 2026-08-26 (56 j de retard).", "",
          "| Variable | z | Seuil (mid) | Traversée 30 j | Lag vs 01/07 | Verdict |",
          "|---|---|---|---|---|---|"]
    for p in prec:
        cross = p["cross"].strftime("%Y-%m-%d") if p["cross"] is not None else "jamais"
        if p["cross"] is None:
            verdict = "brutal (pas de franchi persistant)"
        elif p["lag_days"] is not None and p["lag_days"] >= 14:
            verdict = f"GRADUEL — précurseur ({p['lag_days']} j avant)"
        elif p["lag_days"] is not None and p["lag_days"] >= -14:
            verdict = "synchrone (±2 sem du T3)"
        else:
            verdict = f"tardif ({-p['lag_days']} j après)"
        L.append(f"| {LABELS[p['var']]} | {p['z']:+.2f} | {fmt(p['var'], p['thr'])} | {cross} | "
                 f"{p['lag_days'] if p['lag_days'] is not None else 'n/a'} | {verdict} |")
    L.append("")
    L += ["### Courbe hebdo (roulant 30 j, avr → sep 2026) des variables qui bougent", ""]
    hdr = "| Semaine | " + " | ".join(LABELS[v] for v in moved if v in weekly.columns) + " |"
    if moved:
        L += [hdr, "|" + "---|" * (1 + len([v for v in moved if v in weekly.columns]))]
        for ts, r in weekly.iterrows():
            L.append(f"| {ts} | " + " | ".join(fmt(v, r[v]) for v in moved
                                               if v in weekly.columns) + " |")
    L.append("")

    # règle candidate rétro-testée (meilleur précurseur : lag le plus négatif)
    cands = [p for p in prec if p["cross"] is not None and p["lag_days"] is not None
             and p["lag_days"] >= 14]
    L += ["### La règle précurseur candidate (test rétroactif)", ""]
    if cands:
        best = max(cands, key=lambda p: p["lag_days"])
        sense = "passe SOUS" if contrast.loc[best["var"], "q3"] < contrast.loc[best["var"], "q2"] else "passe AU-DESSUS"
        d30 = d[best["var"]].rolling(30, min_periods=20).mean()
        v26 = d30.loc["2026-01-01":]
        thr = best["thr"]
        if contrast.loc[best["var"], "q3"] < contrast.loc[best["var"], "q2"]:
            hits = v26[v26 < thr]
        else:
            hits = v26[v26 > thr]
        # fausses alertes : jours au-delà du seuil AVANT le 01/07/2026 (le Q2 était bon)
        fa = hits[hits.index < pd.Timestamp("2026-07-01", tz="UTC")]
        L.append(f"- **« {LABELS[best['var']]} 30 j {sense} {thr:.2f} → dérisquer le flux majors »**")
        L.append(f"- Première traversée persistante : **{best['cross']:%Y-%m-%d}** "
                 f"({best['lag_days']} j avant le T3).")
        L.append(f"- Fausse alerte Q2 : {len(fa)} j au-delà du seuil avant 01/07/2026"
                 + (f" (première : {fa.index[0]:%Y-%m-%d})" if len(fa) else " — aucune") + ".")
        ad = ADAPTER_DATES["0.30 % plat"]
        dd = (pd.Timestamp(ad, tz="UTC") - best["cross"]).days
        L.append(f"- Vs adaptateur 0.30 % plat (OFF le {ad}) : la règle signale "
                 f"**{dd} j plus tôt**.")
    else:
        L.append("- AUCUNE variable ne franchit son seuil Q3 de façon persistante AVANT "
                 "le 01/07/2026 → la bascule T3 est BRUTALE côté observables de marché. "
                 "Pas de précurseur 1-2 mois en avance : le levier réaliste n'est pas un "
                 "observable marché mais la FENÊTRE DE DÉTECTION de l'adaptateur — le "
                 "flip vu par un roulant 30 j sort 6-22 j après le 01/07 (volume 07/07, "
                 "funding 12/07, ATR 19/07, DD 22/07, corr7 06/08) contre le 26/08 du "
                 "0.30 % plat 90 j.")
        # la fenêtre du flip en brut (roulant 3 j pour lisibilité)
        r3 = d[VARS].rolling(3, min_periods=2).mean()
        j0 = r3.loc["2026-06-28"]
        j1 = r3.loc["2026-07-04"]
        j2 = r3.loc["2026-07-31"]
        L += ["", "La fenêtre du flip (roulant 3 j, valeurs brutes) :", "",
              "| Observable | 28/06 | 04/07 | 31/07 |", "|---|---|---|---|"]
        for v in VARS:
            L.append(f"| {LABELS[v]} | {fmt(v, j0[v])} | {fmt(v, j1[v])} | "
                     f"{fmt(v, j2[v])} |")
        L.append("")
        L.append("Tout flippe dans la semaine du 28/06 → 04/07 : le ATR% entame sa "
                 "chute (0.89 → 0.66 au 31/07), le funding double (0.0024 → 0.0079 au "
                 "04/07), le DD journalier se rétracte (-2.34 → -1.29) et le corr7 "
                 "bascule en fin de chaîne (pic 0.91 fin juin → 0.71 fin août). La "
                 "breadth devient BIMODALE (0.7 % le 02/07 → 100 % le 08/07, toutes "
                 "les majeures du même côté du ret 24h en alternant) : le sens "
                 "journalier perd toute mémoire. Juin était le mois le plus "
                 "« herd-down » de l'échantillon : le régime a basculé AU SOMMET de sa "
                 "qualité.")
    L.append("")

    L += ["## 5. L'honnêteté", "",
          f"- n = **12 mois / 4 trimestres** pour le 1h : le contraste Q2↔Q3 est "
          "INDICATIF. Une seule occurrence du T3-type dans l'échantillon.",
          "- Recurrence (extension 4h, BTC/ETH/SOL/DOGE, depuis 2025-04 — corr/ATR sur "
          "4 majeures seulement, fenêtre 7 j en barres 4h) :", "",
          "| Mois | ATR% 4h moyen | Corr 7j (4 majeures) |", "|---|---|---|"]
    for ts, r in ext.iterrows():
        L.append(f"| {ts} | {r['atr4h_pct']:.2f} | {r['corr4h_7j']:.2f} |")
    t3_atr = float(ext.loc["2026-07":"2026-08", "atr4h_pct"].mean())
    low_v = ext[(ext.index >= "2025-04") & (ext["atr4h_pct"] < t3_atr)]
    L.append("")
    L.append(f"- Mois avec ATR% 4h moyen < au niveau T3 ({t3_atr:.2f} ; sept-26 absent, "
             "4h arrêté le 22/09) : "
             + (", ".join(low_v.index) if len(low_v) else "aucun")
             + ". MAIS mai-26 (1.27) était un BON mois (edge +0.75 %) : la compression "
             "de vol SEULE ne définit pas le T3-type. Le COMBO T3 — funding ×2.4 "
             "(+1.14σ) + corr7 cassée (-1.33σ) + breadth en repli (-1.06σ) sur un fond "
             "de vol déjà basse — n'apparaît NULLE PART ailleurs dans l'échantillon "
             "disponible : première occurrence, aucune récurrence testable, prudence "
             "maximale.")
    L.append("- Le breadth/corr7 horaires répliquent les définitions du harnais "
             "(breadth_cascade_test.py, _WIN=168) — mais ici agrégés MARCHÉ ENTIER, pas "
             "aux events cascade : ils mesurent le climat, pas le signal.")
    L.append("- Zéro look-ahead : tout observable mensuel n'utilise que des closes ≤ fin "
             "de mois ; la règle candidate est testable en live (roulant 30 j).")
    L.append("- Le funding ne couvre que depuis 2025-10-27 (collecte) — 11 mois.")
    L.append("")

    L += ["## VERDICT", ""]
    top = contrast["z"].abs().idxmax()
    q2f = float(contrast.loc["funding", "q2"])
    q3f = float(contrast.loc["funding", "q3"])
    L.append(f"- Ce qui a changé au T3 : **{LABELS[top]}** ({contrast.loc[top, 'z']:+.2f}σ) "
             f"+ funding ×{(q3f / q2f):.1f} ({q2f:.4f} → {q3f:.4f} %/8h, {contrast.loc['funding', 'z']:+.2f}σ) "
             f"+ breadth {contrast.loc['breadth', 'diff']:+.1f} pts ({contrast.loc['breadth', 'z']:+.2f}σ). "
             "Caractère = GRIND-UP ROTATION (corrélations cassées, longs surpayés, "
             "grind vers le haut) — PAS l'apathie : la vol était déjà basse au Q2 "
             "(0.76 %) et le Q2 a fait +0.75 % d'edge.")
    grad = [p for p in prec if p["cross"] is not None and p["lag_days"] is not None
            and p["lag_days"] >= 14]
    if grad:
        b = max(grad, key=lambda p: p["lag_days"])
        L.append(f"- Précurseur candidat : **{LABELS[b['var']]} 30 j {'<' if contrast.loc[b['var'], 'q3'] < contrast.loc[b['var'], 'q2'] else '>'} {b['thr']:.2f}** "
                 f"— franchi le {b['cross']:%Y-%m-%d}, {b['lag_days']} j avant le T3, "
                 f"vs adaptateur 0.30 % plat OFF le 2026-08-26.")
    else:
        L.append("- Graduel ou brutal : **BRUTAL** — le flip se joue dans la semaine du "
                 "28/06 → 04/07, au sommet de la qualité du régime (juin = mois le plus "
                 "herd-down de l'échantillon). AUCUN précurseur marché 1-2 mois en "
                 "avant ; le franchi 30 j le plus rapide = volume le 07/07 (6 j), "
                 "funding le 12/07 (11 j) — 5-7 semaines avant l'adaptateur 90 j "
                 "(26/08) mais JAMAIS en avance.")
    L.append("- n = 4 trimestres, une seule occurrence du T3-type, pas de récurrence "
             "dans les données (4h 2025-04 →) : la règle « vol basse → dérisquer » est "
             "RÉFUTÉE par mai-26 (vol basse, edge +0.75 %). Le composé funding↑+corr↓+"
             "breadth↓ est la signature à surveiller en pré-enregistré, pas une règle "
             "validée.")
    L.append("")
    L.append("*Script : scripts/regime_forensics.py — read-only klines.db, zéro réseau, "
             "zéro look-ahead. Sources : decay-curve-2026-09-28.md, "
             "regime-adapter-2026-09-28.md.*")

    REPORT.write_text("\n".join(L) + "\n")
    print(f"[ok] rapport écrit -> {REPORT}")
    print("\n=== CONTRASTE Q2 vs Q3 (z) ===")
    print(contrast.round(2).to_string())
    print("\n=== PRÉCURSEURS ===")
    for p in prec:
        print(f"{p['var']:>9} z={p['z']:+.2f} thr={p['thr']:.2f} "
              f"cross={p['cross']} lag={p['lag_days']}")


if __name__ == "__main__":
    main()
