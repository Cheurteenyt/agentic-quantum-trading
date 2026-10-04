"""Walk-forward : le split train/validation glissant qui alimente le gate anti-overfit.

Stdlib pure (le juge ne doit pas pouvoir casser a cause d'une dependance).

Pourquoi ce module existe : le legacy mesurait un PnL sur UNE periode choisie
apres coup, ce qui garantit un resultat flatteur. Ici, la performance est
mesuree sur plusieurs segments hors echantillon disjoints, et le rapport
OOS/IS devient une metrique de premiere classe (docs/03-methodology.md
sections 2.2 et 3).

Deux invariants non negociables :
  1. Zero leakage : le segment de test d'un fold ne touche jamais son train,
     ni les barres d'embargo qui les separent.
  2. `None` signifie NON MESURE, jamais zero. Convertir un None en 0.0 est
     exactement le mensonge qui a coute 4 000 USD.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass
from typing import Callable, Sequence

from .gates import sharpe

__all__ = [
    "Fold",
    "WalkForwardConfig",
    "WalkForwardResult",
    "make_folds",
    "run_walkforward",
    "param_sensitivity",
]


@dataclass(frozen=True)
class Fold:
    """Un decoupage train/test. Bornes en style Python : fin exclusive."""

    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    @property
    def train_bars(self) -> int:
        return self.train_end - self.train_start

    @property
    def test_bars(self) -> int:
        return self.test_end - self.test_start


@dataclass(frozen=True)
class WalkForwardConfig:
    """Parametres du split. Frozen : un split qui change en cours de run rend
    les resultats incomparables entre eux."""

    n_folds: int = 5
    train_ratio: float = 0.7
    anchored: bool = False
    embargo_bars: int = 0
    min_train_bars: int = 100
    min_test_bars: int = 30

    def fingerprint(self) -> str:
        """Empreinte du protocole de validation : deux resultats issus de
        splits differents ne se comparent pas (meme logique que GateConfig)."""
        payload = json.dumps(self.__dict__, sort_keys=True)
        return hashlib.sha1(payload.encode()).hexdigest()[:12]


def make_folds(n_bars: int, cfg: WalkForwardConfig) -> list[Fold]:
    """Construit les folds walk-forward sur une serie de `n_bars` barres.

    Geometrie : les segments de test sont contigus et couvrent la fin de la
    serie sans se chevaucher, ce qui garantit que chaque barre n'est evaluee
    hors echantillon qu'une seule fois (sinon on gonfle artificiellement la
    taille de l'echantillon OOS).

    Leve ValueError si la serie est trop courte pour respecter
    min_train_bars / min_test_bars : mieux vaut aucun resultat qu'un resultat
    mesure sur un echantillon indefendable.
    """
    if n_bars <= 0:
        raise ValueError("n_bars doit etre strictement positif")
    if cfg.n_folds < 1:
        raise ValueError("n_folds doit etre >= 1")
    if not 0.0 < cfg.train_ratio < 1.0:
        raise ValueError("train_ratio doit etre dans ]0, 1[")
    if cfg.embargo_bars < 0:
        raise ValueError("embargo_bars ne peut pas etre negatif")

    # L'embargo est preleve une seule fois, entre le train initial et le
    # premier test : les tests etant contigus, le train de chaque fold
    # suivant s'arrete deja embargo_bars avant son propre test.
    base = n_bars - cfg.embargo_bars
    if base <= 0:
        raise ValueError("embargo_bars consomme toute la serie")

    ratio_term = cfg.train_ratio / (1.0 - cfg.train_ratio)
    test_size = int(base / (ratio_term + cfg.n_folds))
    train_size = base - cfg.n_folds * test_size

    if train_size < cfg.min_train_bars or test_size < cfg.min_test_bars:
        raise ValueError(
            f"serie trop courte : {n_bars} barres donnent train={train_size}, "
            f"test={test_size} par fold (minimums {cfg.min_train_bars}/"
            f"{cfg.min_test_bars})"
        )

    folds: list[Fold] = []
    for i in range(cfg.n_folds):
        test_start = train_size + cfg.embargo_bars + i * test_size
        test_end = test_start + test_size
        train_end = test_start - cfg.embargo_bars
        train_start = 0 if cfg.anchored else train_end - train_size
        folds.append(
            Fold(
                index=i,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
    return folds


@dataclass
class WalkForwardResult:
    """Resultat agrege d'un walk-forward. Directement injectable dans
    LaneMetrics (sharpe_is / sharpe_oos)."""

    folds: list[Fold]
    train_returns: list[list[float]]
    test_returns: list[list[float]]
    sharpe_is: float | None
    sharpe_oos: float | None
    oos_is_ratio: float | None
    fold_sharpes_oos: list[float | None]
    degradation_std: float | None
    config_fingerprint: str


def run_walkforward(returns: Sequence[float], cfg: WalkForwardConfig,
                    periods_per_year: int = 365) -> WalkForwardResult:
    """Execute le walk-forward sur une serie de rendements par barre.

    Le Sharpe OOS est calcule sur la concatenation des segments de test
    (disjoints par construction). Le Sharpe IS est la MEDIANE des Sharpes
    par fold : FIX audit v3 (C5) — en rolling, les trains se chevauchent
    (B compte dans le fold 1 ET le fold 2, mesure x1,85 sur 5000 barres),
    la concatenation surponderait donc les barres les plus recentes.

    periods_per_year : la frequence REELLE des barres (1h -> 8760, 4h ->
    2190, 1d -> 365). Le defaut 365 est la convention journaliere — le
    moteur passe la frequence derivee des barres (FIX lot1 F1 : le defaut
    seul sous-annualisait les series intraday d'un facteur sqrt(24)).
    """
    series = list(returns)
    folds = make_folds(len(series), cfg)

    train_returns = [series[f.train_start:f.train_end] for f in folds]
    test_returns = [series[f.test_start:f.test_end] for f in folds]

    all_train = [r for seg in train_returns for r in seg]
    all_test = [r for seg in test_returns for r in seg]

    fold_sharpes_is = [sharpe(seg, periods_per_year) for seg in train_returns]
    measured_is = [s for s in fold_sharpes_is if s is not None]
    sharpe_is = (statistics.median(measured_is)
                 if len(measured_is) >= 2 else
                 (measured_is[0] if measured_is else None))
    sharpe_oos = sharpe(all_test, periods_per_year)

    # None ou IS <= 0 : le ratio n'a pas de sens, on ne l'invente pas.
    if sharpe_is is None or sharpe_oos is None or sharpe_is <= 0:
        oos_is_ratio = None
    else:
        oos_is_ratio = sharpe_oos / sharpe_is

    fold_sharpes_oos = [sharpe(seg, periods_per_year) for seg in test_returns]
    measured = [s for s in fold_sharpes_oos if s is not None]
    degradation_std = statistics.stdev(measured) if len(measured) >= 2 else None

    return WalkForwardResult(
        folds=folds,
        train_returns=train_returns,
        test_returns=test_returns,
        sharpe_is=sharpe_is,
        sharpe_oos=sharpe_oos,
        oos_is_ratio=oos_is_ratio,
        fold_sharpes_oos=fold_sharpes_oos,
        degradation_std=degradation_std,
        config_fingerprint=cfg.fingerprint(),
    )


def param_sensitivity(
    evaluate: Callable[[dict], float],
    base_params: dict[str, float],
    perturbation_pct: float = 10.0,
) -> float | None:
    """Degradation relative maximale du score sous perturbation +/- X % des params.

    Une strategie dont le score s'effondre pour 10 % de variation d'un
    parametre n'a pas trouve un edge : elle a trouve un pic de bruit dans la
    grille de recherche. C'est ce que mesure ce chiffre, consomme par
    LaneMetrics.param_sensitivity (rejet au-dela de 0.5).

    Renvoie None si le score de base est indisponible/nul (ratio indefini) ou
    si aucune perturbation n'a pu etre evaluee.
    """
    try:
        base_score = evaluate(dict(base_params))
    except Exception:
        return None
    if base_score is None or base_score == 0:
        return None

    worst: float | None = None
    for name, value in base_params.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue  # on ne perturbe que le numerique : un flag n'a pas de +/-10 %
        for sign in (1.0, -1.0):
            trial = dict(base_params)
            trial[name] = value * (1.0 + sign * perturbation_pct / 100.0)
            try:
                score = evaluate(trial)
            except Exception:
                continue  # un essai qui casse n'est pas une preuve de robustesse
            if score is None:
                continue
            if worst is None or score < worst:
                worst = score

    if worst is None:
        return None
    return max(0.0, (base_score - worst) / abs(base_score))
