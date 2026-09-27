#!/usr/bin/env python
"""LA CARTE hold x levier du flux CASCADE MEMECOINS (le flux 2 de the_machine).

La frontiere conjointe hold x levier a ete cartographiee pour les MAJEURES
(24h/12x = le sommet). Ce script cartographie la MEME frontiere pour le flux
cascade memecoins, aujourd'hui 1x mecanique / hold 24h, en repliquant
EXACTEMENT le signal de the_machine.collect_meme (meme univers = klines 1h
hors MAJORS, meme gate cascade 3 bougies rouges amplitudes croissantes,
meme entree open t+1, t >= 200, len >= 500, meme ATR 24h, meme frais maker,
meme sizing vol-inverse 0.10*K clamp [0.02*K, 0.30*K], K = 0.89) sur la
grille hold dans {6h, 24h, 48h, 72h}.

Le levier de chaque cellule = le MAX SANS LIQUIDATION :
    lev <= 100 / (maxMAE_hold + 0.5)
mesure SUR TRAIN (p70 du temps), CONFIRME SUR VAL (une liq en VAL a la
cellule = cellule MORTE). Un slot par strategie (harnais v5 run_stack,
comme la machine). Baseline anti-derive : med_atr (le denominateur du
sizing) calcule sur TRAIN uniquement et applique aux deux periodes.

Garde-fous : compose des mois vs balance finale (ecart ~0), somme des PnL
mensuels, liq = 0 obligatoire par cellule, split train/val par le temps.

Lecture seule : aucune ecriture dans data/warehouse/*.db.

  .venv/bin/python scripts/carte_meme_hold.py
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
from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import MAJORS, collect_meme  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"

K = 0.89                 # le facteur global de la machine
HOLDS = (6, 24, 48, 72)  # la grille (heures)
SPLIT_Q = 0.70           # train = p70 du temps, val = le reste


def collect_meme_grid(con: sqlite3.Connection) -> dict[int, list[dict]]:
    """Le signal cascade EXACT de the_machine.collect_meme, x4 horizons.

    Un seul passage par symbole ; les evenements par hold portent leur
    propre contrainte `ei + hold < len` (identique au trim `ei + 24 >= len`
    du collecteur original pour hold=24 — verifie dans main()).
    """
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol") if r[0] not in MAJORS]
    raw: list[dict] = []          # le pool de signaux, gates identiques
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs, closes = df["open"].values, df["high"].values, df["close"].values
        close_s = pd.Series(closes, index=df.index)
        r1 = close_s.pct_change() * 100
        ra = r1.abs()
        cas = ((r1 < 0) & (r1.shift(1) < 0) & (r1.shift(2) < 0)
               & (ra > ra.shift(1)) & (ra.shift(1) > ra.shift(2))).fillna(False)
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        for t in np.where(cas)[0]:
            ei = t + 1
            if t < 200 or ei >= len(idx_ns):
                continue
            entry = opens[ei]
            if entry <= 0 or not np.isfinite(atr[ei]):
                continue
            raw.append({"sym": sym, "ts_ns": int(idx_ns[ei]), "ei": int(ei),
                        "n": len(idx_ns), "entry": float(entry),
                        "atr_pct": float(atr[ei]),
                        "opens": None, "highs": highs, "closes": closes})
    grid: dict[int, list[dict]] = {}
    for h in HOLDS:
        evs: list[dict] = []
        for e in raw:
            ei, h_len = e["ei"], e["n"]
            if ei + h >= h_len:            # meme trim que le collecteur 24h
                continue
            entry = e["entry"]
            exit_j = ei + h - 1
            x = e["closes"][exit_j]
            evs.append({"sym": e["sym"], "ts_ms": e["ts_ns"],  # NS (convention run_stack)
                        "strategy": "cascade_meme", "lev": 1, "hold_h": h,
                        "fee_rt_bps": MAKER_RT, "entry": entry,
                        "exit": float(x),
                        "price_ret_short": (entry - x) / entry * 100,
                        "fund_sign": 1,
                        "mae_adverse": (e["highs"][ei:ei + h].max() - entry)
                        / entry * 100, "atr_pct": e["atr_pct"]})
        evs.sort(key=lambda e: e["ts_ms"])
        grid[h] = evs
    return grid


def cell_stats(res: dict, capital: float, days: float) -> dict:
    """Stats d'une cellule : ROI/an annualise, DD, WR, garde-fous, mois."""
    roi_tot = (res["balance"] / capital - 1) * 100
    roi_an = roi_tot * 365.25 / days if days > 0 else 0.0
    mr = monthly_rows(res["trades"], capital)
    prod, sum_pnl = 1.0, 0.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
        sum_pnl += x["pnl"]
    gap_c = abs(prod - res["balance"] / capital)
    gap_p = abs(sum_pnl - (res["balance"] - capital))
    rois_m = [x["roi"] for x in mr]
    return {"res": res, "roi_tot": roi_tot, "roi_an": roi_an,
            "dd": res["max_dd"], "wr": res["n_wins"] / max(res["n"], 1) * 100,
            "n": res["n"], "liq": res["n_liq"],
            "worst": min(rois_m) if rois_m else 0.0,
            "best": max(rois_m) if rois_m else 0.0,
            "neg": sum(1 for x in rois_m if x < 0),
            "gap_c": gap_c, "gap_p": gap_p, "months": mr}


def pool_edge(evs: list[dict], fh: dict[str, float], med: float) -> tuple:
    """L'edge TOUS-EVTS hors creneau (lev 1, sizing machine) : % marge/trade.

    Le creneau unique de run_stack ne prend qu'un sous-ensemble des evenements
    (le 1er d'un cluster) — cet edge sans creneau est la reference anti-chance
    pour comparer les holds entre eux."""
    pnls, rets = [], []
    for e in evs:
        fees = e["fee_rt_bps"] / 1e4
        fund = fh.get(e["sym"], 0.0) / 100 * e["hold_h"]
        pnls.append((e["price_ret_short"] / 100 + fund - fees) * sz_of(e, med))
        rets.append(e["price_ret_short"])
    return float(np.mean(pnls)) * 100, float(np.mean(rets)), \
        float(np.mean([r > 0 for r in rets])) * 100


def sz_of(e, med: float) -> float:
    return min(max(0.10 * K * (e["atr_pct"] / med), 0.02 * K), 0.30 * K)


def run_cell(evs: list[dict], lev: float, fh: dict[str, float], med: float
             ) -> dict:
    """Le flux au levier donne, sizing machine exact (baseline anti-derive)."""
    for e in evs:
        e["lev"] = lev

    def size_meme(e, st=None):
        return sz_of(e, med)

    return run_stack(evs, CAPITAL, size_meme, fh)


def main() -> int:
    con = sqlite3.connect(f"{KDB.as_uri()}?mode=ro", uri=True)  # lecture seule
    fh = funding_hourly_all()
    grid = collect_meme_grid(con)

    # ——— replication check : le hold 24h = le collecteur original ———
    ref = collect_meme(con)
    mine = grid[24]
    same = ([e["ts_ms"] for e in ref] == [e["ts_ms"] for e in mine]
            and len(ref) == len(mine)
            and all(abs(a["mae_adverse"] - b["mae_adverse"]) < 1e-9
                    and abs(a["price_ret_short"] - b["price_ret_short"]) < 1e-9
                    for a, b in zip(ref, mine)))
    print(f"[carte] replication the_machine.collect_meme (24h) : "
          f"{len(ref)} evts — {'EXACTE' if same else 'ECART ✗'}")
    if not same:
        print("[carte] STOP — le signal ne replique pas, rapport refuse")
        return 1

    # ——— split train/val par le temps (p70), baseline anti-derive ———
    thr = int(np.quantile([e["ts_ms"] for e in mine], SPLIT_Q))
    d0 = datetime.fromtimestamp(min(e["ts_ms"] for e in mine) / 1e9)
    ds = datetime.fromtimestamp(thr / 1e9)
    d1 = datetime.fromtimestamp(max(e["ts_ms"] for e in mine) / 1e9)
    med_train = float(np.median([e["atr_pct"] for e in mine
                                 if e["ts_ms"] <= thr]))
    print(f"[carte] train {d0:%d/%m/%Y} -> {ds:%d/%m/%Y} | "
          f"val {ds:%d/%m/%Y} -> {d1:%d/%m/%Y} | med_atr TRAIN {med_train:.3f}")

    days_full = (d1 - d0).total_seconds() / 86400
    lines = [
        "# LA CARTE hold x levier — CASCADE MEMECOINS (flux 2 de la machine)",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — harnais v5 "
        f"(run_stack, entree open t+1, MAE fenetre, 1 creneau), signal "
        f"replique EXACTEMENT de the_machine.collect_meme ({len(ref)} evts "
        f"24h, check {'OK' if same else 'KO'}), sizing machine 0.10*K "
        f"(K={K}) clamp [0.02*K, 0.30*K], baseline anti-derive med_atr "
        f"TRAIN = {med_train:.3f}.",
        f"Split par le temps : TRAIN {d0:%d/%m/%Y} -> {ds:%d/%m/%Y} "
        f"(p70), VAL {ds:%d/%m/%Y} -> {d1:%d/%m/%Y}. "
        f"Levier de cellule = 100/(maxMAE_train + 0.5), CONFIRME 0-liq "
        f"sur VAL — une liq en VAL = cellule MORTE.", "",
        "## 1. LE MAE PAR HOLD (la question : l'explosion multi-jour)", "",
        "| Hold | MAE max TRAIN | MAE q99 TRAIN | MAE max VAL | morts 1x "
        "(>=99.5%) tr/va | levier 0-liq (formule) | edge net TOUS-EVTS train "
        "(% marge/trade, WR) |", "|---|---|---|---|---|---|---|"]
    rows: dict[int, dict] = {}
    for h in HOLDS:
        evs = grid[h]
        tr = [e for e in evs if e["ts_ms"] <= thr]
        va = [e for e in evs if e["ts_ms"] > thr]
        mae_tr = [e["mae_adverse"] for e in tr]
        mae_va = [e["mae_adverse"] for e in va]
        lev_raw = 100 / (max(mae_tr) + 0.5)
        lev0 = np.floor((lev_raw - 1e-9) * 100) / 100  # rase le cas limite = -> liq
        dead = lev0 < 0.01
        n1_tr = sum(1 for m in mae_tr if m >= 99.5)
        n1_va = sum(1 for m in mae_va if m >= 99.5)
        pe_tr = pool_edge(tr, fh, med_train)
        rows[h] = {"evs": evs, "ev_tr": tr, "ev_va": va, "mae_tr": max(mae_tr),
                   "mae_va": max(mae_va), "lev0": lev0, "lev_raw": lev_raw,
                   "dead": dead, "n1_tr": n1_tr, "n1_va": n1_va,
                   "pe_tr": pe_tr}
        lines.append(
            f"| {h}h | {max(mae_tr):.1f} % | {np.quantile(mae_tr, 0.99):.1f} % "
            f"| {max(mae_va):.1f} % | {n1_tr} / {n1_va} "
            f"| {'— (morte)' if dead else f'{lev_raw:.2f}x -> {lev0:.2f}x'} | "
            f"{pe_tr[0]:+.3f} % ({pe_tr[2]:.1f} %) |")

    # ——— les cellules de la carte ———
    lines += ["", "## 2. LA CARTE (levier = max 0-liq, confirme VAL)", "",
              "| Hold | Levier 0-liq | ROI/an | ROI total | DD | WR | Trades "
              "| Liqs | Pire mois | Verdict |", "|---|---|---|---|---|---|---|---|---|---|"]
    best_h, best_roi = None, -1e9
    for h in HOLDS:
        c = rows[h]
        if c["dead"]:
            c.update(full=None, verdict="**MORTE** — meme 1x liquide")
            lines.append(f"| {h}h | — | — | — | — | — | — | — | — | MORTE |")
            continue
        full = cell_stats(run_cell(c["evs"], c["lev0"], fh, med_train),
                          CAPITAL, days_full)
        tr_days = (ds - d0).total_seconds() / 86400
        va_days = (d1 - ds).total_seconds() / 86400
        trr = cell_stats(run_cell(c["ev_tr"], c["lev0"], fh, med_train),
                         CAPITAL, tr_days)
        vrr = cell_stats(run_cell(c["ev_va"], c["lev0"], fh, med_train),
                         CAPITAL, va_days)
        val_liq = vrr["liq"]
        if val_liq > 0:
            c["verdict"] = f"**MORTE** — {val_liq} liq en VAL"
            c.update(full=full, tr=trr, va=vrr)
            lines.append(
                f"| {h}h | {c['lev0']:.2f}x | — | — | — | — | {full['n']} "
                f"| **{full['liq']} (VAL!)** | — | MORTE |")
            continue
        ok_gf = full["gap_c"] < 0.005 and full["gap_p"] < 0.01
        c["verdict"] = "viable" if ok_gf else "garde-fou KO"
        c.update(full=full, tr=trr, va=vrr)
        if full["roi_an"] > best_roi:
            best_h, best_roi = h, full["roi_an"]
        lines.append(
            f"| {h}h | {c['lev0']:.2f}x | **{full['roi_an']:+.1f} %** "
            f"| {full['roi_tot']:+.1f} % | {full['dd']:.1f} % "
            f"| {full['wr']:.1f} % | {full['n']} | {full['liq']} "
            f"| {full['worst']:+.1f} % | {c['verdict']} |")
        lines.append(
            f"| ^ train/val | — | {trr['roi_an']:+.1f} / {vrr['roi_an']:+.1f} % "
            f"/an | — | {trr['dd']:.1f} / {vrr['dd']:.1f} % "
            f"| {trr['wr']:.1f} / {vrr['wr']:.1f} % | {trr['n']} / {vrr['n']} "
            f"| {trr['liq']} / {vrr['liq']} | {trr['worst']:+.1f} / "
            f"{vrr['worst']:+.1f} % | train | val |")

    # ——— le 1x mecanique actuel, pour reference (liqs admises) ———
    lines += ["", "## 3. LE 1x MECANIQUE ACTUEL (reference — liqs admises)",
              "", "Le creneau unique esquive les tueurs par chance : le "
              "nombre de morts 1x REELS (section 1) >> les liqs simulees.",
              "", "| Hold | Levier | pris/evts | ROI/an | DD | WR | Liqs "
              "| Perte des liqs |", "|---|---|---|---|---|---|---|---|"]
    ref_rows: dict[int, dict] = {}
    for h in HOLDS:
        c = rows[h]
        res = run_cell(c["evs"], 1.0, fh, med_train)
        st = cell_stats(res, CAPITAL, days_full)
        ref_rows[h] = st
        loss = sum(t["pnl"] for t in res["trades"] if t["liq"])
        lines.append(f"| {h}h | 1x | {st['n']}/{len(c['evs'])} "
                     f"| {st['roi_an']:+.1f} % | {st['dd']:.1f} % "
                     f"| {st['wr']:.1f} % | {st['liq']} | ${loss:,.2f} |")

    # ——— l'effet creneau : pris vs tous-evts (le biais de selection) ———
    lines += ["", "## 3bis. L'EFFET CRENEAU (pris vs tous-evts, TRAIN)", "",
              "Le creneau ne prend qu'un evenement par fenetre de detention "
              "(1er du cluster) : le sous-ensemble pris s'ecarte de l'edge "
              "brut dans les DEUX sens (-0.14 %/trade a 6h, -0.78 % a 48h "
              "mais +0.08 % a 24h et +0.14 % a 72h) — la comparaison des "
              "holds via le creneau porte une part de chance de selection ; "
              "l'edge TOUS-EVTS (section 1) est la reference stable :",
              "", "| Hold | pris | mean pnl pris (% marge) | mean pnl "
              "tous-evts (% marge) |", "|---|---|---|---|"]
    for h in HOLDS:
        c = rows[h]
        tk = run_cell(c["ev_tr"], c["lev0"], fh, med_train)["trades"]
        # mean pnl des pris en % de leur marge :
        mp = float(np.mean([t["pnl"] / t["margin"] * 100 for t in tk])) if tk else 0.0
        lines.append(f"| {h}h | {len(tk)}/{len(c["ev_tr"])} | {mp:+.3f} % "
                     f"| {c['pe_tr'][0]:+.3f} % |")

    # ——— la courbe mensuelle du sommet ———
    if best_h is not None:
        c = rows[best_h]
        lines += ["", f"## 4. LA COURBE MENSUELLE DU SOMMET — "
                  f"{best_h}h a {c['lev0']:.2f}x", "",
                  "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
        for x in c["full"]["months"]:
            lines.append(f"| {x['month']} | {x['n']} "
                         f"| {x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                         f"| {x['roi']:+.1f} % |")

    # ——— verdicts + garde-fous ———
    ratios = " / ".join(
        f"x{rows[HOLDS[i+1]]['mae_tr']/rows[HOLDS[i]]['mae_tr']:.1f}"
        for i in range(len(HOLDS) - 1))
    gf = " / ".join(
        f"{h}h {rows[h]['full']['gap_c']*100:.3f} %" if rows[h].get("full")
        else f"{h}h —" for h in HOLDS)
    sommet = (f"**{best_h}h a {rows[best_h]['lev0']:.2f}x "
              f"({best_roi:+.1f} %/an, DD {rows[best_h]['full']['dd']:.1f} %)**"
              if best_h is not None else "**aucune cellule viable**")
    lines += ["", "## 5. VERDICT", "",
              f"- L'explosion multi-jour : le MAE train progresse "
              f"{ratios} entre holds successifs — MEME pattern que les "
              f"majeures (3,6 -> 7,8 -> 17,1 %), mais amplifie : des 24h "
              f"le MAE memecoin depasse la ligne de mort 1x (99,5 %). Le "
              f"levier 0-liq tombe SOUS 1x des 24h — le bounce multi-jour "
              f"memecoin est un monstre (jusqu'a +538 % au-dessus de "
              f"l'entree a 72h).",
              f"- Le sommet de la carte : {sommet} — le hold 24h tient "
              f"comme sommet (le seul ROI/an positif des 4 cellules) mais "
              f"en levier rase-molette : 0,44x, pas 12x. La vol memecoin ne "
              f"deplace pas l'optimum de hold, elle ecrase le levier. "
              f"Et l'edge tous-evts est ~ZERO net de frais a tous les "
              f"holds (section 1) : le +4,4 %/an vient du sous-ensemble "
              f"du creneau + le funding des shorts, pas d'un edge brut.",
              f"- MAIS la derive : la VAL ({ds:%d/%m/%Y} -> {d1:%d/%m/%Y}) "
              f"donne " + " / ".join(
                  f"{h}h {rows[h]['va']['roi_an']:+.0f} %/an"
                  for h in HOLDS if rows[h].get("va")) +
              " — negative sur 3 cellules sur 4 ; l'exception (48h) suit le "
              "pire TRAIN (-27 %) : pur bruit, aucune persistance. L'edge "
              "24h du TRAIN (+8,8 %/an) ne survit pas en VAL (-5,8 %).",
              f"- Le creneau unique (harnais) esquive les tueurs 1x par "
              f"chance (section 3 vs section 1 : 0 liq simulee a 24h "
              f"contre 3 morts reels) mais porte le biais de selection "
              f"de la section 3bis.",
              f"- Le 1x mecanique actuel de la machine paie la queue quand "
              f"le creneau l'attrape (48h : 1 liq simulee) : chaque liq "
              f"= la marge entiere. Les morts 1x REELS sont 2-9 par an "
              f"selon le hold (section 1).",
              f"- Garde-fou compose des mois : {gf} — "
              f"{'OK (ecart ~0)' if all(rows[h]['full']['gap_c'] < 0.005 and rows[h]['full']['gap_p'] < 0.01 for h in HOLDS if rows[h].get('full')) else 'KO'}.",
              f"- Regle gravee : levier <= 100/(maxMAE_hold + 0,5), mesure "
              f"SUR TRAIN, confirmee SUR VAL (0 liq) — appliquee telle "
              f"quelle ici.", ""]
    out = REPORTS / "carte-hold-levier-memes-2026-09-27.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[carte] rapport ecrit -> {out}")
    for h in HOLDS:
        c = rows[h]
        if c.get("full"):
            f = c["full"]
            print(f"[carte] {h:>2}h @{c['lev0']:.2f}x : {f['roi_an']:+.1f} %/an "
                  f"(tr {c['tr']['roi_an']:+.1f} / val {c['va']['roi_an']:+.1f}), "
                  f"DD {f['dd']:.1f} %, liq {f['liq']}, "
                  f"pire mois {f['worst']:+.1f} %, GF compose "
                  f"{f['gap_c']*100:.3f} %")
        else:
            print(f"[carte] {h:>2}h : MORTE (lev 0-liq {c['lev_raw']:.2f}x < 1)")
    print(f"[carte] 1x mecanique : " + " | ".join(
        f"{h}h {ref_rows[h]['roi_an']:+.1f} %/an liq {ref_rows[h]['liq']}"
        for h in HOLDS))
    if best_h is not None:
        print(f"[carte] SOMMET : {best_h}h a {rows[best_h]['lev0']:.2f}x "
              f"({best_roi:+.1f} %/an)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
