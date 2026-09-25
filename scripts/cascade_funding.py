#!/usr/bin/env python
"""LA CASCADE × LE FUNDING — conditionner le signal roi par le positioning.

Le harnais a montré que la cascade accélérée short 20x est le signal roi.
L'AL Score la conditionne par le RISQUE (volatilité, drawdown). La
dimension manquante : le POSITIONING — le funding. L'hypothèse :
  - funding HAUT (percentile) à l'entrée = longs entassés, piégés,
    encore en train de payer → la continuation baissière est nourrie
    par leurs liquidations → le short gagne PLUS
  - funding BAS/négatif = les shorts sont déjà entassés → risque de
    squeeze → le short gagne MOINS

Méthode identique à l'AL Score (la discipline du projet) :
  - percentile de funding AS-OF à l'entrée (le dernier taux connu ≤ t
    contre ses 30 derniers jours — zéro look-ahead)
  - split train/val PAR LE TEMPS 70/30
  - politique choisie sur TRAIN, jugée sur VAL, sim complet 1 an
  - CONTRÔLE INVERSE (si l'inverse gagne aussi, ne pas croire)

  .venv/bin/python scripts/cascade_funding.py
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.portfolio_sim import KDB, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, run_stack)

REPORTS = ROOT / "reports"
WIN_NS = 30 * 86400 * 10**9


def add_funding_percentiles(events: list[dict]) -> None:
    """Pour chaque événement : le percentile AS-OF du dernier taux de
    funding connu au signal, contre les 30 derniers jours du symbole."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=5)
    by_sym: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = by_sym.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)  # ms→ns / s→ns
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    con.close()

    for e in events:
        ft = by_sym.get(e["sym"])
        if not ft or len(ft[0]) < 30:
            e["fund_pctl"] = float("nan")
            continue
        ts, rt = np.array(ft[0]), np.array(ft[1])
        t0 = e["ts_ms"]                                # déjà en ns (nom hérité)
        pos = int(np.searchsorted(ts, t0, side="right")) - 1
        if pos < 0:
            e["fund_pctl"] = float("nan")
            continue
        lo = np.searchsorted(ts, t0 - WIN_NS, side="left")
        window = rt[lo:pos + 1]
        if len(window) < 10:
            e["fund_pctl"] = float("nan")
            continue
        e["fund_pctl"] = float(np.mean(window <= rt[pos]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", choices=["majors", "all"], default="majors")
    args = ap.parse_args()

    regime = None
    from scripts.portfolio_sim import btc_regime_series
    regime = btc_regime_series()
    events = collect_featured(regime, args.universe)
    for e in events:
        e["strategy"] = "cascade"
        e["lev"] = 20
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    add_funding_percentiles(events)

    # le funding hourly pour le sim (reçu par le short)
    con = sqlite3.connect(KDB)
    acc: dict[str, list[float]] = {}
    for s, r in con.execute("SELECT symbol, rate FROM funding_history"):
        try:
            acc.setdefault(s, []).append(float(r))
        except (TypeError, ValueError):
            continue
    con.close()
    fh = {s: sum(v) / len(v) * 100 / 8 for s, v in acc.items()}

    # --- l'analyse univariée : PnL et liq par tercile de funding (TRAIN) ---
    k = int(len(events) * 0.7)
    train, val = events[:k], events[k:]
    fp_tr = np.array([e["fund_pctl"] for e in train], dtype=float)
    ok = np.isfinite(fp_tr)
    # le PnL de marge par trade (prix seul + funding + frais, lev 20x)
    def margin_pnl(e: dict) -> float:
        return (e["price_ret_short"] * 20
                + fh.get(e["sym"], 0.0) * 24 * 20 / 100
                - MAKER_RT * 20 / 100)
    liq_tr = np.array([e["mae_adverse"] >= 4.5 for e in train])
    pnl_tr = np.array([margin_pnl(e) for e in train])

    q33, q66 = np.nanquantile(fp_tr, [1/3, 2/3])
    lines = [
        "# LA CASCADE × LE FUNDING — le positioning conditionne le roi",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(events)} événements cascade ({args.universe}), percentile de "
        f"funding AS-OF 30j. Train {int(ok.sum())} scorés / Val "
        f"{int(np.isfinite([e['fund_pctl'] for e in val]).sum())}.", "",
        "## Terciles de funding percentile (TRAIN) — marge/trade à 20x", "",
        "| Tercile | N | Marge/trade | Taux de liq (MAE 4,5 %) |",
        "|---|---|---|---|",
    ]
    for label, m in (("T1 (funding bas / shorts entassés)", fp_tr <= q33),
                     ("T2", (fp_tr > q33) & (fp_tr <= q66)),
                     ("T3 (funding haut / longs piégés)", fp_tr > q66)):
        mm = m & ok
        if not mm.any():
            continue
        lines.append(f"| {label} | {int(mm.sum())} | "
                     f"{np.mean(pnl_tr[mm]):+.2f} % | "
                     f"{np.mean(liq_tr[mm])*100:.1f} % |")

    # --- les politiques (choisies sur TRAIN, jugées sur VAL) ---
    def base_fn(e: dict) -> float:
        s = e.get("al_score", float("nan"))
        if np.isnan(s):
            return 0.05
        return 0.0 if s >= 0.75 else 0.075

    def mod_fn(boost: float, cut: float):
        def fn(e: dict) -> float:
            sz = base_fn(e)
            if sz <= 0:
                return 0.0
            p = e.get("fund_pctl", float("nan"))
            if np.isnan(p):
                return sz
            return sz * (boost if p >= q66 else cut)
        return fn

    policies = [("BASE AL 7,5 %/gate (référence)", base_fn, None),
                ("FUNDING boost ×1,3 / cut ×0,7", mod_fn(1.3, 0.7), "inv13"),
                ("FUNDING boost ×1,5 / cut ×0,5", mod_fn(1.5, 0.5), "inv15")]
    lines += ["", "## Le wallet séquentiel (100 $, maker, hold 24h)", "",
              "| Politique | TRAIN 100 $ → | DD | VAL 100 $ → | DD |",
              "|---|---|---|---|---|"]
    results = {}
    for label, fn, _ in policies:
        tr_s = run_stack(train, CAPITAL, fn, fh)
        va_s = run_stack(val, CAPITAL, fn, fh)
        results[label] = (tr_s, va_s, fn)
        lines.append(f"| {label} | ${tr_s['balance']:,.2f} | "
                     f"{tr_s['max_dd']:.1f} % | ${va_s['balance']:,.2f} | "
                     f"{va_s['max_dd']:.1f} % |")

    # le contrôle inverse du meilleur modulé
    best_mod = max(("FUNDING boost ×1,3 / cut ×0,7",
                    "FUNDING boost ×1,5 / cut ×0,5"),
                   key=lambda l: results[l][0]["balance"])
    boost, cut = (1.3, 0.7) if "1,3" in best_mod else (1.5, 0.5)
    inv_fn = mod_fn(cut, boost)          # l'inverse : booster les T1
    inv_full = run_stack(events, CAPITAL, inv_fn, fh)
    best_full = run_stack(events, CAPITAL, results[best_mod][2], fh)
    base_full = run_stack(events, CAPITAL, base_fn, fh)

    ok_dir = best_full["balance"] > base_full["balance"] * 1.05
    ok_inv = inv_full["balance"] > best_full["balance"]
    if ok_dir and not ok_inv:
        verdict = (f"LE POSITIONING MARCHE — {best_mod} améliore le wallet, "
                   f"le contrôle inverse est battu")
    elif ok_dir and ok_inv:
        verdict = ("AMBIGU — direct et inverse s'améliorent tous deux : "
                   "ne pas croire")
    else:
        verdict = ("LE FUNDING N'APPORTE RIEN à la cascade gated — "
                   "l'AL Score reste le seul conditionnement validé")

    mrows = monthly_rows(best_full["trades"], CAPITAL)
    if mrows:
        rois_m = [r["roi"] for r in mrows]
        lines += ["", "## BLOC STATS — meilleure politique, sim complet", "",
                  "| Stat | Valeur |", "|---|---|",
                  f"| Wallet 100 $ → | **${best_full['balance']:,.2f}** |",
                  f"| ROI (1 an) | {(best_full['balance']/CAPITAL-1)*100:+.1f} % |",
                  f"| Max DD | {best_full['max_dd']:.1f} % |",
                  f"| Trades / liq | {best_full['n']} / {best_full['n_liq']} |",
                  f"| ROI mensuel moyen | {np.mean(rois_m):+.1f} % "
                  f"(pire {min(rois_m):+.1f} %) |"]
    lines += ["", f"## VERDICT : {verdict}", "",
              f"- base AL seule : ${base_full['balance']:,.2f} "
              f"(DD {base_full['max_dd']:.1f} %)",
              f"- {best_mod} : ${best_full['balance']:,.2f} "
              f"(DD {best_full['max_dd']:.1f} %)",
              f"- CONTRÔLE INVERSE : ${inv_full['balance']:,.2f} "
              f"(DD {inv_full['max_dd']:.1f} %)",
              "- discipline : percentile AS-OF (zéro look-ahead), seuils de "
              "TRAIN, VAL juge, inverse contrôle."]

    out = REPORTS / f"cascade-funding-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[cascade-funding] base ${base_full['balance']:,.2f} | "
          f"meilleure ${best_full['balance']:,.2f} | "
          f"inverse ${inv_full['balance']:,.2f}")
    print(f"[cascade-funding] {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
