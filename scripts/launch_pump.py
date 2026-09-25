#!/usr/bin/env python
"""LE LAUNCH-PUMP LONG — la seule zone long de la carte de cycle de vie.

La carte (backtest_lifecycle.py) a validé un état : **0-7 jours / près de
l'ATH → LONG 55,5 %** — le pump de lancement, le SEUL terrain long du
marché memecoin Aster. C'était de la cartographie horizon-fixe ; ce test
le passe à l'épreuve qui compte : le WALLET SÉQUENTIEL, comme 3e
composante du stack — et la première décorrelée par la DIRECTION.

L'hypothèse : un perp qui liste et tient près de son ATH dans sa
première semaine est un launch-pump vivant (les détenteurs ne vendent
pas, les nouveaux arrivent) ; tout le reste de l'écosystème est short.

Discipline : baseline blind long sur les mêmes jeunes symboles, contrôle
INVERSE (shorter le launch), train/val par le temps, wallet 100 $.

  .venv/bin/python scripts/launch_pump.py
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, collect_funding_strategies, run_stack)

REPORTS = ROOT / "reports"
MAX_AGE_D = 7
MAX_DD = 20.0
HOLD = 72


def collect_launch(con: sqlite3.Connection, direction: int, hold: int = HOLD,
                   fee_rt: int = TAKER_RT) -> tuple[list[dict], dict]:
    """Les événements launch-pump (jeunes + près ATH), direction ±1.
    Retourne (événements, stats blind sur les mêmes jeunes barres)."""
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' ORDER BY symbol")]
    events: list[dict] = []
    blind = {"n": 0, "w": 0, "s": 0.0}
    for sym in symbols:
        if sym in MAJORS:
            continue                     # les majeures n'ont pas d'âge jeune
        df = load_df(con, sym)
        if df is None or len(df) < 200:
            continue
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        age_d = (idx_ns - idx_ns[0]) / (86400 * 10**9)
        highs = df["high"].values
        lows = df["low"].values
        opens = df["open"].values
        closes = df["close"].values
        close_s = pd.Series(closes, index=idx)
        ath = pd.Series(highs, index=idx).cummax()
        dd = ((ath - close_s) / ath * 100).values

        young = (age_d <= MAX_AGE_D) & (dd <= MAX_DD)
        for t in np.where(young)[0]:
            ei = t + 1
            if ei + HOLD >= len(idx_ns) or t < 48:
                continue
            entry = opens[ei]
            if entry <= 0:
                continue
            exit_j = ei + HOLD - 1
            if exit_j >= len(idx_ns):
                continue
            exit_px = closes[exit_j]
            r_long = (exit_px - entry) / entry * 100
            # la baseline blind : le même calcul SANS le filtre près-ATH
            blind["n"] += 1
            blind["w"] += r_long > 0
            blind["s"] += r_long
            if direction > 0:
                ret_field = -r_long                     # short-semantics
            else:
                ret_field = r_long
            mae = ((highs[ei:exit_j + 1].max() if direction < 0
                    else lows[ei:exit_j + 1].min()))
            mae_adverse = ((mae - entry) / entry * 100 if direction > 0
                           else (entry - mae) / entry * 100)
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "strategy": "launch",
                "lev": 3, "hold_h": HOLD, "fee_rt_bps": fee_rt,
                "entry": entry, "exit": exit_px,
                "price_ret_short": ret_field,
                "fund_sign": -1 if direction > 0 else 1,
                "mae_adverse": abs(mae_adverse),
            })
    events.sort(key=lambda e: e["ts_ms"])
    return events, blind


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--direction", choices=["long", "short"], default="long")
    ap.add_argument("--hold", type=int, default=HOLD)
    ap.add_argument("--maker", action="store_true")
    args = ap.parse_args()
    direction = 1 if args.direction == "long" else -1

    con = sqlite3.connect(KDB)
    launch, blind = collect_launch(
        con, direction, args.hold,
        MAKER_RT if args.maker else TAKER_RT)
    fh = {}
    acc: dict[str, list[float]] = {}
    for s, r in con.execute("SELECT symbol, rate FROM funding_history"):
        try:
            acc.setdefault(s, []).append(float(r))
        except (TypeError, ValueError):
            continue
    for s, v in acc.items():
        fh[s] = sum(v) / len(v) * 100 / 8

    # le stack existant
    regime = btc_regime_series()
    from scripts.anti_liq import add_rolling_scores, collect_featured
    cascade = collect_featured(regime, "majors")
    for e in cascade:
        e["strategy"] = "cascade"
        e["lev"] = 20
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(cascade)
    q66 = float(np.nanquantile(
        [e["al_score"] for e in cascade[:int(len(cascade) * 0.7)]], 2/3))
    fdiv, conf = collect_funding_strategies(con)
    con.close()

    def stack_policy(with_launch: bool):
        def fn(e: dict) -> float:
            s = e.get("strategy")
            if s == "cascade":
                sc = e.get("al_score", float("nan"))
                if np.isnan(sc):
                    return 0.05
                return 0.0 if sc >= q66 else 0.045
            if s == "funding_div":
                return 0.015
            if s == "confluence":
                return 0.01
            if s == "launch" and with_launch:
                return 0.015
            return 0.0
        return fn

    all_ev = sorted(cascade + fdiv + conf + launch,
                    key=lambda e: e["ts_ms"])
    stack_no = run_stack(all_ev, CAPITAL, stack_policy(False), fh)
    stack_yes = run_stack(all_ev, CAPITAL, stack_policy(True), fh)
    alone = run_stack(launch, CAPITAL, lambda e: 0.05, fh)
    oracle_y = run_stack(all_ev, CAPITAL, stack_policy(True), fh, oracle=True)

    n = len(launch)
    wr = sum(1 for e in launch if -e["price_ret_short"] * 1 > 0) / max(n, 1) * 100
    raw_mean = sum(-e["price_ret_short"] for e in launch) / max(n, 1)
    blind_wr = blind["w"] / max(blind["n"], 1) * 100
    blind_mean = blind["s"] / max(blind["n"], 1)

    delta_stack = stack_yes["balance"] - stack_no["balance"]
    ok = (delta_stack > 2 and stack_yes["max_dd"] <= stack_no["max_dd"] + 3
          and n >= 40)
    verdict = (f"LE LAUNCH-PUMP LONG PASSE — 3e composante du stack "
               f"(+{delta_stack:,.2f} $ au stack, DD "
               f"{stack_yes['max_dd']:.1f} % vs {stack_no['max_dd']:.1f} %)"
               if ok else
               f"NE PASSE PAS — effet stack {delta_stack:+.2f} $ à "
               f"DD {stack_yes['max_dd']:.1f} % vs {stack_no['max_dd']:.1f} %")

    lines = [
        "# LE LAUNCH-PUMP LONG — la zone 0-7j / près-ATH en wallet réel",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — direction "
        f"{args.direction.upper()}, hold {HOLD}h, 3x, taker, "
        f"âge ≤ {MAX_AGE_D}j + drawdown ≤ {MAX_DD:.0f} % du ATH.", "",
        "## Baseline anti-dérive (blind long 72h sur les jeunes barres)", "",
        f"- blind long : WR {blind_wr:.1f} % (n={blind['n']}), "
        f"moyenne {blind_mean:+.3f} %/trade",
        f"- launch-pump brut : WR {wr:.1f} % (n={n}), "
        f"moyenne {raw_mean:+.3f} %/trade",
        f"- **Δ vs blind : {raw_mean - blind_mean:+.3f} pts/trade**", "",
        "## Le wallet (100 $)", "",
        f"- launch {args.direction} SEUL (5 % flat) : "
        f"${alone['balance']:,.2f} (DD {alone['max_dd']:.1f} %, "
        f"{alone['n']} trades, liq {alone['n_liq']})",
        f"- STACK ×2 SANS launch : ${stack_no['balance']:,.2f} "
        f"(DD {stack_no['max_dd']:.1f} %, liq {stack_no['n_liq']})",
        f"- STACK ×2 AVEC launch : **${stack_yes['balance']:,.2f}** "
        f"(DD {stack_yes['max_dd']:.1f} %, liq {stack_yes['n_liq']})",
        f"- ORACLE du stack avec launch (plafond) : "
        f"${oracle_y['balance']:,.2f} (DD {oracle_y['max_dd']:.1f} %)", "",
        f"## VERDICT : {verdict}", "",
        "- le contrôle inverse (shorter le launch) se lance avec "
        "`--direction short` — si les deux directions gagnent, ne pas croire.",
    ]
    out = REPORTS / f"launch-pump-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[launch] {n} évts, WR {wr:.1f} % (blind {blind_wr:.1f} %), "
          f"Δ blind {raw_mean - blind_mean:+.3f} pts")
    print(f"[launch] seul ${alone['balance']:,.2f} | stack sans "
          f"${stack_no['balance']:,.2f} (DD {stack_no['max_dd']:.1f} %) | "
          f"avec ${stack_yes['balance']:,.2f} "
          f"(DD {stack_yes['max_dd']:.1f} %)")
    print(f"[launch] {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
