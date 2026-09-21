"""Strategie de breakout de canal de Donchian (long/short, perpetuals).

Le canal est calcule sur les `donchian_len` barres PRECEDENTES, la barre
courante EXCLUE :

    max_high = max(high[i-donchian_len .. i-1])
    min_low  = min(low [i-donchian_len .. i-1])
    rng      = max_high - min_low

Signal brut sur la barre i (information disponible a sa cloture) :

    LONG  si  ref_high[i] > max_high + breakout_mult * rng
    SHORT si  ref_low [i] < min_low  - breakout_mult * rng

`ref_high`/`ref_low` valent close[i] si `use_close` est vrai, sinon high[i] /
low[i]. Le signal n'est retenu que s'il se maintient `confirmation_bars`
barres consecutives dans le meme sens.

REGLE ABSOLUE (docs/08-contributing.md, baselines.py) :
    signal calcule sur la barre i  ->  EXECUTION A L'OPEN DE i+1.
Le canal a l'indice i n'utilise que les barres 0..i-1 et la barre i elle-meme,
jamais i+1 : muter la derniere barre ne peut modifier aucune entree anterieure.
C'est le test anti-look-ahead.

Sorties : stop de protection et take-profit en points de base par rapport au
prix d'entree, ou signal inverse (execute a l'open suivant).

Les 4 postes de cout sont remplis explicitement (jamais None -> zero implicite) :
  - fees        : taker USDT aller-retour (8 bps) via round_trip_fees_usd
  - slippage    : consommation d'un carnet synthetique de 50K notional
  - funding     : cache reel Aster ; si indisponible, 0.0 EXPLICITE + flag au blob
  - liquidation : check_liquidation, gere un levier incompatible avec la maintenance

Stdlib pure. Imports ABSOLUS volontaires : le module reste chargeable seul
(via importlib) sans declencher le __init__ du sous-package.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from backend.services.backtest_v2.baselines import Bar
from backend.services.backtest_v2.costs import (
    CostBreakdown,
    CostDataUnavailable,
    check_liquidation,
    funding_cost_usd,
    load_funding_rate,
    round_trip_fees_usd,
    slippage_usd,
)
from backend.services.backtest_v2.engine import StrategyEval

# --------------------------------------------------------------- parametres

# Espace complet de reference (documente). Le grid effectif ci-dessous en est un
# sous-echantillon representatif garde SOUS 300 combinaisons (cf. tests).
FULL_PARAM_RANGES: dict[str, Sequence[Any]] = {
    "donchian_len": [20, 50, 100],
    "breakout_mult": [0.0, 0.5, 1.0],
    "confirmation_bars": [1, 2],
    "use_close": [True, False],
    "allow_short": [True, False],
    "stop_bps": [200, 500],
    "take_bps": [400, 800],
    "max_leverage": [2, 3],
}

# Grid effectivement explore : 2*2*2*2*2*2*2*2 = 256 combinaisons (< 300).
# Les 8 dimensions sont conservees ; seules donchian_len et breakout_mult sont
# ramenees a leurs bornes pour tenir le budget de 300.
PARAM_SPACE: dict[str, Sequence[Any]] = {
    "donchian_len": [20, 100],
    "breakout_mult": [0.0, 1.0],
    "confirmation_bars": [1, 2],
    "use_close": [True, False],
    "allow_short": [True, False],
    "stop_bps": [200, 500],
    "take_bps": [400, 800],
    "max_leverage": [2, 3],
}

# Notional par trade et profondeur du carnet synthetique (50K).
BOOK_NOTIONAL_USD = 50_000.0
# Taux de maintenance Aster typique pour le check de liquidation.
MAINTENANCE_MARGIN_RATE = 0.005
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_EXECUTION_MODEL = "taker_market"
FEE_FRACTION_ROUND_TRIP = 8.0 / 10_000.0  # 8 bps aller-retour (taker USDT)


# ----------------------------------------------------------------- signaux


def donchian_channel(
    bars: Sequence[Bar], index: int, length: int
) -> tuple[float, float] | None:
    """Canal [min_low, max_high] sur les `length` barres PRECEDANT `index`.

    La barre `index` est volontairement EXCLUE : l'inclure reviendrait a
    comparer un extreme a lui-meme, ce qui rend tout breakout impossible.
    Renvoie None tant que l'historique est insuffisant (aucune extrapolation).
    """
    if length <= 0:
        raise ValueError(f"donchian_len invalide: {length}")
    start = index - length
    if start < 0:
        return None
    window = bars[start:index]
    if not window:
        return None
    return (min(b.low for b in window), max(b.high for b in window))


def compute_signals(bars: Sequence[Bar], params: dict) -> list[int]:
    """Signal desire par barre : +1 long, -1 short, 0 plat.

    signal[i] n'utilise QUE les barres 0..i. Il ne sera execute qu'a l'open de
    i+1 (cf. `simulate`).
    """
    length = int(params["donchian_len"])
    mult = float(params["breakout_mult"])
    confirm = int(params["confirmation_bars"])
    use_close = bool(params["use_close"])
    allow_short = bool(params["allow_short"])
    if length <= 0:
        raise ValueError(f"donchian_len invalide: {length}")
    if mult < 0:
        raise ValueError(f"breakout_mult invalide: {mult}")
    if confirm < 1:
        raise ValueError(f"confirmation_bars invalide: {confirm}")

    raw: list[int] = []
    for i, bar in enumerate(bars):
        chan = donchian_channel(bars, i, length)
        if chan is None:
            raw.append(0)
            continue
        min_low, max_high = chan
        rng = max_high - min_low
        up = max_high + mult * rng
        dn = min_low - mult * rng
        ref_high = bar.close if use_close else bar.high
        ref_low = bar.close if use_close else bar.low
        if ref_high > up:
            raw.append(1)
        elif ref_low < dn:
            raw.append(-1)
        else:
            raw.append(0)

    # Confirmation : le signal doit se maintenir `confirm` barres consecutives.
    signals: list[int] = []
    for i in range(len(raw)):
        s = raw[i]
        if s != 0 and confirm > 1:
            if i + 1 < confirm or any(raw[j] != s for j in range(i - confirm + 1, i)):
                s = 0
        if s < 0 and not allow_short:
            s = 0
        signals.append(s)
    return signals


# ------------------------------------------------------------------- trades


@dataclass
class Trade:
    entry_index: int
    exit_index: int
    side: int  # +1 long, -1 short
    entry_price: float
    exit_price: float
    reason: str  # 'stop' | 'take' | 'reverse' | 'eod'

    @property
    def gross_return(self) -> float:
        return self.side * (self.exit_price / self.entry_price - 1.0)

    @property
    def net_return(self) -> float:
        return self.gross_return - FEE_FRACTION_ROUND_TRIP

    @property
    def holding_bars(self) -> int:
        return max(1, self.exit_index - self.entry_index)


def simulate(bars: Sequence[Bar], params: dict) -> tuple[list[Trade], list[float]]:
    """Simule la strategie. Renvoie (trades clotures, rendement par barre).

    Execution : le signal de la barre i-1 est applique a l'OPEN de la barre i.
    Stop/take sont verifies sur le high/low de chaque barre pendant la detention
    (y compris la barre d'entree). Rendement par barre = sign_position *
    (close[i]/close[i-1] - 1), 0.0 hors position.
    """
    n = len(bars)
    signals = compute_signals(bars, params)
    stop_frac = float(params["stop_bps"]) / 10_000.0
    take_frac = float(params["take_bps"]) / 10_000.0

    trades: list[Trade] = []
    bar_ret = [0.0] * n

    pos = 0
    entry_price = 0.0
    entry_index = 0

    def close_trade(idx: int, price: float, reason: str) -> None:
        nonlocal pos
        trades.append(
            Trade(
                entry_index=entry_index,
                exit_index=idx,
                side=pos,
                entry_price=entry_price,
                exit_price=price,
                reason=reason,
            )
        )
        pos = 0

    for i in range(n):
        bar = bars[i]

        # A. Execution a l'open : le signal de la barre i-1 s'applique ici.
        if i >= 1:
            desired = signals[i - 1]
            if desired != 0 and desired != pos:
                if pos != 0:
                    close_trade(i, bar.open, "reverse")
                pos = desired
                entry_price = bar.open
                entry_index = i

        # B. Stop / take pendant la barre (high/low), y compris barre d'entree.
        if pos != 0:
            if pos == 1:
                stop_price = entry_price * (1.0 - stop_frac)
                take_price = entry_price * (1.0 + take_frac)
                if bar.low <= stop_price:
                    close_trade(i, stop_price, "stop")
                elif bar.high >= take_price:
                    close_trade(i, take_price, "take")
            else:
                stop_price = entry_price * (1.0 + stop_frac)
                take_price = entry_price * (1.0 - take_frac)
                if bar.high >= stop_price:
                    close_trade(i, stop_price, "stop")
                elif bar.low <= take_price:
                    close_trade(i, take_price, "take")

        # C. Rendement par barre selon la position active pendant la barre.
        if i >= 1 and pos != 0:
            bar_ret[i] = pos * (bar.close / bars[i - 1].close - 1.0)

    # Sortie forcee de fin de serie : une position ouverte doit etre valorisee.
    if pos != 0:
        close_trade(n - 1, bars[-1].close, "eod")

    return trades, bar_ret


# -------------------------------------------------------------------- couts


def _bar_hours(bars: Sequence[Bar]) -> float:
    if len(bars) >= 2:
        dt_ms = bars[1].ts - bars[0].ts
        if dt_ms > 0:
            return dt_ms / 3_600_000.0
    return 1.0


def _synthetic_book(reference_price: float, notional_usd: float) -> list[tuple[float, float]]:
    """Carnet synthetique de ~2x le notional demande, en 8 niveaux a +1 bp/niveau."""
    order_qty = notional_usd / reference_price
    per_level = order_qty / 4.0
    return [
        (reference_price * (1.0 + 0.0001 * k), per_level)
        for k in range(8)
    ]


def _build_costs(
    trades: Sequence[Trade],
    bars: Sequence[Bar],
    params: dict,
    symbol: str,
) -> tuple[CostBreakdown, dict[str, Any]]:
    """Agrege les 4 postes sur l'ensemble des trades. Jamais de None implicite."""
    cb = CostBreakdown()
    flags: dict[str, Any] = {"funding_available": False, "funding_reason": None}

    fees = 0.0
    slip = 0.0
    funding = 0.0
    all_safe = True
    hours_per_bar = _bar_hours(bars)

    # Funding : cache reel prioritaire ; si indisponible -> 0.0 EXPLICITE + flag.
    rate = None
    try:
        rate = load_funding_rate(symbol)
        flags["funding_available"] = True
    except CostDataUnavailable as exc:
        flags["funding_available"] = False
        flags["funding_reason"] = str(exc)
        funding = 0.0  # explicite, jamais None

    for t in trades:
        fees += round_trip_fees_usd(BOOK_NOTIONAL_USD, symbol, DEFAULT_EXECUTION_MODEL)

        book = _synthetic_book(t.entry_price, BOOK_NOTIONAL_USD)
        slip += slippage_usd(BOOK_NOTIONAL_USD, book, t.entry_price)

        side = "long" if t.side == 1 else "short"
        if rate is not None:
            holding_hours = t.holding_bars * hours_per_bar
            funding += funding_cost_usd(BOOK_NOTIONAL_USD, holding_hours, side, rate)

        # liquidation : le pire mouvement adverse est borne par le stop.
        chk = check_liquidation(
            entry_price=t.entry_price,
            side=side,
            leverage=float(params["max_leverage"]),
            maintenance_margin_rate=MAINTENANCE_MARGIN_RATE,
            worst_adverse_pct=float(params["stop_bps"]) / 100.0,
        )
        all_safe = all_safe and chk.safe

    cb.fees_usd = fees
    cb.slippage_usd = slip
    cb.funding_usd = funding
    cb.liquidation_checked = True
    cb.liquidation_safe = all_safe if trades else True
    if not flags["funding_available"]:
        cb.warnings.append("funding indisponible: 0.0 explicite (voir blob)")

    return cb, flags


# ------------------------------------------------------------------ contrat


def evaluate(params: dict, bars: Sequence[Bar]) -> StrategyEval:
    """Contrat moteur : (params, bars) -> StrategyEval. Deterministe."""
    symbol = str(params.get("symbol", DEFAULT_SYMBOL))
    trades, bar_ret = simulate(bars, params)

    trade_returns = [t.net_return for t in trades]
    if trades:
        avg_hold = round(sum(t.holding_bars for t in trades) / len(trades))
    else:
        avg_hold = 0

    costs, flags = _build_costs(trades, bars, params, symbol)

    equity = [1.0]
    for r in bar_ret:
        equity.append(equity[-1] * (1.0 + r))

    blob: dict[str, Any] = {
        "strategy": "breakout",
        "n_trades": len(trades),
        "entries": [(t.entry_index, t.side) for t in trades],
        "exit_reasons": [t.reason for t in trades],
        "funding_available": flags["funding_available"],
        "funding_reason": flags["funding_reason"],
        "costs_total_usd": costs.total_usd,
    }

    return StrategyEval(
        bar_returns_per_bar=bar_ret,
        closed_trades=len(trades),
        trade_returns=trade_returns,
        avg_holding_bars=avg_hold,
        costs=costs,
        microstructure_validated=False,
        equity_curve=equity,
        blob=blob,
    )
