"""Strategie `funding_fade` — mean-reversion SUR LE FUNDING (non directionnelle).

Idee
----
Le funding perpetuel est une serie qui revient a sa moyenne. Quand il devient
extreme (z-score eleve), la position surchargee paie cher et se debouclera :

    z(funding) >  entry_z   ->  SHORT  (les longs paient, le short encaisse)
    z(funding) < -entry_z   ->  LONG   (les shorts paient, le long encaisse)
    |z|        <  exit_z    ->  PLAT   (l'anomalie est resorbee)

La source de PnL n'est PAS la direction du prix : c'est le funding encaisse par
le cote gagnant, moins les frais, le slippage et la derive de prix subie.

REGLE ABSOLUE (docs/08-contributing.md, baselines.py) :
    signal calcule sur la barre i  ->  EXECUTION A L'OPEN DE i+1.
Le z-score a l'indice i n'utilise que funding[0..i] (fenetre glissante causale),
et la serie de funding ne depend que de l'INDICE de barre (pas des prix), donc
muter la derniere barre ne peut modifier aucune entree anterieure.

APPROXIMATION DOCUMENTEE — serie de funding
-------------------------------------------
Le cache Aster (`load_funding_rate`) ne fournit qu'UNE moyenne agregee
(`avg_bps_per_8h`), pas l'historique barre par barre. On reconstruit donc une
serie synthetique DETERMINISTE centree sur cette moyenne reelle :

    funding_bps[i] = avg_bps_per_8h + amplitude * oscillation(i, seed(symbol))

ou `oscillation` est une somme de sinusoides d'amplitudes/periodes fixes, avec
une phase derivee du symbole (crc32) : meme symbole -> meme serie, toujours.
Ce n'est PAS du funding historique reel : c'est une enveloppe de variabilite
plausible autour d'une moyenne reelle. Le blob porte le flag
`funding_series_synthetic=True` et `funding_series_note` pour que personne ne
prenne le resultat pour une mesure. Si le cache est indisponible ou perime, la
serie est centree sur 0.0 EXPLICITE (jamais None) et le blob porte
`funding_available=False` + le motif.

Les 4 postes de cout sont remplis explicitement (jamais None -> zero implicite).

Stdlib pure. Imports ABSOLUS volontaires : le module reste chargeable seul
(via importlib) sans declencher le __init__ du sous-package.
"""
from __future__ import annotations

import math
import zlib
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

# Espace complet de reference (documente).
FULL_PARAM_RANGES: dict[str, Sequence[Any]] = {
    "lookback": [100, 200],
    "entry_z": [1.5, 2.0, 2.5],
    "exit_z": [0.3, 0.5],
    "allow_short": [True],
    "stop_bps": [200, 400],
    "max_leverage": [2, 3],
}

# Grid effectivement explore : 2*3*2*1*2*2 = 48 combinaisons (< 300).
PARAM_SPACE: dict[str, Sequence[Any]] = {
    "lookback": [100, 200],
    "entry_z": [1.5, 2.0, 2.5],
    "exit_z": [0.3, 0.5],
    "allow_short": [True],
    "stop_bps": [200, 400],
    "max_leverage": [2, 3],
}

BOOK_NOTIONAL_USD = 50_000.0
MAINTENANCE_MARGIN_RATE = 0.005
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_EXECUTION_MODEL = "taker_market"
FEE_FRACTION_ROUND_TRIP = 8.0 / 10_000.0  # 8 bps aller-retour (taker USDT)
FEE_FRACTION_PER_FILL = FEE_FRACTION_ROUND_TRIP / 2.0  # 4 bps taker PAR fill

# Amplitude plancher de l'oscillation synthetique, en bps par 8h. Le funding
# moyen reel est petit (BTC ~ +0.46 bps/8h) : sans plancher, la serie serait
# quasi plate et aucun z-score ne serait exploitable.
MIN_OSC_AMPLITUDE_BPS = 0.5
FUNDING_SERIES_NOTE = (
    "serie de funding SYNTHETIQUE deterministe centree sur avg_bps_per_8h du "
    "cache Aster (le cache ne stocke qu'une moyenne, pas l'historique par barre)"
)


# -------------------------------------------------------- serie de funding


def _symbol_phase(symbol: str) -> float:
    """Phase deterministe dans [0, 2pi) derivee du symbole (crc32)."""
    seed = zlib.crc32((symbol or "").encode("utf-8"))
    return (seed % 10_000) / 10_000.0 * 2.0 * math.pi


def synthetic_funding_series(
    n: int, base_bps: float, symbol: str
) -> list[float]:
    """Serie de funding (bps/8h) deterministe, centree sur `base_bps`.

    Somme de trois sinusoides de periodes incommensurables, modulee par une
    enveloppe lente : cela produit des episodes d'extremes (|z| > 2.5) comme
    le funding reel, sans aucun aleatoire.
    """
    if n < 0:
        raise ValueError(f"longueur invalide: {n}")
    phase = _symbol_phase(symbol)
    amp = max(MIN_OSC_AMPLITUDE_BPS, abs(base_bps) * 2.0)
    out: list[float] = []
    for i in range(n):
        env = 1.0 + 0.85 * math.sin(2.0 * math.pi * i / 211.0 + phase)
        osc = (
            math.sin(2.0 * math.pi * i / 37.0 + phase)
            + 0.55 * math.sin(2.0 * math.pi * i / 13.0 + 2.1 * phase)
            + 0.30 * math.sin(2.0 * math.pi * i / 89.0 + 0.7 * phase)
        )
        out.append(base_bps + amp * env * osc)
    return out


def resolve_funding(
    n: int, symbol: str, cache_path: Path | None = None
) -> tuple[list[float], float | None, dict[str, Any]]:
    """(serie bps/8h, avg reel ou None, flags). Jamais de None implicite -> 0.0."""
    flags: dict[str, Any] = {
        "funding_available": False,
        "funding_reason": None,
        "funding_avg_bps_per_8h": None,
        "funding_series_synthetic": True,
        "funding_series_note": FUNDING_SERIES_NOTE,
    }
    base = 0.0
    avg: float | None = None
    try:
        rate = load_funding_rate(symbol, cache_path)
        base = float(rate.avg_bps_per_8h)
        avg = base
        flags["funding_available"] = True
        flags["funding_avg_bps_per_8h"] = base
    except CostDataUnavailable as exc:
        # funding indisponible : centre sur 0.0 EXPLICITE, motif conserve.
        base = 0.0
        flags["funding_available"] = False
        flags["funding_reason"] = str(exc)
    return synthetic_funding_series(n, base, symbol), avg, flags


# ----------------------------------------------------------------- z-score


def rolling_zscore(values: Sequence[float], lookback: int) -> list[float]:
    """z[i] sur la fenetre glissante values[i-lookback+1 .. i]. Causal.

    0.0 tant que la fenetre n'est pas pleine, et 0.0 si l'ecart-type est nul
    (serie plate : aucune anomalie mesurable, surtout pas une division).
    """
    if lookback <= 1:
        raise ValueError(f"lookback invalide: {lookback}")
    out: list[float] = []
    for i in range(len(values)):
        if i + 1 < lookback:
            out.append(0.0)
            continue
        win = values[i - lookback + 1 : i + 1]
        m = sum(win) / len(win)
        var = sum((x - m) ** 2 for x in win) / len(win)
        sd = math.sqrt(var)
        out.append(0.0 if sd <= 1e-12 else (values[i] - m) / sd)
    return out


def compute_signals(
    bars: Sequence[Bar],
    params: dict,
    funding_bps: Sequence[float] | None = None,
) -> list[int]:
    """Signal desire par barre : +1 long, -1 short, 0 plat.

    Machine a etats causale : signal[i] ne depend que de funding[0..i].
    `funding_bps` peut etre injecte (tests / donnees externes) ; sinon la serie
    synthetique documentee est utilisee.
    """
    lookback = int(params["lookback"])
    entry_z = float(params["entry_z"])
    exit_z = float(params["exit_z"])
    allow_short = bool(params["allow_short"])
    if entry_z <= 0:
        raise ValueError(f"entry_z invalide: {entry_z}")
    if exit_z < 0 or exit_z >= entry_z:
        raise ValueError(f"exit_z ({exit_z}) doit etre dans [0, entry_z)")

    n = len(bars)
    if funding_bps is None:
        symbol = str(params.get("symbol", DEFAULT_SYMBOL))
        funding_bps, _avg, _flags = resolve_funding(n, symbol, params.get("funding_cache"))
    series = list(funding_bps)[:n]
    z = rolling_zscore(series, lookback)

    signals: list[int] = []
    state = 0
    for i in range(n):
        if i + 1 < lookback:
            signals.append(0)
            continue
        zi = z[i]
        if state == 0:
            if zi > entry_z:
                state = -1  # funding trop haut -> fade en SHORT
            elif zi < -entry_z:
                state = 1  # funding trop bas -> fade en LONG
        else:
            if abs(zi) < exit_z:
                state = 0
            elif zi > entry_z:
                state = -1
            elif zi < -entry_z:
                state = 1
        if state < 0 and not allow_short:
            signals.append(0)
        else:
            signals.append(state)
    return signals


# ------------------------------------------------------------------- trades


@dataclass
class Trade:
    entry_index: int
    exit_index: int
    side: int  # +1 long, -1 short
    entry_price: float
    exit_price: float
    reason: str  # 'stop' | 'flat' | 'reverse' | 'eod'
    funding_return: float = 0.0  # funding encaisse (>0) ou paye (<0), en fraction
    worst_adverse_pct: float = 0.0  # FIX lot2 (F6) : le MAE reellement observe
    slip_frac: float = 0.0  # FIX lot3 (F2) : slippage en fraction du notionnel

    @property
    def price_return(self) -> float:
        return self.side * (self.exit_price / self.entry_price - 1.0)

    @property
    def gross_return(self) -> float:
        return self.price_return + self.funding_return

    @property
    def net_return(self) -> float:
        # FIX lot3 (F2) : le slippage entre dans le net — même comptabilité
        # que la courbe (le funding y est déjà via funding_return).
        return self.gross_return + self.slip_frac - FEE_FRACTION_ROUND_TRIP

    @property
    def holding_bars(self) -> int:
        return max(1, self.exit_index - self.entry_index)


def _bar_hours(bars: Sequence[Bar]) -> float:
    if len(bars) >= 2:
        dt_ms = bars[1].ts - bars[0].ts
        if dt_ms > 0:
            return dt_ms / 3_600_000.0
    return 1.0


def simulate(
    bars: Sequence[Bar],
    params: dict,
    funding_bps: Sequence[float] | None = None,
) -> tuple[list[Trade], list[float]]:
    """Simule la strategie. Renvoie (trades clotures, rendement par barre).

    Execution : le signal de la barre i-1 est applique a l'OPEN de la barre i.
    Le rendement par barre agrege la derive de prix subie ET le funding
    encaisse/paye : un short encaisse quand le funding est positif.
    """
    n = len(bars)
    if funding_bps is None:
        symbol = str(params.get("symbol", DEFAULT_SYMBOL))
        funding_bps, _avg, _flags = resolve_funding(n, symbol, params.get("funding_cache"))
    series = list(funding_bps)[:n]
    signals = compute_signals(bars, params, series)
    stop_frac = float(params["stop_bps"]) / 10_000.0
    hours = _bar_hours(bars)

    trades: list[Trade] = []
    bar_ret = [0.0] * n

    pos = 0
    entry_price = 0.0
    entry_index = 0
    acc_funding = 0.0
    last_mark = 0.0  # dernier prix de valorisation de la position ouverte
    worst = 0.0      # pire mouvement adverse de la position courante (F6)

    def open_trade(i: int, price: float, side: int) -> None:
        nonlocal pos, entry_price, entry_index, last_mark, acc_funding, worst
        pos = side
        entry_price = price
        entry_index = i
        last_mark = price
        acc_funding = 0.0
        worst = 0.0
        # Frais d'entree bookes SUR la barre d'entree (taker par fill) :
        # sans eux l'equite oubliait la moitie des frais (bug T7).
        bar_ret[i] += -FEE_FRACTION_PER_FILL

    def close_trade(idx: int, price: float, reason: str) -> None:
        nonlocal pos, last_mark, acc_funding, worst
        # Jambe de sortie : du dernier mark au prix de sortie REEL (stop, open
        # de retournement, close d'eod). AVANT le fix, la barre de stop restait
        # a 0.0 : la perte stoppee n'entrait JAMAIS dans l'equite (bug T7,
        # reports/aster_deep_regimes.md). Le funding de la barre est deja
        # accrue (accrue_funding) AVANT ce close.
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
                funding_return=acc_funding,
                worst_adverse_pct=worst,
            )
        )
        pos = 0
        acc_funding = 0.0

    def accrue_funding(i: int) -> None:
        """Funding de la barre i, accrue dans le trade ET l'equite.

        Appelle tant que la position a ete DETENUE pendant la barre, y compris
        la barre du stop : avant le fix, le funding de la barre de stop etait
        perdu des deux cotes (trade et equity).
        """
        nonlocal acc_funding
        # funding positif => les longs paient => un short encaisse.
        fund_leg = -pos * (series[i] / 10_000.0) * (hours / 8.0)
        acc_funding += fund_leg
        bar_ret[i] += fund_leg

    for i in range(n):
        bar = bars[i]

        # A. Execution a l'open : le signal de la barre i-1 s'applique ici.
        if i >= 1:
            desired = signals[i - 1]
            if desired != pos:
                if pos != 0:
                    close_trade(i, bar.open, "reverse" if desired != 0 else "flat")
                if desired != 0:
                    open_trade(i, bar.open, desired)

        # B. Stop de protection pendant la barre (high/low), barre d'entree incluse.
        # FIX lot2 (F7) : un gap d'ouverture au-dela du stop execute au MARCHE.
        stopped = False
        if pos != 0:
            if pos == 1:
                stop_price = entry_price * (1.0 - stop_frac)
                if bar.open <= stop_price:
                    accrue_funding(i)
                    close_trade(i, bar.open, "stop")
                    stopped = True
                elif bar.low <= stop_price:
                    accrue_funding(i)
                    close_trade(i, stop_price, "stop")
                    stopped = True
                else:
                    worst = max(worst, (entry_price - bar.low) / entry_price)
            else:
                stop_price = entry_price * (1.0 + stop_frac)
                if bar.open >= stop_price:
                    accrue_funding(i)
                    close_trade(i, bar.open, "stop")
                    stopped = True
                elif bar.high >= stop_price:
                    accrue_funding(i)
                    close_trade(i, stop_price, "stop")
                    stopped = True
                else:
                    worst = max(worst, (bar.high - entry_price) / entry_price)

        # C. Mark-to-market du prix + funding encaisse par le cote gagnant.
        if pos != 0 and not stopped:
            accrue_funding(i)
            bar_ret[i] += pos * (bar.close / last_mark - 1.0)
            last_mark = bar.close

    if pos != 0:
        close_trade(n - 1, bars[-1].close, "eod")

    return trades, bar_ret


# -------------------------------------------------------------------- couts


def _synthetic_book(reference_price: float, notional_usd: float) -> list[tuple[float, float]]:
    """Carnet synthetique de ~2x le notional demande, 8 niveaux a +1 bp/niveau."""
    order_qty = notional_usd / reference_price
    per_level = order_qty / 4.0
    return [
        (reference_price * (1.0 + 0.0001 * k), per_level) for k in range(8)
    ]


def _build_costs(
    trades: Sequence[Trade],
    bars: Sequence[Bar],
    params: dict,
    symbol: str,
    flags: dict[str, Any],
) -> tuple[CostBreakdown, list[float]]:
    """Agrege les 4 postes sur l'ensemble des trades. Jamais de None implicite.

    FIX lot3 (F2) : renvoie aussi le slippage PAR TRADE en fraction du
    notionnel — l'evaluate le book dans la courbe et dans les nets (le
    funding de la courbe vient de la série synthétique du trade lui-même).
    """
    cb = CostBreakdown()
    fees = 0.0
    slip = 0.0
    funding = 0.0
    all_safe = True
    hours_per_bar = _bar_hours(bars)
    per_trade_slip: list[float] = []

    rate = None
    if flags.get("funding_available"):
        try:
            rate = load_funding_rate(symbol, params.get("funding_cache"))
        except CostDataUnavailable as exc:  # pragma: no cover - defensif
            flags["funding_available"] = False
            flags["funding_reason"] = str(exc)
            rate = None

    for t in trades:
        fees += round_trip_fees_usd(BOOK_NOTIONAL_USD, symbol, DEFAULT_EXECUTION_MODEL)

        book = _synthetic_book(t.entry_price, BOOK_NOTIONAL_USD)
        slip_usd = slippage_usd(BOOK_NOTIONAL_USD, book, t.entry_price)
        slip += slip_usd
        per_trade_slip.append(slip_usd / BOOK_NOTIONAL_USD)

        side = "long" if t.side == 1 else "short"
        if rate is not None:
            funding += funding_cost_usd(
                BOOK_NOTIONAL_USD, t.holding_bars * hours_per_bar, side, rate
            )

        # FIX lot2 (F6) : liquidation jugee sur le MAE reellement observe
        # (gaps de fill compris), pas sur la distance du stop supposee.
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
    cb.funding_usd = funding  # 0.0 EXPLICITE si le cache est indisponible
    cb.liquidation_checked = True
    cb.liquidation_safe = all_safe if trades else True
    if not flags.get("funding_available"):
        cb.warnings.append("funding indisponible: 0.0 explicite (voir blob)")
    cb.warnings.append(FUNDING_SERIES_NOTE)
    return cb, per_trade_slip


# ------------------------------------------------------------------ contrat


def evaluate(params: dict, bars: Sequence[Bar]) -> StrategyEval:
    """Contrat moteur : (params, bars) -> StrategyEval. Deterministe."""
    symbol = str(params.get("symbol", DEFAULT_SYMBOL))
    injected = params.get("funding_bps_series")
    if injected is None:
        series, _avg, flags = resolve_funding(
            len(bars), symbol, params.get("funding_cache")
        )
    else:
        series = list(injected)[: len(bars)]
        flags = {
            "funding_available": False,
            "funding_reason": "serie de funding injectee par l'appelant",
            "funding_avg_bps_per_8h": None,
            "funding_series_synthetic": True,
            "funding_series_note": "serie injectee (tests / source externe)",
        }

    trades, bar_ret = simulate(bars, params, series)

    avg_hold = (
        round(sum(t.holding_bars for t in trades) / len(trades)) if trades else 0
    )

    costs, per_trade_slip = _build_costs(trades, bars, params, symbol, flags)
    # FIX lot3 (F2) : UNE comptabilité — le slippage entre dans la courbe ET
    # dans les nets, dérivé du même calcul que le CostBreakdown.
    for t, slip_frac in zip(trades, per_trade_slip):
        t.slip_frac = slip_frac
        bar_ret[t.exit_index] += slip_frac
    trade_returns = [t.net_return for t in trades]

    equity = [1.0]
    for r in bar_ret:
        equity.append(equity[-1] * (1.0 + r))

    blob: dict[str, Any] = {
        "strategy": "funding_fade",
        "n_trades": len(trades),
        "entries": [(t.entry_index, t.side) for t in trades],
        "exit_reasons": [t.reason for t in trades],
        "funding_available": flags["funding_available"],
        "funding_reason": flags["funding_reason"],
        "funding_avg_bps_per_8h": flags["funding_avg_bps_per_8h"],
        "funding_series_synthetic": flags["funding_series_synthetic"],
        "funding_series_note": flags["funding_series_note"],
        "funding_return_total": sum(t.funding_return for t in trades),
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
