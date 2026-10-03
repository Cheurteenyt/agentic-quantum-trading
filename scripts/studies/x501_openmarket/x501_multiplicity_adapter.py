#!/usr/bin/env python3
"""Adaptateur multiplicité du pool OpenMarket (R-multiples par trade) -> backtest_v2.multiplicity.

La version précédente plantait à l'import (`bonferroni_threshold` n'existe pas dans multiplicity.py) et n'avait donc
jamais produit un chiffre. Celle-ci utilise l'API réelle : sharpe_pvalue / bonferroni / benjamini_hochberg.

Principe. sharpe_pvalue(sharpe, n_obs, ppy) teste « Sharpe > 0 » avec se = sqrt(ppy / n_obs). Pour des TRADES on pose
ppy = trades/an et sharpe_annuel = E[R]/sd * sqrt(ppy)  =>  z = E[R]/sd * sqrt(n_obs) = le t de Student (approx. normale).
La corrélation entre symboles (les 40 co-bougent) est corrigée en passant n_obs = n_eff = n / deff, où
deff = (SE blocs-mois / SE iid)²  =>  z = t blocs-mois.

Tests : pool entier + A1 / A3 / A4 (m = 4).
N total d'essais = N_PRIOR (cellules citées dans les messages de commit : 264 + 55 + 12 + 10 = 341)
                 + essais du ledger HORS famille openmarket (déjà comptés dans les 341).
DSR : NON CALCULÉ — il exige la variance des Sharpe de TOUS les essais, que le projet ne conserve pas.

    python3 scripts/studies/x501_openmarket/x501_multiplicity_adapter.py [--trades CSV] [--n-prior 341] [--alpha 0.05]
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import statistics as st
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.backtest_v2.multiplicity import (  # noqa: E402
    benjamini_hochberg, bonferroni, norm_ppf, sharpe_pvalue,
)

DEFAULT_TRADES = Path(__file__).with_name("trades_v8_deep.csv")
DEFAULT_LEDGER = ROOT / "research" / "ledger" / "trials.jsonl"
N_PRIOR_DEFAULT = 341


def load_trades(path: Path) -> list[dict]:
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        d = r["entree_utc"][:10]
        rows.append({"R": float(r["R"]), "month": d[:7], "day": d, "alpha": r["flux"].split(":")[0]})
    return rows


def stats_for(rows: list[dict], years: float) -> dict:
    """E[R], t iid, t blocs-mois, n_eff, p-value unilatérale via sharpe_pvalue (n_obs = n_eff)."""
    R = [r["R"] for r in rows]
    n, mu, sd = len(R), st.mean(R), st.stdev(R)
    by_month = collections.defaultdict(float)
    for r in rows:
        by_month[r["month"]] += r["R"] - mu
    se_iid = sd / math.sqrt(n)
    se_blk = math.sqrt(sum(v * v for v in by_month.values())) / n
    deff = max(1.0, (se_blk / se_iid) ** 2)
    n_eff = n / deff
    ppy = max(1, round(n / years))
    sharpe_ann = mu / sd * math.sqrt(ppy)
    return {"n": n, "mean_R": mu, "sd": sd, "t_iid": mu / se_iid, "t_blocs": mu / se_blk, "deff": deff,
            "n_eff": n_eff, "months": len(by_month),
            "p_iid": sharpe_pvalue(sharpe_ann, n, ppy), "p_blocs": sharpe_pvalue(sharpe_ann, max(2, round(n_eff)), ppy)}


def n_from_ledger(path: Path) -> int:
    if not Path(path).exists():
        return 0
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        if e.get("verdict") != "PREREG" and (e.get("family") or "") != "openmarket":
            n += 1
    return n


def analyze(rows: list[dict], n_total: int, alpha: float = 0.05) -> dict:
    days = sorted(r["day"] for r in rows)
    d0, d1 = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    years = max(0.25, (d1 - d0).days / 365.25)
    groups = [("POOL", rows)] + [(a, [r for r in rows if r["alpha"] == a]) for a in ("A1", "A3", "A4")]
    res = [(name, stats_for(sub, years)) for name, sub in groups]
    pv = [s["p_blocs"] for _, s in res]
    bonf = bonferroni(pv, alpha=alpha, n_tested=n_total)
    bh = benjamini_hochberg(pv, alpha=alpha, n_tested=n_total)
    return {"years": years, "n_total": n_total, "rows": res, "bonf": bonf, "bh": bh,
            "z_star": norm_ppf(1.0 - bonf.threshold)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--trades", default=str(DEFAULT_TRADES))
    ap.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    ap.add_argument("--n-prior", type=int, default=N_PRIOR_DEFAULT)
    ap.add_argument("--alpha", type=float, default=0.05)
    a = ap.parse_args(argv)
    rows = load_trades(Path(a.trades))
    n_total = a.n_prior + n_from_ledger(Path(a.ledger))
    out = analyze(rows, n_total, a.alpha)
    print(f"Pool : {len(rows)} trades sur {out['years']:.1f} an(s) · N total d'essais = {n_total} "
          f"({a.n_prior} cellules citées + {n_total - a.n_prior} du ledger hors openmarket)")
    print(f"Seuil Bonferroni (unilatéral, alpha={a.alpha}) : p < {out['bonf'].threshold:.2e}  <=>  t >= {out['z_star']:.2f}\n")
    print(f"{'test':<6}{'n':>5}{'E[R]':>8}{'t iid':>7}{'t blocs':>8}{'n_eff':>7}{'p blocs':>10}  Bonferroni  BH")
    for i, (name, s) in enumerate(out["rows"]):
        print(f"{name:<6}{s['n']:>5}{s['mean_R']:>+8.3f}{s['t_iid']:>7.2f}{s['t_blocs']:>8.2f}{s['n_eff']:>7.0f}"
              f"{s['p_blocs']:>10.4f}  {'SURVIT' if i in out['bonf'].survivors else 'rejeté':<10}  "
              f"{'SURVIT' if i in out['bh'].survivors else 'rejeté'}")
    print("\nDSR : non calculé (variance des Sharpe d'essais absente du projet).")
    surv = [out["rows"][i][0] for i in out["bonf"].survivors]
    print("VERDICT : " + (f"survivent à Bonferroni : {', '.join(surv)}" if surv else
                          f"AUCUN test ne survit à Bonferroni (N={n_total}) : edge non établi au niveau de preuve exigé."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
