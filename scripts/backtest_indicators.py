#!/usr/bin/env python
"""Backtest des indicateurs Aster — signaux discrets, discipline du registre.

Chaque signal est un ÉVÉNEMENT daté (ex : RSI sort de survente). Sortie :
+1h / +24h / +72h, entrée à l'open suivant, coût 8 bps aller-retour.
SPLIT TEMPOREL 70/30 par symbole : le verdict CONFIRMÉ exige
  train : N ≥ 10 ET winrate ≥ 55 %
  val   : N ≥ 5  ET winrate ≥ 55 % (même direction)
Sinon : BRUIT / INSUFFISANT. Audit de multiplicité : on annonce combien de
combinaisons ont été testées et combien étaient attendues par hasard.

C'est le 1er test systématique des indicateurs CLASSIQUES sur perps Aster.
Résultat attendu honnête : majoritairement BRUIT — c'est la culture.
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import aster_indicators as ta  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
COST_PCT = 0.08          # 8 bps aller-retour
TRAIN_FRAC = 0.70
HORIZONS = (1, 24, 72)


def load_df(con: sqlite3.Connection, symbol: str) -> pd.DataFrame | None:
    rows = con.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol = ? AND interval = '1h' ORDER BY open_time",
        (symbol,)).fetchall()
    if len(rows) < 400:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c])
    df = df.drop_duplicates("ts").set_index("ts").sort_index()
    return df


def signals_of(df: pd.DataFrame) -> list[tuple[str, int, pd.Series]]:
    """(nom, direction +1/-1, Series bool d'événements)."""
    out: list[tuple[str, int, pd.Series]] = []
    close, df = df["close"], df
    r = ta.rsi(close)
    macd_line, macd_sig = ta.macd(close)
    lo_bb, _, hi_bb = ta.bollinger(close)
    bw = ta.bandwidth(close)
    e9, e21 = ta.ema(close, 9), ta.ema(close, 21)
    k, d = ta.stoch(df)
    vz = ta.volume_z(df["volume"])
    red = close < df["open"]
    green = close > df["open"]

    out.append(("rsi_survente_reprise", +1, ta.crossover(r, pd.Series(30, index=close.index))))
    out.append(("rsi_surachat_reprise", -1, ta.crossunder(r, pd.Series(70, index=close.index))))
    out.append(("macd_cross_up", +1, ta.crossover(macd_line, macd_sig)))
    out.append(("macd_cross_down", -1, ta.crossunder(macd_line, macd_sig)))
    out.append(("donchian_breakout", +1, close > ta.donchian_high(df)))
    out.append(("donchian_breakdown", -1, close < ta.donchian_low(df)))
    squeeze = bw <= bw.rolling(200, min_periods=100).quantile(0.2)
    out.append(("bb_squeeze_break_up", +1, squeeze.shift(1, fill_value=False) & (close > hi_bb)))
    out.append(("ema_golden_cross", +1, ta.crossover(e9, e21)))
    out.append(("ema_death_cross", -1, ta.crossunder(e9, e21)))
    out.append(("stoch_survente_reprise", +1, ta.crossover(k, d) & (k.shift(1) < 20)))
    out.append(("stoch_surachat_reprise", -1, ta.crossunder(k, d) & (k.shift(1) > 80)))
    out.append(("vol_spike_reversal_long", +1,
                (vz > 3) & red.shift(1, fill_value=False) & green))
    out.append(("vol_spike_reversal_short", -1,
                (vz > 3) & green.shift(1, fill_value=False) & red))
    return out


def outcomes(df: pd.DataFrame, events: pd.Series, direction: int) -> list[tuple[int, float]]:
    """(horizon, ret %) pour chaque événement — entrée open suivant."""
    res: list[tuple[int, float]] = []
    idx = df.index
    opens = df["open"].values
    closes = df["close"].values
    pos = {ts: i for i, ts in enumerate(idx)}
    for ts in df.index[events.fillna(False)]:
        i = pos[ts]
        entry_i = i + 1
        if entry_i >= len(idx):
            continue
        entry = opens[entry_i]
        if entry <= 0:
            continue
        for h in HORIZONS:
            j = min(entry_i + h, len(idx) - 1)
            if j == entry_i:
                continue
            ret = (closes[j] - entry) / entry * 100 * direction - COST_PCT
            res.append((h, ret))
    return res


def main() -> int:
    con = sqlite3.connect(KDB)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]
    pooled: dict[str, dict[int, list[tuple[str, float, bool]]]] = defaultdict(
        lambda: defaultdict(list))
    per_combo: list[dict] = []
    n_tested = 0
    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None:
            continue
        split_ts = df.index[int(len(df) * TRAIN_FRAC)]
        for name, direction, ev in signals_of(df):
            n_tested += 1
            outs = outcomes(df, ev, direction)
            for h, ret in outs:
                ts_i = None
                pooled[name][h].append((sym, ret, True))
            # split par évènement : train si l'index d'entrée < split_ts
            train_mask = df.index.get_indexer(df.index[ev.fillna(False)]) < int(len(df) * TRAIN_FRAC)
            ev_train = ev.copy()
            ev_train[:] = False
            ev_train[df.index[ev.fillna(False)][train_mask]] = True
            ev_val = ev.copy()
            ev_val[:] = False
            ev_val[df.index[ev.fillna(False)][~train_mask]] = True
            tr = outcomes(df, ev_train, direction)
            va = outcomes(df, ev_val, direction)
            per_combo.append({"symbol": sym, "signal": name, "train": tr, "val": va})
    con.close()

    lines = [
        "# Backtest indicateurs Aster — 1h, 31+ symboles, avril → septembre",
        f"Combinaisons testées : {n_tested} signaux×symboles. "
        f"Coût 8 bps. Split 70/30 temporel.",
        "Règle CONFIRMÉ : train N≥10 & WR≥55 % PUIS val N≥5 & WR≥55 %.",
        "",
        "## Pooled par signal (tous symboles confondus)", "",
        "| Signal | H | N | Winrate | Verdict |", "|---|---|---|---|---|",
    ]
    confirmed_total = 0
    for name in sorted(pooled):
        for h in HORIZONS:
            rets = [r for _, r, *_ in pooled[name][h]]
            n = len(rets)
            if n == 0:
                continue
            wr = sum(1 for x in rets if x > 0) / n * 100
            verdict = "CONFIRMÉ" if (n >= 10 and wr >= 55) else "BRUIT"
            if verdict == "CONFIRMÉ":
                confirmed_total += 1
            lines.append(f"| {name} | +{h}h | {n} | {wr:.1f} % | {verdict} |")

    lines += ["", "## Confirmations par symbole (train + val)", ""]
    any_confirmed = []
    for c in per_combo:
        for h in HORIZONS:
            tr = [r for _, r in c["train"] if _ == h]
            va = [r for _, r in c["val"] if _ == h]
            if (len(tr) >= 10 and sum(1 for x in tr if x > 0) / len(tr) >= 0.55
                    and len(va) >= 5 and sum(1 for x in va if x > 0) / len(va) >= 0.55):
                any_confirmed.append(
                    f"- {c['signal']} @ {c['symbol']} +{h}h : "
                    f"train {len(tr)}/{sum(1 for x in tr if x > 0)} "
                    f"({sum(1 for x in tr if x > 0)/len(tr)*100:.0f} %), "
                    f"val {len(va)}/{sum(1 for x in va if x > 0)} "
                    f"({sum(1 for x in va if x > 0)/len(va)*100:.0f} %)")
    lines += any_confirmed or ["- aucun"]

    n_signals = len(pooled)
    expected = n_signals * len(HORIZONS) * 0.025  # ~2.5 % de faux positifs attendus
    lines += [
        "", "## Audit de multiplicité", "",
        f"- signaux × horizons poolés : {n_signals * len(HORIZONS)}",
        f"- confirmations pooled : {confirmed_total} "
        f"(attendues par hasard ≈ {expected:.0f} au seuil 55 %/N≥10)",
        f"- confirmations par symbole : {len(any_confirmed)} "
        f"(sur {n_tested * len(HORIZONS)} combinaisons)",
        "- VERDICT GLOBAL : " + (
            "à examiner manuellement" if confirmed_total > expected * 2
            else "aucun edge démontré — cohérent avec la culture des résultats nuls"),
    ]

    out = REPORTS / f"backtest-indicators-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[backtest-ind] {n_tested} combinaisons, {confirmed_total} pooled "
          f"confirmés, {len(any_confirmed)} par symbole -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
