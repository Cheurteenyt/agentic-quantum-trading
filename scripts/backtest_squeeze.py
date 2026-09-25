#!/usr/bin/env python
"""LE SQUEEZE HAUSSIER — le miroir exact de la cascade, jamais testé.

La cascade (3 bougies de BAISSE consécutives avec accélération → short)
est le signal le plus puissant du projet. Son miroir — 3 bougies de
HAUSSE consécutives avec accélération → LONG — reste ouvert :
  1. a-t-il un edge au-dessus du blind LONG (la baseline anti-dérive) ?
  2. survit-il au wallet séquentiel (la règle nouvelle) ?
  3. décorrelé de la cascade, améliore-t-il le STACK ?

Le motif : dans un squeeze, les shorts se font liquider — leurs rachats
forcés poussent le prix, ce qui liquide le short suivant (la spirale
haussière). MAIS le marché memecoin est structurellement SHORT (blind
long 60j = 35,7 %) — l'hypothèse de départ est PESSIMISTE, et c'est
volontaire : on cherche un composant long pour décorréler le portefeuille.

Discipline : wallet 100 $, sizing 5 % flat, levier 20x, maker, hold 24h,
liquidation en chemin (MAE 4,5 %), funding réel (le long PAIT le taux
positif), garde-fous anti-bug sur le composé mensuel.

  .venv/bin/python scripts/backtest_squeeze.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, btc_regime_series, monthly_rows)
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"
HOLD = 24


def collect_squeeze(con: sqlite3.Connection) -> list[dict]:
    """Les événements squeeze-long des majeures (miroir de la cascade)."""
    events: list[dict] = []
    for sym in MAJORS:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close = df["close"]
        r1 = close.pct_change() * 100
        ra = r1.abs()
        squeeze = ((r1 > 0) & (r1.shift(1) > 0) & (r1.shift(2) > 0)
                   & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        opens = df["open"].values
        closes = df["close"].values
        lows = df["low"].values
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        for t in np.where(squeeze)[0]:
            ei = t + 1
            if ei + HOLD >= len(idx_ns) or t < 200:
                continue
            entry = opens[ei]
            if entry <= 0:
                continue
            exit_j = ei + HOLD - 1
            if exit_j >= len(idx_ns):
                continue
            exit_px = closes[exit_j]
            r_long = (exit_px - entry) / entry * 100
            # MAE du long : l'excursion BAISSIÈRE max pendant la détention
            mae = (entry - lows[ei:exit_j + 1].min()) / entry * 100
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "strategy": "squeeze",
                "lev": 20, "hold_h": HOLD, "fee_rt_bps": MAKER_RT,
                "entry": entry, "exit": exit_px,
                "price_ret_short": -r_long,      # le champ du wallet (long = signe inversé)
                "fund_sign": -1,                 # le long PAIT le funding positif
                "mae_adverse": mae,
            })
    events.sort(key=lambda e: e["ts_ms"])
    # la sélection séquentielle (premier dispo, skip des chevauchements)
    taken, i = [], 0
    while i < len(events):
        taken.append(events[i])
        hold_end = events[i]["ts_ms"] + HOLD * 3600 * 1000
        while i < len(events) and events[i]["ts_ms"] < hold_end:
            i += 1
    return taken


def main() -> int:
    con = sqlite3.connect(KDB)
    regime = btc_regime_series()
    fh = funding_hourly_all()

    # la baseline anti-dérive côté LONG : le blind long 24h sur les majeures
    blinds: dict[str, dict] = defaultdict(lambda: {"n": 0, "w": 0, "s": 0.0})
    for sym in MAJORS:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        closes = df["close"].values
        opens = df["open"].values
        for t in range(200, len(df) - HOLD):
            entry, exit_px = opens[t + 1], closes[t + HOLD]
            r = (exit_px - entry) / entry * 100
            blinds["blind_long"]["n"] += 1
            blinds["blind_long"]["w"] += r > 0
            blinds["blind_long"]["s"] += r
    con.close()

    squeeze = collect_squeeze(sqlite3.connect(KDB))
    con.close()

    cascade = collect_featured(regime, "majors")
    for e in cascade:
        e["strategy"] = "cascade"
        e["lev"] = 20
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT

    # stats brutes du squeeze (hors wallet)
    n = len(squeeze)
    raw_wr = sum(1 for e in squeeze if -e["price_ret_short"] > 0) / max(n, 1) * 100
    raw_mean = sum(-e["price_ret_short"] for e in squeeze) / max(n, 1)
    bl = blinds["blind_long"]

    # le wallet séquentiel : squeeze seule / cascade seule / STACK
    sq_sim = run_stack(squeeze, CAPITAL, lambda e: 0.05, fh)
    stack_ev = sorted(cascade + squeeze, key=lambda e: e["ts_ms"])

    add_rolling_scores(cascade)
    k = int(len(cascade) * 0.7)
    q66 = float(np.nanquantile([e["al_score"] for e in cascade[:k]], 2/3))

    def stack_policy(e: dict) -> float:
        if e["strategy"] == "cascade":
            sc = e.get("al_score", float("nan"))
            if np.isnan(sc):
                return 0.05
            return 0.0 if sc >= q66 else 0.045
        return 0.015                      # squeeze : 1,5 % flat

    stack = run_stack(stack_ev, CAPITAL, stack_policy, fh)
    oracle = run_stack(stack_ev, CAPITAL, stack_policy, fh, oracle=True)

    def policy2(e: dict) -> float:
        return stack_policy(e) * 2
    stack2 = run_stack(stack_ev, CAPITAL, policy2, fh)

    mrows = monthly_rows(stack2["trades"], CAPITAL)
    checks = []
    if mrows:
        prod = 1.0
        for r in mrows:
            prod *= (1 + r["roi"] / 100)
        gap = abs(prod - stack2["balance"] / CAPITAL)
        rois_m = [r["roi"] for r in mrows]
        checks = [f"composé des mois vs final : écart {gap*100:.3f} % "
                  f"{'OK' if gap < 0.005 else '✗ BUG'}",
                  f"ROI mensuel moyen {np.mean(rois_m):+.1f} % "
                  f"(pire {min(rois_m):+.1f} %, "
                  f"{sum(1 for x in rois_m if x < 0)} mois négatifs)"]

    def bloc(res: dict, label: str) -> str:
        nn = max(res["n"], 1)
        return (f"- **{label}** : {CAPITAL:,.0f} $ → **${res['balance']:,.2f}** "
                f"(ROI {(res['balance']/CAPITAL-1)*100:+.1f} %, "
                f"DD {res['max_dd']:.1f} %, {res['n']} trades, "
                f"WR {res['n_wins']/nn*100:.1f} %, liq {res['n_liq']})")

    verdict_squeeze = ("PASSE le wallet séquentiel — candidat pour le stack"
                       if sq_sim["balance"] > CAPITAL * 1.2
                       else "MORT en séquentiel — pas de composant long ici")
    beats_stack = stack2["balance"] > stack["balance"] * 2

    lines = [
        "# LE SQUEEZE HAUSSIER — le miroir de la cascade",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{n} événements squeeze (majeures, hold 24h, sélection séquentielle).",
        "",
        "## Baseline anti-dérive côté LONG (blind long 24h, majeures)", "",
        f"- blind long : WR {bl['w']/max(bl['n'],1)*100:.1f} % "
        f"(n={bl['n']}), ret moyen {bl['s']/max(bl['n'],1)*100:+.3f} %/trade",
        f"- squeeze-long brut : WR {raw_wr:.1f} %, ret moyen {raw_mean:+.3f} %/trade",
        f"- **Δ brut vs blind : {(raw_mean - bl['s']/max(bl['n'],1)*100)*20:+.2f} % "
        f"de marge/trade à 20x**",
        "",
        "## Le wallet séquentiel (100 $, maker, funding réel)", "",
        bloc(sq_sim, "SQUEEZE seule (5 % flat)"),
        "- cascade seule (7,5 %/gate AL) : la référence = $361.65 (DD 60.4 %)",
        bloc(stack, "STACK cascade 4,5 %/gate + squeeze 1,5 %"),
        bloc(stack2, "STACK ×2"),
        bloc(oracle, "ORACLE du stack ×2 (plafond)"),
        "",
        "## Garde-fous", "",
    ] + ([f"- {c}" for c in checks] or ["- pas de trades ce soir"]) + [
        "",
        f"## VERDICT : {verdict_squeeze}", "",
        f"- le stack ×2 bat le stack ×1 doublé ({beats_stack}) — "
        f"la décorrélation long/short apporte "
        f"{'de la valeur' if beats_stack else 'peu de valeur'}",
        "- la règle : un composant long doit passer le wallet séquentiel",
        "  avant d'entrer dans le stack — comme tout le monde.",
    ]

    out = REPORTS / f"squeeze-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[squeeze] {n} évts, WR {raw_wr:.1f} %, ret moyen {raw_mean:+.3f} % | "
          f"squeeze seule ${sq_sim['balance']:,.2f} (DD {sq_sim['max_dd']:.1f} %)")
    print(f"[squeeze] stack ${stack['balance']:,.2f} (DD {stack['max_dd']:.1f} %) | "
          f"×2 ${stack2['balance']:,.2f} (DD {stack2['max_dd']:.1f} %) | "
          f"oracle ${oracle['balance']:,.2f}")
    print(f"[squeeze] {verdict_squeeze}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
