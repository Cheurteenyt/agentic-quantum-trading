#!/usr/bin/env python
"""QUBO × PREMIUM v2 — les deux variantes ordonnées par le propriétaire (05/10).

Le contexte : v1 (tilt majors-seulement, bas) = FAIL, 1 liq VAL (SOLUSDT
2026-08-26, MAE 13,08 % — liquide à 11x, 10x ET 8x ; il aurait fallu ≤ 7x).
Le bug hunt a validé le code de v1 (run_stack recalcule : MAE ≥ 100/lev − 0,5).
Le budget W40 était épuisé (20/20) — le propriétaire a ORDONNÉ ces deux
variantes explicitement (« il faut tester sur tous les actifs et en reverse »)
: dépassement autorisé par le propriétaire, consommé en ouverture de W41.

VARIANTE A — « tous les actifs » : le régime = la médiane du funding sur TOUS
les symboles couverts (quorum ≥ 20/71, l'info alt parle aussi), même seuil
p50 TRAIN, même sweep {4, 6, 8}, mêmes critères. Fenêtre = depuis que 20
symboles sont couverts.
VARIANTE B — « reverse » : le régime majors de v1 mais INVERSÉ — lever dans
le chaud (L_hot = 12, ≤ plafond 0-liq 12,26x), jugé comme un vrai candidat.
Fenêtre = la couverture majors (2025-10-27 →).

CRITÈRES PASS/FAIL (écrits avant le run, identiques à v1) :
  PASS si VAL : n_liq = 0 ET ret/DD ≥ 1.10 × baseline ET DD ≤ 25 %.

  .venv/bin/python scripts/studies/qubo_premium_allassets_reverse.py
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
    bloc, build_events, base_sizer, weighted_sizer)
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402

DATE = "2026-10-05"
W_CODIFIED = {"cascade_10x": 0.857, "cascade_meme": 0.857,
              "survivor_long": 2.0, "vol_spike_6h": 0.857}
LEV_CALM = 11.0
L_HOT_GRID = [4.0, 6.0, 8.0]
L_HOT_REVERSE = 12.0
KDB = ROOT / "data" / "warehouse" / "klines.db"
QUORUM_ALL = 20
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ASTERUSDT")


def funding_all_series():
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    series = {}
    for sym, in con.execute("SELECT DISTINCT symbol FROM funding_history"):
        rows = con.execute(
            "SELECT funding_time, rate FROM funding_history WHERE symbol=? "
            "ORDER BY funding_time", (sym,)).fetchall()
        if rows:
            series[sym] = (np.array([r[0] for r in rows], dtype=np.float64),
                           np.array([r[1] for r in rows], dtype=np.float64))
    con.close()
    return series


def regime_at(events, series, syms, quorum):
    out = np.full(len(events), np.nan)
    arrs = [(series[s][0], series[s][1]) for s in syms if s in series]
    for i, e in enumerate(events):
        ts_ms = e["ts_ms"] / 1e6
        vals = []
        for t, v in arrs:
            k = int(np.searchsorted(t, ts_ms, side="right")) - 1
            if k >= 0:
                vals.append(v[k])
        if len(vals) >= quorum:
            out[i] = float(np.median(vals))
    return out


def run_cell(events, base, fh, lev_major_fn):
    evs = [{**e, "lev": lev_major_fn(e) if e["strategy"] == "cascade_10x"
            else e["lev"]} for e in events]
    return run_stack(evs, CAPITAL, weighted_sizer(base, W_CODIFIED), fh)


def ret_dd(res):
    months = monthly_rows(res["trades"], CAPITAL)
    roi_an = (res["balance"] / CAPITAL) ** (12 / max(len(months), 1)) - 1
    return (roi_an * 100) / max(res["max_dd"], 0.1)


def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[qpr2] events {dict(counts)} en {time.time()-t0:.0f}s", flush=True)
    series = funding_all_series()
    base = base_sizer(ctx)
    L: list[str] = [
        "# QUBO × PREMIUM v2 — tous les actifs + reverse (l'ordre du propriétaire)",
        f"{DATE} — W40 épuisé (20/20), dépassement autorisé par le propriétaire. "
        "CHAQUE variante vit dans SA fenêtre de couverture (le départ diffère : "
        "les alts commencent 2023, les majeures 2025-10-27), split 70/30 "
        "temporel propre, baseline re-courue par fenêtre. Critères : 0 liq VAL, "
        "ret/DD ≥ 1.10× baseline, DD ≤ 25 %.", ""]
    verdicts: dict[str, str] = {}

    def window(start_ms):
        cov = [e for e in all_ev if e["ts_ms"] / 1e6 >= start_ms]
        ts = np.array([e["ts_ms"] for e in cov])
        t_split = ts.min() + 0.7 * (ts.max() - ts.min())
        return ([e for e in cov if e["ts_ms"] < t_split],
                [e for e in cov if e["ts_ms"] >= t_split], t_split)

    def seuil_of(train_ev, syms, quorum):
        v = regime_at(train_ev, series, syms, quorum)
        v = v[np.isfinite(v)]
        return float(np.quantile(v, 0.5)) if len(v) else None

    def sweep_and_judge(tag, syms, quorum, start_ms, hot_reverse=False):
        tr, va, tsplit = window(start_ms)
        if not tr or not va:
            verdicts[tag] = "NO-GO (fenêtre vide)"
            return
        base_va = run_cell(va, base, fh, lambda e: LEV_CALM)
        b_rr = ret_dd(base_va)
        seuil = seuil_of(tr, syms, quorum)
        if seuil is None:
            verdicts[tag] = "NO-GO (seuil vide — couverture insuffisante)"
            print(f"[qpr2] {tag}: NO-GO seuil vide", flush=True)
            return
        v_tr = regime_at(tr, series, syms, quorum)
        v_va = regime_at(va, series, syms, quorum)
        hot_tr = {e["ts_ms"] for e, h in zip(tr, v_tr > seuil) if h}
        hot_va = {e["ts_ms"] for e, h in zip(va, v_va > seuil) if h}
        n_maj_tr = sum(1 for e in tr if e["strategy"] == "cascade_10x")
        n_maj_va = sum(1 for e in va if e["strategy"] == "cascade_10x")
        print(f"[qpr2] {tag}: seuil {seuil:.2e} | hot T {len(hot_tr)}/{len(tr)} "
              f"V {len(hot_va)}/{len(va)} | majors T/V {n_maj_tr}/{n_maj_va}",
              flush=True)
        L.extend([
            f"## {tag}", "",
            f"Fenêtre depuis "
            f"{datetime.fromtimestamp(start_ms/1000, tz=timezone.utc):%Y-%m-%d}, "
            f"split {datetime.fromtimestamp(tsplit/1e9, tz=timezone.utc):%Y-%m-%d}, "
            f"majors T/V {n_maj_tr}/{n_maj_va}, seuil {seuil:.2e}, hot VAL "
            f"{len(hot_va)}/{len(va)}. Baseline : ${base_va['balance']:,.0f} "
            f"(DD {base_va['max_dd']:.1f} %, liq {base_va['n_liq']}, "
            f"ret/DD {b_rr:.2f}).", ""])
        if hot_reverse:
            c_va = run_cell(va, base, fh,
                            lambda e: L_HOT_REVERSE if e["ts_ms"] in hot_va
                            else LEV_CALM)
            rr = ret_dd(c_va)
            dead = c_va["n_liq"] > 0
            v = "FAIL (cellule MORTE — liq VAL)" if dead else (
                "PASS" if (rr >= 1.10 * b_rr and c_va["max_dd"] <= 25.0)
                else "FAIL (critères ret/DD ou DD)")
            verdicts[tag] = v
            L.extend([f"Reverse : L_hot = {L_HOT_REVERSE:g}. VAL → "
                      f"liq {c_va['n_liq']}, DD {c_va['max_dd']:.1f} %, "
                      f"ret/DD {rr:.2f} → **{v}**."])
            print(f"[qpr2] {tag}: VAL liq {c_va['n_liq']} ret/DD {rr:.2f} → {v}",
                  flush=True)
            return
        cands = []
        for lh in L_HOT_GRID:
            r = run_cell(tr, base, fh,
                         lambda e, lh2=lh: lh2 if e["ts_ms"] in hot_tr
                         else LEV_CALM)
            cands.append({"l": lh, "r": r})
            L.append(f"- L_hot {lh:g}x : T ${r['balance']:,.0f} "
                     f"(DD {r['max_dd']:.1f} %, liq {r['n_liq']})")
        ok = [c for c in cands if c["r"]["n_liq"] == 0
              and c["r"]["max_dd"] <= 25.0 and c["r"]["balance"] > CAPITAL]
        if not ok:
            verdicts[tag] = "FAIL (aucun candidat TRAIN viable)"
            print(f"[qpr2] {tag}: FAIL aucun candidat TRAIN viable", flush=True)
            return
        ch = sorted(ok, key=lambda c: -c["r"]["balance"])[0]
        c_va = run_cell(va, base, fh,
                        lambda e: ch["l"] if e["ts_ms"] in hot_va else LEV_CALM)
        rr = ret_dd(c_va)
        dead = c_va["n_liq"] > 0
        v = "FAIL (cellule MORTE — liq VAL)" if dead else (
            "PASS" if (rr >= 1.10 * b_rr and c_va["max_dd"] <= 25.0)
            else "FAIL (critères ret/DD ou DD)")
        verdicts[tag] = v
        L.extend(["", f"Choisi : L_hot = {ch['l']:g}. VAL → liq {c_va['n_liq']}, "
                  f"DD {c_va['max_dd']:.1f} %, ret/DD {rr:.2f} → **{v}**."])
        print(f"[qpr2] {tag}: L_hot={ch['l']:g} VAL liq {c_va['n_liq']} "
              f"ret/DD {rr:.2f} → {v}", flush=True)

    # ——— VARIANTE A : le régime de TOUS les actifs (quorum 20/71) ———
    firsts = sorted(t[0] for t, _ in series.values())
    all_start = firsts[QUORUM_ALL - 1]
    sweep_and_judge("A (tous actifs, quorum 20)", list(series), QUORUM_ALL,
                    all_start)

    # ——— VARIANTE B : le REVERSE majors (lever à 12x dans le chaud) ———
    maj_start = min(series[s][0][0] for s in MAJORS)
    sweep_and_judge("B (reverse majors 12x)", MAJORS, 4, maj_start,
                    hot_reverse=True)

    # ——— le diagnostic du régime de l'event liq (fenêtre majors) ———
    tr_b, va_b, _ = window(maj_start)
    seuil_b = seuil_of(tr_b, MAJORS, 4)
    r_maj_va = regime_at(va_b, series, MAJORS, 4)
    for e, rv in zip(va_b, r_maj_va):
        if e["strategy"] == "cascade_10x" and \
                e["mae_adverse"] >= 100.0 / LEV_CALM - 0.5:
            L.extend(["", f"Diagnostic : l'event liq VAL majors = {e['sym']} "
                      f"(MAE {e['mae_adverse']:.2f} %) — régime majors "
                      f"{rv:.2e} vs seuil {seuil_b:.2e} → "
                      f"{'HOT' if rv > seuil_b else 'CALM'}."])
            break

    L.extend(["", "## VERDICTS", ""])
    for k, v in verdicts.items():
        L.append(f"- **{k} : {v}**")
    L.extend(["", "Rappel v1 : FAIL (L_hot=8, 1 liq VAL — SOLUSDT MAE 13,08 %).",
              ""])

    out = ROOT / "reports" / f"qubo-premium-v2-{DATE}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[qpr2] rapport -> {out}", flush=True)
    print(f"[qpr2] VERDICTS: {verdicts}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
