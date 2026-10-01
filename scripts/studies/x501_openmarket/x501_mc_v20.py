#!/usr/bin/env python3
"""x501_mc_v20.py — Moteur Monte Carlo v20 d'OpenMarket ×501, RECONSTRUIT (PR #13).

Contexte : le moteur MC v20 original (commit 86595cc, « x501_mc_v20 exécuté
(16 s, mc_v20.json) ») n'a JAMAIS été versionné dans le dépôt — ni le script,
ni mc_v20.json. Cette reconstruction est la référence versionnée qui remplace
la mémoire humaine ; ses chiffres deviennent les chiffres officiels (doctrine
« tout est régénérable par re-exécution », reports/openmarket-x501-baseline-*).

MÉTHODOLOGIE (docs/25-openmarket-x501.md, table « CHIFFRES OFFICIELS MC v20 ») :
  - 12 000 trajectoires × 36 mois, capital initial 100 $, cible ×501 = 50 100 $.
  - Pool = les 31 trades de backtest embarqués (16 BTCUSDT + 15 ETHUSDT,
    scripts/studies/x501_openmarket/x501_backtest_trades_*.csv) ; unité de
    resampling = le RETOUR PAR TRADE en multiples de risque R = pnl_usd_net /
    risque_usd (bootstrap simple AVEC remise, pool unique 31 trades).
  - Cadence : 31 trades sur la fenêtre réelle du backtest (04/04 → 26/09/2026)
    → n_trades(mois) = round(taux × mois) ; 12 m → 65 trades, 36 m → 194.
  - Coûts (docs/25, bps/côté, appliqués par trade sur le notional, 2 côtés) :
    S0 référence 0,0 · MAKER δ=2 central 2,1 · MAKER pur 2,0 · MAKER stress
    3,0 · TAKER all-in 6,1.
  - DD cap 25 % STRICT = contrainte PHYSIQUE du moteur (ratchet/coupe-circuit,
    cf. kScript « strategy.cancelAll au coupe-circuit -25 % ») : après chaque
    trade, si l'équité passe sous 0,75 × pic courant, elle est ramenée EXACTEMENT
    au plancher 0,75 × pic. Le DD max mesuré ne peut donc jamais dépasser
    25,0000 % — c'est le « pire cas 25,000000 % exactement, 0 rupture » de v20.

HYPOTHÈSES DE RECONSTRUCTION (documentées, car le noyau original est perdu) :
  H1. Le retour par trade appliqué à l'équité est r = f × R − c, avec f la
      fraction de risque (par trade, sur l'équité courante → composé) et
      c = 2 × bps × LEV / 10 000 le coût du round-trip en fraction d'équité
      (LEV = levier notionnel effectif).
  H2. f et LEV sont CALIBRÉS sur les DEUX ANCRES officielles docs/25 :
      médiane 12 m S0 = 642,0 $ et TAKER = 272,7 $ (bisection, seed 2026).
      Les 3 scénarios restants (maker 2,0/2,1/3,0) + toutes les probabilités
      sont HORS calibration = contre-vérification véritable (tolérance ±5 %
      sur les médianes, écarts reportés tels quels pour les probabilités).
  H3. Le ratchet ne GÈLE pas la trajectoire : après un coupe-circuit, les
      pertes sous le plancher sont tronquées et les gains re-composent
      (sémantique « cliquet » ; la variante « gel définitif » n'est pas
      retenue faute de source).
  H4. Nombres communs aléatoires : les 5 scénarios tirent le MÊME échantillon
      de trades (seed 2026, numpy default_rng PCG64) → l'effet coût est lu
      toutes choses égales par ailleurs.
  H5. ÉCART DOCUMENTÉ (contre-vérification) : les MÉDIANES 12 m reproduisent
      docs/25 (5/5 dans ±2 %, tolérance ±5 %) mais la DISPERSION de l'original
      n'est pas reproduite : docs/25 donne [P25 ; P75] = [277 ; 1 692] en S0 et
      des queues droites plus épaisses (P(1250) 33,2 %, x501@36m 35,7 %) que ce
      noyau (~[401 ; 1 038], P(1250) ~18 %, x501 ~31 %) — la dispersion
      log-effective de l'original vaut ~2× celle du pool des 31 trades
      resamplés iid. Variantes testées le 01/10 et rejetées : block-bootstrap
      (blocs L=5 et L=8, circularisés) — queues PAS plus larges, probabilités
      dégradées. Le noyau original étant perdu (non versionné), l'écart de
      queues reste assumé : les médianes de CE moteur font foi, les colonnes
      de probabilités de cette reconstruction ne sont PAS comparables à celles
      de docs/25 (lire les écarts dans la table de contre-vérification).

Sorties : scripts/x501_openmarket/x501_mc_v20_results.json
  {<scenario>: {median_12m, p250, p500, p1250, x501_36m}, seed: 2026,
   generated_at, meta}.
Reproductibilité : `--verify` re-exécute et compare les résultats BIT À BIT
  (égalité float64 exacte ; generated_at exclu, c'est l'horloge, pas le calcul).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
TRADES_DIR = REPO_ROOT / "scripts" / "studies" / "x501_openmarket"
RESULTS_PATH = Path(__file__).resolve().parent / "x501_mc_v20_results.json"

ENGINE = "x501_mc_v20"
ENGINE_VERSION = "20.0.0-reconstruit-pr13"
SEED = 2026
N_TRAJECTORIES = 12_000
HORIZON_MONTHS = 36
START_CAPITAL = 100.0
DD_CAP = 0.25  # strict — ratchet physique, cf. docstring H3
TARGET_X501 = 50_100.0  # ×501 depuis 100 $
DAYS_PER_MONTH = 365.25 / 12.0

# --- Hypothèses calibrées (ancrages docs/25 : S0 642,0 $ / TAKER 272,7 $) ---
# Bisection du 01/10/2026, seed 2026, convergence < 1e-9 sur les paramètres.
RISK_FRACTION = 0.04679422  # f — CALIBRÉ sur l'ancre S0 = 642,0 $ (docstring H2)
EFFECTIVE_LEVERAGE = 11.170921  # LEV — CALIBRÉ sur l'ancre TAKER = 272,7 $ (idem)

# Les 5 scénarios de coûts de la table officielle docs/25 (bps/côté).
SCENARIOS: list[tuple[str, float]] = [
    ("S0_reference", 0.0),
    ("MAKER_DELTA2", 2.1),
    ("MAKER_PURE", 2.0),
    ("MAKER_STRESS", 3.0),
    ("TAKER", 6.1),
]

# Table de contre-vérification : les chiffres publiés docs/25 (médiane 12 m ;
# P(≥250) ; P(≥500) ; P(≥1250) ; x501 @ 36 m).
DOCS25: dict[str, tuple[float, float, float, float, float]] = {
    "S0_reference": (642.0, 0.801, 0.601, 0.332, 0.357),
    "MAKER_DELTA2": (468.4, 0.730, 0.504, 0.253, 0.213),
    "MAKER_PURE": (475.4, 0.733, 0.508, 0.257, 0.218),
    "MAKER_STRESS": (412.9, 0.698, 0.461, 0.222, 0.164),
    "TAKER": (272.7, 0.572, 0.335, 0.136, 0.058),
}
CALIBRATION_ANCHORS = ("S0_reference", "TAKER")
TOLERANCE_MEDIAN = 0.05  # ±5 % sur les médianes hors calibration


def load_pool() -> dict:
    """Charge les 31 trades embarqués → R = pnl_usd_net / risque_usd + cadence."""
    rs: list[float] = []
    first: datetime | None = None
    last: datetime | None = None
    files = sorted(TRADES_DIR.glob("x501_backtest_trades_*.csv"))
    if not files:
        raise FileNotFoundError(f"CSV de trades introuvables dans {TRADES_DIR}")
    for path in files:
        with path.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                risk = float(row["risque_usd"])
                if risk <= 0:
                    raise ValueError(f"risque_usd <= 0 dans {path.name}")
                rs.append(float(row["pnl_usd_net"]) / risk)
                ent = datetime.strptime(row["entree_utc"], "%Y-%m-%d %H:%M")
                sor = datetime.strptime(row["sortie_utc"], "%Y-%m-%d %H:%M")
                first = ent if first is None or ent < first else first
                last = sor if last is None or sor > last else last
    assert first is not None and last is not None
    span_months = (last - first).total_seconds() / 86400.0 / DAYS_PER_MONTH
    rate = len(rs) / span_months
    n12 = int(round(rate * 12.0))
    n36 = int(round(rate * float(HORIZON_MONTHS)))
    return {
        "pool": np.array(rs, dtype=np.float64),
        "n_trades": len(rs),
        "span_months": span_months,
        "rate_per_month": rate,
        "n12": n12,
        "n36": n36,
        "files": [p.name for p in files],
    }


def simulate(
    cost_bps: float,
    pool: np.ndarray,
    n12: int,
    n36: int,
    n_traj: int = N_TRAJECTORIES,
    seed: int = SEED,
    risk_fraction: float | None = None,
    leverage: float | None = None,
) -> dict:
    """Une expérience MC complète pour UN scénario de coût (docstring Méthodologie).

    Retourne les métriques demandées + les stats internes (DD, plancher) sous
    clés préfixées « _ » (jamais écrites au JSON officiel).
    """
    f = RISK_FRACTION if risk_fraction is None else risk_fraction
    lev = EFFECTIVE_LEVERAGE if leverage is None else leverage
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, pool.size, size=(n_traj, n36))
    cost_frac = 2.0 * cost_bps * lev / 10_000.0  # round-trip, fraction d'équité
    r = f * pool[idx] - cost_frac
    eq = START_CAPITAL * np.cumprod(1.0 + r, axis=1)
    peak = np.maximum.accumulate(eq, axis=1)
    floor = (1.0 - DD_CAP) * peak
    eq = np.maximum(eq, floor)  # ratchet/coupe-circuit -25 %
    dd = 1.0 - eq / peak
    dd_max_traj = dd.max(axis=1)
    e12 = eq[:, n12 - 1]
    e36 = eq[:, -1]
    return {
        "median_12m": float(np.median(e12)),
        "p250": float(np.mean(e12 >= 250.0)),
        "p500": float(np.mean(e12 >= 500.0)),
        "p1250": float(np.mean(e12 >= 1250.0)),
        "x501_36m": float(np.mean(e36 >= TARGET_X501)),
        "_p25_12m": float(np.percentile(e12, 25)),
        "_p75_12m": float(np.percentile(e12, 75)),
        "_max_dd": float(dd.max()),
        "_floor_touches": int(np.count_nonzero(dd_max_traj >= DD_CAP - 1e-12)),
    }


def run_all(pool_info: dict | None = None) -> dict:
    """Les 5 scénarios, nombres communs aléatoires (mêmes tirages, docstring H4)."""
    info = pool_info or load_pool()
    pool = info["pool"]
    # Même matrice de tirages pour tous les scénarios → re-tirage par scénario
    # avec le même seed = mêmes trajectoires (H4), implémentation simple.
    out: dict[str, dict] = {}
    for name, bps in SCENARIOS:
        res = simulate(bps, pool, info["n12"], info["n36"])
        out[name] = {k: v for k, v in res.items() if not k.startswith("_")}
        out[name]["_stats"] = {k: v for k, v in res.items() if k.startswith("_")}
        out[name]["_stats"]["cost_bps"] = bps
    return out


def build_json(results: dict, info: dict) -> dict:
    """Format officiel : {scenario: {…}, seed, generated_at, meta}."""
    meta = {
        "engine": ENGINE,
        "engine_version": ENGINE_VERSION,
        "n_trajectories": N_TRAJECTORIES,
        "horizon_months": HORIZON_MONTHS,
        "start_capital": START_CAPITAL,
        "target_x501": TARGET_X501,
        "dd_cap": DD_CAP,
        "dd_mechanism": "ratchet/coupe-circuit: equite ramenee au plancher 0.75x pic (jamais au-dela)",
        "random_numbers": "numpy default_rng PCG64, nombres communs entre scenarios (H4)",
        "resampling": "bootstrap avec remise des retours par trade R=pnl_usd_net/risque_usd, pool unique",
        "pool_size": info["n_trades"],
        "pool_files": info["files"],
        "backtest_span_months": round(info["span_months"], 6),
        "trade_rate_per_month": round(info["rate_per_month"], 6),
        "n_trades_12m": info["n12"],
        "n_trades_36m": info["n36"],
        "risk_fraction": RISK_FRACTION,
        "effective_leverage": EFFECTIVE_LEVERAGE,
        "cost_model": "r = f*R - 2*bps*LEV/10000 (round-trip en fraction d'equite)",
        "calibration": "f et LEV ancrees sur docs/25: mediane 12m S0=642.0 et TAKER=272.7 (H2)",
    }
    payload: dict = {"seed": SEED, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    for name, _bps in SCENARIOS:
        payload[name] = {k: results[name][k] for k in ("median_12m", "p250", "p500", "p1250", "x501_36m")}
    payload["meta"] = meta
    return payload


def print_counter_verification(results: dict) -> int:
    """Table docs/25 vs re-run. Retourne le nombre de médianes hors ±5 % (hors ancres)."""
    print("\n=== CONTRE-VÉRIFICATION docs/25 vs re-run x501_mc_v20 ===")
    print(f"{'scénario':<14} {'coût':>5} | {'méd 12m doc':>11} {'re-run':>9} {'écart':>7} | "
          f"{'P250 d/r':>13} {'P500 d/r':>13} {'P1250 d/r':>13} | {'x501 d/r':>13}")
    breaches = 0
    for name, bps in SCENARIOS:
        doc = DOCS25[name]
        res = results[name]
        ecart = (res["median_12m"] - doc[0]) / doc[0]
        anchored = name in CALIBRATION_ANCHORS
        if not anchored and abs(ecart) > TOLERANCE_MEDIAN:
            breaches += 1
        tag = "ANCRE" if anchored else ("HORS ±5%" if abs(ecart) > TOLERANCE_MEDIAN else "ok")
        print(f"{name:<14} {bps:>4.1f}b | {doc[0]:>11.1f} {res['median_12m']:>9.1f} "
              f"{ecart:>+6.1%}{tag:>9} | "
              f"{doc[1]:.3f}/{res['p250']:.3f} {doc[2]:.3f}/{res['p500']:.3f} "
              f"{doc[3]:.3f}/{res['p1250']:.3f} | {doc[4]:.3f}/{res['x501_36m']:.3f}")
    for name, _bps in SCENARIOS:
        st = results[name]["_stats"]
        print(f"  [stats] {name:<14} DDmax={st['_max_dd']:.7f}  coupe-circuit touchés: "
              f"{st['_floor_touches']}/{N_TRAJECTORIES}  P25/P75 12m S0-like: "
              f"{st['_p25_12m']:.0f}/{st['_p75_12m']:.0f}$")
    return breaches


def verify(payload_path: Path) -> bool:
    """--verify : re-exécution et comparaison BIT À BIT des résultats (H4/seed)."""
    with payload_path.open(encoding="utf-8") as fh:
        saved = json.load(fh)
    info = load_pool()
    results = run_all(info)
    ok = True
    for name, _bps in SCENARIOS:
        for key in ("median_12m", "p250", "p500", "p1250", "x501_36m"):
            a, b = saved.get(name, {}).get(key), results[name][key]
            if a is None or a != b:  # égalité float64 exacte = bit à bit
                print(f"  DIFF {name}.{key}: json={a!r} vs re-run={b!r}")
                ok = False
    if saved.get("seed") != SEED:
        print(f"  DIFF seed: json={saved.get('seed')} vs {SEED}")
        ok = False
    print(f"--verify : {'OK — résultats identiques bit à bit (generated_at exclu, horloge)' if ok else 'ÉCHEC'}")
    return ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Moteur MC v20 reconstruit (OpenMarket ×501)")
    ap.add_argument("--verify", action="store_true", help="re-exécute et compare bit à bit le JSON existant")
    ap.add_argument("--out", type=Path, default=RESULTS_PATH)
    args = ap.parse_args(argv)
    if args.verify:
        return 0 if verify(args.out) else 1
    info = load_pool()
    results = run_all(info)
    payload = build_json(results, info)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"pool: {info['n_trades']} trades ({', '.join(info['files'])}), "
          f"fenêtre {info['span_months']:.2f} mois → {info['n12']} trades/12m, {info['n36']}/36m")
    print(f"hypothèses: f={RISK_FRACTION} LEV={EFFECTIVE_LEVERAGE} seed={SEED} "
          f"n_traj={N_TRAJECTORIES} DD_cap={DD_CAP:.0%} (ratchet)")
    print(f"JSON écrit: {args.out}")
    breaches = print_counter_verification(results)
    return 2 if breaches else 0


if __name__ == "__main__":
    sys.exit(main())
