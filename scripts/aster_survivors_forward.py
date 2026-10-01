#!/usr/bin/env python3
"""ASTER SURVIVORS FORWARD — le ledger papier du stack des survivants T21.

Les 4 stratégies découvertes par T21 (scripts/studies/aster_discovery_2123.py,
verdicts reports/aster_discovery_2123.md) génèrent leurs signaux sur les barres
1h FERMÉES de klines.db (univers 36 symboles, nocturne + WS) et leurs trades
entrent dans la table aster_survivors_paper (klines.db) — le verdict à 90 j :

  breakout_don168      : cassure Donchian 168 h (7 j), sortie canal opposé 84 h
                         ou time-stop 168 barres, stop 3×ATR24 — 2 directions.
  trend_long_ema50x200 : EMA50×EMA200 (span, adjust=False), LONG, exit cross
                         bas (fast<slow), stop 3×ATR24, pas de time-stop.
  sma_regime_50d       : close > SMA 50 j (1200 h), LONG, exit close < SMA,
                         stop 10×ATR24, pas de time-stop.
  momentum_bear_lb48   : ret 48 h < -1.5×σ30j (720 h) — SHORT uniquement
                         (l'edge découvert en bear22), stop 3×ATR24, hold 24 h.

Sémantique EXACTE du moteur T21 (un seul fichier de vérité) : signal calculé au
close t -> entrée à l'OPEN t+1 ; stop PRIORITAIRE intrabar (exécuté au prix du
stop, stop peut toucher dès la barre d'entrée) ; sortie signal/time-stop à
l'open suivant ; ret_pct = gross - 8 bps RT (COST_RT taker). Règle 0-liq T21 :
lev_cap = 100/(maxMAE_TRAIN + 0.5) NOTÉ en mémoire de ligne (don168 7.0×,
trend_long 8.2×, sma50d 9.0×, momentum 1.7×) mais la taille PAPER = 1× fixe
pour un verdict relatif propre.

État de position : 1 slot par (stratégie, symbole) — la ligne status='open'
EST l'état. Idempotence : clé naturelle UNIQUE(strategy, symbol, entry_ts),
INSERT simple (jamais OR REPLACE), les exits font un UPDATE ciblé id=? —
un re-run ne duplique rien et ne réécrit jamais une ligne closed.

Lecture klines en partagé (connexion unique, busy_timeout 30 s — pas de
2e connexion dans le process, pas de txn ouverte au repos) ; UN commit en
fin de tir, rollback propre si exception.

    .venv/bin/python scripts/aster_survivors_forward.py          # 1 tir
    .venv/bin/python scripts/aster_survivors_forward.py --dry    # sans écrire
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aster_klines_ws import UNIVERSE_1H  # noqa: E402 — les 36, source de vérité

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
TABLE = "aster_survivors_paper"
WINDOW = 3000            # barres 1h lues (SMA 1200 + sigma 720 + warmups)
MIN_BARS = 260           # sous ce seuil : pas de replay (ATR/EMA200 invalides)
HOUR_MS = 3_600_000
COST_RT = 0.0008         # 8 bps aller-retour taker (modèle T21)
ATR_N = 24               # ATR 24 h (T21)
SIGMA_WIN = 720          # sigma 30 j de rets horaires (T21)

# --- Les 4 survivants T21 — configs exactes de la grille gelée ---------------
# lev_cap = 100 / (maxMAE_TRAIN + 0.5), maxMAE reports/aster_discovery_2123.md
STRATEGIES: dict[str, dict] = {
    "breakout_don168": dict(
        fam="breakout", n=168, hold=168, stop_atr=3.0, lev_cap=7.0),
    "trend_long_ema50x200": dict(
        fam="trend_long", fast=50, slow=200, hold=None, stop_atr=3.0, lev_cap=8.2),
    "sma_regime_50d": dict(
        fam="sma_regime", days=50, hold=None, stop_atr=10.0, lev_cap=9.0),
    "momentum_bear_lb48": dict(
        fam="momentum_bear", lb=48, thr=1.5, hold=24, stop_atr=3.0, lev_cap=1.7),
}

DDL = f"""CREATE TABLE IF NOT EXISTS {TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_ts INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    stop REAL,
    horizon INTEGER,
    exit_ts INTEGER,
    exit_price REAL,
    exit_reason TEXT,
    ret_pct REAL,
    lev_cap REAL,
    status TEXT NOT NULL DEFAULT 'open',
    captured_at INTEGER,
    UNIQUE(strategy, symbol, entry_ts)
)"""
META_DDL = """CREATE TABLE IF NOT EXISTS aster_survivors_meta (
    key TEXT PRIMARY KEY, value TEXT)"""


# ------------------------------------------------------------------ indicateurs
def atr24(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(ATR_N).mean()


def signal_arrays(df: pd.DataFrame, cfg: dict) -> dict:
    """Les tableaux de signaux T21 : entrée au close i, exit (cross/canal),
    gérés au moteur. Identique à build_signals() du one-shot T21, côté filtré :
    trend_long = LONG seul, momentum_bear = SHORT seul."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    n = len(df)
    a = atr24(df)
    sig = {"enter_long": np.zeros(n, bool), "enter_short": np.zeros(n, bool),
           "exit_long": np.zeros(n, bool), "exit_short": np.zeros(n, bool),
           "atr": a.fillna(np.inf).values, "hold": cfg["hold"],
           "stop_atr": cfg["stop_atr"]}
    if cfg["fam"] == "trend_long":
        fast = c.ewm(span=cfg["fast"], adjust=False).mean()
        slow = c.ewm(span=cfg["slow"], adjust=False).mean()
        up, dn = fast > slow, fast < slow
        cross_up = up & ~up.shift(1, fill_value=False)
        sig["enter_long"] = ((cross_up | up).values & a.notna().values)
        sig["exit_long"] = dn.values
    elif cfg["fam"] == "breakout":
        nch = cfg["n"]
        hh = h.rolling(nch).max().shift(1)
        ll = l.rolling(nch).min().shift(1)
        ok = a.notna() & hh.notna()
        sig["enter_long"] = ((c > hh).values & ok.values)
        sig["enter_short"] = ((c < ll).values & ok.values)
        m = max(nch // 2, 4)
        sig["exit_long"] = (c < l.rolling(m).min().shift(1)).values
        sig["exit_short"] = (c > h.rolling(m).max().shift(1)).values
    elif cfg["fam"] == "sma_regime":
        sma = c.rolling(cfg["days"] * 24).mean()
        ok = sma.notna()
        sig["enter_long"] = ((c > sma).values & ok.values)
        sig["exit_long"] = (c < sma).values
    elif cfg["fam"] == "momentum_bear":
        ret = c.pct_change(cfg["lb"])
        s30 = ret.rolling(SIGMA_WIN).std()
        ok = a.notna() & s30.notna()
        sig["enter_short"] = ((ret < -cfg["thr"] * s30).values & ok.values)
    else:
        raise ValueError(cfg["fam"])
    return sig


# ---------------------------------------------------------------------- moteur
def _ret_pct(direction: str, entry: float, exit_p: float) -> float:
    gross = (exit_p / entry - 1.0) if direction == "long" else (entry / exit_p - 1.0)
    return (gross - COST_RT) * 100.0


def replay_key(ts, o, h, l, sig: dict, cfg: dict,
               open_row: sqlite3.Row | None, started_ms: int) -> list[dict]:
    """Replay 1 slot sur la fenêtre, sémantique T21 exacte. Si open_row est
    fourni (position déjà en DB), on la gère depuis sa barre d'entrée (ou depuis
    la fenêtre si elle est plus vieille) puis on scanne les nouvelles entrées ;
    sinon on scanne à plat — entrées éligibles seulement si le signal bar
    (open_time) >= started_ms (rien d'historique n'est inventé)."""
    n = len(ts)
    trades: list[dict] = []
    hold = sig["hold"]
    mult, atrv = sig["stop_atr"], sig["atr"]
    idx_of = {int(t): i for i, t in enumerate(ts)}

    pos = None            # dict(direction, entry_ts, entry_price, stop, entry_idx)
    pending = None        # (barre d'exit, prix, raison) — sortie à l'open suivant
    start = 1
    if open_row is not None:
        e_idx = idx_of.get(int(open_row["entry_ts"]))
        pos = {"direction": open_row["direction"], "entry_ts": int(open_row["entry_ts"]),
               "entry_price": float(open_row["entry_price"]), "stop": open_row["stop"],
               "entry_idx": e_idx}
        start = e_idx if e_idx is not None else 0

    def close(i: int, price: float, reason: str) -> None:
        trades.append({"direction": pos["direction"], "entry_ts": pos["entry_ts"],
                       "entry_price": pos["entry_price"], "stop": pos["stop"],
                       "horizon": hold, "exit_ts": int(ts[i]), "exit_price": float(price),
                       "exit_reason": reason, "status": "closed",
                       "ret_pct": _ret_pct(pos["direction"], pos["entry_price"], price)})

    for i in range(start, n - 1):
        if pos is not None and pending is not None and i == pending[0]:
            close(i, pending[1], pending[2])
            pos = pending = None
        if pos is not None:
            d = pos["direction"]
            if (d == "long" and l[i] <= pos["stop"]) or (d == "short" and h[i] >= pos["stop"]):
                close(i, pos["stop"], "stop")            # stop PRIORITAIRE intrabar
                pos = pending = None
            elif hold is not None and pos["entry_idx"] is not None and i - pos["entry_idx"] >= hold:
                pending = (i + 1, o[i + 1], "time")       # time-stop -> open suivant
            elif (d == "long" and sig["exit_long"][i]) or (d == "short" and sig["exit_short"][i]):
                pending = (i + 1, o[i + 1], "signal")     # exit signal -> open suivant
            continue
        if not (np.isfinite(atrv[i]) and int(ts[i]) >= started_ms):
            continue
        if sig["enter_long"][i]:
            pos = {"direction": "long", "entry_ts": int(ts[i + 1]), "entry_price": float(o[i + 1]),
                   "stop": float(o[i + 1] - mult * atrv[i]), "entry_idx": i + 1}
        elif sig["enter_short"][i]:
            pos = {"direction": "short", "entry_ts": int(ts[i + 1]), "entry_price": float(o[i + 1]),
                   "stop": float(o[i + 1] + mult * atrv[i]), "entry_idx": i + 1}
    if pos is not None:
        trades.append({"direction": pos["direction"], "entry_ts": pos["entry_ts"],
                       "entry_price": pos["entry_price"], "stop": pos["stop"],
                       "horizon": hold, "exit_ts": None, "exit_price": None,
                       "exit_reason": None, "ret_pct": None, "status": "open"})
    return trades


# ------------------------------------------------------------------------- DB
def meta_get(con: sqlite3.Connection, key: str) -> str | None:
    r = con.execute("SELECT value FROM aster_survivors_meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def ensure_schema(con: sqlite3.Connection) -> int:
    """Ensure-style : CREATE IF NOT EXISTS + colonnes manquantes en ALTER
    (jamais de recréation destructrice). Renvoie 1 si la table est neuve."""
    fresh = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone()[0] == 0
    con.execute(DDL)
    con.execute(META_DDL)
    have = {r[1] for r in con.execute(f"PRAGMA table_info({TABLE})").fetchall()}
    for col, typ in (("exit_reason", "TEXT"), ("lev_cap", "REAL")):
        if col not in have:
            con.execute(f"ALTER TABLE {TABLE} ADD COLUMN {col} {typ}")
    return 1 if fresh else 0


def sync_trades(con: sqlite3.Connection, strategy: str, symbol: str,
                trades: list[dict], captured_at: int) -> tuple[int, int]:
    """Idempotence par clé naturelle : INSERT simple (jamais OR REPLACE),
    UPDATE ciblé id=? uniquement sur une ligne encore open."""
    ins = closes = 0
    for t in trades:
        row = con.execute(
            f"SELECT id, status FROM {TABLE} WHERE strategy=? AND symbol=? AND entry_ts=?",
            (strategy, symbol, t["entry_ts"])).fetchone()
        if row is None:
            if t["status"] == "open":
                dup = con.execute(
                    f"SELECT id FROM {TABLE} WHERE strategy=? AND symbol=? AND status='open'",
                    (strategy, symbol)).fetchone()
                if dup:                       # 1 slot : la DB prime, on n'écrase pas
                    continue
            con.execute(
                f"INSERT INTO {TABLE} (strategy, symbol, direction, entry_ts, entry_price,"
                " stop, horizon, exit_ts, exit_price, exit_reason, ret_pct, lev_cap, status,"
                " captured_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (strategy, symbol, t["direction"], t["entry_ts"], t["entry_price"], t["stop"],
                 t["horizon"], t["exit_ts"], t["exit_price"], t["exit_reason"],
                 t["ret_pct"], cfg_lev(strategy), t["status"], captured_at))
            ins += 1
        elif row["status"] == "open" and t["status"] == "closed":
            con.execute(
                f"UPDATE {TABLE} SET exit_ts=?, exit_price=?, exit_reason=?, ret_pct=?,"
                " status='closed' WHERE id=?",
                (t["exit_ts"], t["exit_price"], t["exit_reason"], t["ret_pct"], row["id"]))
            closes += 1
    return ins, closes


def cfg_lev(strategy: str) -> float:
    return STRATEGIES[strategy]["lev_cap"]


def load_window(con: sqlite3.Connection, symbol: str) -> pd.DataFrame | None:
    rows = con.execute(
        "SELECT open_time, open, high, low, close FROM klines "
        "WHERE symbol=? AND interval='1h' ORDER BY open_time DESC LIMIT ?",
        (symbol, WINDOW)).fetchall()
    if len(rows) < MIN_BARS:
        return None
    rows.reverse()
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close"])
    df["ts"] = df["ts"].astype("int64")
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float)
    return df


def symbols_available(con: sqlite3.Connection) -> list[str]:
    have = {r[0] for r in con.execute(
        "SELECT symbol FROM klines WHERE interval='1h' GROUP BY symbol "
        "HAVING COUNT(*) >= ?", (MIN_BARS,)).fetchall()}
    return [s for s in UNIVERSE_1H if s in have]


# ----------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="calcule et loggue, n'écrit rien")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH, timeout=30.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    now = int(time.time())
    started_ms = None
    try:
        fresh = ensure_schema(con)
        started_ms = meta_get(con, "started_ms")
        if started_ms is None:
            started_ms = str(now * 1000 - 2 * HOUR_MS)  # tolérance 2 barres au 1er tir
            con.execute("INSERT OR IGNORE INTO aster_survivors_meta (key, value) VALUES ('started_ms', ?)",
                        (started_ms,))
        started_ms = int(started_ms)
        if not args.dry:
            con.commit()
    except Exception:
        con.rollback()
        con.close()
        raise

    new_ins = new_closes = 0
    open_by_strat: dict[str, int] = {k: 0 for k in STRATEGIES}
    for strategy, cfg in STRATEGIES.items():
        for symbol in symbols_available(con):
            df = load_window(con, symbol)
            if df is None:
                continue
            open_row = con.execute(
                f"SELECT * FROM {TABLE} WHERE strategy=? AND symbol=? AND status='open' "
                "ORDER BY entry_ts DESC LIMIT 1", (strategy, symbol)).fetchone()
            sig = signal_arrays(df, cfg)
            trades = replay_key(df["ts"].values, df["open"].values, df["high"].values,
                                df["low"].values, sig, cfg, open_row, started_ms)
            if not trades:
                continue
            if args.dry:
                for t in trades:
                    print(f"[survivors-forward] (dry) {strategy} {symbol} {t['direction']} "
                          f"entry_ts={t['entry_ts']} status={t['status']}")
                continue
            try:
                i, c = sync_trades(con, strategy, symbol, trades, now)
                new_ins += i
                new_closes += c
            except Exception:
                con.rollback()
                con.close()
                raise
    if not args.dry:
        try:
            for r in con.execute(
                    f"SELECT strategy, COUNT(*) c FROM {TABLE} WHERE status='open' GROUP BY strategy"):
                open_by_strat[r["strategy"]] = r["c"]
            con.execute("INSERT OR REPLACE INTO aster_survivors_meta (key, value) VALUES ('last_run_epoch', ?)",
                        (str(now),))
            con.commit()   # UN commit en fin de tir (règle anti-txn-fantôme)
        except Exception:
            con.rollback()
            con.close()
            raise
    con.close()
    tag = " (dry)" if args.dry else ""
    print(f"[survivors-forward] tir {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now))}{tag} : "
          f"{new_ins} nouvelle(s) ligne(s), {new_closes} close(s), "
          f"ouverts : " + ", ".join(f"{k}={v}" for k, v in open_by_strat.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
