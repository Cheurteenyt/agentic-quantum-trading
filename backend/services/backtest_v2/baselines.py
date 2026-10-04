"""Les 3 benchmarks obligatoires, NETS DE COUTS.

docs/03-methodology.md section 4 : une strategie ne se juge jamais dans
l'absolu. Elle doit battre, en OOS et couts inclus :

    1. buy & hold           sur le meme actif, meme periode
    2. entrees aleatoires   meme frequence, meme duree de detention
    3. momentum simple      croisement de moyennes mobiles

Le benchmark aleatoire est le plus important : il repond a "ce resultat est-il
distinguable du hasard ?". Une lane a 70 % de win-rate sur 19 trades tombe en
plein dans le corps de la distribution aleatoire — c'est du bruit, pas un bord.

DEUX REGLES QUI NE SE NEGOCIENT PAS
-----------------------------------
1. Tous les rendements renvoyes ici sont NETS. Comparer un benchmark brut a une
   strategie nette est un mensonge arithmetique qui favorise la strategie.
2. Zero look-ahead : un signal calcule sur la barre i n'est executable qu'a
   l'OPEN de la barre i+1. Entrer au close de i suppose de connaitre ce close
   avant qu'il n'existe — c'est LE bug qui fabrique de fausses gagnantes.

Stdlib pure (pandas/numpy absents de cet environnement, volontairement).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Sequence

# 4 bps taker par cote sur les paires USDT Aster (cf. costs.TAKER_BPS),
# soit 8 bps aller-retour. Meme convention que costs.round_trip_fees_usd.
DEFAULT_FEES_BPS_ROUND_TRIP = 8.0


# ------------------------------------------------------------------- donnees


@dataclass(frozen=True)
class Bar:
    """Une bougie OHLCV. Immuable : une barre modifiee apres coup est une
    reecriture de l'histoire, exactement ce que le look-ahead exploite."""

    ts: int  # timestamp d'ouverture, en millisecondes
    open: float
    high: float
    low: float
    close: float
    volume: float


def bars_from_klines(raw: Sequence[Sequence]) -> list[Bar]:
    """Parse le format klines Aster/Binance.

    Format attendu par ligne :
        [openTime, open, high, low, close, volume, closeTime, ...]

    Leve ValueError sur ligne trop courte, valeur non numerique, prix <= 0,
    volume negatif, ou timestamps non strictement croissants. On leve plutot
    que de filtrer : une serie silencieusement trouee produit un backtest
    plausible et faux, ce qui est bien pire qu'une erreur bruyante.
    """
    bars: list[Bar] = []
    prev_ts: int | None = None

    for i, row in enumerate(raw):
        if row is None or len(row) < 6:
            raise ValueError(f"kline #{i}: ligne trop courte ({row!r})")
        try:
            ts = int(row[0])
            o, h, l, c = (float(row[1]), float(row[2]), float(row[3]), float(row[4]))
            v = float(row[5])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"kline #{i}: valeur non numerique ({row!r})") from exc

        for name, price in (("open", o), ("high", h), ("low", l), ("close", c)):
            if not price > 0:
                raise ValueError(f"kline #{i}: {name}={price} <= 0")
        if v < 0:
            raise ValueError(f"kline #{i}: volume negatif ({v})")
        if h < l:
            raise ValueError(f"kline #{i}: high {h} < low {l}")
        if prev_ts is not None and ts <= prev_ts:
            raise ValueError(
                f"kline #{i}: timestamp {ts} <= precedent {prev_ts} "
                "(serie non strictement croissante)"
            )

        prev_ts = ts
        bars.append(Bar(ts=ts, open=o, high=h, low=l, close=c, volume=v))

    return bars


def bar_returns(bars: Sequence[Bar]) -> list[float]:
    """Rendements simples close-to-close. len(resultat) == len(bars) - 1."""
    return [
        bars[i].close / bars[i - 1].close - 1.0
        for i in range(1, len(bars))
    ]


# ----------------------------------------------------------------- resultats


@dataclass
class BaselineTrade:
    entry_index: int
    exit_index: int
    side: str  # 'long' | 'short'
    gross_return: float
    net_return: float


@dataclass
class BaselineResult:
    name: str
    total_return: float  # net de couts, capitalise
    trades: list[BaselineTrade] = field(default_factory=list)
    n_trades: int = 0
    win_rate: float | None = None  # None si 0 trade — None n'est pas zero
    returns_per_trade: list[float] = field(default_factory=list)


def _fee_fraction(fees_bps_round_trip: float) -> float:
    """bps aller-retour -> fraction. Toujours >= 0 : le signe est applique
    a la soustraction, jamais laisse a l'appelant (cf. costs.py, ou un cout
    est negatif)."""
    if fees_bps_round_trip < 0:
        raise ValueError(f"frais negatifs interdits: {fees_bps_round_trip}")
    return fees_bps_round_trip / 10_000.0


def compounded_total_return(returns: Sequence[float]) -> float:
    """L'unique algebre de rendement du projet : equity = prod(1 + r) - 1.

    FIX lot2 (F14) : le moteur comparait sum(trade_returns) (cote strategie)
    a ce compose (cote benchmarks) — deux conventions pour le meme gate.
    SOMMER des pourcentages surestime les series gagnantes.
    """
    equity = 1.0
    for r in returns:
        equity *= 1.0 + r
    return equity - 1.0


def _build_result(
    name: str, trades: list[BaselineTrade]
) -> BaselineResult:
    """Agrege des trades en resultat. Le total capitalise les rendements nets :
    sommer des pourcentages surestime les series gagnantes."""
    nets = [t.net_return for t in trades]
    total = compounded_total_return(nets)
    wins = sum(1 for r in nets if r > 0)
    return BaselineResult(
        name=name,
        total_return=total,
        trades=trades,
        n_trades=len(trades),
        win_rate=(wins / len(nets)) if nets else None,
        returns_per_trade=nets,
    )


# ------------------------------------------------------------- buy and hold


def buy_and_hold_return(
    bars: Sequence[Bar],
    fees_bps_round_trip: float = DEFAULT_FEES_BPS_ROUND_TRIP,
) -> float:
    """Rendement total d'un achat au premier close et d'une vente au dernier,
    net d'UN seul aller-retour de frais (on n'entre et ne sort qu'une fois).

    Leve ValueError si moins de 2 barres : il n'y a alors rien a detenir.
    """
    if len(bars) < 2:
        raise ValueError("buy & hold requiert au moins 2 barres")
    fee = _fee_fraction(fees_bps_round_trip)
    gross = bars[-1].close / bars[0].close - 1.0
    return gross - fee


# ------------------------------------------------------------------ momentum


def _sma(bars: Sequence[Bar], end_index: int, window: int) -> float | None:
    """Moyenne mobile des closes se terminant a `end_index` INCLUS.

    Aucune barre posterieure a end_index n'est lue : c'est ce qui garantit
    l'absence de fuite d'information.
    """
    if end_index + 1 < window:
        return None
    total = 0.0
    for i in range(end_index - window + 1, end_index + 1):
        total += bars[i].close
    return total / window


def momentum_baseline(
    bars: Sequence[Bar],
    fast: int = 20,
    slow: int = 50,
    fees_bps_round_trip: float = DEFAULT_FEES_BPS_ROUND_TRIP,
    allow_short: bool = True,
) -> BaselineResult:
    """Croisement de moyennes mobiles simples, la baseline naive.

    Signal sur la barre i : long si SMA(fast) > SMA(slow), short si inferieur
    (uniquement si allow_short, sinon flat). EXECUTION A L'OPEN DE i+1 : le
    signal de la barre i n'est connu qu'une fois cette barre cloturee, donc le
    premier prix reellement atteignable est l'ouverture suivante.

    Consequence testable : la derniere barre ne peut influencer AUCUNE entree
    anterieure. C'est le test anti-look-ahead.
    """
    if fast <= 0 or slow <= 0:
        raise ValueError("fenetres de moyennes mobiles invalides")
    if fast >= slow:
        raise ValueError(f"fast ({fast}) doit etre < slow ({slow})")

    fee = _fee_fraction(fees_bps_round_trip)
    trades: list[BaselineTrade] = []
    n = len(bars)

    position: str | None = None   # 'long' | 'short' | None
    entry_index = -1
    entry_price = 0.0

    def close_position(exit_index: int, exit_price: float) -> None:
        nonlocal position, entry_index, entry_price
        if position == "long":
            gross = exit_price / entry_price - 1.0
        else:
            gross = entry_price / exit_price - 1.0
        trades.append(
            BaselineTrade(
                entry_index=entry_index,
                exit_index=exit_index,
                side=position,  # type: ignore[arg-type]
                gross_return=gross,
                net_return=gross - fee,
            )
        )
        position = None

    # i = barre du signal ; i + 1 = barre d'execution (a son open).
    for i in range(n - 1):
        f = _sma(bars, i, fast)
        s = _sma(bars, i, slow)
        if f is None or s is None:  # pas assez d'historique pour un signal
            continue

        if f > s:
            desired = "long"
        elif f < s:
            desired = "short" if allow_short else None
        else:
            desired = position  # egalite stricte : on ne bouge pas pour rien

        if desired == position:
            continue

        exec_index = i + 1
        exec_price = bars[exec_index].open

        if position is not None:
            close_position(exec_index, exec_price)
        if desired is not None:
            position = desired
            entry_index = exec_index
            entry_price = exec_price

    # Sortie forcee au dernier close : une position ouverte a la fin du
    # backtest doit etre valorisee, pas oubliee (sinon les pertes latentes
    # disparaissent — le mensonge n.4 de la methodo).
    if position is not None:
        close_position(n - 1, bars[-1].close)

    return _build_result("momentum", trades)


# ------------------------------------------------------------------ aleatoire


def _random_trades(
    bars: Sequence[Bar],
    n_trades: int,
    avg_holding_bars: int,
    fee: float,
    rng: random.Random,
    allow_short: bool,
) -> list[BaselineTrade]:
    """Tire n_trades trades aleatoires. Toute la source d'alea passe par `rng`,
    jamais par le module `random` global : un benchmark non reproductible ne
    prouve rien."""
    n = len(bars)
    trades: list[BaselineTrade] = []
    # Derniere barre ou une entree (a l'open) laisse la place a une sortie.
    last_entry = n - 2
    if last_entry < 1:
        return trades

    # FIX audit v3 (C4) : le benchmark respecte le MEME modele d'occupation
    # mono-position que les strategies — sans quoi strategy > random compare
    # deux capacites de capital differentes.
    last_exit = 0
    for _ in range(n_trades):
        entry_index = rng.randint(1, last_entry)
        if entry_index <= last_exit:
            continue
        # Duree geometrique de moyenne avg_holding_bars : meme frequence et
        # meme duree moyenne de detention que la strategie testee.
        hold = 1 + int(rng.expovariate(1.0 / max(1, avg_holding_bars)))
        exit_index = min(entry_index + hold, n - 1)
        if exit_index <= entry_index:
            continue
        last_exit = exit_index

        side = "long"
        if allow_short and rng.random() < 0.5:
            side = "short"

        entry_price = bars[entry_index].open
        exit_price = bars[exit_index].open
        gross = (
            exit_price / entry_price - 1.0
            if side == "long"
            else entry_price / exit_price - 1.0
        )
        trades.append(
            BaselineTrade(
                entry_index=entry_index,
                exit_index=exit_index,
                side=side,
                gross_return=gross,
                net_return=gross - fee,
            )
        )
    return trades


def random_trades_baseline(
    bars: Sequence[Bar],
    n_trades: int,
    avg_holding_bars: int,
    fees_bps_round_trip: float = DEFAULT_FEES_BPS_ROUND_TRIP,
    seed: int = 42,
    allow_short: bool = True,
) -> BaselineResult:
    """Un tirage d'entrees aleatoires, meme frequence et meme duree moyenne de
    detention que la strategie testee. Deterministe pour un seed donne."""
    if n_trades <= 0:
        raise ValueError(f"n_trades invalide: {n_trades}")
    if avg_holding_bars <= 0:
        raise ValueError(f"avg_holding_bars invalide: {avg_holding_bars}")
    fee = _fee_fraction(fees_bps_round_trip)
    rng = random.Random(seed)
    trades = _random_trades(bars, n_trades, avg_holding_bars, fee, rng, allow_short)
    return _build_result("random", trades)


def random_distribution(
    bars: Sequence[Bar],
    n_trades: int,
    avg_holding_bars: int,
    n_trials: int = 1000,
    fees_bps_round_trip: float = DEFAULT_FEES_BPS_ROUND_TRIP,
    seed: int = 42,
    allow_short: bool = True,
) -> list[float]:
    """Distribution nulle : n_trials tirages -> liste des rendements totaux nets.

    C'est la reference qui repond a "distinguable du hasard ?". On compare a la
    DISTRIBUTION, jamais a sa moyenne : la moyenne cache la variance, et c'est
    la variance qui explique les 70 % de win-rate sur 19 trades.

    Un seul Random est utilise pour toute la serie de tirages : chaque essai
    consomme la suite du flux, donc les essais sont independants ET l'ensemble
    reste reproductible.
    """
    if n_trials <= 0:
        raise ValueError(f"n_trials invalide: {n_trials}")
    if n_trades <= 0:
        raise ValueError(f"n_trades invalide: {n_trades}")
    if avg_holding_bars <= 0:
        raise ValueError(f"avg_holding_bars invalide: {avg_holding_bars}")

    fee = _fee_fraction(fees_bps_round_trip)
    rng = random.Random(seed)
    out: list[float] = []
    for _ in range(n_trials):
        trades = _random_trades(bars, n_trades, avg_holding_bars, fee, rng, allow_short)
        equity = 1.0
        for t in trades:
            equity *= 1.0 + t.net_return
        out.append(equity - 1.0)
    return out


# ---------------------------------------------------------------- comparaison


def compare_to_baselines(
    strategy_return: float,
    bars: Sequence[Bar],
    n_trades: int,
    avg_holding_bars: int,
    fees_bps_round_trip: float = DEFAULT_FEES_BPS_ROUND_TRIP,
    seed: int = 42,
) -> dict:
    """Confronte un rendement de strategie NET aux 3 benchmarks.

    `random_percentile` est le pourcentage de tirages aleatoires strictement
    battus par la strategie. Le seuil est 95 : tomber a 60 signifie que 40 %
    des singes font mieux.

    `all_passed` exige les trois. Un seul benchmark battu ne prouve rien :
    battre le hasard dans un marche haussier, c'est souvent juste etre long.
    """
    bh = buy_and_hold_return(bars, fees_bps_round_trip)
    mom = momentum_baseline(bars, fees_bps_round_trip=fees_bps_round_trip)
    dist = random_distribution(
        bars,
        n_trades,
        avg_holding_bars,
        fees_bps_round_trip=fees_bps_round_trip,
        seed=seed,
    )

    beaten = sum(1 for r in dist if strategy_return > r)
    pct = 100.0 * beaten / len(dist)

    beats_bh = strategy_return > bh
    beats_mom = strategy_return > mom.total_return
    beats_rand = pct >= 95.0

    return {
        "buy_and_hold": bh,
        "momentum": mom.total_return,
        "momentum_result": mom,
        "random_distribution": dist,
        "random_percentile": pct,
        "beats_buy_and_hold": beats_bh,
        "beats_momentum": beats_mom,
        "beats_random_95": beats_rand,
        "all_passed": bool(beats_bh and beats_mom and beats_rand),
    }
