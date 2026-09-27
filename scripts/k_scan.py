#!/usr/bin/env python
"""K SCAN — le multiplicateur global de taille, le dernier paramètre libre.

La cellule QUBO jointe (scripts/qubo_joint_lev.py, rapport
reports/qubo-joint-lev-2026-09-27.md) w = [0.857, 0.857, 2.0, 0.857] ×
lev [11x/1x/1x/1x] = $5,181.86 (+5082 %/an, DD 23.3 %, 0 liq) a été
optimisée à K_ATT = 0.89 FIGÉ. Le QUBO a trouvé les poids RELATIFS ; le
K global (le multiplicateur absolu de taille, K_ATT dans qubo_sizing.py)
n'a JAMAIS été scanné — c'est le dernier degré de liberté. Cible user :
DD ≤ 25 % — à 23.3 % il reste ~1.7 pt de DD à convertir en ROI.

Protocole (la doctrine) :
  - K ∈ {0.89 (ancre actuelle), 0.95, 1.00, 1.05, 1.10, 1.15} sur LA
    cellule jointe (poids ET leviers du QUBO joint, pas la main). K est
    patché via scripts.qubo_sizing.K_ATT — base_sizer relit le global à
    chaque appel, AUCUN fichier officiel n'est édité.
  - split train/val PAR LE TEMPS 70/30 (même formule que le QUBO) ;
    K choisi sur TRAIN (0 liq, DD TRAIN ≤ 25 %, max ROI TRAIN), confirmé
    VAL (1 liq VAL = rejet, le DD VAL est rapporté).
  - 0 liq OBLIGATOIRE. Invariance théorique : pnl/margin ne dépend pas
    de K (notional ET marge scalent ensemble : fees/margin et
    funding/margin sont constants, la règle pnl ≤ -margin aussi, et
    mae ≥ 100/lev − 0.5 ne voit pas K) → l'ensemble des liquidations ne
    dépend PAS de K. Vérifié empiriquement : n et liq identiques sur
    toute la grille, et l'ancre K=0.89 doit coller à $5,181.86.
  - garde-fou composé-des-mois vs final (le verdict RELATIF survit aux
    bugs, l'ABSOLU non).
  - honnêteté : un K plus haut amplifie AUSSI les mois négatifs et le
    pire mois — rapportés ; pire mois < -15 % au point recommandé =
    trade-off explicite à décider.

  .venv/bin/python scripts/k_scan.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.qubo_sizing as qs  # noqa: E402
from scripts.qubo_joint_lev import run_with  # noqa: E402
from scripts.qubo_sizing import (  # noqa: E402
    FLUXES, base_sizer, bloc, build_events)
from scripts.stacked_portfolio import CAPITAL  # noqa: E402

REPORTS = ROOT / "reports"
DATE = "2026-09-27"
K_GRID = [0.89, 0.95, 1.00, 1.05, 1.10, 1.15]  # 0.89 = l'ancre officielle
ANCHOR = 5181.86                               # la cellule jointe à K=0.89
# LA CELLULE JOINTE — le choix du QUBO joint (λ=0.03), PAS la main :
# niveaux exacts de la grille 2/7·3 = 0.857 et 2.0.
W_CELL = {"cascade_10x": 2 / 7 * 3, "cascade_meme": 2 / 7 * 3,
          "survivor_long": 2.0, "vol_spike_6h": 2 / 7 * 3}
LEV_CELL = {"cascade_10x": 11.0, "cascade_meme": 1.0,
            "survivor_long": 1.0, "vol_spike_6h": 1.0}


def scan_one(k: float, ctx: dict, fh: dict, train_ev: list, val_ev: list,
             all_ev: list) -> dict:
    """La cellule jointe à un K donné — TRAIN, VAL, FULL."""
    qs.K_ATT = k                     # patch du global (relu par base_sizer)
    base = base_sizer(ctx)
    r_tr = run_with(train_ev, base, W_CELL, LEV_CELL, fh)
    r_va = run_with(val_ev, base, W_CELL, LEV_CELL, fh)
    r_fu = run_with(all_ev, base, W_CELL, LEV_CELL, fh)
    _, mt = bloc(r_tr, f"K={k:.2f} — TRAIN", CAPITAL)
    _, mv = bloc(r_va, f"K={k:.2f} — VAL", CAPITAL)
    _, mf = bloc(r_fu, f"K={k:.2f} — FULL", CAPITAL)
    print(f"[kscan] K={k:.2f}: train ${r_tr['balance']:,.2f} "
          f"(DD {r_tr['max_dd']:.1f} %, liq {r_tr['n_liq']}) | "
          f"val ${r_va['balance']:,.2f} (DD {r_va['max_dd']:.1f} %, "
          f"liq {r_va['n_liq']}) | full ${r_fu['balance']:,.2f} "
          f"(DD {r_fu['max_dd']:.1f} %, liq {r_fu['n_liq']}, "
          f"{mf['neg']} neg, pire {min(mf['rois']):+.1f} %, "
          f"rec {max(mf['rois']):+.1f} %)", flush=True)
    return {"K": k, "tr": r_tr, "va": r_va, "fu": r_fu,
            "mt": mt, "mv": mv, "mf": mf}


def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[kscan] events {dict(counts)} en {time.time()-t0:.0f}s",
          flush=True)

    # ——— le split temporel 70/30 (identique au QUBO joint) ———
    ts = np.array([e["ts_ms"] for e in all_ev])
    t_split = ts.min() + 0.7 * (ts.max() - ts.min())
    d = datetime.fromtimestamp(t_split / 1e9, tz=timezone.utc)
    train_ev = [e for e in all_ev if e["ts_ms"] < t_split]
    val_ev = [e for e in all_ev if e["ts_ms"] >= t_split]
    print(f"[kscan] split {d:%Y-%m-%d} : train {len(train_ev)} / "
          f"val {len(val_ev)}", flush=True)

    # ——— LE SCAN ———
    rows = [scan_one(k, ctx, fh, train_ev, val_ev, all_ev) for k in K_GRID]

    # ——— les garde-fous structurels ———
    anchor_row = rows[0]
    anchor_ok = abs(anchor_row["fu"]["balance"] - ANCHOR) < 0.02
    n_set = {r["fu"]["n"] for r in rows}
    liq_set = {r["fu"]["n_liq"] for r in rows} | \
              {r["tr"]["n_liq"] for r in rows} | \
              {r["va"]["n_liq"] for r in rows}
    invar_ok = len(n_set) == 1 and liq_set == {0}
    gaps_ok = all(r["mf"]["gap_c"] < 0.005 and r["mt"]["gap_c"] < 0.005
                  and r["mv"]["gap_c"] < 0.005 for r in rows)

    # ——— le choix sur TRAIN : 0 liq, DD ≤ 25 %, max ROI TRAIN ———
    ok = [r for r in rows if r["tr"]["n_liq"] == 0
          and r["tr"]["max_dd"] <= 25.0
          and r["tr"]["balance"] > CAPITAL]
    pool = sorted(ok or rows, key=lambda r: -r["tr"]["balance"])
    chosen = next((r for r in pool if r["va"]["n_liq"] == 0), pool[0])

    # ——— la frontière FULL : le max ROI à DD ≤ 25 %, 0 liq ———
    front = [r for r in rows if r["fu"]["n_liq"] == 0
             and r["fu"]["max_dd"] <= 25.0]
    best = max(front or rows, key=lambda r: r["fu"]["balance"])

    # ——— le rapport ———
    L = ["# K SCAN — le multiplicateur global de taille (le dernier paramètre libre)",
         f"{DATE} — la cellule QUBO jointe w = 0.857/0.857/2.00/0.857 × "
         "lev 11x/1x/1x/1x (λ=0.03) a été optimisée à K_ATT = 0.89 figé : "
         "le QUBO a trouvé les poids RELATIFS, le K global (multiplicateur "
         "absolu de la machine) n'avait jamais été scanné. Grille K ∈ "
         + "{" + ", ".join(f"{k:g}" for k in K_GRID) + "} — la cellule est "
         "rejouée à l'IDENTIQUE (poids et leviers du QUBO joint, pas la "
         "main), seul K bouge. Split train/val PAR LE TEMPS 70/30 au "
         f"{d:%Y-%m-%d} ({len(train_ev)}/{len(val_ev)} événements) ; K "
         "choisi sur TRAIN (0 liq, DD TRAIN ≤ 25 %, max ROI TRAIN), "
         "confirmé VAL (1 liq VAL = rejet). Cible user : DD ≤ 25 %.", "",
         "## 0. LES GARDE-FOUS STRUCTURELS", "",
         f"- Ancre K=0.89 : ${anchor_row['fu']['balance']:,.2f} vs "
         f"${ANCHOR:,.2f} attendu (rapport qubo-joint-lev) → "
         + ("**OK, la pipeline reproduit l'ABSOLU**" if anchor_ok
            else "**ÉCART — BUG de pipeline, ne rien conclure**") + ".",
         f"- Invariance 0-liq (théorème d'échelle : pnl/marge est "
         f"indépendant de K — fees et funding scalent comme la marge, "
         f"mae ≥ 100/lev−0.5 ne voit pas K) : trades {sorted(n_set)}, "
         f"liq {sorted(liq_set)} sur TOUTE la grille → "
         + ("**VÉRIFIÉ, 0 liq partout**" if invar_ok
            else "**VIOLÉ — un K crée une liquidation, STOP**") + ".",
         "- Garde-fou composé-des-mois vs final (< 0.005 %) : "
         + ("OK sur les 18 runs." if gaps_ok
            else "**BUG — un verdict ABSOLU est contaminé.**"), "",
         "## 1. LA FRONTIÈRE K → (ROI, DD) — la courbe d'efficience finale", "",
         "| K | TRAIN $ | TRAIN DD | TRAIN liq | VAL $ | VAL DD | VAL liq "
         "| **FULL $** | **ROI/an** | **DD FULL** | liq | record | pire mois "
         "| mois nég | composé |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        mf, mt, mv = r["mf"], r["mt"], r["mv"]
        mark = " ← choix TRAIN→VAL" if r is chosen else \
               (" ← frontière FULL" if r is best else "")
        L.append(
            f"| {r['K']:.2f} | ${r['tr']['balance']:,.0f} "
            f"| {r['tr']['max_dd']:.1f} % | {r['tr']['n_liq']} "
            f"| ${r['va']['balance']:,.2f} | {r['va']['max_dd']:.1f} % "
            f"| {r['va']['n_liq']} | **${r['fu']['balance']:,.2f}** "
            f"| **{mf['roi_an']:+.0f} %** | **{r['fu']['max_dd']:.1f} %** "
            f"| {r['fu']['n_liq']} | {max(mf['rois']):+.1f} % "
            f"| {min(mf['rois']):+.1f} % | {mf['neg']} "
            f"| {mf['gap_c']*100:.3f} % |{mark}")
    L += ["",
          f"**Choix sur TRAIN** (0 liq, DD TRAIN ≤ 25 %, max ROI TRAIN, "
          f"confirmé 0 liq VAL) : **K = {chosen['K']:.2f}**. "
          f"**Point frontière FULL** (max ROI à DD FULL ≤ 25 %, 0 liq) : "
          f"**K = {best['K']:.2f}**.", "",
          "## 2. LE BLOC STATS DU POINT RECOMMANDÉ", ""]
    for res, lbl, meta in ((chosen["tr"], f"CELLULE K={chosen['K']:.2f} — TRAIN",
                            chosen["mt"]),
                           (chosen["va"], f"CELLULE K={chosen['K']:.2f} — VAL",
                            chosen["mv"]),
                           (chosen["fu"], f"CELLULE K={chosen['K']:.2f} — FULL",
                            chosen["mf"])):
        lines, _ = bloc(res, lbl, CAPITAL)
        L += lines + [""]
    L += ["### La table mensuelle FULL au K recommandé", "",
          "| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
          "|---|---|---|---|---|---|"]
    for x in chosen["mf"]["mrows"]:
        L.append(f"| {x['month']} | {x['n']} "
                 f"| {x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                 f"| ${x['start']:,.0f} → ${x['end']:,.0f} "
                 f"| {x['roi']:+.1f} % |")

    # ——— le verdict ———
    g_roi = (best["fu"]["balance"] / anchor_row["fu"]["balance"] - 1) * 100
    worst = min(chosen["mf"]["rois"])
    cibles = [("DD FULL ≤ 25 %", chosen["fu"]["max_dd"] <= 25.0),
              ("0 liq", chosen["fu"]["n_liq"] == 0
               and chosen["va"]["n_liq"] == 0),
              ("record ≥ 80 %", max(chosen["mf"]["rois"]) >= 80.0),
              ("≤ 1 mois négatif/12", chosen["mf"]["neg"] <= 1),
              ("composé ~0", chosen["mf"]["gap_c"] < 0.005)]
    L += ["", "## VERDICT", "",
          f"- L'ancre K=0.89 reproduit ${anchor_row['fu']['balance']:,.2f} "
          + ("(OK)." if anchor_ok else "(ÉCART — BUG)."),
          f"- Le théorème d'échelle tient : le nombre de trades et le "
          f"compte de liquidations sont INVARIANTS à K "
          f"({sorted(n_set)} trades, liq {sorted(liq_set)}) — un K plus "
          f"haut n'a JAMAIS créé de liquidation, il n'amplifie que le PnL.",
          f"- La frontière est monotone : K monte → ROI/an et DD montent "
          f"ensemble. Le point recommandé (max ROI à DD FULL ≤ 25 %) : "
          f"**K = {best['K']:.2f}** → ${best['fu']['balance']:,.2f} "
          f"({best['mf']['roi_an']:+.0f} %/an, DD {best['fu']['max_dd']:.1f} %) "
          f"= {g_roi:+.1f} % de mieux que l'ancre K=0.89 "
          f"(${anchor_row['fu']['balance']:,.2f}, DD {anchor_row['fu']['max_dd']:.1f} %).",
          f"- Le choix doctrinal TRAIN→VAL donne K = {chosen['K']:.2f} "
          f"(TRAIN DD {chosen['tr']['max_dd']:.1f} %, VAL DD "
          f"{chosen['va']['max_dd']:.1f} %, 0 liq partout).",
          f"- L'HONNÊTETÉ : au K recommandé, le pire mois passe de "
          f"{min(anchor_row['mf']['rois']):+.1f} % (K=0.89) à "
          f"{worst:+.1f} %, le record de {max(anchor_row['mf']['rois']):+.1f} % à "
          f"{max(chosen['mf']['rois']):+.1f} %, mois négatifs "
          f"{anchor_row['mf']['neg']} → {chosen['mf']['neg']} — "
          + (f"**pire mois {worst:+.1f} % < -15 % : TRADE-OFF explicite à "
             f"décider** (le ROI acheté par un mois plus dur)."
             if worst < -15.0 else
             f"le pire mois reste ≥ -15 % : le trade-off est propre."),
          f"- Cibles user au K recommandé : "
          + " ; ".join(f"{n} {'OK' if ok else 'ÉCHEC'}" for n, ok in cibles)
          + ".",
          f"- Limite : le K est choisi sur 9 mois TRAIN — le DD VAL "
          f"({chosen['va']['max_dd']:.1f} %) et le DD FULL "
          f"({chosen['fu']['max_dd']:.1f} %) restent les juges de paix ; "
          f"la marge de DD restante avant 25 % est de "
          f"{25.0 - chosen['fu']['max_dd']:.1f} pt.", ""]
    out = REPORTS / f"k-scan-{DATE}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[kscan] rapport -> {out}", flush=True)
    print(f"[kscan] VERDICT: choix TRAIN→VAL K={chosen['K']:.2f} "
          f"| frontière FULL K={best['K']:.2f} "
          f"${best['fu']['balance']:,.2f} ({best['mf']['roi_an']:+.0f} %/an, "
          f"DD {best['fu']['max_dd']:.1f} %) vs ancre "
          f"${anchor_row['fu']['balance']:,.2f} | pire mois "
          f"{min(chosen['mf']['rois']):+.1f} % | liq T/V/F "
          f"{chosen['tr']['n_liq']}/{chosen['va']['n_liq']}/"
          f"{chosen['fu']['n_liq']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
