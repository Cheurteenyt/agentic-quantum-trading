#!/usr/bin/env python
"""QUBO × PREMIUM — le levier majors conditionnel au régime de funding (05/10).

L'UNE variable (le budget de la semaine 2026-W40 : 1 seule expérience) :
la cellule QUBO joint CODIFIÉE (w=[0.857, 0.857, 2.0, 0.857], lev=[11,1,1,1])
reste figée ; le SEUL changement = le levier majors devient conditionnel au
régime premium ex ante :
  - régime = la MÉDIANE cross-sectionnelle du funding des 6 majeures, lue à la
    dernière stamp funding ≤ ts de l'event (zéro look-ahead) ;
  - seuil = la p50 des valeurs TRAIN ;
  - hot (médiane > seuil) → lev majors = L_hot ∈ {4, 6, 8} (compresser) ;
  - calm → 11 (inchangé).
Hypothèse : quand les longs paient cher (funding médian chaud), le 11x majors
est fragile → compresser améliore ret/DD sans créer de liq.
Contrôle inverse (info) : L_hot = 12 (lever dans le chaud ; ≤ plafond 0-liq
12.26x mesuré au joint).

CRITÈRES PASS/FAIL (écrits avant le run) :
  PASS si VAL : n_liq = 0 ET ret/DD_VAL ≥ 1.10 × baseline ET DD ≤ 25 %.
  FAIL sinon → registre, STOP (pas de re-tiraillement du seuil).

  .venv/bin/python scripts/studies/qubo_premium_regime.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.qubo_sizing import (  # noqa: E402
    FLUXES, bloc, build_events, base_sizer, weighted_sizer)
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402

DATE = "2026-10-05"
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ASTERUSDT")
W_CODIFIED = {"cascade_10x": 0.857, "cascade_meme": 0.857,
              "survivor_long": 2.0, "vol_spike_6h": 0.857}
LEV_CALM = 11.0
L_HOT_GRID = [4.0, 6.0, 8.0]
L_HOT_INVERSE = 12.0  # le contrôle : lever dans le chaud (info, PAS un candidat)
KDB = ROOT / "data" / "warehouse" / "klines.db"


def majors_funding_series() -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], float]:
    """(par majeure : times_ms, rates), le dernier timestamp couvert."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    series = {}
    last = 0.0
    for sym in MAJORS:
        rows = con.execute(
            "SELECT funding_time, rate FROM funding_history WHERE symbol=? "
            "ORDER BY funding_time", (sym,)).fetchall()
        t = np.array([r[0] for r in rows], dtype=np.float64)
        v = np.array([r[1] for r in rows], dtype=np.float64)
        series[sym] = (t, v)
        last = max(last, float(t[-1]) if len(t) else 0.0)
    con.close()
    return series, last


def regime_values(events: list[dict],
                  series: dict[str, tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    """La médiane majors du funding à chaque event (la dernière stamp ≤ ts).

    Quorum : ≥ 4 majeures couvertes (ASTER n'existe en funding que fin 2024 —
    exiger les 6 rendrait tout NaN avant sa cotation).
    """
    QUORUM = 4
    out = np.full(len(events), np.nan)
    for i, e in enumerate(events):
        ts_ms = e["ts_ms"] / 1e6  # ns → ms (le piège d'unité connu)
        vals = []
        for sym in MAJORS:
            t, v = series[sym]
            k = int(np.searchsorted(t, ts_ms, side="right")) - 1
            if k >= 0:
                vals.append(v[k])
        if len(vals) >= QUORUM:
            out[i] = float(np.median(vals))
    return out


def run_cell(events: list[dict], base, fh, lev_major_fn) -> dict:
    evs = [{**e, "lev": lev_major_fn(e) if e["strategy"] == "cascade_10x"
            else e["lev"]} for e in events]
    return run_stack(evs, CAPITAL, weighted_sizer(base, W_CODIFIED), fh)


def ret_dd(res: dict) -> float:
    months = monthly_rows(res["trades"], CAPITAL)
    roi_an = (res["balance"] / CAPITAL) ** (12 / max(len(months), 1)) - 1
    return (roi_an * 100) / max(res["max_dd"], 0.1)


def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[qpr] events {dict(counts)} en {time.time()-t0:.0f}s", flush=True)

    # LA FENÊTRE COUVERTE : le funding des majeures ne commence que le
    # 27/10/2025 — l'étude vit DANS cette fenêtre, split 70/30 temporel propre.
    # LIMITE AFFICHÉE : le verdict porte le poids du n majors (T/V imprimé).
    series, _ = majors_funding_series()
    cov_start_ms = min(t[0] for t, _ in series.values())
    cov = [e for e in all_ev if e["ts_ms"] / 1e6 >= cov_start_ms]
    ts = np.array([e["ts_ms"] for e in cov])
    t_split = ts.min() + 0.7 * (ts.max() - ts.min())
    train_ev = [e for e in cov if e["ts_ms"] < t_split]
    val_ev = [e for e in cov if e["ts_ms"] >= t_split]
    n_maj_tr = sum(1 for e in train_ev if e["strategy"] == "cascade_10x")
    n_maj_va = sum(1 for e in val_ev if e["strategy"] == "cascade_10x")
    print(f"[qpr] fenêtre couverte depuis "
          f"{datetime.fromtimestamp(cov_start_ms/1000, tz=timezone.utc):%Y-%m-%d} : "
          f"{len(cov)} events | split "
          f"{datetime.fromtimestamp(t_split/1e9, tz=timezone.utc):%Y-%m-%d} : "
          f"train {len(train_ev)} / val {len(val_ev)} | majors T/V "
          f"{n_maj_tr}/{n_maj_va}", flush=True)

    # ——— le régime premium ex ante ———
    v_tr = regime_values(train_ev, series)
    v_va = regime_values(val_ev, series)
    seuil = float(np.quantile(v_tr[np.isfinite(v_tr)], 0.5))
    hot_tr = int((v_tr > seuil).sum())
    hot_va = int((v_va > seuil).sum())
    print(f"[qpr] seuil p50 TRAIN = {seuil:.2e} | hot TRAIN {hot_tr}/{len(v_tr)} "
          f"| hot VAL {hot_va}/{len(v_va)}", flush=True)

    base = base_sizer(ctx)
    hot_set_tr = {e["ts_ms"] for e, h in zip(train_ev, v_tr > seuil) if h}
    hot_set_va = {e["ts_ms"] for e, h in zip(val_ev, v_va > seuil) if h}

    def fn_hot(l_hot, hot_set):
        return lambda e: (l_hot if e["ts_ms"] in hot_set else LEV_CALM)

    # ——— la baseline codifiée ———
    b_tr = run_cell(train_ev, base, fh, lambda e: LEV_CALM)
    b_va = run_cell(val_ev, base, fh, lambda e: LEV_CALM)
    b_fu = run_cell(all_ev, base, fh, lambda e: LEV_CALM)
    print(f"[qpr] baseline 11x : T ${b_tr['balance']:,.0f} (DD {b_tr['max_dd']:.1f}) "
          f"| V ${b_va['balance']:,.0f} (DD {b_va['max_dd']:.1f}, "
          f"liq {b_va['n_liq']})", flush=True)

    # ——— le sweep TRAIN (la sélection identique au joint) ———
    cands = []
    for l_hot in L_HOT_GRID:
        r = run_cell(train_ev, base, fh, fn_hot(l_hot, hot_set_tr))
        mrows = monthly_rows(r["trades"], CAPITAL)
        rois = [x["roi"] for x in mrows] or [0.0]
        cands.append({"l_hot": l_hot, "train": r,
                      "t_neg": int(sum(v < 0 for v in rois)),
                      "t_rec": max(rois)})
        print(f"[qpr] L_hot={l_hot:g}: T ${r['balance']:,.0f} "
              f"(DD {r['max_dd']:.1f}, liq {r['n_liq']}, {cands[-1]['t_neg']} neg)",
              flush=True)
    ok = [c for c in cands if c["train"]["n_liq"] == 0
          and c["train"]["max_dd"] <= 25.0 and c["train"]["balance"] > CAPITAL]
    pool = sorted(ok or cands,
                  key=lambda c: (0 if c["t_neg"] <= 1 else 1,
                                 -c["train"]["balance"], c["train"]["max_dd"]))
    chosen = pool[0]
    print(f"[qpr] CHOISI (TRAIN): L_hot={chosen['l_hot']:g}", flush=True)

    # ——— le jugement VAL ———
    c_va = run_cell(val_ev, base, fh, fn_hot(chosen["l_hot"], hot_set_va))
    c_fu = run_cell(all_ev, base, fh,
                    fn_hot(chosen["l_hot"], hot_set_tr | hot_set_va))
    inv_va = run_cell(val_ev, base, fh, fn_hot(L_HOT_INVERSE, hot_set_va))
    dead = c_va["n_liq"] > 0

    rr_b = ret_dd(b_va)
    rr_c = ret_dd(c_va)
    verdict = "PASS" if (not dead and rr_c >= 1.10 * rr_b
                         and c_va["max_dd"] <= 25.0) else "FAIL"

    # ——— le rapport ———
    L = ["# QUBO × PREMIUM — le levier majors conditionnel au régime de funding",
         f"{DATE} — UNE variable (budget W40 19/20) : la cellule jointe codifiée "
         "w=[0.857/0.857/2.0/0.857] lev=[11/1/1/1] figée ; le levier majors "
         "seulement devient conditionnel au régime premium ex ante (médiane "
         "funding des 6 majeures, la dernière stamp ≤ ts, seuil p50 TRAIN). "
         f"LIMITE : majors T/V = {n_maj_tr}/{n_maj_va} — le verdict porte ce "
         f"poids. Seuil = {seuil:.2e}. HOT TRAIN {hot_tr}/{len(v_tr)}, "
         f"VAL {hot_va}/{len(v_va)}.", "",
         "## Le sweep TRAIN", "",
         "| L_hot | Train $ | DD | liq | mois nég |", "|---|---|---|---|---|"]
    for c in cands:
        L.append(f"| {c['l_hot']:g}x | ${c['train']['balance']:,.0f} "
                 f"| {c['train']['max_dd']:.1f} % | {c['train']['n_liq']} "
                 f"| {c['t_neg']} |")
    L.append(f"| 11x (baseline) | ${b_tr['balance']:,.0f} "
             f"| {b_tr['max_dd']:.1f} % | {b_tr['n_liq']} | — |")
    L += ["", "## Le jugement VAL (1 liq = MORTE)", "",
          f"Choisi : L_hot = {chosen['l_hot']:g}. VAL baseline : "
          f"${b_va['balance']:,.0f} (DD {b_va['max_dd']:.1f} %, liq "
          f"{b_va['n_liq']}, ret/DD {rr_b:.1f}) → VAL candidat : "
          f"${c_va['balance']:,.0f} (DD {c_va['max_dd']:.1f} %, liq "
          f"**{c_va['n_liq']}**, ret/DD {rr_c:.1f}) → ratio ret/DD "
          f"{rr_c / rr_b:.2f}× la baseline.",
          f"Contrôle inverse (L_hot=12, lever dans le chaud, INFO) : "
          f"${inv_va['balance']:,.0f} (DD {inv_va['max_dd']:.1f} %, "
          f"liq {inv_va['n_liq']}).", "",
          "## VERDICT", "",
          f"**{verdict}** — critères : 0 liq VAL "
          f"({c_va['n_liq']}), ret/DD ≥ 1.10× ({rr_c / rr_b:.2f}×), "
          f"DD ≤ 25 % ({c_va['max_dd']:.1f} %).",
          f"FULL candidat : ${c_fu['balance']:,.0f} vs baseline "
          f"${b_fu['balance']:,.0f}.", ""]
    for res, lbl in ((b_tr, "BASELINE — TRAIN"), (b_va, "BASELINE — VAL"),
                     (c_tr := chosen["train"], f"CANDIDAT L_hot={chosen['l_hot']:g} — TRAIN"),
                     (c_va, "CANDIDAT — VAL"), (c_fu, "CANDIDAT — FULL")):
        lines, _ = bloc(res, lbl, CAPITAL)
        L += lines + [""]

    out = ROOT / "reports" / f"qubo-premium-regime-{DATE}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[qpr] rapport -> {out}", flush=True)
    print(f"[qpr] VERDICT: {verdict} | L_hot={chosen['l_hot']:g} | "
          f"ret/DD {rr_c:.1f} vs {rr_b:.1f} | liq VAL {c_va['n_liq']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
