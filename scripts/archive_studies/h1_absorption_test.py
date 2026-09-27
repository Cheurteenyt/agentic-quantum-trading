#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""H1 — L'ABSORPTION À L'ENTRÉE CASCADE (pré-enregistrée reports/flow-audit-2026-09-27.md).

Hypothèse figée AVANT la data : buy_ratio = taker_buy_volume / volume, moyenne
des 4 bougies 1h précédant le signal (barre signal + 3 avant, STRICTEMENT
ex-ante : l'entrée est à l'open de la barre suivante). Des gros acheteurs qui
encaissent la chute (absorption) = le rebond menace le short cascade → MAE/liq
CROISSANT avec buy_ratio.

Discipline harnais v5 :
  - corpus = anti_liq.collect_featured + add_rolling_scores (le même que les
    études précédentes : events majors, hold 24h, sélection sim)
  - split train/val PAR LE TEMPS 70/30 ; coupures de quartiles choisies sur
    TRAIN uniquement, appliquées telles quelles en VAL
  - PASS = gradient MONOTONE (MAE moyen croissant Q1→Q4) tenu en VAL
  - si PASS : sizing multiplicateur ×{0.75, 1.0, 1.25} par quartile (JAMAIS un
    gate) sur la machine 4 flux (--vol-spike ON), BLOC STATS vs baseline.
    Critère : ROI ≥ baseline ET DD ≤ baseline ET mois négatifs ≤ baseline.
    Garde-fou : composé-des-mois ~0 (verdict RELATIF).

  .venv/bin/python scripts/h1_absorption_test.py
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

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.portfolio_sim import btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, funding_hourly_all, monthly_rows, run_stack)
LEV_M = 10            # le levier du flux cascade_10x (la machine)
LIQ_MOVE_10X = 100 / LEV_M - 0.5   # 9.5 % — la ligne de mort du flux 10x
FEE_PCT_MARGE = LEV_M * (2 + 0) * 2 / 1e4 * 100   # 0.4 % de marge, maker AR
K = 0.89              # le facteur global de la machine


# ----------------------------------------------------------------- PARTIE A
def attach_buy_ratio(events: list[dict]) -> list[str]:
    """Annote e['buy_ratio'] = moyenne taker_buy/vol des 4 bougies 1h AVANT
    l'entrée (open_time entrée − 4h .. −1h = barre signal + 3 précédentes).
    Les events sans CVD → buy_ratio NaN. Retourne les symboles sans CVD."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    cvd: dict[str, dict[int, tuple[float, float]]] = {}
    for s, ot, tb, v in con.execute(
            "SELECT symbol, open_time, taker_buy_volume, volume FROM klines "
            "WHERE interval='1h' AND taker_buy_volume IS NOT NULL"):
        cvd.setdefault(s, {})[int(ot)] = (float(tb or 0.0), float(v or 0.0))
    con.close()
    for e in events:
        sym = e["sym"]
        if sym not in cvd:
            e["buy_ratio"] = float("nan")
            continue
        entry_open_ms = e["ts_ms"] / 10**6          # ts_ms = des NS (leçon)
        ratios = []
        for k in (1, 2, 3, 4):                       # signal bar + 3 avant
            ot = int(entry_open_ms) - k * 3600_000
            bar = cvd[sym].get(ot)
            if bar is None or bar[1] <= 0:
                ratios = []
                break
            ratios.append(bar[0] / bar[1])
        e["buy_ratio"] = float(np.mean(ratios)) if ratios else float("nan")
    return sorted(set(events_all_syms(events)) - set(cvd))


def events_all_syms(events: list[dict]) -> set:
    return {e["sym"] for e in events}


def gradient_map(split: list[dict], cuts: list[float], fh: dict) -> list[str]:
    lines = ["| Quartile | n | MAE moyen % | Liq @9.5 % | WR % | Espérance marge % |",
             "|---|---|---|---|---|---|"]
    edges = [-np.inf] + cuts + [np.inf]
    for qi in range(4):
        m = [e for e in split if edges[qi] < e["buy_ratio"] <= edges[qi + 1]]
        if not m:
            lines.append(f"| Q{qi + 1} ({edges[qi]:.3f}–{edges[qi + 1]:.3f} br) "
                         f"| 0 | — | — | — | — |")
            continue
        mae = np.array([e["mae_adverse"] for e in m])
        liq = np.mean([e["mae_adverse"] >= LIQ_MOVE_10X for e in m]) * 100
        wr = np.mean([e["price_ret_short"] > 0 for e in m]) * 100
        exp = np.mean([e["price_ret_short"] * LEV_M
                       + 240 * fh.get(e["sym"], 0.0) - FEE_PCT_MARGE for e in m])
        lines.append(f"| Q{qi + 1} ({edges[qi]:.3f}–{edges[qi + 1]:.3f} br) "
                     f"| {len(m)} | {mae.mean():.2f} | {liq:.1f} % | {wr:.1f} % "
                     f"| {exp:+.1f} |")
    return lines


def monotone(vals: list[float]) -> bool:
    return all(np.isfinite(v) for v in vals) and \
        all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)) \
        and vals[0] < vals[-1]


def spearman(xs, ys) -> float:
    try:
        from scipy.stats import spearmanr
        return float(spearmanr(xs, ys).statistic)
    except Exception:
        xr = pd.Series(xs).rank().values
        yr = pd.Series(ys).rank().values
        return float(np.corrcoef(xr, yr)[0, 1])


# ----------------------------------------------------------------- PARTIE B
def build_machine(mult_fn, cuts: list[float]):
    """La réplique EXACTE de the_machine.main (4 flux, --vol-spike ON) avec un
    multiplicateur de sizing branché sur le flux cascade_10x."""
    from scripts.full_arsenal_2 import collect as collect_arsenal
    from scripts.p5_frequency_test import collect_vol_spike
    from scripts.the_machine import collect_meme

    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # flux 1 : cascade majors 10x, gate AL p66 (TRAIN 70 %), vol-inverse
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = LEV_M
        e["hold_h"] = 24
        e["fee_rt_bps"] = (2 + 0) * 2
    attach_buy_ratio(events)
    add_rolling_scores(events)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan")) for e in events[:int(len(events) * 0.7)]],
        2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    med_majors = float(np.median([e["atr_pct"] for e in gated]))
    mae_gated = max(e["mae_adverse"] for e in gated)
    lev_safe = 100 / (mae_gated + 0.5)

    # fund_rank (le poids qualité de la machine)
    funding_ts: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = funding_ts.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
    for e in gated:
        ranks, own = [], np.nan
        for s in MAJORS:
            ft = funding_ts.get(s)
            if not ft or len(ft[0]) < 5:
                continue
            pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"],
                                      side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = ft[1][pos]
            ranks.append(ft[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)

    # flux 2 : cascade memecoins
    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = lev_meme

    # flux 3 : survivor long 72h, filtre ATR p90
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    _p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= _p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = (4 + 10) * 2

    # flux 4 : vol-spike reversion 6h (--vol-spike ON)
    spike = collect_vol_spike(con, hold=6)
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = (4 + 10) * 2
    med_spike = float(np.median([e["atr_pct"] for e in spike])) if spike else np.nan
    con.close()

    all_ev = sorted(gated + meme + surv + spike, key=lambda e: e["ts_ms"])

    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * K * (e["atr_pct"] / med_majors), 0.08 * K), 0.40 * K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                s0 = min(s0 * 1.5, 0.50 * K)
            return min(s0 * mult_fn(e, cuts), 0.50 * K)  # ← le SEUL écart
        if s == "cascade_meme":
            return min(max(0.10 * K * (e["atr_pct"] / med_meme), 0.02 * K), 0.30 * K)
        if s == "vol_spike_6h":
            return min(max(0.10 * K * (e["atr_pct"] / med_spike), 0.02 * K), 0.30 * K)
        return 0.20 * K

    stats = {"q66": q66, "mae_gated": mae_gated, "lev_safe": lev_safe,
             "lev_meme": lev_meme, "mae_meme": mae_meme,
             "n_gated": len(gated), "n_meme": len(meme), "n_surv": len(surv),
             "n_spike": len(spike)}
    return all_ev, machine_fn, fh, stats


def bloc(res: dict, label: str) -> list[str]:
    mr = monthly_rows(res["trades"], CAPITAL)
    wr = res["n_wins"] / max(res["n"], 1) * 100
    roi = (res["balance"] / CAPITAL - 1) * 100
    prod, sum_pnl, rois_m = 1.0, 0.0, []
    for x in mr:
        prod *= 1 + x["roi"] / 100
        sum_pnl += x["pnl"]
        rois_m.append(x["roi"])
    gap_c = abs(prod - res["balance"] / CAPITAL)
    gap_p = abs(sum_pnl - (res["balance"] - CAPITAL))
    neg = sum(1 for r in rois_m if r < 0)
    lines = [
        f"### {label}", "",
        f"- Wallet : ${CAPITAL:,.0f} → **${res['balance']:,.2f}** ({roi:+.0f} %/an)",
        f"- Max DD {res['max_dd']:.1f} % | **liq {res['n_liq']}** | "
        f"{res['n']} trades / WR {wr:.1f} %",
        f"- Mois : moyen {np.mean(rois_m):+.1f} % / pire {min(rois_m):+.1f} % / "
        f"record {max(rois_m):+.1f} % ({neg} négatifs)",
        f"- Frais+slip ${res['fees']:,.2f} | funding ${res['funding']:+,.2f}",
        f"- Garde-fou composé-des-mois : écart {gap_c*100:.3f} % "
        f"{'OK' if gap_c < 0.005 else 'BUG'} | somme PnL ${gap_p:.4f}", "",
        "| Mois | Trades | WR | Liq | Balance | ROI |", "|---|---|---|---|---|---|",
    ]
    for x in mr:
        lines.append(
            f"| {x['month']} | {x['n']} | {x['w']/max(x['n'],1)*100:.0f} % "
            f"| {x['liq']} | ${x['end']:,.0f} | {x['roi']:+.1f} % |")
    lines.append("")
    res["_gap_c"], res["_gap_p"], res["_neg"] = gap_c, gap_p, neg
    return lines


def main() -> int:
    fh = funding_hourly_all()
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    add_rolling_scores(events)
    missing = attach_buy_ratio(events)
    events.sort(key=lambda e: e["ts_ms"])
    all_ev = [e for e in events if np.isfinite(e["buy_ratio"])]
    n = len(all_ev)
    k = int(n * 0.7)
    train, val = all_ev[:k], all_ev[k:]
    liq_all = sum(1 for e in all_ev if e["liq"])

    # les coupures : TRAIN uniquement
    cuts = [float(q) for q in np.quantile([e["buy_ratio"] for e in train],
                                          [0.25, 0.50, 0.75])]
    edges = [-np.inf] + cuts + [np.inf]
    qsel = lambda es, qi: [e for e in es
                           if edges[qi] < e["buy_ratio"] <= edges[qi + 1]]
    tr_mae = [np.mean([e["mae_adverse"] for e in qsel(train, qi)])
              if qsel(train, qi) else np.nan for qi in range(4)]
    va_mae = [np.mean([e["mae_adverse"] for e in qsel(val, qi)])
              if qsel(val, qi) else np.nan for qi in range(4)]
    tr_ok, va_ok = monotone(tr_mae), monotone(va_mae)
    passed = tr_ok and va_ok
    rho_tr = spearman([e["buy_ratio"] for e in train],
                      [e["mae_adverse"] for e in train])
    rho_va = spearman([e["buy_ratio"] for e in val],
                      [e["mae_adverse"] for e in val])

    L = [
        "# H1 — L'ABSORPTION À L'ENTRÉE CASCADE (buy_ratio → MAE)",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — corpus "
        f"anti_liq.collect_featured + add_rolling_scores, majors, hold 24h, "
        f"sélection sim : **{n} events** ({liq_all} liqs label lev20), "
        f"train {len(train)} / val {len(val)} (split PAR LE TEMPS).",
        "",
        "Feature EX-ANTE : buy_ratio = moyenne taker_buy_volume/volume des 4",
        "bougies 1h précédant le signal (barre signal + 3 avant ; l'entrée est",
        "à l'open de la barre suivante — zéro look-ahead). Coupures de",
        "quartiles choisies sur TRAIN : "
        f"{cuts[0]:.4f} / {cuts[1]:.4f} / {cuts[2]:.4f}.",
        f"Symboles du corpus sans CVD 1h (exclus) : "
        f"{missing if missing else 'aucun'}.",
        "",
        "## Gradient map (MAE moyen %, liq @9.5 % = ligne de mort 10x,",
        "WR, espérance marge % @10x maker)", "",
    ]
    L += ["**TRAIN**", ""]
    L += gradient_map(train, cuts, fh)
    L += ["", f"Spearman buy_ratio×MAE TRAIN : {rho_tr:+.3f} — monotone "
              f"Q1→Q4 : {'OUI' if tr_ok else 'NON'}", ""]
    L += ["**VAL (coupures TRAIN)**", ""]
    L += gradient_map(val, cuts, fh)
    L += ["", f"Spearman buy_ratio×MAE VAL : {rho_va:+.3f} — monotone "
              f"Q1→Q4 : {'OUI' if va_ok else 'NON'}", ""]

    if not passed:
        L += ["## VERDICT : FAIL", "",
              "Le gradient pré-enregistré (MAE croissant avec buy_ratio) ne",
              "tient pas en VAL. Aucun sizing branché — la machine reste telle",
              "quelle. Comptable de la leçon : corr7/vol7/funding_rank tiennent",
              "(3), fund7/dispersion/niveau s'inversent (3) — buy_ratio rejoint",
              "le camp des inversés s'il tenait en TRAIN.",
              "", "**Prochaine action** : registre H1 = FAIL, passer à H2",
              "(divergence delta fin de flush)."]
        (REPORTS / "h1-absorption-2026-09-27.md").write_text(
            "\n".join(L) + "\n", encoding="utf-8")
        print(f"[h1] FAIL — train mono {tr_ok}, val mono {va_ok} "
              f"(MAE tr {['%.2f' % x for x in tr_mae]} / "
              f"va {['%.2f' % x for x in va_mae]})")
        return 0

    # ----- PARTIE B : la machine 4 flux, sizing ×{0.75, 1.0, 1.25} par quartile
    # mapping pré-enregistré, sens pris sur TRAIN (MAE croissant) :
    # Q1 (peu d'absorption) ×1.25, Q2/Q3 ×1.0, Q4 (absorption forte) ×0.75.
    def mult_fn(e, cuts):
        br = e.get("buy_ratio", float("nan"))
        if not np.isfinite(br):
            return 1.0
        qi = min(int(np.searchsorted(cuts, br, side="left")), 3)
        return (1.25, 1.0, 1.0, 0.75)[qi]

    all_ev_b, fn_h1, fh2, st = build_machine(mult_fn, cuts)
    all_ev2, fn_base, _, _ = build_machine(lambda e, c: 1.0, cuts)
    base = run_stack(all_ev2, CAPITAL, fn_base, fh2)
    h1 = run_stack(all_ev_b, CAPITAL, fn_h1, fh2)

    L += ["## PARTIE B — LA MACHINE 4 flux (--vol-spike ON), critère :",
          "ROI ≥ baseline ET DD ≤ baseline ET mois négatifs ≤ baseline.", ""]
    L += bloc(base, "BASELINE (réplique machine 4 flux, --vol-spike ON, mult=1.0)")
    L += bloc(h1, "H1 SIZING (×1.25/1.0/1.0/0.75 par quartile buy_ratio, flux cascade_10x)")
    ok = (h1["balance"] >= base["balance"] and h1["max_dd"] <= base["max_dd"]
          and h1["_neg"] <= base["_neg"])
    L += [f"**Machine répliquée** : gate AL p66={st['q66']:.2f}, "
          f"MAE gated {st['mae_gated']:.2f} % → levier sûr {st['lev_safe']:.1f}x, "
          f"flux : gated {st['n_gated']} / meme {st['n_meme']} ({st['lev_meme']}x) / "
          f"surv {st['n_surv']} / spike {st['n_spike']}.", "",
          f"## VERDICT MACHINE : "
          f"{'PASS — adopté comme CANDIDAT' if ok else 'FAIL — rejeté, la machine reste la baseline'}", "",
          "Règle 0-liquidation intacte : le multiplicateur touche la TAILLE",
          "(la marge), jamais le levier (10x, ligne de mort 9.5 % inchangée,",
          f"MAE gated {st['mae_gated']:.2f} % < 9.5 %). Verdict RELATIF : le",
          "composé-des-mois ci-dessus est le garde-fou, pas le final nu.",
          "", "**Prochaine action** : si PASS, re-catégoriser buy_ratio en",
          "CANDIDAT au registre et refaire tourner the_machine officiel avec",
          "le mapping ; sinon H1 en CONTEXTE."]
    (REPORTS / "h1-absorption-2026-09-27.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8")
    print(f"[h1] PASS gradient — MAE tr {['%.2f' % x for x in tr_mae]} / "
          f"va {['%.2f' % x for x in va_mae]}")
    print(f"[machine] baseline ${base['balance']:,.2f} (DD {base['max_dd']:.1f} %, "
          f"liq {base['n_liq']}) vs H1 sizing ${h1['balance']:,.2f} "
          f"(DD {h1['max_dd']:.1f} %, liq {h1['n_liq']}, {h1['_neg']} mois nég)")
    print(f"[machine] verdict : {'PASS' if ok else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
