#!/usr/bin/env python
# ARCHIVÉ (28/09) : verdict NUL/CONTEXTE — voir docs/20-registre-indicateurs.md
# (déplacé scripts/ → scripts/archive_studies/ : sys.path/ROOT ajustés d'un cran, ré-exécutable)
"""LA TAIL AU SIZING MACHINE — la confirmation pré-enregistrée (27/09).

Contexte : la TAIL du survivor (les events ATR > p90 jetés par le gate
du flux survivor) = WR 61,9 %, espérance +0,386 $/trade (flat 5 %),
corr < 0,3 avec les 4 flux, 2 rugs -0,2 % — CANDIDAT avec RÉSERVE DE
CONCENTRATION (top 3 trades = +18,14 $ sur +16,23 $ flat : hors eux,
négatif). Étape suivante pré-enregistrée : la confirmation AU SIZING
MACHINE RÉEL — le wallet 4 flux (--vol-spike ON, baseline $4,004.94 =
+3 905 %/an @ DD 24,8 %, 0 liq) + la TAIL en 5e flux au notional
machine 0,20·K (la convention EXACTE du survivor : the_machine.py
`return 0.20 * _K`), sensibilité ×0,5 (0,10·K).

CRITÈRES PRÉ-ENREGISTRÉS (AVANT tout chiffrage) :
  - PASS si ROI ≥ baseline ET DD ≤ baseline ET mois négatifs ≤ baseline
    ET 0 liquidation — jugé sur la config primaire 0,20·K (le 0,10·K
    = mesure de sensibilité à la concentration).
  - CONCENTRATION : si les 3 mêmes gros trades portent l'amélioration,
    BLOC STATS sans eux (les 3 events retirés du wallet) — l'edge
    survit-il hors de ses 3 gros ?
  - TRAIN/VAL PAR LE TEMPS 70/30 sur l'AJOUT : tail coupée 70/30,
    chaque moitié ajoutée au wallet, jugée sur VAL (espérance %/not
    du segment VAL et delta wallet VAL).

MÉTHODE (zéro ré-implémentation, zéro fichier du harnais édité) :
  - qubo_sizing.build_events/base_sizer = la réplique officielle
    bit-à-bit du wallet $4,004.94 (sanity exigée) ;
  - survivor_meme_test.survivor_meme = la partition gate p90 (la TAIL
    verbatim, zéro seuil bougé) ;
  - run_stack = le wallet séquentiel ; la TAIL a un CRÉNEAU distinct
    (strategy « survivor_meme_tail » = 1 slot busy run_stack), le même
    pattern que tous les tests.
DB du warehouse en LECTURE SEULE (wrapper sqlite3 mode=ro).

  .venv/bin/python scripts/tail_machine_confirm.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# ——— LECTURE SEULE : tout connect sur un .db du warehouse passe en
# uri mode=ro (garde-fou anti-écriture, sans toucher au harnais). ———
_orig_connect = sqlite3.connect


def _ro_connect(database, *a, **kw):
    try:
        s = str(database)
        if s.endswith(".db") and "warehouse" in s:
            return _orig_connect(f"file:{quote(s)}?mode=ro", uri=True, **kw)
    except (TypeError, ValueError):
        pass
    return _orig_connect(database, *a, **kw)


sqlite3.connect = _ro_connect

from scripts.portfolio_sim import KDB, monthly_rows  # noqa: E402
from scripts.qubo_sizing import K_ATT, base_sizer, build_events  # noqa: E402
from scripts.stacked_portfolio import CAPITAL, TAKER_RT, run_stack  # noqa: E402
from scripts.survivor_meme_test import survivor_meme  # noqa: E402

REPORTS = ROOT / "reports"
DATE = "2026-09-27"
BASELINE_REF = 4004.94       # l'ABSOLU de référence (rapport volspike 27/09)
NOT_TAIL = 0.20 * K_ATT      # le notional machine du survivor (0,178)
NOT_TAIL_HALF = 0.10 * K_ATT # la sensibilité ×0,5 (0,089)
SLOT = "survivor_meme_tail"  # le créneau TAIL distinct (1 slot run_stack)


def make_fn(base, notional: float):
    """Le sizing machine EXACT + la TAIL au notional fixe (comme le
    survivor : notional constant en % de balance, 1x)."""

    def fn(e, st=None):
        if e.get("strategy") == SLOT:
            return notional
        return base(e, st)

    return fn


def bloc_stats(w: dict) -> dict:
    mrows = monthly_rows(w["trades"], CAPITAL)
    rois = [r["roi"] for r in mrows]
    neg = [r["month"] for r in mrows if r["pnl"] < 0]
    prod = 1.0
    for r in mrows:
        prod *= (1 + r["roi"] / 100)
    gap_c = abs(prod - w["balance"] / CAPITAL)
    gap_p = abs(sum(r["pnl"] for r in mrows) - (w["balance"] - CAPITAL))
    return {"bal": w["balance"], "roi": (w["balance"] / CAPITAL - 1) * 100,
            "dd": w["max_dd"], "liq": w["n_liq"], "n": w["n"],
            "wr": w["n_wins"] / max(w["n"], 1) * 100, "mrows": mrows,
            "rec": max(rois) if rois else 0.0,
            "worst": min(rois) if rois else 0.0, "neg": len(neg),
            "neg_names": neg, "gap_c": gap_c, "gap_p": gap_p}


def net_ret_pct(e: dict, fh: dict[str, float]) -> float:
    """L'équation EXACTE de run_stack en % notionnel (code tilt)."""
    return (e["price_ret_short"]
            + e.get("fund_sign", 1) * fh.get(e["sym"], 0.0) * e["hold_h"]
            - e["fee_rt_bps"] / 100)


def cfg_row(name: str, b: dict) -> str:
    gc = "OK" if b["gap_c"] < 0.005 and b["gap_p"] < 0.01 else "✗ BUG"
    return (f"| {name} | ${b['bal']:,.2f} | {b['roi']:+,.0f} % "
            f"| {b['dd']:.1f} % | {b['liq']} | {b['n']} | {b['wr']:.1f} % "
            f"| {b['rec']:+.1f} % | {b['worst']:+.1f} % | {b['neg']} "
            f"| {b['gap_c']*100:.3f} % / ${b['gap_p']:.4f} {gc} |")


def iso_row(name: str, b: dict) -> str:
    return (f"| {name} | ${b['bal']:,.2f} | {b['roi']:+,.0f} % "
            f"| {b['dd']:.1f} % | {b['liq']} | {b['n']} | {b['wr']:.1f} % "
            f"| {b['rec']:+.1f} % | {b['worst']:+.1f} % | {b['neg']} |")


def month_table(b: dict) -> list[str]:
    out = ["| Mois | Trades | WR | Liq | PnL $ | ROI % |", "|---|---|---|---|---|---|"]
    for r in b["mrows"]:
        out.append(f"| {r['month']} | {r['n']} | {r['w']/max(r['n'],1)*100:.0f} % "
                   f"| {r['liq']} | {r['pnl']:+.2f} | {r['roi']:+.1f} % |")
    return out


def main() -> int:
    t0 = datetime.now(timezone.utc)
    print("[tail-mach] collecte réplique officielle 4 flux (build_events)…")
    all_ev, ctx, fh, counts = build_events()
    sizer_base = base_sizer(ctx)

    print("[tail-mach] partition survivor gate p90 (survivor_meme_test)…")
    con = sqlite3.connect(KDB)
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    raw, gated_part, tail, p90 = survivor_meme(con, fh_raw)
    con.close()
    part_ok = len(gated_part) == counts.get("survivor_long", -1)

    # ——— les 3 wallets du critère ———
    print("[tail-mach] wallets : baseline / +TAIL 0,20·K / +TAIL 0,10·K…")
    w_base = run_stack([dict(e) for e in all_ev], CAPITAL, sizer_base, fh)
    ev20 = sorted([dict(e) for e in all_ev] + [dict(e) for e in tail],
                  key=lambda e: e["ts_ms"])
    w_t20 = run_stack(ev20, CAPITAL, make_fn(sizer_base, NOT_TAIL), fh)
    w_t10 = run_stack(ev20, CAPITAL, make_fn(sizer_base, NOT_TAIL_HALF), fh)
    b_base, b_t20, b_t10 = (bloc_stats(w) for w in (w_base, w_t20, w_t10))

    # ——— la concentration : les 3 gros trades de la TAIL (chemin 0,20·K) ———
    tail_tr = sorted([t for t in w_t20["trades"] if t["strategy"] == SLOT],
                     key=lambda t: t["pnl"], reverse=True)
    top3 = tail_tr[:3]
    top3_keys = {(t["sym"], int(t["entry_ts"].timestamp())) for t in top3}
    tail_iso = [e for e in tail
                if (e["sym"], e["ts_ms"] // 10**9) not in top3_keys]
    w_iso = run_stack(
        sorted([dict(e) for e in all_ev] + [dict(e) for e in tail_iso],
               key=lambda e: e["ts_ms"]),
        CAPITAL, make_fn(sizer_base, NOT_TAIL), fh)
    b_iso = bloc_stats(w_iso)
    pnl_top3 = float(sum(t["pnl"] for t in top3))
    pnl_tail = float(sum(t["pnl"] for t in tail_tr))

    # ——— TRAIN/VAL PAR LE TEMPS sur l'ajout (70/30 sur les events TAIL) ———
    tail_s = sorted(tail, key=lambda e: e["ts_ms"])
    cut = int(len(tail_s) * 0.7)
    segs = {}
    for name, part in (("TRAIN", tail_s[:cut]), ("VAL", tail_s[cut:])):
        rets = np.array([net_ret_pct(e, fh) for e in part])
        segs[name] = {"n": len(part), "n_mo": len({(e["ts_ms"] // (30 * 24 * 3600 * 10**9))
                                                  for e in part}),
                      "wr": float((rets > 0).mean() * 100) if len(rets) else 0.0,
                      "ex": float(rets.mean()) if len(rets) else 0.0}
        w_seg = run_stack(
            sorted([dict(e) for e in all_ev] + [dict(e) for e in part],
                   key=lambda e: e["ts_ms"]),
            CAPITAL, make_fn(sizer_base, NOT_TAIL), fh)
        segs[name]["dbal"] = w_seg["balance"] - w_base["balance"]
        segs[name]["dd"] = w_seg["max_dd"]
        segs[name]["liq"] = w_seg["n_liq"]
        # le delta mensuel de l'ajout sur les mois du segment
        seg_months = {monthly_rows([t], CAPITAL)[0]["month"]
                      for t in w_seg["trades"] if t["strategy"] == SLOT}
        segs[name]["months"] = sorted(seg_months)

    # ——— le critère pré-enregistré ———
    crit20 = (b_t20["roi"] >= b_base["roi"] and b_t20["dd"] <= b_base["dd"]
              and b_t20["neg"] <= b_base["neg"] and b_t20["liq"] == 0)
    crit10 = (b_t10["roi"] >= b_base["roi"] and b_t10["dd"] <= b_base["dd"]
              and b_t10["neg"] <= b_base["neg"] and b_t10["liq"] == 0)
    crit_iso = (b_iso["roi"] >= b_base["roi"] and b_iso["dd"] <= b_base["dd"]
                and b_iso["neg"] <= b_base["neg"] and b_iso["liq"] == 0)
    val_ok = segs["VAL"]["ex"] > 0 and segs["VAL"]["dbal"] > 0
    if crit20 and crit_iso and val_ok:
        verdict = ("PASS : la TAIL au sizing machine améliore le wallet "
                   "(ROI ≥, DD ≤, mois négatifs ≤, 0 liq), l'edge SURVIT "
                   "hors des 3 gros trades et l'ajout tient sur VAL.")
    elif crit20 and crit_iso:
        verdict = ("PASS-wallet / RÉSERVE VAL : critère wallet OK et edge "
                   "hors top-3 OK, mais l'ajout ne tient pas sur VAL.")
    elif crit20:
        verdict = ("PASS-fragile : le critère wallet OK MAIS porté par les "
                   "3 gros trades (hors eux le critère tombe).")
    elif crit10:
        verdict = ("CONTEXTE : le 0,20·K échoue, seule la demi-dose 0,10·K "
                   "passe — sensibilité à la concentration avérée.")
    else:
        verdict = ("FAIL : la TAIL au sizing machine dégrade le wallet "
                   "(ROI/DD/mois négatifs) — pas d'entrée au stack.")

    # ——— le rapport ———
    L = [
        "# LA TAIL AU SIZING MACHINE — la confirmation",
        f"{t0:%d/%m/%Y %H:%M} UTC — la TAIL du survivor (ATR > p90="
        f"{p90:.2f} %, {len(tail)} events) ajoutée en 5e flux au wallet "
        f"4 flux --vol-spike, au notional machine 0,20·K = "
        f"{NOT_TAIL:.3f} (convention EXACTE du survivor dans "
        f"the_machine.py), sensibilité ×0,5 = {NOT_TAIL_HALF:.3f}. "
        f"CRITÈRES PRÉ-ENREGISTRÉS (docstring, AVANT chiffrage) : "
        f"ROI ≥ baseline ET DD ≤ baseline ET mois négatifs ≤ baseline "
        f"ET 0 liq ; concentration isolée (BLOC STATS sans les 3 gros) ; "
        f"TRAIN/VAL 70/30 sur l'ajout, jugé sur VAL. Créneau TAIL "
        f"distinct (1 slot run_stack). Partition gate p90 : "
        f"{'OK bit-identique' if part_ok else '✗ ÉCART — BUG'} "
        f"(gated {len(gated_part)} vs machine {counts.get('survivor_long')}).",
        "",
        "## BLOC STATS STRICT — 3 configs côte à côte", "",
        "| Wallet | Balance | ROI/an | DD | Liq | Trades | WR | Record | "
        "Pire | Nég | Garde-fous |", "|---|---|---|---|---|---|---|---|---|---|---|",
        cfg_row("baseline 4 flux (réf $4,004.94)", b_base),
        cfg_row(f"+ TAIL 0,20·K ({NOT_TAIL:.3f})", b_t20),
        cfg_row(f"+ TAIL 0,10·K ({NOT_TAIL_HALF:.3f})", b_t10),
        "", f"Sanity baseline : ${b_base['bal']:,.2f} vs réf "
        f"${BASELINE_REF:,.2f} (écart ${abs(b_base['bal']-BASELINE_REF):.4f} "
        f"{'OK — bit-reproductible' if abs(b_base['bal']-BASELINE_REF) < 0.05 else '✗ ÉCART'}).",
        f"Delta +TAIL 0,20·K : **${b_t20['bal']-b_base['bal']:+,.2f}** ; "
        f"delta +TAIL 0,10·K : ${b_t10['bal']-b_base['bal']:+,.2f}.", "",
        "## LES TABLES MENSUELLES", ""]
    for name, b in (("baseline 4 flux", b_base), ("+ TAIL 0,20·K", b_t20),
                    ("+ TAIL 0,10·K", b_t10)):
        L += [f"### {name} — {b['neg']} mois négatifs"
              f" ({', '.join(b['neg_names']) if b['neg_names'] else 'aucun'})", ""]
        L += month_table(b)
        L += [""]

    L += ["## LA CONCENTRATION — les 3 gros trades portent-ils tout ?", "",
          f"La TAIL au chemin 0,20·K contribue **${pnl_tail:+,.2f}** de "
          f"PnL de trades dans le wallet ; les 3 meilleurs en portent "
          f"**${pnl_top3:+,.2f}** ({pnl_top3/pnl_tail*100 if pnl_tail else 0:.0f} %).", "",
          "| # | Symbole | Entrée | PnL $ |", "|---|---|---|---|"]
    for t in top3:
        L.append(f"| {tail_tr.index(t)+1} | {t['sym']} "
                 f"| {t['entry_ts']:%Y-%m-%d} | {t['pnl']:+.2f} |")
    L += ["", "### BLOC STATS SANS les 3 gros (events retirés du wallet)", "",
          "| Wallet | Balance | ROI/an | DD | Liq | Trades | WR | Record | "
          "Pire | Nég |", "|---|---|---|---|---|---|---|---|---|---|",
          iso_row(f"+ TAIL 0,20·K SANS top-3 ({len(tail_iso)} events)", b_iso),
          "", f"L'edge hors top-3 : delta wallet "
          f"${b_iso['bal']-b_base['bal']:+,.2f} vs baseline — "
          f"{'il SURVIT' if b_iso['bal'] > b_base['bal'] else 'il NE SURVIT PAS'} "
          f"(critère complet sans top-3 : "
          f"{'OK' if crit_iso else 'ÉCHOUÉ'}).", "",
          "## TRAIN/VAL PAR LE TEMPS sur l'AJOUT (70/30, jugé sur VAL)", "",
          "| Segment | N | Mois | WR net | Espérance %/not | Δ wallet $ | "
          "DD | Liq |", "|---|---|---|---|---|---|---|---|"]
    for name in ("TRAIN", "VAL"):
        s = segs[name]
        L.append(f"| {name} | {s['n']} | {len(s['months'])} | {s['wr']:.1f} % "
                 f"| {s['ex']:+.3f} % | {s['dbal']:+,.2f} | {s['dd']:.1f} % "
                 f"| {s['liq']} |")
    L += ["", f"Lecture : l'ajout tient sur VAL si espérance VAL > 0 et "
          f"Δ wallet VAL > 0 → "
          f"{'OUI' if val_ok else 'NON'} "
          f"(Δ TRAIN {segs['TRAIN']['dbal']:+,.2f} $ composé sur toute la "
          f"période ; Δ VAL = l'effet pur des {segs['VAL']['n']} events VAL, "
          f"le chemin étant identique au baseline avant le split).", "",
          "## LE VERDICT STRICT", "",
          f"- Critère pré-enregistré à 0,20·K : "
          f"{'PASS' if crit20 else 'FAIL'} (ROI {b_t20['roi']:+,.0f} vs "
          f"{b_base['roi']:+,.0f} %, DD {b_t20['dd']:.1f} vs "
          f"{b_base['dd']:.1f} %, nég {b_t20['neg']} vs {b_base['neg']}, "
          f"liq {b_t20['liq']}) ; à 0,10·K : {'PASS' if crit10 else 'FAIL'}.",
          f"- Concentration : edge hors top-3 "
          f"{'OK' if crit_iso and b_iso['bal'] > b_base['bal'] else 'NON confirmé'}.",
          f"- **{verdict}**", "",
          "## NEXT", ""]
    if crit20 and crit_iso:
        L += ["- La TAIL entre au stack comme 5e flux au notional 0,20·K "
              "uniquement sur décision user (la config officielle de la "
              "machine NE CHANGE PAS ce soir — un seul changement par nuit).",
              "- Forward paper : suivre les prochains events TAIL live "
              "(l'edge VAL est le juge final)."]
    elif crit10:
        L += ["- La demi-dose 0,10·K seule passe : proposer le 0,10·K à la "
              "décision user, la pleine dose 0,20·K est rejetée."]
    else:
        L += ["- Ne PAS ajouter la TAIL au stack au sizing machine "
              "(verdict FAIL ci-dessus) — la TAIL reste CONTEXTE au "
              "registre (elle n'était déjà pas dans le stack)."]
    L += ["- Le survivor machine reste EXACTEMENT ce qu'il est (gated p90) ; "
          "le garde ATR p90 n'est PAS retiré — c'est lui qui sépare le "
          "survivor viable du rug.",
          "- Garde-fous composé-des-mois OK sur les wallets du test "
          "(voir table)."]

    out = REPORTS / f"tail-machine-confirm-{DATE}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")

    print(f"[tail-mach] TAIL {len(tail)} events (p90 {p90:.2f} %), "
          f"partition {'OK' if part_ok else 'ÉCART'}")
    for name, b in (("baseline", b_base), ("+TAIL 0.20K", b_t20),
                    ("+TAIL 0.10K", b_t10), ("+TAIL sans top3", b_iso)):
        print(f"[tail-mach] {name}: ${b['bal']:,.2f} ({b['roi']:+,.0f} %/an), "
              f"DD {b['dd']:.1f} %, liq {b['liq']}, {b['neg']} mois négatifs")
    print(f"[tail-mach] TRAIN Δ {segs['TRAIN']['dbal']:+,.2f} $ "
          f"(ex {segs['TRAIN']['ex']:+.3f} %/not) | "
          f"VAL Δ {segs['VAL']['dbal']:+,.2f} $ "
          f"(ex {segs['VAL']['ex']:+.3f} %/not)")
    print(f"[tail-mach] verdict : {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
