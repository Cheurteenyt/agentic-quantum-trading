"""Correction de multiplicite — la defense contre le faux positif de masse.

LE PROBLEME MESURE
------------------
La campagne de demonstration de `07-backtest-engine.md` a tourne sur du BRUIT
GAUSSIEN PUR — aucun edge, par construction. Resultat : 2 survivants sur 24
combinaisons, Sharpe OOS 1,0, 400 trades. Taux d'acceptation 8,3 %.

Le pipeline legacy acceptait 9,43 %. Meme ordre de grandeur, meme cause.

Les gates de `gates.py` jugent chaque lane ISOLEMENT. C'est necessaire, mais
insuffisant : tester 10 000 combinaisons produit des gagnants apparents
MECANIQUEMENT, meme sans aucun signal. Un Sharpe de 1,0 est remarquable sur un
test unique ; sur 10 000 tests, c'est l'attendu du hasard.

Ce module ajoute la couche manquante : juger la CAMPAGNE, pas la lane.

    "Le p-value d'une lane n'a aucun sens si on ne dit pas combien de lanes
     ont ete testees pour la trouver."

TROIS OUTILS
------------
  bonferroni      : conservateur, controle la probabilite d'AU MOINS un faux
                    positif (FWER). A utiliser quand un faux positif coute cher
                    — c'est notre cas : un faux positif part en live.
  benjamini_hochberg : controle la PROPORTION de faux positifs parmi les
                    acceptes (FDR). Moins strict, utile en phase exploratoire.
  deflated_sharpe : corrige le Sharpe lui-meme du nombre d'essais (Bailey &
                    Lopez de Prado). Repond a : "ce Sharpe est-il superieur a
                    ce que le hasard produirait sur N essais ?"

Stdlib pure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


# ---------------------------------------------------------------------------
# Lois normales (stdlib : pas de scipy)
# ---------------------------------------------------------------------------

def norm_cdf(x: float) -> float:
    """Fonction de repartition de la loi normale centree reduite."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p: float) -> float:
    """Quantile de la loi normale centree reduite (inverse de norm_cdf).

    Algorithme d'Acklam, precision ~1e-9 : largement suffisant ici, et sans
    dependance externe.
    """
    if not 0.0 < p < 1.0:
        raise ValueError(f"p doit etre dans ]0,1[, recu {p}")

    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]

    plow, phigh = 0.02425, 1 - 0.02425

    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)

    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# ---------------------------------------------------------------------------
# p-value d'un Sharpe
# ---------------------------------------------------------------------------

def sharpe_pvalue(sharpe: float | None, n_obs: int, periods_per_year: int = 365) -> float | None:
    """p-value unilaterale du test "Sharpe > 0".

    Sous H0 (aucun edge), le Sharpe annualise estime sur n observations suit
    approximativement une loi normale d'ecart-type sqrt(periods_per_year/n).

    Renvoie None si le Sharpe n'est pas mesure ou l'echantillon trop court :
    `None` veut dire NON MESURE, jamais "pas significatif".
    """
    if sharpe is None or n_obs < 2:
        return None
    se = math.sqrt(periods_per_year / n_obs)
    if se <= 0:
        return None
    z = sharpe / se
    return 1.0 - norm_cdf(z)


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

@dataclass
class MultiplicityVerdict:
    """Verdict au niveau CAMPAGNE."""

    n_tested: int
    """Le denominateur. Sans lui, aucun des chiffres ci-dessous n'a de sens."""

    alpha: float
    method: str
    threshold: float
    """Seuil de p-value effectif apres correction."""

    survivors: list[int] = field(default_factory=list)
    """Indices (dans la liste fournie) des lanes qui survivent a la correction."""

    n_survivors: int = 0
    expected_false_positives: float = 0.0
    """Nombre de faux positifs attendus SANS correction. Le chiffre qui fait mal."""

    detail: dict[str, str] = field(default_factory=dict)

    @property
    def all_rejected(self) -> bool:
        return self.n_survivors == 0


def bonferroni(pvalues: Sequence[float | None], alpha: float = 0.05,
               n_tested: int | None = None) -> MultiplicityVerdict:
    """Correction de Bonferroni : seuil = alpha / n.

    Controle le FWER — la probabilite d'accepter AU MOINS un faux positif.
    C'est le bon choix ici : un faux positif ne coute pas "un peu de bruit
    statistique", il part en live avec de l'argent reel.

    `n_tested` permet de passer le VRAI nombre de combinaisons testees, qui peut
    depasser len(pvalues) : les lanes rejetees en amont par les gates ont
    quand meme consomme un essai. Les ignorer serait sous-corriger — exactement
    l'erreur du legacy qui n'ecrivait que ses gagnants.
    """
    n = n_tested if n_tested is not None else len(pvalues)
    if n <= 0:
        raise ValueError("n_tested doit etre > 0")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha doit etre dans ]0,1[, recu {alpha}")

    threshold = alpha / n
    survivors = [i for i, p in enumerate(pvalues) if p is not None and p <= threshold]

    return MultiplicityVerdict(
        n_tested=n,
        alpha=alpha,
        method="bonferroni",
        threshold=threshold,
        survivors=survivors,
        n_survivors=len(survivors),
        expected_false_positives=alpha * n,
        detail={
            "lecture": (
                f"sans correction, {alpha * n:.1f} faux positifs sont attendus "
                f"sur {n} essais au seuil {alpha}"
            )
        },
    )


def benjamini_hochberg(pvalues: Sequence[float | None], alpha: float = 0.05,
                       n_tested: int | None = None) -> MultiplicityVerdict:
    """Procedure de Benjamini-Hochberg : controle le FDR.

    Moins conservateur que Bonferroni : accepte une PROPORTION attendue de faux
    positifs parmi les acceptes (alpha), au lieu d'interdire tout faux positif.

    Utile en phase exploratoire pour ne pas jeter tous les candidats. Ne PAS
    l'utiliser comme critere de passage en live.
    """
    n = n_tested if n_tested is not None else len(pvalues)
    if n <= 0:
        raise ValueError("n_tested doit etre > 0")
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha doit etre dans ]0,1[, recu {alpha}")

    indexed = [(i, p) for i, p in enumerate(pvalues) if p is not None]
    indexed.sort(key=lambda t: t[1])

    # On cherche le plus grand rang k tel que p(k) <= k/n * alpha.
    k_max = 0
    threshold = 0.0
    for rank, (_, p) in enumerate(indexed, start=1):
        if p <= (rank / n) * alpha:
            k_max = rank
            threshold = (rank / n) * alpha

    survivors = sorted(i for i, _ in indexed[:k_max])

    return MultiplicityVerdict(
        n_tested=n,
        alpha=alpha,
        method="benjamini_hochberg",
        threshold=threshold,
        survivors=survivors,
        n_survivors=len(survivors),
        expected_false_positives=alpha * len(survivors),
        detail={
            "lecture": (
                f"parmi les {len(survivors)} acceptes, {alpha:.0%} sont attendus "
                f"faux en moyenne"
            )
        },
    )


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_trials: int,
    n_obs: int,
    variance_of_trial_sharpes: float,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    periods_per_year: int = 365,
) -> float:
    """Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    Repond a la seule question qui compte apres une campagne :

        "Ce Sharpe est-il superieur a ce que le HASARD aurait produit
         de mieux sur n_trials essais ?"

    Renvoie une probabilite dans [0,1]. Interpretation :
      > 0.95  le Sharpe resiste au nombre d'essais
      < 0.95  indistinguable du meilleur tirage chanceux

    `variance_of_trial_sharpes` est la variance des Sharpe de TOUS les essais
    de la campagne (pas seulement les gagnants) : plus la campagne disperse,
    plus le maximum attendu par hasard est eleve.
    """
    if n_trials < 1:
        raise ValueError("n_trials doit etre >= 1")
    if n_obs < 2:
        raise ValueError("n_obs doit etre >= 2")
    if variance_of_trial_sharpes < 0:
        raise ValueError("la variance ne peut pas etre negative")

    # Sharpe maximum attendu par pur hasard sur n_trials essais.
    # Approximation de l'esperance du maximum de n_trials gaussiennes.
    euler = 0.5772156649015329
    sigma = math.sqrt(variance_of_trial_sharpes)

    if n_trials == 1 or sigma == 0.0:
        expected_max = 0.0
    else:
        a = (1 - euler) * norm_ppf(1 - 1.0 / n_trials)
        b = euler * norm_ppf(1 - 1.0 / (n_trials * math.e))
        expected_max = sigma * (a + b)

    # Statistique de test, corrigee des moments d'ordre 3 et 4 : les rendements
    # de trading ne sont pas gaussiens, et ignorer skew/kurtosis surestime la
    # significativite.
    sr = observed_sharpe / math.sqrt(periods_per_year)
    sr_max = expected_max / math.sqrt(periods_per_year)

    denom = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    if denom <= 0:
        return 0.0

    z = (sr - sr_max) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return norm_cdf(z)


@dataclass
class CampaignAudit:
    """Audit statistique d'une campagne entiere."""

    n_tested: int
    n_gate_survivors: int
    n_after_multiplicity: int
    acceptance_rate: float
    expected_by_chance: float
    verdict: str
    detail: dict[str, str] = field(default_factory=dict)

    @property
    def is_suspicious(self) -> bool:
        """True si le nombre de survivants est compatible avec le pur hasard."""
        return self.n_gate_survivors <= self.expected_by_chance


def audit_campaign(
    *,
    n_tested: int,
    sharpes_oos: Sequence[float | None],
    n_obs_per_lane: int,
    alpha: float = 0.05,
    periods_per_year: int = 365,
) -> CampaignAudit:
    """Juge la CAMPAGNE, pas la lane.

    `sharpes_oos` : les Sharpe OOS des lanes ayant passe les gates.
    `n_tested`    : le NOMBRE TOTAL de combinaisons testees, gates comprises.

    C'est la distinction essentielle. Corriger sur le nombre de survivants au
    lieu du nombre d'essais revient a ignorer tous les tickets perdants — le
    biais exact qui a produit "+924 828 USD" dans le legacy.
    """
    if n_tested <= 0:
        raise ValueError("n_tested doit etre > 0")

    measured = [s for s in sharpes_oos if s is not None]
    pvals = [sharpe_pvalue(s, n_obs_per_lane, periods_per_year) for s in sharpes_oos]

    bonf = bonferroni(pvals, alpha=alpha, n_tested=n_tested)

    rate = len(measured) / n_tested
    expected = alpha * n_tested

    if not measured:
        verdict = "AUCUNE LANE MESURABLE"
    elif len(measured) <= expected:
        verdict = "INDISTINGUABLE DU HASARD"
    elif bonf.n_survivors == 0:
        verdict = "AUCUN SURVIVANT APRES CORRECTION"
    else:
        verdict = f"{bonf.n_survivors} CANDIDAT(S) — validation OOS posterieure requise"

    return CampaignAudit(
        n_tested=n_tested,
        n_gate_survivors=len(measured),
        n_after_multiplicity=bonf.n_survivors,
        acceptance_rate=rate,
        expected_by_chance=expected,
        verdict=verdict,
        detail={
            "seuil_bonferroni": f"{bonf.threshold:.3e}",
            "lecture": bonf.detail.get("lecture", ""),
            "rappel": (
                "un survivant n'est pas une strategie validee : c'est un "
                "candidat, a reevaluer sur des donnees posterieures a la campagne"
            ),
        },
    )
