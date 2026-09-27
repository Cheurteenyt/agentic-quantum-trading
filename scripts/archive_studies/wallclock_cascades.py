#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""WALL-CLOCK DES CASCADES — l'effet d'heure d'entrée (hint H2/H3, 27/09).

Le corpus : les events cascade majors du sim (anti_liq.collect_featured +
add_rolling_scores — les ts_ms sont des NANOSECONDES, leçon du projet :
conversion ×10⁻⁹ avant toute extraction d'heure). La question : l'heure
d'entrée UTC (feature cyclique) change-t-elle la QUALITÉ du short 24h ?
Le funding se règle à 00/08/16 UTC — les fenêtres de flush — et les flux
US/Europe ont leurs heures.

DISCIPLINE :
  - split train/val PAR LE TEMPS (70/30), l'heure est une feature, JAMAIS
    le split. Buckets 4h UTC jugés seulement si n ≥ 15 en TRAIN.
  - focus pré-enregistré : entrées dans la fenêtre funding (00/08/16 ±1h)
    vs le reste.
  - puissance honnête : test binomial exact par bucket + puissance
    two-proportion — avec ~160 events TRAIN sur 6 buckets, seul un effet
    ÉNORME est détectable ; la barre = gradient tient en VAL ET cohérent
    2025 vs 2026, sinon CONTEXTE.
  - un effet d'heure = SIZING modifier (×0.75/×1.0/×1.25 par bloc), JAMAIS
    un gate (la leçon). Multiplicateurs choisis sur TRAIN uniquement.
  - toute variante passe par la MACHINE 4 flux (--vol-spike ON), BLOC
    STATS vs baseline $4,004.94, garde-fou composé-des-mois.

  .venv/bin/python scripts/wallclock_cascades.py            # analyse
  .venv/bin/python scripts/wallclock_cascades.py --machine  # + runs sizing
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, funding_hourly_all, monthly_rows, run_stack)
from scripts.the_machine import collect_meme  # noqa: E402

REPORTS = ROOT / "reports"
LEV = 10                                   # le levier du flux cascade majors
FEES_MARGIN_PCT = MAKER_RT * LEV / 100     # 4 bps RT × 10 = 0.40 % de marge
_FUND_HOURS = (0, 8, 16)                   # les règlements de funding Aster


def hour_utc(ts_ns: int) -> int:
    """L'heure d'entrée UTC — les ts sont des NS (leçon ts_ms : ×10⁻⁹)."""
    return datetime.fromtimestamp(ts_ns / 10**9, tz=timezone.utc).hour


def in_funding_window(h: int) -> bool:
    """00/08/16 UTC ± 1h — le flush de funding."""
    return any((h - f) % 24 <= 1 or (f - h) % 24 <= 1 for f in _FUND_HOURS)


def binom_two_sided(k: int, n: int, p0: float) -> float:
    """Le p-value binomial exact two-sided (sans scipy)."""
    if n == 0:
        return 1.0
    pmf = lambda k: math.comb(n, k) * p0 ** k * (1 - p0) ** (n - k)
    pk = pmf(k)
    tot = sum(pmf(i) for i in range(n + 1) if pmf(i) <= pk * (1 + 1e-9))
    return min(1.0, tot)


def mdd_detectable(n1: int, n2: int, p: float, alpha: float = 0.05,
                   power: float = 0.80) -> float:
    """Le delta de proportion minimal détectable (two-proportion z)."""
    za, zb = 1.959964, 0.841621
    return (za * math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
            + zb * math.sqrt(p * (1 - p) / n1 + p * (1 - p) / n2))


def stats_block(evs: list[dict]) -> dict:
    """WR, MAE moyen, taux de liq, EV marge 10x (%/trade, ex-funding)."""
    n = len(evs)
    if n == 0:
        return {"n": 0}
    ret = np.array([e["price_ret_short"] for e in evs])
    mae = np.array([e["mae_adverse"] for e in evs])
    liq = np.array([e["liq"] for e in evs], dtype=bool)
    wr = float((ret > 0).mean() * 100)
    return {"n": n, "wr": wr, "mae": float(mae.mean()),
            "liq": float(liq.mean() * 100),
            "ev": float(ret.mean()) * LEV - FEES_MARGIN_PCT,
            "ret": float(ret.mean())}


def build_corpus():
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    add_rolling_scores(events)
    # la vérification d'unité (leçon ts_ms) : le champ hour doit rejouer
    for e in events:
        assert hour_utc(e["ts_ms"]) == e["hour"], f"unité ts ? {e['ts_ms']}"
    return events


def gradient_map(events: list[dict]) -> tuple[list, list]:
    """Les 6 buckets 4h UTC × TRAIN/VAL + la fenêtre funding + les années."""
    k = int(len(events) * 0.7)
    train, val = events[:k], events[k:]
    rows = []
    for b in range(6):
        t = stats_block([e for e in train if e["hour"] // 4 == b])
        v = stats_block([e for e in val if e["hour"] // 4 == b])
        # binomial exact TRAIN : le WR du bucket vs le WR global TRAIN
        tr = [e for e in train if e["hour"] // 4 == b]
        p0 = np.mean([e["price_ret_short"] > 0 for e in train])
        kw = sum(e["price_ret_short"] > 0 for e in tr)
        p_wr = binom_two_sided(kw, len(tr), p0) if tr else 1.0
        rows.append({"block": b, "train": t, "val": v, "p_train": p_wr})
    # le focus pré-enregistré : fenêtre funding (00/08/16 ±1h) vs reste
    focus = {}
    for name, split in (("TRAIN", train), ("VAL", val)):
        w = stats_block([e for e in split if in_funding_window(e["hour"])])
        o = stats_block([e for e in split if not in_funding_window(e["hour"])])
        focus[name] = {"win": w, "out": o}
    # la robustesse année par année (confondu avec le split — noté)
    years = {}
    for e in events:
        y = datetime.fromtimestamp(e["ts_ms"] / 10**9,
                                   tz=timezone.utc).year
        years.setdefault(y, []).append(e)
    yrows = []
    for y in sorted(years):
        evy = years[y]
        p0y = float(np.mean([e["price_ret_short"] > 0 for e in evy]))
        row = {"year": y, "n": len(evy), "blocks": []}
        for b in range(6):
            eb = [e for e in evy if e["hour"] // 4 == b]
            row["blocks"].append(stats_block(eb) | {
                "p": binom_two_sided(sum(e["price_ret_short"] > 0
                                         for e in eb), len(eb), p0y)
                if eb else 1.0})
        yrows.append(row)
    return rows, focus, yrows, train, val


def gradient_verdict(rows: list, focus: dict, yrows: list) -> tuple[str, list]:
    """La barre haute : gradient en TRAIN, direction tenue en VAL,
    cohérent entre les années. Sinon CONTEXTE."""
    judged = [r for r in rows if r["train"].get("n", 0) >= 15]
    if len(judged) < 3:
        return "CONTEXTE (trop peu de buckets jugables)", []
    evs_tr = [r["train"]["ev"] for r in judged]
    # le gradient TRAIN : l'étendue EV entre buckets jugés
    spread = max(evs_tr) - min(evs_tr)
    # la direction en VAL : le rang Spearman TRAIN vs VAL sur les buckets
    # jugables des deux côtés
    both = [r for r in judged if r["val"].get("n", 0) >= 8]
    if len(both) >= 3:
        a = np.argsort(np.argsort([r["train"]["ev"] for r in both]))
        b = np.argsort(np.argsort([r["val"]["ev"] for r in both]))
        rho = float(np.corrcoef(a, b)[0, 1])
    else:
        rho = float("nan")
    # l'année : rangs 2025 vs 2026 sur les buckets ≥ 8 des deux
    rho_y = float("nan")
    if len(yrows) == 2:
        bb = [i for i in range(6)
              if yrows[0]["blocks"][i].get("n", 0) >= 8
              and yrows[1]["blocks"][i].get("n", 0) >= 8]
        if len(bb) >= 3:
            a = np.argsort(np.argsort([yrows[0]["blocks"][i]["ev"] for i in bb]))
            b = np.argsort(np.argsort([yrows[1]["blocks"][i]["ev"] for i in bb]))
            rho_y = float(np.corrcoef(a, b)[0, 1])
    ok_val = np.isfinite(rho) and rho >= 0.4
    ok_year = (not np.isfinite(rho_y)) or rho_y >= 0.0
    # le focus funding : la direction doit être la même TRAIN et VAL
    dw_tr = focus["TRAIN"]["win"]["ev"] - focus["TRAIN"]["out"]["ev"]
    dw_va = focus["VAL"]["win"]["ev"] - focus["VAL"]["out"]["ev"]
    ok_focus = (np.sign(dw_tr) == np.sign(dw_va)) if (
        np.isfinite(dw_tr) and np.isfinite(dw_va)) else False
    sig = [r for r in judged if r["p_train"] < 0.10]
    if ok_val and ok_year and ok_focus and spread > 2.0 and sig:
        verdict = (f"PASS — spread EV {spread:.1f} pts, rho VAL {rho:.2f}, "
                   f"rho années {rho_y:.2f}, focus funding cohérent "
                   f"({dw_tr:+.1f} / {dw_va:+.1f} pts)")
        factors = sizing_factors(rows)
    else:
        why = []
        if not ok_val:
            why.append(f"rho VAL {rho:.2f}")
        if not ok_year:
            why.append(f"rho années {rho_y:.2f}")
        if not ok_focus:
            why.append(f"focus funding incohérent ({dw_tr:+.1f}/{dw_va:+.1f})")
        if spread <= 2.0:
            why.append(f"spread EV {spread:.1f} pt ≤ 2")
        if not sig:
            why.append("aucun bucket p<0.10")
        verdict = "CONTEXTE — " + " ; ".join(why)
        factors = []
    return verdict, factors


def sizing_factors(rows: list) -> list[tuple[int, float]]:
    """Les multiplicateurs TRAIN-only : top-2 EV → ×1.25, bottom-2 → ×0.75,
    buckets non jugables (n<15) → ×1.0 (jamais modifiés sur du creux)."""
    judged = [r for r in rows if r["train"].get("n", 0) >= 15]
    if len(judged) < 4:
        return []
    order = sorted(judged, key=lambda r: r["train"]["ev"])
    f = {r["block"]: 1.0 for r in rows}
    f[order[0]["block"]] = 0.75
    if len(order) > 1:
        f[order[1]["block"]] = 0.75
    f[order[-1]["block"]] = 1.25
    if len(order) > 2:
        f[order[-2]["block"]] = 1.25
    return [(b, f[b]) for b in range(6)]


# ————————————————————————————— LA MACHINE —————————————————————————————

def run_machine(factor_fn, tag: str) -> dict:
    """La réplication bit-exacte de the_machine --vol-spike (4 flux), avec
    un multiplicateur de sizing SIZING-ONLY sur le flux cascade_10x."""
    from scripts.full_arsenal_2 import collect as collect_arsenal
    from scripts.p5_frequency_test import collect_vol_spike
    from scripts.stacked_portfolio import TAKER_RT

    con = sqlite3.connect(KDB)
    fh = funding_hourly_all()
    fh_raw = pd_read_funding(con)
    regime = btc_regime_series()

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
    for e in gated:
        e["lev"] = 10

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

    spike = collect_vol_spike(con, hold=6)
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    med_spike = float(np.median([e["atr_pct"] for e in spike]))

    _K = 0.89
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
    con.close()

    all_ev = sorted(gated + meme + surv + spike, key=lambda e: e["ts_ms"])

    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            f = factor_fn(e)
            s0 = min(max(0.24 * _K * (e["atr_pct"] / med_majors),
                         0.08 * _K), 0.40 * _K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5 * f, 0.50 * _K)
            return min(max(s0 * f, 0.05 * _K), 0.50 * _K)
        if s == "cascade_meme":
            return min(max(0.10 * _K * (e["atr_pct"] / med_meme),
                           0.02 * _K), 0.30 * _K)
        if s == "vol_spike_6h":
            return min(max(0.10 * _K * (e["atr_pct"] / med_spike),
                           0.02 * _K), 0.30 * _K)
        return 0.20 * _K

    r = run_stack(all_ev, CAPITAL, machine_fn, fh)
    mr = monthly_rows(r["trades"], CAPITAL)
    prod, sum_pnl = 1.0, 0.0
    for x in mr:
        prod *= 1 + x["roi"] / 100
        sum_pnl += x["pnl"]
    gap_c = abs(prod - r["balance"] / CAPITAL)
    gap_p = abs(sum_pnl - (r["balance"] - CAPITAL))
    rois = [x["roi"] for x in mr]
    out = {"tag": tag, "bal": r["balance"],
           "roi": (r["balance"] / CAPITAL - 1) * 100,
           "dd": r["max_dd"], "liq": r["n_liq"], "n": r["n"],
           "wr": r["n_wins"] / max(r["n"], 1) * 100,
           "neg": sum(1 for x in rois if x < 0), "rec": max(rois),
           "worst": min(rois), "mean_m": float(np.mean(rois)),
           "gap_c": gap_c, "gap_p": gap_p, "mr": mr}
    print(f"[machine:{tag}] ${out['bal']:,.2f} ({out['roi']:+.0f} %/an), "
          f"DD {out['dd']:.1f} %, liq {out['liq']}, {out['n']} trades, "
          f"WR {out['wr']:.1f} %, {out['neg']} mois négatifs, "
          f"composé {gap_c*100:.3f} %")
    return out


def pd_read_funding(con):
    import pandas as pd
    return pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)


# ————————————————————————————— LE RAPPORT —————————————————————————————

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--machine", action="store_true",
                    help="exécuter aussi les runs sizing machine 4 flux")
    args = ap.parse_args()

    events = build_corpus()
    n = len(events)
    rows, focus, yrows, train, val = gradient_map(events)
    verdict, factors = gradient_verdict(rows, focus, yrows)

    L = ["# WALL-CLOCK DES CASCADES — l'effet d'heure d'entrée",
         f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {n} events "
         f"cascade majors (sim, hold 24h, sélection séquentielle), "
         f"split TRAIN {len(train)}/VAL {len(val)} PAR LE TEMPS.", "",
         "Le hint H2/H3 : pivoter vers le wall-clock des cascades. Le "
         "funding Aster se règle à 00/08/16 UTC — un effet d'heure serait "
         "un SIZING modifier, jamais un gate.", "",
         "## LA GRADIENT MAP — buckets 4h UTC", "",
         "| Bloc UTC | TRAIN n | WR | MAE | Liq | EV marge 10x | p (binomial) "
         "| VAL n | WR | MAE | Liq | EV |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        t, v = r["train"], r["val"]
        f = lambda d, k: f"{d[k]:.1f}" if d.get("n") else "—"
        L.append(
            f"| {r['block']*4:02d}h–{r['block']*4+3:02d}h | {t.get('n',0)} "
            f"| {f(t,'wr')} % | {f(t,'mae')} % | {f(t,'liq')} % "
            f"| {f(t,'ev')} % | {r['p_train']:.3f} | {v.get('n',0)} "
            f"| {f(v,'wr')} % | {f(v,'mae')} % | {f(v,'liq')} % "
            f"| {f(v,'ev')} % |")
    L += ["", "EV marge = mean(ret_short)×10 − 0.40 % (frais maker 10x), "
              "ex-funding. Buckets jugés si n ≥ 15 TRAIN.", "",
          "## LE FOCUS PRÉ-ENREGISTRÉ — fenêtre funding (00/08/16 ±1h)", "",
          "| Split | Fenêtre n | WR | EV | Reste n | WR | EV | Δ EV |",
          "|---|---|---|---|---|---|---|---|"]
    for name in ("TRAIN", "VAL"):
        w, o = focus[name]["win"], focus[name]["out"]
        d = (w["ev"] - o["ev"]) if w.get("n") and o.get("n") else float("nan")
        L.append(f"| {name} | {w.get('n',0)} | {w.get('wr',0):.1f} % "
                 f"| {w.get('ev',0):+.2f} % | {o.get('n',0)} "
                 f"| {o.get('wr',0):.1f} % | {o.get('ev',0):+.2f} % "
                 f"| {d:+.2f} pts |")
    L += ["", "## LA ROBUSTESSE — années et puissance honnête", ""]
    p_glob = float(np.mean([e["price_ret_short"] > 0 for e in train]))
    for y in yrows:
        parts = [f"{i*4:02d}h n={y['blocks'][i].get('n',0)} "
                 f"EV {y['blocks'][i].get('ev',0):+.1f}"
                 for i in range(6) if y["blocks"][i].get("n")]
        L.append(f"- **{y['year']}** (n={y['n']}) : " + ", ".join(parts))
    n1 = max(r["train"]["n"] for r in rows)
    d_min = mdd_detectable(n1, len(train) - n1, p_glob) * 100
    L += ["",
          f"Puissance honnête : à n≈{n1} par bucket vs {len(train)-n1}, "
          f"alpha 5 %, puissance 80 %, le delta de WR minimal détectable "
          f"est ≈ ±{d_min:.0f} pts — seul un effet ÉNORME est détectable "
          f"avec {n} events. Le test binomial exact par bucket "
          f"(TRAIN, vs WR global {p_glob*100:.0f} %) figure dans la table.",
          "",
          f"## LE VERDICT — {verdict}", ""]
    if factors:
        L.append("Sizing TRAIN-only par bloc (SIZING modifier, jamais un "
                 "gate) : "
                 + ", ".join(f"B{b*4:02d}h ×{f}" for b, f in factors) + ".")
        L.append("")
    if args.machine and factors:
        base = run_machine(lambda e: 1.0, "baseline")
        fmap = dict(factors)
        var = run_machine(
            lambda e: fmap.get(hour_utc(e["ts_ms"]) // 4, 1.0),
            "wallclock")
        crit = (var["roi"] >= base["roi"] and var["dd"] <= base["dd"]
                and var["neg"] <= base["neg"]
                and var["gap_c"] < 0.005 and var["liq"] == 0)
        L += ["", "## LA MACHINE 4 FLUX (--vol-spike ON) — le sizing par bloc",
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
              f"Critère pré-enregistré (vs baseline) : ROI ≥ ET DD ≤ ET "
              f"mois négatifs ≤, 0 liq, garde-fou composé ~0 → "
              f"**{'PASS' if crit else 'FAIL'}**.",
              "", "### La table mensuelle (variante wallclock)", "",
              "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
        for x in var["mr"]:
            L.append(f"| {x['month']} | {x['n']} | "
                     f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                     f"| {x['roi']:+.1f} % |")
    elif not factors:
        L += ["", "Pas de run machine : la barre (gradient VAL + années + "
                  "focus) n'est pas tenue — aucun sizing à tester. Le "
                  "wall-clock des cascades va au registre en CONTEXTE."]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "wallclock-cascades-2026-09-27.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[wallclock] rapport → {out}")
    print(f"[wallclock] VERDICT : {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
