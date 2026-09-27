#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""H2 (divergence delta) + H3 (sweep volumique) — pré-enregistrées
reports/flow-audit-2026-09-27.md, testées sur le corpus H1 (230 events
majors, anti_liq.collect_featured + add_rolling_scores, hold 24h).

Leçon H1 : les MOYENNES lissent les spikes (buy_ratio plat dès TRAIN) —
on garde la DYNAMIQUE :
  - H2 : PENTE CVD sur les 6 bougies 1h avant l'entrée (régression
    linéaire sur le delta cumulé 2*taker_buy − volume, normalisée par le
    volume moyen) × flag nouveau-bas (close de la barre signal = plus-bas
    des 24h closes). Prédiction : divergence (nouveau bas + pente > 0) →
    le short cascade est DÉGRADÉ (MAE haut, WR bas).
  - H3 : sweep EX-ANTE (le low d'une des 6 bougies avant l'entrée casse
    le plus-bas des 48h précédentes avec un volume > 2× sa moyenne 20
    bougies) → le bounce 4-12h post-entrée est plus ample qu'après un
    casse sec (mauvais pour le short).

Discipline harnais v5 :
  - split train/val PAR LE TEMPS 70/30 ; la zone morte de pente (≈0) est
    le quantile 1/3 des |pentes| de TRAIN uniquement ; les buckets H3
    (2-3×, 3-5×, ≥5×) sont des coupures rondes déclarées a priori.
  - PASS = gradient MONOTONE tenu en TRAIN ET en VAL (cellules non vides).
  - Ordre de danger H2 (déclaré AVANT lecture) :
    (0,nég) < (0,≈0) < (1,nég) < (1,≈0) < (0,pos) < (1,pos)
    — la pente CVD positive (absorption) domine le danger, le nouveau
    bas l'amplifie ; (1,nég) = flush qui continue = meilleur short.
  - Ordre H3 : bounce croissant [no-sweep, 2-3×, 3-5×, ≥5×].
  - si PASS : sizing conditionnel ×{0.75, 1.0, 1.25} (flag vs reste) sur
    la machine 4 flux (--vol-spike ON), BLOC STATS vs baseline.
    Critère : ROI ≥ baseline ET DD ≤ baseline ET mois négatifs ≤ baseline.
    Garde-fou : composé-des-mois ~0 (verdict RELATIF). Le multiplicateur
    touche la TAILLE, jamais le levier (règle 0-liq intacte).

  .venv/bin/python scripts/h2_h3_cvd_test.py
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

LEV_M = 10
LIQ_MOVE_10X = 100 / LEV_M - 0.5       # 9.5 % — la ligne de mort du 10x
FEE_PCT_MARGE = LEV_M * (2 + 0) * 2 / 1e4 * 100   # 0.4 % de marge, maker AR
K = 0.89
H2_ORDER = [(0, "neg"), (0, "zero"), (1, "neg"),
            (1, "zero"), (0, "pos"), (1, "pos")]
H3_BUCKETS = [(0, 0.0), (1, 2.0), (1, 3.0), (1, 5.0)]  # (flag, min_mult)
H3_NAMES = ["no_sweep", "sweep_2_3x", "sweep_3_5x", "sweep_ge5x"]


# ----------------------------------------------------------------- features
def attach_cvd_features(events: list[dict]) -> list[str]:
    """Annote ex-ante sur chaque event :
    - cvd_slope  : pente/h du delta cumulé sur les 6 bougies AVANT
      l'entrée, normalisée par le volume moyen (fraction de vol/h/barre)
    - new_low    : close de la barre signal = plus-bas des 24h closes
    - sweep / sweep_mult : casse du plus-bas 48h PAR du volume (>2× base 20)
    - bounce_4_12 / bounce_atr : max(high 4-12h post-entrée) − entrée
    Retourne les symboles du corpus sans CVD 1h."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    px: dict[str, dict[int, tuple[float, float, float, float]]] = {}
    cvd: dict[str, dict[int, tuple[float, float]]] = {}
    for s, ot, lo, hi, cl, v in con.execute(
            "SELECT symbol, open_time, low, high, close, volume FROM klines "
            "WHERE interval='1h'"):
        px.setdefault(s, {})[int(ot)] = (float(lo or 0), float(hi or 0),
                                         float(cl or 0), float(v or 0))
    for s, ot, tb, v in con.execute(
            "SELECT symbol, open_time, taker_buy_volume, volume FROM klines "
            "WHERE interval='1h' AND taker_buy_volume IS NOT NULL"):
        cvd.setdefault(s, {})[int(ot)] = (float(tb or 0.0), float(v or 0.0))
    con.close()

    for e in events:
        sym = e["sym"]
        ems = int(e["ts_ms"] / 10**6)        # ts_ms = des NS (leçon)
        e["cvd_slope"] = e["bounce_4_12"] = float("nan")
        e["sweep_mult"] = 0.0          # max(NaN, x) = NaN en Python — 0.0 sûr
        e["new_low"] = e["sweep"] = -1
        P, C = px.get(sym), cvd.get(sym)
        if not P:
            continue
        # — pente CVD 6 bougies ex-ante (entry−6h .. entry−1h) —
        bars = [C.get(ems - k * 3600_000) if C else None
                for k in (6, 5, 4, 3, 2, 1)]
        if C is not None and all(b is not None and b[1] > 0 for b in bars):
            delta = np.array([2 * b[0] - b[1] for b in bars])
            cum = np.cumsum(delta)
            slope = float(np.polyfit(np.arange(6), cum, 1)[0])
            e["cvd_slope"] = slope / float(np.mean([b[1] for b in bars]))
        # — nouveau bas : close signal (entry−1h) = min des 24 closes —
        cl24 = [P.get(ems - k * 3600_000) for k in range(1, 25)]
        if all(b is not None for b in cl24):
            closes = [b[2] for b in cl24]
            e["new_low"] = int(closes[0] <= min(closes) + 1e-15)
        # — sweep ex-ante : une des 6 bougies avant l'entrée casse le
        #   plus-bas des 48h précédentes avec vol > 2× sa moyenne 20 —
        for k in range(1, 7):
            j = ems - k * 3600_000
            bj = P.get(j)
            prev48 = [P.get(j - i * 3600_000) for i in range(1, 49)]
            prev20 = [P.get(j - i * 3600_000) for i in range(1, 21)]
            if bj is None or any(b is None for b in prev48) \
                    or any(b is None for b in prev20):
                break
            base = float(np.mean([b[3] for b in prev20]))
            if base <= 0:
                continue
            if bj[0] < min(b[0] for b in prev48) and bj[3] > 2.0 * base:
                e["sweep"] = 1
                e["sweep_mult"] = max(e["sweep_mult"], bj[3] / base)
        if e["sweep"] != 1:
            e["sweep"] = 0
        # — bounce 4-12h post-entrée : max high des barres +4h..+11h —
        hi_post = [P.get(ems + k * 3600_000) for k in range(4, 12)]
        if all(b is not None for b in hi_post) and e["entry"] > 0:
            e["bounce_4_12"] = (max(b[1] for b in hi_post)
                                - e["entry"]) / e["entry"] * 100
    return sorted({e["sym"] for e in events} - set(cvd))


def h2_bucket(e) -> str | None:
    """neg / zero / pos selon la zone morte TRAIN (dz en var globale du test)."""
    s = e.get("cvd_slope", float("nan"))
    if not np.isfinite(s) or e.get("new_low", -1) not in (0, 1):
        return None
    if s < -DZ[0]:
        return "neg"
    if s > DZ[0]:
        return "pos"
    return "zero"


DZ = [float("nan")]        # la zone morte, figée sur TRAIN


def h3_bucket(e) -> str | None:
    m = e.get("sweep_mult", float("nan"))
    if e.get("sweep", -1) != 1 or not np.isfinite(m):
        return "no_sweep" if e.get("sweep") == 0 else None
    if m < H3_BUCKETS[1][1]:
        return "no_sweep"
    if m < H3_BUCKETS[2][1]:
        return "sweep_2_3x"
    if m < H3_BUCKETS[3][1]:
        return "sweep_3_5x"
    return "sweep_ge5x"


# ----------------------------------------------------------------- reading
def exp_pct(e, fh) -> float:
    return (e["price_ret_short"] * LEV_M + 240 * fh.get(e["sym"], 0.0)
            - FEE_PCT_MARGE)


def h2_table(split: list[dict], fh) -> list[str]:
    lines = ["| Cellule | n | MAE % | Liq @9.5 | WR % | Espérance marge % |",
             "|---|---|---|---|---|---|"]
    for nl, bk in H2_ORDER:
        m = [e for e in split if e["h2_b"] == bk
             and e["new_low"] == nl]
        tag = f"NL={nl} × pente {bk}"
        if not m:
            lines.append(f"| {tag} | 0 | — | — | — | — |")
            continue
        mae = np.array([e["mae_adverse"] for e in m])
        liq = np.mean([e["mae_adverse"] >= LIQ_MOVE_10X for e in m]) * 100
        wr = np.mean([e["price_ret_short"] > 0 for e in m]) * 100
        exp = float(np.mean([exp_pct(e, fh) for e in m]))
        lines.append(f"| {tag} | {len(m)} | {mae.mean():.2f} | {liq:.1f} % "
                     f"| {wr:.1f} % | {exp:+.1f} |")
    return lines


def h3_table(split: list[dict], fh) -> list[str]:
    lines = ["| Bucket | n | Bounce 4-12h % (moy) | Bounce méd | Bounce/ATR "
             "| MAE 24h % | WR % | Espérance marge % |",
             "|---|---|---|---|---|---|---|---|"]
    for bk in H3_NAMES:
        m = [e for e in split if e["h3_b"] == bk]
        if not m:
            lines.append(f"| {bk} | 0 | — | — | — | — | — | — |")
            continue
        b = np.array([e["bounce_4_12"] for e in m if np.isfinite(e["bounce_4_12"])])
        ba = np.array([e["bounce_4_12"] / e["atr_pct"] for e in m
                       if np.isfinite(e["bounce_4_12"]) and e["atr_pct"] > 0])
        mae = np.array([e["mae_adverse"] for e in m])
        wr = np.mean([e["price_ret_short"] > 0 for e in m]) * 100
        exp = float(np.mean([exp_pct(e, fh) for e in m]))
        lines.append(
            f"| {bk} | {len(m)} | {b.mean() if len(b) else float('nan'):.2f} "
            f"| {np.median(b) if len(b) else float('nan'):.2f} "
            f"| {ba.mean() if len(ba) else float('nan'):.2f} "
            f"| {mae.mean():.2f} | {wr:.1f} % | {exp:+.1f} |")
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


# ----------------------------------------------------------------- machine
def build_machine(flag_features: bool):
    """Réplique EXACTE de the_machine.main (4 flux, --vol-spike ON),
    features CVD attachées AVANT le gate, machine_fn paramétré par
    mult_fn (le SEUL écart, comme h1_absorption_test)."""
    from scripts.full_arsenal_2 import collect as collect_arsenal
    from scripts.p5_frequency_test import collect_vol_spike
    from scripts.the_machine import collect_meme

    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = LEV_M
        e["hold_h"] = 24
        e["fee_rt_bps"] = (2 + 0) * 2
    if flag_features:
        attach_cvd_features(events)
        for e in events:
            e["h2_b"] = h2_bucket(e)
            e["h3_b"] = h3_bucket(e)
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

    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = lev_meme

    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    _p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= _p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = (4 + 10) * 2

    spike = collect_vol_spike(con, hold=6)
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = (4 + 10) * 2
    med_spike = float(np.median([e["atr_pct"] for e in spike])) if spike else np.nan
    con.close()

    all_ev = sorted(gated + meme + surv + spike, key=lambda e: e["ts_ms"])

    def make_fn(mult_fn):
        def machine_fn(e, st=None):
            s = e.get("strategy")
            if s == "cascade_10x":
                s0 = min(max(0.24 * K * (e["atr_pct"] / med_majors),
                             0.08 * K), 0.40 * K)
                if (np.isfinite(e.get("fund_rank", np.nan))
                        and e["fund_rank"] <= 0.33):
                    s0 = min(s0 * 1.5, 0.50 * K)
                return min(s0 * mult_fn(e), 0.50 * K)   # ← le SEUL écart
            if s == "cascade_meme":
                return min(max(0.10 * K * (e["atr_pct"] / med_meme),
                               0.02 * K), 0.30 * K)
            if s == "vol_spike_6h":
                return min(max(0.10 * K * (e["atr_pct"] / med_spike),
                               0.02 * K), 0.30 * K)
            return 0.20 * K
        return machine_fn

    stats = {"q66": q66, "mae_gated": mae_gated, "lev_safe": lev_safe,
             "lev_meme": lev_meme, "mae_meme": mae_meme,
             "n_gated": len(gated), "n_meme": len(meme), "n_surv": len(surv),
             "n_spike": len(spike), "fh": fh}
    return all_ev, make_fn, stats


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


# ----------------------------------------------------------------- main
def main() -> int:
    fh = funding_hourly_all()
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    add_rolling_scores(events)
    missing = attach_cvd_features(events)
    events.sort(key=lambda e: e["ts_ms"])
    h2_raw = [e for e in events
              if np.isfinite(e.get("cvd_slope", float("nan")))
              and e.get("new_low", -1) in (0, 1)]
    k2 = int(len(h2_raw) * 0.7)
    # zone morte H2 : TRAIN uniquement (quantile 1/3 des |pentes|)
    DZ[0] = float(np.quantile([abs(e["cvd_slope"]) for e in h2_raw[:k2]], 1 / 3))
    for e in events:
        e["h2_b"] = h2_bucket(e)
        e["h3_b"] = h3_bucket(e)

    n_all = len(events)
    h2_ev = h2_raw
    tr2, va2 = h2_raw[:k2], h2_raw[k2:]
    h3_ev = [e for e in events if e["h3_b"] is not None
             and np.isfinite(e["bounce_4_12"])]
    k3 = int(len(h3_ev) * 0.7)
    tr3, va3 = h3_ev[:k3], h3_ev[k3:]

    L = [
        "# H2 (divergence delta) + H3 (sweep volumique) — CVD 1h",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — corpus "
        f"anti_liq.collect_featured + add_rolling_scores, majors, hold 24h : "
        f"**{n_all} events** ; H2 exploitable {len(h2_ev)} "
        f"(train {len(tr2)} / val {len(va2)}), H3 exploitable {len(h3_ev)} "
        f"(train {len(tr3)} / val {len(va3)}) — split PAR LE TEMPS 70/30.",
        f"Symboles du corpus sans CVD 1h : {missing if missing else 'aucun'}.",
        "",
        "Features EX-ANTE (leçon H1 : la dynamique, pas la moyenne) :",
        "- H2 : pente CVD = régression linéaire du delta cumulé "
        "(2*taker_buy − volume) sur les 6 bougies 1h avant l'entrée,",
        "  normalisée par le volume moyen ; flag nouveau-bas = close de la",
        "  barre signal = plus-bas des 24 closes précédentes. Zone morte",
        f" ≈0 : |pente| ≤ {DZ[0]:.4f} (q33 des |pentes| TRAIN).",
        "- H3 : sweep = low d'une des 6 bougies avant l'entrée < plus-bas",
        "  des 48h précédentes, avec volume > 2× sa moyenne 20 bougies ;",
        "  outcome = max(high 4-12h post-entrée) − entrée.",
        "",
        "Ordre de danger H2 (déclaré avant lecture) : (0,nég) < (0,≈0) <",
        "(1,nég) < (1,≈0) < (0,pos) < (1,pos) — la pente CVD positive",
        "(absorption) domine, le nouveau bas amplifie ; (1,nég) = flush",
        "qui continue. Ordre H3 : bounce croissant no-sweep → 2-3× →",
        "3-5× → ≥5×. PASS = monotone en TRAIN ET en VAL.", "",
    ]

    # ---------------- H2
    tr_mae2 = [np.mean([e["mae_adverse"] for e in tr2
                        if e["h2_b"] == bk and e["new_low"] == nl])
               if any(e["h2_b"] == bk and e["new_low"] == nl for e in tr2)
               else np.nan for nl, bk in H2_ORDER]
    va_mae2 = [np.mean([e["mae_adverse"] for e in va2
                        if e["h2_b"] == bk and e["new_low"] == nl])
               if any(e["h2_b"] == bk and e["new_low"] == nl for e in va2)
               else np.nan for nl, bk in H2_ORDER]
    tr_ok2, va_ok2 = monotone(tr_mae2), monotone(va_mae2)
    rho2_tr = spearman([e["cvd_slope"] for e in tr2],
                       [e["mae_adverse"] for e in tr2])
    rho2_va = spearman([e["cvd_slope"] for e in va2],
                       [e["mae_adverse"] for e in va2])
    div_tr = [e for e in tr2 if e["h2_b"] == "pos" and e["new_low"] == 1]
    div_va = [e for e in va2 if e["h2_b"] == "pos" and e["new_low"] == 1]
    rest_tr = [e for e in tr2 if not (e["h2_b"] == "pos" and e["new_low"] == 1)]
    rest_va = [e for e in va2 if not (e["h2_b"] == "pos" and e["new_low"] == 1)]

    L += ["## H2 — divergence delta (pente CVD 6h × nouveau-bas)", ""]
    L += ["**TRAIN**", ""]
    L += h2_table(tr2, fh)
    L += ["", f"MAE le long de l'ordre : "
              f"{['%.2f' % x for x in tr_mae2]} — monotone : "
              f"{'OUI' if tr_ok2 else 'NON'}", ""]
    L += ["**VAL (zone morte TRAIN)**", ""]
    L += h2_table(va2, fh)
    L += ["", f"MAE le long de l'ordre : "
              f"{['%.2f' % x for x in va_mae2]} — monotone : "
              f"{'OUI' if va_ok2 else 'NON'}", ""]
    if div_tr and rest_tr and div_va and rest_va:
        L += [
            f"Cellule divergence (NL=1 × pos) vs reste — TRAIN : MAE "
            f"{np.mean([e['mae_adverse'] for e in div_tr]):.2f} vs "
            f"{np.mean([e['mae_adverse'] for e in rest_tr]):.2f} %, WR "
            f"{np.mean([e['price_ret_short'] > 0 for e in div_tr])*100:.1f} vs "
            f"{np.mean([e['price_ret_short'] > 0 for e in rest_tr])*100:.1f} % "
            f"(n {len(div_tr)} vs {len(rest_tr)}) ; VAL : MAE "
            f"{np.mean([e['mae_adverse'] for e in div_va]):.2f} vs "
            f"{np.mean([e['mae_adverse'] for e in rest_va]):.2f} %, WR "
            f"{np.mean([e['price_ret_short'] > 0 for e in div_va])*100:.1f} vs "
            f"{np.mean([e['price_ret_short'] > 0 for e in rest_va])*100:.1f} % "
            f"(n {len(div_va)} vs {len(rest_va)}).",
            f"Spearman pente×MAE : TRAIN {rho2_tr:+.3f}, VAL {rho2_va:+.3f}.", ""]

    # ---------------- H3
    tr_b3 = [np.mean([e["bounce_4_12"] for e in tr3 if e["h3_b"] == bk])
             if any(e["h3_b"] == bk for e in tr3) else np.nan
             for bk in H3_NAMES]
    va_b3 = [np.mean([e["bounce_4_12"] for e in va3 if e["h3_b"] == bk])
             if any(e["h3_b"] == bk for e in va3) else np.nan
             for bk in H3_NAMES]
    tr_ok3, va_ok3 = monotone(tr_b3), monotone(va_b3)
    sw_tr = [e for e in tr3 if e["sweep"] == 1]
    sw_va = [e for e in va3 if e["sweep"] == 1]
    nsw_tr = [e for e in tr3 if e["sweep"] == 0]
    nsw_va = [e for e in va3 if e["sweep"] == 0]

    L += ["## H3 — sweep volumique → bounce 4-12h", ""]
    L += ["**TRAIN**", ""]
    L += h3_table(tr3, fh)
    L += ["", f"Bounce moyen le long de l'ordre : "
              f"{['%.2f' % x for x in tr_b3]} — monotone : "
              f"{'OUI' if tr_ok3 else 'NON'}", ""]
    L += ["**VAL**", ""]
    L += h3_table(va3, fh)
    L += ["", f"Bounce moyen le long de l'ordre : "
              f"{['%.2f' % x for x in va_b3]} — monotone : "
              f"{'OUI' if va_ok3 else 'NON'}", ""]
    if sw_tr and nsw_tr and sw_va and nsw_va:
        L += [
            f"Sweep vs casse sec — TRAIN : bounce "
            f"{np.mean([e['bounce_4_12'] for e in sw_tr]):.2f} vs "
            f"{np.mean([e['bounce_4_12'] for e in nsw_tr]):.2f} % "
            f"(n {len(sw_tr)} vs {len(nsw_tr)}), MAE 24h "
            f"{np.mean([e['mae_adverse'] for e in sw_tr]):.2f} vs "
            f"{np.mean([e['mae_adverse'] for e in nsw_tr]):.2f} % ; VAL : "
            f"bounce {np.mean([e['bounce_4_12'] for e in sw_va]):.2f} vs "
            f"{np.mean([e['bounce_4_12'] for e in nsw_va]):.2f} % "
            f"(n {len(sw_va)} vs {len(nsw_va)}), MAE 24h "
            f"{np.mean([e['mae_adverse'] for e in sw_va]):.2f} vs "
            f"{np.mean([e['mae_adverse'] for e in nsw_va]):.2f} %.", ""]

    pass2, pass3 = tr_ok2 and va_ok2, tr_ok3 and va_ok3
    if not pass2 and not pass3:
        L += [
            "## VERDICT : FAIL H2 ET FAIL H3", "",
            f"- H2 : monotone TRAIN {tr_ok2} / VAL {va_ok2} — le gradient "
            f"pré-enregistré (divergence → short dégradé) ne tient pas.",
            f"- H3 : monotone TRAIN {tr_ok3} / VAL {va_ok3} — le bounce "
            f"après sweep volumique ne domine pas de façon monotone.",
            "",
            "Aucun sizing branché — la machine reste la baseline "
            "(thé-machine 4 flux, $4 004,94). Les 2 hypothèses vont au",
            "registre avec leurs chiffres, sans promotion.",
            "",
            "**Prochaine action** : H4/H5 (quadrants OI) restent "
            "bloquées par le backfill OI granulaire ; sinon wall-clock "
            "sur les cascades (l'heure d'entrée).",
        ]
        (REPORTS / "h2-h3-cvd-2026-09-27.md").write_text(
            "\n".join(L) + "\n", encoding="utf-8")
        print(f"[h2h3] FAIL — H2 mono tr {tr_ok2} va {va_ok2} "
              f"({['%.2f' % x for x in tr_mae2]} / "
              f"{['%.2f' % x for x in va_mae2]}) ; "
              f"H3 mono tr {tr_ok3} va {va_ok3} "
              f"({['%.2f' % x for x in tr_b3]} / {['%.2f' % x for x in va_b3]})")
        return 0

    # ---------------- PARTIE B : la machine 4 flux
    all_ev, make_fn, st = build_machine(flag_features=True)
    fh2 = st["fh"]

    def h2_flag(e):
        return e.get("h2_b") == "pos" and e.get("new_low") == 1

    def h3_flag(e):
        return e.get("sweep") == 1

    flag_fn = h2_flag if pass2 else h3_flag
    which = "H2 (divergence NL=1×pos)" if pass2 else "H3 (sweep ≥2×)"

    variants = [("baseline (mult ≡ 1.0)", lambda e: 1.0),
                ("flag ×0.75 / reste ×1.0", lambda e: 0.75 if flag_fn(e) else 1.0),
                ("flag ×0.75 / reste ×1.25", lambda e: 0.75 if flag_fn(e) else 1.25),
                ("flag ×1.0 / reste ×1.25", lambda e: 1.0 if flag_fn(e) else 1.25)]
    n_flag = sum(1 for e in all_ev
                 if e.get("strategy") == "cascade_10x" and flag_fn(e))

    L += ["## PARTIE B — LA MACHINE 4 flux (--vol-spike ON), sizing "
          f"conditionnel sur {which}", "",
          f"Trades cascade_10x flagués : {n_flag} / "
          f"{st['n_gated']} gated. Critère par variante : ROI ≥ baseline ET "
          "DD ≤ baseline ET mois négatifs ≤ baseline. Le multiplicateur "
          "touche la TAILLE, jamais le levier (10x, ligne de mort 9.5 %, "
          f"MAE gated {st['mae_gated']:.2f} % — règle 0-liq intacte).", ""]
    results = []
    for label, mf in variants:
        res = run_stack(all_ev, CAPITAL, make_fn(mf), fh2)
        results.append((label, res))
        L += bloc(res, label)
    base = results[0][1]
    L += [f"**Machine répliquée** : gate AL p66={st['q66']:.2f}, MAE gated "
          f"{st['mae_gated']:.2f} % → levier sûr {st['lev_safe']:.1f}x, "
          f"flux : gated {st['n_gated']} / meme {st['n_meme']} "
          f"({st['lev_meme']}x) / surv {st['n_surv']} / spike {st['n_spike']}.",
          ""]
    best_label, best = None, None
    for label, res in results[1:]:
        ok = (res["balance"] >= base["balance"] and res["max_dd"] <= base["max_dd"]
              and res["_neg"] <= base["_neg"])
        L.append(f"- {label} : {'PASS' if ok else 'fail'} "
                 f"(${res['balance']:,.2f}, DD {res['max_dd']:.1f} %, "
                 f"{res['_neg']} mois nég)")
        if ok and (best is None or res["balance"] > best["balance"]):
            best_label, best = label, res
    L += ["", f"## VERDICT MACHINE : "
              f"{'PASS — ' + best_label + ' adopté comme CANDIDAT' if best else 'FAIL — rejeté, la machine reste la baseline'}",
          "",
          "Verdict RELATIF : le composé-des-mois ci-dessus est le",
          "garde-fou, pas le final nu. Baseline officielle 27/09 02:03 :",
          "$4 004,94 (+3 905 %/an, DD 24,8 %, 0 liq, record +90,8 %).", "",
          "**Prochaine action** : si PASS, re-catégoriser l'indicateur au",
          "registre (CANDIDAT) et câbler le mapping au paper forward ;",
          "sinon CONTEXTE/NUL avec les chiffres du gradient."]
    (REPORTS / "h2-h3-cvd-2026-09-27.md").write_text(
        "\n".join(L) + "\n", encoding="utf-8")
    for label, res in results:
        print(f"[h2h3] {label}: ${res['balance']:,.2f} DD {res['max_dd']:.1f} % "
              f"liq {res['n_liq']} neg {res['_neg']}")
    print(f"[h2h3] verdict machine : {'PASS ' + best_label if best else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
