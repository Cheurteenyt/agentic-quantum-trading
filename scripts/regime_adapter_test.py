#!/usr/bin/env python
"""L'ADAPTATEUR DE RÉGIME — réagir à la QUALITÉ DU SIGNAL, pas au wallet.

Contexte (reports/decay-curve-2026-09-28.md) : l'edge du gated cascade
majors par trimestre = +0.96 / +0.76 / +0.75 % → **-0.09 % au T3 2026**.
Le garde wallet-level a FAIL (il coupait les rebonds). L'adaptateur est
le mécanisme JAMAIS testé : l'espérance roulante 90 j des trades CLÔTURÉS
du flux gated cascade majors (corpus 165/230, ret short moyen — la même
métrique que la decay curve), et si elle passe sous un seuil → le SIZING
du flux ×r jusqu'au retour. Lent (90 j), lisse (dizaines de trades),
mécaniquement fondé (l'edge mesuré, pas la douleur ressentie).

PRÉ-ENREGISTREMENTS (gravés avant tout run) :
  - seuil OFFICIEL = p25 de la distribution roulante sur TRAIN (70 % temps)
  - alternative testée (non officielle) = seuil plat 0.30 %
  - r ∈ {0.5, 0.75}, appliqué au sizing du flux cascade_10x UNIQUEMENT
  - hystérésis de retour : espérance ≥ seuil pendant 30 j CONTINUS
  - min_n = 10 trades clôturés dans la fenêtre pour déclarer le régime
    mort (la mission : « lisse, basé sur des dizaines de trades »)
  - ZÉRO look-ahead : à chaque date, seuls les trades DÉJÀ CLÔTURÉS
    (exit ≤ date) entrent dans la fenêtre — le lag 90 j est naturel.
  - l'espérance roule sur le CORPUS du flux (signal), pas sur le chemin
    du wallet (pas de circularité balance → sélection → signal).

Validation harnais : la réplique baseline doit retomber sur $4,004.94
(the-machine-2026-09-27-volspike.md) sinon les résultats sont marqués
invalides.

  .venv/bin/python scripts/regime_adapter_test.py
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

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, btc_regime_series, monthly_rows)
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import collect_meme  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402

REPORTS = ROOT / "reports"
OUT = REPORTS / "regime-adapter-2026-09-28.md"
BASELINE_REF = 4004.94          # the-machine-2026-09-27-volspike.md

DAY_NS = 86_400 * 10**9
WIN_NS = 90 * DAY_NS            # la fenêtre roulante
HOLD_NS = 24 * 3600 * 10**9     # hold cascade 24 h (ts_ms = ns)
HYS_NS = 30 * DAY_NS            # hystérésis de retour
MIN_N = 10                      # dizaine minimale pour déclarer le régime mort
K = 0.89                        # le facteur global de the_machine
THRESH_FLAT = 0.30              # alternative non officielle
FACTORS = (0.5, 0.75)
GOOD_Q = ("2025-Q4", "2026-Q1", "2026-Q2")     # les bons régimes
T3_M = ("2026-07", "2026-08", "2026-09")       # le régime mort


# ————————————————————————————— le flux —————————————————————————————
def build_flows() -> tuple:
    """Réplique bit-à-bit de la collecte 4 flux de the_machine.main()."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # flux 1 : cascade majeurs 10x gated AL p66 (identique the_machine)
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
    med_majors = float(np.median([e["atr_pct"] for e in gated]))

    # le poids QUALITÉ fund_rank (copie exacte the_machine)
    funding_ts: dict[str, tuple[list, list]] = {}
    for s, t, r_ in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts_l, rt_l = funding_ts.setdefault(s, ([], []))
            ts_l.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt_l.append(float(r_))
        except (TypeError, ValueError):
            continue
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

    # flux 2 : cascade memecoins (levier mécanique)
    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    for e in meme:
        e["lev"] = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))

    # flux 3 : survivor long 72h, filtre ATR décile supérieur
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    _p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= _p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT

    # flux 4 : vol-spike reversion 6h (import lazy — cycle p5↔machine)
    from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
    spike = collect_vol_spike(con, hold=6)
    med_spike = float(np.median([e["atr_pct"] for e in spike]))
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    con.close()
    for e in gated:
        e["lev"] = 10
    all_ev = sorted(gated + meme + surv + spike, key=lambda e: e["ts_ms"])
    return all_ev, gated, med_majors, med_meme, med_spike, q66, fh


def make_machine_fn(med_majors: float, med_meme: float, med_spike: float,
                    factor_map: dict[int, float]):
    """machine_fn exact (K=0.89, fund_rank ×1.5, pas de corr-tilt) +
    l'adaptateur : ×r sur le sizing cascade quand le régime est mort."""
    def fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * K * (e["atr_pct"] / med_majors), 0.08 * K),
                     0.40 * K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                s0 = min(s0 * 1.5, 0.50 * K)
            return s0 * factor_map.get(id(e), 1.0)
        if s == "cascade_meme":
            return min(max(0.10 * K * (e["atr_pct"] / med_meme), 0.02 * K),
                       0.30 * K)
        if s == "vol_spike_6h":
            return min(max(0.10 * K * (e["atr_pct"] / med_spike), 0.02 * K),
                       0.30 * K)
        return 0.20 * K                    # survivor long
    return fn


# ——————————————————— le signal de régime (zéro look-ahead) ———————————————————
class RollingExpectancy:
    """Espérance roulante 90 j des trades CLÔTURÉS du flux (exits seuls)."""

    def __init__(self, gated: list[dict]):
        pairs = sorted((e["ts_ms"] + HOLD_NS, e["price_ret_short"])
                       for e in gated)
        self.ex_ts = np.array([p[0] for p in pairs])
        self.rets = np.array([p[1] for p in pairs])
        self.cum = np.concatenate([[0.0], np.cumsum(self.rets)])

    def asof(self, ts: int) -> tuple[float, int]:
        """(espérance des exits dans (ts-90j, ts], n) — exits ≤ ts UNIQUEMENT."""
        hi = int(np.searchsorted(self.ex_ts, ts, side="right"))
        lo = int(np.searchsorted(self.ex_ts, ts - WIN_NS, side="right"))
        n = hi - lo
        if n <= 0:
            return float("nan"), 0
        return float((self.cum[hi] - self.cum[lo]) / n), n


def build_timeline(rex: RollingExpectancy,
                   thr: float) -> tuple[np.ndarray, np.ndarray]:
    """L'état de l'adaptateur (True=plein sizing) à chaque mise à jour du
    signal (chaque clôture de trade). Hystérésis 30 j, min_n = MIN_N."""
    on = True
    first_above: int | None = None
    tl_t: list[int] = []
    tl_s: list[bool] = []
    for t in rex.ex_ts:
        exp, n = rex.asof(int(t))
        if on:
            if n >= MIN_N and np.isfinite(exp) and exp < thr:
                on = False                  # le régime mesuré est mort
                first_above = None
        else:
            if np.isfinite(exp) and exp >= thr:
                if first_above is None:
                    first_above = int(t)
                if int(t) - first_above >= HYS_NS:
                    on = True               # 30 j au-dessus → retour
                    first_above = None
            else:
                first_above = None
        tl_t.append(int(t))
        tl_s.append(on)
    return np.array(tl_t), np.array(tl_s)


def state_at(tl_t: np.ndarray, tl_s: np.ndarray, ts: int) -> bool:
    i = int(np.searchsorted(tl_t, ts, side="right")) - 1
    return bool(tl_s[i]) if i >= 0 else True


def full_bloc(res: dict, label: str, capital: float) -> tuple[list[str], dict]:
    """BLOC STATS doctrinal : composé des mois vs final, somme PnL."""
    mr = monthly_rows(res["trades"], capital)
    rois = [x["roi"] for x in mr]
    prod = 1.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
    gap_c = abs(prod - res["balance"] / capital)
    gap_p = abs(sum(x["pnl"] for x in mr) - (res["balance"] - capital))
    n = max(res["n"], 1)
    st = {"balance": res["balance"], "roi": (res["balance"] / capital - 1) * 100,
          "dd": res["max_dd"], "n": res["n"], "wr": res["n_wins"] / n * 100,
          "liq": res["n_liq"], "mean": float(np.mean(rois)) if rois else 0.0,
          "worst": min(rois) if rois else 0.0,
          "rec": max(rois) if rois else 0.0,
          "neg": sum(1 for x in rois if x < 0), "gap_c": gap_c,
          "gap_p": gap_p, "mr": mr}
    lines = [
        f"**{label}** : ${capital:,.0f} → **${res['balance']:,.2f}** "
        f"(ROI **{st['roi']:+.0f} %/an**, DD {st['dd']:.1f} %, "
        f"liq **{st['liq']}**, {st['n']} trades, WR {st['wr']:.1f} %)",
        f"  mois : moyen {st['mean']:+.1f} % / pire {st['worst']:+.1f} % / "
        f"record {st['rec']:+.1f} %, {st['neg']} négatifs — "
        f"composé écart {gap_c*100:.3f} %, PnL ${gap_p:.4f}",
    ]
    return lines, st


def q_of(dt: datetime) -> str:
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def t3_roi(mr: list[dict]) -> float:
    rows = [x for x in mr if x["month"] in T3_M]
    if not rows:
        return 0.0
    return (float(np.prod([1 + x["roi"] / 100 for x in rows])) - 1) * 100


def off_pct_per_quarter(tl_t: np.ndarray, tl_s: np.ndarray,
                        last_exit: int) -> dict[str, float]:
    """% du temps OFF par trimestre (pondéré par la durée entre updates)."""
    tot: dict[str, float] = {}
    off: dict[str, float] = {}
    pts = tl_t.tolist()
    for i, t in enumerate(pts):
        nxt = pts[i + 1] if i + 1 < len(pts) else last_exit
        if nxt <= t:
            continue
        q = q_of(datetime.fromtimestamp(t / 10**9, tz=timezone.utc))
        tot[q] = tot.get(q, 0.0) + (nxt - t)
        if not tl_s[i]:
            off[q] = off.get(q, 0.0) + (nxt - t)
    return {q: (off.get(q, 0.0) / tot[q] * 100) for q in tot if tot[q] > 0}


def main() -> int:
    t0 = datetime.now(timezone.utc)
    (all_ev, gated, med_majors, med_meme, med_spike, q66,
     fh) = build_flows()
    rex = RollingExpectancy(gated)
    last_exit = int(rex.ex_ts[-1])

    # —— TRAIN/VAL par le temps (70/30 sur le corpus gated) ——
    by_entry = sorted(gated, key=lambda e: e["ts_ms"])
    k = int(len(by_entry) * 0.7)
    train_end = by_entry[k - 1]["ts_ms"]
    train_vals = np.array([rex.asof(e["ts_ms"])[0] for e in by_entry[:k]])
    train_vals = train_vals[np.isfinite(train_vals)]
    thr_p25 = float(np.quantile(train_vals, 0.25))       # le choix pré-enregistré

    # —— la courbe roulante (fins de mois + dernier point) ——
    ends = pd.date_range("2025-10-31", periods=13, freq="ME", tz="UTC")
    curve: list[tuple[str, float, int]] = []
    for e in ends:
        ts = int(e.value)
        if ts > last_exit:
            continue
        v, n = rex.asof(ts)
        curve.append((e.strftime("%Y-%m"), v, n))
    curve.append(("dernier", rex.asof(last_exit)[0], rex.asof(last_exit)[1]))

    # —— stats trimestrielles du corpus (réplique decay curve) ——
    qstat: dict[str, list[float]] = {}
    for e in by_entry:
        qstat.setdefault(q_of(datetime.fromtimestamp(
            e["ts_ms"] / 10**9, tz=timezone.utc)), []).append(
            e["price_ret_short"])
    qmean = {q: float(np.mean(v)) for q, v in qstat.items()}

    # —— baseline (validation harnais) + runs adaptateur ——
    base = run_stack(all_ev, CAPITAL,
                     make_machine_fn(med_majors, med_meme, med_spike, {}), fh)
    harness_ok = abs(base["balance"] - BASELINE_REF) < 0.02
    runs: dict[str, dict] = {}
    timelines: dict[str, tuple] = {}
    for thr_label, thr in (("p25 TRAIN", thr_p25), ("0.30 % plat", THRESH_FLAT)):
        timelines[thr_label] = build_timeline(rex, thr)
        tl_t, tl_s = timelines[thr_label]
        for r in FACTORS:
            fmap = {id(e): (1.0 if state_at(tl_t, tl_s, e["ts_ms"]) else r)
                    for e in gated}
            res = run_stack(all_ev, CAPITAL,
                            make_machine_fn(med_majors, med_meme, med_spike,
                                            fmap), fh)
            runs[f"{thr_label} ×{r}"] = {"res": res, "thr": thr, "r": r,
                                         "tl": (tl_t, tl_s)}

    # —— BLOC STATS ——
    blocs, stats = [], {}
    bl, stats["BASELINE"] = full_bloc(base, "BASELINE (machine 4 flux)",
                                      CAPITAL)
    blocs += bl
    for lbl in runs:
        bl, stats[lbl] = full_bloc(runs[lbl]["res"], f"ADAPTATEUR {lbl}",
                                   CAPITAL)
        blocs += bl

    b = stats["BASELINE"]
    lines = [
        "# L'ADAPTATEUR DE RÉGIME — réagir à la qualité du signal",
        f"{t0:%d/%m/%Y %H:%M} UTC — gated cascade majors "
        f"**{len(gated)} events** (gate AL p66={q66:.2f}) ; espérance "
        f"roulante 90 j des trades CLÔTURÉS (ret short moyen, métrique "
        f"decay-curve) ; sizing du flux ×{{0.5, 0.75}} si sous le seuil ; "
        f"hystérésis 30 j ; min_n {MIN_N} ; les 4 flux, --vol-spike ON.",
        "",
        f"**Pré-enregistrements** : seuil officiel = TRAIN p25 "
        f"(**{thr_p25:+.3f} %**, {len(train_vals)} lectures TRAIN, split "
        f"70/30 par le temps au "
        f"{datetime.fromtimestamp(train_end / 10**9, tz=timezone.utc):%d/%m/%Y})"
        f" ; alternative testée {THRESH_FLAT:.2f} % ; ZÉRO look-ahead — "
        f"seuls les trades clôturés (exit ≤ date) alimentent la fenêtre.",
        "",
        f"**Validation harnais** : baseline réplique ${base['balance']:,.2f} "
        f"vs référence ${BASELINE_REF:,.2f} → "
        f"{'**OK — bit-reproductible**' if harness_ok else '**✗ ÉCART — résultats suspects**'}.",
        "",
        "## La courbe roulante (espérance 90 j des clôturés)", "",
        "| Fin de période | Espérance 90 j | n trades |", "|---|---|---|"]
    for m, v, n in curve:
        flag = " **< p25**" if (np.isfinite(v) and v < thr_p25) else ""
        lines.append(f"| {m} | {v:+.3f} % | {n}{flag} |")
    lines += ["", "### Par trimestre d'entrée (réplique decay curve)", ""]
    for q in sorted(qmean):
        mark = " ← le régime mort" if q == "2026-Q3" else ""
        lines.append(f"- {q} : n={len(qstat[q])}, ret short moyen "
                     f"**{qmean[q]:+.2f} %**{mark}")

    lines += ["", "## Les périodes OFF (régime déclaré mort)", ""]
    for lbl, (tl_t, tl_s) in timelines.items():
        offs = [i for i in range(len(tl_t)) if not tl_s[i]]
        segs: list[tuple[int, int]] = []
        for i in offs:
            t = int(tl_t[i])
            nxt = int(tl_t[i + 1]) if i + 1 < len(tl_t) else last_exit
            if segs and t <= segs[-1][1]:
                segs[-1] = (segs[-1][0], max(segs[-1][1], nxt))
            else:
                segs.append((t, nxt))
        lines.append(f"- seuil **{lbl}** ({thr_p25:+.3f} %"
                     if lbl.startswith("p25") else
                     f"- seuil **{lbl}** ({THRESH_FLAT:.2f} %)")
        lines[-1] += f" : {len(segs)} période(s) OFF"
        for a, c in segs:
            da = datetime.fromtimestamp(a / 10**9, tz=timezone.utc)
            dc = datetime.fromtimestamp(min(c, last_exit) / 10**9,
                                        tz=timezone.utc)
            lines.append(f"  - OFF {da:%d/%m/%Y} → {dc:%d/%m/%Y} "
                         f"({(min(c, last_exit) - a) / DAY_NS:.0f} j)")

    lines += ["", "## BLOC STATS — baseline vs adaptateur", ""] + blocs

    # —— le critère du user ——
    lines += ["", "### Le critère (DD ≤ baseline ET pire mois amélioré ET "
              "ROI ≥ baseline −15 %)", "",
              f"| Config | DD ≤ {b['dd']:.1f} | pire mois > {b['worst']:+.1f} "
              f"| ROI ≥ {b['roi']*.85:+.0f} | Verdict |", "|---|---|---|---|---|"]
    for lbl, st in stats.items():
        if lbl == "BASELINE":
            continue
        ok_dd = st["dd"] <= b["dd"] + 1e-9
        ok_w = st["worst"] > b["worst"] + 1e-9
        ok_roi = st["roi"] >= b["roi"] * 0.85 - 1e-9
        verdict = ("VALIDÉ" if (ok_dd and ok_w and ok_roi) else
                   "PARTIEL" if (ok_dd or ok_w) else "FAIL")
        lines.append(
            f"| {lbl} | {'oui' if ok_dd else '**non**'} ({st['dd']:.1f}) "
            f"| {'oui' if ok_w else '**non**'} ({st['worst']:+.1f}) "
            f"| {'oui' if ok_roi else '**non**'} ({st['roi']:+.0f}) "
            f"| **{verdict}** |")

    # —— T3 2026 : l'adaptateur aurait-il protégé ? ——
    lines += ["", "## T3 2026 (juil-sept) : l'exposition du flux majors", "",
              "| Config | Marge cascade T3 | PnL cascade T3 | ROI wallet T3 |",
              "|---|---|---|---|"]

    def cascade_t3(res) -> list[dict]:
        return [t for t in res["trades"]
                if t["strategy"] == "cascade_10x"
                and t["entry_ts"].strftime("%Y-%m") in T3_M]

    for lbl, res, st in ([("BASELINE ×1", base, stats["BASELINE"])]
                         + [(l, runs[l]["res"], stats[l]) for l in runs]):
        cas = cascade_t3(res)
        lines.append(f"| {lbl} | ${sum(t['margin'] for t in cas):,.2f} "
                     f"| ${sum(t['pnl'] for t in cas):+,.2f} "
                     f"| {t3_roi(st['mr']):+.1f} % |")
    lines += ["", "*(le garde wallet-level de l'époque coupait les REBONDS "
              "d'août (+43 % baseline) ; la question : l'adaptateur "
              "signal-level évite-t-il ce piège ?)*"]

    # —— Q4'25-Q2'26 : coupé trop tôt ? ——
    lines += ["", "## Q4'25-Q2'26 (les bons régimes) : coupé trop tôt ?", "",
              "| Config | % jours OFF Q4'25 | Q1'26 | Q2'26 | Marge cascade "
              "Q4-Q2 | PnL cascade Q4-Q2 |", "|---|---|---|---|---|---|"]

    def cascade_good(res) -> list[dict]:
        return [t for t in res["trades"]
                if t["strategy"] == "cascade_10x"
                and q_of(t["entry_ts"]) in GOOD_Q]

    for lbl, res, st in ([("BASELINE ×1", base, stats["BASELINE"])]
                         + [(l, runs[l]["res"], stats[l]) for l in runs]):
        if lbl.startswith("BASELINE"):
            lines.append(f"| {lbl} | 0 % | 0 % | 0 % "
                         f"| ${sum(t['margin'] for t in cascade_good(res)):,.2f} "
                         f"| ${sum(t['pnl'] for t in cascade_good(res)):+,.2f} |")
            continue
        op = off_pct_per_quarter(*runs[lbl]["tl"], last_exit=last_exit)
        cg = cascade_good(res)
        lines.append(
            f"| {lbl} | {op.get('2025-Q4', 0):.0f} % "
            f"| {op.get('2026-Q1', 0):.0f} % | {op.get('2026-Q2', 0):.0f} % "
            f"| ${sum(t['margin'] for t in cg):,.2f} "
            f"| ${sum(t['pnl'] for t in cg):+,.2f} |")

    # —— extrapolation FORWARD (aujourd'hui) ——
    exp_now, n_now = rex.asof(last_exit)
    dn = datetime.fromtimestamp(last_exit / 10**9, tz=timezone.utc)
    state_now = {lbl: state_at(*tl, last_exit) for lbl, tl in timelines.items()}
    rec = ("RESTER EXPOSÉ ×1" if all(state_now.values())
           else "DÉRISKER le flux majors (×0.5-0.75) tant que l'espérance "
                "roulante reste sous le seuil")
    lines += ["", "## Extrapolation FORWARD (aujourd'hui)", "",
              f"- Dernier trade clôturé : {dn:%d/%m/%Y} — espérance roulante "
              f"90 j actuelle = **{exp_now:+.3f} %** ({n_now} trades clôturés).",
              f"- Seuil officiel TRAIN p25 = {thr_p25:+.3f} % → état : "
              f"{'**flux plein ×1**' if state_now['p25 TRAIN'] else '**régime mort — ×r**'} ;"
              f" alternative {THRESH_FLAT:.2f} % → "
              f"{'**×1**' if state_now['0.30 % plat'] else '**régime mort — ×r**'}.",
              f"- Trimestre en cours (T3, entrées) : {qmean.get('2026-Q3', float('nan')):+.2f} %.",
              f"- **Recommandation de l'adaptateur aujourd'hui : {rec}.**",
              "",
              "## VERDICT", "",
              f"- Harnais : {'OK — baseline bit-reproductible' if harness_ok else '✗ ÉCART vs $4,004.94'}.",
              "- Le critère (DD ≤ baseline, pire mois amélioré, ROI ≥ −15 %) "
              "tranche dans la table ci-dessus : la protection T3 ne vaut "
              "que si les bons régimes survivent.",
              "- Mécanique : l'adaptateur est LENT par construction (90 j de "
              "fenêtre + 30 j d'hystérésis) — il rate les V en échange de la "
              "robustesse ; c'est le choix opposé au garde wallet-level FAIL.",
              "",
              f"*Script : scripts/regime_adapter_test.py — espérance = corpus "
              f"du flux (signal), jamais le chemin du wallet.*"]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[adapt] baseline ${base['balance']:,.2f} (harnais "
          f"{'OK' if harness_ok else 'ÉCART'}), seuil p25 TRAIN {thr_p25:+.3f} %")
    for lbl, st in stats.items():
        print(f"[adapt] {lbl}: ${st['balance']:,.2f} ROI {st['roi']:+.0f} % "
              f"DD {st['dd']:.1f} % liq {st['liq']} pire {st['worst']:+.1f} % "
              f"rec {st['rec']:+.1f} % neg {st['neg']}")
    print(f"[adapt] forward : espérance 90j {exp_now:+.3f} % vs p25 "
          f"{thr_p25:+.3f} % → p25 {'×1' if state_now['p25 TRAIN'] else '×r'}, "
          f"plat {'×1' if state_now['0.30 % plat'] else '×r'}")
    print(f"[adapt] rapport : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
