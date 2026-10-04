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
    load_funding_series,
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
    worst_adverse_pct: float = 0.0  # FIX audit v3 : le MAE reellement observe

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
    bars: Sequence[Bar], params: dict, side_fn, hold_max_bars: int
) -> tuple[list[Trade], list[float]]:
    """Simule la strategie. Renvoie (trades clotures, rendement par barre).

    Execution : entree a l'OPEN de la barre i (i >= 1) dans le sens collecteur
    DECIDE A CET OPEN par side_fn(bars[i].ts) — l'as-of strict sur les prints
    de funding connus. FIX audit v3 (C2) : le sens n'est plus une constante
    full-sample (le futur ne choisit plus le cote du passe) ; il est
    re-evalue a chaque open, avec renversement si le cote collecteur change.
    La position est roulee tous les hold_max_bars et coupee par un stop.
    """
    n = len(bars)
    bar_ret: list[float] = [0.0] * n
    stop_frac = float(params["stop_bps"]) / 10_000.0

    trades: list[Trade] = []
    pos_open = False
    pos_sd = 0              # +1 long / -1 short tant que la position vit
    entry_price = 0.0
    entry_index = 0
    held = 0
    last_mark = 0.0  # dernier prix de valorisation de la position ouverte
    worst = 0.0      # FIX audit v3 : le MAE reellement observe

    def open_at(i: int, price: float, sd: int) -> None:
        nonlocal pos_sd, entry_price, entry_index, held, pos_open, last_mark, worst
        pos_sd = sd
        entry_price = price
        entry_index = i
        held = 1
        pos_open = True
        last_mark = price
        worst = 0.0
        # Frais d'entree bookes SUR la barre d'entree (taker par fill) :
        # sans eux l'equite oubliait la moitie des frais (bug T7).
        bar_ret[i] += -FEE_FRACTION_PER_FILL

    def close_trade(idx: int, price: float, reason: str) -> None:
        nonlocal pos_open, entry_price, entry_index, held, last_mark, worst
        if not pos_open:
            return
        # Jambe de sortie : du dernier mark au prix de sortie REEL (stop, open
        # de roulement, close d'eod).
        bar_ret[idx] += pos_sd * (price / last_mark - 1.0) - FEE_FRACTION_PER_FILL
        worst = max(worst, -pos_sd * (price / entry_price - 1.0))
        trades.append(
            Trade(
                entry_index=entry_index,
                exit_index=idx,
                side=pos_sd,
                entry_price=entry_price,
                exit_price=price,
                reason=reason,
                worst_adverse_pct=worst,
            )
        )
        pos_open = False
        held = 0

    for i in range(1, n):
        bar = bars[i]

        # A. Le sens collecteur est re-decide a CHAQUE open, as-of : le taux
        #    connu a cet instant, jamais une moyenne du futur.
        desired = side_fn(bar.ts)
        desired_sd = 1 if desired == "long" else (-1 if desired == "short" else 0)
        if not pos_open:
            if desired_sd == 0:
                continue
            open_at(i, bar.open, desired_sd)
        else:
            held += 1
            if desired_sd != 0 and desired_sd != pos_sd:
                close_trade(i, bar.open, "roll")
                open_at(i, bar.open, desired_sd)

        # B. Stop de protection sur le high/low de la barre.
        if pos_open:
            if pos_sd == 1:
                stop_price = entry_price * (1.0 - stop_frac)
                if bar.low <= stop_price:
                    close_trade(i, stop_price, "stop")
                else:
                    worst = max(worst, (entry_price - bar.low) / entry_price)
            else:
                stop_price = entry_price * (1.0 + stop_frac)
                if bar.high >= stop_price:
                    close_trade(i, stop_price, "stop")
                else:
                    worst = max(worst, (bar.high - entry_price) / entry_price)

        # C. Roulement si la duree max est atteinte (stop de duree). Le close et
        #    le reopen se font au meme open : l'exposition reste continue, le
        #    cote roule est celui du moment (re-decide au prochain open).
        if pos_open and held >= hold_max_bars:
            close_trade(i, bar.open, "roll")
            if not pos_open:  # roule au meme open, meme cote
                open_at(i, bar.open, pos_sd)

        # D. Mark-to-market : la position ouverte est valorisee du dernier mark
        #    (open d'entree/roulement ou close precedent) au close de la barre.
        #    Pour une barre portee sans evenement, c'est le close-to-close
        #    d'avant ; la difference porte sur l'entree (base = open reel) et
        #    la barre de sortie (bookee au prix de sortie, pas 0).
        if pos_open:
            bar_ret[i] += pos_sd * (bar.close / last_mark - 1.0)
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
    fser,
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

    if fser is not None:
        flags["funding_available"] = True
    else:
        flags["funding_reason"] = "série funding indisponible"
        funding = 0.0  # explicite, jamais None

    for t in trades:
        side = "long" if t.side == 1 else "short"

        # fees taker USDT aller-retour (8 bps) sur le notional du carnet.
        fees += round_trip_fees_usd(BOOK_NOTIONAL_USD, symbol, DEFAULT_EXECUTION_MODEL)

        # slippage : consommation d'un carnet synthetique de 50K notional.
        book = _synthetic_book(t.entry_price, BOOK_NOTIONAL_USD)
        slip += slippage_usd(BOOK_NOTIONAL_USD, book, t.entry_price)

        # FIX audit v3 (C1) : funding as-of — Σ des taux réels de
        # (entrée, sortie], signé par le côté.
        if fser is not None:
            holding_hours = t.holding_bars * hours_per_bar
            entry_ms = bars[t.entry_index].ts
            raw = (BOOK_NOTIONAL_USD * fser.sum_pct_between(
                entry_ms, entry_ms + holding_hours * 3_600_000.0) / 100.0)
            funding += -raw if side == "long" else raw

        # FIX audit v3 : liquidation jugee sur le MAE reellement observe.
        chk = check_liquidation(
            entry_price=t.entry_price,
            side=side,
            leverage=float(params["max_leverage"]),
            maintenance_margin_rate=MAINTENANCE_MARGIN_RATE,
            worst_adverse_pct=t.worst_adverse_pct,
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

    # FIX audit v3 (C2) : le sens collecteur est decide AS-OF, barre par
    # barre, sur le dernier print CONNU — plus jamais par la moyenne
    # full-sample du cache (le futur ne choisit plus le cote du passe).
    fser = None
    try:
        fser = load_funding_series(symbol)
    except CostDataUnavailable:
        fser = None

    sf = params.get("side_filter", ("auto",))
    if isinstance(sf, (tuple, list)):
        sf = sf[0] if sf else "auto"
    explicit = sf if sf in ("long", "short") else None

    def side_fn(ts_ms: float) -> str | None:
        if explicit is not None:
            return explicit
        if fser is None:
            return None
        r = fser.rate_asof(ts_ms)
        if r is None:
            return None
        s = _side_from_rate(r)
        # Pas de short si interdit : on reste plat plutot que de prendre le
        # mauvais cote (on paierait le funding au lieu de le collecter).
        if s == "short" and not bool(params.get("allow_short", True)):
            return None
        return s

    trades, bar_ret = simulate(bars, params, side_fn, hold_max_bars)

    trade_returns = [t.net_return for t in trades]
    if trades:
        avg_hold = round(sum(t.holding_bars for t in trades) / len(trades))
    else:
        avg_hold = 0

    costs, flags = _build_costs(trades, bars, params, symbol, fser)

    # Courbe d'equity capitalisee a partir des rendements par barre.
    equity = [1.0]
    for r in bar_ret:
        equity.append(equity[-1] * (1.0 + r))

    blob: dict[str, Any] = {
        "strategy": "funding_carry",
        "symbol": symbol,
        "side_as_of": True,
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
