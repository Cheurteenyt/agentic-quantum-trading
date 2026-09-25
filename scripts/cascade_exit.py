#!/usr/bin/env python
"""L'EXIT SUR ÉPUISEMENT — la première bougie verte comme marqueur de sortie.

La frontière du projet (cascade 20x gated + stack) sort à 24h fixes. La
théorie de la cascade dit autre chose : le bounce VIENT (les shorts
prennent leurs profits, les longs liquides rachètent) — la première
bougie VERTE après la cascade est le marqueur d'épuisement naturel.
Sortir là :
  - détentions plus courtes (moins de funding payé)
  - MAE réduites (moins d'heures exposées au bounce qui tue)
  - moins de liquidations → le réel se rapproche de l'oracle

Le test : MÊMES événements, MÊMES gates AL, MÊME sizing — seul l'exit
change :
  1. 24h fixes (la référence publiée)
  2. première bougie verte (hold 1-24h)
  3. première bougie verte après ≥ 6h (éviter les sorties instantanées
     sur un dead-cat)
  + le contrôle inverse : la première verte DÉCALÉE de 6h (si sortir
    décalé améliore autant, le timing est du bruit)

  .venv/bin/python scripts/cascade_exit.py
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"
MAX_HOLD = 24
MIN_HOLD = 0          # variante 2 : 0 ; variante 3 : 6
DELAY = 0             # contrôle inverse : +6


def recompute_exit(con: sqlite3.Connection, events: list[dict],
                   mode: str, min_hold: int = 0, delay: int = 0,
                   trail_pct: float = 0.015) -> list[dict]:
    """Recalcule l'exit de chaque événement cascade sur les klines.
    mode='fixed' : sortie à 24h pile (la référence).
    mode='green' : première bougie VERTE (close > open) entre
    min_hold+delay et 24h ; sinon 24h.
    mode='trail' : trailing stop — on suit le plus-bas (ll) depuis
    l'entrée ; sortie au premier high ≥ ll×(1+trail_pct) (fill au
    trigger, à l'open si gap), plafonné à 24h."""
    dfs = {s: load_df(con, s) for s in MAJORS}
    out = []
    for e in events:
        df = dfs.get(e["sym"])
        if df is None:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        entry_i = int(np.searchsorted(idx_ns, e["ts_ms"], side="left"))
        if entry_i >= len(idx_ns):
            continue
        opens = df["open"].values
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        exit_j = entry_i + MAX_HOLD - 1
        exit_px = float(closes[exit_j])
        if mode == "green":
            for j in range(entry_i + min_hold + delay,
                           min(entry_i + MAX_HOLD, len(idx_ns))):
                if closes[j] > opens[j]:
                    exit_j = j
                    break
            exit_px = float(closes[exit_j])
        elif mode == "trail":
            ll = float(opens[entry_i])
            end = min(entry_i + MAX_HOLD, len(idx_ns))
            for j in range(entry_i, end):
                ll = min(ll, float(lows[j]))
                trigger = ll * (1 + trail_pct)
                if highs[j] >= trigger:
                    exit_j = j
                    exit_px = float(max(opens[j], trigger))
                    break
        hold_h = exit_j - entry_i + 1
        entry = e["entry"]
        out.append({
            "sym": e["sym"], "ts_ms": e["ts_ms"], "strategy": "cascade",
            "lev": 20, "hold_h": hold_h, "fee_rt_bps": MAKER_RT,
            "entry": entry, "exit": exit_px,
            "price_ret_short": (entry - exit_px) / entry * 100,
            "mae_adverse": (highs[entry_i:exit_j + 1].max() - entry)
            / entry * 100,
            "al_score": e.get("al_score", float("nan")),
        })
    out.sort(key=lambda x: x["ts_ms"])
    return out


def main() -> int:
    con = sqlite3.connect(KDB)
    regime = None
    from scripts.portfolio_sim import btc_regime_series
    regime = btc_regime_series()
    base_events = collect_featured(regime, "majors")
    for e in base_events:
        e["strategy"] = "cascade"
        e["lev"] = 20
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(base_events)
    fh = funding_hourly_all()

    q66 = float(np.nanquantile(
        [e["al_score"] for e in base_events[:int(len(base_events) * 0.7)]],
        2/3))

    def gate_fn(e: dict) -> float:
        s = e.get("al_score", float("nan"))
        if np.isnan(s):
            return 0.05
        return 0.0 if s >= q66 else 0.075

    variants = {
        "24h fixes (référence)": recompute_exit(con, base_events, "fixed"),
        "1re verte (hold 1-24h)": recompute_exit(con, base_events, "green",
                                                 min_hold=0),
        "TRAIL 1,0 %": recompute_exit(con, base_events, "trail",
                                      trail_pct=0.010),
        "TRAIL 1,5 %": recompute_exit(con, base_events, "trail",
                                      trail_pct=0.015),
        "TRAIL 2,5 %": recompute_exit(con, base_events, "trail",
                                      trail_pct=0.025),
        "CONTRÔLE : TRAIL 1,5 % inversé (5 %)": recompute_exit(
            con, base_events, "trail", trail_pct=0.05),
    }

    con.close()

    lines = [
        "# L'EXIT SUR ÉPUISEMENT — la première bougie verte",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — mêmes événements, "
        f"mêmes gates AL (≥ p66 {q66:.2f} → 0), même sizing 7,5 % ; seul "
        f"l'exit change.", "",
        "| Exit | Trades | Hold moyen | Liq | 100 $ → | ROI/an | DD |",
        "|---|---|---|---|---|---|---|",
    ]
    results = {}
    for label, evs in variants.items():
        res = run_stack(evs, CAPITAL, gate_fn, fh)
        holds = [e["hold_h"] for e in evs]
        results[label] = res
        lines.append(
            f"| {label} | {res['n']} | {np.mean(holds):.1f} h | {res['n_liq']} "
            f"| ${res['balance']:,.2f} | "
            f"{(res['balance']/CAPITAL-1)*100:+.0f} % | {res['max_dd']:.1f} % |")

    # train/val sur les deux meilleurs candidats
    ref = results["24h fixes (référence)"]
    best_label = max(results, key=lambda l: results[l]["balance"])
    best = results[best_label]
    ok_dir = best["balance"] > ref["balance"] * 1.05
    ctrl = results["CONTRÔLE : TRAIL 1,5 % inversé (5 %)"]
    ok_inv = ctrl["balance"] > best["balance"]
    if ok_dir and not ok_inv:
        verdict = (f"L'EXIT SUR ÉPUISEMENT MARCHE — {best_label} bat les "
                   f"24h fixes, le contrôle décalé est battu")
    elif ok_dir and ok_inv:
        verdict = "AMBIGU — le décalé améliore autant : timing = bruit"
    else:
        verdict = ("L'EXIT 24h FIXE RESTE LE ROI — la première verte "
                   "n'apporte rien")

    # le stack ×2 avec le meilleur exit
    stack_lines = []
    for label, evs in (("24h fixes", variants["24h fixes (référence)"]),
                       (best_label, variants[best_label])):
        fdiv_conf = []
        con = sqlite3.connect(KDB)
        try:
            from scripts.stacked_portfolio import collect_funding_strategies
            fdiv, conf = collect_funding_strategies(con)
        finally:
            con.close()
        stack_ev = sorted(evs + fdiv + conf, key=lambda x: x["ts_ms"])

        def stack_policy(e: dict) -> float:
            if e["strategy"] == "cascade":
                s = e.get("al_score", float("nan"))
                if np.isnan(s):
                    return 0.05
                return 0.0 if s >= q66 else 0.045
            return 0.015 if e["strategy"] == "funding_div" else 0.01

        def policy2(e: dict) -> float:
            return stack_policy(e) * 2
        s2 = run_stack(stack_ev, CAPITAL, policy2, fh)
        stack_lines.append(
            f"- STACK ×2 avec {label} : 100 $ → **${s2['balance']:,.2f}** "
            f"(ROI {(s2['balance']/CAPITAL-1)*100:+.0f} %, "
            f"DD {s2['max_dd']:.1f} %, liq {s2['n_liq']})")

    mrows = monthly_rows(best["trades"], CAPITAL)
    if mrows:
        rois_m = [r["roi"] for r in mrows]
        lines += ["", "## BLOC STATS — meilleur exit, sim complet", "",
                  "| Stat | Valeur |", "|---|---|",
                  f"| Wallet 100 $ → | **${best['balance']:,.2f}** |",
                  f"| ROI (1 an) | {(best['balance']/CAPITAL-1)*100:+.1f} % |",
                  f"| Max DD | {best['max_dd']:.1f} % |",
                  f"| Trades / liq | {best['n']} / {best['n_liq']} |",
                  f"| ROI mensuel moyen | {np.mean(rois_m):+.1f} % "
                  f"(pire {min(rois_m):+.1f} %) |"]
    lines += ["", "## Le stack ×2 selon l'exit", ""] + stack_lines + [
        "", f"## VERDICT : {verdict}", "",
        "- le contrôle inverse = sortir à la première verte DÉCALÉE de 6h :",
        "  si le décalé améliore autant, le timing de l'épuisement est du bruit.",
    ]

    out = REPORTS / f"cascade-exit-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[cascade-exit] ref ${ref['balance']:,.2f} (DD {ref['max_dd']:.1f} %) | "
          f"best ${best['balance']:,.2f} (DD {best['max_dd']:.1f} %, "
          f"liq {best['n_liq']}) | ctrl ${ctrl['balance']:,.2f}")
    print(f"[cascade-exit] {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
