"""Le moteur — la boucle qui teste et qui ECRIT TOUT.

C'est ici que le biais de survivance est rendu impossible. Le pipeline legacy
testait 1 117 620 combinaisons et n'en ecrivait que 105 357 : uniquement les
gagnantes. Resultat affiche : 100 % de lanes rentables, +924 828 USD, aucune
information exploitable.

`run_campaign()` appelle `store.record()` sur CHAQUE combinaison evaluee. Le
rejet n'est pas une exception dans le flux : c'est le flux normal. Une
combinaison qui echoue produit une ligne en base, avec son motif.

Le moteur ne connait aucune strategie. Il recoit une fonction d'evaluation et
un espace de parametres, et il se charge de :
  - construire l'identite de lane (refus si incomplete)
  - lancer le walk-forward (sharpe IS/OOS, sensibilite parametrique)
  - agreger les 4 postes de cout
  - comparer aux 3 benchmarks
  - soumettre aux gates
  - tout persister, gagnants comme perdants

Stdlib pure.
"""
from __future__ import annotations

import itertools
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Sequence

from .baselines import Bar, bar_returns, compare_to_baselines, compounded_total_return
from .costs import CostBreakdown
from .gates import (
    BenchmarkVerdict,
    Gate,
    GateConfig,
    GateVerdict,
    LaneMetrics,
    bars_per_year,
    evaluate_gates,
    max_drawdown_pct,
)
from .store import BacktestStore, IdentityError, LaneIdentity
from .walkforward import WalkForwardConfig, run_walkforward


@dataclass
class StrategyEval:
    """Ce qu'une fonction de strategie doit renvoyer pour une combinaison.

    Le moteur ne calcule pas les rendements : c'est le role de la strategie.
    Il calcule tout le reste, et il juge.
    """

    bar_returns_per_bar: Sequence[float]
    """Rendement par barre de la strategie (0.0 quand hors position)."""

    closed_trades: int
    trade_returns: Sequence[float]
    """Rendement net par trade cloture — sert au benchmark aleatoire."""

    avg_holding_bars: int
    costs: CostBreakdown
    microstructure_validated: bool = False
    equity_curve: Sequence[float] | None = None
    blob: dict[str, Any] | None = None


@dataclass
class CampaignConfig:
    run_id: str
    data_snapshot_id: str
    """Provenance des donnees. Sans elle un run n'est pas reproductible."""

    gate_config: GateConfig = field(default_factory=GateConfig)
    walkforward_config: WalkForwardConfig = field(default_factory=WalkForwardConfig)
    fees_bps_round_trip: float = 8.0
    benchmark_seed: int = 42
    stop_on_error: bool = False
    """False : une combinaison qui plante est enregistree en erreur, la campagne
    continue. Une campagne nocturne ne doit pas mourir sur un cas limite."""


@dataclass
class CampaignReport:
    run_id: str
    tested: int = 0
    accepted: int = 0
    rejected: int = 0
    errored: int = 0
    rejection_profile: dict[str, int] = field(default_factory=dict)
    survivors: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    @property
    def acceptance_rate(self) -> float:
        """Le denominateur fait partie du resultat. Un taux d'acceptation eleve
        est un signal d'alarme, pas une reussite : le legacy acceptait 9,43 %
        et produisait 100 % de gagnants apparents."""
        return (self.accepted / self.tested) if self.tested else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tested": self.tested,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "errored": self.errored,
            "acceptance_rate": round(self.acceptance_rate, 6),
            "rejection_profile": dict(self.rejection_profile),
            "survivors": self.survivors,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def expand_grid(space: dict[str, Sequence[Any]]) -> Iterator[dict[str, Any]]:
    """Produit cartesien deterministe de l'espace de parametres.

    Ordre stable (cle triee) : deux campagnes identiques testent les
    combinaisons dans le meme ordre, donc produisent le meme rapport.
    """
    if not space:
        yield {}
        return
    keys = sorted(space)
    for combo in itertools.product(*(space[k] for k in keys)):
        yield dict(zip(keys, combo))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _benchmarks_summary(detail: dict[str, Any]) -> dict[str, Any]:
    """Reduit la sortie de compare_to_baselines a des valeurs persistables.

    `compare_to_baselines` renvoie des BaselineResult complets (avec la liste
    des trades). On ne stocke que les chiffres qui font foi : le detail des
    trades du benchmark est reproductible a partir du seed, donc l'archiver
    serait du volume mort — exactement l'erreur des 442 Mo de CSV legacy.
    """
    out: dict[str, Any] = {}
    for k, v in detail.items():
        if isinstance(v, (int, float, bool, str)) or v is None:
            out[k] = v
        elif hasattr(v, "total_return"):
            out[k] = {
                "total_return": v.total_return,
                "n_trades": getattr(v, "n_trades", None),
                "win_rate": getattr(v, "win_rate", None),
            }
        else:
            out[k] = str(v)
    return out


def evaluate_one(
    identity: LaneIdentity,
    ev: StrategyEval,
    bars: Sequence[Bar],
    cfg: CampaignConfig,
    param_sensitivity: float | None = None,
) -> tuple[LaneMetrics, GateVerdict, BenchmarkVerdict | None, dict[str, Any]]:
    """Juge UNE combinaison. Ne persiste rien : c'est run_campaign qui ecrit."""
    # FIX lot1 (F1) : la frequence des barres pilote l'annualisation du
    # Sharpe — 1h = 8760 barres/an, pas 365.
    dt_ms = (bars[1].ts - bars[0].ts) if len(bars) >= 2 else 0.0
    wf = run_walkforward(
        ev.bar_returns_per_bar, cfg.walkforward_config,
        periods_per_year=bars_per_year(dt_ms) if dt_ms > 0 else 365)

    dd = (
        max_drawdown_pct(ev.equity_curve)
        if ev.equity_curve
        else None
    )

    cost_metrics = ev.costs.as_metrics()
    metrics = LaneMetrics(
        closed_trades=ev.closed_trades,
        sharpe_is=wf.sharpe_is,
        sharpe_oos=wf.sharpe_oos,
        max_drawdown_pct=dd,
        param_sensitivity=param_sensitivity,
        fees_usd=cost_metrics["fees_usd"],
        funding_usd=cost_metrics["funding_usd"],
        slippage_usd=cost_metrics["slippage_usd"],
        liquidation_risk_checked=cost_metrics["liquidation_checked"],
        microstructure_validated=ev.microstructure_validated,
        returns_oos=[r for seg in wf.test_returns for r in seg],
    )

    gate = evaluate_gates(metrics, identity_complete=True, cfg=cfg.gate_config)

    # Les benchmarks coutent cher (1000 tirages). On ne les lance que si la
    # lane a survecu aux gates : inutile de benchmarker une lane a 19 trades.
    bench: BenchmarkVerdict | None = None
    bench_detail: dict[str, Any] = {}
    if gate.passed:
        # FIX lot2 (F14) : la MEME algebre que les benchmarks — compose, pas
        # somme (sommer des pourcentages surestime les series gagnantes).
        strategy_return = compounded_total_return(ev.trade_returns)
        cmp_out = compare_to_baselines(
            strategy_return=strategy_return,
            bars=bars,
            n_trades=max(1, ev.closed_trades),
            avg_holding_bars=max(1, ev.avg_holding_bars),
            fees_bps_round_trip=cfg.fees_bps_round_trip,
            seed=cfg.benchmark_seed,
        )
        fails: list[Gate] = []
        if not cmp_out.get("beats_buy_and_hold"):
            fails.append(Gate.BENCH_BUY_HOLD)
        if not cmp_out.get("beats_momentum"):
            fails.append(Gate.BENCH_MOMENTUM)
        if not cmp_out.get("beats_random_95"):
            fails.append(Gate.BENCH_RANDOM)
        bench = BenchmarkVerdict(
            passed=not fails,
            failures=fails,
            detail={k: str(v) for k, v in cmp_out.items()},
        )
        bench_detail = cmp_out

    extra = {
        "walkforward": {
            "sharpe_is": wf.sharpe_is,
            "sharpe_oos": wf.sharpe_oos,
            "oos_is_ratio": wf.oos_is_ratio,
            "degradation_std": wf.degradation_std,
            "fingerprint": wf.config_fingerprint,
        },
        "costs_missing": list(ev.costs.missing),
        "costs_warnings": list(ev.costs.warnings),
        "benchmarks": _benchmarks_summary(bench_detail),
    }
    return metrics, gate, bench, extra


def run_campaign(
    *,
    store: BacktestStore,
    cfg: CampaignConfig,
    bars: Sequence[Bar],
    param_space: dict[str, Sequence[Any]],
    identity_for: Callable[[dict[str, Any]], LaneIdentity],
    evaluate: Callable[[dict[str, Any], Sequence[Bar]], StrategyEval],
    sensitivity_for: Callable[[dict[str, Any]], float | None] | None = None,
) -> CampaignReport:
    """Teste tout l'espace de parametres et ECRIT CHAQUE RESULTAT.

    `evaluate` recoit (params, bars) et renvoie un StrategyEval. S'il leve,
    la combinaison est comptee en erreur et la campagne continue (sauf
    stop_on_error) : une campagne nocturne ne doit pas mourir sur un cas limite,
    mais l'erreur doit rester visible dans le rapport.
    """
    report = CampaignReport(run_id=cfg.run_id, started_at=_utc())

    store.start_run(
        run_id=cfg.run_id,
        gate_config=dict(cfg.gate_config.__dict__),
        gate_fingerprint=cfg.gate_config.fingerprint(),
        data_snapshot_id=cfg.data_snapshot_id,
        notes=f"walkforward={cfg.walkforward_config.fingerprint()}",
    )

    for params in expand_grid(param_space):
        report.tested += 1

        try:
            identity = identity_for(params)
        except IdentityError as exc:
            # Une identite incomplete ne peut pas etre persistee (contrainte
            # SQL). On la compte comme erreur plutot que de la maquiller.
            report.errored += 1
            report.errors.append(f"{params}: identite refusee: {exc}")
            report.rejection_profile[Gate.IDENTITY_INCOMPLETE.value] = (
                report.rejection_profile.get(Gate.IDENTITY_INCOMPLETE.value, 0) + 1
            )
            if cfg.stop_on_error:
                raise
            continue

        try:
            ev = evaluate(params, bars)
            sens = sensitivity_for(params) if sensitivity_for else None
            metrics, gate, bench, extra = evaluate_one(
                identity, ev, bars, cfg, param_sensitivity=sens
            )
        except Exception as exc:  # noqa: BLE001 - on veut la trace, pas un silence
            report.errored += 1
            report.errors.append(f"{identity.key}: {type(exc).__name__}: {exc}")
            if cfg.stop_on_error:
                raise
            continue

        blob = {"params": params, **extra}
        if ev.blob:
            blob["strategy"] = ev.blob

        store.record(
            run_id=cfg.run_id,
            identity=identity,
            metrics={
                "closed_trades": metrics.closed_trades,
                "sharpe_is": metrics.sharpe_is,
                "sharpe_oos": metrics.sharpe_oos,
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "param_sensitivity": metrics.param_sensitivity,
                "fees_usd": metrics.fees_usd,
                "funding_usd": metrics.funding_usd,
                "slippage_usd": metrics.slippage_usd,
                "liquidation_checked": metrics.liquidation_risk_checked,
                "microstructure_validated": metrics.microstructure_validated,
            },
            gate=gate,
            bench=bench,
            blob=blob,
        )

        survived = gate.passed and bench is not None and bench.passed
        if survived:
            report.accepted += 1
            report.survivors.append(
                {
                    "identity": identity.key,
                    "sharpe_oos": metrics.sharpe_oos,
                    "oos_is_ratio": extra["walkforward"]["oos_is_ratio"],
                    "closed_trades": metrics.closed_trades,
                    "params": params,
                }
            )
        else:
            report.rejected += 1
            motifs = list(gate.failures) + (list(bench.failures) if bench else [])
            for g in motifs:
                report.rejection_profile[g.value] = (
                    report.rejection_profile.get(g.value, 0) + 1
                )

    counts = store.finish_run(cfg.run_id)
    report.finished_at = _utc()

    # Coherence : le store est la source de verite, le compteur en memoire
    # ne doit jamais diverger. Une divergence signale un bug de persistance.
    if counts["tested"] + report.errored != report.tested:
        report.errors.append(
            f"INCOHERENCE: store={counts['tested']} + erreurs={report.errored} "
            f"!= testees={report.tested}"
        )

    return report


def format_report(report: CampaignReport, top: int = 10) -> str:
    """Rapport console. Ne remonte QUE les survivants, mais toujours avec le
    denominateur : un chiffre sans son denominateur n'est pas publiable."""
    lines = [
        "=" * 62,
        f"CAMPAGNE {report.run_id}",
        "=" * 62,
        f"  testees   : {report.tested}",
        f"  acceptees : {report.accepted}",
        f"  rejetees  : {report.rejected}",
        f"  erreurs   : {report.errored}",
        f"  taux      : {report.acceptance_rate:.3%}",
    ]

    if report.rejection_profile:
        lines.append("")
        lines.append("  Motifs de rejet :")
        for motif, n in sorted(report.rejection_profile.items(), key=lambda x: -x[1]):
            lines.append(f"    {motif:<32} {n:>6}")

    lines.append("")
    if report.survivors:
        lines.append(f"  SURVIVANTS ({len(report.survivors)}) :")
        for s in report.survivors[:top]:
            lines.append(
                f"    {s['identity']:<48} sharpe_oos={s['sharpe_oos']:.2f} "
                f"ratio={s['oos_is_ratio']:.2f} trades={s['closed_trades']}"
            )
    else:
        lines.append("  AUCUN SURVIVANT.")
        lines.append("  Ce n'est pas un echec de la campagne : c'est son resultat.")

    if report.errors:
        lines.append("")
        lines.append(f"  Erreurs ({len(report.errors)}, 5 premieres) :")
        for e in report.errors[:5]:
            lines.append(f"    {e}")

    lines.append("=" * 62)
    return "\n".join(lines)
