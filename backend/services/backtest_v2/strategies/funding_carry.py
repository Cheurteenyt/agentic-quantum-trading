"""Strategie de collecte de funding (funding carry, non-directionnelle).

La strategie detient le cote QUI ENCAISSE le funding, pas le cote directionnel.
Sur un perpetual, le funding est paye par les longs quand il est positif et par
les shorts quand il est negatif :

    funding > 0  -> les longs paient  -> on est SHORT (on encaisse)
    funding < 0  -> les shorts paient -> on est LONG  (on encaisse)
    funding == 0 -> aucun bord         -> plat

La position est maintenue jusqu'au retournement du signe du funding (ici le taux
moyen est une constante du backtest : il ne tourne pas en cours de serie) OU
jusqu'au "stop de duree" (hold_max_bars). Au-dela, on roule la position (close +
reopen au meme open) pour continuer a collecter le funding periodiquement.

Le PnL de la strategie = derive du sous-jacent (exposition directionnelle
volontairement faible, quasi-neutre) MOINS les frais/slippage PLUS le funding
encaisse. On assume ici une exposition directionnelle faible : la derive est
minee par construction (position maintenue dans le sens collecteur, pas tradee
sur le trend).

REGLE ABSOLUE (docs/08-contributing.md, baselines.py) :
    le signal (le sens collecteur) est une info EXOGENE au prix (il vient du
    cache de funding Aster, connu avant le backtest). Il n'utilise AUCUNE barre
    du sous-jacent, donc muter la derniere barre ne peut modifier AUCUNE entree
    anterieure. C'est le test anti-look-ahead.

Signe/taux du funding : via load_funding_rate(symbol, FUNDING_CACHE_PATH). Si le
cache est absent ou perime (costs.CostDataUnavailable), le funding est mis a
0.0 EXPLICITE et blob['funding_available'] = False ; sans signe connu, la
strategie reste plate (aucun bord non justifie).

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
from pathlib import Path
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

# Espace de parametres explore. 1 * 3 * 1 * 2 * 2 = 12 combinaisons (< 300).
# side_filter n'a qu'une valeur ('auto') : le sens est toujours le sens collecteur.
PARAM_SPACE: dict[str, Sequence[Any]] = {
    "side_filter": [("auto",)],
    "hold_max_bars": [168, 336, 672],   # barres 1h ~ 7j / 14j / 28j
    "allow_short": [True],
    "stop_bps": [200, 500],
    "max_leverage": [2, 3],
}

# Chemin du cache de funding Aster (resolu de facon cwd-independent).
ROOT = Path(__file__).resolve().parents[4]  # .../trading-agent
FUNDING_CACHE_PATH = (
    ROOT / "backend" / "services" / "onchain" / "aster"
    / "aster_public_funding_history_cache.json"
)

# Notional par trade et profondeur du carnet synthetique (50K).
BOOK_NOTIONAL_USD = 50_000.0
# Taux de maintenance Aster typique pour le check de liquidation.
MAINTENANCE_MARGIN_RATE = 0.005
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_EXECUTION_MODEL = "taker_market"
FEE_FRACTION_ROUND_TRIP = 8.0 / 10_000.0  # 8 bps aller-retour (taker USDT)
FEE_FRACTION_PER_FILL = FEE_FRACTION_ROUND_TRIP / 2.0  # 4 bps taker PAR fill


# ----------------------------------------------------------------- trades


@dataclass
class Trade:
    entry_index: int
    exit_index: int
    side: int  # +1 long, -1 short
    entry_price: float
    exit_price: float
    reason: str  # 'roll' | 'stop' | 'eod'

    @property
    def gross_return(self) -> float:
        return self.side * (self.exit_price / self.entry_price - 1.0)

    @property
    def net_return(self) -> float:
        return self.gross_return - FEE_FRACTION_ROUND_TRIP

    @property
    def holding_bars(self) -> int:
        return max(1, self.exit_index - self.entry_index)


def _side_from_rate(avg_bps_per_8h: float) -> str | None:
    """Sens collecteur : positif -> short, negatif -> long, nul -> plat."""
    if avg_bps_per_8h > 0.0:
        return "short"
    if avg_bps_per_8h < 0.0:
        return "long"
    return None


def simulate(
    bars: Sequence[Bar], params: dict, side: str | None, hold_max_bars: int
) -> tuple[list[Trade], list[float]]:
    """Simule la strategie. Renvoie (trades clotures, rendement par barre).

    Execution : entree a l'OPEN de la barre i (i >= 1) dans le sens collecteur,
    connu ex-ante (funding exogene au prix). La position est roulee tous les
    hold_max_bars (stop de duree) et coupe par un stop de protection. Rendement
    par barre = signe_position * (close[i]/close[i-1] - 1), 0.0 hors position.
    """
    n = len(bars)
    bar_ret: list[float] = [0.0] * n
    if side is None:
        return [], bar_ret

    sd = 1 if side == "long" else -1
    stop_frac = float(params["stop_bps"]) / 10_000.0

    trades: list[Trade] = []
    pos_open = False
    entry_price = 0.0
    entry_index = 0
    held = 0
    last_mark = 0.0  # dernier prix de valorisation de la position ouverte

    def open_at(i: int, price: float) -> None:
        nonlocal entry_price, entry_index, held, pos_open, last_mark
        entry_price = price
        entry_index = i
        held = 1
        pos_open = True
        last_mark = price
        # Frais d'entree bookes SUR la barre d'entree (taker par fill) :
        # sans eux l'equite oubliait la moitie des frais (bug T7).
        bar_ret[i] += -FEE_FRACTION_PER_FILL

    def close_trade(idx: int, price: float, reason: str) -> None:
        nonlocal pos_open, entry_price, entry_index, held, last_mark
        if not pos_open:
            return
        # Jambe de sortie : du dernier mark au prix de sortie REEL (stop, open
        # de roulement, close d'eod). AVANT le fix, la barre de stop restait a
        # 0.0 : la perte stoppee n'entrait JAMAIS dans l'equite (bug T7,
        # reports/aster_deep_regimes.md).
        bar_ret[idx] += sd * (price / last_mark - 1.0) - FEE_FRACTION_PER_FILL
        trades.append(
            Trade(
                entry_index=entry_index,
                exit_index=idx,
                side=sd,
                entry_price=entry_price,
                exit_price=price,
                reason=reason,
            )
        )
        pos_open = False
        held = 0

    for i in range(1, n):
        bar = bars[i]

        # A. Ouverture si plat. Le sens est constant et exogene : on entre des
        #    qu'une barre d'execution existe. Aucune info future n'est lue.
        if not pos_open:
            open_at(i, bar.open)
        else:
            held += 1

        # B. Stop de protection sur le high/low de la barre.
        if pos_open:
            if sd == 1:
                stop_price = entry_price * (1.0 - stop_frac)
                if bar.low <= stop_price:
                    close_trade(i, stop_price, "stop")
            else:
                stop_price = entry_price * (1.0 + stop_frac)
                if bar.high >= stop_price:
                    close_trade(i, stop_price, "stop")

        # C. Roulement si la duree max est atteinte (stop de duree). Le close et
        #    le reopen se font au meme open : l'exposition reste continue.
        if pos_open and held >= hold_max_bars:
            close_trade(i, bar.open, "roll")
            if not pos_open:  # roule au meme open
                open_at(i, bar.open)

        # D. Mark-to-market : la position ouverte est valorisee du dernier mark
        #    (open d'entree/roulement ou close precedent) au close de la barre.
        #    Pour une barre portee sans evenement, c'est le close-to-close
        #    d'avant ; la difference porte sur l'entree (base = open reel) et
        #    la barre de sortie (bookee au prix de sortie, pas 0).
        if pos_open:
            bar_ret[i] += sd * (bar.close / last_mark - 1.0)
            last_mark = bar.close

    # Sortie forcee de fin de serie : une position ouverte doit etre valorisee.
    if pos_open:
        close_trade(n - 1, bars[-1].close, "eod")

    return trades, bar_ret


# -------------------------------------------------------------------- couts


def _bar_hours(bars: Sequence[Bar]) -> float:
    if len(bars) >= 2:
        dt_ms = bars[1].ts - bars[0].ts
        if dt_ms > 0:
            return dt_ms / 3_600_000.0
    return 1.0


def _synthetic_book(
    reference_price: float, notional_usd: float
) -> list[tuple[float, float]]:
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
    rate: Any,
) -> tuple[CostBreakdown, dict[str, Any]]:
    """Agrege les 4 postes sur l'ensemble des trades. Jamais de None implicite.

    `rate` est le FundingRate charge (ou None si indisponible). Si None, le
    funding est mis a 0.0 EXPLICITE et le flag blob['funding_available']=False.
    """
    cb = CostBreakdown()
    flags: dict[str, Any] = {"funding_available": False, "funding_reason": None}

    fees = 0.0
    slip = 0.0
    funding = 0.0
    all_safe = True
    hours_per_bar = _bar_hours(bars)

    if rate is not None:
        flags["funding_available"] = True
    else:
        flags["funding_reason"] = "funding cache indisponible ou perime"
        funding = 0.0  # explicite, jamais None

    for t in trades:
        side = "long" if t.side == 1 else "short"

        # fees taker USDT aller-retour (8 bps) sur le notional du carnet.
        fees += round_trip_fees_usd(BOOK_NOTIONAL_USD, symbol, DEFAULT_EXECUTION_MODEL)

        # slippage : consommation d'un carnet synthetique de 50K notional.
        book = _synthetic_book(t.entry_price, BOOK_NOTIONAL_USD)
        slip += slippage_usd(BOOK_NOTIONAL_USD, book, t.entry_price)

        # funding sur le notionnel, prorata de la duree de detention (periodes
        # de 8h = holding_hours / 8).
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
    hold_max_bars = int(params["hold_max_bars"])

    # Funding : cache reel Aster (signe + taille). Si indisponible -> None.
    rate = None
    try:
        rate = load_funding_rate(symbol, FUNDING_CACHE_PATH)
    except CostDataUnavailable:
        rate = None

    # Sens collecteur, resolu depuis le signe du funding (side_filter 'auto').
    side: str | None = None
    if rate is not None:
        side = _side_from_rate(rate.avg_bps_per_8h)
    sf = params.get("side_filter", ("auto",))
    if isinstance(sf, (tuple, list)):
        sf = sf[0] if sf else "auto"
    if sf not in ("auto", None):
        # Filtre explicite (non utilise par PARAM_SPACE) : override le sens.
        side = sf if sf in ("long", "short") else side
    # Pas de short si interdit : on reste plat plutot que de prendre le mauvais
    # cote (on paierait le funding au lieu de le collecter).
    if side == "short" and not bool(params.get("allow_short", True)):
        side = None

    trades, bar_ret = simulate(bars, params, side, hold_max_bars)

    trade_returns = [t.net_return for t in trades]
    if trades:
        avg_hold = round(sum(t.holding_bars for t in trades) / len(trades))
    else:
        avg_hold = 0

    costs, flags = _build_costs(trades, bars, params, symbol, rate)

    # Courbe d'equity capitalisee a partir des rendements par barre.
    equity = [1.0]
    for r in bar_ret:
        equity.append(equity[-1] * (1.0 + r))

    blob: dict[str, Any] = {
        "strategy": "funding_carry",
        "symbol": symbol,
        "side": side,
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
