#!/usr/bin/env python3
"""Reevaluation OOS POSTERIEURE des candidats — la seule validation qui compte.

Un candidat decouvert le jour J n'est pas une strategie : c'est une hypothese.
La seule facon honnete de la tester est de la rejouer sur les barres arrivees
APRES J. Ce script fait exactement cela, et rien d'autre :

    candidats mûrs (age > maturity)  ->  barres postérieures à discovered_at
      ->  rejeu de evaluate(params, oos_bars)  ->  Sharpe OOS reel
      ->  registry.confirm(...)  (la decision vit dans candidates.py)

Aucune barre anterieure a `discovered_at` n'entre dans le rejeu : c'est le point
entier de l'exercice. Sans ce filtre, on remesure la fenetre de decouverte et on
se ment.

MODE PAR DEFAUT : --dry-run implicite. Rien n'est ecrit sans --commit.

    python scripts/reevaluate_oos.py                       # dry-run
    python scripts/reevaluate_oos.py --commit
    python scripts/reevaluate_oos.py --maturity-days 45 --symbols BTCUSDT

Stdlib pure.
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.candidates import CandidateRegistry  # noqa: E402
from backend.services.backtest_v2.strategies import REGISTRY  # noqa: E402
from scripts.fetch_klines import init_db, load_bars  # noqa: E402

KLINES_DB = ROOT / "data" / "warehouse" / "klines.db"
CANDIDATES_DB = ROOT / "data" / "warehouse" / "candidates.db"

MATURITY_DAYS = 30.0
"""Delai minimal avant reevaluation. Plus tot = reutilisation des donnees."""

MIN_OOS_BARS = 100
"""En dessous, le Sharpe OOS n'est pas une mesure, c'est un bruit."""

STALE_DAYS = 90.0
"""Un PENDING jamais evaluable apres ce delai est expire, pas conserve."""


# ------------------------------------------------------------------- helpers


def parse_iso_ms(ts: str) -> int:
    """ISO-8601 (tolerant 'Z'/naive) -> timestamp epoch en millisecondes."""
    s = (ts or "").replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def sharpe(returns: Sequence[float]) -> float:
    """Sharpe brut = mean/std. std<=0 ou n<2 -> 0.0 (pas de mesure = pas d'edge).

    Volontairement non annualise : on compare a `sharpe_oos_discovery`, produit
    par la meme convention dans le moteur.
    """
    vals = [float(r) for r in (returns or []) if r is not None]
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / (n - 1)
    if var <= 0.0:
        return 0.0
    sd = math.sqrt(var)
    if sd <= 0.0 or not math.isfinite(sd):
        return 0.0
    out = mean / sd
    return out if math.isfinite(out) else 0.0


def resolve_strategy(identity_key: str, params: dict) -> tuple[str, Any] | tuple[None, None]:
    """Trouve (nom, evaluate) depuis l'identity_key ou les params stockes.

    identity_key canonique = 'SYMBOL|interval|side|trigger|exec|lev' ou
    `trigger` est le nom de la strategie. On tolere aussi params['strategy'].
    """
    candidates: list[str] = []
    parts = (identity_key or "").split("|")
    if len(parts) >= 4:
        candidates.append(parts[3].strip())
    for key in ("strategy", "strategy_name", "trigger", "name"):
        v = (params or {}).get(key)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())
    # Dernier recours : un nom du REGISTRY apparaissant dans l'identity_key.
    for name in REGISTRY:
        if name in (identity_key or ""):
            candidates.append(name)

    for name in candidates:
        entry = REGISTRY.get(name)
        if entry is not None:
            return name, entry[0]
    return None, None


def resolve_market(identity_key: str, params: dict, default_interval: str) -> tuple[str | None, str]:
    """(symbol, interval) depuis l'identity_key, sinon les params."""
    parts = (identity_key or "").split("|")
    symbol = parts[0].strip().upper() if parts and parts[0].strip() else None
    interval = parts[1].strip() if len(parts) >= 2 and parts[1].strip() else ""

    p = params or {}
    if not symbol:
        v = p.get("symbol") or p.get("pair")
        symbol = str(v).strip().upper() if v else None
    if not interval:
        v = p.get("interval") or p.get("timeframe")
        interval = str(v).strip() if v else ""
    return symbol, (interval or default_interval)


def strategy_params(params: dict) -> dict:
    """Params du modele, sans les cles de contexte (marche/identite)."""
    drop = {"symbol", "pair", "interval", "timeframe", "strategy", "strategy_name",
            "trigger", "name", "side", "execution_model"}
    return {k: v for k, v in (params or {}).items() if k not in drop}


# ---------------------------------------------------------------- reevaluation


def reevaluate_one(
    cand,
    con,
    default_interval: str,
    min_oos_bars: int | None = None,
) -> dict:
    """Rejoue UN candidat sur ses barres postérieures. N'ecrit rien.

    Retourne un dict verdict : {'action': 'confirm'|'skip', 'reason', ...}
    """
    min_oos_bars = MIN_OOS_BARS if min_oos_bars is None else int(min_oos_bars)
    out: dict[str, Any] = {
        "identity_key": cand.identity_key,
        "run_id": cand.run_id,
        "discovered_at": cand.discovered_at,
        "sharpe_oos_discovery": cand.sharpe_oos_discovery,
        "action": "skip",
        "reason": "",
        "sharpe_oos": None,
        "n_oos_bars": 0,
        "n_trades": 0,
    }

    name, evaluate = resolve_strategy(cand.identity_key, cand.params)
    if evaluate is None:
        out["reason"] = "strategie introuvable dans REGISTRY (identity_key/params)"
        return out
    out["strategy"] = name

    symbol, interval = resolve_market(cand.identity_key, cand.params, default_interval)
    if not symbol:
        out["reason"] = "symbole introuvable (identity_key/params)"
        return out
    out["symbol"] = symbol
    out["interval"] = interval

    cutoff_ms = parse_iso_ms(cand.discovered_at)
    # start_ts = cutoff + 1 : la barre de la decouverte elle-meme est exclue.
    try:
        oos_bars = load_bars(con, symbol, interval, start_ts=cutoff_ms + 1)
    except Exception as exc:  # interval inconnu, table absente : visible, pas tu
        out["reason"] = f"chargement des barres impossible: {exc}"
        return out

    out["n_oos_bars"] = len(oos_bars)
    if len(oos_bars) < min_oos_bars:
        out["reason"] = (
            f"{len(oos_bars)} barres OOS < {min_oos_bars} minimum — "
            "pas assez de donnees postérieures pour conclure"
        )
        return out

    try:
        ev = evaluate(strategy_params(cand.params), oos_bars)
    except Exception as exc:
        out["reason"] = f"rejeu impossible: {type(exc).__name__}: {exc}"
        return out

    trade_returns = list(getattr(ev, "trade_returns", None) or [])
    bar_returns = list(getattr(ev, "bar_returns_per_bar", None) or [])
    series = trade_returns if len(trade_returns) >= 2 else bar_returns
    s = sharpe(series)

    n_trades = int(getattr(ev, "closed_trades", 0) or 0) or len(trade_returns)
    out["sharpe_oos"] = s
    out["n_trades"] = n_trades
    out["source"] = "trade_returns" if series is trade_returns else "bar_returns_per_bar"

    threshold = 0.5 * float(cand.sharpe_oos_discovery)
    out["threshold"] = threshold
    out["action"] = "confirm"  # on soumet TOUJOURS la mesure au registre :
    # la decision (confirmed/rejected) appartient a CandidateRegistry.confirm().
    out["reason"] = (
        f"mesure OOS reelle sharpe={s:.4g} (seuil degradation {threshold:.4g}), "
        f"{n_trades} trades sur {len(oos_bars)} barres"
    )
    return out


def run(
    maturity_days: float,
    interval: str,
    symbols: list[str] | None,
    commit: bool,
    klines_db: Path = KLINES_DB,
    candidates_db: Path = CANDIDATES_DB,
) -> dict:
    reg = CandidateRegistry(candidates_db)
    con = None
    results: list[dict] = []
    confirmed = rejected = skipped = 0
    expired = 0
    try:
        due = reg.pending(min_age_days=maturity_days)
        if symbols:
            wanted = {s.strip().upper() for s in symbols if s.strip()}
            due = [
                c for c in due
                if (resolve_market(c.identity_key, c.params, interval)[0] or "") in wanted
            ]

        if due:
            if not klines_db.exists():
                raise SystemExit(
                    f"warehouse absent ({klines_db}) — lancer scripts/fetch_klines.py --fetch"
                )
            con = init_db(klines_db)

        for cand in due:
            verdict = reevaluate_one(cand, con, interval)
            if verdict["action"] == "confirm":
                if commit:
                    status = reg.confirm(
                        cand.identity_key,
                        cand.run_id,
                        forward_sharpe=verdict["sharpe_oos"],
                        forward_trades=verdict["n_trades"],
                    )
                    verdict["status"] = status
                    if status == "confirmed":
                        confirmed += 1
                    else:
                        rejected += 1
                else:
                    # Prevision locale, sans ecriture : la regle reelle reste
                    # celle de CandidateRegistry._decide.
                    would, why = CandidateRegistry._decide(
                        verdict["sharpe_oos"],
                        verdict["n_trades"],
                        cand.sharpe_oos_discovery,
                    )
                    verdict["status"] = f"(dry-run) {would}"
                    verdict["reason"] = why
                    if would == "confirmed":
                        confirmed += 1
                    else:
                        rejected += 1
            else:
                skipped += 1
                verdict["status"] = "(inchange) pending"
            results.append(verdict)

        if commit:
            expired = reg.expire_stale(max_age_days=STALE_DAYS)

        return {
            "due": len(due),
            "confirmed": confirmed,
            "rejected": rejected,
            "skipped": skipped,
            "expired": expired,
            "commit": commit,
            "results": results,
            "stats": reg.stats(),
        }
    finally:
        if con is not None:
            con.close()
        reg.close()


# ---------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    global MIN_OOS_BARS  # noqa: PLW0603 — borne unique, pilotee par la CLI
    p = argparse.ArgumentParser(
        description="Reevalue les candidats mûrs sur les barres POSTERIEURES a leur decouverte."
    )
    p.add_argument("--maturity-days", type=float, default=MATURITY_DAYS,
                   help=f"age minimal d'un candidat pour etre reevalue (defaut {MATURITY_DAYS:g})")
    p.add_argument("--symbols", type=str, default="",
                   help="filtre CSV, ex: BTCUSDT,ETHUSDT (defaut: tous)")
    p.add_argument("--interval", type=str, default="1h",
                   help="interval par defaut si absent de l'identite (defaut 1h)")
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="n'ecrit rien (DEFAUT)")
    p.add_argument("--commit", action="store_true",
                   help="applique reellement les decisions au registre")
    p.add_argument("--min-oos-bars", type=int, default=MIN_OOS_BARS,
                   help=f"barres OOS minimales pour conclure (defaut {MIN_OOS_BARS})")
    args = p.parse_args(argv)

    commit = bool(args.commit)
    symbols = [s for s in (args.symbols or "").split(",") if s.strip()]

    MIN_OOS_BARS = max(2, int(args.min_oos_bars))

    out = run(
        maturity_days=float(args.maturity_days),
        interval=args.interval,
        symbols=symbols or None,
        commit=commit,
    )

    mode = "COMMIT (ecriture)" if commit else "DRY-RUN (aucune ecriture)"
    print(f"=== Reevaluation OOS posterieure — {mode} ===")
    print(f"  maturite    : > {args.maturity_days:g} jours")
    print(f"  filtre      : {','.join(symbols) if symbols else 'tous symboles'}")
    print(f"  candidats dus : {out['due']}")

    for r in out["results"]:
        print(
            f"    - {r['identity_key']}\n"
            f"        decouvert {r['discovered_at']}  sharpe_decouverte="
            f"{r['sharpe_oos_discovery']:.4g}\n"
            f"        barres OOS={r['n_oos_bars']}  sharpe_oos="
            + (f"{r['sharpe_oos']:.4g}" if r["sharpe_oos"] is not None else "n/a")
            + f"  trades={r['n_trades']}\n"
            f"        -> {r['status']} : {r['reason']}"
        )

    if out["due"] == 0:
        print("  Aucun candidat mûr. Le temps est le seul validateur.")

    print(
        f"\n  RESUME : {out['due']} dus | {out['confirmed']} confirmes | "
        f"{out['rejected']} rejetes | {out['skipped']} non mesurables | "
        f"{out['expired']} expires"
    )
    s = out["stats"]
    print(
        f"  REGISTRE : pending={s.get('pending', 0)} confirmed={s.get('confirmed', 0)} "
        f"rejected={s.get('rejected', 0)} expired={s.get('expired', 0)} "
        f"total={s.get('total', 0)} taux={s.get('confirmation_rate', 0.0):.1%}"
    )
    if not commit:
        print("  (dry-run : rien n'a ete ecrit. Utiliser --commit pour appliquer.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
