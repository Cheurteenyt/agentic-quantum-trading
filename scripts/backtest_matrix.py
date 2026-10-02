#!/usr/bin/env python
"""LA MATRICE — tous les candidats × timeframes × leviers × liquidation réelle.

Les candidats confirmés de la campagne v5 (funding_prix_divergence,
confluence, failed_ATH, sweep, vwap_extreme) sont exécutés sur :
  - 1h : tous les symboles (1 an)
  - 15m : les 6 majeures 20x-capable
avec leviers 1x/3x/5x/10x **plafonnés par le max_leverage réel du symbole**
(liq_params) et liquidation en chemin : si l'excursion adverse atteint
100/L − maintMarginPercent, le trade meurt (-100 % marge + 2,5 % fee).

C'est la matrice définitive : signal × timeframe × levier → N, WR marge,
médiane, % liquidés, espérance. Les cellules où le levier n'existe pas
sont exclues (pas de 10x sur un symbole 3x).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df, data_ok  # noqa: E402
from scripts import aster_indicators as ta  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
COST = 0.28  # % notionnel RT (frais 8 + slippage 10/side) — modèle legacy


def price_signals_any(df, btc_close, names):
    """Les signaux price des candidats (failed_ATH, sweep, vwap) sur n'importe quel TF."""
    out = {}
    close = df["close"]
    ath_s = close.cummax().shift(1)
    made = (close > ath_s).fillna(False).astype(bool)
    if "failed_ath" in names:
        out["failed_ath"] = (-1, made.shift(1, fill_value=False)
                             & (close < ath_s.shift(1)).fillna(True))
    if "sweep" in names:
        atr = ta.atr(df, 14)
        prior_low = df["low"].rolling(20).min().shift(1)
        prior_high = df["high"].rolling(20).max().shift(1)
        out["sweep"] = (-1, ((df["high"] > prior_high + 0.15 * atr)
                             & (close < prior_high)).fillna(False))
    if "vwap" in names:
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vwap = ((tp * df["volume"]).rolling(168).sum()
                / df["volume"].rolling(168).sum().where(lambda s: s > 0))
        dev = ((df["close"] - vwap) / vwap).astype(float)
        out["vwap"] = (-1, (dev > 3 * dev.rolling(168).std()).fillna(False))
    return out


def funding_signals_any(df, fh_sym):
    """funding_prix_divergence + confluence (accélération funding × vwap)."""
    g = fh_sym.sort_values("funding_time")
    s_idx = pd.to_datetime(g["funding_time"].astype(float), unit="ms")
    rate = pd.Series(g["rate"].astype(float).values, index=s_idx)
    aligned = rate.reindex(df.index, method="ffill", limit=8)
    accel = aligned.diff(3)
    pchg = df["close"].pct_change(24)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = ((tp * df["volume"]).rolling(168).sum()
            / df["volume"].rolling(168).sum().where(lambda s: s > 0))
    dev = ((df["close"] - vwap) / vwap).astype(float)
    div = ((accel > 0) & (pchg < -0.03)).fillna(False)
    conf = (div & (dev > 3 * dev.rolling(168).std())).fillna(False)
    return {"funding_div": div, "confluence": conf}


def trade_outcomes(df, entry_positions, direction, horizons_bars, liq_p,
                   bar_hours: float = 1.0, funding_per_hour: float = 0.0):
    """Pour chaque entrée : (h, {L: ret marge}) — liquidation en chemin au
    seuil réel 100/L − maint %, funding réel pendant détention (× levier :
    le notional est L× la marge), marge perdue = -100 % − fee si liquidé."""
    idx_ns = df.index.astype("datetime64[ns]").asi8
    opens, closes = df["open"].values, df["close"].values
    lows, highs = df["low"].values, df["high"].values
    mm = liq_p["mm"] / 100
    max_lev = liq_p["max_lev"] or 0
    fee_liq = liq_p.get("fee", 0.025)
    res = []
    import numpy as _np
    bar_ns = int(bar_hours * 3600 * 10**9)
    for i in entry_positions:
        entry_i = i + 1
        if entry_i >= len(idx_ns):
            continue
        entry = opens[entry_i]
        if entry <= 0:
            continue
        entry_open_ns = idx_ns[entry_i]
        for h in horizons_bars:
            # ⚠️ la sortie par TIMESTAMP EXACT : entrée + h barres × la durée
            exit_open_ns = entry_open_ns + h * bar_ns
            j = int(_np.searchsorted(idx_ns, exit_open_ns, side="left"))
            if j >= len(idx_ns) or idx_ns[j] != exit_open_ns:
                continue
            price_ret = (closes[j] - entry) / entry * 100
            mae = ((lows[entry_i:j + 1].min() - entry) / entry * 100 if direction > 0
                   else (highs[entry_i:j + 1].max() - entry) / entry * 100)
            hold_h = (idx_ns[j] - idx_ns[entry_i]) / 3.6e9
            per_lev = {}
            for L in (1, 3, 5, 10):
                if max_lev < L:
                    continue
                th = 100.0 / L - mm * 100
                liq = (direction > 0 and mae <= -th) or (direction < 0 and mae >= th)
                if liq:
                    per_lev[L] = -100.0 - fee_liq * 100
                else:
                    per_lev[L] = (price_ret * direction * L - COST * L
                                  - direction * funding_per_hour * hold_h * L)
            res.append((h, per_lev))
    return res


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    lp = {r[0]: {"max_lev": r[1] or 0, "mm": r[2] or 0, "fee": r[3] or 0.025}
          for r in con.execute(
              "SELECT symbol, max_leverage, maint_margin_pct, liq_fee FROM liq_params")}
    fh = pd.read_sql_query("SELECT symbol, funding_time, rate FROM funding_history", con)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]
    btc = load_df(con, "BTCUSDT")

    # funding réel par symbole (taux moyen par heure, depuis funding_history)
    import statistics
    funding_by_sym: dict[str, float] = {}
    fby, fts = defaultdict(list), defaultdict(list)
    for s, t, rate in con.execute("SELECT symbol, funding_time, rate FROM funding_history"):
        try:
            fby[s].append(float(rate)); fts[s].append(float(t))
        except (TypeError, ValueError):
            continue
    for s, rates in fby.items():
        ts = sorted(fts[s])
        gaps = [(ts[i + 1] - ts[i]) / 3600000 for i in range(len(ts) - 1)
                if 0 < ts[i + 1] - ts[i] < 40000000]
        iv = statistics.median(gaps) if gaps else 8.0
        funding_by_sym[s] = (statistics.mean(rates) * 100) / max(iv, 0.5)

    H_1H = (72, 720, 1440)       # 3j / 30j / 60j
    H_15M = (96, 576, 2880)      # 24h / 72h / 30j en barres 15m

    # résultats[(famille, tf, L, horizon_h)] = liste rets marge
    R: dict[tuple, list[float]] = defaultdict(list)
    n_events = 0

    for sym in sorted(symbols):
        liq_p = lp.get(sym, {"max_lev": 0, "mm": 2.5, "fee": 0.025})
        df1h = load_df(con, sym)
        if df1h is None or not data_ok(df1h):
            continue
        # —— signaux 1h : price + funding ——
        for fam, (d, ev) in price_signals_any(df1h, btc,
                                              {"failed_ath", "sweep", "vwap"}).items():
            pos = [int(df1h.index.searchsorted(t, side="right"))
                   for t in df1h.index[ev.fillna(False)]]
            for h, per_lev in trade_outcomes(df1h, pos, d, H_1H, liq_p,
                                            1.0, funding_by_sym.get(sym, 0.0)):
                for L, ret in per_lev.items():
                    R[(fam, "1h", L, h)].append(ret)
                n_events += 1
        g = fh[fh.symbol == sym]
        if len(g) >= 30:
            for fam, mask in funding_signals_any(df1h, g).items():
                pos = [int(df1h.index.searchsorted(t, side="right"))
                       for t in df1h.index[mask]]
                for h, per_lev in trade_outcomes(df1h, pos, -1, H_1H, liq_p,
                                                1.0, funding_by_sym.get(sym, 0.0)):
                    for L, ret in per_lev.items():
                        R[(fam, "1h", L, h)].append(ret)
                    n_events += 1

    # —— 15m : les 6 majeures 20x, signaux price uniquement ——
    syms15 = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "WIFUSDT", "TURBOUSDT"]
    for sym in syms15:
        liq_p = lp.get(sym, {"max_lev": 0, "mm": 2.5, "fee": 0.025})
        rows = con.execute(
            "SELECT open_time, open, high, low, close, volume FROM klines "
            "WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
        if len(rows) < 10000:
            continue
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        for c in ("open", "high", "low", "close", "volume"):
            df[c] = pd.to_numeric(df[c])
        df = df.drop_duplicates("ts").set_index("ts").sort_index().pipe(
            lambda d: d.set_index(pd.to_datetime(d.index, unit="ms")))
        if not data_ok(df):
            continue
        sigs = price_signals_any(df, None, {"failed_ath", "sweep", "vwap"})
        for fam, (d, ev) in sigs.items():
            pos = [int(df.index.searchsorted(t, side="right"))
                   for t in df.index[ev.fillna(False)]]
            for h, per_lev in trade_outcomes(df, pos, d, H_15M, liq_p,
                                            0.25, funding_by_sym.get(sym, 0.0)):
                for L, ret in per_lev.items():
                    R[(fam, "15m", L, h * 15 // 60)].append(ret)
                n_events += 1
    con.close()

    # —— rapport : la matrice ——
    lines = [
        "# LA MATRICE — candidats × timeframes × leviers × liquidation réelle",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {n_events} exécutions "
        f"simulées. Liquidation en chemin au seuil réel 100/L − maint %, "
        f"levier plafonné par symbole. Marge perdue si liquidé = -100 % − fee.",
        "",
        "| Famille | TF | Levier | H | N | WR marge | Médiane | % liquidés | Espérance |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    best = []
    for (fam, tf, L, h), rets in sorted(R.items()):
        n = len(rets)
        if n < 30:
            continue
        wr = sum(1 for r in rets if r > 0) / n * 100
        med = sorted(rets)[n // 2]
        exp = sum(rets) / n
        n_liq = sum(1 for r in rets if r <= -99.5)
        liq_pct = n_liq / n * 100
        lines.append(f"| {fam} | {tf} | {L}x | +{h}h | {n} | {wr:.1f} % | {med:+.1f} % "
                     f"| {liq_pct:.1f} % | {exp:+.1f} % |")
        best.append((exp, fam, tf, L, h, n, wr, liq_pct))
    best.sort(reverse=True)
    lines += ["", "## TOP 10 espérance (marge par trade)", ""]
    for exp, fam, tf, L, h, n, wr, liq in best[:10]:
        lines.append(f"- **{fam} {tf} {L}x +{h}h** : espérance {exp:+.1f} %, "
                     f"WR {wr:.1f} %, liquidés {liq:.1f} % (n={n})")

    out = REPORTS / f"backtest-matrix-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[matrix] {n_events} exécutions, {len(best)} cellules -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
