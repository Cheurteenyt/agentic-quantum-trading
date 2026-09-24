#!/usr/bin/env python
"""LE SIMULATEUR DE PORTEFEUILLE — du signal à l'argent réel.

Ce que les backtests précédents ne faisaient PAS :
  - le sizing : combien de la balance allouer par trade
  - le compounding : les gains s'accumulent dans la balance
  - le drawdown : la perte maximale depuis le sommet
  - le ROI en $ : le retour sur le capital INITIAL, pas sur le notionnel

La stratégie : cascade accélérée short 20x, hold 24h, sans stop.
  - capital initial : $100 (défaut)
  - position sizing : % de la balance courante en marge par trade
  - levier 20x → notionnel = 20 × la marge
  - frais taker : 4 bps × 2 sides × le notionnel
  - slippage : 10 bps × 2 sides × le notionnel
  - funding : taux réel du symbole × heures de détention × notionnel
    (le SHORT REÇOIT le funding quand le taux est positif)
  - liquidation : en CHEMIN (MAE ≥ 100/lev − maintenance) OU à la sortie

Gates (options, cumulables) :
  --gate regime    : exclut le quadrant haussier/vol_haute (le massacre,
                     WR 28,5 % vs 41,3 % — les squeezes)
  --gate lifecycle : la zone de mort 7-90j + drawdown 20-50 % du ATH
                     (le filtre qui transforme la cascade de neutre à +)

BLOC STATS DE CONCLUSION — la table à reproduire à chaque verdict.

  .venv/bin/python scripts/portfolio_sim.py --capital 100 --size 0.05 \
      --universe majors --gate regime
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

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 20
FEE_BPS = 4        # taker par side
SLIP_BPS = 10      # slippage par side
MAINT_PCT = 0.5    # marge de maintenance approx (liq_params par symbole = affiné)
HOLD_H = 24        # la détention en heures
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
LIQ_MOVE_PCT = 100 / LEV - MAINT_PCT   # le mouvement adverse qui liquide


def btc_regime_series() -> pd.Series:
    """Le régime BTC (tendance EMA7j × volatilité) aligné sur l'index BTC."""
    con = sqlite3.connect(KDB)
    btc = load_df(con, "BTCUSDT")
    con.close()
    if btc is None or len(btc) < 500:
        return pd.Series(dtype=str)
    close = btc["close"]
    trend = np.where(close > close.ewm(span=7, adjust=False).mean(),
                     "haussier", "baissier")
    atr = close.diff().abs().rolling(24).mean()
    vol = np.where(atr > atr.rolling(30 * 24, min_periods=100).median(),
                   "vol_haute", "vol_basse")
    return pd.Series([f"{t}/{v}" for t, v in zip(trend, vol)], index=btc.index)


def collect_events(con: sqlite3.Connection, universe: str, gates: set[str],
                   regime: pd.Series) -> list[dict]:
    """Tous les événements cascade, filtrés par les gates demandés."""
    if universe == "majors":
        symbols = MAJORS
    else:
        symbols = [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
            "ORDER BY symbol")]
    events: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        close = df["close"]
        ret1 = close.pct_change() * 100
        ra = ret1.abs()
        cascade = ((ret1 < 0) & (ret1.shift(1) < 0) & (ret1.shift(2) < 0)
                   & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        opens = df["open"].values
        highs = df["high"].values
        idx = df.index
        idx_ns = idx.astype("datetime64[ns]").asi8

        # le cycle de vie : âge du coin + drawdown depuis l'ATH roulant
        age_days = (idx_ns - idx_ns[0]) / (86400 * 10**9)
        ath = pd.Series(highs, index=idx).cummax()
        dd = (ath - close) / ath * 100

        sym_regime = regime.reindex(idx, method="ffill", limit=48).fillna("?")

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
            exit_px = df["close"].values[exit_j]
            # short : PnL prix = (entry - exit) / entry × notionnel
            price_ret_short = (entry - exit_px) / entry * 100
            mae_adverse = (highs[ei:exit_j + 1].max() - entry) / entry * 100
            if "regime" in gates and sym_regime.iloc[t] == "haussier/vol_haute":
                continue
            if "lifecycle" in gates:
                a, d = age_days[t], dd.iloc[t]
                if not (7 <= a <= 90 and 20 <= d <= 50):
                    continue
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "entry": entry,
                "exit": exit_px, "price_ret_short": price_ret_short,
                "mae_adverse": mae_adverse,
            })
    events.sort(key=lambda e: e["ts_ms"])
    return events


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--size", type=float, default=0.05,
                    help="%% de la balance alloué en marge par trade")
    ap.add_argument("--universe", choices=["majors", "all"], default="majors")
    ap.add_argument("--gate", action="append", default=[],
                    choices=["regime", "lifecycle"])
    ap.add_argument("--maker", action="store_true",
                    help="fills maker-only (GTX) : 2 bps/side, 0 slippage")
    args = ap.parse_args()
    gates = set(args.gate)
    fee_bps, slip_bps = (2, 0) if args.maker else (FEE_BPS, SLIP_BPS)

    con = sqlite3.connect(KDB)
    funding_hourly: dict[str, float] = {}
    for s, r in con.execute("SELECT symbol, rate FROM funding_history"):
        try:
            funding_hourly.setdefault(s, []).append(float(r))
        except (TypeError, ValueError):
            continue
    for s, rates in funding_hourly.items():
        funding_hourly[s] = sum(rates) / len(rates) * 100 / 8  # %/h (8h ref)
    regime = btc_regime_series()
    events = collect_events(con, args.universe, gates, regime)
    con.close()

    # 2. le simulateur de portefeuille
    balance = args.capital
    peak = balance
    max_dd = 0.0
    trough = balance
    equity_curve: list[tuple[int, float]] = []
    trade_log: list[dict] = []
    n_trades = n_liq = n_wins = 0
    fees_total = funding_total = 0.0

    i = 0
    while i < len(events):
        e = events[i]
        if balance <= 1:   # wallet trop petit pour une marge
            break

        margin_alloc = balance * args.size
        notional = margin_alloc * LEV
        entry_price = e["entry"]
        exit_price = e["exit"]
        sym = e["sym"]
        fund_rate_h = funding_hourly.get(sym, 0.0)

        # les frais d'ouverture et de fermeture (sur le notionnel)
        fees = notional * (fee_bps + slip_bps) / 10000 * 2
        # le funding du short : il REÇOIT quand le taux est positif
        funding = notional * fund_rate_h / 100 * HOLD_H
        # le PnL du short : (entry - exit) / entry × notional
        pnl_price = e["price_ret_short"] / 100 * notional
        pnl = pnl_price + funding - fees

        # la LIQUIDATION EN CHEMIN : le MAE adverse dépasse 100/lev − maint
        liq = e["mae_adverse"] >= LIQ_MOVE_PCT or pnl <= -margin_alloc
        if liq:
            pnl = -margin_alloc
            n_liq += 1

        balance += pnl
        fees_total += fees
        funding_total += funding
        n_trades += 1
        n_wins += pnl > 0

        # le drawdown
        peak = max(peak, balance)
        dd = (peak - balance) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        trough = min(trough, balance)

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
    pnls = [t["pnl"] for t in trade_log]
    exp_trade = sum(pnls) / len(pnls) if pnls else 0.0
    rets = []
    for k in range(1, len(equity_curve)):
        prev, curr = equity_curve[k-1][1], equity_curve[k][1]
        if prev > 0:
            rets.append((curr - prev) / prev)
    sharpe = 0.0
    if rets and np.std(rets) > 0:
        sharpe = np.mean(rets) / np.std(rets) * np.sqrt(365)
    verdict = ("TRADEABLE — forward requis"
               if roi > 20 and max_dd < 60 and n_trades >= 30
               else "MARGINAL — à surveiller"
               if roi > 0 and n_trades >= 30
               else "NON TRADEABLE")

    lines = [
        "# LE PORTEFEUILLE — cascade accélérée short 20x, hold 24h",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — 1 an, "
        f"univers {args.universe}, gates: {','.join(sorted(gates)) or 'aucun'}.",
        "",
        "## BLOC STATS DE CONCLUSION", "",
        "| Stat | Valeur |", "|---|---|",
        f"| Wallet initial | ${args.capital:,.0f} |",
        f"| Wallet final | **${final_balance:,.2f}** |",
        f"| **ROI (1 an)** | **{roi:+.1f} %** |",
        f"| Trades exécutés | {n_trades} |",
        f"| Winrate | {n_wins/max(n_trades,1)*100:.1f} % |",
        f"| Liquidations (en chemin) | {n_liq} ({n_liq/max(n_trades,1)*100:.1f} %) |",
        f"| Frais + slippage payés | ${fees_total:,.2f} |",
        f"| Funding net (reçu +) | ${funding_total:+,.2f} |",
        f"| Espérance / trade | ${exp_trade:+.2f} |",
        (f"| Meilleur / pire trade | ${max(pnls):+,.2f} / ${min(pnls):+,.2f} |"
         if pnls else "| Meilleur / pire trade | — |"),
        f"| Max drawdown | {max_dd:.1f} % (creux ${trough:,.2f}) |",
        f"| Sharpe (par trade, annualisé) | {sharpe:.2f} |",
        f"| **VERDICT** | **{verdict}** |",
        "",
        f"Paramètres : sizing {args.size*100:.0f} % de la balance, levier {LEV}x,",
        f"exécution {'MAKER-only (GTX)' if args.maker else 'TAKER'}, "
        f"frais {(fee_bps+slip_bps)*2} bps RT sur notionnel "
        f"(= {(fee_bps+slip_bps)*2*LEV/100:.1f} % de marge), "
        f"liquidation en chemin à {LIQ_MOVE_PCT:.1f} % adverse.",
        "Le funding du short est REÇU quand le taux est positif (signe réel).",
    ]

    out = REPORTS / f"portfolio-sim-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[portfolio] {args.universe} gates={sorted(gates)} : "
          f"{n_trades} trades, ${args.capital:,.0f} -> ${final_balance:,.2f} "
          f"(ROI {roi:+.1f}%), DD {max_dd:.1f}%, liq {n_liq}, "
          f"frais ${fees_total:,.2f}, verdict {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
