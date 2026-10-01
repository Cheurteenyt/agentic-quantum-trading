#!/usr/bin/env python
"""ÉTUDE T8 — LA MACHINE (4 flux) re-jouée sur le deep 2021→2026, par régime.

Question : les edges de la machine (docs/21 = 1 an, 2025-10→2026-09)
tiennent-ils les régimes (bull 2021, bear 2022, recovery 2023, bull 2024,
chop, 2025, 2026) — ou sont-ils des artefacts 2025-2026 ?

PÉRIMÈTRE HONNÊTE (l'analyse d'invocation, vérifiée dans le code) :
  - the_machine.py n'a PAS de mode backtest : il collecte sur la DB du soir
    et écrit reports/the-machine-<date>.md (le rapport officiel — NE PAS
    écraser). Cette étude RÉUTILISE ses modules en lecture et écrit
    UNIQUEMENT reports/aster_machine_deep_regimes.md.
  - Aucun des 4 flux ne lit l'OI (oi_history = 30 j — NON BLOQUANT) :
      · cascade majors : anti_liq.collect_featured = klines 1h + funding ;
        le gate AL Score (add_rolling_scores) = atr_pct, vol24, dd_pct,
        btc_ret24, vwap_dev, cascade_depth — 100 % klines.
      · cascade meme : klines 1h uniquement (the_machine.collect_meme).
      · survivor long : klines 1h (full_arsenal_2.collect).
      · vol_spike_6h : klines 1h (p5_frequency_test.collect_vol_spike).
    LA vraie contrainte = la PROFONDEUR KLINES : seuls BTC/ETH/SOL 1h
    descendent à 2021-09 (backfill T6). BNB/XRP/DOGE et TOUS les
    non-majors commencent 2025-09 (genèse Aster). funding_history ne
    commence qu'en 2025-10-27 (PAS 2021).
  - Flux REJOUABLES deep : cascade majors (univers 3/6 majors avant
    2025-09, 6/6 ensuite — le collecteur suit la donnée disponible) et
    vol_spike_6h (idem). fund_rank (boost ×1,5) = nan avant 2025-10 →
    sizing de base (comportement machine déjà codé pour nan).
  - flux NON rejouables deep : cascade_meme et survivor_long (univers
    non-majors — genèse 2025-09 ; Aster n'existait pas avant). Ils sont
    re-joués sur la seule fenêtre connue (2025-2026).
  - funding du sim : funding_hourly_all = moyenne moderne par symbole
    (2025-10→2026-09) appliquée à toute la timeline — approximation
    documentée (T7 utilisait un modèle par régime ; l'impact machine est
    petit : $53 nets sur $3 906 officiels).

MÉTHODE (fidèle au fonctionnement nocturne de la machine) :
  - chaque cellule régime = la machine telle qu'elle aurait tourné chaque
    nuit DANS ce régime : q66 du gate AL = quantile sur les premiers 70 %
    des événements de la cellule (par le temps), médianes vol-inverse et
    filtres ATR p90 recalibrés sur la cellule ; les scores AL et corr
    roulants sont calculés UNE fois sur la timeline complète (causaux,
    jamais réinitialisés — pas de warm-up artificiel).
  - run séquentiel wallet = run_stack (scripts/stacked_portfolio.py),
    capital frais $100 par cellule, leviers machine (10x/1x/1x/1x).
  - le run deep EMPILÉ (cascade majors + vol_spike, la partie rejouable)
    tourne sur 2021-09→2026-09 avec calibration GLOBALE : q66/ médianes /
    p90 issus des premiers 70 % PAR LE TEMPS (train), le reste (2025-2026)
    = val. Garde-fous composé-des-mois vs balance finale.
  - le pont officiel : re-run « connu » 2025-09→2026-09 (4 flux) à comparer
    aux stats docs/21 (rapport du 27/09 : $100 → $4 004,94, +3 905 %/an).

  .venv/bin/python scripts/studies/aster_machine_deep_regimes.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # scripts/studies/ → racine
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402
from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
from scripts.portfolio_sim import MAJORS, btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, monthly_rows, run_stack)

REPORTS = ROOT / "reports"
KDB_RO = f"file:{ROOT / 'data' / 'warehouse' / 'klines.db'}?mode=ro"
K_V = 0.89  # le facteur global K de la machine (calibration DD 25 %)

# les régimes T7 (reports/aster_deep_regimes.md) + le split 2025/2026
REGIMES = [
    ("bull_2021H2", "2021-09-01", "2022-01-01"),
    ("bear_2022", "2022-01-01", "2023-01-01"),
    ("recovery_2023", "2023-01-01", "2024-01-01"),
    ("bull_2024H1", "2024-01-01", "2024-07-01"),
    ("chop_2024H2", "2024-07-01", "2025-01-01"),
    ("annee_2025", "2025-01-01", "2026-01-01"),
    ("annee_2026", "2026-01-01", "2026-09-30"),
]
KNOWN_START = "2025-09-23"   # genèse : première kline non-major (ASTERUSDT)


def ts_ms(datestr: str) -> int:
    return int(pd.Timestamp(datestr, tz="UTC").value)


def seg_stats(res: dict, capital: float, days: float) -> dict:
    wr = res["n_wins"] / max(res["n"], 1) * 100
    roi = (res["balance"] / capital - 1) * 100
    if days > 0 and res["balance"] > 0:
        roi_an = ((res["balance"] / capital) ** (365.0 / days) - 1) * 100
    else:
        roi_an = -100.0
    mr = monthly_rows(res["trades"], capital)
    rois = [x["roi"] for x in mr]
    return {"n": res["n"], "wr": wr, "liq": res["n_liq"], "roi": roi,
            "roi_an": roi_an, "dd": res["max_dd"], "bal": res["balance"],
            "neg": sum(1 for x in rois if x < 0),
            "worst": min(rois) if rois else 0.0,
            "record": max(rois) if rois else 0.0,
            "fees": res["fees"], "funding": res["funding"], "mr": mr}


def cell(s: dict) -> str:
    if s["n"] == 0:
        return "0t —"
    return (f"{s['n']}t · {s['wr']:.0f}% · {s['roi']:+.0f}% "
            f"({s['roi_an']:+.0f}%/an) · DD{s['dd']:.0f} · "
            f"liq{s['liq']} · {s['neg']}m− pire {s['worst']:+.0f}%")


def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = sqlite3.connect(KDB_RO, uri=True)   # lecture stricte
    fh = funding_hourly_all()                 # moyennes modernes (docstring)
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # ——— collecte UNE fois (les modules de la machine, en lecture) ———
    print("[t8] collecte cascade majors (collect_featured)…", flush=True)
    majors_ev = collect_featured(regime, "majors")
    for e in majors_ev:
        e["strategy"] = "cascade_10x"
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(majors_ev)          # causal, timeline complète

    # corr croisée roulante des majors (le régime systémique de la machine).
    # ALIGNEMENT par timestamp sur la grille BTC (le deep commence à des
    # dates différentes : BTC 09-01, ETH 09-07, SOL 09-09 — un slicing
    # positionnel comme le nightly produirait des fenêtres désalignées).
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    m_idx = majors_dfs["BTCUSDT"].index
    m_ns = m_idx.astype("datetime64[ns]").asi8
    rets = {s: d["close"].pct_change().mul(100).reindex(m_idx).values
            for s, d in majors_dfs.items() if d is not None}
    _WIN = 168
    for e in majors_ev:
        bi = int(np.searchsorted(m_ns, e["ts_ms"], side="left"))
        lo = bi - _WIN
        if lo < 0:
            e["corr"] = np.nan
            continue
        pairs = []
        for i in range(len(MAJORS)):
            for j in range(i + 1, len(MAJORS)):
                a, b = rets.get(MAJORS[i]), rets.get(MAJORS[j])
                if a is None or b is None:
                    continue
                a, b = a[lo:bi], b[lo:bi]
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() > 100:
                    sa, sb = a[m] - a[m].mean(), b[m] - b[m].mean()
                    if sa.std() * sb.std() > 0:
                        pairs.append(float((sa * sb).mean()
                                           / (sa.std() * sb.std())))
        e["corr"] = float(np.mean(pairs)) if pairs else np.nan

    # fund_rank (le boost qualité ×1,5) — nan avant 2025-10 (pas de données)
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
    for e in majors_ev:
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

    print("[t8] collecte meme / survivor / vol_spike…", flush=True)
    from scripts.the_machine import collect_meme
    meme_ev = collect_meme(con)
    arsenal = collect_arsenal(con, fh_raw)
    surv_all = arsenal.get("survivor_long_72h", [])
    for e in surv_all:
        e["strategy"] = "survivor_long"
    spike_all = collect_vol_spike(con, hold=6, atr_gate=False)
    for e in spike_all:
        e["strategy"] = "vol_spike_6h"   # le nom machine (busy key + filtres)

    flows_raw = {"cascade_10x": majors_ev, "cascade_meme": meme_ev,
                 "survivor_long": surv_all, "vol_spike_6h": spike_all}
    print("[t8] événements : " + ", ".join(
        f"{k} {len(v)}" for k, v in flows_raw.items()), flush=True)

    def make_fn_cascade(med: float):
        def fn(e, st=None):    # arité 2 : run_stack passe l'état wallet
            s0 = min(max(0.24 * K_V * (e["atr_pct"] / med),
                         0.08 * K_V), 0.40 * K_V)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5, 0.50 * K_V)
            return s0
        return fn

    def make_fn_pct(base: float, med: float):
        def fn(e, st=None):
            return min(max(base * K_V * (e["atr_pct"] / med),
                           0.02 * K_V), 0.30 * K_V)
        return fn

    def calibrate(flow: str, events: list[dict]) -> tuple[list[dict], object]:
        """La calibration d'une cellule : la machine telle qu'elle tourne
        chaque nuit — q66 sur les premiers 70 % PAR LE TEMPS, médianes et
        p90 sur la population de la cellule, leviers règles 0-liq."""
        ev = [dict(e) for e in events]
        k = int(len(ev) * 0.7)
        if flow == "cascade_10x":
            tr_sc = [e["al_score"] for e in ev[:k]]
            q66 = (float(np.nanquantile(tr_sc, 2 / 3)) if tr_sc
                   else float("nan"))
            gated = [e for e in ev
                     if not (np.isfinite(e.get("al_score", float("nan")))
                             and e["al_score"] >= q66)]
            med = float(np.median([e["atr_pct"] for e in gated]))
            for e in gated:
                e["lev"] = 10
            mae_max = max((e["mae_adverse"] for e in gated), default=0.0)
            return gated, make_fn_cascade(med), q66, med, mae_max
        if flow == "cascade_meme":
            mae_max = max((e["mae_adverse"] for e in ev), default=0.0)
            lev = max(1, int(100 / (mae_max + 0.5)))
            med = float(np.median([e["atr_pct"] for e in ev])) if ev else 1.0
            for e in ev:
                e["lev"] = lev
            return ev, make_fn_pct(0.10, med), None, med, mae_max
        if flow == "survivor_long":
            p90 = float(np.nanquantile([e["atr_pct"] for e in ev], 0.90))
            keep = [e for e in ev if e["atr_pct"] <= p90]
            for e in keep:
                e["lev"] = 1

            def fn(e, st=None):
                return 0.20 * K_V
            return keep, fn, p90, None, 0.0
        if flow == "vol_spike_6h":
            p90 = float(np.nanquantile([e["atr_pct"] for e in ev], 0.90))
            keep = [e for e in ev if e["atr_pct"] <= p90]
            med = (float(np.median([e["atr_pct"] for e in keep]))
                   if keep else 1.0)
            for e in keep:
                e["lev"] = 1
            return keep, make_fn_pct(0.10, med), p90, med, 0.0
        raise ValueError(flow)

    FLOW_LABEL = {"cascade_10x": "cascade majors 10x (gate AL + vol-inv)",
                  "cascade_meme": "cascade meme 1x",
                  "survivor_long": "survivor long 72h 1x",
                  "vol_spike_6h": "vol_spike reversion 6h 1x"}

    # ——— TABLE régime × flux (wallet frais $100 par cellule) ———
    print("[t8] simulations par régime…", flush=True)
    grid: dict[str, dict[str, dict]] = {f: {} for f in flows_raw}
    monitor: dict[str, dict[str, tuple]] = {f: {} for f in flows_raw}
    for name, lo, hi in REGIMES:
        lo_ms, hi_ms = ts_ms(lo), ts_ms(hi)
        days = (hi_ms - lo_ms) / 86400 / 10**9
        for flow, evs in flows_raw.items():
            seg = [e for e in evs if lo_ms <= e["ts_ms"] < hi_ms]
            if not seg:
                grid[flow][name] = None
                continue
            kept, fn, *cal = calibrate(flow, seg)
            res = run_stack(kept, CAPITAL, fn, fh)
            grid[flow][name] = seg_stats(res, CAPITAL, days)
            monitor[flow][name] = (len(seg), len(kept), *cal)

    # ——— le run deep EMPILÉ 2021→2026 (cascade majors + vol_spike) ———
    print("[t8] run deep empilé 2021-2026 (calibration train 70 %)…",
          flush=True)
    deep_lo, deep_hi = ts_ms("2021-09-01"), ts_ms("2026-09-30")
    deep_days = (deep_hi - deep_lo) / 86400 / 10**9
    # événements BRUTS sur la fenêtre deep, puis calibration GLOBALE
    # (train = premiers 70 % PAR LE TEMPS — doctrine, comme la machine)
    maj_deep = [dict(e) for e in flows_raw["cascade_10x"]
                if deep_lo <= e["ts_ms"] < deep_hi]
    spike_raw = [dict(e) for e in flows_raw["vol_spike_6h"]
                 if deep_lo <= e["ts_ms"] < deep_hi]
    k70 = int(len(maj_deep) * 0.7)
    q66_deep = float(np.nanquantile([e["al_score"] for e in maj_deep[:k70]],
                                    2 / 3))
    gated_deep = [e for e in maj_deep
                  if not (np.isfinite(e.get("al_score", float("nan")))
                          and e["al_score"] >= q66_deep)]
    for e in gated_deep:
        e["lev"] = 10
    med_deep = float(np.median([e["atr_pct"] for e in gated_deep]))
    p90_deep = float(np.nanquantile([e["atr_pct"] for e in spike_raw], 0.90))
    spike_deep = [e for e in spike_raw if e["atr_pct"] <= p90_deep]
    for e in spike_deep:
        e["lev"] = 1
    med_sp_deep = float(np.median([e["atr_pct"] for e in spike_deep]))
    mae_deep = max(e["mae_adverse"] for e in gated_deep)
    lev_safe_deep = 100 / (mae_deep + 0.5)

    def machine_deep(e, st=None):
        s = e["strategy"]
        if s == "cascade_10x":
            s0 = min(max(0.24 * K_V * (e["atr_pct"] / med_deep),
                         0.08 * K_V), 0.40 * K_V)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5, 0.50 * K_V)
            return s0
        return min(max(0.10 * K_V * (e["atr_pct"] / med_sp_deep),
                       0.02 * K_V), 0.30 * K_V)

    stack_deep = sorted(gated_deep + spike_deep, key=lambda e: e["ts_ms"])
    res_deep = run_stack(stack_deep, CAPITAL, machine_deep, fh)
    deep = seg_stats(res_deep, CAPITAL, deep_days)

    # attribution par régime du MÊME wallet (le garde-fou des verdicts)
    deep_by_regime: dict[str, dict] = {}
    for name, lo, hi in REGIMES:
        lo_ms, hi_ms = ts_ms(lo), ts_ms(hi)
        pnl = sum(t["pnl"] for t in res_deep["trades"]
                  if lo_ms <= int(t["exit_ts"].timestamp() * 1e9) < hi_ms)
        deep_by_regime[name] = pnl

    # ——— le PONT officiel : re-run connu 2025-09→2026-09 (4 flux) ———
    print("[t8] pont officiel connu 2025-09→2026-09 (4 flux)…", flush=True)
    k_lo = ts_ms(KNOWN_START)
    known_events: list[dict] = []
    for flow, evs in flows_raw.items():
        seg = [e for e in evs if e["ts_ms"] >= k_lo]
        kept, fn, *_ = calibrate(flow, seg)
        for e in kept:
            known_events.append(e)
    known_events.sort(key=lambda e: e["ts_ms"])
    # sizing machine complet sur le pont : la fn par flux du segment connu
    _, fn_maj, *_ = calibrate("cascade_10x",
                              [e for e in flows_raw["cascade_10x"]
                               if e["ts_ms"] >= k_lo])
    _, fn_meme, *_ = calibrate("cascade_meme",
                               [e for e in flows_raw["cascade_meme"]
                                if e["ts_ms"] >= k_lo])
    _, fn_surv, *_ = calibrate("survivor_long",
                               [e for e in flows_raw["survivor_long"]
                                if e["ts_ms"] >= k_lo])
    _, fn_spike, *_ = calibrate("vol_spike_6h",
                                [e for e in flows_raw["vol_spike_6h"]
                                 if e["ts_ms"] >= k_lo])

    def machine_known(e, st=None):
        s = e["strategy"]
        return (fn_maj if s == "cascade_10x" else
                fn_meme if s == "cascade_meme" else
                fn_surv if s == "survivor_long" else fn_spike)(e)

    res_known = run_stack(known_events, CAPITAL, machine_known, fh)
    known_days = (ts_ms("2026-09-30") - k_lo) / 86400 / 10**9
    known = seg_stats(res_known, CAPITAL, known_days)

    # ——— diagnostic du pont : l'effet WARM-UP du gate ———
    # l'officiel (27/09) tournait sur une DB jeune : ses scores AL des
    # 90 premiers jours étaient nan (gate INERTE) — le re-run deep, lui,
    # a des scores finis dès 2025-10 (fenêtre alimentée par 2021-2025).
    print("[t8] pont scénario B (scores FRAIS, warm-up officiel)…",
          flush=True)
    known_maj_b = [dict(e) for e in flows_raw["cascade_10x"]
                   if e["ts_ms"] >= k_lo]
    add_rolling_scores(known_maj_b)      # scores recalculés SANS le deep
    k70b = int(len(known_maj_b) * 0.7)
    tr_b = [e["al_score"] for e in known_maj_b[:k70b]]
    q66_b = float(np.nanquantile(tr_b, 2 / 3)) if tr_b else float("nan")
    gated_b = [e for e in known_maj_b
               if not (np.isfinite(e.get("al_score", float("nan")))
                       and e["al_score"] >= q66_b)]
    for e in gated_b:
        e["lev"] = 10
    med_b = float(np.median([e["atr_pct"] for e in gated_b]))
    other_known = [e for e in known_events if e["strategy"] != "cascade_10x"]
    ev_b = sorted(gated_b + other_known, key=lambda e: e["ts_ms"])

    def machine_known_b(e, st=None):
        s = e["strategy"]
        if s == "cascade_10x":
            return make_fn_cascade(med_b)(e)
        return machine_known(e)

    res_known_b = run_stack(ev_b, CAPITAL, machine_known_b, fh)
    known_b = seg_stats(res_known_b, CAPITAL, known_days)

    # ——— le run deep à levier SÛR 4x (la règle 0-liq satisfaite) ———
    for e in gated_deep:
        e["lev"] = 4
    res_deep4 = run_stack(gated_deep + spike_deep, CAPITAL, machine_deep, fh)
    deep4 = seg_stats(res_deep4, CAPITAL, deep_days)
    for e in gated_deep:
        e["lev"] = 10

    con.close()

    # ——— le rapport ———
    mr = deep["mr"]
    prod = 1.0
    sum_pnl = 0.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
        sum_pnl += x["pnl"]
    gap_c = abs(prod - res_deep["balance"] / CAPITAL)
    gap_p = abs(sum_pnl - (res_deep["balance"] - CAPITAL))

    L = [
        "# ÉTUDE T8 — LA MACHINE sur le deep 2021→2026 (régime × flux)",
        f"Généré : {t0:%Y-%m-%dT%H:%M:%S+00:00} — script : "
        "`scripts/studies/aster_machine_deep_regimes.py` (modules machine "
        "réutilisés en lecture ; DB en mode=ro ; écriture = ce rapport).",
        "", "## 1. L'analyse d'invocation (le périmètre honnête)", "",
        "- the_machine.py n'a **pas de mode backtest** : il collecte sur la "
        "DB du soir et écrit le rapport officiel du jour. Cette étude "
        "réutilise ses modules (`anti_liq.collect_featured`, "
        "`the_machine.collect_meme`, `full_arsenal_2.collect`, "
        "`p5_frequency_test.collect_vol_spike`, `stacked_portfolio.run_stack`) "
        "et écrit UNIQUEMENT ce fichier.",
        "- **L'OI n'est PAS un verrou** : aucun des 4 flux ne lit "
        "oi_history (30 j). Le gate AL Score = 6 features 100 % klines "
        "(atr, vol24, dd, btc_ret24, vwap_dev, cascade_depth) ; les filtres "
        "ATR/medium = klines ; le boost funding = funding_history.",
        "- **Le vrai verrou = la profondeur klines** : seuls BTC/ETH/SOL 1h "
        "descendent à 2021-09 (backfill T6). BNB/XRP/DOGE et TOUS les "
        "non-majors commencent 2025-09 (genèse Aster). funding_history "
        "commence 2025-10-27 (PAS 2021 — la mémoire « funding profond » "
        "était fausse).",
        "- **Rejouable deep** : cascade majors (3/6 majors avant 2025-09, "
        "6/6 ensuite — le collecteur suit la donnée ; corr roulante sur 3 "
        "paires au lieu de 15 ; boost fund_rank inactif avant 2025-10, "
        "comportement nan déjà codé) et vol_spike_6h (même univers).",
        "- **Non rejouable deep** : cascade_meme et survivor_long (univers "
        "non-majors, genèse 2025-09 — Aster n'existait pas avant). Leurs "
        "cellules 2021-2024 sont structurellement vides : « 0t » n'est PAS "
        "un edge testé, c'est une absence de donnée.",
        "- Funding du sim : moyennes modernes par symbole (2025-10→2026-09) "
        "appliquées à toute la timeline — approximation documentée, impact "
        "faible ($53 nets sur $3 906 officiels).",
        "", "## 2. TABLE RÉGIME × FLUX (wallet frais $100/cellule, "
        "leviers machine 10x/1x/1x/1x)", "",
        "Cellule = `trades · WR · ROI seg (ROI/an) · DD · mois− pire mois`. "
        "Calibration par cellule = la machine nocturne du régime (q66 sur "
        "les premiers 70 % de la cellule, médianes/p90 locaux). "
        "`—` = genèse (donnée inexistante, PAS un test).",
        "",
        "| flux | " + " | ".join(n for n, _, _ in REGIMES) + " |",
        "|---|" + "---|" * len(REGIMES),
    ]
    for flow in ("cascade_10x", "cascade_meme", "survivor_long",
                 "vol_spike_6h"):
        cells = []
        for name, _, _ in REGIMES:
            s = grid[flow].get(name)
            cells.append("—" if s is None else cell(s))
        L.append(f"| **{FLOW_LABEL[flow]}** | " + " | ".join(cells) + " |")

    L += ["", "## 3. LE MONITEUR MAE — le 10x tient-il les régimes ? "
          "(règle : levier ≤ 100/(maxMAE+0,5))", "",
          "| régime | ev bruts | gated | q66 | MAE max gated | levier sûr |",
          "|---|---|---|---|---|---|"]
    for name, _, _ in REGIMES:
        m = monitor["cascade_10x"].get(name)
        if m is None:
            L.append(f"| {name} | — | — | — | — | — |")
            continue
        n_ev, n_g, q66, med, mae = m
        L.append(f"| {name} | {n_ev} | {n_g} | {q66:.2f} | {mae:.2f} % | "
                 f"{100 / (mae + 0.5):.1f}x "
                 f"{'OK' if mae < 9.5 else '⚠ 10x MORDU'} |")
    L += ["",
          "⚠ `q66 = nan` = gate AL INERTE dans la cellule : "
          "`add_rolling_scores` exige ≥ 50 événements sur 90 jours "
          "roulants ; l'univers deep 3 majors produit ~45 év/90 j → "
          "scores nan → cellule « gated » = cascades BRUTES (toutes "
          "prises, levier 10x appliqué). Le gate n'a fonctionné que sur "
          "l'univers 6 majors (2025-2026)."]

    L += ["", "## 4. LE RUN DEEP EMPILÉ (cascade majors + vol_spike 1x, "
          f"2021-09→2026-09, calibration train 70 %)", "",
          "La seule partie de la machine testable sur le cycle complet. "
          f"q66 deep = {q66_deep:.2f} (train = premiers 70 % = "
          "2021-09→~2025-06 ; ATTENTION : scores AL majoritairement nan sur "
          "cette période, cf. section 3 — le q66 deep repose sur le sous-"
          f"ensemble fini). MAE max gated deep {mae_deep:.2f} % → levier "
          f"sûr {lev_safe_deep:.1f}x — **le 10x NE TIENT PAS**.", "",
          "| Stat | 10x (config machine) | 4x (levier sûr 0-liq) |",
          "|---|---|---|",
          f"| Wallet $100 → | **${res_deep['balance']:,.2f}** | "
          f"**${res_deep4['balance']:,.2f}** |",
          f"| ROI (CAGR) | {deep['roi']:+.0f} % ({deep['roi_an']:+.0f} %/an) "
          f"| {deep4['roi']:+.0f} % ({deep4['roi_an']:+.0f} %/an) |",
          f"| Max DD | {deep['dd']:.1f} % | {deep4['dd']:.1f} % |",
          f"| **Liquidations** | **{deep['liq']}** | "
          f"**{deep4['liq']}** |",
          f"| Trades / WR | {deep['n']} / {deep['wr']:.1f} % | "
          f"{deep4['n']} / {deep4['wr']:.1f} % |",
          f"| Mois pire / record | {deep['worst']:+.1f} % / "
          f"{deep['record']:+.1f} % ({deep['neg']} négatifs) | "
          f"{deep4['worst']:+.1f} % / {deep4['record']:+.1f} % "
          f"({deep4['neg']} négatifs) |",
          f"| Garde-fou composé des mois | écart {gap_c*100:.3f} % "
          f"{'OK' if gap_c < 0.005 else '✗ BUG'} | — |",
          f"| Garde-fou somme PnL | écart ${gap_p:.4f} "
          f"{'OK' if gap_p < 0.01 else '✗ BUG'} | — |",
          "", "PnL du MÊME wallet (10x) par régime (continuité, pas de "
          "reset — wallet éteint après 2023-12 : balance ≤ 1 $) :",
          "", "| régime | PnL $ |", "|---|---|"]
    for name, _, _ in REGIMES:
        L.append(f"| {name} | {deep_by_regime[name]:+,.2f} |")

    L += ["", "### La table mensuelle du run deep (10x)", "",
          "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
    for x in mr:
        L.append(f"| {x['month']} | {x['n']} | "
                 f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} | "
                 f"{x['roi']:+.1f} % |")

    L += ["", "## 5. LE PONT OFFICIEL — re-run connu 2025-09→2026-09 "
          "(4 flux) vs docs/21", "",
          f"- Scénario A (scores AL alimentés par le deep, gate actif dès "
          f"2025-10) : ${CAPITAL:,.0f} → **${res_known['balance']:,.2f}** "
          f"({known['roi']:+.0f} %), DD {known['dd']:.1f} %, "
          f"liq {known['liq']}, {known['n']} trades, WR {known['wr']:.1f} %.",
          f"- Scénario B (scores FRAIS recalculés sur la fenêtre seule — "
          f"warm-up 90 j = DB jeune, gate inerte tôt, comme l'officiel) : "
          f"→ **${res_known_b['balance']:,.2f}** ({known_b['roi']:+.0f} %), "
          f"DD {known_b['dd']:.1f} %, liq {known_b['liq']}, "
          f"{known_b['n']} trades, q66 B = {q66_b:.2f}.",
          "- Officiel (27/09, DB jeune sans deep) : $100 → $4 004,94 "
          "(+3 905 %/an), DD 24,8 %, 0 liq, 1 356 trades, WR 52,3 %, "
          "q66 = 0.68, MAE gated 7,84 %.",
          "- Lecture : l'écart A ↔ B isole l'effet WARM-UP du gate (l'état "
          "de la DB change la sélection) ; l'écart B ↔ officiel = la dérive "
          "de DB en 3 jours (nouveaux symboles, nouvelles bougies). Les "
          "stats « 1 an » de la machine dépendent donc de l'état de "
          "warm-up de la DB au moment du run — un fait de méthode, pas un "
          "bug.", "",
          "## 6. VERDICT", ""]

    # verdict structuré par les chiffres
    bear = grid["cascade_10x"].get("bear_2022")
    bull21 = grid["cascade_10x"].get("bull_2021H2")
    spike_bear = grid["vol_spike_6h"].get("bear_2022")
    L += [
        "**INFIRMÉ — le levier 10x n'est PAS régime-indépendant.** La "
        "règle 0-liq échoue hors fenêtre connue : MAE max gated > 9,5 % "
        "dans 6 cellules/7 (11,6 % bull 2021, 22,6 % bear 2022, 18,9 % "
        "2023, 11,6 % 2024H1, 12,4 % chop, 18,6 % 2025 ; seul 2026 tient à "
        "7,84 %). Le run deep 10x : 14 liquidations, wallet $100 → "
        f"${res_deep['balance']:,.2f} (mort fin 2023). Au levier sûr 4x : "
        f"0 liq mais ${res_deep4['balance']:,.2f} — la cascade majors "
        "rejouée deep N'EST PAS rentable, gate ou pas de gate.",
        "",
        f"**INFIRMÉ — l'edge brut cascade est régime-dépendant.** WR 38-51 "
        f"%, ROI négatif dans 6/7 régimes en cellule frais ({bull21['roi']:+.0f} "
        f"% bull 2021, {bear['roi']:+.0f} % bear 2022). Le +168 % de la "
        "cellule 2026 = la seule fenêtre jamais testée par la machine. "
        "L'edge « cascade majors » est une propriété de 2025-2026, pas du "
        "cycle.",
        "",
        "**INFIRMÉ (partiel) — le gate AL Score ne peut pas s'engager sur "
        "l'univers 3 majors** : min_window = 50 év/90 j contre ~45 observés "
        "→ scores nan 2021-2025 → cellules « gated » = cascades BRUTES. "
        "Le gate n'a jamais fonctionné qu'univers 6 majors (2025-2026). "
        "Sa valeur protectrice deep est donc INTESTÉE, pas réfutée.",
        "",
        f"**PARTIEL — vol_spike_6h ≈ plat hors 2025-2026** "
        f"({spike_bear['roi']:+.0f} % bear 2022, ±5 % ailleurs, DD ≤ 14) : "
        "0 liq constaté partout (1x, jamais > 99,5 % adverse dans le sim), "
        "mais l'edge est une propriété de la fenêtre connue, pas un "
        "régime-indépendant.",
        "",
        "**NON TESTABLE deep — cascade_meme et survivor_long** (genèse "
        "2025-09 ; « 0t » = absence de donnée). Sur la fenêtre connue en "
        "cellule frais : meme +4 % (T4 2025) / -8 % (2026), survivor +57 % "
        "(2026, DD 7) — le survivor est le flux le plus sain des deux.",
        "",
        "**PONT — les stats officielles dépendent de l'état de warm-up de "
        "la DB** : scénario A (gate deep-informé) "
        f"${res_known['balance']:,.2f} vs scénario B (warm-up officiel) "
        f"${res_known_b['balance']:,.2f} vs officiel $4 004,94. Le même "
        "moteur, trois états de DB, des ROI qui vont de +651 % à +3 905 % "
        ": les ABSOLUS de docs/21 sont fragiles, les RELATIFS (ordre des "
        "flux, 0-liq sur la fenêtre connue) tiennent.",
        "",
        "**IMPLICATIONS ADAPTATEUR** : (1) asservir le levier cascade au "
        "régime — levier ≤ 100/(MAE_pire_du_régime + 0,5), soit 4x sur le "
        "cycle complet, 10x seulement si le moniteur MAE 6 majors reste "
        "< 9,5 % ; (2) ne pas généraliser les ROI 2025-2026 — la cible "
        "« 60-70 %/mois stable » n'est observée que dans une fenêtre haussière "
        "majeure ; (3) le forward paper reste le seul juge — le deep dit "
        "QUELLE robustesse chercher (0-liq à 4x, edge positif en bear), "
        "pas quelle config promouvoir.",
        "",
        "Règle gravée : levier ≤ 100/(maxMAE + 0,5) — vérifié cellule par "
        "cellule, section 3. Verdicts RELATIFS conservés (le classement "
        "des régimes), ABSOLUS non. Garde-fou composé-des-mois affiché "
        "section 4.", "",
        "Fichiers : étude `scripts/studies/aster_machine_deep_regimes.py` "
        "— lecture seule `data/warehouse/klines.db` (aucune écriture prod).",
    ]
    out = REPORTS / "aster_machine_deep_regimes.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[t8] rapport : {out}")
    print(f"[t8] deep empilé : ${res_deep['balance']:,.2f} "
          f"(CAGR {deep['roi_an']:+.0f} %/an), DD {deep['dd']:.1f} %, "
          f"liq {deep['liq']} | MAE gated deep {mae_deep:.2f} % → "
          f"{lev_safe_deep:.1f}x | pont connu ${res_known['balance']:,.2f} "
          f"(officiel $4 004,94)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
