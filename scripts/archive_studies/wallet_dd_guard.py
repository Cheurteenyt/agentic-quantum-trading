#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""LE GARDE DRAWDOWN DU WALLET — le désengagement prop-firm sur la machine.

Ce qui n'avait JAMAIS été testé : le garde au niveau du WALLET (les
gardes antérieurs étaient au niveau du SIGNAL : sizing conditionnel —
cher, dd_cross — nul). Mécanisme : à chaque nouveau trade, si le
drawdown courant du PORTEFEUILLE (pic → balance) dépasse le seuil S,
la taille du trade est multipliée par r JUSQU'AU RETOUR sous S/2
(l'hystérésis — sinon clignotement). 6 cellules
(S ∈ {10, 15, 20} × r ∈ {0.5, 0.75}) + le contrôle sans garde, sur
2 configs : la machine 4 flux (poids main) et la variante QUBO
(λ=0.03, w=0.857/0.857/2.0/1.143 — rapport qubo-sizing-2026-09-27).

Le piège classique (l'attention mécanique) : le garde coupe la taille
après les pertes = il rate le rebond. C'est POUR ÇA que le hystérésis
S/2 et le retour existent — et le « coût de garde » est MESURÉ :
trades passés en taille réduite, leur PnL réalisé vs leur
contre-factuel pleine taille (le PnL est linéaire dans la taille :
pnl_pleine = pnl_réduit / r à balance donnée). Si le garde coûte plus
qu'il ne protège, on le dira (la culture des nuls).

Split temporel 70/30 PAR LE TEMPS (zéro look-ahead) : jugé sur TRAIN,
confirmé sur VAL. Règle de décision : PASS si (pire mois amélioré ET
DD ≤ baseline ET ROI ≥ baseline −10 %) sur TRAIN, confirmé VAL.
Sinon CONTEXTE/NUL avec les chiffres.

  .venv/bin/python scripts/wallet_dd_guard.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.qubo_sizing import (  # noqa: E402
    base_sizer, bloc, build_events, weighted_sizer)
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402

REPORTS = ROOT / "reports"
DATE = "2026-09-27"
# les poids QUBO retenus (λ=0.03) : niveaux exacts de la discrétisation
# m=3 bits, W_MAX=2, K=7 → 0.857=6/7, 1.143=8/7, 2.0
W_QUBO = {"cascade_10x": 6 / 7, "cascade_meme": 6 / 7,
          "survivor_long": 2.0, "vol_spike_6h": 8 / 7}
CELLS = [(10.0, 0.50), (10.0, 0.75), (15.0, 0.50),
         (15.0, 0.75), (20.0, 0.50), (20.0, 0.75)]


def guard_sizer(inner, S: float, r: float):
    """×r tant que le DD wallet > S, pleine taille revenue sous S/2.

    Journal : un booléen par trade taillé, aligné 1-pour-1 sur
    res['trades'] (le sizing est appelé exactement une fois par trade
    exécuté — asserté dans guard_cost)."""
    on = {"flag": False}
    log: list[bool] = []

    def fn(e, st=None):
        dd = float(st["dd"]) if st else 0.0
        if dd > S:
            on["flag"] = True
        elif dd < S / 2:
            on["flag"] = False
        log.append(on["flag"])
        return inner(e, st) * (r if on["flag"] else 1.0)
    return fn, log


def guard_cost(log: list[bool], trades: list[dict], r: float) -> dict:
    """Le coût du garde : trades taillés + PnL réalisé vs contre-factuel.

    cost = réalisé − contre-factuel : négatif = profit manqué (le garde
    a raté le rebond), positif = pertes évitées (il a protégé)."""
    assert len(log) == len(trades), (
        f"journal garde {len(log)} != trades {len(trades)} — alignement rompu")
    g = [(t, a) for t, a in zip(trades, log) if a]
    pnl_g = sum(t["pnl"] for t, _ in g)
    pnl_cf = sum(t["pnl"] / r for t, _ in g)
    return {"n_g": len(g), "pnl_g": pnl_g, "pnl_cf": pnl_cf,
            "cost": pnl_g - pnl_cf}


def wstats(res: dict) -> dict:
    mrows = monthly_rows(res["trades"], CAPITAL)
    rois = [x["roi"] for x in mrows] or [0.0]
    return {"bal": res["balance"], "dd": res["max_dd"], "n": res["n"],
            "liq": res["n_liq"],
            "wr": res["n_wins"] / max(res["n"], 1) * 100,
            "neg": int(sum(v < 0 for v in rois)), "worst": min(rois),
            "rec": max(rois), "nm": len(mrows)}


def main() -> int:
    t0 = time.time()
    all_ev, ctx, fh, counts = build_events()
    print(f"[guard] events {dict(counts)} en {time.time()-t0:.0f}s")
    base = base_sizer(ctx)
    configs = [("machine", base), ("qubo", weighted_sizer(base, W_QUBO))]

    # ——— le split PAR LE TEMPS (70/30), identique à qubo_sizing ———
    ts = np.array([e["ts_ms"] for e in all_ev])
    t_split = ts.min() + 0.7 * (ts.max() - ts.min())
    d_split = datetime.fromtimestamp(t_split / 1e9, tz=timezone.utc)
    wins = {"TRAIN": [e for e in all_ev if e["ts_ms"] < t_split],
            "VAL": [e for e in all_ev if e["ts_ms"] >= t_split],
            "FULL": all_ev}
    print(f"[guard] split {d_split:%Y-%m-%d} : "
          f"{len(wins['TRAIN'])} train / {len(wins['VAL'])} val")

    # ——— les 2 configs × 7 cellules × 3 fenêtres ———
    R: dict[tuple, dict] = {}
    for cname, sizer in configs:
        for wname, ev in wins.items():
            r0 = run_stack(ev, CAPITAL, sizer, fh)
            R[(cname, "ctrl", wname)] = {"res": r0, "cost": None}
            for S, r in CELLS:
                fn, log = guard_sizer(sizer, S, r)
                rg = run_stack(ev, CAPITAL, fn, fh)
                R[(cname, (S, r), wname)] = {
                    "res": rg, "cost": guard_cost(log, rg["trades"], r)}
            st = wstats(r0)
            print(f"[guard] {cname} {wname} ctrl : ${r0['balance']:,.2f} "
                  f"(DD {st['dd']:.1f} %, pire {st['worst']:+.1f} %, "
                  f"liq {st['liq']})")

    # ——— la décision : jugée sur TRAIN, confirmée sur VAL ———
    verdicts: dict[tuple, dict] = {}
    for cname, _ in configs:
        tb = wstats(R[(cname, "ctrl", "TRAIN")]["res"])
        vb = wstats(R[(cname, "ctrl", "VAL")]["res"])
        for S, r in CELLS:
            t = wstats(R[(cname, (S, r), "TRAIN")]["res"])
            v = wstats(R[(cname, (S, r), "VAL")]["res"])
            train_ok = (t["worst"] > tb["worst"] and t["dd"] <= tb["dd"]
                        and t["bal"] >= 0.9 * tb["bal"])
            val_ok = (v["liq"] == 0 and v["worst"] >= vb["worst"]
                      and v["dd"] <= vb["dd"] and v["bal"] >= 0.9 * vb["bal"])
            verdicts[(cname, (S, r))] = {
                "t": t, "v": v, "tb": tb, "vb": vb,
                "train_ok": train_ok, "val_ok": val_ok,
                "pass": train_ok and val_ok}

    # ——— le rapport ———
    L = ["# LE GARDE DRAWDOWN DU WALLET — le désengagement prop-firm",
         f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
         "mécanisme WALLET (pas signal) : DD wallet > S ⇒ taille ×r "
         "jusqu'au retour sous S/2 (hystérésis). 6 cellules + contrôle, "
         "2 configs (machine main / QUBO λ=0.03), split 70/30 au "
         f"{d_split:%Y-%m-%d} (zéro look-ahead). Briques importées de "
         "the_machine/stacked_portfolio/qubo_sizing — zéro fichier "
         "officiel édité.", "",
         "## REPRODUCTION DES BASELINES (absolu)", ""]
    for cname, _ in configs:
        fb = wstats(R[(cname, "ctrl", "FULL")]["res"])
        L.append(f"- **{cname}** contrôle FULL : ${fb['bal']:,.2f} "
                 f"(DD {fb['dd']:.1f} %, liq {fb['liq']}, "
                 f"{fb['n']} trades, pire {fb['worst']:+.1f} %, "
                 f"record {fb['rec']:+.1f} %, {fb['neg']} mois négatif)")

    for cname, _ in configs:
        cLabel = ("MACHINE 4 FLUX (poids main)" if cname == "machine"
                  else "VARIANTE QUBO (w=0.86/0.86/2.0/1.14)")
        L += ["", f"## CONFIG {cLabel}", ""]
        for wname in ("FULL",):
            for cell in ["ctrl"] + CELLS:
                e = R[(cname, cell, wname)]
                res = e["res"]
                lines, meta = bloc(res, f"{cname} {cell} — {wname}", CAPITAL)
                L += lines
                if e["cost"] is not None:
                    c = e["cost"]
                    L.append(
                        f"  garde : {c['n_g']} trades taillés "
                        f"({c['n_g']/max(res['n'],1)*100:.0f} %), PnL "
                        f"réalisé ${c['pnl_g']:+,.2f} vs contre-factuel "
                        f"${c['pnl_cf']:+,.2f} pleine taille → coût net "
                        f"**${c['cost']:+,.2f}** "
                        f"({'protège' if c['cost'] > 0 else 'RATE le rebond'})"
                        f" | wallet vs contrôle : "
                        f"{(res['balance']/R[(cname,'ctrl',wname)]['res']['balance']-1)*100:+.1f} %")
                L.append("")
                L += ["| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
                      "|---|---|---|---|---|---|"]
                for x in meta["mrows"]:
                    L.append(
                        f"| {x['month']} | {x['n']} "
                        f"| {x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                        f"| ${x['start']:,.0f} → ${x['end']:,.0f} "
                        f"| {x['roi']:+.1f} % |")
                L.append("")

    # ——— la table de décision TRAIN/VAL ———
    L += ["## LA TABLE DE DÉCISION — TRAIN (jugé) / VAL (confirmé)", ""]
    for cname, _ in configs:
        L += [f"### {cname}", "",
              "| Cellule (S/r) | TRAIN $ | DD | pire mois | | VAL $ | DD "
              "| pire mois | liq | coût garde FULL | verdict |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        tb = verdicts[(cname, CELLS[0])]["tb"]
        vb = verdicts[(cname, CELLS[0])]["vb"]
        L.append(f"| contrôle (sans garde) | ${tb['bal']:,.2f} "
                 f"| {tb['dd']:.1f} % | {tb['worst']:+.1f} % | | "
                 f"${vb['bal']:,.2f} | {vb['dd']:.1f} % "
                 f"| {vb['worst']:+.1f} % | {vb['liq']} | — | référence |")
        for S, r in CELLS:
            vd = verdicts[(cname, (S, r))]
            t, v = vd["t"], vd["v"]
            cost = R[(cname, (S, r), "FULL")]["cost"]
            lbl = "PASS" if vd["pass"] else (
                "CONTEXTE" if vd["train_ok"] and not vd["val_ok"] else "NUL")
            L.append(
                f"| S={S:.0f} %/r={r:.2f} | ${t['bal']:,.2f} "
                f"| {t['dd']:.1f} % | {t['worst']:+.1f} % | | "
                f"${v['bal']:,.2f} | {v['dd']:.1f} % | {v['worst']:+.1f} % "
                f"| {v['liq']} | ${cost['cost']:+,.2f} ({cost['n_g']} tr) "
                f"| **{lbl}** |")
        L.append("")

    # ——— le verdict ———
    L += ["## VERDICT", ""]
    for cname, _ in configs:
        passing = [(S, r) for S, r in CELLS if verdicts[(cname, (S, r))]["pass"]]
        if passing:
            best = max(passing, key=lambda c: verdicts[(cname, c)]["t"]["bal"])
            vd = verdicts[(cname, best)]
            cf = R[(cname, best, "FULL")]["res"]
            fb = wstats(R[(cname, "ctrl", "FULL")]["res"])
            L += [
                f"- **{cname} : PASS** sur {len(passing)}/6 cellules — "
                f"meilleure S={best[0]:.0f} %/r={best[1]:.2f} : FULL "
                f"${cf['balance']:,.2f} vs contrôle ${fb['bal']:,.2f}, "
                f"DD {wstats(cf)['dd']:.1f} % vs {fb['dd']:.1f} %, "
                f"pire mois {wstats(cf)['worst']:+.1f} % vs "
                f"{fb['worst']:+.1f} %, liq {wstats(cf)['liq']}."]
        else:
            worst_tr = [(S, r) for S, r in CELLS]
            n_trainok = sum(verdicts[(cname, c)]["train_ok"] for c in worst_tr)
            L += [
                f"- **{cname} : PAS DE PASS** "
                f"({n_trainok}/6 passent TRAIN mais aucun confirmé VAL). "
                "Le garde wallet compresse-t-il vraiment ? Les chiffres "
                "au-dessus tranchent : le désengagement coupe aussi le "
                "rebond (coût de garde positif = profit manqué) — "
                "CONTEXTE/NUL, on ne l'empile pas."]
    L += ["", "Leçon enregistrée pour le registre : garde SIGNAL "
          "(sizing conditionnel cher, dd_cross nul) ≠ garde WALLET. "
          "Le garde wallet ne touche jamais au set de trades (tailles "
          "jamais nulles, liqs invariantes) — il ne fait que comprimer "
          "l'exposition quand le wallet saigne.", ""]
    out = REPORTS / f"wallet-dd-guard-{DATE}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[guard] rapport -> {out}")

    # ——— la synthèse console ———
    for cname, _ in configs:
        tb = verdicts[(cname, CELLS[0])]["tb"]
        print(f"[guard] {cname} TRAIN ctrl : ${tb['bal']:,.2f} "
              f"(DD {tb['dd']:.1f} %, pire {tb['worst']:+.1f} %)")
        for S, r in CELLS:
            vd = verdicts[(cname, (S, r))]
            t, v = vd["t"], vd["v"]
            cost = R[(cname, (S, r), "FULL")]["cost"]
            print(f"[guard]   S={S:.0f}/r={r:.2f}: T ${t['bal']:,.2f} "
                  f"DD {t['dd']:.1f} pire {t['worst']:+.1f} | "
                  f"V ${v['bal']:,.2f} DD {v['dd']:.1f} "
                  f"pire {v['worst']:+.1f} | coût ${cost['cost']:+,.2f} "
                  f"({cost['n_g']} tr) | "
                  f"{'PASS' if vd['pass'] else ('CONTEXTE' if vd['train_ok'] else 'NUL')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
