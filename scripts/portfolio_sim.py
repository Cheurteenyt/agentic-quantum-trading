#!/usr/bin/env python
"""LE SIMULATEUR DE PORTEFEUILLE — du signal à l'argent réel, mois par mois.

La stratégie : cascade accélérée short 20x, hold 24h, sans stop.
  - capital initial : $100 (défaut)
  - position sizing : % de la balance courante en marge par trade
  - levier 20x → notionnel = 20 × la marge
  - frais taker 4 bps / maker 2 bps par side ×2, slippage taker 10 bps/side
  - funding : taux réel du symbole × heures de détention × notionnel
    (le SHORT REÇOIT le funding quand le taux est positif)
  - liquidation : en CHEMIN (MAE ≥ 100/lev − maintenance) OU à la sortie

DEUX SIMULATIONS par run :
  1. RÉELLE   — tous les trades, liquidations en chemin appliquées
  2. ORACLE   — les trades qui se feraient liquider ne sont PAS pris
                (impossible en pratique : c'est le PLAFOND du signal,
                 la borne « ceux qui se font pas liquidé »)

GARDE-FOUS ANTI-BUG du ROI (affichés à chaque run) :
  - le bucketing mensuel se fait par l'heure de SORTIE (le pnl atterrit
    à la fermeture, pas à l'entrée)
  - produit des (1+ROI_mensuel) vs balance finale/capitale — écart > 0,5 %
    = BUG affiché
  - somme des PnL mensuels vs PnL total — écart > 0,01 $ = BUG affiché

  .venv/bin/python scripts/portfolio_sim.py --capital 100 --size 0.03 \
      --universe majors --maker
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
MAKER_BPS = 2      # maker par side (GTX), slippage ~0
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


def run_sim(events: list[dict], capital: float, size: float,
            funding_hourly: dict[str, float], fee_bps: int, slip_bps: int,
            oracle: bool = False, size_fn=None) -> dict:
    """La simulation séquentielle. oracle=True : les trades voués à la
    liquidation ne sont pas pris (plafond théorique, pnl=0, pas de frais).
    size_fn(e) -> taille (0-1) par trade : remplace le sizing fixe."""
    balance = capital
    peak = trough = balance
    max_dd = 0.0
    equity: list[tuple[int, float]] = []
    trades: list[dict] = []
    n = n_liq = n_wins = 0
    fees_tot = fund_tot = 0.0

    i = 0
    while i < len(events):
        e = events[i]
        if balance <= 1:
            break
        trade_size = size_fn(e) if size_fn is not None else size
        if trade_size <= 0:
            i += 1               # gated : le créneau est libéré pour le suivant
            continue
        margin_alloc = balance * trade_size
        notional = margin_alloc * LEV
        fees = notional * (fee_bps + slip_bps) / 10000 * 2
        funding = notional * funding_hourly.get(e["sym"], 0.0) / 100 * HOLD_H
        pnl = e["price_ret_short"] / 100 * notional + funding - fees

        liq = e["mae_adverse"] >= LIQ_MOVE_PCT or pnl <= -margin_alloc
        if liq and oracle:
            pnl = 0.0            # l'oracle n'a pas pris le trade
            liq = False
        elif liq:
            pnl = -margin_alloc
            n_liq += 1

        balance += pnl
        if not oracle:
            fees_tot += fees
            fund_tot += funding
        n += 1
        n_wins += pnl > 0

        peak = max(peak, balance)
        dd = (peak - balance) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        trough = min(trough, balance)

        exit_ms = e["ts_ms"] + HOLD_H * 3600 * 10**9   # ts_ms = des NS (nom hérité)
        equity.append((exit_ms, balance))
        trades.append({
            "sym": e["sym"],
            "exit_ts": datetime.fromtimestamp(exit_ms / 10**9, tz=timezone.utc),
            "pnl": pnl, "balance": balance, "liq": liq,
        })
        hold_end = e["ts_ms"] + HOLD_H * 3600 * 10**9  # ts_ms = des NS (nom hérité)
        while i < len(events) and events[i]["ts_ms"] < hold_end:
            i += 1

    return {"balance": balance, "max_dd": max_dd, "trough": trough,
            "equity": equity, "trades": trades, "n": n, "n_liq": n_liq,
            "n_wins": n_wins, "fees": fees_tot, "funding": fund_tot}


def monthly_rows(trades: list[dict], capital: float) -> list[dict]:
    """Décomposition mensuelle par heure de SORTIE (le pnl atterrit là)."""
    rows: dict[str, dict] = {}
    for t in sorted(trades, key=lambda x: x["exit_ts"]):
        m = t["exit_ts"].strftime("%Y-%m")
        r = rows.setdefault(m, {"pnl": 0.0, "n": 0, "w": 0, "liq": 0,
                                "nonliq_n": 0, "nonliq_w": 0, "nonliq_pnl": 0.0})
        r["pnl"] += t["pnl"]
        r["n"] += 1
        r["w"] += t["pnl"] > 0
        r["liq"] += t["liq"]
        if not t["liq"]:
            r["nonliq_n"] += 1
            r["nonliq_w"] += t["pnl"] > 0
            r["nonliq_pnl"] += t["pnl"]
    out, bal = [], capital
    for m in sorted(rows):
        r = rows[m]
        start = bal
        bal += r["pnl"]
        out.append({"month": m, **r, "start": start, "end": bal,
                    "roi": (r["pnl"] / start * 100) if start > 0 else 0.0})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--size", type=float, default=0.05,
                    help="%% de la balance alloué en marge par trade")
    ap.add_argument("--universe", choices=["majors", "all"], default="majors")
    ap.add_argument("--maker", action="store_true",
                    help="fills maker-only (GTX) : 2 bps/side, 0 slippage")
    args = ap.parse_args()
    fee_bps, slip_bps = (MAKER_BPS, 0) if args.maker else (FEE_BPS, SLIP_BPS)

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
    # UN SEUL collecteur cascade (anti_liq) — la divergence des deux
    # collecteurs (warmup + features) produisait deux vérités (25/09)
    # import paresseux : anti_liq importe run_sim de ce module
    from scripts.anti_liq import collect_featured
    events = collect_featured(regime, args.universe)
    con.close()

    real = run_sim(events, args.capital, args.size, funding_hourly,
                   fee_bps, slip_bps, oracle=False)
    oracle = run_sim(events, args.capital, args.size, funding_hourly,
                     fee_bps, slip_bps, oracle=True)

    mrows = monthly_rows(real["trades"], args.capital)
    orows = monthly_rows(oracle["trades"], args.capital)
    if not mrows:
        out = REPORTS / f"portfolio-sim-{datetime.now(timezone.utc):%Y-%m-%d}.md"
        REPORTS.mkdir(exist_ok=True)
        out.write_text("# LE PORTEFEUILLE — aucun trade ce soir "
                       "(klines absentes ? vérifier le fetch nocturne)\n",
                       encoding="utf-8")
        print("[portfolio] aucun trade — klines absentes ? vérifier le fetch")
        return 0

    # --- GARDE-FOUS ANTI-BUG ---
    checks: list[str] = []
    prod_roi = 1.0
    for r in mrows:
        prod_roi *= (1 + r["roi"] / 100)
    gap = abs(prod_roi - real["balance"] / args.capital)
    checks.append(f"composé des mois vs final : écart {gap*100:.3f} % "
                  + ("OK" if gap < 0.005 else "✗ BUG"))
    sum_pnl = sum(r["pnl"] for r in mrows)
    pnl_gap = abs(sum_pnl - (real["balance"] - args.capital))
    checks.append(f"somme PnL mensuels vs total : écart ${pnl_gap:.4f} "
                  + ("OK" if pnl_gap < 0.01 else "✗ BUG"))

    def fmt_table(rows: list[dict], label: str) -> list[str]:
        ls = [f"### {label}", "",
              "| Mois | Trades | WR | Liq | Balance début → fin | ROI mois | ROI cumulé |",
              "|---|---|---|---|---|---|---|"]
        cap = args.capital
        for r in rows:
            cum = (r["end"] / cap - 1) * 100
            ls.append(
                f"| {r['month']} | {r['n']} | {r['w']/max(r['n'],1)*100:.0f} % "
                f"| {r['liq']} | ${r['start']:,.0f} → ${r['end']:,.0f} "
                f"| {r['roi']:+.1f} % | {cum:+.1f} % |")
        return ls

    pnls = [t["pnl"] for t in real["trades"]]
    exp_trade = sum(pnls) / len(pnls) if pnls else 0.0
    rois_m = [r["roi"] for r in mrows]
    neg_months = sum(1 for x in rois_m if x < 0)
    verdict = ("TRADEABLE — forward requis"
               if real["balance"] / args.capital > 1.2 and real["max_dd"] < 60
               and real["n"] >= 30 else "MARGINAL — à surveiller"
               if real["balance"] > args.capital and real["n"] >= 30
               else "NON TRADEABLE")

    lines = [
        "# LE PORTEFEUILLE — cascade accélérée short 20x, hold 24h",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — 1 an, "
        f"univers {args.universe}, "
        f"exécution {'MAKER (GTX)' if args.maker else 'TAKER'}, "
        f"sizing {args.size*100:.0f} %, capital ${args.capital:,.0f}.",
        "", "## GARDE-FOUS ANTI-BUG", "",
    ] + [f"- {c}" for c in checks] + [
        "", "## BLOC STATS DE CONCLUSION (RÉEL)", "",
        "| Stat | Valeur |", "|---|---|",
        f"| Wallet initial → final | ${args.capital:,.0f} → **${real['balance']:,.2f}** |",
        f"| **ROI (1 an)** | **{(real['balance']/args.capital-1)*100:+.1f} %** |",
        f"| ROI mensuel moyen | {np.mean(rois_m):+.1f} % "
        f"(pire {min(rois_m):+.1f} %, meilleur {max(rois_m):+.1f} %, "
        f"{neg_months} mois négatifs) |",
        f"| Trades / Winrate | {real['n']} / {real['n_wins']/max(real['n'],1)*100:.1f} % |",
        f"| Liquidations (en chemin) | {real['n_liq']} "
        f"({real['n_liq']/max(real['n'],1)*100:.1f} %) |",
        f"| Frais + slippage payés | ${real['fees']:,.2f} |",
        f"| Funding net (reçu +) | ${real['funding']:+,.2f} |",
        f"| Espérance / trade | ${exp_trade:+.2f} |",
        (f"| Meilleur / pire trade | ${max(pnls):+,.2f} / ${min(pnls):+,.2f} |"
         if pnls else "| Meilleur / pire trade | — |"),
        f"| Max drawdown | {real['max_dd']:.1f} % (creux ${real['trough']:,.2f}) |",
        f"| **VERDICT** | **{verdict}** |",
        "", f"## ORACLE ANTI-LIQUIDATION — le plafond « ceux qui se font pas liquidé »",
        f"", f"Les {real['n_liq']} trades que la sim RÉELLE liquide en chemin "
        f"ne sont pas pris ici (impossible en pratique) :",
        f"wallet ${args.capital:,.0f} → **${oracle['balance']:,.2f}** "
        f"(ROI {(oracle['balance']/args.capital-1)*100:+.1f} %), "
        f"DD {oracle['max_dd']:.1f} %, WR {oracle['n_wins']/max(oracle['n'],1)*100:.1f} %, "
        f"moyenne mensuelle "
        f"{np.mean([r['roi'] for r in orows]):+.1f} % "
        f"(pire {min(r['roi'] for r in orows):+.1f} %).",
        f"Sur les SEULS trades non liquidés (stat ex-post) : WR "
        f"{sum(1 for t in real['trades'] if not t['liq'] and t['pnl']>0)/max(sum(1 for t in real['trades'] if not t['liq']),1)*100:.1f} %, "
        f"pnl moyen ${sum(t['pnl'] for t in real['trades'] if not t['liq'])/max(sum(1 for t in real['trades'] if not t['liq']),1):+.2f}.",
    ] + fmt_table(mrows, "RÉEL — ROI par mois (bucketing par sortie)") \
      + [""] + fmt_table(orows, "ORACLE anti-liquidation — par mois") + [
        "", "Paramètres : levier 20x, "
        f"frais {(fee_bps+slip_bps)*2} bps RT sur notionnel "
        f"(= {(fee_bps+slip_bps)*2*LEV/100:.1f} % de marge), "
        f"liquidation en chemin à {LIQ_MOVE_PCT:.1f} % adverse, hold {HOLD_H}h.",
        "L'oracle anti-liquidation = un plafond, PAS une stratégie : personne",
        "ne sait ex ante quel trade sera liquidé. L'écart réel ↔ oracle = le",
        "coût exact des liquidations.",
    ]

    out = REPORTS / f"portfolio-sim-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[portfolio] {args.universe} "
          f"{'maker' if args.maker else 'taker'} size={args.size:.0%} : "
          f"RÉEL ${args.capital:,.0f}→${real['balance']:,.2f} "
          f"({(real['balance']/args.capital-1)*100:+.1f}%/an, "
          f"moy. mensuelle {np.mean(rois_m):+.1f}%, DD {real['max_dd']:.1f}%, "
          f"liq {real['n_liq']}) | ORACLE ${oracle['balance']:,.2f} "
          f"({(oracle['balance']/args.capital-1)*100:+.1f}%/an, "
          f"moy. mensuelle {np.mean([r['roi'] for r in orows]):+.1f}%)")
    for c in checks:
        print(f"[portfolio] garde-fou : {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
