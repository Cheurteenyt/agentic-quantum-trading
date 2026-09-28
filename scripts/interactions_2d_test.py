#!/usr/bin/env python
"""INTERACTIONS 2D — les cellules 2×2 que l'additif ne voit pas (28/09).

CONTEXTE PRÉ-ENREGISTRÉ (mission, critère AVANT calcul) : le gate v1 est
additif (moyenne des rangs) et l'AL v2 additif a FAIL. MAIS les features
peuvent porter des INTERACTIONS. Preuve partielle : la lifecycle_map
(âge × dd — 30-90j/20-50 % = SHORT 65,4 %, cellule ≠ de ses marges).

LES 4 PAIRES (pré-enregistrées, sur les 230 events cascade majors) :
  1. dd_pct  × age        2. atr_pct × cascade_depth
  3. corr7   × vol7       4. atr_pct × vol24
« age » : les 6 majeures partagent la MÊME date de début klines (snapshot),
un âge-token serait du temps calendaire et s'aliaserait au split — on
retient l'analogue ex-ante de la lifecycle : age = âge du DRAWDOWN en
jours, depuis le plus haut glissant (cummax des highs, la MÊME référence
que dd_pct). Redéfini à chaque nouveau sommet, zéro alias temporel.

MÉTHODE :
  - univers = build_universe() d'al_score_v2 (réplication bit-exact de
    the_machine 4 flux --vol-spike, briques importées, zéro édition) ;
  - r_not = espérance en % du notionnel (copie exacte al_score_v2.main) ;
  - split 70/30 PAR LE TEMPS (convention machine events[:int(n*0.7)]) ;
  - coupures = MÉDIANES TRAIN de chaque feature ; 4 cellules par paire ;
  - modèle additif ajusté SUR TRAIN : pred(cellule) = grand_mean
    + marg(f1) + marg(f2) ; écart = espérance de la cellule − prédiction
    additif (ce que les marges ne prédisent pas) ;
  - GARDE MULTIPLICITÉ (16 tests = 4 paires × 4 cellules), seuil DUR :
      n ≥ 20 par cellule TRAIN,
      |écart VAL| ≥ 3,0 pts d'espérance,
      signe de l'écart TRAIN = signe VAL,
      n VAL ≥ 5 (sinon le pattern est invérifiable).
    n=230 → fragile par construction : la barre est volontairement haute,
    la plupart doivent FAIL.
  - SI PASS (rare) : UNE intervention de sizing max sur la cellule la plus
    solide (×0,75 la toxique OU ×1,25 la porteuse, plafond machine 0,50·K
    respecté) sur la machine 4 flux --vol-spike ON → BLOC STATS vs
    baseline $4,004.94 ; critère ROI ≥ ET DD ≤ ET mois négatifs ≤.

Lecture SEULE de data/warehouse/klines.db.

  .venv/bin/python scripts/interactions_2d_test.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.al_score_v2 import (  # noqa: E402
    TRAIN_FRAC, bloc, build_universe, machine_fn_factory, ro_con, sim)
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.portfolio_sim import MAJORS  # noqa: E402
from scripts.stacked_portfolio import CAPITAL  # noqa: E402

REPORTS = ROOT / "reports"
K = 0.89                                  # calibration DD machine (INTOUCHÉE)
CAP_10X = 0.50 * K                        # plafond absolu flux cascade 10x
MIN_N_TR = 20                             # garde : n minimal cellule TRAIN
MIN_N_VA = 5                              # garde : n minimal cellule VAL
DEV_MIN = 3.0                             # pts d'espérance exigés en VAL

# (f1, f2, label) — pré-enregistré, l'ordre des cellules est figé
PAIRS = [
    ("dd_pct", "age_dd", "dd_pct × age(drawdown)"),
    ("atr_pct", "cascade_depth", "atr_pct × cascade_depth"),
    ("corr7", "vol7", "corr7 × vol7"),
    ("atr_pct", "vol24", "atr_pct × vol24"),
]
CELL_NAMES = ("lo/lo", "lo/hi", "hi/lo", "hi/hi")


# ------------------------------------------------------------ la feature --
def attach_age_dd(events: list[dict]) -> None:
    """age = jours depuis le plus haut glissant (cummax des HIGHS, la même
    référence que dd_pct dans anti_liq.collect_featured). Barre du signal
    = barre d'entrée (ts_ms, en NS — convention anti_liq)."""
    con = ro_con()
    for sym in MAJORS:
        df = load_df(con, sym)
        if df is None:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        highs = df["high"].values
        cum = np.maximum.accumulate(highs)
        last_peak = 0
        ages = np.empty(len(highs))
        for i in range(len(highs)):
            if highs[i] >= cum[i] and (i == 0 or highs[i] > highs[i - 1]):
                last_peak = i           # nouveau sommet strict
            ages[i] = (idx_ns[i] - idx_ns[last_peak]) / 86400e9
        for e in events:
            if e["sym"] != sym:
                continue
            bi = int(np.searchsorted(idx_ns, e["ts_ms"], side="left"))
            if bi >= len(idx_ns):
                bi = len(idx_ns) - 1
            e["age_dd"] = float(ages[bi])
    con.close()


# ------------------------------------------------------- la grille 2×2 --
def pair_grid(events: list[dict], n70: int, f1: str, f2: str) -> dict:
    """2×2 par médianes TRAIN ; additif ajusté SUR TRAIN, jugé en VAL."""
    rows = []
    for i, e in enumerate(events):
        v1, v2 = e.get(f1, np.nan), e.get(f2, np.nan)
        if np.isfinite(v1) and np.isfinite(v2):
            rows.append((i, float(v1), float(v2), e["r_not"]))
    tr = [r for r in rows if r[0] < n70]
    va = [r for r in rows if r[0] >= n70]
    out = {"n_tr": len(tr), "n_va": len(va), "cells": {}, "ok": len(tr) > 0}
    if not tr or not va:
        out["ok"] = False
        return out
    m1 = float(np.median([r[1] for r in tr]))
    m2 = float(np.median([r[2] for r in tr]))
    out["m1"], out["m2"] = m1, m2

    def cell_of(r):
        a = "hi" if r[1] > m1 else "lo"
        b = "hi" if r[2] > m2 else "lo"
        return a + "/" + b

    grand = float(np.mean([r[3] for r in tr]))
    # marges : moyenne conditionnelle − grand mean (décomposition additive
    # standard deux facteurs, ajustée SUR TRAIN uniquement)
    marg1 = {"lo": 0.0, "hi": 0.0}
    marg2 = {"lo": 0.0, "hi": 0.0}
    for side in ("lo", "hi"):
        v1s = [r[3] for r in tr if ("hi" if r[1] > m1 else "lo") == side]
        v2s = [r[3] for r in tr if ("hi" if r[2] > m2 else "lo") == side]
        if v1s:
            marg1[side] = float(np.mean(v1s)) - grand
        if v2s:
            marg2[side] = float(np.mean(v2s)) - grand

    for name in CELL_NAMES:
        a, b = name.split("/")
        pred = grand + marg1[a] + marg2[b]
        tr_in = [r for r in tr if cell_of(r) == name]
        va_in = [r for r in va if cell_of(r) == name]
        tr_c = [r[3] for r in tr_in]
        va_c = [r[3] for r in va_in]
        esp_tr = float(np.mean(tr_c)) if tr_c else float("nan")
        esp_va = float(np.mean(va_c)) if va_c else float("nan")
        out["cells"][name] = {
            "n_tr": len(tr_c), "n_va": len(va_c),
            "wr_tr": 100.0 * float(np.mean(np.array(tr_c) > 0)) if tr_c else np.nan,
            "wr_va": 100.0 * float(np.mean(np.array(va_c) > 0)) if va_c else np.nan,
            "esp_tr": esp_tr, "esp_va": esp_va,
            "pred": pred,
            "dev_tr": esp_tr - pred if tr_c else np.nan,
            "dev_va": esp_va - pred if va_c else np.nan,
            "mae_tr": float(np.nanmean([events[r[0]]["mae_adverse"]
                                        for r in tr_in])) if tr_in else np.nan,
        }
    return out


def verdict_cell(c: dict) -> tuple[bool, str]:
    """Garde dur pré-enregistré (16 tests)."""
    if c["n_tr"] < MIN_N_TR:
        return False, f"n TRAIN {c['n_tr']} < {MIN_N_TR}"
    if c["n_va"] < MIN_N_VA:
        return False, f"n VAL {c['n_va']} < {MIN_N_VA} (invérifiable)"
    if not (np.isfinite(c["dev_tr"]) and np.isfinite(c["dev_va"])):
        return False, "écart non calculable"
    if abs(c["dev_va"]) < DEV_MIN:
        return False, f"|écart VAL| {abs(c['dev_va']):.2f} < {DEV_MIN} pts"
    if np.sign(c["dev_tr"]) != np.sign(c["dev_va"]):
        return False, f"signe TRAIN {c['dev_tr']:+.2f} ≠ VAL {c['dev_va']:+.2f}"
    return True, "PASS"


# ------------------------------------------------------------------ main --
def main() -> int:
    warnings.filterwarnings("ignore", message="Mean of empty slice")
    print("[ix2d] univers 4 flux (briques al_score_v2 / the_machine)…",
          flush=True)
    uni = build_universe()
    events = uni["events"]
    print(f"[ix2d] events majors {len(events)} / gated {len(uni['gated'])} "
          f"/ meme {len(uni['meme'])} / surv {len(uni['surv'])} / spike "
          f"{len(uni['spike'])}", flush=True)

    # r_not : copie EXACTE al_score_v2.main (% du notionnel, indépendant
    # du sizing) — l'espérance de chaque cellule.
    for e in events:
        fund_pct = uni["fh"].get(e["sym"], 0.0) * e.get("hold_h", 24)
        e["r_not"] = (e["price_ret_short"] + e.get("fund_sign", 1) * fund_pct
                      - e["fee_rt_bps"] / 100.0)

    attach_age_dd(events)

    # baseline bit-repro AVANT toute comparaison (obligatoire)
    base_fn = machine_fn_factory(uni["med_majors"], uni["med_meme"],
                                 uni["med_spike"])
    base = sim(uni, base_fn)
    b0 = bloc(base, "baseline")
    print(f"[ix2d] baseline ${base['balance']:,.2f} ({b0['roi']:+.0f} %/an) "
          f"DD {base['max_dd']:.1f} % liq {base['n_liq']} mois nég "
          f"{b0['neg']} (officiel : $4,004.94 / +3905 % / 24.8 % / 0)",
          flush=True)

    n70 = int(len(events) * TRAIN_FRAC)
    print(f"[ix2d] split {TRAIN_FRAC:.0%} par le temps : TRAIN {n70} / "
          f"VAL {len(events) - n70}", flush=True)

    # ——— les 4 paires × 4 cellules = 16 tests (garde dur) ———
    results = {}
    n_tests = n_pass = 0
    for f1, f2, label in PAIRS:
        g = pair_grid(events, n70, f1, f2)
        results[label] = g
        print(f"\n=== {label}  (médianes TRAIN : {f1}≤{g.get('m1', float('nan')):.4g} "
              f"/ {f2}≤{g.get('m2', float('nan')):.4g} ; n TR {g['n_tr']} "
              f"VA {g['n_va']}) ===", flush=True)
        for name in CELL_NAMES:
            c = g["cells"][name]
            n_tests += 1
            ok, why = verdict_cell(c)
            n_pass += ok
            print(f"  {name:6s} TR n={c['n_tr']:3d} WR {c['wr_tr']:5.1f} % "
                  f"esp {c['esp_tr']:+.3f} dev {c['dev_tr']:+.3f} | "
                  f"VA n={c['n_va']:3d} WR {c['wr_va']:5.1f} % esp "
                  f"{c['esp_va']:+.3f} dev {c['dev_va']:+.3f} | "
                  f"pred {c['pred']:+.3f} maeTR {c['mae_tr']:.2f} → "
                  f"{'PASS' if ok else 'fail'} ({why})", flush=True)
    print(f"\n[ix2d] garde multiplicité : {n_pass}/{n_tests} PASS "
          f"(attendu 0-1)", flush=True)

    # ——— SI PASS : UNE intervention de sizing max ———
    best = None
    for label, g in results.items():
        if not g.get("ok"):
            continue
        for name in CELL_NAMES:
            c = g["cells"][name]
            ok, _ = verdict_cell(c)
            if ok:
                score = abs(c["dev_va"])
                cand = (label, name, c, score)
                if best is None or score > best[3]:
                    best = cand
    sized_r = None
    if best is not None:
        label, name, c, _ = best
        # la cellule toxique (écart négatif = pire que l'additif prédit)
        # est coupée ×0,75 ; la porteuse est boostée ×1,25 — UNE seule.
        toxic = c["dev_va"] < 0
        mult = 0.75 if toxic else 1.25
        f1, f2 = next((f1, f2) for f1, f2, lb in PAIRS if lb == label)
        m1, m2 = results[label]["m1"], results[label]["m2"]
        a, b = name.split("/")

        def flag(e):
            v1, v2 = e.get(f1, np.nan), e.get(f2, np.nan)
            if not (np.isfinite(v1) and np.isfinite(v2)):
                return False
            s1 = "hi" if v1 > m1 else "lo"
            s2 = "hi" if v2 > m2 else "lo"
            return e.get("strategy") == "cascade_10x" and s1 + "/" + s2 == name

        for e in events:
            e["ix_mult"] = mult if flag(e) else 1.0
        n_touch = sum(1 for e in uni["gated"] if e["ix_mult"] != 1.0)

        def sized_fn(e, st=None):
            sz = base_fn(e, st)
            if e.get("ix_mult", 1.0) != 1.0 and sz > 0:
                sz = sz * e["ix_mult"]
                if e.get("strategy") == "cascade_10x":
                    sz = min(sz, CAP_10X)     # plafond absolu machine
            return sz

        sized_r = sim(uni, sized_fn)
        bs = bloc(sized_r, "sized")
        print(f"\n[ix2d] INTERVENTION : cellule {label} [{name}] "
              f"({'toxique ×0,75' if toxic else 'porteuse ×1,25'}) — "
              f"{n_touch} trades cascade touchés", flush=True)
        print(f"[ix2d] sized   ${sized_r['balance']:,.2f} ({bs['roi']:+.0f} "
              f"%/an) DD {sized_r['max_dd']:.1f} % liq {sized_r['n_liq']} "
              f"mois nég {bs['neg']} — vs baseline ${base['balance']:,.2f} "
              f"DD {base['max_dd']:.1f} % mois nég {b0['neg']}", flush=True)
        roi_ok = sized_r["balance"] >= base["balance"]
        dd_ok = sized_r["max_dd"] <= base["max_dd"]
        neg_ok = bs["neg"] <= b0["neg"]
        print(f"[ix2d] critères : ROI {'OK' if roi_ok else 'FAIL'} / "
              f"DD {'OK' if dd_ok else 'FAIL'} / mois nég "
              f"{'OK' if neg_ok else 'FAIL'}", flush=True)
        interven = {"label": label, "name": name, "mult": mult,
                    "toxic": toxic, "n_touch": n_touch,
                    "roi_ok": roi_ok, "dd_ok": dd_ok, "neg_ok": neg_ok,
                    "bloc": bs}
    else:
        interven = None

    # ——— le rapport ———
    write_report(results, n_tests, n_pass, base, b0, sized_r, interven,
                 n70, len(events))
    print(f"[ix2d] rapport : {REPORTS / 'interactions-2d-2026-09-28.md'}",
          flush=True)
    return 0


def write_report(results, n_tests, n_pass, base, b0, sized_r, interven,
                 n70, n_ev) -> None:
    lines = [
        "# INTERACTIONS 2D — les cellules que l'additif ne voit pas",
        "28/09/2026 — 230 events cascade majors (univers machine 4 flux "
        "`--vol-spike ON`, briques `al_score_v2`/`the_machine` importées, "
        "klines.db lecture seule). Split 70/30 PAR LE TEMPS "
        f"(TRAIN {n70} / VAL {n_ev - n70}). Coupures = médianes TRAIN. "
        "Espérance = r_not % du notionnel (maker RT flux cascade). "
        "Additif ajusté SUR TRAIN : pred = grand mean + marge f1 + marge f2 ; "
        "écart = cellule − pred (ce que les marges ne prédisent pas).",
        "",
        "**Garde multiplicité pré-enregistré (16 tests)** : n ≥ 20/cellule "
        "TRAIN, |écart VAL| ≥ 3,0 pts d'espérance, signe TRAIN = VAL, "
        "n VAL ≥ 5. n=230 → fragile par construction : barre haute, la "
        "plupart doivent FAIL.",
        "",
        "« age » = âge du DRAWDOWN (jours depuis le plus haut glissant, "
        "même référence cummax-highs que dd_pct) — l'âge-token est "
        "impossible sur les majeures (même date de snapshot klines pour "
        "les 6 → aliasage au split). Analogue ex-ante de la lifecycle "
        "âge × dd.",
        "",
    ]
    for label, g in results.items():
        if not g.get("ok"):
            lines.append(f"## {label} — données insuffisantes")
            lines.append("")
            continue
        lines.append(f"## {label} — médianes TRAIN : "
                     f"{g['m1']:.4g} / {g['m2']:.4g} (n TR {g['n_tr']} / "
                     f"VA {g['n_va']})")
        lines.append("")
        lines.append("| Cellule | n TR | WR TR | esp TR | écart TR | n VA | "
                     "WR VA | esp VA | écart VA | pred additif | verdict |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for name in CELL_NAMES:
            c = g["cells"][name]
            ok, why = verdict_cell(c)
            lines.append(
                f"| {name} | {c['n_tr']} | {c['wr_tr']:.1f} % | "
                f"{c['esp_tr']:+.3f} | {c['dev_tr']:+.3f} | {c['n_va']} | "
                f"{c['wr_va']:.1f} % | {c['esp_va']:+.3f} | "
                f"{c['dev_va']:+.3f} | {c['pred']:+.3f} | "
                f"{'**PASS**' if ok else 'fail'} — {why} |")
        lines.append("")
    lines.append(f"## Verdict global : {n_pass}/{n_tests} PASS "
                 f"(attendu 0-1)")
    lines.append("")
    if interven:
        bs = interven["bloc"]
        mr = bs["mr"]
        lines.append(
            f"## Intervention sizing (UNE max) : {interven['label']} "
            f"[{interven['name']}] ×{interven['mult']} "
            f"({'toxique coupée' if interven['toxic'] else 'porteuse boostée'}, "
            f"plafond 0,50·K respecté) — {interven['n_touch']} trades cascade "
            "touchés")
        lines.append("")
        lines.append("| Config | Balance | ROI/an | DD | Liq | Mois nég | "
                     "Record mois | Pire mois |")
        lines.append("|---|---|---|---|---|---|---|---|")
        lines.append(
            f"| BASELINE 4 flux | ${base['balance']:,.2f} | "
            f"{b0['roi']:+.0f} % | {base['max_dd']:.1f} % | "
            f"{base['n_liq']} | {b0['neg']} | {b0['rec']:+.1f} % | "
            f"{b0['worst']:+.1f} % |")
        lines.append(
            f"| SIZED | ${sized_r['balance']:,.2f} | {bs['roi']:+.0f} % | "
            f"{sized_r['max_dd']:.1f} % | {sized_r['n_liq']} | {bs['neg']} | "
            f"{bs['rec']:+.1f} % | {bs['worst']:+.1f} % |")
        lines.append("")
        crit = (f"ROI {'≥ OK' if interven['roi_ok'] else '< FAIL'} / "
                f"DD {'≤ OK' if interven['dd_ok'] else '> FAIL'} / "
                f"mois nég {'≤ OK' if interven['neg_ok'] else '> FAIL'}")
        verdict = "RETENU pour re-test" if all(
            [interven["roi_ok"], interven["dd_ok"],
             interven["neg_ok"]]) else "REJETÉ"
        lines.append(f"**Critères : {crit} → {verdict}.** Garde-fou "
                     "composé-des-mois : la somme des PnL mensuels et le "
                     "produit des (1+roi) recollent avec le final.")
        lines.append("")
        lines.append("| Mois | ROI % | PnL $ |")
        lines.append("|---|---|---|")
        for x in mr:
            lines.append(f"| {x['month']} | {x['roi']:+.1f} | "
                         f"{x['pnl']:+,.2f} |")
        lines.append("")
    else:
        lines.append(
            "## Pas d'intervention")
        lines.append("")
        lines.append(
            f"{'Aucune cellule ne passe le garde' if n_pass == 0 else 'PASS non retenu pour intervention'}"
            " — les marges prédisent les cellules : **aucune preuve "
            "d'interaction exploitable** sur les 230 events. Le gate "
            "additif v1 n'a rien manqué de mesurable à cette échelle ; "
            "la cellule lifecycle 30-90j/20-50 % (n=1783, memecoins) ne "
            "se transpose pas en interaction majeures 2×2.")
        lines.append("")
    lines.append(f"*Baseline bit-repro : ${base['balance']:,.2f} "
                 f"({b0['roi']:+.0f} %/an) @ DD {base['max_dd']:.1f} %, "
                 f"{base['n_liq']} liq — officiel $4,004.94 / +3905 % / "
                 "24,8 % / 0. Script : `scripts/interactions_2d_test.py` "
                 "(lecture seule klines.db).*")
    (REPORTS / "interactions-2d-2026-09-28.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
