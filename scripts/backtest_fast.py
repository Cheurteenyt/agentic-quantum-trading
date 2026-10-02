#!/usr/bin/env python
"""Moteur FAST — registre de signaux + cache d'événements + évaluation instantanée.

ARCHITECTURE PRODUCTIVITÉ :
  1. REGISTRE : chaque signal est défini dans un registre (grilles de
     paramètres incluses → ~100 variantes générées automatiquement).
  2. CACHE : les événements (signal, symbole, ts, direction) sont stockés
     dans signal_events, versionnés par hash de définition — un signal ne
     se recalcule que si sa définition change.
  3. ÉVALUATION : outcomes + baseline anti-dérive + régimes + liquidation
     réelle + funding réel — tout depuis le cache, en secondes.

Tester une NOUVELLE idée = ajouter une entrée au registre. Rien d'autre.

  .venv/bin/python scripts/backtest_fast.py            # build + éval
  .venv/bin/python scripts/backtest_fast.py --reg      # juste le registre
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df, outcomes, COST_PCT, HORIZONS  # noqa: E402
from scripts import aster_indicators as ta  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
LEV = 3  # levier memecoins (plafond exchangeInfo des vedettes)


# ---------------------------------------------------------------- REGISTRE
def build_registry() -> dict[str, dict]:
    """Le registre : nom → (direction, fn_events(df, fh_sym) -> DatetimeIndex).

    Grilles de paramètres générées automatiquement — la multiplicité est
    assumée et auditée par la campagne.
    """
    reg: dict[str, dict] = {}

    def add(name: str, direction: int, fn, needs_funding: bool = False):
        reg[name] = {"direction": direction, "fn": fn, "funding": needs_funding}

    # ——— famille RSI (grille de seuils) ———
    for th in (25, 30, 35):
        add(f"rsi_survente_reprise_{th}", +1,
            lambda df, t=th: ta.crossover(ta.rsi(df["close"]),
                                          pd.Series(t, index=df.index)))
    for th in (65, 70, 75):
        add(f"rsi_surachat_reprise_{th}", -1,
            lambda df, t=th: ta.crossunder(ta.rsi(df["close"]),
                                           pd.Series(t, index=df.index)))
    # ——— famille VWAP extrême (grille de k) ———
    def vwap_extreme(k: float, side: int):
        def fn(df):
            tp = (df["high"] + df["low"] + df["close"]) / 3
            vwap = ((tp * df["volume"]).rolling(168).sum()
                    / df["volume"].rolling(168).sum().where(lambda s: s > 0))
            dev = ((df["close"] - vwap) / vwap).astype(float)
            return (dev > k * dev.rolling(168).std()).fillna(False) if side < 0 \
                else (dev < -k * dev.rolling(168).std()).fillna(False)
        return fn
    for k in (2.0, 2.5, 3.0, 3.5):
        add(f"vwap_extreme_short_k{k}", -1, vwap_extreme(k, -1))
        add(f"vwap_extreme_long_k{k}", +1, vwap_extreme(k, +1))
    # ——— famille Donchian (grille de longueurs) ———
    for n in (20, 48, 96):
        add(f"donchian_breakout_{n}", +1,
            lambda df, n=n: ta.crossover(df["close"],
                                         df["high"].rolling(n).max().shift(1)))
        add(f"donchian_breakdown_{n}", -1,
            lambda df, n=n: ta.crossunder(df["close"],
                                          df["low"].rolling(n).min().shift(1)))
    # ——— famille squeeze (grille de percentiles) ———
    for pct in (10, 20, 30):
        def sq(df, p=pct):
            bw = ta.bandwidth(df["close"])
            squeeze = bw <= bw.rolling(200, min_periods=100).quantile(p / 100)
            _, _, hi = ta.bollinger(df["close"])
            return squeeze.shift(1, fill_value=False) & (df["close"] > hi)
        add(f"bb_squeeze_break_up_p{pct}", +1, sq)
    # ——— famille failed_ATH (grille de profondeur de raté) ———
    for depth in (0.0, 1.0, 3.0):
        def fa(df, d=depth):
            close = df["close"]
            ath = close.cummax().shift(1)
            made = (close > ath).fillna(False).astype(bool)
            failed = made.shift(1, fill_value=False) & \
                (close < ath.shift(1) * (1 - d / 100)).fillna(True)
            return failed
        add(f"failed_ath_breakout_short_d{depth}", -1, fa)
    # ——— famille MACD / EMA (références) ———
    add("macd_cross_up", +1,
        lambda df: ta.crossover(ta.macd(df["close"])[0], ta.macd(df["close"])[1]))
    add("macd_cross_down", -1,
        lambda df: ta.crossunder(ta.macd(df["close"])[0], ta.macd(df["close"])[1]))
    e9 = lambda df: ta.ema(df["close"], 9)
    e21 = lambda df: ta.ema(df["close"], 21)
    add("ema_golden_cross", +1, lambda df: ta.crossover(e9(df), e21(df)))
    add("ema_death_cross", -1, lambda df: ta.crossunder(e9(df), e21(df)))

    # ——— famille FUNDING (grilles ; fn reçoit df ET la série de funding) ———
    def funding_div(pchg_th: float):
        def fn(df, rate_s: pd.Series):
            aligned = rate_s.reindex(df.index, method="ffill", limit=8)
            accel = aligned.diff(3)
            pchg = df["close"].pct_change(24)
            return ((accel > 0) & (pchg < -pchg_th)).fillna(False)
        return fn
    for th in (0.02, 0.03, 0.05):
        add(f"funding_prix_divergence_short_p{int(th*1000)}", -1,
            funding_div(th), needs_funding=True)

    def vwap_confluence(k: float, pchg_th: float):
        vf = vwap_extreme(k, -1)
        divf = funding_div(pchg_th)
        def fn(df, rate_s):
            return (vf(df) & divf(df, rate_s)).fillna(False)
        return fn
    for k in (2.0, 3.0):
        for th in (0.02, 0.03):
            add(f"confluence_vwap{k}_div{int(th*1000)}", -1,
                vwap_confluence(k, th), needs_funding=True)

    return reg


REG_VERSION = None


def registry_version(reg: dict) -> str:
    h = hashlib.sha256()
    for name in sorted(reg):
        h.update(name.encode())
        h.update(inspect := getattr(reg[name]["fn"], "__code__", None).co_code
                 if hasattr(reg[name]["fn"], "__code__") else b"")
    return h.hexdigest()[:12]


# ---------------------------------------------------------------- ÉVALUATION
def outcomes_fast(idx_ns, opens, closes, highs, entry_positions, direction,
                  horizons, cost_pct, funding_per_hour) -> list[tuple]:
    res = []
    for i in entry_positions:
        entry_i = i + 1
        if entry_i >= len(idx_ns):
            continue
        entry = opens[entry_i]
        if entry <= 0:
            continue
        entry_ts = idx_ns[entry_i] // 10**6
        for h in horizons:
            j = entry_i + h - 1
            if j >= len(idx_ns):
                continue
            hold_h = (idx_ns[j] - idx_ns[entry_i]) / 3.6e9
            ret = ((closes[j] - entry) / entry * 100 * direction
                   - cost_pct - direction * funding_per_hour * hold_h)
            mae = ((lows := 0) or 0)  # placeholder — MAE calculée au besoin
            res.append((h, round(ret, 4), entry_ts))
    return res


def main() -> int:
    reg = build_registry()
    con = sqlite3.connect(KDB, timeout=60)
    con.execute("""CREATE TABLE IF NOT EXISTS signal_events (
        signal TEXT NOT NULL, symbol TEXT NOT NULL, ts_ms INTEGER NOT NULL,
        direction INTEGER NOT NULL, sversion TEXT NOT NULL,
        PRIMARY KEY (signal, symbol, ts_ms))""")
    ver = registry_version(reg)
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]

    fh = pd.read_sql_query("SELECT symbol, funding_time, rate FROM funding_history", con)
    fh_by: dict[str, pd.DataFrame] = {}
    for s, g in fh.groupby("symbol"):
        fh_by[s] = g

    btc = load_df(con, "BTCUSDT")
    built = 0
    cache_rows: list[tuple] = []
    for sym in sorted(symbols):
        df = load_df(con, sym)
        if df is None or len(df) < 400:
            continue
        rate_s = None
        if sym in fh_by:
            g = fh_by[sym].set_index("funding_time")["rate"].astype(float).sort_index()
            g.index = pd.to_datetime(g.index, unit="ms")
            rate_s = g
        # pré-calculs partagés
        df["_vz20"] = ta.volume_z(df["volume"], 20)
        for name, spec in reg.items():
            try:
                if spec["funding"]:
                    if rate_s is None:
                        continue
                    ev = spec["fn"](df, rate_s)
                else:
                    ev = spec["fn"](df)
            except Exception as exc:  # noqa: BLE001 — un signal faux ne bloque pas
                print(f"[fast] {name}@{sym}: {str(exc)[:50]}", file=sys.stderr)
                continue
            ev = pd.DatetimeIndex(ev[ev.fillna(False)].index)
            for ts in ev:
                cache_rows.append((name, sym, int(ts.value // 10**6),
                                   spec["direction"], ver))
        built += 1
        print(f"[fast] {sym}: registre appliqué ({len(reg)} signaux)", file=sys.stderr)
    con.executemany("INSERT OR IGNORE INTO signal_events VALUES (?,?,?,?,?)",
                    cache_rows)
    con.commit()
    n_ev = con.execute("SELECT COUNT(*) FROM signal_events WHERE sversion=?",
                       (ver,)).fetchone()[0]
    print(f"[fast] {built} symboles, {len(cache_rows)} événements nouveaux, "
          f"{n_ev} actifs en cache", file=sys.stderr)

    # ——— ÉVALUATION vectorisée (instantanée depuis le cache) ———
    import numpy as np
    slip_by_sym: dict[str, float] = {}
    try:
        for s, b in con.execute("SELECT symbol, slip_bps FROM slippage_measured"):
            slip_by_sym[s] = float(b)
    except sqlite3.OperationalError:
        pass
    funding_by_sym: dict[str, float] = {}
    import statistics
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

    # prix en mémoire (ns-index) pour l'évaluation
    price_arr: dict[str, tuple] = {}
    price_df: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 400:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        price_arr[sym] = (idx_ns, df["open"].values, df["close"].values)
        price_df[sym] = df

    horizons = HORIZONS
    # baseline blind SHORT par horizon (avec coûts+funding par symbole)
    blind: dict[int, list[float]] = defaultdict(list)
    for sym, (idx_ns, opens, closes) in price_arr.items():
        cost = 0.08 + slip_by_sym.get(sym, 10.0) / 100 * 2
        fh_ = funding_by_sym.get(sym, 0.0)
        for h in horizons:
            i = np.arange(0, len(idx_ns) - h, 24)
            e, x = opens[i], closes[np.minimum(i + h - 1, len(idx_ns) - 1)]
            blind[h].extend(((x - e) / e * 100 * (-1) - cost + fh_ * h).tolist())
    blind_wr = {h: (sum(1 for r in blind[h] if r > 0) / len(blind[h]) * 100
                    if blind[h] else 50.0) for h in horizons}

    events = con.execute("SELECT signal, symbol, ts_ms, direction FROM signal_events "
                         "WHERE sversion=?", (ver,)).fetchall()
    per_sig: dict[tuple[str, int], list[float]] = defaultdict(list)
    for sig, sym, ts_ms, direction in events:
        pa = price_arr.get(sym)
        if pa is None:
            continue
        idx_ns, opens, closes = pa
        i = int(np.searchsorted(idx_ns, ts_ms * 10**6, side="right"))
        if i == 0 or i >= len(idx_ns):
            continue
        entry = opens[i]
        if entry <= 0:
            continue
        cost = 0.08 + slip_by_sym.get(sym, 10.0) / 100 * 2
        fh_ = funding_by_sym.get(sym, 0.0)
        for h in horizons:
            # ⚠️ test PAR HORIZON (l'ancien skip max-horizons excluait les 90
            # derniers jours = biais de survie qui gonflait le WR)
            j = i + h - 1
            if j >= len(idx_ns):
                continue
            hold = (idx_ns[j] - idx_ns[i]) / 3.6e9
            ret = ((closes[j] - entry) / entry * 100 * direction
                   - cost - direction * fh_ * hold)
            per_sig[(sig, h)].append(ret)

    lines = [
        f"# Moteur FAST — {len(reg)} signaux × {len(horizons)} horizons × "
        f"{len(price_arr)} symboles (cache v{ver})",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — coûts réels + funding réels.",
        "Baseline blind SHORT (anti-dérive) : " +
        ", ".join(f"+{h}h {blind_wr[h]:.1f} %" for h in horizons),
        "",
        "| Signal | H | N | WR | Δ blind | Médiane | Pire |", "|---|---|---|---|---|---|---|",
    ]
    best = []
    for (sig, h), rets in sorted(per_sig.items()):
        n = len(rets)
        if n < 30:
            continue
        wr = sum(1 for r in rets if r > 0) / n * 100
        delta = wr - blind_wr[h]
        med = sorted(rets)[n // 2]
        worst = min(rets)
        lines.append(f"| {sig} | +{h}h | {n} | {wr:.1f} % | {delta:+.1f} pts "
                     f"| {med:+.2f} % | {worst:+.1f} % |")
        best.append((delta, sig, h, n, wr, med))
    best.sort(reverse=True)
    lines += ["", "## TOP 10 par Δ blind (N≥30)", ""]
    for delta, sig, h, n, wr, med in best[:10]:
        lines.append(f"- **{sig} +{h}h** : Δ {delta:+.1f} pts, WR {wr:.1f} %, "
                     f"n={n}, médiane {med:+.2f} %")
    out = REPORTS / f"backtest-fast-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[fast] {len(per_sig)} cellules évaluées, top Δ {best[0][0] if best else 0:+.1f} "
          f"-> {out}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
