"""Gates de rejet et benchmarks obligatoires.

Traduction executable de docs/03-methodology.md. Aucune dependance externe
(stdlib pure) : ce module est le juge, il ne doit pas pouvoir casser.

Principe : un resultat n'est pas "bon" ou "mauvais", il est REJETE ou
SURVIVANT. Le rejet est la valeur par defaut. Une lane doit prouver qu'elle
merite d'exister, pas l'inverse.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class Gate(str, Enum):
    """Motifs de rejet. Persistes en base : le taux par motif est une metrique."""

    SAMPLE_TOO_SMALL = "sample_too_small"
    SHARPE_TOO_LOW = "sharpe_oos_too_low"
    DRAWDOWN_TOO_DEEP = "drawdown_too_deep"
    OVERFIT = "overfit_oos_is_ratio"
    PARAM_UNSTABLE = "param_instability"
    COSTS_INCOMPLETE = "costs_incomplete"
    MICROSTRUCTURE_UNVALIDATED = "microstructure_unvalidated"
    IDENTITY_INCOMPLETE = "identity_incomplete"
    BENCH_BUY_HOLD = "fails_buy_and_hold"
    BENCH_RANDOM = "indistinguishable_from_random"
    BENCH_MOMENTUM = "fails_momentum_baseline"


@dataclass(frozen=True)
class GateConfig:
    """Seuils. Modifiables, mais TOUT changement doit etre trace en base.

    Les valeurs par defaut viennent de docs/03-methodology.md section 3.
    """

    min_closed_trades: int = 100
    min_sharpe_oos: float = 0.8
    max_drawdown_pct: float = 25.0
    min_oos_is_ratio: float = 0.6
    param_perturbation_pct: float = 10.0
    max_param_degradation: float = 0.5
    random_bench_trials: int = 1000
    random_bench_percentile: float = 95.0
    require_microstructure: bool = False
    """Par defaut NON bloquant. La validation de fillabilite (profondeur de
    carnet, latence) est un vrai garde-fou, mais AUCUNE strategie du projet ne
    la fournit encore. La laisser bloquante par defaut rendrait ce gate
    SYSTEMATIQUEMENT rejetant -> inutile. On l'active explicitement quand une
    strategie implemente une vraie validation."""

    def fingerprint(self) -> str:
        """Empreinte des seuils : deux resultats juges differemment ne se comparent pas."""
        import hashlib
        import json

        payload = json.dumps(self.__dict__, sort_keys=True)
        return hashlib.sha1(payload.encode()).hexdigest()[:12]


@dataclass
class LaneMetrics:
    """Ce qu'un backtest doit produire pour etre jugeable.

    `None` ne veut pas dire zero : il veut dire NON MESURE, et une metrique non
    mesuree est un rejet, jamais un pass par defaut. C'est exactement l'erreur
    du legacy (funding absent traite comme funding nul).
    """

    closed_trades: int | None = None
    sharpe_oos: float | None = None
    max_drawdown_pct: float | None = None
    sharpe_is: float | None = None

    # Les 4 postes de cout — docs/03-methodology.md section 2.3
    fees_usd: float | None = None
    funding_usd: float | None = None
    slippage_usd: float | None = None
    liquidation_risk_checked: bool = False

    # Le mensonge n.4 : jamais sommes
    pnl_realized_usd: float | None = None
    pnl_unrealized_usd: float | None = None

    microstructure_validated: bool = False
    param_sensitivity: float | None = None  # degradation relative sous +/-10 %

    # Rendements OOS, pour les benchmarks
    returns_oos: Sequence[float] = field(default_factory=list)


@dataclass
class GateVerdict:
    passed: bool
    failures: list[Gate]
    detail: dict[str, str]
    config_fingerprint: str

    @property
    def primary_failure(self) -> Gate | None:
        return self.failures[0] if self.failures else None

    def as_row(self) -> dict:
        """Forme persistable : le rejet est une donnee, pas un log jete."""
        return {
            "gate_passed": self.passed,
            "gate_failures": ",".join(g.value for g in self.failures),
            "gate_primary_failure": self.primary_failure.value if self.primary_failure else None,
            "gate_config_fingerprint": self.config_fingerprint,
        }


# ---------------------------------------------------------------- statistiques


def sharpe(returns: Sequence[float], periods_per_year: int = 365) -> float | None:
    """Sharpe annualise. None si l'echantillon ne permet pas de le calculer.

    Le test de variance est RELATIF a l'echelle des rendements : en flottant,
    var([0.01]*50) vaut ~1e-36 et non 0 exactement, ce qui produisait un Sharpe
    de 5.4e16. Un Sharpe astronomique n'est jamais un bon resultat, c'est
    toujours une division par un bruit numerique.
    """
    n = len(returns)
    if n < 2:
        return None
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    scale = max(abs(mean), max((abs(r) for r in returns), default=0.0), 1e-12)
    if var <= (scale * 1e-9) ** 2:
        return None
    return (mean / math.sqrt(var)) * math.sqrt(periods_per_year)


def max_drawdown_pct(equity: Sequence[float]) -> float | None:
    """Drawdown maximal en %, calcule sur une courbe d'equity."""
    if len(equity) < 2:
        return None
    peak = equity[0]
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak * 100.0)
    return worst


def percentile(values: Sequence[float], p: float) -> float:
    """Percentile par interpolation lineaire. Stdlib pure."""
    if not values:
        raise ValueError("percentile sur sequence vide")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


# --------------------------------------------------------------------- gates


def evaluate_gates(
    m: LaneMetrics,
    identity_complete: bool,
    cfg: GateConfig | None = None,
) -> GateVerdict:
    """Applique tous les gates. Ne s'arrete pas au premier echec : on veut
    connaitre TOUS les motifs de rejet, c'est ce qui rend le rapport utile."""
    cfg = cfg or GateConfig()
    fails: list[Gate] = []
    detail: dict[str, str] = {}

    def reject(gate: Gate, msg: str) -> None:
        fails.append(gate)
        detail[gate.value] = msg

    # 0. Identite — sans elle rien n'est comparable (69,7 % du legacy)
    if not identity_complete:
        reject(Gate.IDENTITY_INCOMPLETE, "6 champs d'identite requis, incomplet")

    # 1. Taille d'echantillon — 99,6 % du legacy echouait ici
    if m.closed_trades is None:
        reject(Gate.SAMPLE_TOO_SMALL, "closed_trades non mesure")
    elif m.closed_trades < cfg.min_closed_trades:
        reject(
            Gate.SAMPLE_TOO_SMALL,
            f"{m.closed_trades} trades < {cfg.min_closed_trades} requis",
        )

    # 2. Sharpe OOS
    if m.sharpe_oos is None:
        reject(Gate.SHARPE_TOO_LOW, "sharpe_oos non mesure")
    elif m.sharpe_oos < cfg.min_sharpe_oos:
        reject(Gate.SHARPE_TOO_LOW, f"sharpe OOS {m.sharpe_oos:.2f} < {cfg.min_sharpe_oos}")

    # 3. Drawdown
    if m.max_drawdown_pct is None:
        reject(Gate.DRAWDOWN_TOO_DEEP, "drawdown non mesure")
    elif m.max_drawdown_pct > cfg.max_drawdown_pct:
        reject(
            Gate.DRAWDOWN_TOO_DEEP,
            f"DD {m.max_drawdown_pct:.1f} % > {cfg.max_drawdown_pct} %",
        )

    # 4. Overfit — le gate le plus discriminant
    if m.sharpe_is is None or m.sharpe_oos is None:
        reject(Gate.OVERFIT, "split train/validation absent")
    elif m.sharpe_is <= 0:
        reject(Gate.OVERFIT, f"sharpe IS {m.sharpe_is:.2f} <= 0, ratio indefini")
    else:
        ratio = m.sharpe_oos / m.sharpe_is
        if ratio < cfg.min_oos_is_ratio:
            reject(
                Gate.OVERFIT,
                f"ratio OOS/IS {ratio:.2f} < {cfg.min_oos_is_ratio} (overfit)",
            )

    # 5. Stabilite parametrique
    if m.param_sensitivity is None:
        reject(Gate.PARAM_UNSTABLE, "sensibilite parametrique non testee")
    elif m.param_sensitivity > cfg.max_param_degradation:
        reject(
            Gate.PARAM_UNSTABLE,
            f"degradation {m.param_sensitivity:.0%} sous +/-{cfg.param_perturbation_pct:.0f} %",
        )

    # 6. Cout complet — None = non mesure = rejet, jamais zero implicite
    missing = [
        name
        for name, val in (
            ("fees", m.fees_usd),
            ("funding", m.funding_usd),
            ("slippage", m.slippage_usd),
        )
        if val is None
    ]
    if not m.liquidation_risk_checked:
        missing.append("liquidation")
    if missing:
        reject(Gate.COSTS_INCOMPLETE, "postes de cout manquants: " + ", ".join(missing))

    # 7. Microstructure
    if cfg.require_microstructure and not m.microstructure_validated:
        reject(Gate.MICROSTRUCTURE_UNVALIDATED, "fillabilite non validee")

    return GateVerdict(
        passed=not fails,
        failures=fails,
        detail=detail,
        config_fingerprint=cfg.fingerprint(),
    )


# ---------------------------------------------------------------- benchmarks


@dataclass
class BenchmarkVerdict:
    passed: bool
    failures: list[Gate]
    detail: dict[str, str]


def random_benchmark_percentile(
    strategy_total_return: float,
    pool_returns: Sequence[float],
    n_trades: int,
    cfg: GateConfig | None = None,
    seed: int = 42,
) -> tuple[float, float]:
    """Tire N portefeuilles aleatoires de meme frequence dans le meme pool de
    rendements, renvoie (percentile atteint par la strategie, seuil requis).

    C'est LE benchmark qui repond a "est-ce distinguable du hasard ?".
    Deterministe (seed fixe) : un benchmark non reproductible ne prouve rien.
    """
    cfg = cfg or GateConfig()
    if not pool_returns or n_trades <= 0:
        raise ValueError("pool de rendements vide ou n_trades invalide")

    rng = random.Random(seed)
    pool = list(pool_returns)
    sims: list[float] = []
    for _ in range(cfg.random_bench_trials):
        sims.append(sum(rng.choice(pool) for _ in range(n_trades)))

    beaten = sum(1 for s in sims if strategy_total_return > s)
    return 100.0 * beaten / len(sims), cfg.random_bench_percentile


def evaluate_benchmarks(
    strategy_return: float,
    buy_hold_return: float | None,
    momentum_return: float | None,
    pool_returns: Sequence[float],
    n_trades: int,
    cfg: GateConfig | None = None,
    seed: int = 42,
) -> BenchmarkVerdict:
    """Les 3 benchmarks obligatoires. Tous les rendements doivent etre NETS de couts."""
    cfg = cfg or GateConfig()
    fails: list[Gate] = []
    detail: dict[str, str] = {}

    if buy_hold_return is None:
        fails.append(Gate.BENCH_BUY_HOLD)
        detail[Gate.BENCH_BUY_HOLD.value] = "buy & hold non calcule"
    elif strategy_return <= buy_hold_return:
        fails.append(Gate.BENCH_BUY_HOLD)
        detail[Gate.BENCH_BUY_HOLD.value] = (
            f"strategie {strategy_return:.4f} <= buy&hold {buy_hold_return:.4f}"
        )

    if momentum_return is None:
        fails.append(Gate.BENCH_MOMENTUM)
        detail[Gate.BENCH_MOMENTUM.value] = "baseline momentum non calculee"
    elif strategy_return <= momentum_return:
        fails.append(Gate.BENCH_MOMENTUM)
        detail[Gate.BENCH_MOMENTUM.value] = (
            f"strategie {strategy_return:.4f} <= momentum {momentum_return:.4f}"
        )

    if not pool_returns or n_trades <= 0:
        fails.append(Gate.BENCH_RANDOM)
        detail[Gate.BENCH_RANDOM.value] = "benchmark aleatoire non executable"
    else:
        pct, required = random_benchmark_percentile(
            strategy_return, pool_returns, n_trades, cfg, seed
        )
        if pct < required:
            fails.append(Gate.BENCH_RANDOM)
            detail[Gate.BENCH_RANDOM.value] = (
                f"bat {pct:.1f} % des tirages aleatoires, {required:.0f} % requis"
            )
        else:
            detail["random_percentile"] = f"{pct:.1f}"

    return BenchmarkVerdict(passed=not fails, failures=fails, detail=detail)
