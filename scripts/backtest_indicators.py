#!/usr/bin/env python
"""Campagne de backtest v2 — indicateurs prix + FUNDING, régime de marché,
robustesse hors jours extrêmes. Discipline du registre, résultats complets.

NOUVEAUTÉS v2 (demandes utilisateur) :
  - 5 horizons (+1h/+4h/+12h/+24h/+72h)
  - conditionnement par RÉGIME de marché BTC (tendance haussière/baissière/
    range × volatilité haute/basse) — un signal qui ne survit qu'à un régime
    n'est pas un signal
  - ROBUSTESSE : winrate recalculé en EXCLUANT les ±6h des 5 plus gros
    mouvements quotidiens BTC — si l'edge disparaît hors crash/pump, il
    dépend d'un événement, pas d'une méthode
  - stats complètes : médiane, pire trade, meilleur (une moyenne gonflée
    par un outlier doit se voir)
  - signaux FUNDING (4,5 mois d'historique Aster) : flip, extrême-contre-
    courant, accélération

Règle CONFIRMÉ (pré-enregistrée) : pooled N≥10 & WR≥55 % en TRAIN(70 %)
ET confirmé en VAL(30 %). Audit de multiplicité annoncé.
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
COST_PCT = 0.08
TRAIN_FRAC = 0.70
HORIZONS = (1, 4, 12, 24, 72, 168, 336, 720)   # jusqu'à +30 jours
BIG_MOVE_DAYS = 5      # exclure ±6h autour des N plus gros jours BTC
BIG_MOVE_TH = 6 * 3600  # fenêtre d'exclusion en secondes
COOLDOWN_S = 24 * 3600  # 1 événement max / 24h / signal / symbole
MIN_COVERAGE = 0.90     # complétude minimale des klines du symbole
MAX_GAP_H = 6           # trou max toléré dans les klines


def selftest() -> None:
    """Le harnais PROUVE sa justesse sur des données synthétiques à issue
    connue — à chaque run. Toute dérive = abort avant les vrais chiffres."""
    idx = pd.date_range("2026-01-01", periods=50, freq="1h")
    df = pd.DataFrame({
        "open": [100.0] * 50,
        "high": [101.0] * 50,
        "low": [99.0] * 50,
        "close": [100.5] * 50,
        "volume": [1.0] * 50,
    }, index=idx)
    df.iloc[10, df.columns.get_loc("open")] = 100.0   # bougie d'entrée
    # pump de +10 % à partir de la bougie 10 : closes[10+] = 110
    df.loc[df.index[10:], "close"] = 110.0
    ev = [idx[9].timestamp()]  # signal à la bougie 9 → entrée à la bougie 10
    for h in (1, 4, 24):
        res = outcomes(df, ev, +1)
        got = [r for hh, r, _ in res if hh == h]
        expected = (110.0 - 100.0) / 100.0 * 100 - 0.08  # +10 % - coût
        assert got and abs(got[0] - expected) < 1e-9, \
            f"selftest h={h}: {got} != {expected}"
    # direction short = miroir exact
    res = outcomes(df, ev, -1)
    got = [r for hh, r, _ in res if hh == 1]
    assert abs(got[0] - (-10.0 - 0.08)) < 1e-9, f"selftest short: {got}"
    print("[selftest] harnais vérifié sur données synthétiques — OK",
          file=sys.stderr)


def data_ok(df: pd.DataFrame) -> bool:
    """Complétude : couverture ≥ MIN_COVERAGE et aucun trou > MAX_GAP_H."""
    if len(df) < 400:
        return False
    span_h = (df.index[-1] - df.index[0]).total_seconds() / 3600 + 1
    coverage = len(df) / span_h
    gaps = df.index.to_series().diff().dropna().dt.total_seconds() / 3600
    return coverage >= MIN_COVERAGE and (len(gaps) == 0 or gaps.max() <= MAX_GAP_H)


def cooldown(events_ms: pd.DatetimeIndex, cooldown_s: float = COOLDOWN_S) -> pd.DatetimeIndex:
    """Garde un événement par fenêtre de cooldown (dé-corrélation)."""
    kept: list = []
    last = None
    for ts in events_ms:
        t = ts.timestamp()
        if last is None or t - last >= cooldown_s:
            kept.append(ts)
            last = t
    return pd.DatetimeIndex(kept)


def load_df(con, symbol: str) -> pd.DataFrame | None:
    rows = con.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol = ? AND interval = '1h' ORDER BY open_time",
        (symbol,)).fetchall()
    if len(rows) < 400:
        return None
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c])
    return df.drop_duplicates("ts").set_index("ts").sort_index().pipe(
        lambda d: d.set_index(pd.to_datetime(d.index, unit="ms")))


def price_signals(df: pd.DataFrame) -> list[tuple[str, int, pd.Series]]:
    out: list[tuple[str, int, pd.Series]] = []
    close = df["close"]
    r = ta.rsi(close)
    macd_line, macd_sig = ta.macd(close)
    _, _, hi_bb = ta.bollinger(close)
    bw = ta.bandwidth(close)
    e9, e21 = ta.ema(close, 9), ta.ema(close, 21)
    k, d = ta.stoch(df)
    vz = ta.volume_z(df["volume"])
    red, green = close < df["open"], close > df["open"]
    up30 = pd.Series(30, index=close.index)
    up70 = pd.Series(70, index=close.index)
    out += [
        ("rsi_survente_reprise", +1, ta.crossover(r, up30)),
        ("rsi_surachat_reprise", -1, ta.crossunder(r, up70)),
        ("macd_cross_up", +1, ta.crossover(macd_line, macd_sig)),
        ("macd_cross_down", -1, ta.crossunder(macd_line, macd_sig)),
        ("donchian_breakout", +1, ta.crossover(close, ta.donchian_high(df))),
        ("donchian_breakdown", -1, ta.crossunder(close, ta.donchian_low(df))),
        ("bb_squeeze_break_up", +1,
         (bw <= bw.rolling(200, min_periods=100).quantile(0.2)).shift(1, fill_value=False)
         & (close > hi_bb)),
        ("ema_golden_cross", +1, ta.crossover(e9, e21)),
        ("ema_death_cross", -1, ta.crossunder(e9, e21)),
        ("stoch_survente_reprise", +1, ta.crossover(k, d) & (k.shift(1) < 20)),
        ("stoch_surachat_reprise", -1, ta.crossunder(k, d) & (k.shift(1) > 80)),
        ("vol_spike_retournement_long", +1,
         (vz > 3) & red.shift(1, fill_value=False) & green),
        ("vol_spike_retournement_short", -1,
         (vz > 3) & green.shift(1, fill_value=False) & red),
    ]
    return out


def funding_signals(fh: pd.DataFrame, btc_close: pd.Series) -> list[dict]:
    """Signaux basés sur l'historique de funding (4,5 mois).

    Chaque signal = liste de (timestamp_utc_s, direction). L'entrée se fait
    au close 1h suivant sur le symbole du funding.
    """
    out: list[dict] = []
    fh = fh.sort_values("funding_time").reset_index(drop=True)
    for sym, g in fh.groupby("symbol"):
        rate = g["rate"].astype(float)
        ts = g["funding_time"].astype(float)
        # percentiles par symbole (les niveaux absolus varient trop)
        p90 = rate.quantile(0.9)
        p10 = rate.quantile(0.1)
        events: dict[str, list[tuple[float, int]]] = defaultdict(list)
        flip_neg = (rate.shift(1) > 0) & (rate <= 0)   # crowd long se dégonfle
        flip_pos = (rate.shift(1) < 0) & (rate >= 0)
        for t in ts[flip_neg.fillna(False)]:
            events["funding_flip_neg"].append((t, -1))   # short
        for t in ts[flip_pos.fillna(False)]:
            events["funding_flip_pos"].append((t, +1))   # long
        for t in ts[rate > p90]:
            events["funding_extreme_contre_courant"].append((t, -1))  # crowded long -> short
        for t in ts[rate < p10]:
            events["funding_extreme_contre_courant"].append((t, +1))  # crowded short -> long
        acc = rate.diff(3)  # 3 funding du même sens = accélération
        for t in ts[(acc > 0) & (rate > 0)]:
            events["funding_accel_momentum"].append((t, +1))
        for k, v in events.items():
            out.append({"symbol": sym, "signal": k, "events": v})
    return out


def outcomes(df: pd.DataFrame, events, direction: int) -> list[tuple[int, float, float]]:
    """(horizon, ret %, ts_entrée_s) — entrée au close 1h APRÈS le signal."""
    import numpy as np

    res: list[tuple[int, float, float]] = []
    idx = df.index  # DatetimeIndex
    idx_ns = idx.astype("datetime64[ns]").asi8  # résolution unifiée (ns)
    opens, closes = df["open"].values, df["close"].values
    for ev_ts in events:  # secondes
        target_ns = int(float(ev_ts) * 1e9)
        i = int(np.searchsorted(idx_ns, target_ns, side="right")) - 1
        entry_i = i + 1
        if entry_i >= len(idx):
            continue
        entry = opens[entry_i]
        if entry <= 0:
            continue
        entry_ts = idx[entry_i].timestamp()
        for h in HORIZONS:
            j = entry_i + h - 1
            if j >= len(idx):
                continue
            ret = (closes[j] - entry) / entry * 100 * direction - COST_PCT
            res.append((h, ret, entry_ts))
    return res


def main() -> int:
    selftest()
    con = sqlite3.connect(KDB)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]

    btc = load_df(con, "BTCUSDT")
    assert btc is not None, "BTCUSDT 1h requis"
    btc_close = btc["close"]
    e50 = ta.ema(btc_close, 50)
    btc_trend_up = btc_close > e50
    btc_atr = ta.atr(btc) / btc_close
    atr_hi = btc_atr > btc_atr.rolling(500, min_periods=100).quantile(0.7)
    # les 5 plus gros mouvements quotidiens BTC (close-to-close)
    daily = btc_close.resample("1D").last().pct_change().abs().dropna()
    big_days = set(daily.nlargest(BIG_MOVE_DAYS).index.date)
    big_windows = [(int(pd.Timestamp(d).timestamp()), int((pd.Timestamp(d) + pd.Timedelta(days=1)).timestamp()))
                   for d in big_days]

    def in_big_window(ts_s: float) -> bool:
        return any(w0 - BIG_MOVE_TH <= ts_s <= w1 + BIG_MOVE_TH for w0, w1 in big_windows)

    import numpy as np
    btc_ns = btc.index.astype("datetime64[ns]").asi8

    def regime(ts_s: float) -> str:
        i = int(np.searchsorted(btc_ns, int(float(ts_s) * 1e9), side="right")) - 1
        if i < 0:
            return "?"
        trend = "hausse" if btc_trend_up.iloc[i] else "baisse"
        vol = "vol_haute" if atr_hi.iloc[i] else "vol_basse"
        return f"{trend}/{vol}"

    # ——— collecte des événements prix ———
    # events[(signal, horizon)] -> list[(ret, entry_ts)]
    pooled: dict[tuple[str, int], list[tuple[float, float, str]]] = defaultdict(list)
    n_combos = 0
    n_skip_data = 0
    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None or not data_ok(df):
            n_skip_data += 1
            continue
        for name, direction, ev in price_signals(df):
            n_combos += 1
            ev_s = [t.timestamp() for t in cooldown(df.index[ev.fillna(False)])]
            for h, ret, ets in outcomes(df, ev_s, direction):
                pooled[(name, h)].append((ret, ets, regime(ets)))

    # ——— événements funding (chaque événement porte sa propre direction) ———
    # ⚠️ funding_time est en MILLISECONDES : conversion en secondes ici
    fh = pd.read_sql_query("SELECT symbol, funding_time, rate FROM funding_history",
                           con)
    fund_rows: list[tuple[str, str, int, float, float]] = []
    for fsg in funding_signals(fh, btc_close):
        sym = fsg["symbol"]
        df = load_df(con, sym)
        if df is None or not data_ok(df):
            continue
        n_combos += 1
        by_dir: dict[int, list[float]] = defaultdict(list)
        for t, d in fsg["events"]:
            by_dir[d].append(t / 1000.0)  # ms -> s
        for d, ts_list in by_dir.items():
            ts_kept = cooldown(pd.DatetimeIndex(pd.to_datetime(ts_list, unit="s")))
            ts_list = [t.timestamp() for t in ts_kept]
            for h, ret, ets in outcomes(df, ts_list, d):
                fund_rows.append((fsg["signal"], sym, h, ret, ets))
    con.close()

    # fusion funding dans pooled (sous préfixe distinct)
    for sig, sym, h, ret, ets in fund_rows:
        pooled[(f"{sig}", h)].append((ret, ets, "n/a"))

    # ——— rapport ———
    lines = [
        "# Campagne backtest v2 — prix + funding, régimes, robustesse",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{n_combos} combinaisons signal×symbole, 5 horizons, coûts 8 bps.",
        "Règle CONFIRMÉ (pré-enregistrée) : pooled N≥10 & WR≥55 % en TRAIN(70 %) "
        "puis confirmé en VAL(30 %). Audit de multiplicité en fin de rapport.",
        "",
        "## Résultats poolés (tous symboles)", "",
        "| Signal | H | N | WR | Médiane | Pire | Moy | Robuste hors big-moves ? | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    confirmed, tested_cells = 0, 0
    for (name, h), evs in sorted(pooled.items()):
        rets = [r for r, _, _ in evs]
        n = len(rets)
        if n < 10:
            continue
        tested_cells += 1
        mid = len(rets) // 2
        srt = sorted(rets)
        median = srt[mid]
        worst, best = srt[0], srt[-1]
        wr_all = sum(1 for x in rets if x > 0) / n * 100
        # robustesse : exclure les big moves
        keep = [r for r, ets, _ in evs if not in_big_window(ets)]
        wr_rob = (sum(1 for x in keep if x > 0) / len(keep) * 100
                  if len(keep) >= 10 else None)
        # train/val : split par temps d'entrée sur TOUTE la période poolée
        all_ts = sorted(ets for _, ets, _ in evs)
        split_ts = all_ts[int(len(all_ts) * TRAIN_FRAC)]
        tr = [r for r, ets, _ in evs if ets < split_ts]
        va = [r for r, ets, _ in evs if ets >= split_ts]
        wr_tr = sum(1 for x in tr if x > 0) / len(tr) * 100 if len(tr) >= 10 else None
        wr_va = sum(1 for x in va if x > 0) / len(va) * 100 if len(va) >= 5 else None
        verdict = ("CONFIRMÉ" if wr_tr is not None and wr_va is not None
                   and wr_tr >= 55 and wr_va >= 55 else "BRUIT")
        confirmed += verdict == "CONFIRMÉ"
        rob_s = "—" if wr_rob is None else f"{wr_rob:.0f} %"
        lines.append(
            f"| {name} | +{h}h | {n} | {wr_all:.1f} % | {median:+.2f} % "
            f"| {worst:+.1f} % | {sum(rets)/n:+.2f} % | {rob_s} | {verdict} |")

    lines += ["", "## Régimes de marché (signaux avec N≥50)", "",
              "| Signal | H | N | Hausse | Baisse | Vol haute | Vol basse |", "|---|---|---|---|---|---|---|"]
    for (name, h), evs in sorted(pooled.items()):
        if len(evs) < 50:
            continue
        by_reg: dict[str, list[float]] = defaultdict(list)
        for r, _, reg in evs:
            if reg != "n/a":
                by_reg[reg].append(r)
        if not by_reg:
            continue
        cells = []
        for reg in ("hausse/vol_basse", "hausse/vol_haute", "baisse/vol_basse", "baisse/vol_haute"):
            rr = by_reg.get(reg, [])
            cells.append(f"{sum(1 for x in rr if x > 0)/len(rr)*100:.0f} % (n={len(rr)})"
                         if len(rr) >= 15 else "—")
        lines.append(f"| {name} | +{h}h | {len(evs)} | " + " | ".join(cells) + " |")

    expected = tested_cells * 0.025
    lines += [
        "", "## Audit de multiplicité", "",
        f"- cellules signal×horizon testées : {tested_cells}",
        f"- confirmés poolés : {confirmed} (attendus par hasard ≈ {expected:.0f})",
        "- VERDICT GLOBAL : " + (
            "à examiner manuellement — au-dessus du hasard ×2"
            if confirmed > expected * 2 and confirmed > 0 else
            "aucun edge démontré — cohérent avec la culture des résultats nuls"),
        "",
        "Rappel : un signal « robuste » doit garder son WR hors big-moves ET",
        "sur plusieurs régimes. Tout le reste = bruit, et on le dit.",
    ]

    out = REPORTS / f"backtest-campagne-v2-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[campagne] {n_combos} combinaisons, {tested_cells} cellules, "
          f"{confirmed} confirmés -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
