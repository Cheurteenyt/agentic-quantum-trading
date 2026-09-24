#!/usr/bin/env python
"""Paper-trading FORWARD — les 5 candidats jugés sur les données de demain.

Chaque nuit : détecte les événements frais (< 48h) des 5 signaux candidats
issus de la campagne v5 (au-dessus du drift, coûts+funding réels), ouvre un
paper trade à l'open suivant, et CLÔT les trades dont l'horizon est écoulé
avec les prix RÉELS. Le ledger cumulatif = le vrai juge : si un candidat ne
survit pas en forward, il sort — sans réécriture de l'histoire.

Ledger : klines.db:paper_trades. Rapport : reports/paper-forward-<date>.md
"""
from __future__ import annotations

import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import (  # noqa: E402
    load_df, price_signals, COST_PCT, HORIZONS,
)
from scripts import aster_indicators as ta  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"

# les 5 candidats de la campagne v5 : (signal, horizon_h, direction)
CANDIDATES = [
    ("funding_div_plus_vwap_short", 24, -1),   # la confluence vedette (v6)
    ("funding_div_plus_vwap_short", 168, -1),
    ("funding_prix_divergence_short", 12, -1),
    ("funding_extreme_contre_courant", 168, -1),
    ("vwap_extreme_reprise_short", 1440, -1),
    ("vwap_extreme_reprise_short", 2160, -1),
    ("sweep_liquidite_short", 2160, -1),
]
WINDOW_H = 48  # on détecte les événements des 48 dernières heures


def load_env_funding_stats(con: sqlite3.Connection) -> dict[str, float]:
    """taux de funding moyen PAR HEURE par symbole (comme le harnais)."""
    import statistics
    by_sym: dict[str, list[float]] = defaultdict(list)
    by_ts: dict[str, list[float]] = defaultdict(list)
    for s, t, rate in con.execute("SELECT symbol, funding_time, rate FROM funding_history"):
        try:
            by_sym[s].append(float(rate))
            by_ts[s].append(float(t))
        except (TypeError, ValueError):
            continue
    out: dict[str, float] = {}
    for s, rates in by_sym.items():
        ts = sorted(by_ts[s])
        gaps = [(ts[i + 1] - ts[i]) / 3600000 for i in range(len(ts) - 1)
                if 0 < ts[i + 1] - ts[i] < 40000000]
        iv = statistics.median(gaps) if gaps else 8.0
        out[s] = (statistics.mean(rates) * 100) / max(iv, 0.5)
    return out


def funding_div_mask(df: pd.DataFrame, fh_sym: pd.DataFrame) -> pd.Series:
    """funding_prix_divergence_short : funding qui accélère + prix -3 %/24h."""
    rate = fh_sym.set_index("funding_time")["rate"].astype(float).sort_index()
    rate.index = pd.to_datetime(rate.index, unit="ms")
    aligned = rate.reindex(df.index, method="ffill", limit=8)
    accel = aligned.diff(3)
    pchg = df["close"].pct_change(24)
    return ((accel > 0) & (pchg < -0.03)).fillna(False)


def funding_extreme_events(fh_sym: pd.DataFrame) -> pd.DatetimeIndex:
    """funding_extreme_contre_courant : rate > p90 EXPANDING (anti look-ahead)."""
    rate = fh_sym["rate"].astype(float)
    ts = fh_sym["funding_time"].astype(float)
    p90 = rate.expanding(min_periods=30).quantile(0.9)
    return pd.DatetimeIndex(ts[(rate > p90).fillna(False)] * 10**6)


def main() -> int:
    con = sqlite3.connect(KDB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS paper_trades (
        signal TEXT NOT NULL, symbol TEXT NOT NULL, horizon_h INTEGER NOT NULL,
        direction INTEGER NOT NULL, signal_ts INTEGER NOT NULL,
        entry_ts INTEGER NOT NULL, entry_price REAL NOT NULL,
        exit_ts INTEGER, exit_price REAL, ret_pct REAL,
        funding_pct REAL, status TEXT NOT NULL, created_at REAL NOT NULL,
        PRIMARY KEY (signal, symbol, signal_ts));
    """)
    now = time.time()
    now_ms = int(now * 1000)
    since_ms = now_ms - WINDOW_H * 3600 * 1000

    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'").fetchall()]
    funding_stats = load_env_funding_stats(con)
    fh = pd.read_sql_query("SELECT symbol, funding_time, rate FROM funding_history", con)
    btc = load_df(con, "BTCUSDT")

    opened = closed_n = 0
    for name, horizon, direction in CANDIDATES:
        for sym in sorted(symbols):
            df = load_df(con, sym)
            if df is None or len(df) < 400:
                continue
            fh_sym = fh[fh.symbol == sym]
            if name in ("funding_prix_divergence_short",
                        "funding_div_plus_vwap_short"):
                if fh_sym.empty:
                    continue
                mask = funding_div_mask(df, fh_sym)
                if name == "funding_div_plus_vwap_short":
                    tp = (df["high"] + df["low"] + df["close"]) / 3
                    vwap = ((tp * df["volume"]).rolling(168).sum()
                            / df["volume"].rolling(168).sum().replace(0, pd.NA))
                    dev = ((df["close"] - vwap) / vwap).astype(float)
                    mask = mask & (dev > 3 * dev.rolling(168).std()).fillna(False)
                ev = df.index[mask]
            elif name == "funding_extreme_contre_courant":
                if fh_sym.empty:
                    continue
                ev = funding_extreme_events(fh_sym)
            else:
                sig = dict((n, (d, s)) for n, d, s in price_signals(df, btc))
                if name not in sig:
                    continue
                ev = df.index[sig[name][1].fillna(False)]
            # événements frais uniquement
            ev = pd.DatetimeIndex([t for t in ev if t.timestamp() * 1000 >= since_ms])
            for ts in ev:
                sig_ts = int(ts.timestamp() * 1000)
                if con.execute(
                    "SELECT 1 FROM paper_trades WHERE signal=? AND symbol=? "
                    "AND signal_ts=?", (name, sym, sig_ts)).fetchone():
                    continue
                i = int(df.index.searchsorted(ts, side="right"))
                if i >= len(df.index):
                    continue
                entry_i = i  # l'open de la bougie suivante = bougie i ici
                entry_ts = int(df.index[entry_i].timestamp() * 1000)
                entry_price = float(df["open"].iloc[entry_i])
                if entry_price <= 0:
                    continue
                exit_ts_ms = entry_ts + horizon * 3600 * 1000
                if now_ms >= exit_ts_ms:
                    # horizon déjà écoulé : clôture immédiate au prix réel
                    j = min(entry_i + horizon - 1, len(df.index) - 1)
                    exit_price = float(df["close"].iloc[j])
                    exit_ts = int(df.index[j].timestamp() * 1000)
                    hold_h = (df.index[j] - df.index[entry_i]).total_seconds() / 3600
                    ret = ((exit_price - entry_price) / entry_price * 100 * direction
                           - COST_PCT
                           - direction * funding_stats.get(sym, 0.0) * hold_h)
                    status = "closed"
                    closed_n += 1
                else:
                    exit_price = exit_ts = ret = None
                    status = "open"
                    closed_n += 0
                con.execute(
                    "INSERT OR IGNORE INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (name, sym, horizon, direction, sig_ts, entry_ts, entry_price,
                     exit_ts, exit_price, ret, None, status, now))
                opened += 1

    # clôture des paper trades ouverts dont l'horizon est atteint
    for row in con.execute(
            "SELECT rowid, signal, symbol, horizon_h, direction, entry_ts, "
            "entry_price FROM paper_trades WHERE status='open'").fetchall():
        rid, name, sym, horizon, direction, entry_ts, entry_price = row
        df = load_df(con, sym)
        if df is None:
            continue
        exit_ts_ms = entry_ts + horizon * 3600 * 1000
        if now_ms < exit_ts_ms:
            continue
        target = pd.Timestamp(exit_ts_ms, unit="ms")
        j = int(df.index.searchsorted(target, side="left"))
        j = min(j, len(df.index) - 1)
        exit_price = float(df["close"].iloc[j])
        exit_ts = int(df.index[j].timestamp() * 1000)
        entry_dt = pd.Timestamp(entry_ts, unit="ms")
        hold_h = (df.index[j] - entry_dt).total_seconds() / 3600
        ret = ((exit_price - entry_price) / entry_price * 100 * direction
               - COST_PCT
               - direction * funding_stats.get(sym, 0.0) * hold_h)
        con.execute("UPDATE paper_trades SET exit_ts=?, exit_price=?, ret_pct=?, "
                    "status='closed' WHERE rowid=?", (exit_ts, exit_price,
                                                      round(ret, 4), rid))
        closed_n += 1
    con.commit()

    # ——— rapport ———
    rows = con.execute("SELECT signal, horizon_h, status, COUNT(*), "
                       "AVG(ret_pct) FROM paper_trades GROUP BY 1,2,3").fetchall()
    lines = [f"# Paper Forward — {datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC",
             "Les 5 candidats de la campagne v5 jugés sur les données fraîches.",
             f"Cette exécution : {opened} ouvertures, {closed_n} clôtures.", "",
             "| Candidat | H | Statut | N | WR | Ret moyen |", "|---|---|---|---|---|---|"]
    for sig, h, status, n, avg in rows:
        wr = con.execute("SELECT AVG(ret_pct > 0) FROM paper_trades "
                         "WHERE signal=? AND horizon_h=? AND status=?",
                         (sig, h, status)).fetchone()[0]
        wr_s = f"{wr*100:.0f} %" if wr is not None else "—"
        avg_s = f"{avg:+.2f} %" if avg is not None else "—"
        lines.append(f"| {sig} | +{h}h | {status} | {n} | {wr_s} | {avg_s} |")
    # cumul par candidat (closed uniquement)
    lines += ["", "## Cumul forward (closed uniquement)", ""]
    for name, horizon, _d in CANDIDATES:
        r = con.execute("SELECT COUNT(*), AVG(ret_pct>0), AVG(ret_pct), "
                        "SUM(ret_pct) FROM paper_trades WHERE signal=? "
                        "AND status='closed'", (name,)).fetchone()
        if r[0]:
            lines.append(f"- **{name} +{horizon}h** : {r[0]} trades, "
                         f"WR {r[1]*100:.0f} %, moyen {r[2]:+.2f} %, "
                         f"cumulé {r[3]:+.2f} %")
    out = REPORTS / f"paper-forward-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[paper] {opened} ouvertures, {closed_n} clôtures -> {out}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
