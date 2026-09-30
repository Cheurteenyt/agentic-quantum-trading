"""Strategie de momentum multi-periode (EMA cross + filtre de regime).

Momentum long/short sur perpetuals BTC/ETH. Le signal combine :

  1. un croisement de moyennes mobiles EXPONENTIELLES (fast vs slow) ;
  2. un filtre de REGIME (tendance longue) : on ne prend une position que si le
     sens du cross est aligne avec le sens de `close vs regime_ema`.

    position = sign(fast_ema - slow_ema)   SI   aligne avec sign(close - regime_ema)
             = plat                         sinon

REGLE ABSOLUE (docs/08-contributing.md, baselines.py) :
    signal calcule sur la barre i  ->  EXECUTION A L'OPEN DE i+1.
Les EMA a l'indice i n'utilisent que les closes 0..i (recurrence causale), donc
muter la derniere barre ne peut modifier aucune entree anterieure. C'est le
test anti-look-ahead.

Sorties : stop de protection et take-profit en points de base par rapport au
prix d'entree, ou croisement inverse du signal (execute a l'open suivant).

Les 4 postes de cout sont remplis explicitement (jamais None -> zero implicite) :
  - fees      : taker USDT aller-retour (8 bps) via round_trip_fees_usd
  - slippage  : consommation d'un carnet synthetique de 50K notional
  - funding   : cache reel Aster ; si indisponible, 0.0 EXPLICITE + flag au blob
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
    "fast_ema": [8, 12, 20],
    "slow_ema": [40, 60, 100],
    "regime_ema": [120, 200],
    "allow_short": [True, False],
    "stop_bps": [200, 500, 1000],
    "take_bps": [400, 1000],
    "max_leverage": [2, 3, 5],
}

# Grid effectivement explore : 2*2*2*2*3*2*3 = 288 combinaisons (< 300).
# On garde les 7 dimensions et les plages completes de stop/take/levier ;
# seules fast_ema et slow_ema sont ramenees a leurs bornes pour tenir le budget.
PARAM_SPACE: dict[str, Sequence[Any]] = {
    "fast_ema": [8, 20],
    "slow_ema": [40, 100],
    "regime_ema": [120, 200],
    "allow_short": [True, False],
    "stop_bps": [200, 500, 1000],
    "take_bps": [400, 1000],
    "max_leverage": [2, 3, 5],
}

# Notional par trade et profondeur du carnet synthetique (50K).
BOOK_NOTIONAL_USD = 50_000.0
# Taux de maintenance Aster typique pour le check de liquidation.
MAINTENANCE_MARGIN_RATE = 0.005
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_EXECUTION_MODEL = "taker_market"
FEE_FRACTION_ROUND_TRIP = 8.0 / 10_000.0  # 8 bps aller-retour (taker USDT)
FEE_FRACTION_PER_FILL = FEE_FRACTION_ROUND_TRIP / 2.0  # 4 bps taker PAR fill


# ----------------------------------------------------------------- indicateurs


def ema_series(closes: Sequence[float], period: int) -> list[float]:
    """EMA causale : ema[i] ne depend que de closes[0..i].

    Recurrence classique alpha = 2/(period+1), amorcee sur le premier close.
    Aucune valeur posterieure n'est lue -> zero look-ahead par construction.
    """
    if period <= 0:
        raise ValueError(f"periode EMA invalide: {period}")
    out: list[float] = []
    alpha = 2.0 / (period + 1.0)
    prev = 0.0
    for i, c in enumerate(closes):
        if i == 0:
            prev = c
        else:
            prev = alpha * c + (1.0 - alpha) * prev
        out.append(prev)
    return out


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def compute_signals(bars: Sequence[Bar], params: dict) -> list[int]:
    """Signal desire par barre : +1 long, -1 short, 0 plat.

    signal[i] utilise UNIQUEMENT l'information disponible a la cloture de la
    barre i (EMA causales, close[i]). Il ne sera execute qu'a l'open de i+1.
    """
    fast_p = int(params["fast_ema"])
    slow_p = int(params["slow_ema"])
    regime_p = int(params["regime_ema"])
    allow_short = bool(params["allow_short"])
    if fast_p >= slow_p:
        raise ValueError(f"fast_ema ({fast_p}) doit etre < slow_ema ({slow_p})")

    closes = [b.close for b in bars]
    fast = ema_series(closes, fast_p)
    slow = ema_series(closes, slow_p)
    regime = ema_series(closes, regime_p)

    # Avant d'avoir `regime_p` barres, l'EMA de regime n'est pas fiable : on
    # reste plat plutot que de trader sur un indicateur non amorci.
    warmup = max(slow_p, regime_p)

    signals: list[int] = []
    for i in range(len(bars)):
        if i + 1 < warmup:
            signals.append(0)
            continue
        cross = _sign(fast[i] - slow[i])
        trend = _sign(closes[i] - regime[i])
        # Filtre de regime : ne trader QUE dans le sens de la tendance longue.
        if cross != 0 and cross == trend:
            desired = cross
        else:
            desired = 0
        if desired < 0 and not allow_short:
            desired = 0
        signals.append(desired)
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
    stop_bps = float(params["stop_bps"])
    take_bps = float(params["take_bps"])
    stop_frac = stop_bps / 10_000.0
    take_frac = take_bps / 10_000.0

    trades: list[Trade] = []
    bar_ret = [0.0] * n

    pos = 0  # +1 / -1 / 0
    entry_price = 0.0
    entry_index = 0
    last_mark = 0.0  # dernier prix de valorisation de la position ouverte

    def open_trade(i: int, price: float, side: int) -> None:
        nonlocal pos, entry_price, entry_index, last_mark
        pos = side
        entry_price = price
        entry_index = i
        last_mark = price
        # Frais d'entree bookes SUR la barre d'entree (taker par fill) :
        # sans eux l'equite oubliait la moitie des frais (bug T7).
        bar_ret[i] += -FEE_FRACTION_PER_FILL

    def close_trade(idx: int, price: float, reason: str) -> None:
        nonlocal pos, last_mark
        # Jambe de sortie : du dernier mark au prix de sortie REEL (stop, take,
        # open de retournement, close d'eod). AVANT le fix, la barre de stop
        # restait a 0.0 : la perte stoppee n'entrait JAMAIS dans l'equite
        # (bug T7, reports/aster_deep_regimes.md).
        bar_ret[idx] += pos * (price / last_mark - 1.0) - FEE_FRACTION_PER_FILL
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
            if desired != pos:
                if pos != 0:
                    close_trade(i, bar.open, "reverse")
                if desired != 0:
                    open_trade(i, bar.open, desired)

        # B. Stop / take pendant la barre (high/low), y compris barre d'entree.
        if pos != 0:
            if pos == 1:
                stop_price = entry_price * (1.0 - stop_frac)
                take_price = entry_price * (1.0 + take_frac)
                if bar.low <= stop_price:
                    close_trade(i, stop_price, "stop")
                elif bar.high >= take_price:
                    close_trade(i, take_price, "take")
            else:  # short
                stop_price = entry_price * (1.0 + stop_frac)
                take_price = entry_price * (1.0 - take_frac)
                if bar.high >= stop_price:
                    close_trade(i, stop_price, "stop")
                elif bar.low <= take_price:
                    close_trade(i, take_price, "take")

        # C. Mark-to-market : la position ouverte est valorisee du dernier mark
        #    (open d'entree ou close precedent) au close de la barre. Pour une
        #    barre portee sans evenement, c'est identique au close-to-close
        #    d'avant ; la difference porte sur l'entree (base = open reel) et
        #    la barre de sortie (bookee au prix de sortie, pas 0).
        if pos != 0:
            bar_ret[i] += pos * (bar.close / last_mark - 1.0)
            last_mark = bar.close

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
    """Carnet synthetique de ~2x le notional demande, en 8 niveaux a +1 bp/niveau.

    Le premier niveau est au prix de reference (impact nul), les suivants
    degradent d'1 bp : un ordre de `notional_usd` traverse plusieurs niveaux et
    subit donc un slippage strictement positif, mesure par costs.slippage_usd.
    """
    order_qty = notional_usd / reference_price
    per_level = order_qty / 4.0  # 8 niveaux -> ~2x le notional absorbable
    levels: list[tuple[float, float]] = []
    for k in range(8):
        price = reference_price * (1.0 + 0.0001 * k)
        levels.append((price, per_level))
    return levels


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
        # fees taker USDT aller-retour (8 bps) sur le notional du carnet.
        fees += round_trip_fees_usd(BOOK_NOTIONAL_USD, symbol, DEFAULT_EXECUTION_MODEL)

        # slippage : consommation d'un carnet synthetique de 50K notional.
        book = _synthetic_book(t.entry_price, BOOK_NOTIONAL_USD)
        slip += slippage_usd(BOOK_NOTIONAL_USD, book, t.entry_price)

        # funding sur le notionnel, prorata de la duree de detention.
        if rate is not None:
            side = "long" if t.side == 1 else "short"
            holding_hours = t.holding_bars * hours_per_bar
            funding += funding_cost_usd(BOOK_NOTIONAL_USD, holding_hours, side, rate)

        # liquidation : le pire mouvement adverse est borne par le stop.
        side = "long" if t.side == 1 else "short"
        worst_adverse_pct = float(params["stop_bps"]) / 100.0
        chk = check_liquidation(
            entry_price=t.entry_price,
            side=side,
            leverage=float(params["max_leverage"]),
            maintenance_margin_rate=MAINTENANCE_MARGIN_RATE,
            worst_adverse_pct=worst_adverse_pct,
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

    # Courbe d'equity capitalisee a partir des rendements par barre.
    equity = [1.0]
    for r in bar_ret:
        equity.append(equity[-1] * (1.0 + r))

    blob: dict[str, Any] = {
        "strategy": "momentum",
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
