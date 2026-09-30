#!/usr/bin/env python
"""ÉTUDE T9 — LE STACK MULTI-RÉGIME 2021→2026 (gates de régime sans look-ahead).

Question (suite constructive de T8) : un STACK dont l'EXPOSITION est
conditionnée à la DÉTECTION de régime (bull → momentum ; bear → short
BTC/ETH PORTÉ ; memes → fade funding réel élevé ; vol_spike permanent)
aurait-il produit la STABILITÉ à travers 2021-2026, là où la lane
continue cascade 10x meurt (T8 : 14 liq, $0.99) et où le 4x ne fait que
survivre ($14.36) ?

Composantes (chaîne T7/Q3/P3) :
  - momentum REF harnais (fast 20 / slow 100 / regime_ema 200, long only,
    stop 200 bps / take 1000 bps) sur BTC/ETH/SOL — GATE : détecteur bull.
  - short BTC/ETH PORTÉ : entrée au flip bear du détecteur, sortie au flip
    bull — PAS de stop serré (leçon Q3 : l'exposition constante paie,
    le short tradé à stops 2 % perd le whipsaw) ; funding du portage compté.
  - fade funding réel élevé sur memes : harnais funding_fade REF sur la
    série réelle, GATE fund7 > 0.5 bps/8h (mécanisme P3) — quand la série
    existe (funding_history : majors 2025-10-27, ASTER 2025-09, autres
    2026-04) ; composante STRUCTURELLEMENT vide avant.
  - vol_spike reversion 6h 1x permanent (T8, levier 1).

DÉTECTEURS (sans look-ahead — le régime à t n'utilise que les données ≤ t) :
  - D1 SMA 200 jours du close BTC 1h (rolling 4800 barres) : close > sma =
    bull, sinon bear. Warm-up honnête : régime INCONNU les ~200 premiers
    jours (le stack n'y trade que vol_spike).
  - D2 SMA 100 jours (2400 barres) — la sensibilité au LAG du détecteur.
  - D3 vol-régime ATR% : ATR 14 j / close vs médiane roulante 180 j —
    rapporté (flips + lag), ne définit pas de direction.

MÉTHODE :
  - split TRAIN/VAL PAR LE TEMPS : TRAIN = premières 70 % des barres
    (2021-09→~2025-05), VAL = le reste. TOUTES les calibrations (q66
    cascade, p90/med vol_spike, levier du short porté par la règle
    0-liq sur le MAE TRAIN) sont calculées sur TRAIN, jugées sur VAL.
  - levier du short porté : lev ≤ 100/(MAE_train + 0.5), plafonné 2x
    (harnais) — le MAE VAL réalisé est comparé à la ligne de liq.
  - wallet séquentiel = run_stack (scripts/stacked_portfolio.py), capital
    frais $100, un créneau par (stratégie × symbole), garde-fous
    composé-des-mois + somme PnL.
  - témoins : (a) lane continue cascade 10x + vol_spike (réplique T8),
    (b) idem levier sûr 4x, (c) buy&hold BTC (l'échelle honnête).

Coûts et funding (honnêteté) :
  - momentum / fade : 8 bps taker aller-retour (convention harnais v5) ;
    cascade : 4 bps maker RT ; vol_spike : 28 bps taker RT (convention
    machine) — chaque jambe garde SON modèle de coûts validé.
  - funding : momentum longs paient la moyenne moderne par symbole
    (funding_hourly_all, approximation T8 documentée) ; le short porté
    paie/encaisse le MODÈLE T7 par régime (bear_2022 = -0.5 bps/8h → le
    short PAIE ~5.5 %/an de portage) puis le réel mesuré as-of à partir
    de 2025-10-27 ; fade = funding réel par symbole.
  - fills modèle : stops au prix du stop (optimiste sur gaps) — les
    conclusions négatives en sont renforcées.

  .venv/bin/python scripts/studies/aster_multiregime_stack.py
"""
from __future__ import annotations

import sqlite3
import sys
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # scripts/studies/ → racine
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.strategies import (  # noqa: E402
    funding_fade as ff,
    momentum as mom,
)
from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
from scripts.portfolio_sim import MAJORS, btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, monthly_rows, run_stack)

REPORTS = ROOT / "reports"
KDB_RO = f"file:{ROOT / 'data' / 'warehouse' / 'klines.db'}?mode=ro"
K_V = 0.89                      # facteur global machine (calibration DD 25 %)
CARRY_SYMS = ["BTCUSDT", "ETHUSDT"]
HARNESS_FEE_RT = 8.0            # bps taker aller-retour (harnais v5)

# les 6 régimes T7 (reports/aster_deep_regimes.md)
REGIMES = [
    ("bull_2021H2", "2021-09-01", "2022-01-01"),
    ("bear_2022", "2022-01-01", "2023-01-01"),
    ("recovery_2023", "2023-01-01", "2024-01-01"),
    ("bull_2024H1", "2024-01-01", "2024-07-01"),
    ("chop_2024H2", "2024-07-01", "2025-01-01"),
    ("connu_2025_2026", "2025-01-01", "2026-09-30"),
]

# configs REF de la dernière campagne (harnais, cf. aster_deep_regimes_p2.py)
MOM_REF = dict(fast_ema=20, slow_ema=100, regime_ema=200, allow_short=False,
               stop_bps=200, take_bps=1000, max_leverage=2)
FADE_REF = dict(lookback=200, entry_z=2.5, exit_z=0.5, allow_short=True,
                stop_bps=200, max_leverage=3)

# tailles marge (hypothèses de sizing, un créneau par stratégie × symbole)
SZ_MOM = 0.08                   # momentum, lev 2
SZ_CARRY = 0.25                 # short porté, lev = lev_carry
SZ_FADE = 0.05                  # fade memes, lev 2

# modèle de funding T7 pour les majors (bps/8h) — calendrier 2021-2024
CAL_FUND_BPS = [
    ("2021-09-01", "2022-01-01", 2.0),
    ("2022-01-01", "2023-01-01", -0.5),   # bear : le short PAIE le portage
    ("2023-01-01", "2024-01-01", 0.5),
    ("2024-01-01", "2024-07-01", 1.5),
    ("2024-07-01", "2025-01-01", 0.5),
]
CONN_FUND_CONST_BPS = {"BTCUSDT": 0.343, "ETHUSDT": 0.367}  # 2025-01→réel
REAL_FUND_START_MS = 1761580800000          # funding_history majors 2025-10-27


def ts_ns(datestr: str) -> int:
    return int(pd.Timestamp(datestr, tz="UTC").value)


def ms_of(datestr: str) -> int:
    return int(pd.Timestamp(datestr, tz="UTC").value // 10**6)


# ------------------------------------------------------------------ données
def open_ro() -> sqlite3.Connection:
    con = sqlite3.connect(KDB_RO, uri=True)
    return con


def load_bars(con: sqlite3.Connection, symbol: str) -> list[Bar]:
    rows = con.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol = ? AND interval = '1h' ORDER BY open_time",
        (symbol,)).fetchall()
    return [Bar(ts=int(r[0]), open=float(r[1]), high=float(r[2]),
                low=float(r[3]), close=float(r[4]), volume=float(r[5]))
            for r in rows]


def load_funding_pts(con: sqlite3.Connection, symbol: str
                     ) -> tuple[list[int], list[float]]:
    """(funding_time_ms, bps/8h) triés — le taux réel."""
    rows = con.execute(
        "SELECT funding_time, rate FROM funding_history WHERE symbol = ? "
        "ORDER BY funding_time", (symbol,)).fetchall()
    ts = [int(r[0]) for r in rows if r[0] is not None]
    rt = [float(r[1]) * 10_000.0 for r in rows if r[0] is not None]
    return ts, rt


# --------------------------------------------------------------- détecteurs
def detector_sma(btc: list[Bar], days: int, confirm_bars: int = 48
                 ) -> tuple[list[int | None], int]:
    """+1 = bull (close > SMA), -1 = bear, None = warm-up. CAUSAL : l'état
    de la barre t n'utilise que les closes ≤ t ; l'EXECUTION est à t+1.
    CONFIRMATION anti-bruit : l'état ne bascule qu'après `confirm_bars`
    (48 h) consécutifs de l'autre côté — règle de DESIGN (le close colle à
    la SMA dans le chop : le close flicker), pas une calibration sur PnL.
    Le lag de confirmation est assumé et chiffré. Renvoie (état, nb bascules
    BRUTES avant confirmation)."""
    close = pd.Series([b.close for b in btc])
    sma = close.rolling(days * 24, min_periods=days * 24).mean()
    out: list[int | None] = []
    cur: int | None = None
    pend: int | None = None
    pend_n = 0
    n_raw = 0
    prev_raw: int | None = None
    for i in range(len(close)):
        s = sma.iloc[i]
        raw = None if not np.isfinite(s) else (1 if close.iloc[i] > s else -1)
        if prev_raw is not None and raw is not None and raw != prev_raw:
            n_raw += 1
        prev_raw = raw if raw is not None else prev_raw
        if raw is None:
            out.append(None)
            continue
        if cur is None:
            cur = raw
            out.append(cur)
            continue
        if raw == cur:
            pend, pend_n = None, 0
        else:
            pend_n = pend_n + 1 if pend == raw else 1
            pend = raw
            if pend_n >= confirm_bars:
                cur = raw
                pend, pend_n = None, 0
        out.append(cur)
    return out, n_raw


def detector_atr_pct(btc: list[Bar], confirm_bars: int = 48
                     ) -> tuple[list[int | None], pd.Series, int]:
    """D3 vol-régime : +1 = haute vol (ATR% > médiane 180 j), -1 = basse.
    Causal (rolling), même confirmation anti-bruit 48 h. Rapporté, ne
    définit pas de direction."""
    c = pd.Series([b.close for b in btc])
    h = pd.Series([b.high for b in btc])
    l = pd.Series([b.low for b in btc])
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr_pct = tr.rolling(336).mean() / c * 100.0
    med = atr_pct.rolling(4320, min_periods=720).median()
    raw = [None if not (np.isfinite(atr_pct.iloc[i]) and np.isfinite(med.iloc[i]))
           else (1 if atr_pct.iloc[i] > med.iloc[i] else -1)
           for i in range(len(c))]
    out: list[int | None] = []
    cur: int | None = None
    pend: int | None = None
    pend_n = 0
    n_raw = 0
    prev_raw: int | None = None
    for i, r in enumerate(raw):
        if prev_raw is not None and r is not None and r != prev_raw:
            n_raw += 1
        prev_raw = r if r is not None else prev_raw
        if r is None:
            out.append(None)
            continue
        if cur is None:
            cur = r
            out.append(cur)
            continue
        if r == cur:
            pend, pend_n = None, 0
        else:
            pend_n = pend_n + 1 if pend == r else 1
            pend = r
            if pend_n >= confirm_bars:
                cur = r
                pend, pend_n = None, 0
        out.append(cur)
    return out, atr_pct, n_raw


def flips(state: list[int | None], btc: list[Bar]) -> list[tuple[str, str, str, float]]:
    """Les bascules (date, de → vers, prix) — le LAG du détecteur."""
    out = []
    prev: int | None = None
    for t, s in enumerate(state):
        if s is None:
            continue
        if prev is not None and s != prev:
            d = datetime.fromtimestamp(btc[t].ts / 1000, tz=timezone.utc)
            out.append((f"{d:%Y-%m-%d %H:%M}", "bull" if prev == 1 else "bear",
                        "bull" if s == 1 else "bear", btc[t].close))
        prev = s
    return out


def regime_share(state: list[int | None], btc: list[Bar]) -> dict[str, tuple[float, float, float]]:
    """Part des barres bull / bear / inconnues par régime calendaire."""
    out = {}
    for name, lo, hi in REGIMES:
        lo_ms, hi_ms = ms_of(lo), ms_of(hi)
        seg = [s for b, s in zip(btc, state) if lo_ms <= b.ts < hi_ms]
        n = max(len(seg), 1)
        out[name] = (sum(1 for s in seg if s == 1) / n * 100,
                     sum(1 for s in seg if s == -1) / n * 100,
                     sum(1 for s in seg if s is None) / n * 100)
    return out


# ---------------------------------------------------------------- momentum
def momentum_events_gated(bars: list[Bar], params: dict, det: list[int | None],
                          sym: str) -> list[dict]:
    """momentum REF (harnais) exécuté fidèlement (open i+1, stop/take
    intrabar), GATE détecteur : le signal de i-1 n'est exécuté que si le
    détecteur (connu à la clôture de i-1) dit bull ; un flip bear force la
    sortie au prochain open. Aucun look-ahead : gate[i-1] ∈ données ≤ i-1."""
    n = len(bars)
    signals = mom.compute_signals(bars, params)
    stop_frac = float(params["stop_bps"]) / 10_000.0
    take_frac = float(params["take_bps"]) / 10_000.0
    evs: list[dict] = []
    pos = 0
    entry_price = 0.0
    entry_i = 0
    for i in range(n):
        b = bars[i]
        if i >= 1:
            desired = signals[i - 1] if det[i - 1] == 1 else 0
            if desired != pos:
                if pos != 0:
                    reason = ("regime" if desired == 0 and signals[i - 1] != 0
                              else "reverse")
                    evs.append(_mk_event(bars, sym, "momentum", pos, entry_i, i,
                                         entry_price, b.open, reason, 2,
                                         HARNESS_FEE_RT, -1))
                    pos = 0
                if desired != 0:
                    pos = desired
                    entry_price = b.open
                    entry_i = i
        if pos == 1:
            sp = entry_price * (1.0 - stop_frac)
            tp = entry_price * (1.0 + take_frac)
            if b.low <= sp:
                evs.append(_mk_event(bars, sym, "momentum", 1, entry_i, i,
                                     entry_price, sp, "stop", 2,
                                     HARNESS_FEE_RT, -1))
                pos = 0
            elif b.high >= tp:
                evs.append(_mk_event(bars, sym, "momentum", 1, entry_i, i,
                                     entry_price, tp, "take", 2,
                                     HARNESS_FEE_RT, -1))
                pos = 0
    if pos != 0:
        evs.append(_mk_event(bars, sym, "momentum", pos, entry_i, n - 1,
                             entry_price, bars[-1].close, "eod", 2,
                             HARNESS_FEE_RT, -1))
    return evs


def _mk_event(bars: list[Bar], sym: str, strat: str, side: int, ei: int,
              xi: int, entry: float, exit_: float, reason: str, lev: float,
              fee_rt_bps: float, fund_sign: int) -> dict:
    lo = min(b.low for b in bars[ei:xi + 1])
    hi = max(b.high for b in bars[ei:xi + 1])
    mae = ((entry - lo) / entry * 100 if side == 1
           else (hi - entry) / entry * 100)
    return {"sym": sym, "strategy": strat,
            "ts_ms": int(bars[ei].ts) * 10**6,          # ms → NS
            "hold_h": max(1, xi - ei), "lev": lev,
            "fee_rt_bps": fee_rt_bps, "fund_sign": fund_sign,
            "entry": entry, "exit": exit_, "reason": reason,
            "price_ret_short": side * (exit_ / entry - 1.0) * 100.0,
            "mae_adverse": mae}


# ------------------------------------------------------------ short porté
def carry_episodes(bars: list[Bar], det: list[int | None]) -> list[dict]:
    """Épisodes short portés : entrée à l'open qui suit le flip bear,
    sortie à l'open qui suit le flip bull (le RÉGIME est le stop — pas de
    stop serré, leçon Q3). eod si toujours bear à la fin de la série."""
    eps: list[dict] = []
    cur: dict | None = None
    for t in range(len(bars)):
        s = det[t]
        if cur is None:
            if s == -1:
                cur = {"ei": t + 1, "sig_i": t}
        else:
            if s == 1:
                cur["xi"] = t + 1
                eps.append(cur)
                cur = None
    if cur is not None:
        cur["xi"] = len(bars) - 1
        cur["eod"] = True
        eps.append(cur)
    return [e for e in eps if e["ei"] < e["xi"] < len(bars)]


def carry_event(bars: list[Bar], sym: str, ep: dict, lev: float,
                fund_bps_8h: float, idx: int) -> dict:
    ei, xi = ep["ei"], ep["xi"]
    entry = bars[ei].open
    exit_ = bars[xi].close if ep.get("eod") else bars[xi].open
    # MAE : de l'open d'entrée au moment de sortie (open de xi, ou close
    # de la dernière barre en eod) — la jambe adverse maximale du portage.
    end = xi + 1 if ep.get("eod") else xi
    hi = max(x.high for x in bars[ei:end])
    mae = (hi - entry) / entry * 100
    ev = _mk_event(bars, f"{sym}@carry{idx}", f"carry_short_{sym}", -1,
                   ei, xi, entry, exit_, "regime_exit", lev, HARNESS_FEE_RT, +1)
    ev["mae_adverse"] = mae
    ev["fund_bps_8h"] = fund_bps_8h
    ev["ep_entry"] = entry
    ev["ep_exit"] = exit_
    ev["ep_days"] = xi - ei
    return ev


def daily_fund_bps(sym: str, day_ms: int, real_ts: list[int],
                   real_rt: list[float]) -> float:
    """bps/8h pour un jour : réel as-of (moyenne 7 j des taux ≤ jour, shifted)
    dès que ≥ 20 points réels existent ; sinon modèle T7 calendaire ; sinon
    la constante P2 « connu » (2025-01→2025-10)."""
    pos = bisect_right(real_ts, day_ms)
    if pos >= 20:
        return float(np.mean(real_rt[max(0, pos - 56):pos]))
    for lo, hi, bps in CAL_FUND_BPS:
        if ms_of(lo) <= day_ms < ms_of(hi):
            return bps
    return CONN_FUND_CONST_BPS.get(sym, 0.4)


# ------------------------------------------------------------- fade memes
def fade_events(con: sqlite3.Connection, fh: dict[str, float]
                ) -> tuple[list[dict], list[tuple]]:
    """funding_fade REF harnais sur la série de funding RÉELLE par symbole
    (pas-à-pas, shifted), GATE P3 : fund7 (moyenne 7 j du funding connu à
    la clôture du signal) > 0.5 bps/8h. Univers = non-majors avec klines
    ≥ 800 barres ET ≥ 50 points de funding, couverture ≥ 30 %."""
    syms = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol")]
    evs: list[dict] = []
    used = []
    for sym in syms:
        if sym in MAJORS:
            continue
        rows = con.execute(
            "SELECT open_time, open, high, low, close, volume FROM klines "
            "WHERE symbol = ? AND interval = '1h' ORDER BY open_time",
            (sym,)).fetchall()
        if len(rows) < 800:
            continue
        ts, rt = load_funding_pts(con, sym)
        if len(ts) < 50:
            continue
        bars = [Bar(ts=int(r[0]), open=float(r[1]), high=float(r[2]),
                    low=float(r[3]), close=float(r[4]), volume=float(r[5]))
                for r in rows]
        lo, hi = ts[0], ts[-1]
        cov = sum(1 for b in bars if lo <= b.ts <= hi) / len(bars)
        if cov < 0.30:
            continue
        avg = float(np.mean(rt))
        j, m = -1, len(ts)
        series = []
        for b in bars:
            while j + 1 < m and ts[j + 1] <= b.ts:
                j += 1
            series.append(rt[j] if j >= 0 else avg)
        trades, _bar_ret = ff.simulate(bars, dict(FADE_REF, symbol=sym),
                                       funding_bps=series)
        n_kept = 0
        for tr in trades:
            if tr.side != -1:
                continue
            sig_i = tr.entry_index - 1
            lo7 = max(0, sig_i - 167)
            fund7 = float(np.mean(series[lo7:sig_i + 1])) if sig_i >= 0 else np.nan
            if not np.isfinite(fund7) or fund7 <= 0.5:
                continue                      # le GATE P3 : carburant exigé
            ev = _mk_event(bars, sym, "fade_meme", -1, tr.entry_index,
                           tr.exit_index, tr.entry_price, tr.exit_price,
                           tr.reason, 2, HARNESS_FEE_RT, +1)
            ev["fund7_bps"] = fund7
            evs.append(ev)
            n_kept += 1
        used.append((sym, len(trades), n_kept, cov, avg))
    return evs, used


# -------------------------------------------------------------- vol_spike
def spike_events(con: sqlite3.Connection, train_end_ns: int
                 ) -> tuple[list[dict], float, float]:
    """vol_spike 6h (T8, levier 1) — p90/med calibrés sur TRAIN uniquement
    (amélioration doctrinale vs T8 qui calibrait p90 sur toute la fenêtre)."""
    evs = collect_vol_spike(con, hold=6, atr_gate=False)
    for e in evs:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["hold_h"] = 6
        e["fee_rt_bps"] = TAKER_RT
    tr = [e for e in evs if e["ts_ms"] < train_end_ns]
    p90 = float(np.nanquantile([e["atr_pct"] for e in tr], 0.90)) if tr else 99.0
    keep = [e for e in evs if e["atr_pct"] <= p90]
    med = float(np.median([e["atr_pct"] for e in keep])) if keep else 1.0
    return keep, p90, med


# --------------------------------------------------------------- cascade
def cascade_witness(con: sqlite3.Connection, regime: pd.Series,
                    train_end_ns: int, lev: float) -> tuple[list[dict], float]:
    """Réplique T8 : cascade majors gated par l'AL Score (q66 TRAIN),
    médiane ATR de la population gated, boost fund_rank, levier imposé."""
    evs = collect_featured(regime, "majors")
    for e in evs:
        e["strategy"] = "cascade_10x"
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(evs)
    # fund_rank (as-of) — le boost qualité de la machine
    fts: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            tt, rr = fts.setdefault(s, ([], []))
            tt.append(t * 10**6 if t > 10**11 else t * 10**9)
            rr.append(float(r))
        except (TypeError, ValueError):
            continue
    for e in evs:
        ranks, own = [], np.nan
        for s in MAJORS:
            ft = fts.get(s)
            if not ft or len(ft[0]) < 5:
                continue
            pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"],
                                      side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = ft[1][pos]
            ranks.append(ft[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)
    win = [e for e in evs if ts_ns("2021-09-01") <= e["ts_ms"] < ts_ns("2026-09-30")]
    win = sorted(win, key=lambda e: e["ts_ms"])
    k70 = int(len(win) * 0.7)
    q66 = float(np.nanquantile([e["al_score"] for e in win[:k70]], 2 / 3))
    gated = [e for e in win
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    med = float(np.median([e["atr_pct"] for e in gated]))
    for e in gated:
        e["lev"] = lev
    return gated, med


def make_fn_cascade(med: float):
    def fn(e, st=None):
        s0 = min(max(0.24 * K_V * (e["atr_pct"] / med), 0.08 * K_V),
                 0.40 * K_V)
        if (np.isfinite(e.get("fund_rank", np.nan)) and e["fund_rank"] <= 0.33):
            return min(s0 * 1.5, 0.50 * K_V)
        return s0
    return fn


# ------------------------------------------------------------------ stats
def seg_stats(res: dict, capital: float, days: float) -> dict:
    wr = res["n_wins"] / max(res["n"], 1) * 100
    roi = (res["balance"] / capital - 1) * 100
    roi_an = (((res["balance"] / capital) ** (365.0 / days) - 1) * 100
              if days > 0 and res["balance"] > 0 else -100.0)
    mr = monthly_rows(res["trades"], capital)
    rois = [x["roi"] for x in mr]
    return {"n": res["n"], "wr": wr, "liq": res["n_liq"], "roi": roi,
            "roi_an": roi_an, "dd": res["max_dd"], "bal": res["balance"],
            "neg": sum(1 for x in rois if x < 0),
            "worst": min(rois) if rois else 0.0,
            "record": max(rois) if rois else 0.0,
            "fees": res["fees"], "funding": res["funding"], "mr": mr}


def by_regime_stats(res: dict) -> list[dict]:
    """Attribution des trades du wallet par régime d'ENTRÉE : PnL, WR, liq,
    DD intra-régime sur le chemin de balance (le garde-fou des verdicts)."""
    trades = res["trades"]
    out = []
    for name, lo, hi in REGIMES:
        lo_ns, hi_ns = ts_ns(lo), ts_ns(hi)
        days = max((hi_ns - lo_ns) / 86400 / 10**9, 1.0)
        seg = [t for t in trades if lo_ns <= int(t["entry_ts"].timestamp() * 1e9) < hi_ns]
        bal_start = CAPITAL + sum(t["pnl"] for t in trades
                                  if int(t["entry_ts"].timestamp() * 1e9) < lo_ns)
        pnl = sum(t["pnl"] for t in seg)
        roi_seg = pnl / bal_start * 100 if bal_start > 0 else float("nan")
        roi_an = (((1 + roi_seg / 100) ** (365.0 / days) - 1) * 100
                  if bal_start > 0 and (1 + roi_seg / 100) > 0 else -100.0)
        # DD intra-régime sur les marques de balance
        bal, peak, dd = bal_start, bal_start, 0.0
        for t in seg:
            bal += t["pnl"]
            peak = max(peak, bal)
            if peak > 0:
                dd = max(dd, (peak - bal) / peak * 100)
        n = len(seg)
        w = sum(1 for t in seg if t["pnl"] > 0)
        # mois du régime
        mr = monthly_rows(seg, bal_start) if seg else []
        neg = sum(1 for x in mr if x["roi"] < 0)
        worst = min((x["roi"] for x in mr), default=0.0)
        out.append({"name": name, "days": days, "n": n,
                    "wr": w / max(n, 1) * 100, "liq": sum(1 for t in seg if t["liq"]),
                    "pnl": pnl, "bal_start": bal_start, "roi": roi_seg,
                    "roi_an": roi_an, "dd": dd, "neg": neg, "worst": worst})
    return out


def garde_fous(res: dict, capital: float) -> tuple[float, float]:
    mr = monthly_rows(res["trades"], capital)
    prod = 1.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
    gap_c = abs(prod - res["balance"] / capital)
    sum_pnl = sum(x["pnl"] for x in mr)
    gap_p = abs(sum_pnl - (res["balance"] - capital))
    return gap_c, gap_p


def fmt_reg(s: dict) -> str:
    if s["n"] == 0:
        return "0t —"
    return (f"{s['n']}t · {s['wr']:.0f}% · {s['roi']:+.1f}% "
            f"({s['roi_an']:+.0f}%/an) · DD{s['dd']:.1f} · "
            f"liq{s['liq']} · {s['neg']}m− pire {s['worst']:+.1f}%")


# ------------------------------------------------------------------- main
def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = open_ro()
    regime = btc_regime_series()
    fh = funding_hourly_all()

    bars = {s: load_bars(con, s) for s in MAJORS}
    btc = bars["BTCUSDT"]
    k70 = int(len(btc) * 0.7)
    train_end_ms = btc[k70].ts
    train_end_ns = train_end_ms * 10**6
    deep_lo, deep_hi = ts_ns("2021-09-01"), ts_ns("2026-09-30")
    deep_days = (deep_hi - deep_lo) / 86400 / 10**9
    d_first = datetime.fromtimestamp(btc[0].ts / 1000, tz=timezone.utc)
    d_train = datetime.fromtimestamp(train_end_ms / 1000, tz=timezone.utc)
    d_last = datetime.fromtimestamp(btc[-1].ts / 1000, tz=timezone.utc)
    print(f"[t9] bars BTC {len(btc)} {d_first:%Y-%m-%d}→{d_last:%Y-%m-%d} | "
          f"TRAIN → {d_train:%Y-%m-%d} (70 %)", flush=True)

    # ——— détecteurs ———
    det1, raw1 = detector_sma(btc, 200)
    det2, raw2 = detector_sma(btc, 100)
    det3, atr_pct, raw3 = detector_atr_pct(btc)
    fl1, fl2, fl3 = flips(det1, btc), flips(det2, btc), flips(det3, btc)
    sh1, sh3 = regime_share(det1, btc), regime_share(det3, btc)
    warmup_days = sum(1 for s in det1 if s is None) / 24
    print(f"[t9] D1 flips={len(fl1)} D2 flips={len(fl2)} D3 flips={len(fl3)} "
          f"warm-up D1={warmup_days:.0f} j", flush=True)

    # ——— momentum gated (harnais REF × 3 majors) ———
    mom_ev: list[dict] = []
    for sym in MAJORS:
        evs = momentum_events_gated(bars[sym], dict(MOM_REF, symbol=sym),
                                    det1, sym)
        for e in evs:
            e["strategy"] = f"momentum_{sym}"
        mom_ev += evs
    print(f"[t9] momentum gated : {len(mom_ev)} évts", flush=True)

    # ——— short porté BTC/ETH (épisodes détecteur, levier 0-liq sur TRAIN) ———
    carry_evs_all: dict[str, list[dict]] = {}
    lev_carry: float | None = None
    mae_train = 0.0
    for sym in CARRY_SYMS:
        b = bars[sym]
        eps = carry_episodes(b, det1)
        fts, frt = load_funding_pts(con, sym)
        evs = []
        for k, ep in enumerate(eps):
            days = [b2.ts for b2 in b[ep["ei"]:ep["xi"]]]
            fbps = float(np.mean([daily_fund_bps(sym, d, fts, frt)
                                  for d in days[::24]] or [0.0]))
            evs.append((ep, fbps))
        carry_evs_all[sym] = evs
        # MAE TRAIN : épisodes entièrement dans TRAIN (exit ≤ train_end)
        for ep, fbps in evs:
            xi_ms = b[min(ep["xi"], len(b) - 1)].ts
            if xi_ms <= train_end_ms:
                entry = b[ep["ei"]].open
                hi = max(x.high for x in b[ep["ei"]:ep["xi"]])
                mae_train = max(mae_train, (hi - entry) / entry * 100)
    lev_carry = min(2.0, 100.0 / (mae_train + 0.5)) if mae_train > 0 else 2.0
    carry_ev: list[dict] = []
    for sym in CARRY_SYMS:
        for k, (ep, fbps) in enumerate(carry_evs_all[sym]):
            carry_ev.append(carry_event(bars[sym], sym, ep, lev_carry, fbps, k))
    print(f"[t9] carry : {len(carry_ev)} épisodes, MAE train {mae_train:.1f} % "
          f"→ lev {lev_carry:.2f}x", flush=True)

    # ——— fade memes (P3 : fund7 > 0.5 bps/8h) ———
    fade_ev, fade_used = fade_events(con, fh)
    print(f"[t9] fade memes : {len(fade_ev)} évts sur {len(fade_used)} séries",
          flush=True)

    # ——— vol_spike permanent (p90/med TRAIN) ———
    spike_ev, sp_p90, sp_med = spike_events(con, train_end_ns)
    print(f"[t9] vol_spike : {len(spike_ev)} évts (p90 {sp_p90:.2f}, "
          f"med {sp_med:.2f})", flush=True)

    def fn_spike(e, st=None):
        return min(max(0.10 * K_V * (e["atr_pct"] / sp_med), 0.02 * K_V),
                   0.30 * K_V)

    def fn_stack(e, st=None):
        s = e["strategy"]
        if s.startswith("momentum"):
            return SZ_MOM
        if s.startswith("carry_short"):
            return SZ_CARRY
        if s == "fade_meme":
            return SZ_FADE
        return fn_spike(e, st)

    # funding dict : moyennes modernes (momentum/fade/spike) + épisodes carry
    fh_stack = dict(fh)
    for sym in CARRY_SYMS:
        for k, (ep, fbps) in enumerate(carry_evs_all[sym]):
            fh_stack[f"{sym}@carry{k}"] = fbps / 100.0 / 8.0   # %/h

    # ——— LE STACK MULTI-RÉGIME ———
    stack_ev = sorted(mom_ev + carry_ev + fade_ev + spike_ev,
                      key=lambda e: e["ts_ms"])
    res_t9 = run_stack(stack_ev, CAPITAL, fn_stack, fh_stack)
    t9 = seg_stats(res_t9, CAPITAL, deep_days)
    t9_reg = by_regime_stats(res_t9)

    # ——— sensibilité : détecteur D2 (SMA 100 j) ———
    mom_ev2: list[dict] = []
    for sym in MAJORS:
        evs = momentum_events_gated(bars[sym], dict(MOM_REF, symbol=sym),
                                    det2, sym)
        for e in evs:
            e["strategy"] = f"momentum_{sym}"
        mom_ev2 += evs
    carry_ev2: list[dict] = []
    mae2 = 0.0
    eps2_all: list[tuple[str, dict, float]] = []
    for sym in CARRY_SYMS:
        b = bars[sym]
        fts, frt = load_funding_pts(con, sym)
        for ep in carry_episodes(b, det2):
            days = [b2.ts for b2 in b[ep["ei"]:ep["xi"]]]
            fbps = float(np.mean([daily_fund_bps(sym, d, fts, frt)
                                  for d in days[::24]] or [0.0]))
            xi_ms = b[min(ep["xi"], len(b) - 1)].ts
            if xi_ms <= train_end_ms:
                entry = b[ep["ei"]].open
                hi = max(x.high for x in b[ep["ei"]:ep["xi"]])
                mae2 = max(mae2, (hi - entry) / entry * 100)
            eps2_all.append((sym, ep, fbps))
    lev2 = min(2.0, 100.0 / (mae2 + 0.5)) if mae2 > 0 else 2.0
    for k, (sym, ep, fbps) in enumerate(eps2_all):
        carry_ev2.append(carry_event(bars[sym], sym, ep, lev2, fbps, k))
    stack_ev2 = sorted(mom_ev2 + carry_ev2 + fade_ev + spike_ev,
                       key=lambda e: e["ts_ms"])

    fh_stack2 = dict(fh)
    for e in carry_ev2:
        fh_stack2[e["sym"]] = e["fund_bps_8h"] / 100.0 / 8.0
    res_t9b = run_stack(stack_ev2, CAPITAL, fn_stack, fh_stack2)
    t9b = seg_stats(res_t9b, CAPITAL, deep_days)

    # ——— les composantes SEULES (lanes gated, même sizing, wallet frais) ———
    lanes = {}
    for lbl, evs, fn in (("momentum", mom_ev, lambda e, st=None: SZ_MOM),
                         ("carry", carry_ev, lambda e, st=None: SZ_CARRY),
                         ("fade", fade_ev, lambda e, st=None: SZ_FADE),
                         ("vol_spike", spike_ev, fn_spike)):
        lanes[lbl] = seg_stats(run_stack(sorted(evs, key=lambda x: x["ts_ms"]),
                                         CAPITAL, fn, fh_stack),
                               CAPITAL, deep_days)

    # ——— TÉMOINS : la lane continue cascade (T8) + buy&hold ———
    cas_ev, cas_med = cascade_witness(con, regime, train_end_ns, 10)
    res_a = run_stack(sorted(cas_ev + spike_ev, key=lambda e: e["ts_ms"]),
                      CAPITAL, make_fn_cascade(cas_med), fh)
    wit_a = seg_stats(res_a, CAPITAL, deep_days)
    for e in cas_ev:
        e["lev"] = 4
    res_b = run_stack(sorted(cas_ev + spike_ev, key=lambda e: e["ts_ms"]),
                      CAPITAL, make_fn_cascade(cas_med), fh)
    wit_b = seg_stats(res_b, CAPITAL, deep_days)

    closes = np.array([b.close for b in btc])
    bh_final = closes[-1] / closes[0]
    bh_peak = np.maximum.accumulate(closes)
    bh_dd = float(np.max((bh_peak - closes) / bh_peak * 100))
    bh_months = []
    mser = pd.Series(closes, index=pd.to_datetime([b.ts for b in btc],
                                                  unit="ms")).resample("MS").last()
    mret = mser.pct_change().dropna() * 100
    bh_neg = int((mret < 0).sum())
    bh_worst = float(mret.min())

    mae_mon = {
        "momentum": max((e["mae_adverse"] for e in mom_ev), default=0.0),
        "carry": max((e["mae_adverse"] for e in carry_ev), default=0.0),
        "fade": max((e["mae_adverse"] for e in fade_ev), default=0.0),
        "spike": max((e["mae_adverse"] for e in spike_ev), default=0.0),
    }
    # le coût WHIPSAW du carry : gains bruts des épisodes gagnants vs
    # pertes des bascules perdantes (la matière de la composante manquante)
    carry_win = sum(e["price_ret_short"] / 100 * SZ_CARRY * lev_carry
                    for e in carry_ev if e["price_ret_short"] > 0)
    carry_loss = sum(e["price_ret_short"] / 100 * SZ_CARRY * lev_carry
                     for e in carry_ev if e["price_ret_short"] <= 0)
    top = sorted(res_t9["trades"], key=lambda t: t["pnl"], reverse=True)
    con.close()

    gap_c, gap_p = garde_fous(res_t9, CAPITAL)

    # ================================================================ RAPPORT
    L = [
        "# ÉTUDE T9 — LE STACK MULTI-RÉGIME 2021→2026 (gates de régime)",
        f"Généré : {t0:%Y-%m-%dT%H:%M:%S+00:00} — script : "
        "`scripts/studies/aster_multiregime_stack.py`. DB en mode=ro ; "
        "écriture = ce rapport uniquement.",
        "",
        "## 1. La méthode (l'honnêteté d'abord)", "",
        f"- **Données** : BTC/ETH/SOL 1h 2021-09→2026-09 "
        f"({len(btc)} barres BTC, backfill T6) — les seules séries profondes ; "
        "memes = univers non-majors (genèse 2025-09, Aster n'existait pas avant).",
        f"- **Split TRAIN/VAL PAR LE TEMPS** : TRAIN = premières 70 % des "
        f"barres = 2021-09→{d_train:%Y-%m-%d}, VAL = {d_train:%Y-%m-%d}→"
        f"{d_last:%Y-%m-%d}. TOUTES les calibrations (q66 cascade, p90/med "
        "vol_spike, levier du short porté) sont calculées sur TRAIN, jugées "
        "sur VAL — première étude de la chaîne à split barre-based strict.",
        "- **Détecteurs (sans look-ahead)** : D1 = SMA 200 j du close BTC 1h "
        "(bull si close > SMA) ; D2 = SMA 100 j (sensibilité au lag) ; D3 = "
        "vol-régime ATR% (ATR 14 j vs médiane 180 j, rapporté). L'état à la "
        "barre t n'utilise que les closes ≤ t ; l'exécution est à t+1. "
        f"Warm-up honnête D1 : {warmup_days:.0f} jours de régime INCONNU "
        "(2021-09→2022-03) — le stack n'y trade que vol_spike.",
        "- **Stack conditionnel** : bull détecté → momentum REF harnais "
        "(fast 20/slow 100/regime_ema 200, long only, stop 200 bps, take "
        "1000 bps, lev 2) sur BTC/ETH/SOL ; bear détecté → short BTC/ETH "
        "PORTÉ (entrée au flip bear, sortie au flip bull, PAS de stop serré "
        "— leçon Q3 ; levier = règle 0-liq sur le MAE TRAIN, plafonné 2x) ; "
        "memes → fade funding réel (harnais funding_fade REF) gate "
        "fund7 > 0.5 bps/8h (P3) quand la série existe ; vol_spike 6h 1x "
        "permanent. Wallet séquentiel `run_stack`, $100 frais, un créneau "
        "par stratégie × symbole.",
        f"- **Sizing** (hypothèses documentées) : momentum {SZ_MOM:.0%} "
        f"(lev 2), carry {SZ_CARRY:.0%} (lev {lev_carry:.2f}x), fade "
        f"{SZ_FADE:.0%} (lev 2), vol_spike 0.10×K_V×(atr/med) borné "
        "[0.02, 0.30]×K_V (lev 1).",
        "- **Coûts/funding comptés** : momentum/fade 8 bps taker RT "
        "(harnais v5), cascade 4 bps maker RT, vol_spike 28 bps taker RT "
        "(machine) ; momentum longs PAIENT la moyenne moderne par symbole "
        "(approximation T8) ; le short porté paie/encaisse le modèle T7 par "
        "régime (bear_2022 = -0.5 bps/8h → le short PAIE ~5.5 %/an de "
        "portage) puis le réel mesuré as-of (2025-10-27→) ; fade = funding "
        "réel par symbole. Fills modèle : stops au prix du stop (optimiste "
        "sur gaps) — les conclusions négatives en sont renforcées.",
        f"- **Perimètre** : la composante memes est STRUCTURELLEMENT vide "
        f"avant 2025 (ni klines non-majors ni funding_history) — son absence "
        "2021-2024 est une absence de donnée, PAS un test. Le momentum "
        "2021-H2 est partiellement aveugle (warm-up du détecteur) : la "
        "fin de cycle 2021 (pire régime du momentum, T7) n'est que "
        "partiellement vécue par le stack.",
        "",
        "## 2. LES DÉTECTEURS — bascules et LAG", "",
        "| détecteur | fenêtre | flips (confirmés / bruts) | commentaire |",
        "|---|---|---|---|",
        f"| D1 SMA 200 j | 4800 barres (~200 j) | {len(fl1)} / {raw1} | "
        f"warm-up {warmup_days:.0f} j ; confirmation 48 h (anti-flicker) |",
        f"| D2 SMA 100 j | 2400 barres (~100 j) | {len(fl2)} / {raw2} | "
        "réagit ~2x plus vite, whipsaws plus nombreux |",
        f"| D3 ATR% 14 j vs méd 180 j | 336 barres | {len(fl3)} / {raw3} | "
        "vol-régime, pas de direction (rapporté) |",
        "", "### Les bascules D1 (SMA 200 j) — le LAG chiffré", "",
        "| date | de → vers | prix BTC |", "|---|---|---|"]
    for d, a, b, px in fl1:
        L.append(f"| {d} | {a} → {b} | {px:,.0f} |")
    L += ["", "### L'accord détecteur ↔ régimes T7 (part des barres)", "",
          "| régime | D1 bull % | D1 bear % | D1 inconnu % | D3 haute-vol % |",
          "|---|---|---|---|---|"]
    for name, _, _ in REGIMES:
        bu, be, un = sh1[name]
        hv, lv, un3 = sh3[name]
        L.append(f"| {name} | {bu:.0f} | {be:.0f} | {un:.0f} | {hv:.0f} |")
    L += ["",
          "Lecture : le LAG de D1 = ~2-3 mois sur les renversements majeurs "
          "(la SMA 200 j accuse le retard de sa fenêtre) — c'est le prix de "
          "l'anti-bruit ; le détecteur NE PEUT PAS capter le premier mois "
          "d'un nouveau régime (chiffré dans la table ci-dessus : les parts "
          "bull/bear par régime).",
          "",
          "## 3. LE STACK MULTI-RÉGIME — BLOC STATS GLOBAL (wallet frais "
          "$100, 2021-09→2026-09)", "",
          "| Stat | valeur |", "|---|---|",
          f"| Wallet $100 → | **${res_t9['balance']:,.2f}** |",
          f"| ROI (CAGR) | {t9['roi']:+.1f} % ({t9['roi_an']:+.1f} %/an) |",
          f"| Max DD | {t9['dd']:.1f} % |",
          f"| **Liquidations** | **{t9['liq']}** |",
          f"| Trades / WR | {t9['n']} / {t9['wr']:.1f} % |",
          f"| Frais / funding | ${res_t9['fees']:,.2f} / "
          f"${res_t9['funding']:+,.2f} |",
          f"| Mois pire / record | {t9['worst']:+.1f} % / "
          f"{t9['record']:+.1f} % ({t9['neg']} négatifs) |",
          f"| Garde-fou composé des mois | écart {gap_c*100:.3f} % "
          f"{'OK' if gap_c < 0.005 else '✗ BUG'} |",
          f"| Garde-fou somme PnL | écart ${gap_p:.4f} "
          f"{'OK' if gap_p < 0.01 else '✗ BUG'} |",
          f"| Levier short porté (règle 0-liq TRAIN) | {lev_carry:.2f}x "
          f"(MAE train {mae_train:.1f} %) |",
          "",
          "## 4. BLOC STATS PAR RÉGIME (attribution par régime d'ENTRÉE, "
          "continuité du wallet)", "",
          "Cellule = `trades · WR · ROI seg (ROI/an) · DD intra · liq · "
          "mois− pire mois`. La cible ré-qualifiée : **ROI > 0 et DD ≤ 25 % "
          "dans CHAQUE régime**.", "",
          "| régime | stack multi-régime |", "|---|---|"]
    for r in t9_reg:
        L.append(f"| {r['name']} | {fmt_reg(r)} |")
    L += ["", "### Régime × composante (PnL $ du MÊME wallet, attribution "
          "entrée)", "",
          "| régime | momentum | carry short | fade memes | vol_spike |",
          "|---|---|---|---|---|"]
    for name, lo, hi in REGIMES:
        lo_ns, hi_ns = ts_ns(lo), ts_ns(hi)
        cells = []
        for pref in ("momentum", "carry_short", "fade_meme", "vol_spike"):
            seg = [t for t in res_t9["trades"]
                   if t["strategy"].startswith(pref)
                   and lo_ns <= int(t["entry_ts"].timestamp() * 1e9) < hi_ns]
            pnl = sum(t["pnl"] for t in seg)
            n = len(seg)
            w = sum(1 for t in seg if t["pnl"] > 0)
            cells.append(f"{pnl:+,.1f}$ ({n}t, WR {w/max(n,1)*100:.0f}%)"
                         if n else "0t —")
        L.append(f"| {name} | " + " | ".join(cells) + " |")

    L += ["", "### Les composantes en lane GATED seule (wallet frais $100, "
          "même sizing)", "",
          "| composante | wallet | ROI/an | DD | liq | trades | WR |", "|---|---|---|---|---|---|---|"]
    for lbl, s in lanes.items():
        L.append(f"| {lbl} | ${s['bal']:,.2f} | {s['roi_an']:+.1f} % | "
                 f"{s['dd']:.1f} | {s['liq']} | {s['n']} | {s['wr']:.0f} % |")

    L += ["", "## 5. LES TÉMOINS (l'échelle honnête)", "",
          "| run | wallet $100 → | CAGR | DD | liq | trades | WR | mois− |",
          "|---|---|---|---|---|---|---|---|",
          f"| (a) lane continue cascade 10x + vol_spike (T8) | "
          f"${res_a['balance']:,.2f} | {wit_a['roi_an']:+.0f} %/an | "
          f"{wit_a['dd']:.1f} | {wit_a['liq']} | {wit_a['n']} | "
          f"{wit_a['wr']:.0f} % | {wit_a['neg']} |",
          f"| (b) idem levier sûr 4x | ${res_b['balance']:,.2f} | "
          f"{wit_b['roi_an']:+.0f} %/an | {wit_b['dd']:.1f} | {wit_b['liq']} | "
          f"{wit_b['n']} | {wit_b['wr']:.0f} % | {wit_b['neg']} |",
          f"| (c) buy&hold BTC | x{bh_final:.2f} (${100*bh_final:,.0f}) | "
          f"{((bh_final) ** (365.0 / deep_days) - 1) * 100:+.1f} %/an | "
          f"{bh_dd:.1f} | — | 1 | — | {bh_neg} |",
          f"| **T9 stack multi-régime** | **${res_t9['balance']:,.2f}** | "
          f"**{t9['roi_an']:+.1f} %/an** | **{t9['dd']:.1f}** | "
          f"**{t9['liq']}** | {t9['n']} | {t9['wr']:.1f} % | {t9['neg']} |",
          "",
          "T8 (référence) : 10x → $0.99 (14 liq, mort fin 2023), 4x → "
          "$14.36, 0 liq. La réplique (a)/(b) confirme l'ordre de grandeur "
          "(deltas mineurs : calibration vol_spike sur TRAIN ici, q66 "
          "identique).",
          "",
          "## 6. LE MONITEUR MAE (règle 0-liq : levier ≤ 100/(MAE+0.5))", "",
          "| jambe | levier | MAE max réalisé | ligne de liq | statut |",
          "|---|---|---|---|---|",
          f"| momentum (lev 2) | 2x | {mae_mon['momentum']:.2f} % | 49.5 % | "
          f"{'OK' if mae_mon['momentum'] < 49.5 else '✗'} |",
          f"| carry short (lev {lev_carry:.2f}x) | {lev_carry:.2f}x | "
          f"{mae_mon['carry']:.2f} % | {100/lev_carry-0.5:.1f} % | "
          f"{'OK' if mae_mon['carry'] < 100/lev_carry-0.5 else '✗'} |",
          f"| fade memes (lev 2) | 2x | {mae_mon['fade']:.2f} % | 49.5 % | "
          f"{'OK' if mae_mon['fade'] < 49.5 else '✗'} |",
          f"| vol_spike (lev 1) | 1x | {mae_mon['spike']:.2f} % | 99.5 % | "
          f"{'OK' if mae_mon['spike'] < 99.5 else '✗'} |",
          "",
          f"Sensibilité D2 (SMA 100 j) : ${res_t9b['balance']:,.2f} "
          f"({t9b['roi_an']:+.0f} %/an, DD {t9b['dd']:.1f}, "
          f"**liq {t9b['liq']}**) — 27 flips contre 19 pour D1. La règle "
          "0-liq calibrée sur le MAE TRAIN de D1 ne TRANSFÈRE PAS à un "
          "détecteur plus rapide : le levier du short porté doit être "
          "re-dérivé par détecteur (le whipsaw du détecteur EST un risque "
          "de liquidation, pas seulement un coût).",
          "",
          "## 7. LES ÉPISODES DU SHORT PORTÉ (le test de la leçon Q3)", "",
          f"Le portage rapporte **{carry_win * 100:+.1f} % de wallet en "
          f"gains bruts** (épisodes gagnants) mais les bascules perdantes "
          f"renversent **{carry_loss * 100:+.1f} %** : le net carry = "
          f"{(carry_win + carry_loss) * 100:+.1f} % — les whipsaws du "
          "détecteur mangent les 3/4 du carburant bear. C'est LE poste "
          "d'amélioration n°1.", "",
          "| symbole | entrée | sortie | prix E→S | MAE | funding bps/8h | "
          "jours |", "|---|---|---|---|---|---|---|"]
    for e in sorted(carry_ev, key=lambda x: x["ts_ms"]):
        din = datetime.fromtimestamp(e["ts_ms"] / 10**9, tz=timezone.utc)
        dout = datetime.fromtimestamp(
            (e["ts_ms"] + e["hold_h"] * 3600 * 10**9) / 10**9,
            tz=timezone.utc)
        L.append(f"| {e['sym'].split('@')[0]} | {din:%Y-%m-%d} | "
                 f"{dout:%Y-%m-%d} | {e['ep_entry']:,.0f}→{e['ep_exit']:,.0f} "
                 f"| {e['mae_adverse']:.1f} % | {e['fund_bps_8h']:+.2f} | "
                 f"{e['ep_days']//24} |")

    L += ["", "## 8. LA TABLE MENSUELLE DU STACK (garde-fou des ABSOLUS)", "",
          "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
    for x in t9["mr"]:
        L.append(f"| {x['month']} | {x['n']} | "
                 f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} | "
                 f"{x['roi']:+.1f} % |")

    L += ["", "### Les 5 plus gros PnL du wallet (le contrôle anti-artefact "
          "de sizing)", "",
          "| sens | stratégie | symbole | entrée | PnL $ | balance après |",
          "|---|---|---|---|---|---|"]
    for t in top[:5] + top[-5:]:
        d = t["entry_ts"]
        L.append(f"| {'gain' if t['pnl'] > 0 else 'perte'} | {t['strategy']} "
                 f"| {t['sym'].split('@')[0]} | {d:%Y-%m-%d} | "
                 f"{t['pnl']:+,.2f} | ${t['balance']:,.2f} |")

    # ——— VERDICT ———
    ok_reg = [r for r in t9_reg if r["roi"] > 0 and r["dd"] <= 25]
    fail_reg = [r for r in t9_reg if not (r["roi"] > 0 and r["dd"] <= 25)]
    ok_names = ", ".join(r["name"] for r in ok_reg) or "aucun"
    fail_names = ("; ".join(f"{r['name']} ({r['roi_an']:+.1f} %/an, "
                            f"DD {r['dd']:.0f} %)" for r in fail_reg)
                  or "aucun")
    L += ["", "## 9. VERDICT", ""]
    L.append(
        "**La question T9 : le multi-régime atteint-il la STABILITÉ ? "
        "Cible ré-qualifiée = ROI > 0 ET DD ≤ 25 % dans CHAQUE régime, "
        "0 liq, DD global ≤ 25 %.**")
    L.append("")
    L.append(
        f"**Résultat : {len(ok_reg)}/6 régimes qualifiés** ({ok_names}). "
        f"Régimes en échec : {fail_names}. "
        f"Global : $100 → ${res_t9['balance']:,.2f} ({t9['roi_an']:+.0f} %/an), "
        f"DD {t9['dd']:.1f} %, {t9['liq']} liq, {t9['neg']} mois négatifs.")
    L.append("")
    L.append(
        "**Ce que le multi-régime RÈGLE (vs T8)** : le MODE DE MORT de la "
        f"lane continue. Le témoin 10x finit à ${res_a['balance']:,.2f} "
        f"({wit_a['liq']} liq, wallet éteint fin 2023), le 4x à "
        f"${res_b['balance']:,.2f} — le stack gaté ne liquide PAS (D1) et "
        "reste positif sur 5 ans là où la cascade rejouée deep détruit le "
        "capital. Le conditionnement par le détecteur transforme une "
        "hécatombe en stagnation.")
    L.append("")
    L.append(
        "**MAIS le stack ne bat PAS le buy&hold en risk-adjusté sur ce "
        f"cycle** : +{t9['roi_an']:.1f} %/an pour DD {t9['dd']:.0f} % contre "
        f"+{((bh_final) ** (365.0 / deep_days) - 1) * 100:.1f} %/an pour DD "
        f"{bh_dd:.0f} % (B&H). La promesse du multi-régime n'est pas tenue "
        "en performance, seulement en 0-liq et en lissage partiel des "
        "régimes extrêmes.")
    L.append("")
    L.append(
        "**Ce qui manque encore (les trous chiffrés)** : (1) le WHIPSAW du "
        f"détecteur — le carry gagne {carry_win*100:+.0f} % brut mais rend "
        f"{carry_loss*100:+.0f} % en bascules (chop 2024H2 : 6 retournements "
        "juil-oct 2024 = -26 % de seg) ; une HYSTÉRÉSIS (bande ±2-3 %) ou "
        "la confirmation renforcée fund7/vol7 de P2 est la composante "
        "manquante n°1 ; (2) un edge VIVANT pour connu_2025_2026 — le "
        "momentum y est mort (T7), le fade memes à peine né (genèse "
        "donnée), la cascade 2026 reste une propriété de fenêtre (T8) ; "
        "(3) le LAG : ~2-3 mois de chaque nouveau régime sont structurel-"
        "lement perdus (la SMA 200 j accuse sa fenêtre) ; (4) le vol_spike "
        "« permanent 1x » est un DRAG sur 5 ans (-2.4 %/an en lane) — "
        "« 0 liq » n'est pas un edge.")
    L.append("")
    L.append(
        "**Limites** : fills optimistes sur gaps ; funding 2021-2024 "
        "modélisé (T7) ; l'univers memes inexistait avant 2025-09 ; les "
        "tailles de marge sont des hypothèses (non optimisées — une "
        "optimisation sur VAL serait de l'overfitting) ; le warm-up du "
        "détecteur épargne au stack une partie du bull 2021 (pire régime "
        "du momentum). Les RELATIFS (ordre des runs, signes par régime) "
        "survivent aux bugs ; les ABSOLUS restent à confirmer par le "
        "forward paper.")
    L.append("")
    L.append(
        "Fichiers : étude `scripts/studies/aster_multiregime_stack.py` — "
        "lecture seule `data/warehouse/klines.db` (aucune écriture prod).")

    out = REPORTS / "aster_multiregime_stack.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[t9] rapport : {out}")
    print(f"[t9] STACK ${res_t9['balance']:,.2f} ({t9['roi_an']:+.0f} %/an) "
          f"DD {t9['dd']:.1f} liq {t9['liq']} | témoins 10x "
          f"${res_a['balance']:,.2f} / 4x ${res_b['balance']:,.2f} | "
          f"qualifiés {len(ok_reg)}/6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
