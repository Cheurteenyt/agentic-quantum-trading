#!/usr/bin/env python
"""W41 — LES TROIS CHANTIERS QUBO (pré-enregistrés research/hypotheses/qubo-w41-trois-chantiers.md).

CH1 — MM liq-tolérant : la marge par trade plafonnée à k% du wallet
      (margin = balance × sz, une liq coûte exactement la marge — le cap
      sz ≤ k/100 rend k liqs absorbables). Sweep k ∈ {1, 2, 4} % sur TRAIN,
      jugement VAL : DD ≤ 25 %, ret/DD ≥ 1.10× la référence 8x non plafonnée,
      liqs ≤ 3.
CH2 — Stress funding : run_stack applique déjà le coût (fund = notional ×
      taux_horaire × hold_h) via le dict fh — les scénarios cadence ×8 et
      rate ×2 = des fh scalés, PAR FLUX. PASS si la perte ROI < 10 % du brut.
CH3 — Tilt par-symbole : T = funding_last(symbol) / médiane TRAIN du symbole,
      T > seuil → lev ÷ 2 sur les 3 flux alts (jamais conditionnés). Sweep
      seuil ∈ {1.5, 2.0}. PASS : DD alts −5 % sans perdre > 10 % de ROI.

Fenêtre : la couverture funding réelle (2025-10-27 →), split 70/30 →
2026-06-11. Le protocole run_stack n'est JAMAIS modifié.

  .venv/bin/python scripts/studies/w41_trois_chantiers.py
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
W = {"cascade_10x": 0.857, "cascade_meme": 0.857,
     "survivor_long": 2.0, "vol_spike_6h": 0.857}
LEV_MAJ = 11.0
KDB = ROOT / "data" / "warehouse" / "klines.db"
ALTS = ("cascade_meme", "vol_spike_6h")


def funding_series():
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


def funding_last_of(e, series):
    t, v = series.get(e["sym"], (None, None))
    if t is None or not len(t):
        return None
    k = int(np.searchsorted(t, e["ts_ms"] / 1e6, side="right")) - 1
    return float(v[k]) if k >= 0 else None


def ret_dd(res):
    months = monthly_rows(res["trades"], CAPITAL)
    roi_an = (res["balance"] / CAPITAL) ** (12 / max(len(months), 1)) - 1
    return (roi_an * 100) / max(res["max_dd"], 0.1)


def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[w41] events {dict(counts)} en {time.time()-t0:.0f}s", flush=True)
    series = funding_series()
    base = base_sizer(ctx)

    cov_start_ms = min(t[0] for s in ("BTCUSDT",) for t, _ in [series[s]])
    cov = [e for e in all_ev if e["ts_ms"] / 1e6 >= cov_start_ms]
    for e in cov:
        if e["strategy"] == "cascade_10x":
            e["lev"] = LEV_MAJ
    ts = np.array([e["ts_ms"] for e in cov])
    t_split = ts.min() + 0.7 * (ts.max() - ts.min())
    train_ev = [e for e in cov if e["ts_ms"] < t_split]
    val_ev = [e for e in cov if e["ts_ms"] >= t_split]
    print(f"[w41] fenêtre depuis "
          f"{datetime.fromtimestamp(cov_start_ms/1000, tz=timezone.utc):%Y-%m-%d} : "
          f"train {len(train_ev)} / val {len(val_ev)}", flush=True)

    w_sizer = weighted_sizer(base, W)
    L: list[str] = ["# W41 — LES TROIS CHANTIERS (pré-enregistrés, exécutés dans l'ordre)",
                    f"{DATE} — fenêtre 2025-10-27→, split 70/30, cellule codifiée "
                    "w=[0.857/0.857/2.0/0.857] lev majors 11. Le protocole "
                    "run_stack inchangé : le cap de marge = un wrapper du sizer, "
                    "les scénarios funding = des fh scalés.", ""]
    verdicts: dict[str, str] = {}

    # ============ CHANTIER 1 : le MM liq-tolérant ============
    print("[w41] — CH1 : le MM liq-tolérant —", flush=True)

    def cap_sizer(k):
        def fn(e, st=None):
            return min(w_sizer(e, st), k / 100.0)
        return fn

    # la référence : les mêmes poids à 8x sans cap (la cellule plus sûre)
    ev8_tr = [{**e, "lev": 8.0 if e["strategy"] == "cascade_10x" else e["lev"]}
              for e in train_ev]
    ev8_va = [{**e, "lev": 8.0 if e["strategy"] == "cascade_10x" else e["lev"]}
              for e in val_ev]
    ref8_tr = run_stack(ev8_tr, CAPITAL, w_sizer, fh)
    ref8_va = run_stack(ev8_va, CAPITAL, w_sizer, fh)
    ref_rr = ret_dd(ref8_va)
    print(f"[w41] CH1 réf 8x : T ${ref8_tr['balance']:,.0f} (liq "
          f"{ref8_tr['n_liq']}) | V ${ref8_va['balance']:,.0f} (DD "
          f"{ref8_va['max_dd']:.1f}, liq {ref8_va['n_liq']}) ret/DD {ref_rr:.2f}",
          flush=True)

    cands1 = []
    for k in (1.0, 2.0, 4.0):
        r = run_stack(train_ev, CAPITAL, cap_sizer(k), fh)
        mrows = monthly_rows(r["trades"], CAPITAL)
        rois = [x["roi"] for x in mrows] or [0.0]
        cands1.append({"k": k, "r": r,
                       "neg": int(sum(x < 0 for x in rois))})
        print(f"[w41] CH1 cap {k:g}% : T ${r['balance']:,.0f} (DD "
              f"{r['max_dd']:.1f}, liq {r['n_liq']})", flush=True)
    L += ["## CH1 — le MM liq-tolérant (la marge plafonnée k% du wallet)", "",
          f"Référence 8x sans cap : VAL ${ref8_va['balance']:,.0f} "
          f"(DD {ref8_va['max_dd']:.1f} %, liq {ref8_va['n_liq']}, "
          f"ret/DD {ref_rr:.2f}).", "",
          "| cap | Train $ | DD | liq |", "|---|---|---|---|"]
    for c in cands1:
        L.append(f"| {c['k']:g} % | ${c['r']['balance']:,.0f} "
                 f"| {c['r']['max_dd']:.1f} % | {c['r']['n_liq']} |")
    ok1 = [c for c in cands1 if c["r"]["n_liq"] <= 3
           and c["r"]["max_dd"] <= 25.0 and c["r"]["balance"] > CAPITAL]
    if ok1:
        ch1 = sorted(ok1, key=lambda c: -c["r"]["balance"])[0]
        v1r = run_stack(val_ev, CAPITAL, cap_sizer(ch1["k"]), fh)
        rr1 = ret_dd(v1r)
        v = ("PASS" if (v1r["max_dd"] <= 25.0 and rr1 >= 1.10 * ref_rr
                        and v1r["n_liq"] <= 3)
             else "FAIL (critères non atteints)")
        verdicts["CH1 MM liq-tolérant"] = v
        L += ["", f"Choisi : cap {ch1['k']:g} %. VAL → ${v1r['balance']:,.0f} "
              f"(DD {v1r['max_dd']:.1f} %, liq {v1r['n_liq']}, ret/DD "
              f"{rr1:.2f}) → **{v}** (critères : DD ≤ 25, ret/DD ≥ 1.10× la réf "
              f"8x, liq ≤ 3)."]
        print(f"[w41] CH1 VAL: cap {ch1['k']:g}% liq {v1r['n_liq']} DD "
              f"{v1r['max_dd']:.1f} ret/DD {rr1:.2f} → {v}", flush=True)
    else:
        verdicts["CH1 MM liq-tolérant"] = "FAIL (aucun cap viable TRAIN)"
        L += ["", "Aucun cap viable sur TRAIN — FAIL."]

    # ============ CHANTIER 2 : le stress funding (par flux) ============
    print("[w41] — CH2 : le stress funding —", flush=True)
    L += ["", "## CH2 — le stress funding (les scénarios plateforme)", "",
          "| flux | n pris | ROI brut | ROI cadence ×8 | ROI rate ×2 | "
          "perte ×8 / brut |", "|---|---|---|---|---|---|"]
    fh8 = {s: v * 8.0 for s, v in fh.items()}
    fh2 = {s: v * 2.0 for s, v in fh.items()}
    for f in ("cascade_10x", "cascade_meme", "survivor_long", "vol_spike_6h"):
        evs = [e for e in val_ev if e["strategy"] == f]
        if not evs:
            continue
        r0 = run_stack(evs, CAPITAL, w_sizer, fh)
        r8 = run_stack(evs, CAPITAL, w_sizer, fh8)
        r2 = run_stack(evs, CAPITAL, w_sizer, fh2)
        gross0 = r0["balance"] - CAPITAL + r0.get("fees_tot", 0) * 0 + 0
        perte8 = (r0["balance"] - r8["balance"]) / max(r0["balance"], 1)
        L.append(f"| {f} | {r0['n']} | ${r0['balance']:,.0f} "
                 f"| ${r8['balance']:,.0f} | ${r2['balance']:,.0f} "
                 f"| {perte8 * 100:.1f} % |")
        st = ("OK" if abs(perte8) < 0.10 else "FRAGILE (≥ 10 % du solde)")
        print(f"[w41] CH2 {f}: brut ${r0['balance']:,.0f} → ×8 "
              f"${r8['balance']:,.0f} ({perte8 * 100:+.1f} %) → {st}",
              flush=True)
    verdicts["CH2 stress funding"] = "CARACTÉRISATION (les seuils au rapport)"

    # ============ CHANTIER 3 : le tilt par-symbole sur les alts ============
    print("[w41] — CH3 : le tilt par-symbole —", flush=True)
    med_sym = {}
    for e in train_ev:
        if e["strategy"] in ALTS:
            fl = funding_last_of(e, series)
            if fl is not None:
                med_sym.setdefault(e["sym"], []).append(fl)
    med_sym = {s: float(np.median(v)) for s, v in med_sym.items()
               if len(v) >= 10 and np.median(v) != 0}
    print(f"[w41] CH3: {len(med_sym)} symboles avec une médiane TRAIN", flush=True)

    def tilt_sizer(seuil):
        def fn(e, st=None):
            sz = w_sizer(e, st)
            if e["strategy"] in ALTS and e["sym"] in med_sym:
                fl = funding_last_of(e, series)
                if fl is not None and fl / med_sym[e["sym"]] > seuil:
                    return sz * 0.5
            return sz
        return fn

    best3 = None
    for seuil in (1.5, 2.0):
        r = run_stack(train_ev, CAPITAL, tilt_sizer(seuil), fh)
        print(f"[w41] CH3 seuil {seuil}: T ${r['balance']:,.0f} (DD "
              f"{r['max_dd']:.1f}, liq {r['n_liq']})", flush=True)
        if best3 is None or r["max_dd"] < best3[1]["max_dd"]:
            best3 = (seuil, r)
    seuil3 = best3[0]
    v3 = run_stack(val_ev, CAPITAL, tilt_sizer(seuil3), fh)
    b_va = run_stack(val_ev, CAPITAL, w_sizer, fh)
    dd_alt_b = b_va["max_dd"]
    dd_alt_v = v3["max_dd"]
    roi_keep = (v3["balance"] / b_va["balance"]) if b_va["balance"] > 0 else 0
    v = ("PASS" if (dd_alt_v <= dd_alt_b - 5.0 * 0.01 * dd_alt_b * 100 / 100
                    and roi_keep >= 0.90) else "FAIL")
    verdicts["CH3 tilt par-symbole"] = v
    L += ["", "## CH3 — le tilt par-symbole sur les alts", "",
          f"Seuil choisi (TRAIN, DD min) : T > {seuil3}. VAL : DD "
          f"{dd_alt_v:.1f} % vs {dd_alt_b:.1f} % sans tilt, ROI conservé "
          f"{roi_keep:.2f}× → **{v}** (critères : DD −5 % relatif, ROI ≥ 0.90×)."]

    # ——— le bloc stats du meilleur CH1 ———
    if ok1:
        lines, _ = bloc(v1r, f"CH1 cap {ch1['k']:g} % — VAL", CAPITAL)
        L += [""] + lines

    L += ["", "## VERDICTS", ""]
    for k2, v2 in verdicts.items():
        L.append(f"- **{k2} : {v2}**")
    L += [""]

    out = ROOT / "reports" / f"w41-trois-chantiers-{DATE}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[w41] rapport -> {out}", flush=True)
    print(f"[w41] VERDICTS: {verdicts}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
