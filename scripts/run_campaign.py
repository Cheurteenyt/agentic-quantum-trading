#!/usr/bin/env python3
"""Lance une campagne de backtest REELLE sur les donnees du warehouse.

    python scripts/run_campaign.py --strategy all --check
    python scripts/run_campaign.py --strategy momentum
    python scripts/run_campaign.py --strategy all --symbols BTCUSDT,ETHUSDT

Branche de vraies strategies sur `engine.run_campaign`. Toute la chaine de
defense est deja testee ; ici on l'orchestre.

DEUX GARDES AJOUTEES (lecons de la premiere campagne reelle du 2026-08-09) :

1. REFUS SOUS-ECHANTILLONNE. La premiere campagne a tourne sur 500 bougies et
   produit 11-38 trades/lane, donc le gate sample_too_small tombait a 100 % —
   pas parce que les strategies etaient mauvaises, mais parce que les donnees
   etaient trop courtes pour le walk-forward 5 folds. `check_readiness` calcule
   le nombre de trades *attendu* par lane et refuse poliment si < min_closed_trades.

2. MULTIPLICITE GLOBALE. `run_campaign` juge une strategie a la fois (run_id
   par strategie). Si on ne retenait que le meilleur survivant global, on
   oublierait les 2 autres strategies dans le denominateur -> re-selection
   bias, EXACTEMENT le piege du legacy. `_run_all` agrege donc tous les
   survivants de toutes les strategies et applique UNE seule correction de
   multiplicite sur le nombre TOTAL de combinaisons testees.

Le defaut est securise : --check ne lance rien.

Stdlib pure.
"""
from __future__ import annotations

import argparse
import itertools
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.candidates import CandidateRegistry  # noqa: E402
from backend.services.backtest_v2.engine import (  # noqa: E402
    CampaignConfig,
    run_campaign,
)
from backend.services.backtest_v2.multiplicity import audit_campaign  # noqa: E402
from backend.services.backtest_v2.reporting import (  # noqa: E402
    build_report,
    render_console,
)
from backend.services.backtest_v2.strategies import (  # noqa: E402
    REGISTRY,
    identity_for,
    list_strategies,
)
from scripts.fetch_klines import (  # noqa: E402
    init_db,
    load_bars,
    warehouse_stats,
)

KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
CANDIDATES_DB = ROOT / "data" / "warehouse" / "candidates.db"
REPORTS_DIR = ROOT / "reports"
MIN_TRADES_SANE = 100  # seuil du gate sample_too_small par defaut


def _pilot_trades(symbols: list[str], interval: str) -> int | None:
    """Nombre de trades REEL d'une lane pilote (1ere combo de chaque strategie).

    Au lieu d'estimer, on mesure : on evalue les strategies sur les barres et
    on prend le MAX de trades entre elles. C'est la vraie attente pour le gate
    sample_too_small. Retourne None si aucune donnee.
    """
    if not KLINES_DB.exists():
        return None
    con = init_db(KLINES_DB)
    try:
        bars = load_bars(con, symbols[0], interval) if symbols else []
    finally:
        con.close()
    if not bars:
        return None

    best = 0
    for name in list_strategies():
        ev, ps, _ = REGISTRY[name]
        import itertools
        first = next(itertools.product(*(ps[k] for k in sorted(ps))))
        params = dict(zip(sorted(ps), first))
        try:
            e = ev(params, bars)
            best = max(best, e.closed_trades or 0)
        except Exception:
            # Une lane pilote qui plante n'invalide pas la preparedness ;
            # on l'ignore et on garde les autres.
            continue
    return best


def _combo_count(param_space: dict) -> int:
    n = 1
    for v in param_space.values():
        n *= len(v)
    return n


def check_readiness(symbols: list[str], interval: str,
                    min_trades: int = MIN_TRADES_SANE) -> dict:
    """Refuse poliment une campagne qui ne peut pas produire de verdict sane.

    Estime le nombre de trades *attendu* par lane a partir de la longueur de la
    serie et du nombre de folds du walk-forward (defaut 5). Si meme la lane la
    plus active ne depasse pas `min_trades`, la campagne ne fera que remplir
    la base de rejets sample_too_small — inutile et couteux.
    """
    out = {"ready": False, "series": [], "blockers": [],
           "n_folds": 5, "min_trades": min_trades}

    if not KLINES_DB.exists():
        out["blockers"].append(f"warehouse absent ({KLINES_DB})")
        return out

    from backend.services.backtest_v2.walkforward import WalkForwardConfig
    n_folds = WalkForwardConfig().n_folds
    out["n_folds"] = n_folds

    con = init_db(KLINES_DB)
    try:
        stats = warehouse_stats(con)
        # Mesure REELLE d'une lane pilote : on evalua la premiere combo de
        # chaque strategie sur les barres et on compte ses trades. Estimation
        # bien plus fidele qu'une borne theorique (les strategies ne tradeant
        # qu'aux croisements, pas a chaque barre).
        pilot_trades = _pilot_trades(symbols, interval)
        for s in stats.get("series", []):
            sym, itv = s["symbol"], s["interval"]
            if sym not in symbols or itv != interval:
                continue
            n_bars = s["bars"]
            # max_theo est une borne haute (trade a chaque barre test) ; la
            # mesure pilote est la vraie attente. On garde la plus prudente.
            max_theo_trades = n_bars // n_folds
            entry = {"symbol": sym, "interval": itv, "bars": n_bars,
                     "max_theo_trades": max_theo_trades,
                     "pilot_trades": pilot_trades, "gaps": s.get("gaps", 0)}
            if pilot_trades is not None and pilot_trades < min_trades:
                entry["usable"] = False
                out["blockers"].append(
                    f"{sym} {itv}: lane pilote = {pilot_trades} trades "
                    f"< {min_trades} requis. Les strategies ne tradeant qu'aux "
                    f"croisements, 500 barres ne suffisent pas au walk-forward "
                    f"{n_folds} folds. Allonge l'historique (fetch_klines --fetch-range)."
                )
            elif s.get("gaps"):
                entry["usable"] = False
                out["blockers"].append(f"{sym} {itv}: {s['gaps']} trou(s)")
            else:
                entry["usable"] = True
            out["series"].append(entry)

        if not out["series"]:
            out["blockers"].append(
                f"aucune serie pour {','.join(symbols)} {interval} dans le warehouse"
            )
        out["ready"] = any(s["usable"] for s in out["series"])
        return out
    finally:
        con.close()


def _run_one(strategy: str, symbols: list[str], interval: str,
             max_combos: int | None, store_path: Path) -> dict:
    """Lance UNE campagne strategie sur TOUTES les paires. Renvoie un
    agregat {tested, accepted, rejected, errored, survivors} sur l'ensemble
    des symboles. La correction de multiplicite globale se fait dans
    _global_audit, qui lit deja tous les rapports.
    """
    from backend.services.backtest_v2.store import BacktestStore  # local import

    evaluate, ps, strat_name = REGISTRY[strategy]
    total = _combo_count(ps)

    chosen_space = None
    if max_combos is not None and total > max_combos:
        print(f"  ! {strategy}: {total} combinaisons > limite {max_combos} "
              f"(--max-combos). Troncature representative.")
        keys = sorted(ps)
        step = max(1, total // max_combos)
        grouped: dict[str, list] = {}
        for combo in itertools.islice(
            (dict(zip(keys, c)) for c in itertools.product(*(ps[k] for k in keys))),
            0, None, step):
            for k, v in combo.items():
                grouped.setdefault(k, [])
                if v not in grouped[k]:
                    grouped[k].append(v)
        chosen_space = grouped

    # Charge les barres de chaque paire (provenance par paire).
    con_klines = init_db(KLINES_DB)
    try:
        all_bars = []
        for sym in symbols:
            b = load_bars(con_klines, sym, interval)
            if not b:
                print(f"  ! {sym} {interval}: aucune bougie — skip")
                continue
            snap = warehouse_stats(con_klines)
            sid = next(
                (s["snapshot_id"] for s in snap.get("series", [])
                 if s["symbol"] == sym and s["interval"] == interval),
                f"unknown-{sym}-{interval}",
            )
            all_bars.append((sym, b, sid))
    finally:
        con_klines.close()

    if not all_bars:
        return {"run_id": "n/a", "tested": 0, "accepted": 0,
                "rejected": 0, "errored": 0, "survivors": []}

    # Une seule base de resultats pour toutes les paires de la strategie.
    store = BacktestStore(store_path)
    try:
        agg = {"run_id": f"{strategy}-multi-{interval}", "tested": 0,
               "accepted": 0, "rejected": 0, "errored": 0, "survivors": []}
        for sym, bars, snap in all_bars:
            idfn = identity_for(strat_name, symbol=sym, interval=interval)
            run_id = f"{strategy}-{sym}-{interval}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
            cfg = CampaignConfig(run_id=run_id, data_snapshot_id=snap)
            report = run_campaign(
                store=store,
                cfg=cfg,
                bars=bars,
                param_space=chosen_space if chosen_space is not None else ps,
                identity_for=idfn,
                evaluate=evaluate,
                sensitivity_for=None,
            )
            agg["tested"] += report.tested
            agg["accepted"] += report.accepted
            agg["rejected"] += report.rejected
            agg["errored"] += report.errored
            agg["survivors"].extend(report.survivors)
        return agg
    finally:
        store.close()


def _run_all(selected: list[str], symbols: list[str], interval: str,
             max_combos: int | None, store_path: Path) -> list[dict]:
    """Lance toutes les strategies et agrege pour UNE correction globale."""
    reports = []
    for strat in selected:
        print(f"\n--- {strat} ---")
        rep = _run_one(strat, symbols, interval, max_combos, store_path)
        print(render_console(build_report(campaign=rep), width=78))
        reports.append((strat, rep))
    return reports


def _global_audit(reports: list[tuple[str, dict]]) -> dict:
    """UNE seule correction de multiplicite sur TOUTES les strategies.

    C'est le denominateur qui compte : 800 combinaisons testees, pas 256 par
    strategie. Sinon on re-selectionne le meilleur survivant global en
    oubliant les strategies qui n'ont rien produit -> biais du legacy.
    """
    total_tested = sum(r["tested"] for _, r in reports)
    all_sharpes = []
    for _, r in reports:
        for s in r.get("survivors", []):
            all_sharpes.append(s.get("sharpe_oos"))
    # n_obs par lane : on ne le connait pas ici, on utilise une borne prudente
    # (longueur de serie / folds). L'audit est robuste a une estimation ; c'est
    # un seuil, pas une mesure precise.
    n_obs = 500 // 5  # par defaut ; sur-évalué = correction plus severe = safe
    a = audit_campaign(
        n_tested=max(1, total_tested),
        sharpes_oos=all_sharpes,
        n_obs_per_lane=n_obs,
    )
    return {
        "n_tested": a.n_tested,
        "n_gate_survivors": a.n_gate_survivors,
        "n_after_multiplicity": a.n_after_multiplicity,
        "expected_by_chance": a.expected_by_chance,
        "verdict": a.verdict,
        "detail": a.detail,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Campagne de backtest sur donnees reelles.")
    p.add_argument("--strategy", required=True,
                   help=f"une de : {', '.join(list_strategies())}, ou 'all'")
    p.add_argument("--symbols", default="BTCUSDT",
                   help="liste sep. par virgules (defaut BTCUSDT)")
    p.add_argument("--interval", default="1h")
    p.add_argument("--max-combos", type=int, default=None,
                   help="plafonne le nombre de combinaisons par strategie")
    p.add_argument("--store", default=str(ROOT / "data" / "warehouse" / "backtest.db"))
    p.add_argument("--check", action="store_true",
                   help="read-only : rapporte le plan + la faisabilite")
    p.add_argument("--no-report", action="store_true")
    p.add_argument("--register", action="store_true",
                   help="enregistre les candidats (survivants apres multiplicite)")
    args = p.parse_args()

    if args.strategy == "all":
        selected = list_strategies()
    elif args.strategy in REGISTRY:
        selected = [args.strategy]
    else:
        print(f"strategie inconnue : {args.strategy}. Disponibles : "
              f"{', '.join(list_strategies())}")
        return 2

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    # --check : read-only, aucune campagne, mais avec l'analyse de faisabilite.
    if args.check:
        print("=== Plan de campagne (lecture seule) ===")
        for strat in selected:
            n = _combo_count(REGISTRY[strat][1])
            print(f"  · {strat:<16} {n:>5} combinaisons  "
                  f"symboles={','.join(symbols)} {args.interval}")
        tot = sum(_combo_count(REGISTRY[s][1]) for s in selected)
        print(f"\nTotal maximal : {tot} combinaisons sur {len(symbols)} paire(s).")
        rd = check_readiness(symbols, args.interval)
        print("\n=== Faisabilite (refus sous-echantillonne) ===")
        for s in rd["series"]:
            flag = "OK" if s["usable"] else "INUTILISABLE"
            print(f"  · {s['symbol']} {s['interval']} : {s['bars']} barres "
                  f"~{s['max_theo_trades']} trades/lane max -> {flag}")
        if rd["blockers"]:
            print("\n  ! Bloqueurs :")
            for b in rd["blockers"]:
                print(f"    - {b}")
            print("\n  CONSEIL : allonge l'historique avant de conclure "
                  "(fetch_klines.py --fetch-range).")
        else:
            print("\n  Donnees suffisantes pour un verdict significatif.")
        return 0

    # Guarde 1 : on refuse poliment une campagne qui ne peut pas juger.
    rd = check_readiness(symbols, args.interval)
    if not rd["ready"]:
        print("=== Campagne refusee : donnees insuffisantes ===")
        for b in rd["blockers"]:
            print(f"  ! {b}")
        print("\nCONSEIL : python scripts/fetch_klines.py --fetch-range BTCUSDT "
              "--target-bars 3000\n         puis relance la campagne.")
        return 1

    store_path = Path(args.store)
    store_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== Campagne(s) : {', '.join(selected)} ===")
    reports = _run_all(selected, symbols, args.interval, args.max_combos, store_path)

    # Guarde 2 : UNE correction de multiplicite globale.
    audit = _global_audit(reports)
    print("\n=== Audit de multiplicite (GLOBAL, toutes strategies) ===")
    print(f"  combinaisons testees : {audit['n_tested']}")
    print(f"  survivants gates     : {audit['n_gate_survivors']}")
    print(f"  apres correction     : {audit['n_after_multiplicity']}")
    print(f"  attendus par hasard  : {audit['expected_by_chance']:.1f}")
    print(f"  VERDICT              : {audit['verdict']}")

    if args.register and audit["n_after_multiplicity"] > 0:
        reg = CandidateRegistry(CANDIDATES_DB)
        try:
            n = 0
            for strat, rep in reports:
                for s in rep.get("survivors", [])[: audit["n_after_multiplicity"]]:
                    sharpe = s.get("sharpe_oos")
                    if sharpe is None:
                        continue
                    from backend.services.backtest_v2.candidates import Candidate
                    try:
                        reg.register(Candidate(
                            identity_key=s["identity"], run_id=rep["run_id"],
                            discovered_at=datetime.now(timezone.utc).isoformat(),
                            sharpe_oos_discovery=float(sharpe),
                            n_tested_in_campaign=audit["n_tested"],
                            params=s.get("params", {}),
                        ))
                        n += 1
                    except Exception as exc:  # doublon ou identite invalide
                        print(f"  ! candidat non enregistre ({s['identity']}) : {exc}")
            print(f"\n  {n} candidat(s) enregistre(s) en vue de reevaluation OOS.")
        finally:
            reg.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
