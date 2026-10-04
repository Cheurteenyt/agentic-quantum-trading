#!/usr/bin/env python
"""W42-RECON-1 — LA RECONSTRUCTION (pré-enregistrée + amendée :
research/hypotheses/w42-reconstruction.md, gel 12465ab, amendement c8f8db1).

La question : le wallet joint survivor_long + vol_spike_6h (les deux seuls
flux vivants du grand audit post-fix) sous cap de marge 1 % bat-il chaque
flux seul en ret/DD et en stabilité mensuelle ?

Protocole (gelé, amendé avant run) :
  - période complète 2021→2026, données fixées, split TEMPOREL 70/30 ;
  - sizing w=1 codifié (base_sizer) + cap de marge 1 % en wrapper — le cap
    s'applique aux SOLOS et au JOINT (comparaison appariée) ;
  - coûts réels + stress ×1,5 ; run_stack inchangé (moteur post-fix lots 1-3) ;
  - PASS si (1) ret/DD joint VAL ≥ 1,00× survivor solo VAL, (2) mois négatifs
    joint < min des solos, (3) 0 liq, (4) coûts ×1,5 → solde > capital ;
  - SOUS_PUISSANT si < 30 events survivor en VAL ;
  - contrôles : inverse, corr mensuelle, part du top 5 % ;
  - le moteur corrigé (funding as-of, DD MtM, bookage à la sortie) rend les
    ABSOLUS du grand audit morts : les solos re-mesurés = la nouvelle référence.

  .venv/bin/python scripts/studies/w42_reconstruction.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.qubo_sizing import base_sizer, bloc, build_events  # noqa: E402
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402

DATE = "2026-10-05"
LIVING = ("survivor_long", "vol_spike_6h")
CAP = 0.01                       # le cap de marge 1 % (doctrine W41 CH1)
HYPO = ("le portefeuille survivor_long + vol_spike sous cap de marge "
        "re-dérivé sur données propres bat chaque flux seul en ret/DD et "
        "stabilité mensuelle")


def ret_dd(res: dict) -> float:
    months = monthly_rows(res["trades"], CAPITAL)
    roi_an = (res["balance"] / CAPITAL) ** (12 / max(len(months), 1)) - 1
    return (roi_an * 100) / max(res["max_dd"], 0.1)


def neg_months(res: dict) -> int:
    months = monthly_rows(res["trades"], CAPITAL)
    return int(sum(x["roi"] < 0 for x in months))


def monthly_roi(trades: list[dict]) -> dict[str, float]:
    by: dict[str, float] = defaultdict(float)
    for t in trades:
        by[t["exit_ts"].strftime("%Y-%m")] += t["pnl"]
    return {k: v / CAPITAL * 100 for k, v in sorted(by.items())}


def corr_months(a: dict[str, float], b: dict[str, float]) -> float:
    common = sorted(set(a) & set(b))
    if len(common) < 6:
        return float("nan")
    return float(np.corrcoef([a[k] for k in common],
                             [b[k] for k in common])[0, 1])


def line(res: dict, label: str) -> str:
    return (f"| {label} | {res['n']} | ${res['balance']:,.2f} "
            f"| {res['max_dd']:.2f} % | {res['n_liq']} "
            f"| {neg_months(res)} | {ret_dd(res):.1f} |")


def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[w42] events {dict(counts)} en {time.time() - t0:.0f}s", flush=True)
    ev = [e for e in all_ev if e["strategy"] in LIVING]
    ts = np.array([e["ts_ms"] for e in ev])
    t_split = ts.min() + 0.7 * (ts.max() - ts.min())
    train = [e for e in ev if e["ts_ms"] < t_split]
    val = [e for e in ev if e["ts_ms"] >= t_split]
    n_s_val = sum(1 for e in val if e["strategy"] == "survivor_long")
    split_day = datetime.fromtimestamp(t_split / 1e9, tz=timezone.utc)
    print(f"[w42] train {len(train)} / val {len(val)} "
          f"(split {split_day:%Y-%m-%d}, survivor VAL {n_s_val})", flush=True)

    base = base_sizer(ctx)

    def cap_sizer(e, st=None):
        return min(base(e, st), CAP)

    # ——— les solos post-fix : la nouvelle référence (même sizing + cap) ———
    solo_s_va = run_stack([e for e in val if e["strategy"] == "survivor_long"],
                          CAPITAL, cap_sizer, fh)
    solo_v_va = run_stack([e for e in val if e["strategy"] == "vol_spike_6h"],
                          CAPITAL, cap_sizer, fh)
    # ——— le joint ———
    joint_tr = run_stack(train, CAPITAL, cap_sizer, fh)
    joint_va = run_stack(val, CAPITAL, cap_sizer, fh)
    # ——— le stress coûts ×1,5 sur le joint VAL ———
    val15 = [{**e, "fee_rt_bps": e["fee_rt_bps"] * 1.5} for e in val]
    joint_va15 = run_stack(val15, CAPITAL, cap_sizer, fh)

    # ——— les contrôles (documentation, non bloquants) ———
    inv_ev = [{**e, "price_ret_short": -e["price_ret_short"]}
              for e in val if e["strategy"] == "survivor_long"]
    solo_s_inv = run_stack(inv_ev, CAPITAL, cap_sizer, fh)
    corr = corr_months(monthly_roi(solo_s_va["trades"]),
                       monthly_roi(solo_v_va["trades"]))
    pnls = sorted((t["pnl"] for t in joint_va["trades"]), reverse=True)
    k_top = max(1, int(np.ceil(len(pnls) * 0.05))) if pnls else 0
    top_share = (sum(pnls[:k_top]) / sum(pnls) * 100
                 if pnls and sum(pnls) != 0 else float("nan"))

    # ——— les critères gelés ———
    rr_s, rr_v, rr_j = ret_dd(solo_s_va), ret_dd(solo_v_va), ret_dd(joint_va)
    c1 = rr_j >= 1.00 * rr_s
    c2 = neg_months(joint_va) < min(neg_months(solo_s_va), neg_months(solo_v_va))
    c3 = joint_va["n_liq"] == 0
    c4 = joint_va15["balance"] > CAPITAL
    sous_puissant = n_s_val < 30
    if sous_puissant:
        verdict = "SOUS_PUISSANT"
    else:
        verdict = "PASS" if (c1 and c2 and c3 and c4) else "FAIL"

    # ——— le rapport ———
    L = [f"# W42-RECON-1 — la reconstruction ({DATE})",
         "Pré-enregistrée + amendée : research/hypotheses/w42-reconstruction.md "
         "(gel 12465ab, amendement c8f8db1 — moteur post-fix lots 1-3).",
         f"Split {split_day:%Y-%m-%d} : train {len(train)} / val {len(val)}. "
         f"Cap de marge 1 % apparié aux deux côtés.", "",
         "## Les wallets (VAL, moteurs post-fix)", "",
         "| wallet | n | solde | DD | liq | mois nég | ret/DD |",
         "|---|---|---|---|---|---|---|",
         line(solo_s_va, "survivor_long solo"),
         line(solo_v_va, "vol_spike_6h solo"),
         line(joint_va, "JOINT"),
         line(joint_va15, "JOINT coûts ×1,5"), "",
         f"## Les critères gelés", "",
         f"- C1 ret/DD joint ≥ 1,00× survivor solo : {rr_j:.1f} vs {rr_s:.1f} "
         f"→ **{'OK' if c1 else 'KO'}**",
         f"- C2 mois négatifs joint < min des solos : {neg_months(joint_va)} "
         f"vs {min(neg_months(solo_s_va), neg_months(solo_v_va))} "
         f"→ **{'OK' if c2 else 'KO'}**",
         f"- C3 0 liquidation : {joint_va['n_liq']} → **{'OK' if c3 else 'KO'}**",
         f"- C4 coûts ×1,5 → solde > capital : ${joint_va15['balance']:,.2f} "
         f"→ **{'OK' if c4 else 'KO'}**",
         f"- SOUS_PUISSANT (survivor VAL < 30) : n={n_s_val} "
         f"→ **{'OUI' if sous_puissant else 'NON'}**", "",
         "## Les contrôles", "",
         f"- inverse (survivor inversé VAL) : ${solo_s_inv['balance']:,.2f}, "
         f"ret/DD {ret_dd(solo_s_inv):.1f} (le sens codé doit dominer)",
         f"- corr mensuelle survivor/vol_spike : {corr:.2f} (prédiction < 0,30)",
         f"- part du top 5 % des trades dans le pnl joint : {top_share:.0f} %", "",
         "## Baseline anti-dérive (train, mémoire)", "",
         f"- joint TRAIN : ${joint_tr['balance']:,.2f} (DD "
         f"{joint_tr['max_dd']:.2f} %, liq {joint_tr['n_liq']})",
         "- les ABSOLUS pré-fix du grand audit ($155/DD 7,4 % ; $122/DD 13,4 %) "
         "sont morts avec le moteur : référence = les solos ci-dessus.", ""]
    lines, _ = bloc(joint_va, "JOINT VAL", CAPITAL)
    L += lines + ["", f"## VERDICT : {verdict}", ""]

    out = ROOT / "reports" / f"w42-reconstruction-{DATE}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[w42] rapport -> {out}", flush=True)
    print(f"[w42] VERDICT: {verdict} (C1 {c1} C2 {c2} C3 {c3} C4 {c4} "
          f"n_val_survivor {n_s_val})", flush=True)

    subprocess.run([
        str(ROOT / ".venv" / "bin" / "python"), "scripts/lab_ledger.py", "log",
        "--family", "reconstruction", "--strategy", "w42-portfolio",
        "--hypothesis", HYPO, "--verdict", verdict,
        "--n", str(len(val)), "--er", f"{rr_j:.2f}",
        "--ref", f"reports/w42-reconstruction-{DATE}.md",
        "--notes", (f"joint ${joint_va['balance']:,.2f} DD "
                    f"{joint_va['max_dd']:.2f} % ret/DD {rr_j:.1f} vs survivor "
                    f"solo ${solo_s_va['balance']:,.2f} DD "
                    f"{solo_s_va['max_dd']:.2f} % ret/DD {rr_s:.1f} ; C1 {c1} "
                    f"C2 {c2} C3 {c3} C4 {c4}")],
        check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
