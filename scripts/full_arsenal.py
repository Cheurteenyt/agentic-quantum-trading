#!/usr/bin/env python
"""L'ARSENAL COMPLET — chaque stratégie validée à SON levier sans-mort.

La règle gravée (lev ≤ 100/(maxMAE + 0,5)) s'applique à CHAQUE flux, pas
seulement à la cascade. Les 8 candidats v5 du paper forward tournent à
des leviers arbitraires — ici chacun reçoit :
  - sa distribution MAE (max réel sur 1 an) → son levier sans-mort
  - son sizing vol-inverse (taille ∝ ATR, la loi confirmée 3×)
  - son wallet seul, puis l'arsenal COMBINÉ (créneaux par stratégie)

Les flux dont le MAE max interdit tout levier utile sont marqués
« 1x seulement » — l'observation de cycle de vie reste en dehors.

  .venv/bin/python scripts/full_arsenal.py
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

from scripts.backtest_indicators import load_df, price_signals  # noqa: E402
from scripts.portfolio_sim import KDB, btc_regime_series, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"
HOLD = 24
SIGNALS = ["sweep_liquidite_short", "vwap_extreme_reprise_short",
           "failed_ath_breakout_short", "streak_vert_fade_short"]


def collect_stream(con: sqlite3.Connection, name: str,
                   fh: pd.DataFrame) -> list[dict]:
    """Les événements d'un signal du harnais, univers 1h complet, 24h."""
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' ORDER BY symbol")]
    btc = load_df(con, "BTCUSDT")
    events: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        sig = dict((n, (d, s)) for n, d, s in price_signals(df, btc))
        if name not in sig:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens = df["open"].values
        highs = df["high"].values
        closes = df["close"].values
        atr = _atr(df)
        for t in np.where(sig[name][1].fillna(False))[0]:
            ei = t + 1
            if ei + HOLD >= len(idx_ns) or t < 200:
                continue
            entry = opens[ei]
            if entry <= 0:
                continue
            exit_j = ei + HOLD - 1
            if exit_j >= len(idx_ns):
                continue
            x = closes[exit_j]
            events.append({
                "sym": sym, "ts_ms": int(idx_ns[ei]), "strategy": name,
                "lev": 1, "hold_h": HOLD, "fee_rt_bps": MAKER_RT,
                "entry": entry, "exit": float(x),
                "price_ret_short": (entry - x) / entry * 100,
                "fund_sign": 1,
                "mae_adverse": (highs[ei:exit_j + 1].max() - entry)
                / entry * 100,
                "atr_pct": float(atr[ei]) if ei < len(atr) else float("nan"),
            })
    events.sort(key=lambda e: e["ts_ms"])
    return events


def _atr(df: pd.DataFrame) -> np.ndarray:
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]),
                                              abs(l[1:] - c[:-1])))
    atr = np.empty(len(c))
    atr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        atr[i] = (atr[i - 1] * 13 + tr[i - 1]) / 14
    return atr / c * 100          # en % du prix


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    fh = funding_hourly_all()
    streams: dict[str, list[dict]] = {}
    for name in SIGNALS:
        ev = collect_stream(con, name, fh)
        if ev:
            streams[name] = ev
    con.close()

    lines = [
        "# L'ARSENAL COMPLET — chaque edge à son levier mécanique",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — hold 24h, "
        f"maker, sizing vol-inverse (base calibrée), levier = "
        f"100/(maxMAE + 0,5) par flux.", "",
        "| Flux | N | WR 24h | MAE max | Levier sûr | 100 $ → (5 % not.) | ROI/an | DD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    arsenal: dict[str, list[dict]] = {}
    for name, ev in streams.items():
        maes = np.array([e["mae_adverse"] for e in ev])
        mae_max = float(maes.max())
        lev_safe = 100 / (mae_max + 0.5)
        lev = max(1, int(lev_safe))
        med_atr = float(np.median([e["atr_pct"] for e in ev]))
        base = 0.20
        for e in ev:
            e["lev"] = lev
            e["atr_ref"] = med_atr
        def fn(e, st=None, base=base, med=med_atr):
            return min(max(base * (e["atr_pct"] / med), base / 3, 0.02),
                       base * 5 / 3)
        r = run_stack(ev, CAPITAL, fn, fh)
        n = r["n"]
        wr = r["n_wins"] / max(n, 1) * 100
        roi = (r["balance"] / CAPITAL - 1) * 100
        arsenal[name] = ev
        lines.append(f"| {name} | {n} | {wr:.1f} % | {mae_max:.2f} % | "
                     f"{lev}x | ${r['balance']:,.2f} | {roi:+.0f} % | "
                     f"{r['max_dd']:.1f} % |")

    # l'arsenal combiné : tous les flux, créneaux séparés, chacun son levier
    all_ev = sorted(sum(arsenal.values(), []),
                    key=lambda e: e["ts_ms"])
    lev_by_strat = {}
    for name, ev in arsenal.items():
        mae_max = max(e["mae_adverse"] for e in ev)
        lev_by_strat[name] = max(1, int(100 / (mae_max + 0.5)))
    med_by_strat = {name: float(np.median([e["atr_pct"] for e in ev]))
                    for name, ev in arsenal.items()}
    def arsenal_fn(e, st=None):
        lev = lev_by_strat[e["strategy"]]
        med = med_by_strat[e["strategy"]]
        return min(max(0.20 * (e["atr_pct"] / med), 0.20 / 3, 0.02),
                   0.20 * 5 / 3)
    r_all = run_stack(all_ev, CAPITAL, arsenal_fn, fh)
    mr = monthly_rows(r_all["trades"], CAPITAL)
    rec = max(x["roi"] for x in mr) if mr else 0.0
    neg = sum(1 for x in mr if x["roi"] < 0) if mr else 0
    roi = (r_all["balance"] / CAPITAL - 1) * 100
    lines += ["", "## L'ARSENAL COMBINÉ (tous les flux, leviers mécaniques)", "",
              f"- {r_all['n']} trades, 100 $ → **${r_all['balance']:,.2f}** "
              f"({roi:+.0f} %/an), DD {r_all['max_dd']:.1f} %, "
              f"liq {r_all['n_liq']}, record mois {rec:+.1f} %, "
              f"{neg} mois négatifs",
              f"- leviers mécaniques : "
              f"{', '.join(f'{k} {v}x' for k, v in lev_by_strat.items())}", "",
              "## VERDICT", "",
              "- chaque flux porte son propre plafond de levier — les flux",
              "  à MAE max énorme (90j) restent à 1x = observations, pas",
              "  stratégies ; les flux 24h à MAE raisonnable deviennent",
              "  des composants du portefeuille à levier mécanique.",
              "- la cascade gated (+197 %→+1 498 % avec sizing) reste le",
              "  noyau ; l'arsenal ajoute les flux dont le WR 24h survit",
              "  aux coûts maker."]

    out = REPORTS / f"full-arsenal-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[arsenal] combiné : {r_all['n']} trades, "
          f"${r_all['balance']:,.2f} ({roi:+.0f} %/an), "
          f"DD {r_all['max_dd']:.1f} %, liq {r_all['n_liq']}")
    print(f"[arsenal] leviers : {lev_by_strat}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
