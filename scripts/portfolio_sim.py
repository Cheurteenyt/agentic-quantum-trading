#!/usr/bin/env python
"""LE SIMULATEUR DE PORTEFEUILLE — du signal à l'argent réel.

Ce que les backtests précédents ne faisaient PAS :
  - le sizing : combien de la balance allouer par trade
  - le compounding : les gains s'accumulent dans la balance
  - le drawdown : la perte maximale depuis le sommet
  - le ROI en $ : le retour sur le capital INITIAL, pas sur le notionnel

La stratégie : cascade accélérée short 20x sur les 6 majeures.
  - capital initial : $1000 (ajustable)
  - position sizing : 10 % de la balance courante par trade
  - levier 20x → notionnel = 2 × la balance (10 % × 20x)
  - frais taker : 4 bps × 2 sides × le notionnel
  - slippage : 10 bps × 2 sides × le notionnel
  - funding : le taux moyen × les heures de détention × le notionnel
  - liquidation : -100 % de la marge allouée

  .venv/bin/python scripts/portfolio_sim.py --capital 1000 --size 0.10
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 20
FEE_BPS = 4        # taker par side
SLIP_BPS = 10      # slippage par side
HOLD_H = 24        # la détention en heures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=1000.0)
    ap.add_argument("--size", type=float, default=0.10,
                    help="%% de la balance alloué en marge par trade")
    args = ap.parse_args()

    con = sqlite3.connect(KDB)
    majors = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]

    # 1. collecter tous les événements cascade avec leurs prix d'entrée/sortie
    events: list[dict] = []
    for sym in majors:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        ret1 = df["close"].pct_change() * 100
        ra = ret1.abs()
        opens, closes = df["open"].values, df["close"].values
        highs, lows = df["high"].values, df["low"].values
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8
        cascade = ((ret1 < 0) & (ret1.shift(1) < 0) & (ret1.shift(2) < 0)
                   & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        for t in np.where(cascade)[0]:
            ei = t + 1
            if ei + HOLD_H >= len(idx_ns):
                continue
            entry = opens[ei]
            if entry <= 0:
                continue
            exit_j = ei + HOLD_H - 1
            if exit_j >= len(idx_ns):
                continue
            exit_px = closes[exit_j]
            price_ret_short = (entry - exit_px) / exit_px * 100  # short: (e-x)/x
            mae_adverse = (highs[ei:exit_j + 1].max() - entry) / entry * 100
            events.append({
                "sym": sym, "ts_ms": idx_ns[ei], "entry": entry,
                "exit": exit_px, "price_ret_short": price_ret_short,
                "mae_adverse": mae_adverse,
            })
    con.close()
    events.sort(key=lambda e: e["ts_ms"])

    # 2. le simulateur de portefeuille
    balance = args.capital
    peak = balance
    max_dd = 0.0
    equity_curve: list[tuple[int, float]] = []
    trade_log: list[dict] = []
    n_trades = n_liq = n_wins = 0

    # le funding moyen par symbole (approximation)
    funding_hourly: dict[str, float] = {}
    con2 = sqlite3.connect(KDB)
    for s, t, r in con2.execute("SELECT symbol, funding_time, rate FROM funding_history"):
        try:
            funding_hourly.setdefault(s, []).append(float(r))
        except (TypeError, ValueError):
            continue
    con2.close()
    for s, rates in funding_hourly.items():
        funding_hourly[s] = sum(rates) / len(rates) * 100 / 8  # %/h (8h interval)

    i = 0
    while i < len(events):
        # prendre le PREMIER trade disponible (le plus ancien pas encore traité)
        e = events[i]
        if balance <= 0:
            break

        margin_alloc = balance * args.size
        notional = margin_alloc * LEV
        entry_price = e["entry"]
        qty = notional / entry_price
        exit_price = e["exit"]
        sym = e["sym"]
        fund_rate_h = funding_hourly.get(sym, 0.0)

        # les frais d'ouverture et de fermeture (sur le notionnel)
        fees = notional * (FEE_BPS + SLIP_BPS) / 10000 * 2
        # le funding (sur le notionnel, par heure de détention)
        funding_cost = notional * fund_rate_h / 100 * HOLD_H
        # le PnL du short : (entry - exit) / exit × notional
        pnl_price = (entry_price - exit_price) / exit_price * notional
        # le PnL net = le PnL prix - les frais - le funding
        pnl = pnl_price - fees - funding_cost

        # la liquidation : si la perte ≥ la marge allouée
        liq = pnl <= -margin_alloc
        if liq:
            pnl = -margin_alloc
            n_liq += 1

        balance += pnl
        n_trades += 1
        n_wins += pnl > 0

        # le drawdown
        peak = max(peak, balance)
        dd = (peak - balance) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

        equity_curve.append((e["ts_ms"], balance))
        trade_log.append({
            "sym": sym, "ts": datetime.fromtimestamp(e["ts_ms"]/10**9, tz=timezone.utc),
            "pnl": pnl, "balance": balance, "liq": liq,
        })

        # sauter les trades qui chevauchent cette période de détention
        hold_end = e["ts_ms"] + HOLD_H * 3600 * 1000
        while i < len(events) and events[i]["ts_ms"] < hold_end:
            i += 1

    # 3. les stats
    final_balance = balance
    roi = (final_balance / args.capital - 1) * 100
    daily_rets = []
    for k in range(1, len(equity_curve)):
        prev, curr = equity_curve[k-1][1], equity_curve[k][1]
        if prev > 0:
            daily_rets.append((curr - prev) / prev)
    sharpe = 0.0
    if daily_rets and np.std(daily_rets) > 0:
        sharpe = np.mean(daily_rets) / np.std(daily_rets) * np.sqrt(365)

    lines = [
        "# LE PORTEFEUILLE — cascade accélérée short 20x sur les majeures",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — simulation sur 1 an.",
        "",
        f"| Paramètre | Valeur |",
        f"|---|---|",
        f"| Capital initial | ${args.capital:,.0f} |",
        f"| Position sizing | {args.size*100:.0f}% de la balance par trade |",
        f"| Levier | {LEV}x |",
        f"| Trades exécutés | {n_trades} |",
        f"| Trades gagnants | {n_wins} ({n_wins/max(n_trades,1)*100:.1f} %) |",
        f"| Liquidations | {n_liq} ({n_liq/max(n_trades,1)*100:.1f} %) |",
        "",
        f"| Résultat | Valeur |",
        f"|---|---|",
        f"| Balance finale | **${final_balance:,.2f}** |",
        f"| **ROI annuel** | **{roi:+.1f} %** |",
        f"| Max drawdown | {max_dd:.1f} % |",
        f"| Sharpe ratio | {sharpe:.2f} |",
        f"| PnL total | ${final_balance - args.capital:+,.2f} |",
        "",
        "La lecture : le ROI est le retour sur le CAPITAL INITIAL, avec le",
        "compounding (les gains augmentent les positions futures). Le max",
        "drawdown = la perte max depuis le sommet — c'est ce qui compte pour",
        "la survie. Un Sharpe > 1 = le rendement dépasse le risque.",
    ]

    out = REPORTS / f"portfolio-sim-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[portfolio] {n_trades} trades, balance ${final_balance:,.2f} "
          f"(ROI {roi:+.1f}%), max DD {max_dd:.1f}%, Sharpe {sharpe:.2f}")
    print(f"[portfolio] rapport: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
