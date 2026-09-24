#!/usr/bin/env python
"""Campagne x20 — micro-signaux sur 15m pour les symboles levier 20x.

Contrainte d'or du 20x : liquidation à ~2,5 % adverse (100/20 − maint 2,5 %
sur les majeurs). Tout signal doit donc tenir son excursion adverse sous ce
seuil pendant TOUTE la détention — on mesure le MAE de chaque trade et le
% de liquidés.

Signaux (jamais backtestés sur Aster, fenêtres ultra-courtes) :
  atr_squeeze_burst   : ATR14 au 20e percentile sur 48 barres → la barre
                        d'expansion dans son sens (compression → tir)
  mèche_rejet_long    : mèche basse ≥ 2× corps au plus bas 48 barres → snap
  volume_vide_pompe   : 8 barres sous z-vol −1,5 puis barre à z +3 → suivre
Baseline : entrées aveugles au même pas de temps (le vrai ennemi à 20x).

Sorties : ret sur MARGE (levier 20x appliqué), % liquidés, audit.
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
LEV = 20
LIQ_TH = 2.5          # % adverse → liquidation à 20x (majeurs)
COST_NOTIONAL = 0.18  # % du notionnel (frais+slippage) — ×20 sur la marge
HOLDS = (4, 8, 16)    # barres 15m : 1h, 2h, 4h


def x20_signals(df: pd.DataFrame) -> list[tuple[str, int, pd.Series]]:
    out: list[tuple[str, int, pd.Series]] = []
    close = df["close"]
    atr = ta.atr(df, 14)
    atr_p20 = atr.rolling(48, min_periods=20).quantile(0.2)
    squeeze = atr <= atr_p20
    body = (df["close"] - df["open"]).abs()
    # 1. compression → burst directionnel
    out.append(("atr_squeeze_burst_long", +1,
                squeeze.shift(1, fill_value=False)
                & (df["close"] > df["open"])
                & (df["close"] - df["open"] > atr.shift(1))))
    out.append(("atr_squeeze_burst_short", -1,
                squeeze.shift(1, fill_value=False)
                & (df["close"] < df["open"])
                & (df["open"] - df["close"] > atr.shift(1))))
    # 2. mèche de rejet au plus bas 48 barres (liquidités mangées, reprise)
    prior_low = df["low"].rolling(48).min().shift(1)
    lower_wick = (df[["open", "close"]].min(axis=1) - df["low"])
    out.append(("meche_rejet_long", +1,
                (df["low"] <= prior_low) & (lower_wick >= 2 * body)))
    # 3. FAILED ATH en 15m (cycle de vie micro) : bougie fait un nouveau
    #    plus-haut absolu, la suivante clôture sous l'ancien → short
    ath = close.cummax().shift(1)
    made_ath = close > ath
    out.append(("failed_ath_micro_short", -1,
                made_ath.shift(1, fill_value=False)
                & (close < ath.shift(1, fill_value=False))))
    # 3. volume vide → pompe
    vz = ta.volume_z(df["volume"], 48)
    dead = vz.rolling(8).max() < -1.5
    pump_up = vz > 3
    out.append(("volume_vide_pompe_long", +1,
                dead.shift(1, fill_value=False) & pump_up & (df["close"] > df["open"])))
    out.append(("volume_vide_pompe_short", -1,
                dead.shift(1, fill_value=False) & pump_up & (df["close"] < df["open"])))
    return out


def main() -> int:
    con = sqlite3.connect(KDB)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='15m'").fetchall()]
    pooled: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    base: dict[int, list[tuple[float, float]]] = defaultdict(list)
    n_combos = 0
    for sym in sorted(symbols):
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
        closes, opens = df["close"].values, df["open"].values
        lows, highs = df["low"].values, df["high"].values

        for name, direction, ev in x20_signals(df):
            n_combos += 1
            ev_store: dict[int, list] = defaultdict(list)
            for ts in df.index[ev.fillna(False)]:
                i = int(df.index.searchsorted(ts, side="right"))
                if i + max(HOLDS) >= len(df.index):
                    continue
                entry = opens[i]
                for h in HOLDS:
                    j = i + h - 1
                    if j >= len(df.index):
                        continue
                    ret_price = (closes[j] - entry) / entry * 100
                    mae = ((lows[i:j + 1].min() - entry) / entry * 100 if direction > 0
                           else (highs[i:j + 1].max() - entry) / entry * 100)
                    liq = (direction > 0 and mae <= -LIQ_TH) or \
                          (direction < 0 and mae >= LIQ_TH)
                    ret_margin = -100.0 if liq else (ret_price * direction * LEV
                                                     - COST_NOTIONAL * LEV)
                    ev_store[h].append((ret_margin, mae))
            for h, lst in ev_store.items():
                pooled[(name, h)].extend(lst)

        # baseline : entrées aveugles toutes les 8 barres (2h)
        for h in HOLDS:
            lst = []
            for i in range(0, len(df.index) - max(HOLDS), 8):
                entry = opens[i]
                j = i + h - 1
                ret_price = (closes[j] - entry) / entry * 100
                mae = ((lows[i:j + 1].min() - entry) / entry * 100)
                liq = mae <= -LIQ_TH
                lst.append((-100.0 if liq else ret_price * LEV - COST_NOTIONAL * LEV,
                            mae))
            base[h].extend(lst)
    con.close()

    lines = [
        f"# Campagne x20 — micro-signaux 15m (levier {LEV}x, liquidation à {LIQ_TH} % adverse)",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — {n_combos} signaux×symboles, "
        f"coûts {COST_NOTIONAL} % notionnel ×{LEV}.",
        "Ret = sur MARGE. Liquidé = excursion adverse ≥ seuil → marge perdue.",
        "",
        "## Signaux", "",
        "| Signal | Hold | N | WR marge | Médiane marge | % liquidés | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    confirmed = 0
    for (name, h), lst in sorted(pooled.items()):
        n = len(lst)
        if n < 30:
            continue
        rets = [r for r, _ in lst]
        liqs = [m for _, m in lst]
        n_liq = sum(1 for r, m in lst if r == -100.0)
        wins = sum(1 for r in rets if r > 0)
        wr = wins / n * 100
        med = sorted(rets)[n // 2]
        verdict = "CONFIRMÉ" if wr >= 55 and n_liq / n < 0.05 else "BRUIT"
        confirmed += verdict == "CONFIRMÉ"
        lines.append(f"| {name} | {h} barres ({h*15}m) | {n} | {wr:.1f} % "
                     f"| {med:+.1f} % | {n_liq/n*100:.1f} % | {verdict} |")
    lines += ["", "## Baseline (entrées aveugles, 2h de pas)", ""]
    for h in HOLDS:
        lst = base[h]
        rets = [r for r, _ in lst]
        n_liq = sum(1 for r, _ in lst if r == -100.0)
        wins = sum(1 for r in rets if r > 0)
        lines.append(f"- hold {h} barres ({h*15}m) : n={len(rets)}, "
                     f"WR {wins/len(rets)*100:.1f} %, liquidés {n_liq/len(rets)*100:.1f} %, "
                     f"ret moyen {sum(rets)/len(rets):+.1f} % (marge)")
    lines += [
        "", "À 20x, les coûts mangent 3,6 % de marge par aller-retour : un signal",
        "doit produire un mouvement médian ≥ 0,2 % en sa faveur pour vivre.",
        "La baseline aveugle est le vrai juge : un signal ne vaut que son écart",
        "à cette baseline (WR et % de liquidés).",
    ]

    # ——— STOP/TARGET : la géométrie du 20x (marche bougie par bougie) ———
    # stop d'abord dans la même bougie = perte (conservateur). Cible 2:1.
    STOPS = (0.8, 1.2, 1.6)
    TARGETS = (1.6, 2.4, 3.2)
    lines += ["", "## Géométrie STOP/TARGET à 20x (marche 15m, max 32 barres)", "",
              "| Signal | Stop % | Target % | N | WR target | Espérance marge |", "|---|---|---|---|---|---|"]
    n_combos_st = 0
    con = sqlite3.connect(KDB)
    for sym in sorted(symbols):
        rows = con.execute(
            "SELECT open_time, open, high, low, close, volume FROM klines "
            "WHERE symbol=? AND interval='15m' ORDER BY open_time", (sym,)).fetchall()
        if len(rows) < 10000:
            continue
        df15 = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        for c in ("open", "high", "low", "close", "volume"):
            df15[c] = pd.to_numeric(df15[c])
        df15 = df15.drop_duplicates("ts").set_index("ts").sort_index().pipe(
            lambda d: d.set_index(pd.to_datetime(d.index, unit="ms")))
        closes15, opens15 = df15["close"].values, df15["open"].values
        highs15, lows15 = df15["high"].values, df15["low"].values
        idx15 = df15.index
        for name, direction, ev in x20_signals(df15):
            ev_ts = idx15[ev.fillna(False)]
            for stop_pct in STOPS:
                for tgt_pct in TARGETS:
                    n_combos_st += 1
                    wins = losses = 0
                    ev_sum = 0.0
                    n_ev = 0
                    for ts in ev_ts:
                        i = int(idx15.searchsorted(ts, side="right"))
                        if i + 32 >= len(idx15):
                            continue
                        entry = opens15[i]
                        stop_px = entry * (1 - stop_pct / 100) if direction > 0 \
                            else entry * (1 + stop_pct / 100)
                        tgt_px = entry * (1 + tgt_pct / 100) if direction > 0 \
                            else entry * (1 - tgt_pct / 100)
                        outcome = None
                        for k in range(i, min(i + 32, len(idx15))):
                            lo, hi = lows15[k], highs15[k]
                            if direction > 0:
                                if lo <= stop_px:
                                    outcome = "stop"; break
                                if hi >= tgt_px:
                                    outcome = "target"; break
                            else:
                                if hi >= stop_px:
                                    outcome = "stop"; break
                                if lo <= tgt_px:
                                    outcome = "target"; break
                        if outcome is None:
                            continue
                        n_ev += 1
                        if outcome == "target":
                            wins += 1
                            ev_sum += (tgt_pct * LEV - COST_NOTIONAL * LEV)
                        else:
                            losses += 1
                            ev_sum += (-(stop_pct * LEV) - COST_NOTIONAL * LEV)
                    if n_ev >= 30:
                        wr = wins / n_ev * 100
                        exp = ev_sum / n_ev
                        lines.append(f"| {name} | {stop_pct} | {tgt_pct} | {n_ev} "
                                     f"| {wr:.1f} % | {exp:+.1f} % |")
    con.close()
    out = REPORTS / f"backtest-x20-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[x20] {n_combos} combinaisons, {confirmed} confirmés -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
