"""Modelisation des 4 postes de cout — le gate `costs_incomplete` prend vie ici.

docs/03-methodology.md section 2.3 : un backtest sans ces quatre postes n'est
pas un backtest.

    fees        maker/taker reels, aller-retour, sur le notionnel
    funding     sur le NOTIONNEL (pas la marge), prorata de la duree de detention
    slippage    fonction de la taille vs profondeur du carnet
    liquidation distance au prix de liquidation, verifiee

PRINCIPE DIRECTEUR
------------------
Chaque poste renvoie soit un cout mesure, soit `None` + un motif. `None` n'est
JAMAIS converti en zero. Le legacy traitait un funding absent comme un funding
nul : c'est comme ca qu'un cout disparait d'un backtest.

Les taux fee viennent de aster_perps_model (source officielle Aster, audit
2026-05-31). Les caches locaux sont GELES depuis juin 2026 : ce module refuse
par defaut d'utiliser une donnee de funding perimee (docs/05-data-sources.md).

Stdlib pure.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

ASTER_DIR = Path(__file__).resolve().parents[1] / "onchain/aster"
FUNDING_CACHE = ASTER_DIR / "aster_public_funding_history_cache.json"

# Age au dela duquel une donnee de funding cachee n'est plus utilisable.
MAX_FUNDING_AGE_DAYS = 30

# Taux Aster officiels (bps), miroir de aster_perps_model.py.
# Duplique volontairement : ce module ne doit pas dependre du package legacy.
TAKER_BPS = {"USDT": 4.0, "USD1": 0.5}
MAKER_BPS = {"USDT": 0.0, "USD1": 0.0}
DEFAULT_TAKER_BPS = 4.0

MAKER_MODELS = {"maker_post_only", "bbo_limit_maker", "post_only"}


class CostDataUnavailable(Exception):
    """Donnee de cout absente ou perimee. Jamais rattrapee par une valeur par defaut."""


# ------------------------------------------------------------------- helpers


def quote_asset(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if s.endswith("USD1"):
        return "USD1"
    if s.endswith("USDT"):
        return "USDT"
    return "UNKNOWN"


def fee_bps(symbol: str, execution_model: str) -> float:
    """bps par cote. Le modele d'execution fait partie de l'identite de lane :
    supposer maker quand on execute en taker divise le cout par 8 sur USDT."""
    q = quote_asset(symbol)
    if (execution_model or "").strip().lower() in MAKER_MODELS:
        return MAKER_BPS.get(q, 0.0)
    return TAKER_BPS.get(q, DEFAULT_TAKER_BPS)


# --------------------------------------------------------------------- fees


def round_trip_fees_usd(
    notional_usd: float, symbol: str, execution_model: str
) -> float:
    """Cout d'un aller-retour complet. Toujours negatif (c'est une charge)."""
    if notional_usd <= 0:
        raise ValueError(f"notionnel invalide: {notional_usd}")
    return -abs(notional_usd * (fee_bps(symbol, execution_model) / 10_000.0) * 2.0)


# ------------------------------------------------------------------ funding


@dataclass(frozen=True)
class FundingRate:
    symbol: str
    avg_bps_per_8h: float
    sample_count: int
    last_funding_time_ms: int
    cached_at: float
    interval_hours: float = 8.0  # FIX lot2 (F12) : mesuré par le cache, 8h si absent

    @property
    def age_days(self) -> float:
        return (time.time() - self.cached_at) / 86400.0

    @property
    def is_stale(self) -> bool:
        return self.age_days > MAX_FUNDING_AGE_DAYS


def load_funding_rate(
    symbol: str, cache_path: Path | None = None
) -> FundingRate:
    """Lit le funding cache. Leve si absent, incomplet, ou trop vieux.

    Lever plutot que renvoyer None est volontaire : un appelant distrait peut
    ignorer un None, il ne peut pas ignorer une exception.
    """
    path = cache_path or FUNDING_CACHE
    try:
        blob: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CostDataUnavailable(f"cache funding illisible: {path}") from exc

    entry = (blob.get("symbols") or {}).get(symbol)
    if not entry:
        raise CostDataUnavailable(f"funding absent du cache pour {symbol}")

    data = entry.get("data") or {}
    if data.get("status") != "ok":
        raise CostDataUnavailable(
            f"funding {symbol}: status={data.get('status')!r}"
        )

    avg = data.get("avg_funding_bps_per_8h")
    count = data.get("funding_count")
    if avg is None or not count:
        raise CostDataUnavailable(f"funding {symbol}: moyenne ou echantillon manquant")

    rate = FundingRate(
        symbol=symbol,
        avg_bps_per_8h=float(avg),
        sample_count=int(count),
        last_funding_time_ms=int(data.get("last_funding_time") or 0),
        cached_at=float(entry.get("cached_at") or 0.0),
        interval_hours=float(data.get("funding_interval_hours") or 8.0),
    )
    if rate.is_stale:
        raise CostDataUnavailable(
            f"funding {symbol}: cache vieux de {rate.age_days:.0f} jours "
            f"(max {MAX_FUNDING_AGE_DAYS}) — rafraichir avant de backtester"
        )
    return rate


def funding_cost_usd(
    notional_usd: float,
    holding_hours: float,
    side: str,
    rate: FundingRate,
) -> float:
    """Funding sur le NOTIONNEL, prorata de la duree de detention.

    L'erreur du legacy etait de l'appliquer a la marge : avec un levier 5, le
    cout reel est 5x superieur a l'estimation.

    Signe : funding positif = les longs paient. Un short encaisse (cout positif).
    """
    if notional_usd <= 0:
        raise ValueError(f"notionnel invalide: {notional_usd}")
    if holding_hours < 0:
        raise ValueError(f"duree invalide: {holding_hours}")

    # FIX lot2 (F12) : l'intervalle vient du cache (mesuré par
    # refresh_aster_cache), pas d'un 8h supposé — les intervalles Aster
    # ne sont pas universellement 8h.
    periods = holding_hours / rate.interval_hours
    cost = notional_usd * (rate.avg_bps_per_8h / 10_000.0) * periods

    s = (side or "").strip().lower()
    if s == "long":
        return -cost
    if s == "short":
        return cost
    raise ValueError(
        f"side={side!r} : le funding a un signe, 'both' doit etre resolu "
        "par trade avant d'appeler cette fonction"
    )


# ----------------------------------------------------------------- slippage


def slippage_usd(
    notional_usd: float,
    book_levels: Sequence[tuple[float, float]],
    reference_price: float,
) -> float:
    """Slippage par consommation reelle du carnet.

    `book_levels` : [(prix, quantite), ...] du cote traverse, du meilleur au pire.
    Leve si le carnet ne peut pas absorber l'ordre — c'est une information
    capitale, pas un cas limite : une lane non executable n'est pas une lane.

    ATTENTION au choix de `reference_price`. Cette fonction mesure l'ecart entre
    le prix moyen obtenu et la reference fournie :

      - reference = best ask (achat) -> renvoie le seul IMPACT de marche.
        Le demi-spread doit alors etre compte ailleurs, sinon il disparait.
      - reference = mid              -> renvoie impact + demi-spread.

    Un ordre absorbe par le premier niveau au prix de reference renvoie donc 0,
    ce qui est correct mais optimiste si la reference n'est pas executable.
    En cas de doute, passer le mid : sous-estimer un cout est l'erreur qui coute.
    """
    if notional_usd <= 0:
        raise ValueError(f"notionnel invalide: {notional_usd}")
    if reference_price <= 0:
        raise ValueError(f"prix de reference invalide: {reference_price}")
    if not book_levels:
        raise CostDataUnavailable("carnet vide : slippage non mesurable")

    remaining = notional_usd / reference_price  # quantite a executer
    filled_qty = 0.0
    filled_cost = 0.0

    for price, qty in book_levels:
        if remaining <= 0:
            break
        if price <= 0 or qty <= 0:
            continue
        take = min(remaining, qty)
        filled_cost += take * price
        filled_qty += take
        remaining -= take

    if remaining > 1e-12:
        raise CostDataUnavailable(
            f"carnet insuffisant : {remaining / (notional_usd / reference_price):.1%} "
            "de l'ordre non executable — taille trop grande pour ce marche"
        )

    avg_price = filled_cost / filled_qty
    return -abs((avg_price - reference_price) * filled_qty)


def slippage_from_spread_usd(
    notional_usd: float, spread_bps: float, participation: float = 1.0
) -> float:
    """Approximation degradee : demi-spread, majoree par la participation.

    A n'utiliser que si le carnet n'est pas disponible, et a signaler comme
    telle. Moins fiable que `slippage_usd`.
    """
    if notional_usd <= 0:
        raise ValueError(f"notionnel invalide: {notional_usd}")
    if spread_bps < 0:
        raise ValueError(f"spread invalide: {spread_bps}")
    return -abs(notional_usd * (spread_bps / 10_000.0) / 2.0 * max(1.0, participation))


# -------------------------------------------------------------- liquidation


@dataclass(frozen=True)
class LiquidationCheck:
    safe: bool
    liquidation_price: float
    distance_pct: float
    reason: str = ""


def check_liquidation(
    entry_price: float,
    side: str,
    leverage: float,
    maintenance_margin_rate: float,
    worst_adverse_pct: float,
) -> LiquidationCheck:
    """Verifie que le pire mouvement adverse observe n'atteint pas la liquidation.

    `worst_adverse_pct` doit venir des donnees reelles du backtest (pire MAE),
    pas d'une hypothese. Une lane liquidee ne perd pas son stop : elle perd la
    marge entiere.
    """
    if entry_price <= 0:
        raise ValueError(f"prix d'entree invalide: {entry_price}")
    if leverage <= 0:
        raise ValueError(f"levier invalide: {leverage}")
    if not 0 <= maintenance_margin_rate < 1:
        raise ValueError(f"taux de maintenance invalide: {maintenance_margin_rate}")

    move_to_liq = (1.0 / leverage) - maintenance_margin_rate
    s = (side or "").strip().lower()
    if s == "long":
        liq_price = entry_price * (1.0 - move_to_liq)
    elif s == "short":
        liq_price = entry_price * (1.0 + move_to_liq)
    else:
        raise ValueError(f"side={side!r} invalide pour un calcul de liquidation")

    distance_pct = move_to_liq * 100.0
    if move_to_liq <= 0:
        return LiquidationCheck(
            False, liq_price, distance_pct,
            f"levier {leverage:g} incompatible avec une maintenance de "
            f"{maintenance_margin_rate:.2%} : liquidation immediate",
        )
    if worst_adverse_pct >= distance_pct:
        return LiquidationCheck(
            False, liq_price, distance_pct,
            f"pire mouvement adverse {worst_adverse_pct:.2f} % >= distance de "
            f"liquidation {distance_pct:.2f} % : la lane a ete liquidee",
        )
    return LiquidationCheck(True, liq_price, distance_pct)


# ------------------------------------------------------------ agregation


@dataclass
class CostBreakdown:
    """Les 4 postes, separes. Jamais un total opaque."""

    fees_usd: float | None = None
    funding_usd: float | None = None
    slippage_usd: float | None = None
    liquidation_checked: bool = False
    liquidation_safe: bool | None = None
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing and self.liquidation_checked

    @property
    def total_usd(self) -> float | None:
        """Total UNIQUEMENT si les 4 postes sont mesures. Sinon None.

        Un total partiel est pire qu'une absence de total : il a l'air d'un
        chiffre et il sous-estime systematiquement.
        """
        if not self.complete:
            return None
        return (self.fees_usd or 0.0) + (self.funding_usd or 0.0) + (self.slippage_usd or 0.0)

    def as_metrics(self) -> dict[str, Any]:
        """Forme consommable par gates.LaneMetrics / store.record()."""
        return {
            "fees_usd": self.fees_usd,
            "funding_usd": self.funding_usd,
            "slippage_usd": self.slippage_usd,
            "liquidation_checked": bool(self.liquidation_checked and self.liquidation_safe),
        }


def compute_costs(
    *,
    notional_usd: float,
    symbol: str,
    side: str,
    execution_model: str,
    holding_hours: float,
    entry_price: float,
    leverage: float,
    maintenance_margin_rate: float | None = None,
    worst_adverse_pct: float | None = None,
    book_levels: Sequence[tuple[float, float]] | None = None,
    spread_bps: float | None = None,
    funding_cache: Path | None = None,
) -> CostBreakdown:
    """Calcule les 4 postes. Un poste indisponible est signale, jamais suppose nul."""
    out = CostBreakdown()

    # 1. fees — toujours calculables
    try:
        out.fees_usd = round_trip_fees_usd(notional_usd, symbol, execution_model)
    except ValueError as exc:
        out.missing.append(f"fees: {exc}")

    # 2. funding — depend du cache, souvent perime
    try:
        rate = load_funding_rate(symbol, funding_cache)
        out.funding_usd = funding_cost_usd(notional_usd, holding_hours, side, rate)
        if rate.sample_count < 30:
            out.warnings.append(
                f"funding base sur {rate.sample_count} points seulement"
            )
    except (CostDataUnavailable, ValueError) as exc:
        out.missing.append(f"funding: {exc}")

    # 3. slippage — carnet reel prioritaire, spread en degrade
    if book_levels:
        try:
            out.slippage_usd = slippage_usd(notional_usd, book_levels, entry_price)
        except (CostDataUnavailable, ValueError) as exc:
            out.missing.append(f"slippage: {exc}")
    elif spread_bps is not None:
        try:
            out.slippage_usd = slippage_from_spread_usd(notional_usd, spread_bps)
            out.warnings.append("slippage estime par demi-spread, carnet indisponible")
        except ValueError as exc:
            out.missing.append(f"slippage: {exc}")
    else:
        out.missing.append("slippage: ni carnet ni spread fournis")

    # 4. liquidation
    if maintenance_margin_rate is None or worst_adverse_pct is None:
        out.missing.append(
            "liquidation: maintenance_margin_rate et worst_adverse_pct requis"
        )
    else:
        try:
            chk = check_liquidation(
                entry_price, side, leverage, maintenance_margin_rate, worst_adverse_pct
            )
            out.liquidation_checked = True
            out.liquidation_safe = chk.safe
            if not chk.safe:
                out.warnings.append(f"liquidation: {chk.reason}")
        except ValueError as exc:
            out.missing.append(f"liquidation: {exc}")

    return out
