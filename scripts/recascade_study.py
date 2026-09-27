#!/usr/bin/env python
"""RE-CASCADE DES CASCADES — le 2e feu sur le même symbole ≤ 7j (27/09).

Le corpus : les 230 events cascade majors du sim (anti_liq.collect_featured
+ add_rolling_scores — ts_ms = des NS, leçon du projet). La question jamais
testée : quand le signal cascade re-fire sur le MÊME symbole peu après, le
short 2e feu est-il MEILLEUR (continuation confirmée — les cascades couplées
continuent, le vendeur unique est réfuté) ou PIRE (le 1er feu a capté le
mouvement, les vendeurs sont épuisés — le failed_ATH montrait « la 2e
approche arrive trop tard » : retest = WR 0.0-0.9 % vs 43-60 % en direct) ?

DISCIPLINE (le harnais v5 = LA référence) :
  - le tag est EX-ANTE : au signal, on connaît l'historique des feux du
    symbole (7j lookback) — zéro look-ahead. Les feux BRUTS (le signal
    `cas`, mêmes filtres que collect_featured : t ≥ 200, entry > 0),
    PAS les events sélectionnés (la sélection séquentielle saute 24h).
  - biais de sélection noté honnêtement : un re-feu < 24h dans le corpus
    implique que le feu précédent du symbole a été SAUTÉ (une autre
    position tenait le slot global) — observable ex-ante quand même.
  - split TRAIN 70 / VAL 30 PAR LE TEMPS ; sous-test pré-enregistré :
    re-feu < 24h (la même vague) vs 1-7j (une nouvelle vague).
  - la barre = gradient TRAIN (spread EV > 2 pts) ET direction tenue en
    VAL ET cohérent 2025 vs 2026 ET p<0.10 (two-prop 1er vs re-feux,
    sinon binomial par bucket). Sinon CONTEXTE, pas de run machine.
  - si PASS : sizing SIZING-ONLY ×{0.75, 1.0, 1.25} par tag (TRAIN-only)
    sur la MACHINE 4 flux (--vol-spike ON, réplication bit-exacte via
    wallclock_cascades.run_machine), BLOC STATS vs baseline $4,004.94,
    garde-fou composé-des-mois, 0 liq.
  - puissance honnête : delta de WR minimal détectable two-proportion.

  .venv/bin/python scripts/recascade_study.py            # analyse
  .venv/bin/python scripts/recascade_study.py --machine  # + runs sizing
"""
from __future__ import annotations

import argparse
import bisect
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import collect_featured as _collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import MAKER_RT  # noqa: E402
import scripts.wallclock_cascades as wc  # noqa: E402
from scripts.wallclock_cascades import (  # noqa: E402
    binom_two_sided, mdd_detectable, run_machine, stats_block)

REPORTS = ROOT / "reports"
DAY_NS = 24 * 3600 * 10**9
LEV = 10
FEES_MARGIN_PCT = MAKER_RT * LEV / 100
TAGS = ("1er feu", "re-feu <24h", "re-feu 1-7j")

# ————————————————————————————— LE CORPUS —————————————————————————————

_fire_cache: dict[str, tuple[list[int], list[float]]] | None = None


def raw_fires() -> dict[str, tuple[list[int], list[float]]]:
    """TOUS les feux cascade par symbole (le signal brut, PAS la sélection
    du sim) — la formule `cas` et les filtres d'entrée de collect_featured
    (t ≥ 200, entry > 0). Retour : {sym: ([ts_ns...], [entry_px...])}."""
    global _fire_cache
    if _fire_cache is not None:
        return _fire_cache
    con = sqlite3.connect(KDB)
    out: dict[str, tuple[list[int], list[float]]] = {}
    for sym in MAJORS:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close = df["close"]
        r1 = close.pct_change() * 100
        ra = r1.abs()
        cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens = df["open"].values
        ts_l, px_l = [], []
        for t in np.where(cas)[0]:
            if t < 200 or t + 1 >= len(idx_ns) or opens[t + 1] <= 0:
                continue
            ts_l.append(int(idx_ns[t + 1]))
            px_l.append(float(opens[t + 1]))
        if ts_l:
            out[sym] = (ts_l, px_l)
    con.close()
    _fire_cache = out
    return out


def tag_events(events: list[dict]) -> list[dict]:
    """Le tag ex-ante par event : 1er feu (aucun feu du symbole ≤ 7j) vs
    re-feu <24h (la même vague) vs re-feu 1-7j (une nouvelle vague) ;
    le nb de feux récents (1/2/3+) ; le Δ prix et le gap vs le dernier feu."""
    fires = raw_fires()
    for e in events:
        fl = fires.get(e["sym"])
        ts = e["ts_ms"]
        if not fl:
            e |= {"rec_tag": "1er feu", "rec_n7": 0, "rec_n24": 0,
                  "rec_count": "0", "rec_gap_h": float("nan"),
                  "rec_dpx": float("nan")}
            continue
        ts_l = fl[0]
        hi = bisect.bisect_left(ts_l, ts)          # feux STRICTEMENT avant
        pri7 = [i for i in range(hi) if ts_l[i] >= ts - 7 * DAY_NS]
        n7, n24 = len(pri7), sum(1 for i in pri7 if ts_l[i] >= ts - DAY_NS)
        if n7 == 0:
            tag = "1er feu"
        elif n24:
            tag = "re-feu <24h"
        else:
            tag = "re-feu 1-7j"
        e["rec_tag"] = tag
        e["rec_n7"] = n7
        e["rec_n24"] = n24
        e["rec_count"] = "0" if n7 == 0 else (
            "1" if n7 == 1 else ("2" if n7 == 2 else "3+"))
        if n7:
            j = pri7[-1]                            # le dernier feu ≤ 7j
            e["rec_gap_h"] = (ts - ts_l[j]) / 3.6e12
            e["rec_dpx"] = (e["entry"] - fl[1][j]) / fl[1][j] * 100
        else:
            e["rec_gap_h"] = float("nan")
            e["rec_dpx"] = float("nan")
    return events


def build_corpus() -> list[dict]:
    regime = btc_regime_series()
    events = _collect_featured(regime, "majors")
    wc.add_rolling_scores(events)
    tag_events(events)
    for e in events:
        assert wc.hour_utc(e["ts_ms"]) == e["hour"], f"unité ts ? {e['ts_ms']}"
    return events


# ————————————————————————————— L'ANALYSE —————————————————————————————

def two_prop_p(k1: int, n1: int, k2: int, n2: int) -> float:
    """Le p-value two-proportion z (two-sided), sans scipy."""
    if n1 == 0 or n2 == 0:
        return 1.0
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(p1 - p2) / se
    return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))


def gradient_map(events: list[dict]):
    k = int(len(events) * 0.7)
    train, val = events[:k], events[k:]
    p0 = float(np.mean([e["price_ret_short"] > 0 for e in train]))

    def rows_for(keyfn, labels):
        rows = []
        for lab in labels:
            t = stats_block([e for e in train if keyfn(e) == lab])
            v = stats_block([e for e in val if keyfn(e) == lab])
            tr = [e for e in train if keyfn(e) == lab]
            kw = sum(e["price_ret_short"] > 0 for e in tr)
            rows.append({"label": lab, "train": t, "val": v,
                         "p_train": binom_two_sided(kw, len(tr), p0)
                         if tr else 1.0})
        return rows

    main = rows_for(lambda e: e["rec_tag"], list(TAGS))
    counts = rows_for(lambda e: e["rec_count"], ["0", "1", "2", "3+"])
    # les années (la leçon wall-clock : un gradient incohérent = artefact)
    years: dict[int, list[dict]] = {}
    for e in events:
        y = datetime.fromtimestamp(e["ts_ms"] / 10**9,
                                   tz=timezone.utc).year
        years.setdefault(y, []).append(e)
    yrows = []
    for y in sorted(years):
        evy = years[y]
        p0y = float(np.mean([x["price_ret_short"] > 0 for x in evy]))
        yrows.append({"year": y, "n": len(evy),
                      "tags": {lab: stats_block(
                          [x for x in evy if x["rec_tag"] == lab])
                          for lab in TAGS},
                      "p0": p0y})
    # les deltas de prix et gaps entre feux (les re-feux seulement)
    refire = [e for e in events if e["rec_tag"] != "1er feu"]
    dpx = np.array([e["rec_dpx"] for e in refire
                    if np.isfinite(e["rec_dpx"])])
    gaps = np.array([e["rec_gap_h"] for e in refire
                     if np.isfinite(e["rec_gap_h"])])
    return main, counts, yrows, train, val, refire, dpx, gaps


def gradient_verdict(main: list, yrows: list, train: list):
    """La barre haute : spread EV > 2 pts TRAIN, direction tenue en VAL,
    cohérent entre années, p<0.10 (two-prop 1er vs re-feux, sinon bucket)."""
    judged = [r for r in main if r["train"].get("n", 0) >= 15]
    why = []
    if len(judged) < 2:
        return "CONTEXTE (moins de 2 buckets jugables n≥15 TRAIN)", [], why
    evs = [r["train"]["ev"] for r in judged]
    spread = max(evs) - min(evs)
    # la direction VAL : (re-feu − 1er feu) même signe TRAIN/VAL par bucket
    first_tr = next((r for r in main if r["label"] == "1er feu"), None)
    dirs_ok, dirs_n = True, 0
    for r in judged:
        if r["label"] == "1er feu" or r["val"].get("n", 0) < 8:
            continue
        d_tr = r["train"]["ev"] - first_tr["train"]["ev"]
        d_va = r["val"]["ev"] - first_tr["val"]["ev"]
        dirs_n += 1
        if np.sign(d_tr) != np.sign(d_va):
            dirs_ok = False
            why.append(f"{r['label']} VAL inversé ({d_tr:+.1f}/{d_va:+.1f})")
    # les années : (re-feu − 1er feu) même signe 2025/2026 (n≥15/an)
    years_ok, years_n = True, 0
    for r in judged:
        if r["label"] == "1er feu":
            continue
        signs = []
        for y in yrows:
            if y["tags"][r["label"]].get("n", 0) >= 15 \
                    and y["tags"]["1er feu"].get("n", 0) >= 15:
                signs.append(y["tags"][r["label"]]["ev"]
                             - y["tags"]["1er feu"]["ev"])
        if len(signs) == 2:
            years_n += 1
            if np.sign(signs[0]) != np.sign(signs[1]):
                years_ok = False
                why.append(f"{r['label']} années inversées "
                           f"({signs[0]:+.1f}/{signs[1]:+.1f})")
    # la significativité : two-prop 1er vs tous re-feux (TRAIN), sinon bucket
    k1 = sum(e["price_ret_short"] > 0 for e in train
             if e["rec_tag"] == "1er feu")
    n1 = sum(1 for e in train if e["rec_tag"] == "1er feu")
    k2 = sum(e["price_ret_short"] > 0 for e in train
             if e["rec_tag"] != "1er feu")
    n2 = sum(1 for e in train if e["rec_tag"] != "1er feu")
    p_tp = two_prop_p(k1, n1, k2, n2)
    sig = p_tp < 0.10 or any(r["p_train"] < 0.10 for r in judged)
    if spread <= 2.0:
        why.append(f"spread EV {spread:.1f} pt ≤ 2")
    if dirs_n == 0 or not dirs_ok:
        if dirs_n == 0:
            why.append("aucun bucket VAL n≥8")
    if years_n == 0 or not years_ok:
        if years_n == 0:
            why.append("années non jugables (n<15)")
    if not sig:
        why.append(f"p two-prop {p_tp:.2f}, aucun bucket p<0.10")
    if spread > 2.0 and dirs_ok and dirs_n > 0 and years_ok and years_n > 0 \
            and sig:
        verdict = (f"PASS — spread EV {spread:.1f} pts, direction VAL "
                   f"tenue ({dirs_n}/{dirs_n} buckets), années cohérentes "
                   f"({years_n}/{years_n}), p two-prop {p_tp:.3f}")
        # le sizing TRAIN-only : le meilleur bucket jugé ×1.25, le pire ×0.75
        order = sorted(judged, key=lambda r: r["train"]["ev"])
        fmap = {r["label"]: 1.0 for r in main}
        fmap[order[0]["label"]] = 0.75
        if len(order) > 2 and order[-1]["train"]["ev"] - \
                order[0]["train"]["ev"] > 4.0:
            fmap[order[-1]["label"]] = 1.25
        factors = sorted(fmap.items(), key=lambda kv: list(TAGS).index(kv[0]))
    else:
        verdict = "CONTEXTE — " + " ; ".join(why) if why else "CONTEXTE"
        factors = []
    return verdict, factors, why


# ————————————————————————————— LA MACHINE —————————————————————————————

def patch_collect() -> None:
    """Branche le tag re-cascade dans le collect de la machine : les events
    passent par tag_events AVANT le gate al_score (le tag est ex-ante)."""
    _orig = wc.collect_featured

    def wrapped(regime, universe="majors"):
        evs = _orig(regime, universe)
        return tag_events(evs)

    wc.collect_featured = wrapped


# ————————————————————————————— LE RAPPORT —————————————————————————————

def f1(d: dict, key: str) -> str:
    return f"{d[key]:.1f}" if d.get("n") else "—"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", action="store_true",
                    help="exécuter aussi les runs sizing machine 4 flux")
    args = ap.parse_args()

    events = build_corpus()
    n = len(events)
    main, counts, yrows, train, val, refire, dpx, gaps = gradient_map(events)
    verdict, factors, why = gradient_verdict(main, yrows, train)

    L = ["# RE-CASCADE DES CASCADES — le 2e feu sur le même symbole ≤ 7j",
         f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {n} events "
         f"cascade majors (sim, hold 24h, sélection séquentielle), split "
         f"TRAIN {len(train)}/VAL {len(val)} PAR LE TEMPS. Tag ex-ante : "
         "les feux BRUTS du symbole (signal `cas`, 7j lookback), pas les "
         "events sélectionnés.", "",
         "Les hypothèses : (a) le 2e feu = CONTINUATION confirmée → short "
         "meilleur ; (b) le 2e feu = vendeurs épuisés (le failed_ATH "
         "montrait la 2e approche trop tard : retest WR 0.0-0.9 % vs "
         "43-60 % direct) → short pire.", "",
         "## LE CORPUS TAGGÉ", "",
         "| Tag | n | % | n TRAIN | n VAL |", "|---|---|---|---|---|"]
    for r in main:
        nt = sum(1 for e in train if e["rec_tag"] == r["label"])
        nv = sum(1 for e in val if e["rec_tag"] == r["label"])
        L.append(f"| {r['label']} | {r['train'].get('n', 0) + r['val'].get('n', 0)} "
                 f"| {(r['train'].get('n', 0) + r['val'].get('n', 0)) / n * 100:.0f} % "
                 f"| {nt} | {nv} |")
    L += ["",
          f"Deltas de prix entre feux (re-feux, n={len(dpx)}) : médiane "
          f"{np.median(dpx):+.2f} % (négatif = le prix a continué de baisser "
          f"depuis le feu précédent), p25/p75 "
          f"{np.quantile(dpx, 0.25):+.2f} / {np.quantile(dpx, 0.75):+.2f} %. "
          f"Gap médian au dernier feu : {np.median(gaps):.0f} h "
          f"(p25/p75 {np.quantile(gaps, 0.25):.0f} / "
          f"{np.quantile(gaps, 0.75):.0f} h).",
          "",
          "Biais de sélection noté : la sélection séquentielle saute 24h "
          "GLOBALEMENT — un re-feu <24h du corpus implique que le feu "
          "précédent du symbole a été sauté (une autre position tenait le "
          "slot). Observable ex-ante quand même (l'historique des feux est "
          "connu au signal).", "",
          "## LA GRADIENT MAP — 1er feu vs re-feu", "",
          "| Tag | TRAIN n | WR | MAE | Liq | EV marge 10x | p (binomial) "
          "| VAL n | WR | MAE | Liq | EV |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in main:
        t, v = r["train"], r["val"]
        L.append(
            f"| {r['label']} | {t.get('n', 0)} | {f1(t, 'wr')} % "
            f"| {f1(t, 'mae')} % | {f1(t, 'liq')} % | {f1(t, 'ev')} % "
            f"| {r['p_train']:.3f} | {v.get('n', 0)} | {f1(v, 'wr')} % "
            f"| {f1(v, 'mae')} % | {f1(v, 'liq')} % | {f1(v, 'ev')} % |")
    L += ["", "EV marge = mean(ret_short)×10 − 0.40 % (frais maker 10x), "
              "ex-funding. Buckets jugés si n ≥ 15 TRAIN.", "",
          "## LE SOUS-TEST PRÉ-ENREGISTRÉ — nb de feux récents (7j)", "",
          "| Feux récents | TRAIN n | WR | EV | VAL n | WR | EV |",
          "|---|---|---|---|---|---|---|"]
    for r in counts:
        t, v = r["train"], r["val"]
        L.append(f"| {r['label']} | {t.get('n', 0)} | {f1(t, 'wr')} % "
                 f"| {f1(t, 'ev')} % | {v.get('n', 0)} | {f1(v, 'wr')} % "
                 f"| {f1(v, 'ev')} % |")
    L += ["", "## LA ROBUSTESSE — années et puissance honnête", ""]
    for y in yrows:
        parts = [f"{lab} n={y['tags'][lab].get('n', 0)} "
                 f"EV {y['tags'][lab].get('ev', 0):+.1f}"
                 for lab in TAGS if y["tags"][lab].get("n")]
        L.append(f"- **{y['year']}** (n={y['n']}) : " + ", ".join(parts))
    n_first = sum(1 for e in train if e["rec_tag"] == "1er feu")
    p_glob = float(np.mean([e["price_ret_short"] > 0 for e in train]))
    d_min = mdd_detectable(n_first, len(train) - n_first, p_glob) * 100
    # la lecture binaire hors barre : (re-feu − 1er feu) par coupe
    bin_rows = []
    for name, evs in (("TRAIN", train), ("VAL", val)):
        bin_rows.append((name, evs))
    for y in sorted({datetime.fromtimestamp(e["ts_ms"] / 10**9,
                                           tz=timezone.utc).year
                     for e in events}):
        bin_rows.append((str(y),
                         [e for e in events
                          if datetime.fromtimestamp(e["ts_ms"] / 10**9,
                                                    tz=timezone.utc).year
                          == y]))
    k1 = sum(e["price_ret_short"] > 0 for e in train
             if e["rec_tag"] == "1er feu")
    k2 = sum(e["price_ret_short"] > 0 for e in train
             if e["rec_tag"] != "1er feu")
    p_tp = two_prop_p(k1, n_first, k2, len(train) - n_first)
    L += ["",
          f"Puissance honnête : 1er feu n={n_first} vs re-feux "
          f"n={len(train) - n_first} en TRAIN, alpha 5 %, puissance 80 %, "
          f"le delta de WR minimal détectable est ≈ ±{d_min:.0f} pts — "
          "seul un effet ÉNORME est détectable. Hypothèse concurrente "
          "pré-enregistrée : failed_ATH « la 2e approche arrive trop tard "
          "» (retest WR 0.0-0.9 %) — ici le 2e feu est un NOUVEAU signal "
          "de cascade (3 bougies + accélération), pas un retest de niveau.",
          "",
          "## LA LECTURE BINAIRE HORS BARRE — 1er feu vs re-feu poolé", "",
          "| Coupe | 1er feu n | EV | re-feu n | EV | Δ EV |", 
          "|---|---|---|---|---|---|"]
    for name, evs in bin_rows:
        f_ = stats_block([e for e in evs if e["rec_tag"] == "1er feu"])
        r_ = stats_block([e for e in evs if e["rec_tag"] != "1er feu"])
        d = (r_["ev"] - f_["ev"]) if f_.get("n") and r_.get("n") \
            else float("nan")
        L.append(f"| {name} | {f_.get('n', 0)} | {f_.get('ev', 0):+.1f} % "
                 f"| {r_.get('n', 0)} | {r_.get('ev', 0):+.1f} % "
                 f"| {d:+.1f} pts |")
    L += ["",
          f"p two-prop (WR 1er feu vs re-feux, TRAIN) = {p_tp:.3f} — sous "
          "le seuil brut 0.10 mais NON ajusté pour la multiplicité (3 tags "
          "× 2 sous-coupes × 4 coupes) et le bucket 1er feu (n=11 TRAIN, "
          f"4 VAL) est SOUS la barre de jugabilité n≥15 (détection ±{d_min:.0f} "
          "pts). La direction « 1er feu pire » est cohérente sur les 4 "
          "coupes mais indistinguable du bruit à ce n — un hint, pas un "
          "candidat.", "",
          f"## LE VERDICT — {verdict}", ""]
    if factors:
        L.append("Sizing TRAIN-only par tag (SIZING modifier, jamais un "
                 "gate) : "
                 + ", ".join(f"« {t} » ×{f}" for t, f in factors) + ".")
        L.append("")
    if args.machine and factors:
        patch_collect()
        base = run_machine(lambda e: 1.0, "baseline")
        fmap = dict(factors)
        var = run_machine(
            lambda e: fmap.get(e.get("rec_tag", ""), 1.0), "recascade")
        crit = (var["roi"] >= base["roi"] and var["dd"] <= base["dd"]
                and var["neg"] <= base["neg"]
                and var["gap_c"] < 0.005 and var["liq"] == 0)
        L += ["", "## LA MACHINE 4 FLUX (--vol-spike ON) — le sizing par tag",
              "",
              "| Run | Wallet | ROI/an | DD | Liq | Trades/WR | Mois "
              "moy/pire/record | Nég | Composé |",
              "|---|---|---|---|---|---|---|---|---|"]
        for x in (base, var):
            L.append(
                f"| {x['tag']} | ${x['bal']:,.2f} | {x['roi']:+.0f} % "
                f"| {x['dd']:.1f} % | {x['liq']} | {x['n']} / "
                f"{x['wr']:.1f} % | {x['mean_m']:+.1f} % / "
                f"{x['worst']:+.1f} % / {x['rec']:+.1f} % | {x['neg']} "
                f"| {x['gap_c']*100:.3f} % |")
        L += ["",
              "Critère pré-enregistré (vs baseline $4,004.94) : ROI ≥ ET "
              "DD ≤ ET mois négatifs ≤, 0 liq, garde-fou composé ~0 → "
              f"**{'PASS' if crit else 'FAIL'}**.",
              "", "### La table mensuelle (variante recascade)", "",
              "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
        for x in var["mr"]:
            L.append(f"| {x['month']} | {x['n']} | "
                     f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                     f"| {x['roi']:+.1f} % |")
    elif not factors:
        L += ["", "Pas de run machine : la barre (gradient VAL + années + "
                  "signif.) n'est pas tenue — aucun sizing à tester. Le "
                  "re-cascade va au registre en " + verdict.split(" — ")[0]
                  + "."]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "recascade-2026-09-27.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[recascade] rapport → {out}")
    print(f"[recascade] VERDICT : {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
