"""Strategie de volatility harvesting (market-making simule, non-directionnelle).

Principe : on ne parie PAS sur la direction. On cote des deux cotes du marche
et on encaisse la fourchette intra-barre (high - low), diminuee d'une marge de
securite `spread_bps` qui represente ce que le carnet reel ne nous laissera
jamais capturer :

    pnl_brut(barre) = max(0, (high - low) - spread_bps/10000 * close) * notionnel / close

Si high <= low, ou si la fourchette est plus etroite que la marge de securite,
le resultat est 0 : PAS de trade (ni gain, ni cout).

REGLE ABSOLUE (docs/08-contributing.md, baselines.py) :
    signal calcule sur la barre i  ->  EXECUTION A L'OPEN DE i+1.

Concretement : on decide de coter pendant la barre i+1 UNIQUEMENT si la barre i
(deja close, donc information disponible) presentait une fourchette exploitable.
La recolte de la barre i+1 est realisee pendant la barre i+1 : c'est un
resultat, pas une information anticipee. Muter la derniere barre ne peut donc
modifier aucun rendement anterieur — c'est le test anti-look-ahead.

Aucune exposition close->close : le rendement par barre est purement la recolte
de fourchette, jamais un delta directionnel.

Les 4 postes de cout sont remplis explicitement (jamais None -> zero implicite) :
  - fees        : taker USDT aller-retour (8 bps) via round_trip_fees_usd
  - slippage    : consommation d'un carnet synthetique de 50K notional
  - funding     : cache reel Aster ; si indisponible, 0.0 EXPLICITE + flag au blob
  - liquidation : check_liquidation, avec le pire mouvement adverse observe

`microstructure_validated` reste False : aucun carnet reel n'est valide ici, le
carnet utilise pour le slippage est synthetique. Une strategie de market-making
non validee sur carnet reel n'est PAS deployable.

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
    load_funding_series,
    round_trip_fees_usd,
    slippage_usd,
)
from backend.services.backtest_v2.engine import StrategyEval

# --------------------------------------------------------------- parametres

# 3 * 1 * 2 = 6 combinaisons (tres largement < 300).
PARAM_SPACE: dict[str, Sequence[Any]] = {
    "spread_bps": [5, 10, 20],
    "allow_short": [True],
    "max_leverage": [2, 3],
}

FULL_PARAM_RANGES: dict[str, Sequence[Any]] = dict(PARAM_SPACE)

BOOK_NOTIONAL_USD = 50_000.0
MAINTENANCE_MARGIN_RATE = 0.005
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_EXECUTION_MODEL = "taker_market"


# ----------------------------------------------------------------- signaux


def harvestable_fraction(bar: Bar, spread_bps: float) -> float:
    """Fraction de notionnel recoltable sur CETTE barre (>= 0).

    max(0, (high - low) - spread_frac * close) / close.
    Renvoie 0.0 si high <= low ou si la fourchette n'excede pas la marge.
    """
    if bar.close <= 0:
        return 0.0
    if bar.high <= bar.low:
        return 0.0
    spread_frac = float(spread_bps) / 10_000.0
    captured = (bar.high - bar.low) - spread_frac * bar.close
    if captured <= 0.0:
        return 0.0
    return captured / bar.close


def compute_signals(bars: Sequence[Bar], params: dict) -> list[int]:
    """signal[i] = 1 si la barre i, DEJA CLOSE, etait exploitable.

    Le signal n'utilise que l'information de la barre i. Il autorise la cotation
    pendant la barre i+1 (execution a l'open de i+1).
    """
    spread_bps = float(params["spread_bps"])
    if spread_bps < 0:
        raise ValueError(f"spread_bps invalide: {spread_bps}")
    return [1 if harvestable_fraction(b, spread_bps) > 0.0 else 0 for b in bars]


# ------------------------------------------------------------------- trades


@dataclass
class Trade:
    """Une session de cotation d'UNE barre (round-trip complet dans la barre)."""

    bar_index: int
    gross_return: float
    fee_usd: float
    slippage_usd: float

    fund_usd: float = 0.0  # FIX audit v3 (C3) : le funding entre dans le net

    @property
    def net_return(self) -> float:
        return self.gross_return + (self.fee_usd + self.slippage_usd
                                    + self.fund_usd) / BOOK_NOTIONAL_USD

    @property
    def holding_bars(self) -> int:
        return 1


def _synthetic_book(reference_price: float, notional_usd: float) -> list[tuple[float, float]]:
    """Carnet synthetique de ~2x le notional demande, 8 niveaux a +1 bp/niveau."""
    order_qty = notional_usd / reference_price
    per_level = order_qty / 4.0
    return [
        (reference_price * (1.0 + 0.0001 * k), per_level)
        for k in range(8)
    ]


def simulate(bars: Sequence[Bar], params: dict) -> tuple[list[Trade], list[float]]:
    """Simule la recolte. Renvoie (trades clotures, rendement par barre).

    Barre i : on cote seulement si signals[i-1] == 1 (execution a l'open de i).
    Le rendement de la barre i est la recolte realisee pendant la barre i,
    nette des frais et du slippage. 0.0 hors position.
    """
    n = len(bars)
    signals = compute_signals(bars, params)
    spread_bps = float(params["spread_bps"])
    symbol = str(params.get("symbol", DEFAULT_SYMBOL))

    trades: list[Trade] = []
    bar_ret = [0.0] * n

    for i in range(n):
        if i == 0 or signals[i - 1] != 1:
            continue  # pas de cotation autorisee sur cette barre
        gross = harvestable_fraction(bars[i], spread_bps)
        if gross <= 0.0:
            continue  # fourchette trop etroite : PAS de trade, pas de cout

        fee = round_trip_fees_usd(BOOK_NOTIONAL_USD, symbol, DEFAULT_EXECUTION_MODEL)
        book = _synthetic_book(bars[i].open, BOOK_NOTIONAL_USD)
        slip = slippage_usd(BOOK_NOTIONAL_USD, book, bars[i].open)

        t = Trade(bar_index=i, gross_return=gross, fee_usd=fee, slippage_usd=slip)
        trades.append(t)
        bar_ret[i] = t.net_return

    return trades, bar_ret


# -------------------------------------------------------------------- couts


def _bar_hours(bars: Sequence[Bar]) -> float:
    if len(bars) >= 2:
        dt_ms = bars[1].ts - bars[0].ts
        if dt_ms > 0:
            return dt_ms / 3_600_000.0
    return 1.0


def _worst_adverse_pct(bars: Sequence[Bar]) -> float:
    """Pire amplitude intra-barre observee, en %. Donnee reelle, pas hypothese."""
    worst = 0.0
    for b in bars:
        if b.close > 0 and b.high > b.low:
            worst = max(worst, (b.high - b.low) / b.close * 100.0)
    return worst


def _build_costs(
    trades: Sequence[Trade],
    bars: Sequence[Bar],
    params: dict,
    symbol: str,
) -> tuple[CostBreakdown, dict[str, Any]]:
    """Agrege les 4 postes. Jamais de None implicite."""
    cb = CostBreakdown()
    flags: dict[str, Any] = {"funding_available": False, "funding_reason": None}

    fees = 0.0
    slip = 0.0
    funding = 0.0
    all_safe = True
    hours_per_bar = _bar_hours(bars)
    worst_adverse = _worst_adverse_pct(bars)

    # FIX audit v3 (C1+C3) : funding as-of par barre ET booké dans la courbe.
    fser = None
    try:
        fser = load_funding_series(symbol)
        flags["funding_available"] = True
    except CostDataUnavailable as exc:
        flags["funding_available"] = False
        flags["funding_reason"] = str(exc)

    for t in trades:
        fees += t.fee_usd
        slip += t.slippage_usd

        # Le book est neutre en direction : on facture la jambe longue
        # (conservateur : on ne credite jamais) sur sa durée (1 barre).
        if fser is not None:
            holding_hours = t.holding_bars * hours_per_bar
            entry_ms = bars[t.bar_index].ts
            raw = (BOOK_NOTIONAL_USD * fser.sum_pct_between(
                entry_ms, entry_ms + holding_hours * 3_600_000.0) / 100.0)
            fund_usd = -raw
            funding += fund_usd
            t.fund_usd = fund_usd

        chk = check_liquidation(
            entry_price=bars[t.bar_index].open,
            side="long",
            leverage=float(params["max_leverage"]),
            maintenance_margin_rate=MAINTENANCE_MARGIN_RATE,
            worst_adverse_pct=worst_adverse,
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

    avg_hold = 1 if trades else 0

    costs, flags = _build_costs(trades, bars, params, symbol)
    # FIX audit v3 (C3) : la courbe est reconstruite APRÈS la comptabilité —
    # le funding booké entre dans l'equity (réconciliation complète).
    bar_ret = [0.0] * len(bars)
    for t in trades:
        bar_ret[t.bar_index] = t.net_return
    trade_returns = [t.net_return for t in trades]

    equity = [1.0]
    for r in bar_ret:
        equity.append(equity[-1] * (1.0 + r))

    blob: dict[str, Any] = {
        "strategy": "volatility_harvesting",
        "directional": False,
        "n_trades": len(trades),
        "harvest_bars": [t.bar_index for t in trades],
        "spread_bps": float(params["spread_bps"]),
        "funding_available": flags["funding_available"],
        "funding_reason": flags["funding_reason"],
        "worst_adverse_pct": _worst_adverse_pct(bars),
        "costs_total_usd": costs.total_usd,
        "microstructure_note": (
            "carnet synthetique : aucune validation de carnet reel, "
            "microstructure_validated=False"
        ),
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
