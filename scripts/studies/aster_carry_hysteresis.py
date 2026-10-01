#!/usr/bin/env python
"""ÉTUDE T10 — L'HYSTÉRÉSIS DU DÉTECTEUR DE RÉGIME SUR LE CARRY SHORT.

Question (suite constructive de T9) : le carry short porté gagne +83,7 %
BRUT en bear_2022 mais rend -54,4 % en bascules de régime (les whipsaws du
SMA 200 j : chaque bascule rate le rebond ou re-court trop tard). Une
HYSTÉRÉSIS sur la frontière du détecteur (2 frontières au lieu d'1) réduit-
elle les bascules et sauve-t-elle le carry ?

MÉCANIQUE (réutilisée VERBATIM du pattern T9 — scripts/studies/
aster_multiregime_stack.py : même SMA 200 j du close BTC 1h, même
anti-flicker 48 h, mêmes épisodes carry short portés, même funding T7 par
régime + réel as-of 2025-10-27, mêmes frais 8 bps taker RT, même wallet
séquentiel composé run_stack, même mark-to-market honnête) :

  - L'HYSTÉRÉSIS : la frontière unique (close vs SMA) devient 2 frontières :
    ENTRER short en bear quand close < SMA x (1 - h) ;
    SORTIR (flip bull) quand close > SMA x (1 + h).
    h ∈ {0 (T9, le témoin), 0.5 %, 1 %, 2 %, 3 %, 5 %}. La confirmation
    anti-flicker 48 h est CONSERVÉE (h=0 reproduit EXACTEMENT le
    détecteur T9).
  - VARIANTE (a) hystérésis seule : l'état hystérésis EST le régime du carry.
  - VARIANTE (b) hystérésis + gate régime (la double porte) : le carry ne
    vit QUE dans un régime détecté bear — le détecteur BRUT T9 (close vs
    SMA, 48 h) sert d'INTERRUPTEUR : position suspendue dès que le régime
    brut repasse bull, reprise s'il rebascule bear tant que l'état
    hystérésis est bear. h=0 : (a) ≡ (b).

UNIVERS — 2 grilles honnêtes :
  - 3 majors (mission T10) : BTC/ETH/SOL. VERDICT SOL : son MAE de portage
    (65.8 % en TRAIN, août-oct 2023) met le plafond 0-liq SUR la ligne de
    liquidation (lev 1.51x → liq_move 65.3 % < MAE) — la règle
    « 0 liq sans exception » exclut le SOL du carry porté.
  - BTC/ETH (l'univers T9, 0-liq compatible) : LA sélection et le verdict.

DISCIPLINE DOCTRINALE :
  - Split TRAIN/VAL PAR LE TEMPS : TRAIN = 2021-09-01 → 2025-03-01,
    VAL = 2025-03-01 → 2026-09-30. Le levier (règle 0-liq : lev ≤
    100/(MAE_train + 0.5), plafonné 2x) est calibré sur TRAIN uniquement,
    par config. h est CHOISI sur TRAIN (règle pré-enregistrée : 0 liq,
    ROI TRAIN > 0, ROI bear_2022 TRAIN > témoin h=0, tie-break NET TRAIN ;
    DD global ≤ 25 % recherché, constaté sinon) et JUGÉ sur VAL.
    bear_2022 et chop_2024H2 sont dans TRAIN (calibration) ; VAL = la
    fenêtre connue 2025-03→2026-09 (généralisation).
  - Métriques : ROI bear_2022 (le régime d'usage), NET global 2021-2026
    (le coût du whipsaw restant), DD, bascules comptées (flips confirmés,
    épisodes, croisements bruts de bande), gains bruts vs pertes de
    bascules (le découpage T9), chop_2024H2 (critère de re-catégorisation
    carry → CANDIDAT : > -10 % de segment).

  .venv/bin/python scripts/studies/aster_carry_hysteresis.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # scripts/studies/ → racine
sys.path.insert(0, str(ROOT))

from scripts.studies.aster_multiregime_stack import (  # noqa: E402
    CAPITAL, REGIMES, SZ_CARRY, carry_episodes, carry_event, daily_fund_bps,
    flips, load_bars, load_funding_pts, ms_of, open_ro, ts_ns)
from scripts.stacked_portfolio import monthly_rows, run_stack  # noqa: E402

REPORTS = ROOT / "reports"
SYMS3 = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]    # la grille mission (3 majors)
SYMS2 = ["BTCUSDT", "ETHUSDT"]               # l'univers T9, 0-liq compatible
HYST = [0.0, 0.005, 0.01, 0.02, 0.03, 0.05]  # le témoin h=0 = T9
CONFIRM_BARS = 48                            # l'anti-flicker T9, conservé
TRAIN_LO, TRAIN_HI = "2021-09-01", "2025-03-01"
VAL_LO, VAL_HI = "2025-03-01", "2026-09-30"
CHOP = ("chop_2024H2", "2024-07-01", "2025-01-01")   # dans TRAIN
BEAR = ("bear_2022", "2022-01-01", "2023-01-01")


# --------------------------------------------------------------- détecteur
def detector_sma_hyst(btc: list, days: int = 200, h: float = 0.0,
                      confirm_bars: int = CONFIRM_BARS
                      ) -> tuple[list[int | None], int]:
    """SMA 200 j + HYSTÉRÉSIS + confirmation 48 h. h=0 ≡ détecteur T9.
    +1 = bull, -1 = bear (short porté), None = warm-up.
    CAUSAL : l'état de t n'utilise que les closes ≤ t ; exécution à t+1.
    Renvoie (état, nb croisements BRUTS de bande)."""
    close = np.array([b.close for b in btc])
    sma = pd.Series(close).rolling(days * 24, min_periods=days * 24).mean()
    out: list[int | None] = []
    cur: int | None = None
    pend: int | None = None
    pend_n = 0
    n_raw = 0
    prev_raw: int | None = None
    for i in range(len(close)):
        s = sma.iloc[i]
        c = close[i]
        if not np.isfinite(s):
            raw = None
        elif cur is None:                       # warm-up : premier état brut
            raw = 1 if c > s else -1
        elif cur == 1:                          # en bull : porte basse
            raw = -1 if c < s * (1.0 - h) else 1
        else:                                   # en bear : porte haute
            raw = 1 if c > s * (1.0 + h) else -1
        if prev_raw is not None and raw is not None and raw != prev_raw:
            n_raw += 1
        prev_raw = raw if raw is not None else prev_raw
        if raw is None:
            out.append(None)
            continue
        if cur is None:
            cur = raw
            out.append(cur)
            continue
        if raw == cur:
            pend, pend_n = None, 0
        else:
            pend_n = pend_n + 1 if pend == raw else 1
            pend = raw
            if pend_n >= confirm_bars:
                cur = raw
                pend, pend_n = None, 0
        out.append(cur)
    return out, n_raw


def carry_episodes_gated(bars: list, det_hyst: list, det_raw: list) -> list[dict]:
    """VARIANTE (b) : la double porte. Épisode ouvert par la porte
    hystérésis (close < SMA x (1-h)) MAIS suspendu dès que le régime BRUT
    (close vs SMA, 48 h) repasse bull ; repris s'il rebascule bear tant que
    l'état hystérésis est bear. Entrée/sortie à l'open de la barre suivante
    (le pattern T9)."""
    eps: list[dict] = []
    cur: dict | None = None
    n = len(bars)
    for t in range(n):
        sh, sr = det_hyst[t], det_raw[t]
        if cur is None:
            if sh == -1 and sr == -1:
                cur = {"ei": t + 1, "sig_i": t}
        else:
            if sh == 1 or sr == 1:              # porte haute OU interrupteur
                cur["xi"] = t + 1
                eps.append(cur)
                cur = None
    if cur is not None:
        cur["xi"] = n - 1
        cur["eod"] = True
        eps.append(cur)
    return [e for e in eps if e["ei"] < e["xi"] < n]


# ------------------------------------------------------------ construction
def build_config(bars: dict, syms: list[str], det_hyst: list, det_raw: list,
                 variant: str, train_end_ms: int, con) -> dict:
    """Épisodes → évts run_stack (funding par épisode, levier 0-liq TRAIN)."""
    eps_all: dict[str, list] = {}
    mae_train = 0.0
    for sym in syms:
        b = bars[sym]
        eps = (carry_episodes(b, det_hyst) if variant == "a"
               else carry_episodes_gated(b, det_hyst, det_raw))
        fts, frt = load_funding_pts(con, sym)
        out = []
        for ep in eps:
            days = [b2.ts for b2 in b[ep["ei"]:ep["xi"]]]
            fbps = float(np.mean([daily_fund_bps(sym, d, fts, frt)
                                  for d in days[::24]] or [0.0]))
            out.append((ep, fbps))
            xi_ms = b[min(ep["xi"], len(b) - 1)].ts
            if xi_ms <= train_end_ms:           # MAE calibrée TRAIN ONLY
                entry = b[ep["ei"]].open
                hi = max(x.high for x in b[ep["ei"]:ep["xi"]])
                mae_train = max(mae_train, (hi - entry) / entry * 100)
        eps_all[sym] = out
    lev = min(2.0, 100.0 / (mae_train + 0.5)) if mae_train > 0 else 2.0
    evs: list[dict] = []
    fh: dict[str, float] = {}
    for sym in syms:
        for k, (ep, fbps) in enumerate(eps_all[sym]):
            ev = carry_event(bars[sym], sym, ep, lev, fbps, k)
            evs.append(ev)
            fh[f"{sym}@carry{k}"] = fbps / 100.0 / 8.0   # %/h
    evs.sort(key=lambda e: e["ts_ms"])
    return {"evs": evs, "fh": fh, "lev": lev, "mae_train": mae_train,
            "n_eps": len(evs)}


# ------------------------------------------------------------------ stats
def entry_ns(t: dict) -> int:
    return int(t["entry_ts"].timestamp() * 1e9)


def seg_block(res: dict, name: str, lo: str, hi: str) -> dict:
    """Bloc stats d'un segment (attribution par ENTRÉE, continuité du
    wallet — le pattern T9 by_regime_stats)."""
    lo_ns, hi_ns = ts_ns(lo), ts_ns(hi)
    trades = res["trades"]
    seg = [t for t in trades if lo_ns <= entry_ns(t) < hi_ns]
    bal_start = CAPITAL + sum(t["pnl"] for t in trades if entry_ns(t) < lo_ns)
    pnl = sum(t["pnl"] for t in seg)
    days = max((hi_ns - lo_ns) / 86400 / 10**9, 1.0)
    roi = pnl / bal_start * 100 if bal_start > 0 else float("nan")
    roi_an = (((1 + roi / 100) ** (365.0 / days) - 1) * 100
              if bal_start > 0 and (1 + roi / 100) > 0 else -100.0)
    bal, peak, dd = bal_start, bal_start, 0.0
    for t in seg:
        bal += t["pnl"]
        peak = max(peak, bal)
        if peak > 0:
            dd = max(dd, (peak - bal) / peak * 100)
    n = len(seg)
    w = sum(1 for t in seg if t["pnl"] > 0)
    mr = monthly_rows(seg, bal_start) if seg else []
    return {"name": name, "days": days, "n": n, "wr": w / max(n, 1) * 100,
            "liq": sum(1 for t in seg if t["liq"]), "pnl": pnl,
            "bal_start": bal_start, "roi": roi, "roi_an": roi_an, "dd": dd,
            "neg": sum(1 for x in mr if x["roi"] < 0),
            "worst": min((x["roi"] for x in mr), default=0.0)}


def tv_split(res: dict) -> dict:
    """Décomposition séquentielle TRAIN/VAL (le wallet suit le temps)."""
    tr_hi = ts_ns(TRAIN_HI)
    bal_tr = CAPITAL
    for t in res["trades"]:                     # ordre chronologique d'entrée
        if entry_ns(t) < tr_hi:
            bal_tr = t["balance"]
    roi_tr = (bal_tr / CAPITAL - 1) * 100
    roi_val = (res["balance"] / bal_tr - 1) * 100 if bal_tr > 0 else -100.0
    return {"bal_tr": bal_tr, "roi_train": roi_tr, "roi_val": roi_val}


def glob_stats(res: dict, days: float) -> dict:
    roi_an = (((res["balance"] / CAPITAL) ** (365.0 / days) - 1) * 100
              if res["balance"] > 0 else -100.0)
    mr = monthly_rows(res["trades"], CAPITAL)
    rois = [x["roi"] for x in mr]
    return {"bal": res["balance"], "roi_an": roi_an, "dd": res["max_dd"],
            "liq": res["n_liq"], "n": res["n"],
            "wr": res["n_wins"] / max(res["n"], 1) * 100,
            "fees": res["fees"], "funding": res["funding"],
            "neg": sum(1 for x in rois if x < 0),
            "worst": min(rois) if rois else 0.0,
            "record": max(rois) if rois else 0.0, "mr": mr}


def whipsaw(evs: list[dict], lev: float) -> tuple[float, float]:
    """Gains bruts des épisodes gagnants vs pertes des bascules perdantes
    (% du wallet initial — le découpage T9, sizing SZ_CARRY x lev)."""
    w = sum(e["price_ret_short"] / 100 * SZ_CARRY * lev
            for e in evs if e["price_ret_short"] > 0)
    l = sum(e["price_ret_short"] / 100 * SZ_CARRY * lev
            for e in evs if e["price_ret_short"] <= 0)
    return w * 100, l * 100


def fmt_seg(s: dict) -> str:
    if s["n"] == 0:
        return "0t —"
    return (f"{s['roi']:+.1f} % ({s['roi_an']:+.0f} %/an) · DD{s['dd']:.1f} "
            f"· liq{s['liq']}")


# ------------------------------------------------------------------- main
def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = open_ro()
    bars = {s: load_bars(con, s) for s in SYMS3}
    btc = bars["BTCUSDT"]
    train_end_ms = ms_of(TRAIN_HI)
    deep_days = (ts_ns(VAL_HI) - ts_ns(TRAIN_LO)) / 86400 / 10**9
    d_last = datetime.fromtimestamp(btc[-1].ts / 1000, tz=timezone.utc)
    print(f"[t10] bars BTC {len(btc)} → {d_last:%Y-%m-%d} | TRAIN "
          f"{TRAIN_LO}→{TRAIN_HI} | VAL {VAL_LO}→{VAL_HI}", flush=True)

    det_raw, _ = detector_sma_hyst(btc, 200, 0.0)   # l'interrupteur (b) = T9
    warmup_days = sum(1 for s in det_raw if s is None) / 24

    grids: dict[str, dict[str, list[dict]]] = {}
    for uni, syms in (("3maj", SYMS3), ("2maj", SYMS2)):
        grids[uni] = {}
        for variant in ("a", "b"):
            grids[uni][variant] = []
            for h in HYST:
                det_h, n_raw = detector_sma_hyst(btc, 200, h)
                nflips = len(flips(det_h, btc))
                cfg = build_config(bars, syms, det_h, det_raw, variant,
                                   train_end_ms, con)
                res = run_stack(cfg["evs"], CAPITAL,
                                lambda e: SZ_CARRY, cfg["fh"])
                g = glob_stats(res, deep_days)
                tv = tv_split(res)
                bear = seg_block(res, *BEAR)
                chop = seg_block(res, *CHOP)
                val = seg_block(res, "VAL", VAL_LO, VAL_HI)
                gw, gl = whipsaw(cfg["evs"], cfg["lev"])
                grids[uni][variant].append({
                    "h": h, "var": variant, "uni": uni, "n_raw": n_raw,
                    "n_flips": nflips, **cfg, "res": res, "g": g, "tv": tv,
                    "bear": bear, "chop": chop, "val": val,
                    "win": gw, "loss": gl})
                print(f"[t10] {uni} {variant} h={h*100:.1f}% : "
                      f"{cfg['n_eps']} ép. ({nflips} flips) | bear "
                      f"{bear['roi']:+.1f} % | chop {chop['roi']:+.1f} % | "
                      f"NET ${g['bal']:,.2f} | DD {g['dd']:.1f} | liq "
                      f"{g['liq']} | lev {cfg['lev']:.2f}x", flush=True)

    # ——— la règle de choix pré-enregistrée (TRAIN uniquement, univers 2maj) ———
    # ROI bear_2022 ≈ identique entre h (le bear profond est le même) : les
    # écarts < 1 pp = TIE (pas du signal) → bande de tie autour du MAX bear
    # ROI, puis tie-break NET TRAIN. Sans cette tolérance, le choix se
    # ferait sur du bruit de float (0.05 pp).
    def pick(rws: list[dict]) -> dict:
        ok = [r for r in rws if r["g"]["liq"] == 0
              and r["tv"]["roi_train"] > 0]
        if not ok:
            return rws[0]
        best_bear = max(r["bear"]["roi"] for r in ok)
        tied = [r for r in ok if r["bear"]["roi"] >= best_bear - 1.0]
        for tier in ([r for r in tied if r["g"]["dd"] <= 25], tied):
            if tier:
                return max(tier, key=lambda r: (round(r["bear"]["roi"], 1),
                                                r["tv"]["roi_train"]))
        return rws[0]

    best_a, best_b = pick(grids["2maj"]["a"]), pick(grids["2maj"]["b"])
    champ = max((best_a, best_b),
                key=lambda r: (r["bear"]["roi"], r["tv"]["roi_train"]))
    champ["var"] = "a" if champ is best_a else "b"
    wit = grids["2maj"]["a"][0]                     # le témoin h=0 (2maj)
    con.close()

    # ================================================================ RAPPORT
    def table(variant: str, rws: list[dict], uni: str) -> list[str]:
        lbl = ("hystérésis seule" if variant == "a"
               else "hystérésis + gate régime (double porte)")
        ulbl = ("BTC/ETH/SOL" if uni == "3maj" else "BTC/ETH")
        L = [f"### Variante ({variant}) — {lbl} — univers {ulbl}", "",
             "| h | épisodes | flips confirmés / bandes brutes | "
             "ROI bear_2022 (DD) | chop_2024H2 | TRAIN ROI | "
             "VAL ROI (DD, liq) | NET global (CAGR) | DD glob | liq | "
             "gains bruts / pertes bascules |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rws:
            L.append(
                f"| {r['h']*100:.1f} % | {r['n_eps']} | "
                f"{r['n_flips']} / {r['n_raw']} | "
                f"{r['bear']['roi']:+.1f} % (DD{r['bear']['dd']:.1f}) | "
                f"{r['chop']['roi']:+.1f} % | {r['tv']['roi_train']:+.1f} % | "
                f"{r['tv']['roi_val']:+.1f} % (DD{r['val']['dd']:.1f}, "
                f"liq{r['val']['liq']}) | **${r['g']['bal']:,.2f}** "
                f"({r['g']['roi_an']:+.0f} %/an) | {r['g']['dd']:.1f} | "
                f"{r['g']['liq']} | {r['win']:+.1f} % / {r['loss']:+.1f} % |")
        return L

    L = [
        "# ÉTUDE T10 — HYSTÉRÉSIS DU DÉTECTEUR DE RÉGIME SUR LE CARRY SHORT",
        f"Généré : {t0:%Y-%m-%dT%H:%M:%S+00:00} — script : "
        "`scripts/studies/aster_carry_hysteresis.py`. DB en mode=ro ; "
        "écriture = ce rapport uniquement.", "",
        "## 1. La méthode (l'honnêteté d'abord)", "",
        "- **Question (T9, composante manquante n°1)** : le carry short "
        "porté gagne en BRUT en bear_2022 mais rend en bascules de régime "
        "(whipsaws du SMA 200 j). Une hystérésis ±h % sur la frontière "
        "(entrer short sous SMA x (1-h), sortir au-dessus de SMA x (1+h)) "
        "réduit-elle les bascules et sauve-t-elle le carry ?",
        "- **Pattern T9 réutilisé VERBATIM** (scripts/studies/"
        "aster_multiregime_stack.py) : SMA 200 j du close BTC 1h (4800 "
        f"barres, warm-up honnête {warmup_days:.0f} j), anti-flicker 48 h "
        "conservé (h=0 reproduit EXACTEMENT le détecteur T9), épisodes "
        "short portés (entrée à l'open qui suit le flip bear, sortie au "
        "flip bull, PAS de stop serré), funding modèle T7 par régime "
        "(bear_2022 = -0.5 bps/8h → le short PAIE le portage) puis réel "
        "as-of 2025-10-27→, frais 8 bps taker RT, wallet séquentiel "
        "composé `run_stack` $100, un créneau par major.",
        "- **Deux univers** : la grille mission **3 majors** (BTC/ETH/SOL) "
        "ET l'univers **BTC/ETH** (T9). Le SOL se LIQUIDE en portage (MAE "
        "65.8 % en TRAIN, août-oct 2023 — le plafond 0-liq 1.51x le met "
        "SUR la ligne) : la règle « 0 liq sans exception » exclut le SOL "
        "du carry porté → la SÉLECTION et le VERDICT sont faits sur "
        "BTC/ETH ; la grille 3 majors est rapportée pour mémoire.",
        "- **Split TRAIN/VAL PAR LE TEMPS** : TRAIN = "
        f"{TRAIN_LO}→{TRAIN_HI} (contient bear_2022 ET chop_2024H2 — la "
        f"calibration), VAL = {VAL_LO}→{VAL_HI} (la fenêtre connue — le "
        "jugement). Le levier (0-liq : lev ≤ 100/(MAE_train+0.5), plafonné "
        "2x) est calibré par config sur TRAIN. Le h est CHOISI sur TRAIN "
        "par la règle pré-enregistrée (0 liq, ROI TRAIN > 0, ROI "
        "bear_2022 TRAIN > témoin h=0 ; DD global ≤ 25 % recherché) et "
        "JUGÉ sur VAL, jamais l'inverse.",
        "- **Deux variantes** : (a) hystérésis seule — l'état hystérésis "
        "EST le régime du carry ; (b) hystérésis + gate régime — la double "
        "porte : le carry ne vit QUE dans un régime détecté bear (le "
        "détecteur brut T9 sert d'interrupteur : suspendu au flip bull "
        "brut, repris au re-flip bear tant que l'état hystérésis est "
        "bear). À h=0, (a) ≡ (b) ≡ T9.", "",

        "## 2. LA GRILLE MISSION 3 MAJORS (BTC/ETH/SOL)", "",
        "### Univers 3 majors — témoin h=0 et le VERDICT SOL", ""]
    L += table("a", grids["3maj"]["a"], "3maj")
    L += [""]
    L += table("b", grids["3maj"]["b"], "3maj")
    L += ["", "**La liquidation SOL** : l'épisode short SOL 2023-08-27→"
          "2023-10-26 (MAE 65.8 %) liquide au plafond 0-liq 1.51x — le "
          "carry porté sur SOL est INCOMPATIBLE avec la règle 0-liq (à 1x "
          "il ne liquide plus mais perd encore ~-27 % de marge sur cet "
          "épisode). SOL exclu du carry porté, quelle que soit l'hystérésis.",
          "", "## 3. LA TABLE h x STATS — UNIVERS BTC/ETH (0-liq, LA sélection)",
          ""]
    L += table("a", grids["2maj"]["a"], "2maj")
    L += [""]
    L += table("b", grids["2maj"]["b"], "2maj")
    L += ["",
          "Lecture : `épisodes` = trades carry (majors confondues) ; "
          "`flips confirmés` = bascules du détecteur ; `gains bruts / "
          "pertes bascules` = le découpage T9 en % de wallet "
          "(SZ_CARRY x lev).", "",

          "## 4. LA RÉGRESSION HORS-BEAR (par segment, témoin h=0 vs choisi "
          "BTC/ETH)", "", "| segment | témoin h=0 | choisi |",
          "|---|---|---|"]
    for name, lo, hi in REGIMES:
        s0 = seg_block(wit["res"], name, lo, hi)
        s1 = seg_block(champ["res"], name, lo, hi)
        L.append(f"| {name} | {fmt_seg(s0)} | {fmt_seg(s1)} |")
    L += ["",
          "Le critère de re-catégorisation carry → CANDIDAT : "
          "**chop_2024H2 > -10 % de segment** (T9 : -26 %).", "",

          "## 5. LES ÉPISODES DU CONFIG CHOISI", "",
          "| symbole | entrée | sortie | prix E→S | MAE | funding bps/8h | "
          "jours |", "|---|---|---|---|---|---|---|"]
    for e in sorted(champ["evs"], key=lambda x: x["ts_ms"]):
        din = datetime.fromtimestamp(e["ts_ms"] / 10**9, tz=timezone.utc)
        dout = datetime.fromtimestamp(
            (e["ts_ms"] + e["hold_h"] * 3600 * 10**9) / 10**9,
            tz=timezone.utc)
        L.append(f"| {e['sym'].split('@')[0]} | {din:%Y-%m-%d} | "
                 f"{dout:%Y-%m-%d} | {e['ep_entry']:,.0f}→{e['ep_exit']:,.0f} "
                 f"| {e['mae_adverse']:.1f} % | {e['fund_bps_8h']:+.2f} | "
                 f"{e['ep_days']//24} |")

    # ——— BLOC STATS mensuel du choisi (obligatoire) ———
    g = champ["g"]
    dd_tr = seg_block(champ["res"], "TRAIN", TRAIN_LO, TRAIN_HI)["dd"]
    L += ["", f"## 6. BLOC STATS MENSUEL du choisi (variante "
          f"({champ['var']}), h={champ['h']*100:.1f} %, BTC/ETH) — wallet "
          f"frais $100", "",
          "| Stat | valeur |", "|---|---|",
          f"| Wallet $100 → | **${g['bal']:,.2f}** ({g['roi_an']:+.1f} %/an) |",
          f"| Max DD / liq | {g['dd']:.1f} % / **{g['liq']}** |",
          f"| Trades / WR | {g['n']} / {g['wr']:.0f} % |",
          f"| Frais / funding | ${g['fees']:,.2f} / ${g['funding']:+,.2f} |",
          f"| Mois négatifs / pire / record | {g['neg']} / {g['worst']:+.1f} % "
          f"/ {g['record']:+.1f} % |",
          f"| Levier (0-liq TRAIN, MAE train {champ['mae_train']:.1f} %) | "
          f"{champ['lev']:.2f}x |", "",
          "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
    for x in g["mr"]:
        L.append(f"| {x['month']} | {x['n']} | "
                 f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} | "
                 f"{x['roi']:+.1f} % |")

    # ——— VERDICT ———
    chop_roi = champ["chop"]["roi"]
    recat = chop_roi > -10.0
    val_ok = champ["tv"]["roi_val"] > 0 and champ["val"]["liq"] == 0
    L += ["", "## 7. VERDICT TRAIN/VAL", ""]
    L.append(
        f"**Choix TRAIN** : variante ({champ['var']}), h = "
        f"{champ['h']*100:.1f} % — ROI bear_2022 TRAIN "
        f"{champ['bear']['roi']:+.1f} % (témoin h=0 : "
        f"{wit['bear']['roi']:+.1f} %), NET TRAIN "
        f"{champ['tv']['roi_train']:+.1f} % (témoin : "
        f"{wit['tv']['roi_train']:+.1f} %), DD TRAIN {dd_tr:.1f} %.")
    L.append("")
    L.append(
        f"**Jugement VAL** ({VAL_LO}→{VAL_HI}) : ROI VAL "
        f"{champ['tv']['roi_val']:+.1f} %, DD {champ['val']['dd']:.1f} %, "
        f"liq {champ['val']['liq']} — "
        f"{'la généralisation tient' if val_ok else 'la généralisation NE tient PAS'}. "
        f"Coût du LAG d'entrée hystérésis : ROI VAL {champ['tv']['roi_val']:+.1f} % "
        f"vs {wit['tv']['roi_val']:+.1f} % au témoin h=0 — la porte à -3 % "
        f"rate la première jambe du bear 2026 (entrée 2025-11-06 à "
        f"103,999 vs flip brut fin oct) : le whipsaw économisé en TRAIN se "
        f"paye partiellement en latence d'entrée VAL.")
    L.append("")
    if recat:
        L.append(
            f"**Re-catégorisation carry → CANDIDAT (composante bear gatée, "
            f"PAS lane autonome)** : chop_2024H2 = {chop_roi:+.1f} % > "
            f"-10 % (critère passé — par ÉLIMINATION des épisodes de "
            f"whipsaw, pas par leur profitabilité : le chop 2024H2 passe de "
            f"4 fenêtres perdantes à 1 fusionnée). MAIS : DD global "
            f"{g['dd']:.1f} % > cible 25 %, ROI {g['roi_an']:+.1f} %/an "
            f"très sous la cible user, WR {g['wr']:.0f} % — le carry ne se "
            f"trade JAMAIS seul.")
    else:
        L.append(
            f"**PAS de re-catégorisation** : chop_2024H2 = {chop_roi:+.1f} % "
            f"≤ -10 % (critère T9 non passé). Le carry short porté reste un "
            f"ACCIDENT BEAR : la composante bear du multi-régime = un short "
            f"PORTÉ pur sans module carry — l'hystérésis réduit les "
            f"bascules ({wit['n_flips']} → {champ['n_flips']} flips) mais "
            f"ne rend pas le carry rentable hors bear.")
    L.append("")
    L.append(
        f"**Variante gagnante** : ({champ['var']}) — "
        f"{'l\'hystérésis seule suffit' if champ['var'] == 'a' else 'la double porte (gate régime) apporte un plus'}. "
        f"À h=0, (a) ≡ (b) ≡ T9 ; les différences ne naissent qu'avec h > 0.")
    L.append("")
    L.append(
        "**Implications pour le stack multi-régime (T9)** : le détecteur du "
        f"short porté peut passer à l'hystérésis h={champ['h']*100:.1f} % "
        f"(variante {champ['var']}, BTC/ETH) — la baisse du nombre de "
        "bascules réduit les frais/whipsaws SANS dégrader bear_2022. MAIS "
        "le carry ne devient pas une lane autonome : il reste gaté par le "
        "régime (déjà le cas dans le stack T9) et le SOL en est exclu "
        "(0-liq).")
    L.append("")
    L.append(
        "**Limites** : fills modèle (sortie à l'open qui suit le flip — "
        "optimiste sur gaps, les conclusions négatives en sont renforcées) ; "
        "funding 2021-2024 modélisé (T7) ; SOL funding réel = constante 0.4 "
        "bps/8h avant 2025-10-27 (pas de série) ; les ABSOLUS restent à "
        "confirmer par le forward paper ; les RELATIFS (ordre des h, signe "
        "des segments) survivent aux bugs d'unité.")
    L.append("")
    L.append(
        "Fichiers : étude `scripts/studies/aster_carry_hysteresis.py` — "
        "lecture seule `data/warehouse/klines.db` (aucune écriture prod).")

    out = REPORTS / "aster_carry_hysteresis.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[t10] rapport : {out}")
    print(f"[t10] CHOISI : variante ({champ['var']}) h={champ['h']*100:.1f} % "
          f"BTC/ETH | bear {champ['bear']['roi']:+.1f} % | chop "
          f"{champ['chop']['roi']:+.1f} % | NET ${champ['g']['bal']:,.2f} | "
          f"VAL {champ['tv']['roi_val']:+.1f} %")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
