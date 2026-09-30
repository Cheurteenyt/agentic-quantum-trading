#!/usr/bin/env python3
"""Orchestration nocturne : la chaine complete, de la donnee au verdict.

    donnees fraiches -> campagne -> gates -> multiplicite -> candidats -> rapport

C'est le point d'entree unique du pipeline automatise. Il enchaine des modules
qui existent deja et qui sont testes ; il n'ajoute aucune logique de jugement.

POURQUOI CET ORDRE
------------------
Chaque etape retire une facon de se mentir, et l'ordre n'est pas negociable :

  1. gates          jugent UNE lane      (< 100 trades, overfit, couts absents)
  2. multiplicite   juge LA CAMPAGNE     (10 000 essais sur du bruit -> 1231
                                          lanes a Sharpe > 1 : mesure reelle)
  3. candidats      jugent LE TEMPS      (seule une periode OOS posterieure
                                          valide ; aucune stat ne la remplace)

Sauter l'etape 2 industrialise le faux positif. Sauter l'etape 3 fait passer
en live un resultat qui n'a jamais vu de donnee inedite.

MODE PAR DEFAUT : --dry-run. Rien n'est ecrit sans demande explicite.

    python scripts/nightly_campaign.py --check
    python scripts/nightly_campaign.py --run --symbols BTCUSDT --interval 1h
    python scripts/nightly_campaign.py --review          # reevalue les candidats mûrs

Stdlib pure.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.candidates import (  # noqa: E402
    Candidate,
    CandidateRegistry,
)
from backend.services.backtest_v2.multiplicity import audit_campaign  # noqa: E402
from backend.services.backtest_v2.reporting import (  # noqa: E402
    build_report,
    health_flags,
    render_console,
    render_discord,
    render_markdown,
)
from scripts.fetch_klines import detect_gaps, init_db, load_bars, warehouse_stats  # noqa: E402

KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
CANDIDATES_DB = ROOT / "data" / "warehouse" / "candidates.db"
STORE_DB = ROOT / "data" / "warehouse" / "backtest.db"
REPORTS_DIR = ROOT / "reports"

MIN_BARS = 3000
"""En dessous, le walk-forward ne peut pas produire un OOS defendable.
(30/09 : 300 → 3000, aligné sur ce docstring — les 16 séries du lab à
599-1 636 barres produisaient des walk-forwards bruités et coûtaient
~20 % du temps de campagne ; le ciblage --target-bars 3000 des fetches
est la même doctrine.)"""

MAX_BARS_NIGHTLY = 3000
"""La fenêtre glissante du validateur nocturne (30/09, forcée par le
backfill T6) : la campagne juge le RÉGIME RÉCENT — les séries 1m du
backfill profond à 2,67 M bougies auraient explosé la campagne en heures.
L'historique profond 2021→ (la couche ÉTUDE, one-shots) est séparé du
validateur : deux questions, deux outils."""

MATURITY_DAYS = 30
"""Delai minimal avant reevaluation d'un candidat. Evaluer plus tot revient a
reutiliser les donnees de la decouverte — le contraire d'une validation."""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_readiness(klines_db: Path = KLINES_DB) -> dict:
    """Le pipeline peut-il tourner ? Read-only, n'ecrit rien.

    Une campagne lancee sur des donnees trouees produit un resultat faux mais
    credible : c'est la pire des sorties. On refuse plutot que de deviner.
    """
    out: dict = {"ready": False, "series": [], "blockers": []}

    if not klines_db.exists():
        out["blockers"].append(
            f"warehouse absent ({klines_db}) — lancer scripts/fetch_klines.py --fetch"
        )
        return out

    con = init_db(klines_db)
    try:
        stats = warehouse_stats(con)
        series = stats.get("series") or []
        if not series:
            out["blockers"].append("warehouse vide — aucune serie telechargee")
            return out

        for s in series:
            sym, itv = s["symbol"], s["interval"]
            n = s["bars"]
            gaps = detect_gaps(con, sym, itv)
            entry = {"symbol": sym, "interval": itv, "bars": n, "gaps": len(gaps)}

            if n < MIN_BARS:
                entry["usable"] = False
                out["blockers"].append(
                    f"{sym} {itv} : {n} barres / {MIN_BARS} minimum — serie trop courte"
                )
            elif gaps:
                entry["usable"] = False
                out["blockers"].append(
                    f"{sym} {itv} : {len(gaps)} trou(s) — un trou fausse un backtest "
                    f"silencieusement"
                )
            else:
                entry["usable"] = True
            out["series"].append(entry)

        out["ready"] = any(s["usable"] for s in out["series"])
        return out
    finally:
        con.close()


def audit_from_campaign(campaign: dict, n_obs_per_lane: int) -> dict:
    """Applique la correction de multiplicite au resultat d'une campagne.

    Le denominateur passe a `audit_campaign` est le nombre TOTAL de
    combinaisons testees, pas le nombre de survivants : une lane rejetee a
    quand meme consomme un essai. Ne corriger que sur les survivants revient a
    ignorer les tickets perdants.
    """
    sharpes = [s.get("sharpe_oos") for s in campaign.get("survivors", [])]
    a = audit_campaign(
        n_tested=max(1, campaign.get("tested", 0)),
        sharpes_oos=sharpes,
        n_obs_per_lane=n_obs_per_lane,
    )
    return {
        "n_tested": a.n_tested,
        "n_gate_survivors": a.n_gate_survivors,
        "n_after_multiplicity": a.n_after_multiplicity,
        "expected_by_chance": a.expected_by_chance,
        "verdict": a.verdict,
        "detail": a.detail,
    }


def register_survivors(campaign: dict, audit: dict, registry: CandidateRegistry) -> int:
    """Enregistre comme CANDIDATS les lanes ayant survecu a la multiplicite.

    Seules celles-la : une lane qui passe les gates mais tombe a la correction
    n'est pas un candidat, c'est un tirage chanceux.
    """
    if audit.get("n_after_multiplicity", 0) <= 0:
        return 0

    n = 0
    for s in campaign.get("survivors", [])[: audit["n_after_multiplicity"]]:
        sharpe = s.get("sharpe_oos")
        if sharpe is None:
            continue  # non mesure = non candidat
        try:
            registry.register(
                Candidate(
                    identity_key=s["identity"],
                    run_id=campaign["run_id"],
                    discovered_at=_utc(),
                    sharpe_oos_discovery=float(sharpe),
                    n_tested_in_campaign=campaign.get("tested", 0),
                    params=s.get("params", {}),
                )
            )
            n += 1
        except Exception as exc:  # doublon ou identite invalide : visible, pas tu
            print(f"  ! candidat non enregistre ({s['identity']}) : {exc}")
    return n


def write_report(sections, run_id: str, reports_dir: Path = REPORTS_DIR) -> Path:
    """Ecrit le rapport markdown dans reports/, jamais dans docs/.

    Un rapport est une sortie de run, pas de la documentation : c'est la regle
    qui a fait deraper docs/ vers 36 fichiers.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"campaign-{run_id}-{stamp}.md"
    path.write_text(render_markdown(sections), encoding="utf-8")
    return path


def review_candidates(
    registry: CandidateRegistry, maturity_days: float = MATURITY_DAYS
) -> dict:
    """Liste les candidats mûrs pour reevaluation.

    Ne les evalue PAS : la reevaluation exige de rejouer la strategie sur les
    donnees arrivees depuis, ce qui suppose une strategie concrete. Cette
    fonction expose le travail a faire, elle ne le simule pas.
    """
    due = registry.pending(min_age_days=maturity_days)
    return {
        "due": [
            {
                "identity_key": c.identity_key,
                "run_id": c.run_id,
                "discovered_at": c.discovered_at,
                "sharpe_oos_discovery": c.sharpe_oos_discovery,
                "n_tested_in_campaign": c.n_tested_in_campaign,
            }
            for c in due
        ],
        "count": len(due),
        "stats": registry.stats(),
    }


def run_nightly(
    symbols: list[str] | None = None,
    intervals: list[str] | None = None,
    store_path: Path = STORE_DB,
    candidates_db: Path = CANDIDATES_DB,
    reports_dir: Path = REPORTS_DIR,
) -> int:
    """Le maillon manquant : donnees -> campagne -> multiplicite -> candidats.

    Seul mode qui ECRIT (store de backtest, registre de candidats, rapport).
    Une seule correction de multiplicite, GLOBALE sur toutes les strategies et
    toutes les paires : sinon le denominateur ment.
    """
    from backend.services.backtest_v2.engine import CampaignConfig, run_campaign
    from backend.services.backtest_v2.store import BacktestStore
    from backend.services.backtest_v2.strategies import (
        REGISTRY,
        identity_for,
        list_strategies,
    )

    r = check_readiness()
    if not r["ready"]:
        print("=== Campagne refusee : pipeline NON pret ===")
        for b in r["blockers"]:
            print(f"  ! {b}")
        return 1

    wanted = [s for s in r["series"] if s["usable"]]
    if symbols:
        up = {s.upper() for s in symbols}
        wanted = [s for s in wanted if s["symbol"].upper() in up]
    if intervals:
        wanted = [s for s in wanted if s["interval"] in intervals]
    if not wanted:
        print("=== Campagne refusee : aucune serie utilisable dans le scope demande ===")
        return 1

    con = init_db(KLINES_DB)
    try:
        stats = warehouse_stats(con)
        snap_by_key = {
            (s["symbol"], s["interval"]): s.get("snapshot_id")
            or f"unknown-{s['symbol']}-{s['interval']}"
            for s in stats.get("series", [])
        }
        series_bars = []
        for entry in wanted:
            sym, itv = entry["symbol"], entry["interval"]
            bars = load_bars(con, sym, itv)
            if not bars:
                print(f"  ! {sym} {itv} : aucune bougie chargee — skip")
                continue
            if len(bars) > MAX_BARS_NIGHTLY:
                bars = bars[-MAX_BARS_NIGHTLY:]
            series_bars.append(
                (sym, itv, bars, snap_by_key.get((sym, itv), f"unknown-{sym}-{itv}"))
            )
    finally:
        con.close()

    if not series_bars:
        print("=== Campagne refusee : aucune barre chargeable ===")
        return 1

    store_path.parent.mkdir(parents=True, exist_ok=True)
    run_id = f"nightly-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    combined: dict = {
        "run_id": run_id,
        "tested": 0,
        "accepted": 0,
        "rejected": 0,
        "errored": 0,
        "survivors": [],
    }
    min_bars = min(len(b) for _, _, b, _ in series_bars)

    store = BacktestStore(store_path)
    try:
        for sym, itv, bars, snap in series_bars:
            for strat in list_strategies():
                evaluate, ps, name = REGISTRY[strat]
                cfg = CampaignConfig(
                    run_id=f"{strat}-{sym}-{itv}-"
                    f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}",
                    data_snapshot_id=snap,
                )
                print(f"--- {strat} {sym} {itv} ({len(bars)} barres) ---")
                report = run_campaign(
                    store=store,
                    cfg=cfg,
                    bars=bars,
                    param_space=ps,
                    identity_for=identity_for(name, symbol=sym, interval=itv),
                    evaluate=evaluate,
                )
                combined["tested"] += report.tested
                combined["accepted"] += report.accepted
                combined["rejected"] += report.rejected
                combined["errored"] += report.errored
                combined["survivors"].extend(report.survivors)
    finally:
        store.close()

    audit = audit_from_campaign(combined, n_obs_per_lane=max(1, min_bars // 5))

    reg = CandidateRegistry(candidates_db)
    try:
        n = register_survivors(combined, audit, reg)
    finally:
        reg.close()

    sections = build_report(campaign=combined, audit=audit)
    print()
    print(render_console(sections, width=78))
    print("\n=== Audit de multiplicite (GLOBAL) ===")
    print(f"  combinaisons testees : {audit['n_tested']}")
    print(f"  survivants gates     : {audit['n_gate_survivors']}")
    print(f"  apres correction     : {audit['n_after_multiplicity']}")
    print(f"  attendus par hasard  : {audit['expected_by_chance']:.1f}")
    print(f"  VERDICT              : {audit['verdict']}")
    print(f"\n  {n} candidat(s) enregistre(s).")

    path = write_report(sections, run_id, reports_dir)
    print(f"  rapport : {path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Orchestration nocturne du backtest.")
    p.add_argument("--check", action="store_true", help="etat du pipeline (defaut)")
    p.add_argument("--run", action="store_true",
                   help="lance la campagne reelle (SEUL mode qui ecrit)")
    p.add_argument("--symbols", default=None,
                   help="liste sep. par virgules (defaut : toutes les paires)")
    p.add_argument("--interval", default=None,
                   help="liste sep. par virgules (defaut : tous les intervalles)")
    p.add_argument("--store", default=str(STORE_DB))
    p.add_argument("--review", action="store_true", help="candidats mûrs a reevaluer")
    p.add_argument("--maturity-days", type=float, default=MATURITY_DAYS)
    p.add_argument("--discord", action="store_true", help="sortie decoupee Discord")
    args = p.parse_args()

    if args.run:
        syms = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
                if args.symbols else None)
        itvs = ([s.strip() for s in args.interval.split(",") if s.strip()]
                if args.interval else None)
        return run_nightly(symbols=syms, intervals=itvs,
                           store_path=Path(args.store))

    if args.review:
        reg = CandidateRegistry(CANDIDATES_DB)
        try:
            out = review_candidates(reg, args.maturity_days)
            print(f"=== Candidats mûrs (>= {args.maturity_days:g} j) ===")
            print(f"  a reevaluer : {out['count']}")
            for c in out["due"]:
                print(
                    f"    {c['identity_key']}  sharpe_decouverte="
                    f"{c['sharpe_oos_discovery']:.2f}  essais={c['n_tested_in_campaign']}"
                )
            s = out["stats"]
            print(
                f"  registre : {s.get('confirmed', 0)} confirmes / "
                f"{s.get('total', 0)} candidats "
                f"({s.get('confirmation_rate', 0):.1%})"
            )
            if out["count"] == 0:
                print("  Aucun candidat mûr. Le temps est le seul validateur.")
            return 0
        finally:
            reg.close()

    # --check est le defaut : aucune ecriture sans demande explicite.
    r = check_readiness()
    print("=== Etat du pipeline nocturne (lecture seule) ===")
    for s in r["series"]:
        flag = "OK" if s["usable"] else "INUTILISABLE"
        print(
            f"  · {s['symbol']:<10} {s['interval']:<5} {s['bars']:>6} barres  "
            f"{s['gaps']} trou(s)  -> {flag}"
        )
    if r["blockers"]:
        print("\n  Bloqueurs :")
        for b in r["blockers"]:
            print(f"    ! {b}")
    print(
        f"\nRESULTAT : {'pipeline pret' if r['ready'] else 'pipeline NON pret'}"
    )
    return 0 if r["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
