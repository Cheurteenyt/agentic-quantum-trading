"""Strategie de retour a la moyenne (z-score sur moyenne mobile simple).

Mean-reversion long/short sur perpetuals. Le signal est un z-score calcule sur
une fenetre glissante de `lookback` closes :

    z[i] = (close[i] - mean(close[i-lookback+1..i])) / dispersion

  - `use_std=True`  : dispersion = ecart-type (population) de la fenetre ;
  - `use_std=False` : dispersion = ecart absolu moyen (MAD), plus robuste aux
    pics de volatilite mais moins sensible.

    z < -entry_z  ->  LONG   (prix anormalement bas, on parie sur le retour)
    z > +entry_z  ->  SHORT  (si allow_short)
    |z| < exit_z  ->  PLAT   (le retour a la moyenne a eu lieu)

Entre entry_z et exit_z la position en cours est CONSERVEE (bande d'hysteresis) :
sans cela la strategie ferait des aller-retours a chaque oscillation du z.

REGLE ABSOLUE (docs/08-contributing.md, baselines.py) :
    signal calcule sur la barre i  ->  EXECUTION A L'OPEN DE i+1.
La fenetre du z-score a l'indice i n'utilise que les closes i-lookback+1..i :
muter la derniere barre ne peut modifier aucune entree anterieure. C'est le
test anti-look-ahead.

Sorties : stop de protection et take-profit en points de base par rapport au
prix d'entree (verifies sur le high/low), ou disparition du signal (executee a
l'open suivant).

Les 4 postes de cout sont remplis explicitement (jamais None -> zero implicite) :
  - fees        : taker USDT aller-retour (8 bps) via round_trip_fees_usd
  - slippage    : consommation d'un carnet synthetique de 50K notional
  - funding     : cache reel Aster ; si indisponible, 0.0 EXPLICITE + flag au blob
  - liquidation : check_liquidation, gere un levier incompatible avec la maintenance

Stdlib pure. Imports ABSOLUS volontaires : le module reste chargeable seul
(via importlib) sans declencher le __init__ du sous-package.
"""
from __future__ import annotations

import math
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
    "lookback": [20, 50, 100],
    "entry_z": [1.5, 2.0, 2.5],
    "exit_z": [0.3, 0.5],
    "use_std": [True, False],
    "allow_short": [True, False],
    "stop_bps": [150, 300],
    "take_bps": [100, 200],
    "max_leverage": [2, 3],
}

# Grid effectivement explore : 2*2*2*2*2*2*2*2 = 256 combinaisons (< 300).
# Les 8 dimensions sont conservees ; seules lookback et entry_z sont ramenees a
# leurs bornes pour tenir le budget (1152 combinaisons sinon).
PARAM_SPACE: dict[str, Sequence[Any]] = {
    "lookback": [20, 100],
    "entry_z": [1.5, 2.5],
    "exit_z": [0.3, 0.5],
    "use_std": [True, False],
    "allow_short": [True, False],
    "stop_bps": [150, 300],
    "take_bps": [100, 200],
    "max_leverage": [2, 3],
}

# Notional par trade et profondeur du carnet synthetique (50K).
BOOK_NOTIONAL_USD = 50_000.0
# Taux de maintenance Aster typique pour le check de liquidation.
MAINTENANCE_MARGIN_RATE = 0.005
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_EXECUTION_MODEL = "taker_market"
FEE_FRACTION_ROUND_TRIP = 8.0 / 10_000.0  # 8 bps aller-retour (taker USDT)
FEE_FRACTION_PER_FILL = FEE_FRACTION_ROUND_TRIP / 2.0  # 4 bps taker PAR fill

# En dessous de ce seuil la dispersion est consideree nulle : un z-score
# calcule sur une serie plate est un artefact numerique, pas un signal.
MIN_DISPERSION = 1e-12


# ----------------------------------------------------------------- indicateurs


def zscore_series(
    closes: Sequence[float], lookback: int, use_std: bool = True
) -> list[float | None]:
    """z-score causal : z[i] n'utilise que closes[i-lookback+1..i].

    Renvoie None (et non 0.0 : `None` n'est pas zero) tant que la fenetre n'est
    pas complete, ou lorsque la dispersion est nulle — dans ces deux cas le
    z-score n'existe pas, il ne vaut pas zero.
    """
    if lookback <= 1:
        raise ValueError(f"lookback invalide: {lookback}")

    out: list[float | None] = []
    for i in range(len(closes)):
        if i + 1 < lookback:
            out.append(None)
            continue
        window = closes[i - lookback + 1 : i + 1]
        mean = sum(window) / lookback
        if use_std:
            var = sum((x - mean) ** 2 for x in window) / lookback
            disp = math.sqrt(var)
        else:
            disp = sum(abs(x - mean) for x in window) / lookback
        if disp <= MIN_DISPERSION:
            out.append(None)
            continue
        out.append((closes[i] - mean) / disp)
    return out


def compute_signals(bars: Sequence[Bar], params: dict) -> list[int]:
    """Signal desire par barre : +1 long, -1 short, 0 plat.

    signal[i] utilise UNIQUEMENT l'information disponible a la cloture de la
    barre i (fenetre de z-score fermee en i). Il ne sera execute qu'a l'open de
    i+1. La bande [exit_z, entry_z] conserve la position precedente.
    """
    lookback = int(params["lookback"])
    entry_z = float(params["entry_z"])
    exit_z = float(params["exit_z"])
    use_std = bool(params["use_std"])
    allow_short = bool(params["allow_short"])
    if entry_z <= 0:
        raise ValueError(f"entry_z doit etre > 0 (recu {entry_z})")
    if exit_z < 0:
        raise ValueError(f"exit_z doit etre >= 0 (recu {exit_z})")
    if exit_z >= entry_z:
        raise ValueError(
            f"exit_z ({exit_z}) doit etre < entry_z ({entry_z}) : sans bande "
            "d'hysteresis la strategie oscille a chaque barre"
        )

    closes = [b.close for b in bars]
    zs = zscore_series(closes, lookback, use_std)

    signals: list[int] = []
    desired = 0
    for z in zs:
        if z is None:
            desired = 0
        elif z < -entry_z:
            desired = 1
        elif z > entry_z:
            desired = -1
        elif abs(z) < exit_z:
            desired = 0
        # sinon : zone intermediaire -> on conserve `desired` tel quel.

        out = desired
        if out < 0 and not allow_short:
            out = 0
        signals.append(out)
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
    worst_adverse_pct: float = 0.0  # FIX lot2 (F6) : le MAE reellement observe

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

    pos = 0  # +1 / -1 / 0
    entry_price = 0.0
    entry_index = 0
    last_mark = 0.0  # dernier prix de valorisation de la position ouverte
    worst = 0.0      # pire mouvement adverse de la position courante (F6)

    def open_trade(i: int, price: float, side: int) -> None:
        nonlocal pos, entry_price, entry_index, last_mark, worst
        pos = side
        entry_price = price
        entry_index = i
        last_mark = price
        worst = 0.0
        # Frais d'entree bookes SUR la barre d'entree (taker par fill) :
        # sans eux l'equite oubliait la moitie des frais (bug T7).
        bar_ret[i] += -FEE_FRACTION_PER_FILL

    def close_trade(idx: int, price: float, reason: str) -> None:
        nonlocal pos, last_mark, worst
        # Jambe de sortie : du dernier mark au prix de sortie REEL (stop, take,
        # open de retournement, close d'eod). AVANT le fix, la barre de stop
        # restait a 0.0 : la perte stoppee n'entrait JAMAIS dans l'equite
        # (bug T7, reports/aster_deep_regimes.md).
        bar_ret[idx] += pos * (price / last_mark - 1.0) - FEE_FRACTION_PER_FILL
        # FIX lot2 (F6) : le MAE du trade = le pire adverse OBSERVE, fill de
        # gap compris — jamais une distance de stop supposee.
        worst = max(worst, -pos * (price / entry_price - 1.0))
        trades.append(
            Trade(
                entry_index=entry_index,
                exit_index=idx,
                side=pos,
                entry_price=entry_price,
                exit_price=price,
                reason=reason,
                worst_adverse_pct=worst,
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
        # FIX lot2 (F7) : un gap d'ouverture au-dela du stop execute au MARCHE
        # (open) — le modele taker_market ne donne jamais un fill meilleur
        # que le prix disponible apres le gap.
        if pos != 0:
            if pos == 1:
                stop_price = entry_price * (1.0 - stop_frac)
                take_price = entry_price * (1.0 + take_frac)
                if bar.open <= stop_price:
                    close_trade(i, bar.open, "stop")
                elif bar.low <= stop_price:
                    close_trade(i, stop_price, "stop")
                elif bar.high >= take_price:
                    close_trade(i, take_price, "take")
                else:
                    worst = max(worst, (entry_price - bar.low) / entry_price)
            else:  # short
                stop_price = entry_price * (1.0 + stop_frac)
                take_price = entry_price * (1.0 - take_frac)
                if bar.open >= stop_price:
                    close_trade(i, bar.open, "stop")
                elif bar.high >= stop_price:
                    close_trade(i, stop_price, "stop")
                elif bar.low <= take_price:
                    close_trade(i, take_price, "take")
                else:
                    worst = max(worst, (bar.high - entry_price) / entry_price)

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

        # FIX lot2 (F6) : liquidation jugee sur le MAE reellement observe
        # (gaps de fill compris), pas sur la distance du stop supposee.
        side = "long" if t.side == 1 else "short"
        worst_adverse_pct = t.worst_adverse_pct
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
        "strategy": "mean_reversion",
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
