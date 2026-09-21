"""Strategies : les modules qui GENEREIENT des rendements.

Le moteur (`engine.run_campaign`) ne connait AUCUNE strategie. Il recoit une
fonction `evaluate(params, bars) -> StrategyEval` et l'espace de parametres ;
il calcule et juge tout le reste.

Chaque fichier ici expose :
  - `evaluate(params, bars) -> StrategyEval`   (contrat moteur)
  - `PARAM_SPACE` (dict[str, Sequence])        (espace a explorer)
  - `STRATEGY_NAME` (str)                       (pour l'identite de lane)

Pour ajouter une strategie : creer `ma_strat.py` ici avec ces trois noms, puis
l'ajouter dans `REGISTRY` ci-dessous. RIEN d'autre a modifier.

Règle absolue commune (cf. docs/08-contributing.md) :
  signal sur barre i  ->  execution a l'OPEN de i+1.  Pas de look-ahead.
"""
from __future__ import annotations

from typing import Callable, Sequence

from ..baselines import Bar
from ..engine import StrategyEval
from ..store import LaneIdentity

StrategyFn = Callable[[dict, Sequence[Bar]], StrategyEval]


def make_identity(strategy_name: str, params: dict, *,
                  symbol: str, interval: str) -> LaneIdentity:
    """Construit l'identite de lane canonique depuis les parametres.

    Le moteur exige une LaneIdentity complete (6 champs + leverage) ; sinon
    l'insertion est refusee. On derive tout depuis `params` de facon
    deterministe — une meme combinaison produit toujours la meme identite,
    donc les resultats sont comparables et non dupliques.

    `side` : la plupart des strategies ici changent de direction (long/short),
    donc on marque 'both'. `trigger` = le nom de la strategie. `execution_model`
    = taker_market par defaut (on execute au marche).
    """
    lev = params.get("max_leverage") or 1.0
    return LaneIdentity(
        symbol=symbol or "UNKNOWN",
        interval=interval or "1h",
        side="both",
        trigger=strategy_name,
        execution_model="taker_market",
        leverage=float(lev),
    )


REGISTRY: dict[str, tuple[StrategyFn, dict, str]] = {}
"""Nom -> (evaluate, PARAM_SPACE, STRATEGY_NAME)."""


def register(name: str, evaluate: StrategyFn, param_space: dict,
             strategy_name: str) -> None:
    REGISTRY[name] = (evaluate, param_space, strategy_name)


def list_strategies() -> list[str]:
    return sorted(REGISTRY)


def identity_for(strategy_name: str, *, symbol: str, interval: str):
    """Retourne la fonction identity_for attendue par run_campaign."""
    def _id(params: dict) -> LaneIdentity:
        return make_identity(strategy_name, params, symbol=symbol, interval=interval)
    return _id


# Les imports sont en bas : ils peuplent REGISTRY via register().
from .momentum import evaluate as _mom, PARAM_SPACE as _mom_ps  # noqa: E402
from .mean_reversion import evaluate as _mr, PARAM_SPACE as _mr_ps  # noqa: E402
from .breakout import evaluate as _bo, PARAM_SPACE as _bo_ps  # noqa: E402

register("momentum", _mom, _mom_ps, "momentum")
register("mean_reversion", _mr, _mr_ps, "mean_reversion")
register("breakout", _bo, _bo_ps, "breakout")

# Strategies non-directionnelles (edges structurels perpetuals)
from .funding_carry import evaluate as _fc, PARAM_SPACE as _fc_ps  # noqa: E402
from .funding_fade import evaluate as _ff, PARAM_SPACE as _ff_ps  # noqa: E402
from .volatility_harvesting import evaluate as _vh, PARAM_SPACE as _vh_ps  # noqa: E402

register("funding_carry", _fc, _fc_ps, "funding_carry")
register("funding_fade", _ff, _ff_ps, "funding_fade")
register("volatility_harvesting", _vh, _vh_ps, "volatility_harvesting")
