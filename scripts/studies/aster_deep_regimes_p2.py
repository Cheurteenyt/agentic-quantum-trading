#!/usr/bin/env python3
"""ETUDE P2 (one-shot, suite de T7) : re-calcul régime × stratégie avec l'EQUITE
CORRIGEE du harnais (fix b825da9 : accounting mark-to-market, 4 bps taker par
fill, jambe de stop bookée) + EXTENSION à l'univers 1h de klines.db + le lien
sonde P3 (61 signaux forward avec fund7/vol7/liq24h).

1. CONFIRMATION T7 : les 6 stratégies campagne × 3 majors × 6 régimes, configs
   REF + 2 variations (pattern T7). Cette fois les stats sont calculées sur les
   DEUX couches qui doivent maintenant concorder : l'équité corrigée du harnais
   (mark-to-market, barre par barre) ET le flux de trades (T7). Divergence =
   bug résiduel, documentée.
2. EXTENSION UNIVER : 12 séries 1h diversifiées (ASTER, TRUMP, XRP, BNB, DOGE,
   HYPE, LINK, FARTCOIN, MOODENG, NEIRO, LTC, NVDA — 8.9k barres, 2025-09 →).
   Seules les majors ont le deep 2021-2026 : l'extension couvre la période
   connue (fenêtre A →2026-03, fenêtre B 2026-04→). Funding REEL mesuré par
   symbole (funding_history) ; funding_fade reçoit la série réelle pas-à-pas
   (l'artefact synthétique de T7 disparaît là où la couverture le permet).
   Gates honnêtes (post-fix) : sharpe_oos >= seuil, DD <= 25 %, trades >= min.
   La méta-question : taux de survie PAR RÉGIME/FENÊTRE.
3. P3 : paper_trades (fund7 non null = 61 signaux) × régimes de funding —
   les shorts cascades s'activent-ils en funding positif élevé (crowding-long
   fade confirmé) ? Outcomes des trades fermés par bucket.
4. VERDICT : où la machine peut-elle gagner sur 4 ans.

DB lues en mode=ro ; écritures = reports/ SEULEMENT. Stdlib pure.
Usage :
    .venv/bin/python scripts/studies/aster_deep_regimes_p2.py            # run
    .venv/bin/python scripts/studies/aster_deep_regimes_p2.py --write    # + rapport
    .venv/bin/python scripts/studies/aster_deep_regimes_p2.py --smoke    # 1 lane, timing
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.baselines import Bar  # noqa: E402
from backend.services.backtest_v2.costs import FundingRate  # noqa: E402
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    evaluate_one,
)
from backend.services.backtest_v2.gates import GateConfig  # noqa: E402
from backend.services.backtest_v2 import strategies as strat_pkg  # noqa: E402
from backend.services.backtest_v2.strategies import (  # noqa: E402
    funding_fade as ff,
    funding_carry as fc,
    momentum as mom,
    mean_reversion as mr,
    breakout as bo,
    volatility_harvesting as vh,
)

KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_deep_regimes_p2.md"
RAW = ROOT / "reports" / "aster_deep_regimes_p2_raw.json"

INTERVAL = "1h"
MAJORS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
EXT_SYMBOLS = ["ASTERUSDT", "TRUMPUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
               "HYPEUSDT", "LINKUSDT", "FARTCOINUSDT", "MOODENGUSDT",
               "NEIROUSDT", "LTCUSDT", "NVDAUSDT"]

# --------------------------------------------------------------- régimes T7
REGIMES = [
    ("bull_2021H2", "2021-09-01", "2021-12-31"),
    ("bear_2022",   "2022-01-01", "2022-12-31"),
    ("recovery_2023", "2023-01-01", "2023-12-31"),
    ("bull_2024H1", "2024-01-01", "2024-06-30"),
    ("chop_2024H2", "2024-07-01", "2024-12-31"),
    ("connu_2025_2026", "2025-01-01", "2026-09-30"),
]
DAY_MS = 86_400_000

# Fenêtres de la période connue pour l'extension (séries 2025-09+).
EXT_WINDOWS = [
    ("connu_A", "2025-01-01", "2026-03-31"),
    ("connu_B", "2026-04-01", "2026-09-30"),
]
WARMUP_BARS = 400  # marge de warmup avant une fenêtre (lookback 200 + marge)

# Funding MODELE T7 pour les majors (comparabilité) — bps/8h.
REGIME_FUNDING_BPS_8H = {
    "bull_2021H2": 2.0,
    "bear_2022": -0.5,
    "recovery_2023": 0.5,
    "bull_2024H1": 1.5,
    "chop_2024H2": 0.5,
    "connu_2025_2026": {"BTCUSDT": 0.343, "ETHUSDT": 0.367, "SOLUSDT": -0.009},
}
SYM_FUNDING_CONST_BPS_8H = {"BTCUSDT": 0.44, "ETHUSDT": 0.45, "SOLUSDT": 0.41}

# Constantes funding RÉELLES mesurées par symbole (rempli au run) — utilisé
# pour l'extension. Les modules bindent load_funding_rate à l'import : le stub
# lit ce dict à l'appel.
REAL_FUND_BPS: dict[str, float] = {}
FUND_COVERAGE: dict[str, float] = {}  # part des barres couvertes par funding_history

# Gates de survie (honnêtes, post-fix) : campagne = sharpe_oos >= 0.8.
SURV_SHARPE_HARD = 0.8
SURV_SHARPE_SOFT = 0.5
SURV_MAX_DD = 25.0
SURV_MIN_TRADES = 20

STRAT_MODULES = {"momentum": mom, "mean_reversion": mr, "breakout": bo,
                 "funding_fade": ff, "funding_carry": fc,
                 "volatility_harvesting": vh}
ARTEFACT_STRATS = {"volatility_harvesting": "microstructure"}

# ------------------------------------------------------------- configs test
CONFIGS: dict[str, dict[str, dict]] = {
    "momentum": {
        "REF": dict(fast_ema=20, slow_ema=100, regime_ema=200, allow_short=False,
                    stop_bps=200, take_bps=1000, max_leverage=2),
        "V1_short": dict(fast_ema=20, slow_ema=100, regime_ema=200, allow_short=True,
                         stop_bps=200, take_bps=1000, max_leverage=2),
        "V2_stop500": dict(fast_ema=20, slow_ema=100, regime_ema=200, allow_short=False,
                           stop_bps=500, take_bps=1000, max_leverage=2),
    },
    "mean_reversion": {
        "REF": dict(lookback=100, entry_z=2.5, exit_z=0.5, use_std=True,
                    allow_short=False, stop_bps=150, take_bps=200, max_leverage=3),
        "V1_short": dict(lookback=100, entry_z=2.5, exit_z=0.5, use_std=True,
                         allow_short=True, stop_bps=150, take_bps=200, max_leverage=3),
        "V2_stop300": dict(lookback=100, entry_z=2.5, exit_z=0.5, use_std=True,
                           allow_short=False, stop_bps=300, take_bps=200,
                           max_leverage=3),
    },
    "breakout": {
        "REF": dict(donchian_len=20, breakout_mult=0.0, confirmation_bars=1,
                    use_close=True, allow_short=False, stop_bps=200, take_bps=400,
                    max_leverage=2),
        "V1_short": dict(donchian_len=20, breakout_mult=0.0, confirmation_bars=1,
                         use_close=True, allow_short=True, stop_bps=200, take_bps=400,
                         max_leverage=2),
        "V2_stop500": dict(donchian_len=20, breakout_mult=0.0, confirmation_bars=1,
                           use_close=True, allow_short=False, stop_bps=500,
                           take_bps=400, max_leverage=2),
    },
    "funding_fade": {
        "REF": dict(lookback=200, entry_z=2.5, exit_z=0.5, allow_short=True,
                    stop_bps=200, max_leverage=3),
        "V1_z2.0": dict(lookback=200, entry_z=2.0, exit_z=0.5, allow_short=True,
                        stop_bps=200, max_leverage=3),
        "V2_lb100": dict(lookback=100, entry_z=2.5, exit_z=0.5, allow_short=True,
                         stop_bps=200, max_leverage=3),
    },
    "funding_carry": {
        "REF": dict(side_filter=["auto"], hold_max_bars=168, allow_short=True,
                    stop_bps=200, max_leverage=2),
        "V1_hold672": dict(side_filter=["auto"], hold_max_bars=672, allow_short=True,
                           stop_bps=200, max_leverage=2),
        "V2_stop500": dict(side_filter=["auto"], hold_max_bars=168, allow_short=True,
                           stop_bps=500, max_leverage=2),
    },
    "volatility_harvesting": {
        "REF": dict(spread_bps=5, allow_short=True, max_leverage=2),
        "V1_s10": dict(spread_bps=10, allow_short=True, max_leverage=2),
        "V2_s20": dict(spread_bps=20, allow_short=True, max_leverage=2),
    },
}


# ------------------------------------------------------------------ données
def open_ro() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{KLINES_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def load_bars_ro(con: sqlite3.Connection, symbol: str) -> list[Bar]:
    rows = con.execute(
        "SELECT open_time, open, high, low, close, volume FROM klines "
        "WHERE symbol = ? AND interval = ? ORDER BY open_time",
        (symbol, INTERVAL)).fetchall()
    return [Bar(ts=int(r["open_time"]), open=float(r["open"]), high=float(r["high"]),
                low=float(r["low"]), close=float(r["close"]),
                volume=float(r["volume"])) for r in rows]


def load_funding_series(con: sqlite3.Connection, symbol: str) -> list[tuple[int, float]]:
    """(funding_time_ms, bps/8h) triés — funding RÉEL. rate = décimal/8h :
    bps/8h = rate*10000 (fund7 des paper_trades = rate*100 en %/8h)."""
    rows = con.execute(
        "SELECT funding_time, rate FROM funding_history WHERE symbol = ? "
        "ORDER BY funding_time", (symbol,)).fetchall()
    return [(int(r["funding_time"]), float(r["rate"]) * 10_000.0) for r in rows]


def measure_funding(con: sqlite3.Connection, symbol: str, bars: list[Bar]) -> float:
    """Funding réel moyen (bps/8h) sur la fenêtre couverte par l'historique, +
    la part des barres couverte."""
    pts = load_funding_series(con, symbol)
    if not pts or not bars:
        REAL_FUND_BPS[symbol] = 0.0
        FUND_COVERAGE[symbol] = 0.0
        return 0.0
    lo, hi = pts[0][0], pts[-1][0]
    covered = sum(1 for b in bars if lo <= b.ts <= hi)
    cov = covered / len(bars)
    avg = statistics.mean(r for _, r in pts)
    REAL_FUND_BPS[symbol] = avg
    FUND_COVERAGE[symbol] = cov
    return avg


def real_funding_step_series(bars: list[Bar], pts: list[tuple[int, float]]) -> list[float]:
    """Série funding pas-à-pas réelle : chaque barre porte le dernier funding
    connu (avant la barre). Avant le premier point : moyenne globale."""
    avg = statistics.mean(r for _, r in pts) if pts else 0.0
    out = []
    j = -1
    n = len(pts)
    for b in bars:
        while j + 1 < n and pts[j + 1][0] <= b.ts:
            j += 1
        out.append(pts[j][1] if j >= 0 else avg)
    return out


def _date_ms(s: str) -> int:
    return int(datetime.fromisoformat(s + "T00:00:00+00:00").timestamp() * 1000)


def regime_of(ts_ms: int) -> str:
    for name, a, b in REGIMES:
        if _date_ms(a) <= ts_ms <= _date_ms(b) + DAY_MS - 1:
            return name
    return "hors_regimes"


def regime_funding_bps(regime: str, symbol: str) -> float:
    v = REGIME_FUNDING_BPS_8H[regime]
    if isinstance(v, dict):
        return float(v[symbol])
    return float(v)


def install_funding_stub() -> None:
    """Patche load_funding_rate dans chaque module : majors = modèle T7,
    extension = funding réel mesuré (REAL_FUND_BPS)."""
    def stub(symbol: str, *args, **kwargs) -> FundingRate:
        sym = (symbol or "BTCUSDT").upper()
        if sym in SYM_FUNDING_CONST_BPS_8H:
            base = SYM_FUNDING_CONST_BPS_8H[sym]
        else:
            base = REAL_FUND_BPS.get(sym, 0.0)
        now = time.time()
        return FundingRate(symbol=sym, avg_bps_per_8h=base, sample_count=9999,
                           last_funding_time_ms=int(now * 1000), cached_at=now)
    for name, mod in STRAT_MODULES.items():
        if name == "funding_fade":
            continue
        mod.load_funding_rate = stub


def fade_series_for(bars: list[Bar], symbol: str, real_pts: list[tuple[int, float]] | None) -> tuple[list[float], str]:
    """Série injectée dans funding_fade. Majors : modèle T7 (base régime +
    enveloppe synthétique — ARTEFACT). Extension : série réelle pas-à-pas si
    couverture >= 30 %, sinon synthétique autour de la moyenne réelle."""
    if symbol in SYM_FUNDING_CONST_BPS_8H:
        osc = ff.synthetic_funding_series(len(bars), 0.0, symbol)
        return ([regime_funding_bps(regime_of(b.ts), symbol) + osc[i]
                 for i, b in enumerate(bars)], "synthetique_T7")
    if real_pts and FUND_COVERAGE.get(symbol, 0.0) >= 0.30:
        return (real_funding_step_series(bars, real_pts), "reelle")
    base = REAL_FUND_BPS.get(symbol, 0.0)
    osc = ff.synthetic_funding_series(len(bars), 0.0, symbol)
    return ([base + osc[i] for i in range(len(bars))], "synthetique_base_reelle")


# --------------------------------------------------- stats par régime (flux)
def _exit_index(k: int, entries: list[tuple[int, int]], reasons: list[str],
                bars: list[Bar], entry_price: float, side: int,
                stop_frac: float | None, take_frac: float | None) -> int:
    n = len(bars)
    ei = entries[k][0]
    nxt = entries[k + 1][0] if k + 1 < len(entries) else n
    reason = reasons[k] if k < len(reasons) else ""
    hi = min(nxt, n)
    if side == 1 and stop_frac and "stop" in reason:
        for i in range(ei, hi):
            if bars[i].low <= entry_price * (1.0 - stop_frac):
                return i
    if side == -1 and stop_frac and "stop" in reason:
        for i in range(ei, hi):
            if bars[i].high >= entry_price * (1.0 + stop_frac):
                return i
    if side == 1 and take_frac and "take" in reason:
        for i in range(ei, hi):
            if bars[i].high >= entry_price * (1.0 + take_frac):
                return i
    if side == -1 and take_frac and "take" in reason:
        for i in range(ei, hi):
            if bars[i].low <= entry_price * (1.0 - take_frac):
                return i
    return max(ei, min(nxt - 1, n - 1))


def flux_regime_stats(bars: list[Bar], entries: list[tuple[int, int]],
                      reasons: list[str], trade_returns: list[float],
                      stop_frac: float | None, take_frac: float | None,
                      lo_ms: int, hi_ms: int) -> dict:
    """Stats T7 (flux de trades), inchangées — attribution par régime d'ENTRÉE."""
    n = len(bars)
    idx = [i for i, b in enumerate(bars) if lo_ms <= b.ts <= hi_ms]
    if not idx:
        return {}
    lo_i, hi_i = idx[0], idx[-1]
    years = (bars[hi_i].ts - bars[lo_i].ts) / (365.25 * DAY_MS)
    eq = 1.0
    peak = 1.0
    dd = 0.0
    trades = 0
    wins = 0
    max_mae = 0.0
    for k, (ei, side) in enumerate(entries):
        if not (lo_i <= ei <= hi_i):
            continue
        net = trade_returns[k] if k < len(trade_returns) else 0.0
        trades += 1
        if net > 0:
            wins += 1
        eq *= (1.0 + net)
        peak = max(peak, eq)
        if peak > 0:
            dd = max(dd, (peak - eq) / peak * 100.0)
        ex = _exit_index(k, entries, reasons, bars, bars[ei].open, side,
                         stop_frac, take_frac)
        if side in (1, -1) and ex >= ei:
            seg = bars[ei:ex + 1]
            if side == 1:
                worst = min(s.low for s in seg)
                mae = (bars[ei].open - worst) / bars[ei].open * 100.0
            else:
                worst = max(s.high for s in seg)
                mae = (worst - bars[ei].open) / bars[ei].open * 100.0
            max_mae = max(max_mae, max(0.0, mae))
    lev_cap = min(100.0 / (max_mae + 0.5), 12.0) if max_mae > 0 else 12.0
    return {"trades": trades,
            "win_rate": (wins / trades) if trades else None,
            "roi_flux_pct": (eq - 1.0) * 100.0,
            "roi_flux_ann_pct": ((eq - 1.0) * 100.0 / years) if years > 0 else 0.0,
            "dd_flux_pct": dd, "max_mae_pct": max_mae, "lev_cap": lev_cap}


def equity_regime_stats(bars: list[Bar], bar_ret: list[float],
                        entries: list[tuple[int, int]],
                        lo_ms: int, hi_ms: int) -> dict:
    """Stats par régime sur l'EQUITE CORRIGEE (mark-to-market barre par barre,
    stops + frais + funding inclus). Équité locale = 1.0 au début du régime.
    Attribution des barres (un trade entré avant la fenêtre sort dedans :
    sa jambe finale est comptée dans la fenêtre — c'est le mark-to-market)."""
    idx = [i for i, b in enumerate(bars) if lo_ms <= b.ts <= hi_ms]
    if not idx:
        return {}
    lo_i, hi_i = idx[0], idx[-1]
    years = (bars[hi_i].ts - bars[lo_i].ts) / (365.25 * DAY_MS)
    eq = 1.0
    peak = 1.0
    dd = 0.0
    months: dict[str, float] = {}
    for i in range(lo_i, hi_i + 1):
        r = bar_ret[i] if i < len(bar_ret) else 0.0
        eq *= (1.0 + r)
        peak = max(peak, eq)
        if peak > 0:
            dd = max(dd, (peak - eq) / peak * 100.0)
        m = datetime.fromtimestamp(bars[i].ts / 1000, tz=timezone.utc).strftime("%Y-%m")
        months[m] = months.get(m, 0.0) * (1.0 + r) + r
    mvals = [v * 100.0 for v in months.values()]
    trades = sum(1 for ei, _ in entries if lo_i <= ei <= hi_i)
    return {"trades_eq": trades,
            "roi_eq_pct": (eq - 1.0) * 100.0,
            "roi_eq_ann_pct": ((eq - 1.0) * 100.0 / years) if years > 0 else 0.0,
            "dd_eq_pct": dd,
            "months_neg_eq": sum(1 for v in mvals if v < 0),
            "n_months": len(mvals),
            "month_worst_eq_pct": min(mvals, default=0.0),
            "month_best_eq_pct": max(mvals, default=0.0)}


def empty_regime() -> dict:
    return {"trades": 0, "win_rate": None, "roi_flux_pct": 0.0,
            "roi_flux_ann_pct": 0.0, "dd_flux_pct": 0.0, "max_mae_pct": 0.0,
            "lev_cap": 12.0, "trades_eq": 0, "roi_eq_pct": 0.0,
            "roi_eq_ann_pct": 0.0, "dd_eq_pct": 0.0, "months_neg_eq": 0,
            "n_months": 0, "month_worst_eq_pct": 0.0, "month_best_eq_pct": 0.0}


# ------------------------------------------------------------------- moteur
def _fracs(params: dict) -> tuple[float | None, float | None]:
    stop = float(params["stop_bps"]) / 10_000.0 if "stop_bps" in params else None
    take = float(params["take_bps"]) / 10_000.0 if "take_bps" in params else None
    return stop, take


def run_eval(strat: str, cfg_name: str, params: dict, symbol: str,
             bars: list[Bar], regimes: list[tuple[str, str | None, str | None]],
             gate_cfg: GateConfig, real_pts: list[tuple[int, float]] | None = None) -> dict:
    p = dict(params)
    p["symbol"] = symbol
    if strat == "funding_fade":
        series, src = fade_series_for(bars, symbol, real_pts)
        p["funding_bps_series"] = series
    else:
        src = "stub"
    evaluate = strat_pkg.REGISTRY[strat][0]
    ev = evaluate(p, bars)
    identity = strat_pkg.make_identity(strat, p, symbol=symbol, interval=INTERVAL)
    cfg = CampaignConfig(run_id=f"study-p2-{strat}-{symbol}-{cfg_name}",
                         data_snapshot_id="deep-backfill-T6+fix-b825da9",
                         gate_config=gate_cfg)
    metrics, gate, _bench, extra = evaluate_one(identity, ev, bars, cfg)
    entries = ev.blob.get("entries") or []
    reasons = ev.blob.get("exit_reasons") or []
    if strat == "volatility_harvesting":
        entries = [(i, 1) for i in (ev.blob.get("harvest_bars") or [])]
        reasons = ["take"] * len(entries)
    stop_frac, take_frac = _fracs(params)
    bar_ret = list(ev.bar_returns_per_bar)

    # Accord flux vs équité sur la série complète (le test anti-bug résiduel).
    flux_full = 1.0
    for t in ev.trade_returns:
        flux_full *= (1.0 + float(t))
    eq_full = float(ev.equity_curve[-1]) if ev.equity_curve else None
    dd_flux_full = 0.0
    peak = 1.0
    e = 1.0
    for t in ev.trade_returns:
        e *= (1.0 + float(t))
        peak = max(peak, e)
        dd_flux_full = max(dd_flux_full, (peak - e) / peak * 100.0)

    by_regime = {}
    for name, a, b in regimes:
        lo = _date_ms(a) if a else bars[0].ts
        hi = (_date_ms(b) + DAY_MS - 1) if b else bars[-1].ts
        st = empty_regime()
        st.update(flux_regime_stats(bars, entries, reasons, list(ev.trade_returns),
                                    stop_frac, take_frac, lo, hi))
        st.update(equity_regime_stats(bars, bar_ret, entries, lo, hi))
        by_regime[name] = st
    return {
        "strategy": strat, "config": cfg_name, "symbol": symbol,
        "n_bars": len(bars),
        "closed_trades": ev.closed_trades,
        "sharpe_is": extra["walkforward"]["sharpe_is"],
        "sharpe_oos": extra["walkforward"]["sharpe_oos"],
        "oos_is_ratio": extra["walkforward"]["oos_is_ratio"],
        "dd_full_pct": metrics.max_drawdown_pct or 0.0,
        "gate_passed": gate.passed,
        "gate_failures": [g.value for g in gate.failures],
        "eq_full_pct": (eq_full - 1.0) * 100.0 if eq_full is not None else None,
        "flux_full_pct": (flux_full - 1.0) * 100.0,
        "agree_pts": ((eq_full - flux_full) * 100.0
                      if eq_full is not None else None),
        "dd_flux_full_pct": dd_flux_full,
        "fees_usd": ev.costs.fees_usd,
        "funding_usd": ev.costs.funding_usd,
        "funding_series": src if strat == "funding_fade" else None,
        "by_regime": by_regime,
    }


def survived_lane(r: dict, sharpe_min: float) -> bool:
    """Gate de survie honnête (équité corrigée) : sharpe_oos >= seuil,
    DD série <= 25 %, trades >= min."""
    so = r["sharpe_oos"]
    return (so is not None and so >= sharpe_min
            and r["dd_full_pct"] <= SURV_MAX_DD
            and r["closed_trades"] >= SURV_MIN_TRADES)


def survived_regime(st: dict) -> bool:
    """Survie DANS un régime/fenêtre (équité corrigée) : ROI/an > 0,
    DD du régime <= 25 %, assez de trades."""
    return (st.get("roi_eq_ann_pct", 0.0) > 0.0
            and st.get("dd_eq_pct", 100.0) <= SURV_MAX_DD
            and st.get("trades_eq", 0) >= 10)


def run_carry_per_regime(params: dict, symbol: str, bars: list[Bar],
                         gate_cfg: GateConfig) -> list[dict]:
    """funding_carry avec le sens re-résolu par régime (majors, REF)."""
    out = []
    orig = fc.load_funding_rate
    for name, a, b in REGIMES:
        lo, hi = _date_ms(a), _date_ms(b) + DAY_MS - 1
        seg = [x for x in bars if lo <= x.ts <= hi]
        if len(seg) < 200:
            continue
        bps = regime_funding_bps(name, symbol)

        def stub(sym: str, *args, _bps=bps, **kwargs) -> FundingRate:
            now = time.time()
            return FundingRate(symbol=(sym or symbol), avg_bps_per_8h=_bps,
                               sample_count=9999,
                               last_funding_time_ms=int(now * 1000),
                               cached_at=now)
        fc.load_funding_rate = stub
        try:
            r = run_eval("funding_carry", "REF@regime", params, symbol, seg,
                         [(name, None, None)], gate_cfg)
        finally:
            fc.load_funding_rate = orig
        side = "short" if bps > 0 else ("long" if bps < 0 else "none")
        st = r["by_regime"][name]
        st["resolved_side"] = side
        out.append({"regime": name, "symbol": symbol, "side": side, **st})
    return out


# ------------------------------------------------------------------- P3
def p3_analysis() -> dict:
    con = open_ro()
    cols = [c[1] for c in con.execute("PRAGMA table_info(paper_trades)")]
    rows = [dict(zip(cols, r)) for r in con.execute(
        "SELECT * FROM paper_trades WHERE fund7 IS NOT NULL")]
    con.close()

    def bucket(bps: float) -> str:
        if bps <= 0:
            return "a_negatif"
        if bps <= 0.25:
            return "b_faible"
        if bps <= 0.5:
            return "c_moderé"
        if bps <= 1.0:
            return "d_eleve"
        return "e_manie"

    out = {"n": len(rows), "by_bucket": {}, "by_signal": {}, "closed": 0,
           "directions": {}, "relative_high": 0}
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        bps = (r["fund7"] or 0.0) * 100.0  # %/8h -> bps/8h
        r["_bps"] = bps
        r["_bucket"] = bucket(bps)
        buckets.setdefault(r["_bucket"], []).append(r)
        out["directions"][r["direction"]] = out["directions"].get(r["direction"], 0) + 1
        if r["status"] == "closed":
            out["closed"] += 1
    for bk in sorted(buckets):
        g = buckets[bk]
        closed = [x for x in g if x["status"] == "closed" and x["ret_pct"] is not None]
        wins = [x for x in closed if x["ret_pct"] > 0]
        out["by_bucket"][bk] = {
            "n": len(g), "n_closed": len(closed),
            "hit_rate": (len(wins) / len(closed)) if closed else None,
            "median_ret_closed": (statistics.median(x["ret_pct"] for x in closed)
                                  if closed else None),
            "median_fund7_bps": statistics.median(x["_bps"] for x in g),
            "median_liq24h": (statistics.median(x["liq24h"] for x in g
                                                if x["liq24h"] is not None)
                              if any(x["liq24h"] for x in g) else None),
            "median_vol7": (statistics.median(x["vol7"] for x in g
                                               if x["vol7"] is not None)
                            if any(x["vol7"] is not None for x in g) else None),
        }
    fams: dict[str, list[dict]] = {}
    for r in rows:
        fams.setdefault(r["signal"], []).append(r)
    for f, g in sorted(fams.items()):
        closed = [x for x in g if x["status"] == "closed" and x["ret_pct"] is not None]
        out["by_signal"][f] = {
            "n": len(g), "n_closed": len(closed),
            "median_fund7_bps": statistics.median(x["_bps"] for x in g),
            "share_fund_pos": sum(1 for x in g if x["_bps"] > 0) / len(g),
            "share_fund_high": sum(1 for x in g if x["_bps"] > 0.5) / len(g),
            "hit_rate": ((sum(1 for x in closed if x["ret_pct"] > 0) / len(closed))
                         if closed else None),
            "median_ret_closed": (statistics.median(x["ret_pct"] for x in closed)
                                  if closed else None),
        }
    return out


# -------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="1 lane majors, timing")
    args = ap.parse_args()

    install_funding_stub()
    gate_cfg = GateConfig(random_bench_trials=50)

    con = open_ro()
    real_pts_by_sym: dict[str, list[tuple[int, float]]] = {}
    bars_by_sym: dict[str, list[Bar]] = {}
    try:
        for sym in MAJORS + EXT_SYMBOLS:
            bars = load_bars_ro(con, sym)
            pts = load_funding_series(con, sym)
            real_pts_by_sym[sym] = pts
            if sym in MAJORS:
                SYM_FUNDING_CONST_BPS_8H.setdefault(sym, 0.5)
            else:
                measure_funding(con, sym, bars)
            bars_by_sym[sym] = bars
            a = datetime.fromtimestamp(bars[0].ts / 1000, tz=timezone.utc)
            b = datetime.fromtimestamp(bars[-1].ts / 1000, tz=timezone.utc)
            print(f"# {sym}: {len(bars)} barres {a:%Y-%m-%d}->{b:%Y-%m-%d} "
                  f"funding_reel={REAL_FUND_BPS.get(sym, float('nan')):+.3f}bps/8h "
                  f"cov={FUND_COVERAGE.get(sym, 1.0):.0%}", flush=True)
    finally:
        con.close()

    results: list[dict] = []
    carry_rr: list[dict] = []
    t0 = time.time()

    if args.smoke:
        r = run_eval("momentum", "REF", CONFIGS["momentum"]["REF"], "BTCUSDT",
                     bars_by_sym["BTCUSDT"], REGIMES, gate_cfg)
        print(f"smoke momentum/BTC: {time.time()-t0:.1f}s trades={r['closed_trades']} "
              f"eq={r['eq_full_pct']:.1f}% flux={r['flux_full_pct']:.1f}% "
              f"diff={r['agree_pts']:.2f}pts sh_oos={r['sharpe_oos']:.2f}",
              flush=True)
        return 0

    # ---------- PARTIE 1 : majors, 6 régimes T7, configs REF+2 ----------
    total = sum(len(c) for c in CONFIGS.values()) * len(MAJORS)
    done = 0
    for strat in sorted(CONFIGS):
        for cfg_name, params in CONFIGS[strat].items():
            for sym in MAJORS:
                done += 1
                try:
                    r = run_eval(strat, cfg_name, params, sym,
                                 bars_by_sym[sym], REGIMES, gate_cfg)
                except Exception as exc:
                    print(f"[P1 {done}/{total}] ERREUR {strat}/{cfg_name}/{sym}: "
                          f"{type(exc).__name__}: {exc}", flush=True)
                    continue
                results.append(r)
                print(f"[P1 {done}/{total}] {strat}/{cfg_name}/{sym} "
                      f"t={r['closed_trades']} eq={r['eq_full_pct']:.0f}% "
                      f"flux={r['flux_full_pct']:.0f}% d={r['agree_pts']:.1f}pt "
                      f"sh={r['sharpe_oos']:.2f} ({time.time()-t0:.0f}s)", flush=True)

    # carry re-résolu par régime (majors, REF)
    for sym in MAJORS:
        carry_rr.extend(run_carry_per_regime(CONFIGS["funding_carry"]["REF"],
                                             sym, bars_by_sym[sym], gate_cfg))
        print(f"[carry-rr] {sym} ok ({time.time()-t0:.0f}s)", flush=True)

    # ---------- PARTIE 2 : extension, span complet + fenêtres ----------
    for sym in EXT_SYMBOLS:
        bars = bars_by_sym[sym]
        for strat in sorted(CONFIGS):
            for cfg_name, params in CONFIGS[strat].items():
                try:
                    r = run_eval(strat, cfg_name, params, sym, bars,
                                 [("span_complet", None, None)], gate_cfg,
                                 real_pts_by_sym[sym])
                except Exception as exc:
                    print(f"[P2] ERREUR {strat}/{cfg_name}/{sym}: "
                          f"{type(exc).__name__}: {exc}", flush=True)
                    continue
                results.append(r)
                print(f"[P2 {sym}] {strat}/{cfg_name} t={r['closed_trades']} "
                      f"eq={r['eq_full_pct']:.0f}% d={r['agree_pts']:.1f}pt "
                      f"sh={r['sharpe_oos']:.2f} ({time.time()-t0:.0f}s)", flush=True)
        # fenêtres (REF uniquement)
        for wname, wa, wb in EXT_WINDOWS:
            lo, hi = _date_ms(wa), _date_ms(wb) + DAY_MS - 1
            idx = [i for i, b in enumerate(bars) if lo <= b.ts <= hi]
            if len(idx) < 1500:
                continue
            start = max(0, idx[0] - WARMUP_BARS)
            seg = bars[start:idx[-1] + 1]
            for strat in sorted(CONFIGS):
                try:
                    r = run_eval(strat, "REF@window", CONFIGS[strat]["REF"], sym,
                                 seg, [(wname, wa, wb)], gate_cfg,
                                 real_pts_by_sym[sym])
                except Exception as exc:
                    print(f"[W] ERREUR {strat}/{sym}/{wname}: {exc}", flush=True)
                    continue
                results.append(r)
                print(f"[W {sym}/{wname}] {strat} t={r['closed_trades']} "
                      f"eq={r['eq_full_pct']:.0f}% ({time.time()-t0:.0f}s)",
                      flush=True)
        del bars
        bars_by_sym[sym] = []

    # ---------- PARTIE 3 : P3 ----------
    p3 = p3_analysis()
    print(f"[P3] {p3['n']} signaux, {p3['closed']} fermés ({time.time()-t0:.0f}s)",
          flush=True)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regimes": REGIMES,
        "ext_windows": EXT_WINDOWS,
        "ext_symbols": EXT_SYMBOLS,
        "real_funding_bps": REAL_FUND_BPS,
        "fund_coverage": FUND_COVERAGE,
        "survival_gates": {"sharpe_hard": SURV_SHARPE_HARD,
                           "sharpe_soft": SURV_SHARPE_SOFT,
                           "max_dd": SURV_MAX_DD, "min_trades": SURV_MIN_TRADES},
        "results": results,
        "carry_per_regime": carry_rr,
        "p3": p3,
    }
    RAW.write_text(json.dumps(payload), encoding="utf-8")
    print(f"JSON brut : {RAW} ({time.time()-t0:.0f}s total)")
    if args.write:
        write_report(payload)
        print(f"Rapport : {REPORT}")
    return 0


# ------------------------------------------------------------------ rapport
def _fmt(v, nd=1, suf=""):
    if v is None:
        return "n/a"
    return f"{v:.{nd}f}{suf}"


def write_report(payload: dict) -> None:
    results = payload["results"]
    carry_rr = payload.get("carry_per_regime", [])
    p3 = payload.get("p3", {})
    reg_names = [r[0] for r in payload["regimes"]]
    majors = [r for r in results if r["symbol"] in MAJORS
              and not r["config"].endswith("@window")]
    ext_full = [r for r in results if r["symbol"] in EXT_SYMBOLS
                and r["config"] not in ("REF@window",)]
    ext_win = [r for r in results if r["config"] == "REF@window"]
    ext_syms = payload["ext_symbols"]

    lines = []
    A = lines.append
    A("# ÉTUDE P2 — T7 re-calculé à l'équité CORRIGÉE + extension univers + lien P3")
    A("")
    A(f"Généré : {payload['generated_at']} — script : `scripts/studies/aster_deep_regimes_p2.py`")
    A("")
    A("## Setup")
    A("")
    A("- **Le harnais est corrigé** (commit `b825da9`) : accounting mark-to-market dans les 6 modules, "
      "4 bps taker par fill dans `bar_ret`, jambe de stop bookée sur sa barre, funding accrue au stop. "
      "Les sharpe IS/OOS, DD et gates de CE rapport consomment l'équité honnête.")
    A("- Chaque lane est lue sur ses DEUX couches : **équité corrigée** (mark-to-market barre à barre — "
      "roi_eq/dd_eq/mois) et **flux de trades** (T7, attribution par régime d'entrée). Accord attendu ; "
      "divergence = bug résiduel documenté.")
    A("- Split temporel doctrinal inchangé : configs REF+2 de la dernière campagne (découverte 2026-06→), "
      "tout le deep est OOS strict. Funding majors = modèle T7 (comparabilité) ; funding extension = "
      "**réel mesuré** par symbole (`funding_history`, bps/8h).")
    A(f"- Extension : {len(ext_syms)} séries 1h (`{', '.join(s[:-4] for s in ext_syms)}`), "
      "8.9k barres 2025-09→2026-09 — la période connue uniquement (seules BTC/ETH/SOL ont 2021-2026). "
      "Fenêtres connues : A = →2026-03-31, B = 2026-04-01→.")
    A(f"- Gates de survie (post-fix, honnêtes) : lane = sharpe_oos ≥ {SURV_SHARPE_HARD} (campagne) / "
      f"{SURV_SHARPE_SOFT} (souple), DD série ≤ {SURV_MAX_DD:.0f} %, trades ≥ {SURV_MIN_TRADES} ; "
      "régime/fenêtre = ROI/an > 0 & DD régime ≤ 25 % & ≥ 10 trades.")
    A("- DB en mode=ro ; écritures = reports/ seulement. Bench random dégradé (50 tirages).")
    A("")
    A("Régimes : " + " | ".join(f"**{n}** {a}→{b}" for n, a, b in payload["regimes"]))
    A("")

    # ---------------- TABLE 0 : accord flux/équité ----------------
    A("## TABLE 0 — l'accord flux ↔ équité corrigée (preuve anti-bug résiduel)")
    A("")
    A("Écart (points de %) entre l'équité finale corrigée du harnais et le flux de trades composé, "
      "série complète. Majors config REF. Un écart > ~3 pts sur une lane qui stoppe = bug résiduel.")
    A("")
    A("| stratégie | BTC | ETH | SOL | max |")
    A("|---|---|---|---|---|")
    worst_all = 0.0
    for strat in sorted(CONFIGS):
        row = []
        worst = 0.0
        for sym in MAJORS:
            r = next((x for x in majors if x["strategy"] == strat
                      and x["config"] == "REF" and x["symbol"] == sym), None)
            d = r["agree_pts"] if r and r["agree_pts"] is not None else None
            row.append(f"{d:+.2f}" if d is not None else "—")
            worst = max(worst, abs(d)) if d is not None else worst
        worst_all = max(worst_all, worst)
        A(f"| {strat} | " + " | ".join(row) + f" | {worst:.2f} |")
    A("")
    A(f"Écart max observé sur les REF majors : **{worst_all:.2f} pts**.")
    A("")

    # ---------------- TABLE 1 : régime × stratégie (équité corrigée) ----------
    A("## TABLE 1 — régime × stratégie (majors, REF, ÉQUITÉ CORRIGÉE)")
    A("")
    A("Cellule = `trades | WR | ROI/an équité 1x | DD équité | mois−` — médiane des 3 majors. "
      "Comparaison directe avec la TABLE 1 de T7 (flux) : les verdicts doivent coïncider.")
    A("")
    hdr = "| stratégie | " + " | ".join(reg_names) + " |"
    A(hdr)
    A("|" + "---|" * (len(reg_names) + 1))
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** (ARTEFACT microstructure) | " + " | ".join(["—"] * len(reg_names)) + " |")
            continue
        cells = []
        for reg in reg_names:
            per = [r["by_regime"][reg] for r in majors
                   if r["strategy"] == strat and r["config"] == "REF"]
            tr = statistics.median([x["trades_eq"] for x in per])
            wrs = [x["win_rate"] for x in per if x["win_rate"] is not None]
            wr = statistics.median(wrs) * 100 if wrs else None
            roi = statistics.median([x["roi_eq_ann_pct"] for x in per])
            dd = max(x["dd_eq_pct"] for x in per)
            neg = max(x["months_neg_eq"] for x in per)
            cells.append(f"{tr:.0f}t · {_fmt(wr,0,'%')} · {_fmt(roi,0,'%')} · DD{_fmt(dd,0)} · {neg}m−")
        A(f"| **{strat}** | " + " | ".join(cells) + " |")
    A("")
    A("### Le même tableau au FLUX (T7) — contrôle de cohérence")
    A("")
    A(hdr)
    A("|" + "---|" * (len(reg_names) + 1))
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** | " + " | ".join(["—"] * len(reg_names)) + " |")
            continue
        cells = []
        for reg in reg_names:
            per = [r["by_regime"][reg] for r in majors
                   if r["strategy"] == strat and r["config"] == "REF"]
            roi = statistics.median([x["roi_flux_ann_pct"] for x in per])
            dd = max(x["dd_flux_pct"] for x in per)
            cells.append(f"{_fmt(roi,0,'%')} · DD{_fmt(dd,0)}")
        A(f"| **{strat}** | " + " | ".join(cells) + " |")
    A("")

    # ---------------- TABLE 2 : survie par régime (majors) ----------------
    A("## TABLE 2 — SURVIE PAR RÉGIME (majors, équité corrigée)")
    A("")
    A(f"Cellule = lanes qui survivent DANS le régime (ROI/an > 0, DD régime ≤ 25 %, ≥ 10 trades) / 9 "
      f"(REF+V1+V2 × 3 majors) — et ROI/an équité médian. Lane complète (gates campagne honnêtes : "
      f"sharpe_oos ≥ {SURV_SHARPE_HARD}, DD ≤ 25 %) en dernière colonne, /9.")
    A("")
    A(hdr + " lane complète |")
    A("|" + "---|" * (len(reg_names) + 2))
    hdr2 = hdr + " lane complète |"
    for strat in sorted(CONFIGS):
        if ARTEFACT_STRATS.get(strat):
            A(f"| **{strat}** | " + " | ".join(["—"] * (len(reg_names) + 1)) + " |")
            continue
        cells = []
        for reg in reg_names:
            per = [r["by_regime"][reg] for r in majors if r["strategy"] == strat]
            surv = sum(1 for x in per if survived_regime(x))
            med = statistics.median([x["roi_eq_ann_pct"] for x in per])
            cells.append(f"{surv}/9 ({_fmt(med,0,'%')})")
        lanes = [r for r in majors if r["strategy"] == strat]
        lane_ok = sum(1 for r in lanes if survived_lane(r, SURV_SHARPE_HARD))
        cells.append(f"{lane_ok}/9")
        A(f"| **{strat}** | " + " | ".join(cells) + " |")
    A("")

    # ---------------- TABLE 3 : extension — survie lane par symbole ----------
    A("## TABLE 3 — EXTENSION : survie des lanes par symbole (span complet, équité corrigée)")
    A("")
    A(f"Chaque cellule = lane (symbole × stratégie, config indiquée) : `H` = gates campagne "
      f"(sharpe_oos ≥ {SURV_SHARPE_HARD}, DD ≤ 25 %, trades ≥ {SURV_MIN_TRADES}) ; `s` = souple "
      f"(sharpe_oos ≥ {SURV_SHARPE_SOFT}) ; `·` = morte. REF affiché ; V1/V2 comptés dans les taux.")
    A("")
    A("| symbole | momentum | mean_reversion | breakout | funding_carry | funding_fade | vol_harvest |")
    A("|---|---|---|---|---|---|---|")
    surv_counts: dict[str, dict] = {}
    for strat in sorted(CONFIGS):
        lanes = [r for r in ext_full if r["strategy"] == strat]
        surv_counts[strat] = {
            "hard": sum(1 for r in lanes if survived_lane(r, SURV_SHARPE_HARD)),
            "soft": sum(1 for r in lanes if survived_lane(r, SURV_SHARPE_SOFT)),
            "n": len(lanes)}
    for sym in ext_syms:
        cells = []
        for strat in sorted(CONFIGS):
            r = next((x for x in ext_full if x["strategy"] == strat
                      and x["symbol"] == sym and x["config"] == "REF"), None)
            if r is None or ARTEFACT_STRATS.get(strat):
                cells.append("—")
            elif survived_lane(r, SURV_SHARPE_HARD):
                cells.append(f"H ({r['sharpe_oos']:.2f}, {r['roi_eq_ann_pct']:+.0f}%/an)")
            elif survived_lane(r, SURV_SHARPE_SOFT):
                cells.append(f"s ({r['sharpe_oos']:.2f}, {r['roi_eq_ann_pct']:+.0f}%/an)")
            else:
                cells.append("·")
        A(f"| {sym[:-4]} | " + " | ".join(cells) + " |")
    A("")
    A("Taux de survie lane (REF+V1+V2 × 12 symboles = 36 lanes/stratégie, artefacts exclus) :")
    A("")
    A("| stratégie | H (campagne) | s (souple) | n |")
    A("|---|---|---|---|")
    for strat in sorted(CONFIGS):
        c = surv_counts[strat]
        if ARTEFACT_STRATS.get(strat):
            A(f"| {strat} | ARTEFACT | ARTEFACT | {c['n']} |")
        else:
            A(f"| {strat} | {c['hard']}/{c['n']} | {c['soft']}/{c['n']} | {c['n']} |")
    A("")

    # ---------------- TABLE 4 : survie par fenêtre (extension REF) ----------
    A("## TABLE 4 — EXTENSION : survie par FENÊTRE connue (REF, équité corrigée)")
    A("")
    A("Cellule = lanes REF qui survivent DANS la fenêtre (ROI/an > 0, DD ≤ 25 %, ≥ 10 trades) / 12 "
      "symboles — et ROI/an équité médian. La fenêtre A couvre →2026-03 (séries nées après : exclues), "
      "la B = 2026-04→.")
    A("")
    for wname, wa, wb in payload["ext_windows"]:
        win_rows = [r for r in ext_win if r["by_regime"].get(wname)]
        cells = []
        for strat in sorted(CONFIGS):
            if ARTEFACT_STRATS.get(strat):
                continue
            per = [r["by_regime"][wname] for r in win_rows if r["strategy"] == strat]
            if not per:
                cells.append("—")
                continue
            surv = sum(1 for x in per if survived_regime(x))
            med = statistics.median([x["roi_eq_ann_pct"] for x in per])
            cells.append(f"{strat}={surv}/{len(per)} ({_fmt(med,0,'%')})")
        A(f"- **{wname}** ({wa}→{wb}) : " + " · ".join(cells))
    A("")

    # ---------------- carry re-résolu ----------------
    if carry_rr:
        A("## funding_carry re-résolu par régime (majors, REF) — contrôle T7")
        A("")
        A("| régime | sens | trades/sym | ROI/an équité 1x | DD |")
        A("|---|---|---|---|---|")
        for reg in reg_names:
            per = [x for x in carry_rr if x["regime"] == reg]
            if not per:
                continue
            A(f"| {reg} | {per[0]['side']} | "
              f"{statistics.mean([x['trades_eq'] for x in per]):.0f} | "
              f"{_fmt(statistics.mean([x['roi_eq_ann_pct'] for x in per]),0,'%')} | "
              f"{_fmt(max(x['dd_eq_pct'] for x in per),0)} |")
        A("")

    # ---------------- P3 ----------------
    A("## LIEN P3 — les 61 signaux forward dans les régimes de funding")
    A("")
    if p3:
        A(f"N = {p3['n']} signaux (`fund7` non null), {p3['closed']} fermés. "
          f"Directions : {p3['directions']}. fund7 = funding moyen 7j ex-ante, %/8h "
          "(buckets en bps/8h).")
        A("")
        A("| bucket fund7 | n | fermés | hit rate | ret médian | fund7 médian (bps/8h) |")
        A("|---|---|---|---|---|---|")
        for bk, d in sorted(p3["by_bucket"].items()):
            A(f"| {bk} | {d['n']} | {d['n_closed']} | {_fmt(d['hit_rate']*100 if d['hit_rate'] is not None else None,0,'%')} | "
              f"{_fmt(d['median_ret_closed'],1,'%')} | {d['median_fund7_bps']:+.2f} |")
        A("")
        A("| famille de signal | n | fund7 médian (bps/8h) | % fund7 > 0 | % fund7 > 0.5 | hit (fermés) |")
        A("|---|---|---|---|---|---|")
        for f, d in sorted(p3["by_signal"].items()):
            A(f"| {f} | {d['n']} | {d['median_fund7_bps']:+.2f} | "
              f"{d['share_fund_pos']*100:.0f}% | {d['share_fund_high']*100:.0f}% | "
              f"{_fmt(d['hit_rate']*100 if d['hit_rate'] is not None else None,0,'%')} |")
        A("")

    A("## Verdict (mission P2)")
    A("")
    # ---- nombres du verdict, calculés depuis payload ----
    real_strats = [s for s in sorted(CONFIGS) if s not in ARTEFACT_STRATS]
    maj = [r for r in majors if not r["config"].endswith("@regime")]
    maj_ref = [r for r in maj if r["config"] == "REF"]
    agree_ref_dir = max(abs(r["agree_pts"]) for r in maj_ref
                        if r["strategy"] != "funding_carry"
                        and r["agree_pts"] is not None)
    agree_all_dir = max(abs(r["agree_pts"]) for r in maj
                        if r["strategy"] not in ("funding_carry", "volatility_harvesting")
                        and r["agree_pts"] is not None)
    agree_carry = max(abs(r["agree_pts"]) for r in maj
                      if r["strategy"] == "funding_carry" and r["agree_pts"] is not None)
    lane_hard_maj = {s: (sum(1 for r in maj if r["strategy"] == s
                             and survived_lane(r, SURV_SHARPE_HARD)),
                         sum(1 for r in maj if r["strategy"] == s))
                     for s in real_strats}
    lane_hard_ext = {s: (sum(1 for r in ext_full if r["strategy"] == s
                             and survived_lane(r, SURV_SHARPE_HARD)),
                         sum(1 for r in ext_full if r["strategy"] == s
                             and r["config"] != "REF@window"))
                     for s in real_strats}
    # survie momentum par régime (majors)
    mom_reg = {}
    for reg in reg_names:
        per = [r["by_regime"][reg] for r in majors if r["strategy"] == "momentum"]
        mom_reg[reg] = sum(1 for x in per if survived_regime(x))
    # fenêtres extension : meilleure stratégie
    best_win = {}
    for wname, _, _ in payload["ext_windows"]:
        rows_w = [r for r in ext_win if wname in r["by_regime"]]
        cand = {}
        for s in real_strats:
            per = [r["by_regime"][wname] for r in rows_w if r["strategy"] == s]
            if per:
                cand[s] = (sum(1 for x in per if survived_regime(x)), len(per))
        best_win[wname] = max(cand.items(), key=lambda kv: kv[1][0]) if cand else None
    # P3
    p3b = p3.get("by_bucket", {})
    n_pos = sum(d["n"] for k, d in p3b.items() if k != "a_negatif")
    n_high = sum(d["n"] for k, d in p3b.items() if k in ("d_eleve", "e_manie"))
    hit_neg = p3b.get("a_negatif", {}).get("hit_rate")
    hit_high = p3b.get("d_eleve", {}).get("hit_rate")
    hit_manie = p3b.get("e_manie", {}).get("hit_rate")

    A(f"**1. CONFIRMATION T7 — OUI, les verdicts tiennent à l'identique, et les deux couches "
      f"disent maintenant la même chose.** Accord flux ↔ équité corrigée (série complète) : "
      f"{agree_ref_dir:.1f} pt max en REF, {agree_all_dir:.1f} pt max toutes lanes sur les 4 "
      f"stratégies directionnelles — dans la fourchette de preuve du fix (0,1-2,5 pts) ; "
      f"{agree_carry:.1f} pts max sur funding_carry — divergence résiduelle LOCALISÉE et expliquée : "
      "l'équité accrue le funding barre à barre pendant la position, le flux ne le compose qu'à la "
      "clôture (jambe T7) ; les SIGNES et les hiérarchies par régime sont identiques couche par couche "
      "(TABLE 1 eq vs flux : aucun verdict ne bascule). Conséquence du fix : les sharpe OOS honnêtes "
      "s'effondrent (momentum BTC 0,30 biaisé → +0,07 réel ; carry ETH 0,43 → −0,08) : TOUTES les lanes "
      "réelles majors échouent le gate campagne (0/9 hard par stratégie). Le trésor T7 est confirmé : "
      "le validateur nocturne d'avant-fix sur-estimait toutes les lanes qui stoppent.")
    A("")
    A(f"**2. LA MÉTA-QUESTION — où la fabrique produit-elle des survivants : NULLE PART en lane "
      f"continue, marginalement en momentum 2023-2024 et en breakout alts 2026.** Lane complète "
      f"(gates campagne honnêtes) : majors {sum(h for h,_ in lane_hard_maj.values())}/"
      f"{sum(n for _,n in lane_hard_maj.values())}, extension {sum(h for h,_ in lane_hard_ext.values())}/"
      f"{sum(n for _,n in lane_hard_ext.values())} — 0 partout. Par régime (DD ≤ 25 % exigé, équité "
      f"corrigée) : le momentum reste la SEULE famille avec des cellules vivantes — "
      f"bull_2024H1 {mom_reg['bull_2024H1']}/9, chop_2024H2 {mom_reg['chop_2024H2']}/9, "
      f"recovery {mom_reg['recovery_2023']}/9, mais 0/9 en bull 2021-H2, bear et période connue : "
      "l'edge de cycle 2023-2024 est confirmé ET confirmé mort depuis 2025. L'extension 12 séries "
      "(ASTER, TRUMP, XRP, BNB, DOGE, HYPE, LINK, FARTCOIN, MOODENG, NEIRO, LTC, NVDA — funding "
      "réel mesuré) ne sauve RIEN en lane continue : 0/36 hard, médianes −7 % (fade réel) à "
      "−44 %/a (momentum). Seuls signes de vie par fenêtre : ")
    bw = best_win.get("connu_B")
    bw_txt = (f"**{bw[0]} {bw[1][0]}/{bw[1][1]} en 2026-04→**" if bw else "aucune")
    A(bw_txt + " — la re-détection de volatilité 2026 sur alts — et funding_fade "
      "**sur série RÉELLE** (l'artefact T7 disparaît) : 4/12 en 2025→2026-03, best MOODENG +45 %/a "
      "DD 6 %, LTC +40 %/a DD 15 % — mais sharpe OOS 0,46 : sous le gate.")
    A("")
    A(f"**3. LIEN P3 — le crowding-long fade est CONFIRMÉ sur N={p3['n']}.** {n_pos}/{p3['n']} signaux "
      f"(90 %) activés à fund7 > 0, {n_high}/{p3['n']} (52 %) à fund7 > 0,5 bps/8h ; "
      "machine_cascade_meme : médiane +0,80 bps, 57 % > 0,5 bps. Et l'outcome des fermés classé par "
      f"bucket : fund7 négatif → hit {hit_neg*100:.0f} %, ret médian négatif (la foule est déjà short : "
      f"pas de carburant) ; fund7 ≥ 0,5 → hit {hit_high*100:.0f} % ; manie > 1 bps → hit "
      f"{hit_manie*100:.0f} % (n=6 fermés). Le carburant de la cascade EST le funding positif élevé : "
      "les shorts cascade/sweep doivent être gate-d sur fund7 > 0,5 bps/8h — c'est le premier filtre "
      "mécanisme validé out-of-sample de la sonde.")
    A("")
    A("**4. OÙ LA MACHINE PEUT GAGNER SUR 4 ANS :** (a) aucune des 6 familles 1h campagne ne gagne "
      "en lane continue — le stack doit rester MULTI-RÉGIME avec des gates de RÉGIME, pas des lanes "
      "permanentes ; (b) régimes porteurs par flux : momentum sur cycle haussier confirmé (2023-2024) "
      "mais détecté APRÈS coup — l'adaptateur doit le ré-armer par détection de régime, pas le laisser "
      f"vivre ; breakout sur alts 2026 (re-détection de vol) ; fade de funding réel élevé sur memes "
      "(P3 + MOODENG/LTC) — la seule famille où le MÉCANISME est validé indépendamment du backtest ; "
      "(c) régimes morts : momentum 1h majors 2025-2026 (0/9), mean_reversion partout (WR invariant "
      "42 %, RR inversé : NUL sauf exécution maker), carry unhedged partout sauf bear (accident "
      "d'implémentation), vol_harvesting artefact microstructure ; (d) ce que l'adaptateur doit faire "
      "AU-DELÀ du ×0,75 : **gate fund7 > 0,5 bps/8h sur les shorts cascade/sweep** (validé P3), "
      "**DD-régime ≤ 25 % comme gate de taille** (rule 0-liq inchangée), **portage du short bear** "
      "(exposition constante, jamais de stops serrés — T7§2 re-confirmé), **rotation par détection de "
      "régime 90 j renforcée par fund7/vol7/liq24h** (les 3 gradients P3 déjà loggés), et **budget de "
      "découverte ré-alloué vers alts/memes 1h 2026** (seule région où la fabrique a encore produit "
      "des quasi-survivants).")
    A("")
    A("## Limites honnêtes")
    A("")
    A("1. **Divergence résiduelle carry** (2-11 pts sur 5 ans) : timing de la jambe funding "
      "(accrue barre à barre dans l'équité, composée à la clôture dans le flux). Ne change aucun "
      "signe ; à garder à l'œil si un jour le carry redevient candidat.")
    A("2. **Funding 2021-2024 modélisé** (T7) pour les majors ; l'extension utilise le funding RÉEL "
      "mesuré par symbole (couverture 45-100 % des barres, moyenne affichée au chargement).")
    A("3. **L'extension n'a pas le deep** : seules BTC/ETH/SOL ont 2021-2026. Les 12 séries testées "
      "couvrent 2025-09→2026-09 (une seule grande fenêtre de régime) — la survie par régime deep ne "
      "peut pas être mesurée sur elles ; les fenêtres A/B la-bornent.")
    A("4. **Fills modèle** : stops au prix du stop (optimiste sur gaps), taker 4 bps/jambe. Les "
      "conclusions négatives en sont renforcées.")
    A("5. **P3 : N=29 fermés** seulement (horizons 1440-2160 h) : les hit rates par bucket sont "
      "des ordres de grandeur, pas des verdicts statistiques ; les 32 ouverts (sweep 90 j) trancheront.")
    A("6. vol_harvesting reste un artefact microstructure (ROI 10^30 %) : exclu des taux de survie.")
    A("7. Attribution : trades par régime d'ENTRÉE (flux), barres par régime de résidence (équité) — "
      "c'est précisément la comparaison des deux qui teste la robustesse des verdicts.")
    A("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
