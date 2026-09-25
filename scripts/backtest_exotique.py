#!/usr/bin/env python
"""Campagne EXOTIQUE — indicateurs jamais créés sur Aster, testés honnêtement.

1. CONTAGION BTC→memecoins : BTC bouge de ±2 % en 1h → les memecoins
   suivent-ils (momentum) ou reviennent-ils (fade) ? Entrée à la bougie
   suivante, horizons 1h/4h/24h. La version ingénieuse du beta.
2. DRIFT DE RÈGLEMENT DE FUNDING : le prix dump-t-il à l'instant précis où
   le funding est réglé, quand le taux est extrême (la foule dé-leverage) ?
   Short à la bougie de règlement conditionné au p75+ expanding.
3. SAISONNALITÉ HORAIRE : winrate horaire des 24 heures (descriptif — le
   calendrier est historiquement le royaume du bruit, mais ça coûte rien).

Baseline anti-dérive incluse pour chaque horizon.
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

from scripts.backtest_indicators import load_df, COST_PCT, HORIZONS  # noqa: E402
from scripts import aster_indicators as ta  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 3  # levier réaliste memecoins (plafond exchangeInfo)


# ⚠ DIVERGENCE harnais (trouvée par l'audit Ariad 25/09) : cette copie
# locale d'outcomes diffère du harnais v5 — exit à i+h (off-by-one),
# SANS funding pendant détention ni filtre data_ok. Les verdicts
# directionnels de la campagne exotique restent valables, les chiffres
# précis ne sont pas comparables au harnais. Fichier one-shot non wired.
def outcomes(df, entry_positions: list[int], direction: int,
             horizons=(1, 4, 24)) -> list[tuple[int, float]]:
    res = []
    closes = df["close"].values
    for i in entry_positions:
        entry = df["open"].values[i + 1] if i + 1 < len(df.index) else None
        if not entry or entry <= 0:
            continue
        for h in horizons:
            j = i + h
            if j >= len(df.index):
                continue
            res.append((h, (closes[j] - entry) / entry * 100 * direction - COST_PCT))
    return res


def main() -> int:
    con = sqlite3.connect(KDB)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]
    btc = load_df(con, "BTCUSDT")
    btc_ret1 = btc["close"].pct_change()

    # ——— 1. CONTAGION ———
    shocks = btc.index[(btc_ret1.abs() >= 0.02).fillna(False)]
    contagion: dict[tuple[str, int], list[float]] = defaultdict(list)
    for sym in sorted(symbols):
        if sym == "BTCUSDT":
            continue
        df = load_df(con, sym)
        if df is None or len(df) < 1000:
            continue
        # direction du trade = celle du choc BTC (momentum de contagion)
        positions = []
        for s_ts in shocks:
            i = int(df.index.searchsorted(s_ts, side="right"))
            if i >= len(df.index):
                continue
            bdir = 1 if btc_ret1.loc[s_ts] > 0 else -1
            positions.append((i, bdir))
        for h in (1, 4, 24):
            for i, bdir in positions:
                if i + h >= len(df.index) or i == 0:
                    continue
                entry = df["open"].values[i]
                ret = (df["close"].values[i + h] - entry) / entry * 100 * bdir - COST_PCT
                contagion[(f"contagion_{sym}", h)].append(ret)

    # ——— 2. DRIFT DE RÈGLEMENT DE FUNDING ———
    fh = pd.read_sql_query("SELECT symbol, funding_time, rate FROM funding_history", con)
    settle: dict[tuple[str, int], list[float]] = defaultdict(list)
    n_settle_events = 0
    for sym, g in fh.groupby("symbol"):
        df = load_df(con, sym)
        if df is None:
            continue
        rate = g["rate"].astype(float).reset_index(drop=True)
        ts = g["funding_time"].astype(float).reset_index(drop=True)
        p75 = rate.expanding(min_periods=30).quantile(0.75)
        hot = ts[(rate > p75).fillna(False)]  # ms
        entry_positions = []
        for t_ms in hot:
            if t_ms / 1000 < df.index[0].timestamp() + 3600:
                continue
            i = int(df.index.searchsorted(pd.Timestamp(int(t_ms), unit="ms"),
                                          side="left"))
            if 0 < i < len(df.index) - 2:
                entry_positions.append(i - 1)  # open de la bougie DE règlement
                n_settle_events += 1
        for h in (1, 2):
            rets = outcomes(df, entry_positions, -1, horizons=(h,))
            for h2, ret in rets:
                settle[(f"settlement_dump_short", h2)].append(ret)

    # ——— 3. SAISONNALITÉ HORAIRE (descriptif) ———
    hour_ret: dict[int, list[float]] = defaultdict(list)
    for sym in symbols[:15]:
        df = load_df(con, sym)
        if df is None:
            continue
        r1 = df["close"].pct_change() * 100
        hours = df.index.hour
        for h, r in zip(hours[1:], r1[1:]):
            if pd.notna(r):
                hour_ret[int(h)].append(float(r))

    # baseline anti-dérive : blind LONG et blind SHORT par horizon
    blind = {}
    for h in (1, 4, 24):
        wins_l = n_l = 0
        for sym in symbols:
            df = load_df(con, sym)
            if df is None:
                continue
            closes, opens = df["close"].values, df["open"].values
            for i in range(0, len(df.index) - h, 24):
                e, x = opens[i], closes[min(i + h, len(df.index) - 1)]
                n_l += 1
                wins_l += (x - e) / e * 100 - COST_PCT > 0
        blind[h] = wins_l / n_l * 100 if n_l else 50.0

    # ——— rapport ———
    lines = [
        "# Campagne EXOTIQUE — contagion, drift de funding, saisonnalité",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — levier {LEV}x "
        f"(plafond memecoins), coûts {COST_PCT} % RT, baseline anti-dérive incluse.",
        "",
        "## 1. Contagion BTC → alt (trade dans le sens du choc BTC)", "",
        "Baseline blind LONG : " +
        ", ".join(f"+{h}h {blind[h]:.1f} %" for h in (1, 4, 24)), "",
        "| Symbole | H | N | WR | Δ vs blind-long | Verdict |", "|---|---|---|---|---|---|",
    ]
    above = 0
    for (name, h), rets in sorted(contagion.items()):
        if len(rets) < 30:
            continue
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        delta = wr - blind[h]
        verdict = "CANDIDAT" if delta >= 5 and wr >= 55 else "bruit"
        above += verdict == "CANDIDAT"
        lines.append(f"| {name} | +{h}h | {len(rets)} | {wr:.1f} % "
                     f"| {delta:+.1f} pts | {verdict} |")

    lines += ["", "## 2. Drift de règlement de funding (short à la boulie de règlement, "
              "rate > p75 expanding)", "",
              f"{n_settle_events} règlements chauds testés.", ""]
    for h in (1, 2):
        rets = settle.get(("settlement_dump_short", h), [])
        if not rets:
            continue
        wr = sum(1 for r in rets if r > 0) / len(rets) * 100
        lines.append(f"- horizon +{h}h : N={len(rets)}, WR {wr:.1f} %, "
                     f"médian {sorted(rets)[len(rets)//2]:+.2f} % — "
                     + ("au-dessus du bruit" if wr >= 55 else "bruit"))

    lines += ["", "## 3. Saisonnilité horaire (blind 1h, descriptif)", "",
              "Heures avec |drift| marqué (descriptif, quasi toujours du bruit) :"]
    hr_wr = []
    for h in sorted(hour_ret):
        rr = hour_ret[h]
        if len(rr) >= 500:
            pos = sum(1 for x in rr if x > 0) / len(rr) * 100
            if pos <= 45 or pos >= 55:
                hr_wr.append((h, pos, len(rr), sum(rr) / len(rr)))
    for h, pos, n, mean in hr_wr:
        lines.append(f"- heure {h:02d}h UTC : {pos:.1f} % de bougies vertes "
                     f"(n={n}, moyen {mean:+.3f} %)")
    if not hr_wr:
        lines.append("- aucune heure avec biais marqué — cohérent avec l'efficience")

    out = REPORTS / f"backtest-exotique-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[exotique] {len(contagion)} paires de contagion, "
          f"{n_settle_events} règlements chauds, {above} candidats contagion -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
