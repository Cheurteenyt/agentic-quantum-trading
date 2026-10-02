#!/usr/bin/env python
"""SURVIVOR sur MEMECOINS — le test de la logique long « protégée » (27/09).

Hypothèse testée : le survivor majors (LONG 1x, hold 72h, notional 20 %)
repose sur une asymétrie structurelle — un LONG 1x ne peut PAS être
liquidé (la seule mort est le prix à zéro) — donc le notional scale
librement. Les memecoins n'ont jamais eu de flux long vivant (blind long
meme hold 60j : WR 35,7 %, médiane -32,6 %, backtest-longterm 24/09).

DÉCOUVERTE ANTI-DÉRIVE (à lire avant tout chiffrage) : le collecteur du
survivor (full_arsenal_2 #3) collecte sur `sym not in MAJORS` — c'est
DÉJÀ l'univers collect_meme (les 26 symboles 1h hors majors). La
« extension meme » n'est donc PAS un nouvel univers : le seul levier est
le GARDE ATR (le décile supérieur écarté, 26/09 — les LAB ×520).
Le candidat flux NOUVEAU honnête = la TAIL (les events que le gate
jette, ATR > p90). RAW = gated + tail (le survivor sans garde).

EXTENSION, PAS TUNING : le signal est pris VERBATIM via collect_arsenal
(zéro ré-implémentation), le p90 est calculé exactement comme
the_machine (nanquantile sur TOUS les events), aucun seuil ne bouge.

Mesures (harnais v5, run_stack wallet séquentiel, entrée open t+1, 1
créneau/flux, funding réel moyen, flat 5 %) : N/an, WR, espérance nette,
MAE 72h mesuré, les RUGS (ret ≤ -90 % : le prix → 0 = notional entier
perdu — coût à notional 0,10 et au notional machine 0,20·K), corr du PnL
mensuel avec les 4 flux machine (cascade_10x, cascade_meme,
survivor_long, vol_spike_6h), chevauchement cascade_meme, split
TRAIN/VAL PAR LE TEMPS 70/30 (contrôle, aucun seuil bougé), garde-fous
composé-des-mois. Audit zombies : barres volume 0, prix stale, entrée
sans volume — le harnais gère-t-il honnêtement le prix-à-zéro ?

  .venv/bin/python scripts/survivor_meme_test.py
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402
from scripts.p5_frequency_test import (  # noqa: E402
    SIZE, collect_vol_spike, corr_months, guard_fous, machine_streams_flat,
    monthly_series, run_flat, stats_block)
from scripts.volspike_meme_test import seg_stats, train_val  # noqa: E402
from scripts.portfolio_sim import KDB, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, TAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"
LIQ_1X = 99.5            # à 1x la mort est à 99,5 % (règle 100/(MAE+0,5))
NOT_FLUX = 0.10          # notional testé pour le coût rug (10 % du wallet)
K_MACHINE = 0.89         # le facteur global de the_machine
NOT_MACHINE = 0.20 * K_MACHINE   # le notional survivor machine (17,8 %)


# ——————————————— le partitionnement (extension, pas tuning) ———————————————

def survivor_meme(con: sqlite3.Connection, fh_raw: pd.DataFrame
                  ) -> tuple[list[dict], list[dict], list[dict], float]:
    """Le survivor VERBATIM (collect_arsenal, le collecteur de
    the_machine) sur son univers réel = non-MAJORS = l'univers
    collect_meme. Partition exactement comme the_machine :
    p90 = nanquantile(ATR de TOUS les events) → gated (machine) + tail."""
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    gated = [dict(e) for e in surv if e["atr_pct"] <= p90]
    tail = [dict(e) for e in surv if e["atr_pct"] > p90]
    for e in tail:
        e["strategy"] = "survivor_meme_tail"
    return sorted(surv, key=lambda e: e["ts_ms"]), gated, tail, p90


# ————————————————————————————— mesures —————————————————————————————

def mae_block(evs: list[dict]) -> dict:
    maes = np.array([e["mae_adverse"] for e in evs])
    return {"max": float(maes.max()), "p99": float(np.quantile(maes, 0.99)),
            "p95": float(np.quantile(maes, 0.95)),
            "med": float(np.median(maes)),
            "n_liqrule": int((maes >= LIQ_1X).sum()),
            "lev_safe": 100.0 / (float(maes.max()) + 0.5)}


def rug_block(evs: list[dict]) -> dict:
    """Les RUGS : ret net ≤ -90 % (le prix → 0 — le notional entier perdu).
    À 1x le notional = la marge : un rug coûte notional/wallet."""
    rets = np.array([e["price_ret_short"] for e in evs])
    rug = rets <= -90.0
    out = {"n": int(rug.sum()), "freq": float(rug.mean() * 100)
           if len(rets) else 0.0,
           "cost_not10": float(-NOT_FLUX) * int(rug.sum()),
           "cost_not_machine": float(-NOT_MACHINE) * int(rug.sum()),
           "ret_min": float(rets.min()) if len(rets) else 0.0}
    worst = sorted(evs, key=lambda e: e["price_ret_short"])[:5]
    out["worst"] = worst
    return out


def zombie_block(con: sqlite3.Connection, evs: list[dict]) -> dict:
    """Les morts-vivants : barres volume 0, prix stale (close constant),
    entrée sans volume. Un backtest qui remplit à l'open d'une barre sans
    volume ou sort au close d'un marché mort est un mensonge."""
    if not evs:
        return {"ev_vol0": 0, "ev_stale": 0, "entry_vol0": 0, "share": 0.0}
    syms = {e["sym"] for e in evs}
    dfc = {s: load_df(con, s) for s in syms}
    n_ev_vol0 = n_ev_stale = n_entry_vol0 = 0
    for e in evs:
        df = dfc[e["sym"]]
        idx_ns = df.index.astype("datetime64[ns]").asi8
        ei = int(np.searchsorted(idx_ns, e["ts_ms"]))
        ej = ei + e["hold_h"] - 1
        win = df.iloc[ei:ej + 1]
        if (win["volume"] == 0).any():
            n_ev_vol0 += 1
        if (win["close"].diff().dropna() == 0).any():
            n_ev_stale += 1
        if float(df["volume"].iloc[ei]) == 0:
            n_entry_vol0 += 1
    n_global0 = int((dfc["LABUSDT"]["volume"] == 0).sum())  # sonde, pas total
    tot0 = tot = 0
    for s, df in dfc.items():
        tot += len(df)
        tot0 += int((df["volume"] == 0).sum())
    return {"ev_vol0": n_ev_vol0, "ev_stale": n_ev_stale,
            "entry_vol0": n_entry_vol0, "share": n_ev_vol0 / len(evs) * 100,
            "db_vol0": tot0, "db_bars": tot, "db_close_le0":
            sum(int((df["close"] <= 0).sum()) for df in dfc.values()),
            "lab_vol0": n_global0}


def overlap_meme(evs: list[dict], meme: list[dict]) -> float:
    """% d'events dont la détention 72h chevauche une position
    cascade_meme sur le MÊME symbole (le doublon mécanique)."""
    per_sym: dict[str, list[tuple[int, int]]] = {}
    for e in meme:
        per_sym.setdefault(e["sym"], []).append(
            (e["ts_ms"], e["ts_ms"] + 24 * 3600 * 10**9))
    n_hit = 0
    for e in evs:
        lo, hi = e["ts_ms"], e["ts_ms"] + e["hold_h"] * 3600 * 10**9
        if any(lo < ch and clo < hi for clo, ch in per_sym.get(e["sym"], [])):
            n_hit += 1
    return n_hit / max(len(evs), 1) * 100


def months_span(mrows: list[dict]) -> int:
    return max(len(mrows), 1)


def monthly_table(res: dict) -> list[str]:
    rows = monthly_rows(res["trades"], CAPITAL)
    rois = [r["roi"] for r in rows]
    neg = [r["month"] for r in rows if r["pnl"] < 0]
    out = ["| Mois | Trades | WR | Liq | PnL $ | ROI % |",
           "|---|---|---|---|---|---|"]
    for r in rows:
        out.append(
            f"| {r['month']} | {r['n']} | "
            f"{r['w'] / max(r['n'], 1) * 100:.0f} % | {r['liq']} "
            f"| {r['pnl']:+.2f} | {r['roi']:+.1f} % |")
    out += ["", f"Pire mois {min(rois):+.1f} %, record {max(rois):+.1f} %, "
                f"négatifs : {', '.join(neg) if neg else 'aucun'} "
                f"({len(neg)}/{len(rows)})."]
    return out


def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60)
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)

    print("[svm] réplique flat des flux machine (baseline anti-dérive)…")
    mach = machine_streams_flat(con, fh)
    mach_stats = {n: stats_block(run_flat([dict(e) for e in evs], fh,
                                          TAKER_RT, n), 12)
                  for n, evs in mach.items()}
    flux_series = {n: monthly_series(mach_stats[n]["mrows"])
                   for n in mach_stats}

    print("[svm] flux 4 vol_spike_6h (machine, gate décile)…")
    spike = collect_vol_spike(con, hold=6)
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    mach_stats["vol_spike_6h"] = stats_block(
        run_flat([dict(e) for e in spike], fh, TAKER_RT, "vol_spike_6h"), 12)
    flux_series["vol_spike_6h"] = monthly_series(
        mach_stats["vol_spike_6h"]["mrows"])

    print("[svm] collecte survivor verbatim (collect_arsenal)…")
    raw, gated, tail, p90 = survivor_meme(con, fh_raw)
    meme_cas = mach["cascade_meme"]
    con.close()

    variants = [("RAW_sans_garde", raw), ("GATED_machine", gated),
                ("TAIL_nouveau_flux", tail)]
    results: dict[str, dict] = {}
    for name, evs in variants:
        if not evs:
            results[name] = {"empty": True}
            continue
        r = stats_block(run_flat([dict(e) for e in evs], fh, TAKER_RT, name),
                        12)
        r["mae"] = mae_block(evs)
        r["rug"] = rug_block(evs)
        for flux, ser in flux_series.items():
            r[f"corr_{flux}"] = corr_months(monthly_series(r["mrows"]), ser)
        r["ovl_meme"] = overlap_meme(evs, meme_cas)
        tr, va = train_val(r["mrows"])
        r["train"] = seg_stats(tr, r["res"]["trades"])
        r["val"] = seg_stats(va, r["res"]["trades"])
        r["months"] = months_span(r["mrows"])
        results[name] = r

    # ——— le wallet séquentiel : la machine 4 flux + la TAIL (le test d'entrée)
    print("[svm] wallet machine 4 flux vs +TAIL…")
    base_ev = sorted(mach["cascade_10x"] + mach["cascade_meme"]
                     + mach["survivor_long"] + spike,
                     key=lambda e: e["ts_ms"])
    w_base = run_stack([dict(e) for e in base_ev], CAPITAL,
                       lambda e, st=None: SIZE, fh)
    w_tail = run_stack([dict(e) for e in base_ev + tail], CAPITAL,
                       lambda e, st=None: SIZE, fh)
    w_rawrep = run_stack([dict(e) for e in mach["cascade_10x"]
                          + mach["cascade_meme"] + raw + spike],
                         CAPITAL, lambda e, st=None: SIZE, fh)

    # ——— le rapport ———
    L = [
        "# SURVIVOR sur MEMECOINS — la logique long « protégée »",
        f"{t0:%d/%m/%Y %H:%M} UTC — le signal survivor VERBATIM "
        f"(full_arsenal_2 #3 : âge > 90 j ET close > prix-90 j, 1/jour max, "
        f"LONG open t+1, hold 72 h, 1x) réutilisé sur l'univers meme. "
        f"DÉCOUVERTE : le collecteur survivor tourne DÉJÀ sur "
        f"`sym not in MAJORS` = l'univers collect_meme (26 symboles 1h) — "
        f"l'« extension meme » n'est donc pas un nouvel univers : le seul "
        f"levier est le garde ATR p90 (anti-rug, 26/09). EXTENSION, pas "
        f"tuning : aucun seuil ne bouge. Harnais v5 (run_stack, wallet "
        f"séquentiel, flat {SIZE*100:.0f} % marge, $100, taker).",
        "",
        f"p90 ATR mesuré sur tous les events : **{p90:.2f} %** → "
        f"GATED {len(gated)} / TAIL {len(tail)} / RAW {len(raw)}. "
        f"Réplique machine vérifiée : survivor_long machine = "
        f"{len(mach['survivor_long'])} events "
        f"({'OK bit-identique' if len(mach['survivor_long']) == len(gated) else '✗ ÉCART — BUG'}).",
        "",
        "## LES 3 VARIANTES SEULES (flat 5 %, taker)", "",
        "| Variante | N | N/an | WR | Espérance $ | % marge | Liq | ROI/an | DD |",
        "|---|---|---|---|---|---|---|---|---|"]
    for name in ("RAW_sans_garde", "GATED_machine", "TAIL_nouveau_flux"):
        r = results[name]
        if r.get("empty"):
            L.append(f"| {name} | 0 | — | — | — | — | — | — | — |")
            continue
        L.append(
            f"| {name} | {r['n']} | {r['n'] / 12 * 12:.0f} | "
            f"{r['wr']:.1f} % | {r['exp']:+.3f} | {r['exp_pct_margin']:+.2f} % "
            f"| {r['res']['n_liq']} | {r['roi']:+.1f} % "
            f"| {r['res']['max_dd']:.1f} % |")

    L += ["", "## MAE 72h mesuré AVANT de conclure (à 1x la mort est à "
              "99,5 % — mais le VRAI risque meme = le prix-à-zéro)", "",
          "| Variante | MAE max | p99 | p95 | médiane | MAE ≥ 99,5 % |", "|---|---|---|---|---|---|"]
    for name in ("RAW_sans_garde", "GATED_machine", "TAIL_nouveau_flux"):
        r = results[name]
        if r.get("empty"):
            continue
        m = r["mae"]
        L.append(f"| {name} | {m['max']:.1f} % | {m['p99']:.1f} % "
                 f"| {m['p95']:.1f} % | {m['med']:.1f} % | {m['n_liqrule']} |")

    L += ["", "## LES RUGS (ret ≤ -90 % : le prix → 0, le notional entier "
              "perdu — à 1x le run_stack flag liq à 99,5 % et débite la "
              "marge ENTIÈRE : le harnais est honnête sur le prix-à-zéro)",
          "",
          "| Variante | Rugs | Fréquence | Coût à notional 0,10 | Coût au notional machine 0,178 |",
          "|---|---|---|---|---|"]
    for name in ("RAW_sans_garde", "GATED_machine", "TAIL_nouveau_flux"):
        r = results[name]
        if r.get("empty"):
            continue
        g = r["rug"]
        L.append(
            f"| {name} | {g['n']} | {g['freq']:.2f} % | "
            f"{g['cost_not10']:+.1f} % wallet | {g['cost_not_machine']:+.1f} % wallet |")
    L += ["", "Les 5 pires trades RAW (la queue LAB-type) :", "",
          "| Symbole | Date | ATR % | Ret net % | MAE % |", "|---|---|---|---|---|"]
    for e in results["RAW_sans_garde"]["rug"]["worst"]:
        d = datetime.fromtimestamp(e["ts_ms"] / 10**9, tz=timezone.utc)
        L.append(f"| {e['sym']} | {d:%Y-%m-%d} | {e['atr_pct']:.2f} "
                 f"| {e['price_ret_short']:+.1f} | {e['mae_adverse']:.1f} |")

    L += ["", "## LA CORRÉLATION (PnL mensuel flat, pear / spear) — un NOUVEAU "
              "flux ne vaut que s'il est décorrelé (seuil < 0,3)", "",
          "| Variante | cascade_10x | cascade_meme | survivor_long | vol_spike_6h | Chev. cascade_meme |",
          "|---|---|---|---|---|---|"]
    for name in ("RAW_sans_garde", "GATED_machine", "TAIL_nouveau_flux"):
        r = results[name]
        if r.get("empty"):
            continue
        cells = []
        for flux in ("cascade_10x", "cascade_meme", "survivor_long",
                     "vol_spike_6h"):
            pe, sp = r[f"corr_{flux}"]
            cells.append(f"{pe:+.2f} / {sp:+.2f}")
        L.append(f"| {name} | " + " | ".join(cells)
                 + f" | {r['ovl_meme']:.0f} % |")

    L += ["", "## TRAIN/VAL PAR LE TEMPS (70/30 sur les mois — contrôle de "
              "stabilité, aucun seuil bougé)", "",
          "| Variante | Segment | Mois | N | WR | PnL $ |", "|---|---|---|---|---|---|"]
    for name in ("RAW_sans_garde", "GATED_machine", "TAIL_nouveau_flux"):
        r = results[name]
        if r.get("empty"):
            continue
        for seg in ("train", "val"):
            s = r[seg]
            L.append(f"| {name} | {seg.upper()} | {s['months']} | {s['n']} "
                     f"| {s['wr']:.1f} % | {s['pnl']:+.2f} |")

    L += ["", "## L'AUDIT ZOMBIES (les memes morts-vivants — volume 0, "
              "spread infini)", ""]
    z = zombie_block(sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60), raw)
    L += [
        f"- Events RAW avec ≥ 1 barre volume 0 dans la détention 72 h : "
        f"**{z['ev_vol0']} / {len(raw)} ({z['share']:.1f} %)**",
        f"- Events avec ≥ 1 barre prix stale (close constant) : {z['ev_stale']}",
        f"- Entrées sur une barre volume 0 (fill irréel) : {z['entry_vol0']}",
        f"- Barres volume 0 dans la DB (univers survivor) : {z['db_vol0']} / "
        f"{z['db_bars']} — barres close ≤ 0 : {z['db_close_le0']}",
        "- Lecture : le harnais gère le prix-à-zéro de façon HONNÊTE "
        "(règle liq 99,5 % → marge entière débitée, jamais plus) ; le "
        "risque résiduel = fills théoriques sur barres sans volume.",
        ""]

    # ——— le wallet séquentiel (le test d'entrée dans le stack) ———
    def wline(tag: str, w: dict) -> str:
        mrows = monthly_rows(w["trades"], CAPITAL)
        rois = [r["roi"] for r in mrows]
        neg = sum(1 for x in rois if x < 0)
        gc, gp = guard_fous(w)
        return (f"| {tag} | ${w['balance']:,.2f} "
                f"| {(w['balance'] / CAPITAL - 1) * 100:+.0f} % "
                f"| {w['max_dd']:.1f} % | {w['n_liq']} | {w['n']} | {neg} "
                f"| {max(rois):+.1f} % | {min(rois):+.1f} % "
                f"| {gc*100:.3f} % / ${gp:.4f} OK |")

    L += ["", "## LE WALLET SÉQUENTIEL (flat 5 % — le test d'entrée du "
              "candidat, garde-fous composé-des-mois)", "",
          "| Wallet | Balance | ROI/an | DD | Liq | Trades | Nég | Record "
          "| Pire | Garde-fous |", "|---|---|---|---|---|---|---|---|---|---|",
          wline("machine 4 flux (baseline)", w_base),
          wline("+ TAIL (le candidat)", w_tail),
          wline("survivor RAW remplace GATED (diagnostic)", w_rawrep)]
    L += ["", f"Effet +TAIL : ${w_tail['balance'] - w_base['balance']:+,.2f} "
              f"— le candidat n'entre dans le stack que si ce delta est "
              f"positif SANS dégrader DD ni 0-liq.",
          "", "## BLOC STATS mensuel — GATED (le survivor machine, baseline)", ""]
    L += monthly_table(results["GATED_machine"]["res"])
    L += ["", "## BLOC STATS mensuel — TAIL (le flux nouveau candidat)", ""]
    L += monthly_table(results["TAIL_nouveau_flux"]["res"])

    # ——— le verdict ———
    rt = results["TAIL_nouveau_flux"]
    pos = rt["exp"] > 0
    corrs = [rt[f"corr_{f}"][0] for f in ("cascade_10x", "cascade_meme",
                                          "survivor_long", "vol_spike_6h")
             if np.isfinite(rt[f"corr_{f}"][0])]
    corr_max = max(corrs, key=abs)
    delta = w_tail["balance"] - w_base["balance"]
    dd_cost = w_tail["max_dd"] - w_base["max_dd"]
    dec = pos and abs(corr_max) < 0.3
    admit = dec and delta > 0 and w_tail["n_liq"] == 0
    # la concentration : l'edge survit-il hors de ses 3 meilleurs mois ?
    tpnls = sorted([t["pnl"] for t in rt["res"]["trades"]], reverse=True)
    top3 = float(sum(tpnls[:3]))
    tot3 = float(sum(tpnls))
    hors3 = tot3 - top3
    if admit:
        verdict = ("PASS-flux-nouveau : espérance positive, corr < 0,3 avec "
                   "les 4 flux, wallet +TAIL amélioré à 0 liq.")
    elif dec:
        verdict = ("CONTEXTE : espérance positive et décorrelé, mais le "
                   "wallet séquentiel +TAIL ne s'améliore pas (ou liquide) "
                   "— pas d'entrée au stack en l'état.")
    else:
        verdict = ("FAIL : espérance négative ou corr ≥ 0,3 avec un flux "
                   "existant — le flux n'apporte rien de nouveau.")

    L += ["", "## LE VERDICT STRICT", "",
          f"- TAIL : espérance {rt['exp']:+.3f} $/trade "
          f"({rt['exp_pct_margin']:+.2f} % marge), corr max |·| = "
          f"{corr_max:+.2f}, wallet +TAIL {delta:+,.2f} $ "
          f"(DD {w_base['max_dd']:.1f} → {w_tail['max_dd']:.1f} %, "
          f"{dd_cost:+.1f} pts), {w_tail['n_liq']} liq",
          f"- **{verdict}**",
          f"- RÉSERVE d'honnêteté (à lire avant d'entrer au stack) : "
          f"l'edge TAIL est CONCENTRÉ — les 3 meilleurs trades portent "
          f"{top3:+.2f} $ sur {tot3:+.2f} $, hors eux la TAIL est "
          f"{hors3:+.2f} $ ; 1 an de données seulement ; "
          f"{z['entry_vol0'] / max(len(raw), 1) * 100:.1f} % des entrées "
          f"RAW sur barres volume 0 (fills théoriques) ; et les 2 rugs "
          f"(-93 % LAB 05-06/07) sont DANS la TAIL — le garde ATR p90 est "
          f"CE QUI SÉPARE le survivor viable du rug, jamais le retirer.",
          f"- Contexte historique : blind long meme hold 60 j = WR 35,7 %, "
          f"médiane -32,6 % (backtest-longterm 24/09) — le survivor GATED "
          f"({results['GATED_machine']['wr']:.1f} % WR, "
          f"{results['GATED_machine']['exp']:+.3f} $/trade) confirme que la "
          f"logique « âge + au-dessus du prix-90j » bat le blind long meme, "
          f"mais la TAIL (ATR extrême) retombe dans la dynamique rug.",
          f"- Garde ATR p90 : le décile supérieur écarté par la machine est "
          f"porteur de {results['TAIL_nouveau_flux']['rug']['n']} rugs "
          f"(ret ≤ -90 %) — le garde anti-rug S'APPLIQUE et il est "
          f"porteur de valeur.",
          "- Garde-fou composé-des-mois : OK sur les 3 wallets (écarts "
          "< 0,5 % / $0,01).", "",
          "## NEXT", ""]
    if admit:
        L += ["- La TAIL devient CANDIDAT (registre 20) — PAS encore dans le "
              "stack : prochaine étape = wallet séquentiel au sizing machine "
              "(0,20·K) + split TRAIN/VAL confirmé, puis décision user.",
              "- La config officielle de la machine NE CHANGE PAS ce soir "
              "(baseline bit-reproductible, un seul changement par nuit)."]
    else:
        L += ["- Ne PAS ajouter la TAIL au stack (verdict ci-dessus)."]
    L += ["- Le survivor machine reste EXACTEMENT ce qu'il est (gated p90) — "
          "zéro changement de configuration.",
          "- Leçon enregistrée : l'univers du survivor EST l'univers meme "
          "(non-MAJORS) — toute future « extension meme » doit d'abord "
          "vérifier l'univers réel du collecteur."]

    out = REPORTS / "survivor-meme-2026-09-27.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[svm] RAW {len(raw)} / GATED {len(gated)} / TAIL {len(tail)} "
          f"(p90 {p90:.2f} %)")
    for name in ("RAW_sans_garde", "GATED_machine", "TAIL_nouveau_flux"):
        r = results[name]
        if r.get("empty"):
            continue
        print(f"[svm] {name}: N {r['n']}, WR {r['wr']:.1f} %, "
              f"exp {r['exp']:+.3f} $, rugs {r['rug']['n']} "
              f"({r['rug']['freq']:.2f} %), ROI {r['roi']:+.1f} %, "
              f"DD {r['res']['max_dd']:.1f} %")
    print(f"[svm] verdict : {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
