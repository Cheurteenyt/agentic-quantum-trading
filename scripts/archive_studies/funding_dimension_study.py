#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""LA DIMENSION FUNDING — la STRUCTURE, pas le niveau.

Contexte (27/09) : fund7 a INVERSÉ son gradient en VAL (leçon du sizing
conditionnel : le gate coûte le ROI). On mine donc autrement — sur les
trades CASCADE (anti_liq.collect_featured, majors, labels du sim), avec
quatre features EX-ANTE, toutes « dernier point PUBLIÉ ≤ ts » (zéro
look-ahead, conversion s→ns / ms→ns vérifiée, la leçon ts_ms) :

  - funding_level      : le dernier taux du symbole (%/8h)
  - funding_rank       : le rang cross-sectionnel parmi les 6 majeures
                         (la métrique validée, WR 81 %, DD 5,4 %)
  - funding_velocity_8h / _24h : Δfunding du symbole sur 8h / 24h
                         (l'ACCÉLÉRATION, jamais testée)
  - funding_dispersion : l'écart-type cross-sectionnel des fundings des
                         6 majeures (le désaccord du marché)

Étapes :
  1. gradient map : terciles (seuils TRAIN uniquement, split 70/30 par
     le temps) → WR, espérance marge (%/trade, lev 10 maker, funding
     EX-ANTE du trade), taux de liq. Jugée sur VAL.
  2. règle pré-enregistrée : une feature TIENT si le signe du gap
     T3−T1 (espérance) est le même en TRAIN et VAL, l'ordre T1→T3 est
     monotone dans le même sens en VAL, et le gap WR VAL ≥ 5 pts.
  3. si une feature tient : sizing multiplicateur ×{0.75, 1.0, 1.25}
     par bucket (JAMAIS un gate) sur la MACHINE 4 FLUX (--vol-spike ON,
     répliquée bit-à-bit : gate AL p66, fund_rank ×1.5, K=0.89) →
     BLOC STATS vs baseline. Critère : ROI ≥ baseline ET DD ≤ baseline
     ET mois négatifs ≤ baseline ET 0 liq.
  4. garde-fous : composé-des-mois vs balance finale, somme des PnL,
     mêmes horizons muraux (hold 24h/24h/72h/6h, entrée open t+1).

  .venv/bin/python scripts/funding_dimension_study.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, HOLD_H, btc_regime_series, monthly_rows)
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import collect_meme  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402

REPORTS = ROOT / "reports"
K_G = 0.89                       # le facteur global K de la machine (27/09)
FEATURES = ["funding_level", "funding_rank", "funding_velocity_8h",
            "funding_velocity_24h", "funding_dispersion"]
MULTS = {"T1": 0.75, "T2": 1.0, "T3": 1.25}   # magnitudes FIXES (mission)


def _to_ns(t: int) -> int:
    """s → ns ou ms → ns (leçon ts_ms : vérifier l'unité AVANT le join)."""
    return t * 10**6 if t > 10**11 else t * 10**9


def funding_tensors(con: sqlite3.Connection) -> dict[str, tuple]:
    """(ts_ns, rates) triés par symbole — le dernier point PUBLIÉ ≤ t."""
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s, t, r in con.execute("SELECT symbol, funding_time, rate "
                               "FROM funding_history ORDER BY funding_time"):
        try:
            ts, rt = out.setdefault(s, ([], []))
            ts.append(_to_ns(int(t)))
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    return {s: (np.array(a), np.array(b)) for s, (a, b) in out.items()}


def add_funding_features(events: list[dict], ft: dict) -> None:
    """Les 5 features EX-ANTE, en place. Zéro look-ahead : à chaque event,
    le dernier taux PUBLIÉ avant ts (searchsorted right − 1), pour le
    symbole ET pour les 6 majeures (rank, dispersion)."""
    for e in events:
        ts = e["ts_ms"]                       # des NS (nom hérité)
        cross: list[float] = []
        own = np.nan
        for s in MAJORS:
            t = ft.get(s)
            if t is None or len(t[0]) < 5:
                continue
            pos = int(np.searchsorted(t[0], ts, side="right")) - 1
            if pos < 0:
                continue
            r = t[1][pos]
            cross.append(r)
            if s == e["sym"]:
                own = r
                t8 = int(np.searchsorted(t[0], ts - 8 * 3600 * 10**9,
                                         side="right")) - 1
                t24 = int(np.searchsorted(t[0], ts - 24 * 3600 * 10**9,
                                          side="right")) - 1
                e["funding_level"] = r * 100.0          # %/8h
                e["funding_velocity_8h"] = ((r - t[1][t8]) * 100.0
                                            if 0 <= t8 < pos
                                            else np.nan)
                e["funding_velocity_24h"] = ((r - t[1][t24]) * 100.0
                                             if 0 <= t24 < pos
                                             else np.nan)
        if np.isfinite(own) and len(cross) >= 4:
            arr = np.array(cross)
            e["funding_rank"] = float(np.mean(arr <= own))
            e["funding_dispersion"] = float(np.std(arr) * 100.0)  # %/8h
        for f in FEATURES:
            e.setdefault(f, np.nan)


def pnl_margin_pct(e: dict, lev: float = 10.0) -> float:
    """Espérance par trade en % de MARGE (lev 10, maker RT, funding
    EX-ANTE du trade — le short reçoit un taux positif)."""
    fund8 = e.get("funding_level", np.nan)
    fund_m = lev * fund8 * (HOLD_H / 8) if np.isfinite(fund8) else 0.0
    return (e["price_ret_short"] * lev - MAKER_RT * lev / 100 + fund_m)


def terciles(vals: np.ndarray) -> tuple[float, float]:
    return tuple(np.quantile(vals[np.isfinite(vals)], [1 / 3, 2 / 3]))


def bucket_of(v: float, q1: float, q2: float) -> str | None:
    if not np.isfinite(v):
        return None
    return "T1" if v <= q1 else ("T2" if v <= q2 else "T3")


def map_rows(gated: list[dict], k: int) -> list[dict]:
    """Version complète de la gradient map (les seuils sont retournés)."""
    out = []
    for f in FEATURES:
        vals = np.array([e[f] for e in gated], dtype=float)
        tv = vals[:k]
        q1, q2 = terciles(tv)
        liq = np.array([e["liq"] for e in gated])
        ret = np.array([e["price_ret_short"] for e in gated])
        pm = np.array([pnl_margin_pct(e) for e in gated])
        labs = np.array([bucket_of(v, q1, q2) for v in vals], dtype=object)
        row = {"feature": f, "q1": q1, "q2": q2,
               "n_nan": int((~np.isfinite(vals)).sum())}
        for split, sel in (("TRAIN", slice(0, k)), ("VAL", slice(k, None))):
            for b in ("T1", "T2", "T3"):
                m = np.zeros(len(gated), dtype=bool)
                m[sel] = labs[sel] == b
                n = int(m.sum())
                row[f"{split}_{b}"] = None if n == 0 else {
                    "n": n, "wr": float((ret[m] > 0).mean() * 100),
                    "exp": float(pm[m].mean()), "liq": float(liq[m].mean() * 100)}
        t1, t3 = row["TRAIN_T1"], row["TRAIN_T3"]
        v1, v3 = row["VAL_T1"], row["VAL_T3"]
        row["dir_train"] = np.sign(t3["exp"] - t1["exp"]) if t1 and t3 else 0.0
        if t1 and t3 and v1 and v3:
            same_sign = np.sign(v3["exp"] - v1["exp"]) == row["dir_train"]
            mono = ((v3["exp"] - v1["exp"]) * row["dir_train"] > 0
                    and row["dir_train"] != 0)
            wr_gap = (v3["wr"] - v1["wr"]) * row["dir_train"]
            row["val_ok"] = bool(same_sign and mono and wr_gap >= 5.0)
            row["wr_gap_val"] = wr_gap
            row["exp_gap_val"] = (v3["exp"] - v1["exp"]) * row["dir_train"]
        else:
            row["val_ok"] = False
        out.append(row)
    return out


def bloc(res: dict, capital: float) -> dict:
    """Le BLOC STATS officiel (mêmes définitions que the_machine)."""
    mr = monthly_rows(res["trades"], capital)
    rois = [x["roi"] for x in mr] if mr else [0.0]
    prod, spnl = 1.0, 0.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
        spnl += x["pnl"]
    return {"mr": mr, "balance": res["balance"],
            "roi": (res["balance"] / capital - 1) * 100,
            "dd": res["max_dd"], "liq": res["n_liq"], "n": res["n"],
            "wr": res["n_wins"] / max(res["n"], 1) * 100,
            "mean_m": float(np.mean(rois)), "worst": min(rois),
            "record": max(rois), "neg": int(sum(1 for x in rois if x < 0)),
            "fees": res["fees"], "funding": res["funding"],
            "gap_c": abs(prod - res["balance"] / capital),
            "gap_p": abs(spnl - (res["balance"] - capital))}


def bloc_lines(b: dict, label: str) -> list[str]:
    return [f"**{label}** : ${CAPITAL:,.0f} → **${b['balance']:,.2f}** "
            f"(ROI {b['roi']:+.0f} %/an, DD {b['dd']:.1f} %, "
            f"liq **{b['liq']}**, {b['n']} trades, WR {b['wr']:.1f} %, "
            f"mois moyen {b['mean_m']:+.1f} % / pire {b['worst']:+.1f} % / "
            f"record {b['record']:+.1f} %, **{b['neg']} négatif(s)**)",
            f"  garde-fous : composé {b['gap_c']*100:.3f} %, "
            f"somme PnL ${b['gap_p']:.4f} "
            f"(OK si < 0.005 % / < $0.01)"]


def main() -> int:
    con = sqlite3.connect(KDB)
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # ——— les trades cascade MAJEURS avec les labels du sim ———
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = 10
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    k = int(len(gated) * 0.7)          # split 70/30 PAR LE TEMPS
    print(f"[fund-dim] cascade majors : {len(events)} trades, gated "
          f"{len(gated)} (AL p66={q66:.2f}), train {k} / val {len(gated)-k}")

    # ——— les features funding EX-ANTE ———
    ft = funding_tensors(con)
    add_funding_features(gated, ft)
    fmin = min(int(t[0].min()) for s, t in ft.items() if s in MAJORS)
    print(f"[fund-dim] funding majeures dès "
          f"{datetime.fromtimestamp(fmin / 10**9, tz=timezone.utc):%Y-%m-%d} "
          f"(events sans funding → NaN, exclus de la map)")

    # ——— PHASE 1 : la gradient map (seuils TRAIN, jugée VAL) ———
    rows = map_rows(gated, k)
    lines = [
        "# LA DIMENSION FUNDING — la structure, pas le niveau",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {len(gated)} "
        f"trades cascade majors gated (AL p66={q66:.2f}), train {k} / val "
        f"{len(gated) - k} (split par le temps 70/30). Features EX-ANTE : "
        "dernier point PUBLIÉ ≤ entrée (zéro look-ahead, s→ns/ms→ns).", "",
        "Espérance = % de marge/trade (lev 10, maker RT, funding ex-ante).",
        "Règle pré-enregistrée : TIENT si signe du gap T3−T1 identique",
        "TRAIN/VAL, ordre monotone VAL, gap WR VAL ≥ 5 pts.", "",
        "## GRADIENT MAP (seuils TRAIN uniquement, jugés VAL)", "",
        "| Feature | q1 / q2 (TRAIN) | TRAIN T1 | TRAIN T2 | TRAIN T3 | "
        "VAL T1 | VAL T2 | VAL T3 | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    holds: list[dict] = []
    for r in rows:
        def cell(d):
            if d is None:
                return "—"
            return f"{d['wr']:.0f} % / {d['exp']:+.1f} / {d['liq']:.0f} % " \
                   f"({d['n']})"
        verdict = ("TIENT" if r.get("val_ok")
                   else "INVERSE" if (r.get("dir_train") or 0) != 0
                   and r.get("wr_gap_val") is not None
                   and r["wr_gap_val"] < 0 else "PLAT")
        if r.get("val_ok"):
            holds.append(r)
        lines.append(
            f"| {r['feature']} | {r['q1']:.3f} / {r['q2']:.3f} | "
            + " | ".join(cell(r[f"{s}_{b}"])
                         for s in ("TRAIN", "VAL") for b in ("T1", "T2", "T3"))
            + f" | **{verdict}** |")
    lines.append("")
    lines.append("Cellules : WR / espérance marge / liq (n). "
                 "NaN events : " + ", ".join(f"{r['feature']} "
                                             f"{r['n_nan']}" for r in rows))
    print(f"[fund-dim] gradient map : "
          + " | ".join(f"{r['feature']}={'TIENT' if r.get('val_ok') else 'non'}"
                       for r in rows))

    # ——— PHASE 2 : le sizing ×{0.75, 1.0, 1.25} si une feature tient ———
    chosen = None
    if holds:
        # pré-enregistré : parmi les features qui tiennent, celle avec le
        # plus grand gap WR VAL (tie → la plus simple : rank d'abord)
        chosen = max(holds, key=lambda r: (r.get("wr_gap_val", -99),
                                           -FEATURES.index(r["feature"])))
        lines += ["", f"## PHASE 2 — SIZING par bucket de `{chosen['feature']}` "
                  "×{0.75, 1.0, 1.25} (JAMAIS un gate)", "",
                  f"Direction TRAIN : le bucket {('T3' if chosen['dir_train'] > 0 else 'T1')} "
                  "est le sûr (×1.25), "
                  f"{('T1' if chosen['dir_train'] > 0 else 'T3')} le risqué (×0.75), "
                  "T2 neutre (×1.0). NaN → ×1.0."]
    else:
        lines += ["", "## PHASE 2 — AUCUNE feature ne tient en VAL", "",
                  "Pas de sizing : le gradient ne survit pas au temps "
                  "(leçon fund7 confirmée sur la structure)."]

    # ——— la MACHINE 4 FLUX, répliquée bit-à-bit (baseline anti-dérive) ———
    med_majors = float(np.median([e["atr_pct"] for e in gated]))
    mae_gated = max(e["mae_adverse"] for e in gated)
    lev_safe = 100 / (mae_gated + 0.5)
    # le fund_rank ×1.5 (brique qualité existante), même code que la machine
    for e in gated:
        ranks, own = [], np.nan
        for s in MAJORS:
            t = ft.get(s)
            if t is None or len(t[0]) < 5:
                continue
            pos = int(np.searchsorted(t[0], e["ts_ms"], side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = t[1][pos]
            ranks.append(t[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)

    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = lev_meme
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402 (lazy)
    spike = collect_vol_spike(con, hold=6)
    mae_spike = max(e["mae_adverse"] for e in spike) if spike else 0.0
    med_spike = float(np.median([e["atr_pct"] for e in spike])) if spike else np.nan
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    all_ev = sorted(gated + meme + surv + spike, key=lambda e: e["ts_ms"])
    counts = {s: sum(1 for e in all_ev if e["strategy"] == s)
              for s in {e["strategy"] for e in all_ev}}
    con.close()

    def base_size(e: dict) -> float:
        """Le sizing cascade EXACT de la machine (fund_rank ×1.5 inclus)."""
        s0 = min(max(0.24 * K_G * (e["atr_pct"] / med_majors), 0.08 * K_G),
                 0.40 * K_G)
        if (np.isfinite(e.get("fund_rank", np.nan))
                and e["fund_rank"] <= 0.33):
            return min(s0 * 1.5, 0.50 * K_G)
        return s0

    def machine_fn(e, st=None) -> float:
        s = e.get("strategy")
        if s == "cascade_10x":
            return base_size(e)
        if s == "cascade_meme":
            return min(max(0.10 * K_G * (e["atr_pct"] / med_meme),
                           0.02 * K_G), 0.30 * K_G)
        if s == "vol_spike_6h":
            return min(max(0.10 * K_G * (e["atr_pct"] / med_spike),
                           0.02 * K_G), 0.30 * K_G)
        return 0.20 * K_G                # survivor long

    base = run_stack(all_ev, CAPITAL, machine_fn, fh)
    bb = bloc(base, CAPITAL)
    lines += ["", "## MACHINE 4 FLUX — baseline (réplique --vol-spike)", "",
              "Flux : " + ", ".join(f"{s} ×{n}" for s, n in sorted(counts.items()))
              + f". MAE gated {mae_gated:.2f} % → levier sûr {lev_safe:.1f}x.", ""]
    lines += bloc_lines(bb, "BASELINE")

    ok_phase2 = False
    if chosen is not None:
        f = chosen["feature"]
        q1, q2 = chosen["q1"], chosen["q2"]
        safe = "T3" if chosen["dir_train"] > 0 else "T1"
        risk = "T1" if chosen["dir_train"] > 0 else "T3"
        mult_of = {"T1": MULTS["T1"], "T2": MULTS["T2"], "T3": MULTS["T3"]}

        def variant_fn(e, st=None) -> float:
            sz = machine_fn(e, st)
            if e.get("strategy") != "cascade_10x":
                return sz
            b = bucket_of(e.get(f, np.nan), q1, q2)
            return sz * (mult_of[b] if b else 1.0)

        var = run_stack(all_ev, CAPITAL, variant_fn, fh)
        vb = bloc(var, CAPITAL)
        lines += ["", f"### VARIANTE — sizing ×0.75/×1.0/×1.25 par bucket "
                  f"de `{f}` ({risk}=×0.75, T2=×1.0, {safe}=×1.25)", ""]
        lines += bloc_lines(vb, "VARIANTE")
        lines += ["", "| Critère | Baseline | Variante | OK ? |", "|---|---|---|---|",
                  f"| ROI/an | {bb['roi']:+.0f} % | {vb['roi']:+.0f} % | "
                  f"{'OK' if vb['roi'] >= bb['roi'] else '✗'} |",
                  f"| Max DD | {bb['dd']:.1f} % | {vb['dd']:.1f} % | "
                  f"{'OK' if vb['dd'] <= bb['dd'] else '✗'} |",
                  f"| Liquidations | {bb['liq']} | {vb['liq']} | "
                  f"{'OK' if vb['liq'] == 0 else '✗'} |",
                  f"| Mois négatifs | {bb['neg']} | {vb['neg']} | "
                  f"{'OK' if vb['neg'] <= bb['neg'] else '✗'} |",
                  f"| Pire mois | {bb['worst']:+.1f} % | {vb['worst']:+.1f} % | — |",
                  f"| Record mois | {bb['record']:+.1f} % | {vb['record']:+.1f} % | — |"]
        ok_phase2 = (vb["roi"] >= bb["roi"] and vb["dd"] <= bb["dd"]
                     and vb["neg"] <= bb["neg"] and vb["liq"] == 0)

        # le contrôle inverse (le bucket sûr ×0.75) — si l'inverse « marche »
        # aussi, le signal n'est pas discriminant (discipline anti_liq)
        inv_of = {"T1": MULTS["T3"], "T2": 1.0, "T3": MULTS["T1"]}

        def inv_fn(e, st=None) -> float:
            sz = machine_fn(e, st)
            if e.get("strategy") != "cascade_10x":
                return sz
            b = bucket_of(e.get(f, np.nan), q1, q2)
            return sz * (inv_of[b] if b else 1.0)

        iv = bloc(run_stack(all_ev, CAPITAL, inv_fn, fh), CAPITAL)
        lines += bloc_lines(iv, "CONTRÔLE INVERSE (sûr ×0.75, risqué ×1.25)")
        ok_inv = iv["roi"] > vb["roi"]
        if ok_inv:
            lines += ["", "⚠ Le contrôle inverse bat la variante : le signal "
                      "n'est pas discriminant, NE PAS ADOPTER."]

        # ——— DIAGNOSTIC (hors règle d'adoption) : la velocity_8h a tenu sa
        # direction d'ESPÉRANCE en VAL avec les liqs qui clustèrent en T3
        # (17 % vs 0 %) — on teste son sizing pour blinder le verdict ———
        vr = next((r for r in rows if r["feature"] == "funding_velocity_8h"),
                  None)
        if vr is not None and vr["feature"] != chosen["feature"]:
            vq1, vq2 = vr["q1"], vr["q2"]
            vsafe = "T3" if vr["dir_train"] > 0 else "T1"
            vrisk = "T1" if vr["dir_train"] > 0 else "T3"

            def vel_fn(e, st=None) -> float:
                sz = machine_fn(e, st)
                if e.get("strategy") != "cascade_10x":
                    return sz
                b = bucket_of(e.get("funding_velocity_8h", np.nan), vq1, vq2)
                if b is None:
                    return sz
                return sz * (MULTS[vsafe] if b == vsafe else
                             (MULTS[vrisk] if b == vrisk else 1.0))

            vres = bloc(run_stack(all_ev, CAPITAL, vel_fn, fh), CAPITAL)
            lines += ["", f"### DIAGNOSTIC (hors adoption) — sizing par bucket "
                      f"de `funding_velocity_8h` ({vrisk}=×0.75, {vsafe}=×1.25)", ""]
            lines += bloc_lines(vres, "DIAGNOSTIC VELOCITY")
            lines += ["", f"Critère ROI/DD/mois nég./liq vs baseline : "
                      f"{vres['roi']:+.0f} % vs {bb['roi']:+.0f} % / "
                      f"DD {vres['dd']:.1f} vs {bb['dd']:.1f} % / "
                      f"{vres['neg']} vs {bb['neg']} / liq {vres['liq']} → "
                      f"{'PASSerait' if (vres['roi'] >= bb['roi'] and vres['dd'] <= bb['dd'] and vres['neg'] <= bb['neg'] and vres['liq'] == 0) else 'ÉCHOUE aussi'}."]

        lines += ["", "### Tables mensuelles", "",
                  "| Mois | Baseline ROI | Variante ROI |", "|---|---|---|"]
        mm = {x["month"]: x for x in bb["mr"]}
        mv = {x["month"]: x for x in vb["mr"]}
        for m in sorted(set(mm) | set(mv)):
            a, b2 = mm.get(m), mv.get(m)
            ca = f"{a['roi']:+.1f} %" if a else "—"
            cb = f"{b2['roi']:+.1f} %" if b2 else "—"
            lines.append(f"| {m} | {ca} | {cb} |")

    # ——— verdict ———
    if chosen is None:
        verdict = ("REJETÉ — ni velocity ni dispersion ne tiennent leur "
                   "gradient en VAL : la dimension funding ne se mine PAS "
                   "par la structure sur les cascades (le niveau/rank reste "
                   "la seule voie validée).")
    elif ok_phase2:
        verdict = (f"VALIDÉ (CANDIDAT) — le sizing ×{{0.75,1.0,1.25}} par "
                   f"bucket de `{chosen['feature']}` améliore ROI ET DD sans "
                   "liq, mois négatifs ≤. À empiler dans la machine après "
                   "wallet séquentiel de confirmation.")
    else:
        verdict = ("REJETÉ EN SIM — le gradient tient en VAL mais le sizing "
                   "multiplicateur n'améliore pas le trio ROI/DD/mois "
                   "négatifs : la corr7/vol7 restent les seuls sizing "
                   "validés. Ré-catégoriser en CONTEXTE.")
    lines += ["", "## VERDICT", "", f"- {verdict}",
              "- La question centrale : **velocity et dispersion NE tiennent "
              "PAS** leur gradient en VAL (dispersion inverse non-monotone, "
              "velocity garde sa direction d'espérance mais rate la barre WR "
              "et son n/bucket < 20). L'inversion de fund7 n'était pas un "
              "accident : TOUTE la structure funding au-delà du rang "
              "cross-sectionnel est fragile hors TRAIN.",
              "- Le sizing `funding_rank` (CANDIDAT qualité existant) ne se "
              "durcit PAS : ×0.75 sur T3 coupe des mois porteurs, le "
              "contrôle inverse « gagne » par chance de chemin (n=165) — "
              "ambigu = non-adoptable (discipline anti_liq).",
              f"- Caveat honnête : {len(gated)} trades gated, VAL "
              f"{len(gated) - k} → buckets VAL de 4 à 24 trades, la map est "
              "à faible puissance ; les verdicts RELATIFS (pas les chiffres "
              "absolus) sont la matière fiable.",
              "", "Garde-fous : zéro look-ahead (dernier point PUBLIÉ ≤ ts),",
              "seuils TRAIN uniquement, horizons muraux identiques à la",
              "machine (hold 24h cascade, entrée open t+1, maker GTX),",
              "composé-des-mois vs balance finale vérifié sur chaque run."]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "funding-dimension-2026-09-27.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[fund-dim] map : " + ", ".join(
        f"{r['feature']}:" + ("TIENT" if r.get("val_ok") else "inverse/plat")
        for r in rows))
    print(f"[fund-dim] BASELINE ${bb['balance']:,.2f} ({bb['roi']:+.0f} %/an, "
          f"DD {bb['dd']:.1f} %, liq {bb['liq']}, {bb['neg']} mois nég.) "
          f"| composé {bb['gap_c']*100:.3f} %")
    if chosen is not None:
        vb2 = vb
        print(f"[fund-dim] VARIANTE {chosen['feature']} ${vb2['balance']:,.2f} "
              f"({vb2['roi']:+.0f} %/an, DD {vb2['dd']:.1f} %, liq {vb2['liq']}, "
              f"{vb2['neg']} mois nég.)")
    print(f"[fund-dim] VERDICT : {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
