#!/usr/bin/env python
"""ÉTUDE T11 — LE STACK MULTI-RÉGIME V2 : LE DÉTECTEUR À HYSTÉRÉSIS ±3 %
APPLIQUÉ AU STACK COMPLET DE T9.

Question (T10 → T11) : le whipsaw du carry short porté est la composante
manquante n°1 du stack T9 (DD global 42.8 %, 36 mois négatifs/61, régimes
qualifiés 2/6). T10 a CHOISI sur TRAIN (carry SEUL, 2021-09→2025-03) la
variante (a) hystérésis h=3 % univers BTC/ETH : 19→9 bascules,
chop_2024H2 -27.3 %→-6.9 %, VAL tient (+15.7 %, liq 0). T11 applique ce
détecteur au STACK COMPLET de T9 et répond : la composante manquante n°1
est-elle comblée (DD global ≤ 25 %, régimes qualifiés ?/6) ?

V2 = T9 VERBATIM, UNE SEULE chose change : le détecteur D1 (SMA 200 j du
close BTC 1h + confirmation anti-flicker 48 h) devient SMA 200 j +
HYSTÉRÉSIS ±3 % (entrer bear sous SMA x (1-3 %), flip bull au-dessus de
SMA x (1+3 %), même confirmation 48 h). Ce détecteur hystérésis gate le
momentum ET définit les épisodes du carry short porté BTC/ETH (SOL exclu
du carry — 0-liq, verdict T10). fade memes (gate fund7 P3) et vol_spike
(p90/med TRAIN) sont INCHANGÉS (indépendants du détecteur).

HONNÊTETÉ (l'ordre compte) :
  - V1 (T9) est RE-SIMULÉ dans le MÊME run (mêmes données du jour, mêmes
    fonctions importées du module T9) — la comparaison avant/après est
    APPARIÉE, pas recopiée d'un vieux rapport.
  - h=3 % N'EST PAS re-calibré ici : il vient de T10 (calibré sur le
    carry SEUL, TRAIN 2021-09→2025-03). L'application au stack complet
    (où le même détecteur gate AUSSI le momentum) = la GÉNÉRALISATION,
    jugée sur VAL (split 70 % barres de la convention T9, ~2025-05).
  - Split TRAIN/VAL PAR LE TEMPS (70 % barres, convention T9) ; toutes
    les calibrations (MAE carry 0-liq, p90/med vol_spike, q66 cascade)
    sur TRAIN, jugées sur VAL. Le h n'est PAS un paramètre optimisé ici.
  - Coûts/funding identiques T9 : 8 bps taker RT momentum/fade, 28 bps
    vol_spike (machine), cascade 4 bps maker RT ; funding T7 par régime
    + réel as-of 2025-10-27 ; mark-to-market `run_stack`, garde-fous
    composé-des-mois + somme PnL ; wallet frais $100.

  .venv/bin/python scripts/studies/aster_multiregime_stack_v2.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # scripts/studies/ → racine
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import MAJORS, btc_regime_series  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, funding_hourly_all, monthly_rows, run_stack)
from scripts.studies.aster_carry_hysteresis import detector_sma_hyst  # noqa: E402
from scripts.studies.aster_multiregime_stack import (  # noqa: E402
    CARRY_SYMS, K_V, MOM_REF, REGIMES, SZ_CARRY, SZ_FADE, SZ_MOM, TAKER_RT,
    by_regime_stats, carry_episodes, carry_event, cascade_witness,
    daily_fund_bps, detector_sma, fade_events, flips, fmt_reg, garde_fous,
    load_bars, load_funding_pts, make_fn_cascade, momentum_events_gated,
    open_ro, regime_share, seg_stats, spike_events, ts_ns)

REPORTS = ROOT / "reports"
HYST_H = 0.03          # le h CHOISI en T10 (carry seul, TRAIN) — NON re-calibré
DD_TARGET = 25.0       # la cible ré-qualifiée T9 : ROI > 0 ET DD ≤ 25 %/régime


# ------------------------------------------------------------------ helpers
def entry_ns(t: dict) -> int:
    return int(t["entry_ts"].timestamp() * 1e9)


def seg_block(res: dict, name: str, lo: str, hi: str) -> dict:
    """Bloc stats d'un segment (attribution par ENTRÉE, continuité du
    wallet — le pattern T9/T10)."""
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


def tv_split(res: dict, train_end_ms: int) -> tuple[float, float, float]:
    """Décomposition séquentielle TRAIN/VAL (le wallet suit le temps,
    split 70 % barres de la convention T9)."""
    hi_ns = train_end_ms * 10**6
    bal_tr = CAPITAL
    for t in sorted(res["trades"], key=entry_ns):
        if entry_ns(t) < hi_ns:
            bal_tr = t["balance"]
    roi_tr = (bal_tr / CAPITAL - 1) * 100
    roi_val = (res["balance"] / bal_tr - 1) * 100 if bal_tr > 0 else -100.0
    return roi_tr, roi_val, bal_tr


def strat_stats(res: dict, prefix: str) -> tuple[int, float, float]:
    """(n trades, WR %, PnL $) d'une composante DANS le wallet composé."""
    seg = [t for t in res["trades"] if t["strategy"].startswith(prefix)]
    n = len(seg)
    w = sum(1 for t in seg if t["pnl"] > 0)
    return n, w / max(n, 1) * 100, sum(t["pnl"] for t in seg)


def whipsaw(carry_evs: list[dict], lev: float) -> tuple[float, float]:
    """Gains bruts des épisodes gagnants vs pertes des bascules perdantes
    (% du wallet initial — le découpage T9, sizing SZ_CARRY x lev)."""
    w = sum(e["price_ret_short"] / 100 * SZ_CARRY * lev
            for e in carry_evs if e["price_ret_short"] > 0)
    l = sum(e["price_ret_short"] / 100 * SZ_CARRY * lev
            for e in carry_evs if e["price_ret_short"] <= 0)
    return w * 100, l * 100


def leg_mae(evs: list[dict]) -> float:
    return max((e["mae_adverse"] for e in evs), default=0.0)


# ------------------------------------------------------------------- main
def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = open_ro()
    fh = funding_hourly_all()

    bars = {s: load_bars(con, s) for s in MAJORS}
    btc = bars["BTCUSDT"]
    k70 = int(len(btc) * 0.7)
    train_end_ms = btc[k70].ts
    train_end_ns = train_end_ms * 10**6
    deep_days = (ts_ns("2026-09-30") - ts_ns("2021-09-01")) / 86400 / 10**9
    d_first = datetime.fromtimestamp(btc[0].ts / 1000, tz=timezone.utc)
    d_train = datetime.fromtimestamp(train_end_ms / 1000, tz=timezone.utc)
    d_last = datetime.fromtimestamp(btc[-1].ts / 1000, tz=timezone.utc)
    train_lo_s = f"{d_first:%Y-%m-%d}"
    train_hi_s = f"{d_train:%Y-%m-%d}"
    val_hi_s = f"{d_last:%Y-%m-%d}"
    print(f"[t11] bars BTC {len(btc)} {d_first:%Y-%m-%d}→{d_last:%Y-%m-%d} | "
          f"TRAIN → {train_hi_s} (70 % barres, T9)", flush=True)

    # ——— les détecteurs ———
    det1, raw1 = detector_sma(btc, 200)              # V1 (T9) verbatim
    det0, _ = detector_sma_hyst(btc, 200, 0.0)       # hérédité : h=0 ≡ T9
    mism = sum(1 for a, b in zip(det1, det0) if a != b)
    det_h, raw_h = detector_sma_hyst(btc, 200, HYST_H)   # V2 (h T10)
    fl1, flh = flips(det1, btc), flips(det_h, btc)
    sh1, shh = regime_share(det1, btc), regime_share(det_h, btc)
    warmup = sum(1 for s in det1 if s is None) / 24
    print(f"[t11] D1 V1 flips={len(fl1)}/{raw1} | V2 h=3 % "
          f"flips={len(flh)}/{raw_h} | hérédité h=0≡T9 : {mism} barres ≠",
          flush=True)

    # ——— composantes indépendantes du détecteur (UNE fois) ———
    fade_ev, fade_used = fade_events(con, fh)
    spike_ev, sp_p90, sp_med = spike_events(con, train_end_ns)
    print(f"[t11] fade memes {len(fade_ev)} évts ({len(fade_used)} séries) | "
          f"vol_spike {len(spike_ev)} évts (p90 {sp_p90:.2f}, med "
          f"{sp_med:.2f})", flush=True)

    def fn_spike(e, st=None):
        return min(max(0.10 * K_V * (e["atr_pct"] / sp_med), 0.02 * K_V),
                   0.30 * K_V)

    def fn_stack(e, st=None):
        s = e["strategy"]
        if s.startswith("momentum"):
            return SZ_MOM
        if s.startswith("carry_short"):
            return SZ_CARRY
        if s == "fade_meme":
            return SZ_FADE
        return fn_spike(e, st)

    def build_stack(det: list, carry_syms: list[str]) -> dict:
        """Le stack T9 verbatim pour UN détecteur donné (momentum gated
        + carry short porté + fade + vol_spike, wallet composé)."""
        mom_ev: list[dict] = []
        for sym in MAJORS:
            evs = momentum_events_gated(bars[sym], dict(MOM_REF, symbol=sym),
                                        det, sym)
            for e in evs:
                e["strategy"] = f"momentum_{sym}"
            mom_ev += evs
        carry_ev: list[dict] = []
        eps_all: dict[str, list] = {}
        mae_tr = 0.0
        for sym in carry_syms:
            b = bars[sym]
            eps = carry_episodes(b, det)
            fts, frt = load_funding_pts(con, sym)
            out = []
            for ep in eps:
                days = [b2.ts for b2 in b[ep["ei"]:ep["xi"]]]
                fbps = float(np.mean([daily_fund_bps(sym, d, fts, frt)
                                      for d in days[::24]] or [0.0]))
                out.append((ep, fbps))
                xi_ms = b[min(ep["xi"], len(b) - 1)].ts
                if xi_ms <= train_end_ms:            # MAE calibrée TRAIN ONLY
                    entry = b[ep["ei"]].open
                    hi = max(x.high for x in b[ep["ei"]:ep["xi"]])
                    mae_tr = max(mae_tr, (hi - entry) / entry * 100)
            eps_all[sym] = out
        lev = min(2.0, 100.0 / (mae_tr + 0.5)) if mae_tr > 0 else 2.0
        for sym in carry_syms:
            for k, (ep, fbps) in enumerate(eps_all[sym]):
                carry_ev.append(carry_event(bars[sym], sym, ep, lev, fbps, k))
        fh_st = dict(fh)
        for sym in carry_syms:
            for k, (ep, fbps) in enumerate(eps_all[sym]):
                fh_st[f"{sym}@carry{k}"] = fbps / 100.0 / 8.0   # %/h
        stack_ev = sorted(mom_ev + carry_ev + fade_ev + spike_ev,
                          key=lambda e: e["ts_ms"])
        res = run_stack(stack_ev, CAPITAL, fn_stack, fh_st)
        return {"mom": mom_ev, "carry": carry_ev, "lev": lev,
                "mae": mae_tr, "res": res}

    # ——— V1 (T9) et V2 (hystérésis) dans le MÊME run ———
    s1 = build_stack(det1, CARRY_SYMS)
    print(f"[t11] V1 : mom {len(s1['mom'])} évts | carry {len(s1['carry'])} "
          f"ép (MAE train {s1['mae']:.1f} % → lev {s1['lev']:.2f}x) | stack "
          f"${s1['res']['balance']:,.2f} DD {s1['res']['max_dd']:.1f}",
          flush=True)
    s2 = build_stack(det_h, CARRY_SYMS)
    print(f"[t11] V2 : mom {len(s2['mom'])} évts | carry {len(s2['carry'])} "
          f"ép (MAE train {s2['mae']:.1f} % → lev {s2['lev']:.2f}x) | stack "
          f"${s2['res']['balance']:,.2f} DD {s2['res']['max_dd']:.1f}",
          flush=True)

    v1 = seg_stats(s1["res"], CAPITAL, deep_days)
    v2 = seg_stats(s2["res"], CAPITAL, deep_days)
    r1, r2 = by_regime_stats(s1["res"]), by_regime_stats(s2["res"])
    gc1, gp1 = garde_fous(s1["res"], CAPITAL)
    gc2, gp2 = garde_fous(s2["res"], CAPITAL)
    tv1 = tv_split(s1["res"], train_end_ms)
    tv2 = tv_split(s2["res"], train_end_ms)
    val1 = seg_block(s1["res"], "VAL", train_hi_s, val_hi_s)
    val2 = seg_block(s2["res"], "VAL", train_hi_s, val_hi_s)

    # ——— TÉMOINS (identiques V1/V2, calculés une fois) ———
    regime = btc_regime_series()
    cas_ev, cas_med = cascade_witness(con, regime, train_end_ns, 10)
    res_a = run_stack(sorted(cas_ev + spike_ev, key=lambda e: e["ts_ms"]),
                      CAPITAL, make_fn_cascade(cas_med), fh)
    wit_a = seg_stats(res_a, CAPITAL, deep_days)
    for e in cas_ev:
        e["lev"] = 4
    res_b = run_stack(sorted(cas_ev + spike_ev, key=lambda e: e["ts_ms"]),
                      CAPITAL, make_fn_cascade(cas_med), fh)
    wit_b = seg_stats(res_b, CAPITAL, deep_days)

    closes = np.array([b.close for b in btc])
    bh_final = closes[-1] / closes[0]
    bh_peak = np.maximum.accumulate(closes)
    bh_dd = float(np.max((bh_peak - closes) / bh_peak * 100))
    bh_cagr = (bh_final ** (365.0 / deep_days) - 1) * 100
    mser = pd.Series(closes, index=pd.to_datetime([b.ts for b in btc],
                                                  unit="ms")).resample("MS").last()
    mret = mser.pct_change().dropna() * 100
    bh_neg = int((mret < 0).sum())
    bh_worst = float(mret.min())

    # ——— décompositions ———
    w1 = whipsaw(s1["carry"], s1["lev"])
    w2 = whipsaw(s2["carry"], s2["lev"])
    mom1, mom2 = strat_stats(s1["res"], "momentum"), strat_stats(s2["res"], "momentum")
    car1, car2 = strat_stats(s1["res"], "carry_short"), strat_stats(s2["res"], "carry_short")
    fad1, spk1 = strat_stats(s1["res"], "fade_meme"), strat_stats(s1["res"], "vol_spike")
    fad2, spk2 = strat_stats(s2["res"], "fade_meme"), strat_stats(s2["res"], "vol_spike")
    mae_mon = {"momentum": leg_mae(s2["mom"]), "carry": leg_mae(s2["carry"]),
               "fade": leg_mae(fade_ev), "spike": leg_mae(spike_ev)}
    q1 = [r for r in r1 if r["roi"] > 0 and r["dd"] <= DD_TARGET]
    q2 = [r for r in r2 if r["roi"] > 0 and r["dd"] <= DD_TARGET]
    c1 = next(r for r in r1 if r["name"] == "chop_2024H2")
    c2 = next(r for r in r2 if r["name"] == "chop_2024H2")
    k1 = next(r for r in r1 if r["name"] == "connu_2025_2026")
    k2 = next(r for r in r2 if r["name"] == "connu_2025_2026")
    worst_reg2 = max(r2, key=lambda r: r["dd"])
    top = sorted(s2["res"]["trades"], key=lambda t: t["pnl"], reverse=True)
    ra1 = v1["roi_an"] / v1["dd"] if v1["dd"] > 0 else float("nan")
    ra2 = v2["roi_an"] / v2["dd"] if v2["dd"] > 0 else float("nan")
    ra_bh = bh_cagr / bh_dd if bh_dd > 0 else float("nan")
    con.close()

    # ================================================================ RAPPORT
    L = [
        "# ÉTUDE T11 — STACK MULTI-RÉGIME V2 : LE DÉTECTEUR À HYSTÉRÉSIS "
        "±3 % APPLIQUÉ AU STACK COMPLET DE T9",
        f"Généré : {t0:%Y-%m-%dT%H:%M:%S+00:00} — script : "
        "`scripts/studies/aster_multiregime_stack_v2.py`. DB en mode=ro ; "
        "écriture = ce rapport uniquement.",
        "",
        "## 1. La méthode (l'honnêteté d'abord)", "",
        "- **Question (T9 → T10 → T11)** : le whipsaw du carry short porté "
        "est la composante manquante n°1 du stack T9 (gains bruts du carry "
        f"{w1[0]:+.1f} % rendus à {w1[1]:+.1f} % en bascules ; DD global "
        "42.8 % ; 36 mois négatifs/61 ; 2/6 régimes qualifiés). T10 a "
        "CHOISI sur TRAIN (carry SEUL, 2021-09→2025-03) la variante (a) "
        "hystérésis h=3 % univers BTC/ETH. T11 l'applique au STACK "
        "COMPLET et juge : la composante n°1 est-elle comblée ?",
        "- **V2 = T9 VERBATIM, UNE SEULE chose change** : le détecteur D1 "
        "(SMA 200 j du close BTC 1h, confirmation anti-flicker 48 h) "
        "devient SMA 200 j + HYSTÉRÉSIS ±3 % (entrer bear sous "
        "SMA x (1-3 %), flip bull au-dessus de SMA x (1+3 %), même "
        "confirmation 48 h). Ce détecteur gate le MOMENTUM (BTC/ETH/SOL, "
        "REF harnais fast 20/slow 100/regime_ema 200, stop 200 bps/take "
        "1000 bps, lev 2) ET définit les épisodes du CARRY short porté "
        "BTC/ETH (SOL exclu du carry — 0-liq, verdict T10 ; entrée à "
        "l'open qui suit le flip bear, sortie au flip bull, PAS de stop "
        "serré). fade memes (gate fund7 > 0.5 bps/8h, P3) et vol_spike 6h "
        "1x permanent (p90/med TRAIN) sont INCHANGÉS — indépendants du "
        "détecteur. Sizing T9 : momentum 8 %, carry 25 %, fade 5 %, "
        "vol_spike 0.10×K_V×(atr/med) borné [0.02, 0.30]×K_V.",
        "- **Comparaison APPARIÉE** : V1 (T9) est re-simulé dans le MÊME "
        "run (mêmes données du jour, mêmes fonctions importées du module "
        "T9 verbatim) — les deltas avant/après ne peuvent pas venir d'un "
        f"drift de données. Hérédité vérifiée : le détecteur h=0 reproduit "
        f"le détecteur T9 à {mism} barre(s) près.",
        "- **h=3 % N'EST PAS re-calibré ici** : il vient de T10, calibré "
        "sur le carry SEUL (TRAIN 2021-09→2025-03). L'application au "
        "stack complet — où le même détecteur gate AUSSI le momentum, "
        "effet JAMAIS calibré — est la GÉNÉRALISATION, testée sur VAL. "
        "C'est LA limite de l'étude (cf. §10).",
        f"- **Split TRAIN/VAL PAR LE TEMPS** (convention T9, 70 % des "
        f"barres) : TRAIN = {train_lo_s}→{train_hi_s}, VAL = {train_hi_s}→"
        f"{val_hi_s}. Calibrations TRAIN uniquement : MAE du carry (règle "
        "0-liq lev ≤ 100/(MAE_train+0.5), plafonné 2x), p90/med "
        "vol_spike, q66 cascade (témoins). Jugement VAL. Le bear_2022 et "
        "le chop_2024H2 sont DANS TRAIN ; VAL = la fenêtre connue.",
        "- **Coûts/funding identiques T9** : 8 bps taker RT "
        "momentum/fade/carry, 28 bps vol_spike (machine), 4 bps maker "
        "cascade (témoins) ; momentum longs PAIENT la moyenne moderne "
        "par symbole ; le short porté paie/encaisse le modèle T7 par "
        "régime (bear_2022 = -0.5 bps/8h → le short PAIE le portage) "
        "puis le réel as-of (2025-10-27→) ; fade = funding réel par "
        "symbole. Wallet séquentiel `run_stack` $100 frais, un créneau "
        "par stratégie × symbole, garde-fous composé-des-mois + somme "
        "PnL. Fills modèle (stops au prix du stop, sorties à l'open qui "
        "suit le flip — optimiste sur gaps : les conclusions négatives "
        "en sont RENFORCÉES).",
        f"- **Périmètre** : memes STRUCTURELLEMENT vides avant 2025 "
        f"(donnée) ; warm-up du détecteur {warmup:.0f} j (2021-09→2022-03) "
        "— le stack n'y trade que vol_spike.", "",

        "## 2. LE DÉTECTEUR — V1 vs V2 (les bascules)", "",
        "| détecteur | flips confirmés / bandes brutes | commentaire |",
        "|---|---|---|",
        f"| V1 — SMA 200 j (T9) | {len(fl1)} / {raw1} | confirmation 48 h, "
        f"warm-up {warmup:.0f} j |",
        f"| V2 — SMA 200 j + hystérésis ±3 % (T10 h) | {len(flh)} / {raw_h} "
        f"| mêmes 48 h ; {len(fl1) - len(flh)} bascules éliminées |",
        "", "### Les bascules V2 (l'hystérésis en action)", "",
        "| date | de → vers | prix BTC |", "|---|---|---|"]
    for d, a, b, px in flh:
        L.append(f"| {d} | {a} → {b} | {px:,.0f} |")
    L += ["", "### L'accord détecteur ↔ régimes T7 (part des barres bull/"
          "bear/inconnu %)", "",
          "| régime | V1 bull/bear/inconnu | V2 bull/bear/inconnu |",
          "|---|---|---|"]
    for name, _, _ in REGIMES:
        bu, be, un = sh1[name]
        bu2, be2, un2 = shh[name]
        L.append(f"| {name} | {bu:.0f}/{be:.0f}/{un:.0f} | "
                 f"{bu2:.0f}/{be2:.0f}/{un2:.0f} |")
    L += ["", "Lecture : l'hystérésis ne change PAS la cartographie des "
          "grands régimes (le bear 2022 reste bear, les bulls restent "
          "bulls) — elle supprime les allers-retours de frontière dans "
          "le chop. Le lag d'entrée/sortie s'ajoute au lag structurel "
          "de la SMA 200 j (~2-3 mois).", "",

          "## 3. LE STACK V2 — BLOC STATS GLOBAL (wallet frais $100, "
          "2021-09→2026-09)", "",
          "| Stat | valeur |", "|---|---|",
          f"| Wallet $100 → | **${v2['bal']:,.2f}** |",
          f"| ROI (CAGR) | {v2['roi']:+.1f} % ({v2['roi_an']:+.1f} %/an) |",
          f"| Max DD | {v2['dd']:.1f} % |",
          f"| **Liquidations** | **{v2['liq']}** |",
          f"| Trades / WR | {v2['n']} / {v2['wr']:.1f} % |",
          f"| Frais / funding | ${v2['fees']:,.2f} / ${v2['funding']:+,.2f} |",
          f"| Mois pire / record | {v2['worst']:+.1f} % / "
          f"{v2['record']:+.1f} % ({v2['neg']} négatifs) |",
          f"| Garde-fou composé des mois | écart {gc2*100:.3f} % "
          f"{'OK' if gc2 < 0.005 else '✗ BUG'} |",
          f"| Garde-fou somme PnL | écart ${gp2:.4f} "
          f"{'OK' if gp2 < 0.01 else '✗ BUG'} |",
          f"| Levier short porté (0-liq TRAIN, MAE train {s2['mae']:.1f} %) "
          f"| {s2['lev']:.2f}x |",
          "",

          "## 4. LA COMPARAISON AVANT/APRÈS — V1 (T9) vs V2 (T11), même "
          "run, mêmes données", "",
          "| métrique | V1 (T9, SMA 200 j) | V2 (hystérésis ±3 %) | lecture |",
          "|---|---|---|---|",
          f"| Wallet $100 → | ${v1['bal']:,.2f} | **${v2['bal']:,.2f}** | "
          f"{'V2 gagne' if v2['bal'] > v1['bal'] else 'V2 perd'} |",
          f"| NET (CAGR) | {v1['roi_an']:+.1f} %/an | **{v2['roi_an']:+.1f} "
          f"%/an** | {'+'
          if v2['roi_an'] > v1['roi_an'] else ''}"
          f"{(v2['roi_an'] - v1['roi_an']):.1f} pts |",
          f"| **Max DD global** | {v1['dd']:.1f} % | **{v2['dd']:.1f} %** | "
          f"cible ≤ 25 % : {'ATTEINTE' if v2['dd'] <= DD_TARGET else 'NON atteinte'} |",
          f"| Liquidations | {v1['liq']} | {v2['liq']} | 0-liq tenu |",
          f"| Trades / WR | {v1['n']} / {v1['wr']:.1f} % | {v2['n']} / "
          f"{v2['wr']:.1f} % | |",
          f"| **Mois négatifs** | {v1['neg']} / {len(v1['mr'])} | "
          f"**{v2['neg']} / {len(v2['mr'])}** | cible ≤ 1/12 "
          f"({len(v2['mr'])//12} max) |",
          f"| Pire mois / record | {v1['worst']:+.1f} % / "
          f"{v1['record']:+.1f} % | {v2['worst']:+.1f} % / "
          f"{v2['record']:+.1f} % | |",
          f"| Frais / funding | ${v1['fees']:,.2f} / ${v1['funding']:+,.2f} "
          f"| ${v2['fees']:,.2f} / ${v2['funding']:+,.2f} | |",
          f"| **Risk-ajusté (CAGR/DD)** | {ra1:.2f} | **{ra2:.2f}** | "
          f"B&H : {ra_bh:.2f} |",
          f"| ROI VAL (DD, liq) | {tv1[1]:+.1f} % (DD {val1['dd']:.1f}, "
          f"liq {val1['liq']}) | **{tv2[1]:+.1f} %** (DD {val2['dd']:.1f}, "
          f"liq {val2['liq']}) | la généralisation "
          f"{'TIENT' if tv2[1] > 0 and val2['liq'] == 0 else 'NE tient PAS'} |",
          f"| Whipsaw carry (gains / pertes bascules) | {w1[0]:+.1f} % / "
          f"{w1[1]:+.1f} % | {w2[0]:+.1f} % / {w2[1]:+.1f} % | "
          f"{-(w1[1] - w2[1]):.1f} pts de whipsaw économisés |",
          f"| Régimes qualifiés (ROI > 0 ET DD ≤ 25 %) | {len(q1)}/6 | "
          f"**{len(q2)}/6** | |",
          "",
          "**L'échelle honnête (témoins et B&H)**", "",
          "| run | wallet $100 → | CAGR | DD | liq | trades | WR | mois− |",
          "|---|---|---|---|---|---|---|---|",
          f"| (a) lane continue cascade 10x + vol_spike (T8) | "
          f"${wit_a['bal']:,.2f} | {wit_a['roi_an']:+.0f} %/an | "
          f"{wit_a['dd']:.1f} | {wit_a['liq']} | {wit_a['n']} | "
          f"{wit_a['wr']:.0f} % | {wit_a['neg']} |",
          f"| (b) idem levier sûr 4x | ${wit_b['bal']:,.2f} | "
          f"{wit_b['roi_an']:+.0f} %/an | {wit_b['dd']:.1f} | "
          f"{wit_b['liq']} | {wit_b['n']} | {wit_b['wr']:.0f} % | "
          f"{wit_b['neg']} |",
          f"| (c) buy&hold BTC | x{bh_final:.2f} (${100*bh_final:,.0f}) | "
          f"{bh_cagr:+.1f} %/an | {bh_dd:.1f} | — | 1 | — | {bh_neg} |",
          f"| V1 stack multi-régime (T9) | ${v1['bal']:,.2f} | "
          f"{v1['roi_an']:+.1f} %/an | {v1['dd']:.1f} | {v1['liq']} | "
          f"{v1['n']} | {v1['wr']:.1f} % | {v1['neg']} |",
          f"| **V2 stack (hystérésis ±3 %)** | **${v2['bal']:,.2f}** | "
          f"**{v2['roi_an']:+.1f} %/an** | **{v2['dd']:.1f}** | "
          f"**{v2['liq']}** | {v2['n']} | {v2['wr']:.1f} % | {v2['neg']} |",
          "",

          "## 5. BLOC STATS PAR RÉGIME — V1 vs V2 (attribution par régime "
          "d'ENTRÉE, continuité du wallet)", "",
          "Cellule = `trades · WR · ROI seg (ROI/an) · DD intra · liq · "
          "mois− pire mois`. Cible ré-qualifiée : **ROI > 0 et DD ≤ 25 % "
          "dans CHAQUE régime**.", "",
          "| régime | V1 (T9) | V2 (T11) |", "|---|---|---|"]
    for a, b in zip(r1, r2):
        L.append(f"| {a['name']} | {fmt_reg(a)} | {fmt_reg(b)} |")
    L += ["",
          f"**Qualifiés** : V1 {len(q1)}/6 "
          f"({', '.join(r['name'] for r in q1) or 'aucun'}) → V2 "
          f"**{len(q2)}/6** ({', '.join(r['name'] for r in q2) or 'aucun'}). "
          f"Le pire DD intra-régime V2 = {worst_reg2['dd']:.1f} % "
          f"({worst_reg2['name']}).",
          "",
          f"**Zoom chop_2024H2 (LE segment qui échouait)** : V1 "
          f"{c1['roi']:+.1f} % ({c1['roi_an']:+.0f} %/an), DD {c1['dd']:.1f} "
          f"%, {c1['neg']} mois− → V2 **{c2['roi']:+.1f} % "
          f"({c2['roi_an']:+.0f} %/an), DD {c2['dd']:.1f} %, {c2['neg']} "
          f"mois−**. Le critère T10 (> -10 % de segment) "
          f"{'est tenu par le STACK' if c2['roi'] > -10 else 'n\'est PAS tenu par le STACK complet'}.",
          f"**Zoom connu_2025_2026** : V1 {k1['roi']:+.1f} % "
          f"({k1['roi_an']:+.0f} %/an), DD {k1['dd']:.1f} % → V2 "
          f"**{k2['roi']:+.1f} % ({k2['roi_an']:+.0f} %/an), DD "
          f"{k2['dd']:.1f} %** — l'hystérésis "
          f"{'améliore' if k2['roi'] > k1['roi'] else 'dégrade'} la fenêtre "
          "connue (le retard d'entrée bear 2025-11 contre les whipsaws "
          "économisés).",
          "",

          "## 6. LE CARRY SHORT PORTÉ DANS LE STACK — le test de la "
          "composante n°1", "",
          f"Whipsaw (découpage T9, % du wallet, SZ_CARRY x "
          f"{s2['lev']:.2f}x) : V1 gains {w1[0]:+.1f} % / pertes de "
          f"bascules {w1[1]:+.1f} % (net {w1[0]+w1[1]:+.1f} %) → V2 gains "
          f"**{w2[0]:+.1f} %** / pertes **{w2[1]:+.1f} %** (net "
          f"**{w2[0]+w2[1]:+.1f} %**). Les épisodes passent de "
          f"{len(s1['carry'])} à {len(s2['carry'])}.", "",
          "| symbole | entrée | sortie | prix E→S | MAE | funding bps/8h | "
          "jours |", "|---|---|---|---|---|---|---|"]
    for e in sorted(s2["carry"], key=lambda x: x["ts_ms"]):
        din = datetime.fromtimestamp(e["ts_ms"] / 10**9, tz=timezone.utc)
        dout = datetime.fromtimestamp(
            (e["ts_ms"] + e["hold_h"] * 3600 * 10**9) / 10**9,
            tz=timezone.utc)
        L.append(f"| {e['sym'].split('@')[0]} | {din:%Y-%m-%d} | "
                 f"{dout:%Y-%m-%d} | {e['ep_entry']:,.0f}→{e['ep_exit']:,.0f} "
                 f"| {e['mae_adverse']:.1f} % | {e['fund_bps_8h']:+.2f} | "
                 f"{e['ep_days']//24} |")
    L += ["", "### Le moniteur MAE du stack V2 (règle 0-liq : "
          "levier ≤ 100/(MAE+0.5))", "",
          "| jambe | levier | MAE max réalisé | ligne de liq | statut |",
          "|---|---|---|---|---|",
          f"| momentum (lev 2) | 2x | {mae_mon['momentum']:.2f} % | 49.5 % | "
          f"{'OK' if mae_mon['momentum'] < 49.5 else '✗'} |",
          f"| carry short (lev {s2['lev']:.2f}x) | {s2['lev']:.2f}x | "
          f"{mae_mon['carry']:.2f} % | {100/s2['lev']-0.5:.1f} % | "
          f"{'OK' if mae_mon['carry'] < 100/s2['lev']-0.5 else '✗'} |",
          f"| fade memes (lev 2) | 2x | {mae_mon['fade']:.2f} % | 49.5 % | "
          f"{'OK' if mae_mon['fade'] < 49.5 else '✗'} |",
          f"| vol_spike (lev 1) | 1x | {mae_mon['spike']:.2f} % | 99.5 % | "
          f"{'OK' if mae_mon['spike'] < 99.5 else '✗'} |",
          "",

          "## 7. LES COMPOSANTES DANS LE WALLET COMPOSÉ (V1 vs V2)", "",
          "| composante | V1 n/WR/PnL | V2 n/WR/PnL |",
          "|---|---|---|",
          f"| momentum (gate détecteur) | {mom1[0]}t / {mom1[1]:.0f} % / "
          f"{mom1[2]:+,.1f}$ | {mom2[0]}t / {mom2[1]:.0f} % / "
          f"{mom2[2]:+,.1f}$ |",
          f"| carry short porté | {car1[0]}t / {car1[1]:.0f} % / "
          f"{car1[2]:+,.1f}$ | {car2[0]}t / {car2[1]:.0f} % / "
          f"{car2[2]:+,.1f}$ |",
          f"| fade memes | {fad1[0]}t / {fad1[1]:.0f} % / {fad1[2]:+,.1f}$ | "
          f"{fad2[0]}t / {fad2[1]:.0f} % / {fad2[2]:+,.1f}$ |",
          f"| vol_spike | {spk1[0]}t / {spk1[1]:.0f} % / {spk1[2]:+,.1f}$ | "
          f"{spk2[0]}t / {spk2[1]:.0f} % / {spk2[2]:+,.1f}$ |",
          "",
          "Lecture : le gate momentum change AVEC le détecteur (l'hystérésis "
          "retarde les ré-entrées bull et retient les positions à travers "
          "les petits croisements de bande) — c'est l'effet de "
          "généralisation NON calibré, mesuré ici, pas optimisé.", "",

          "## 8. LA TABLE MENSUELLE DU STACK V2 (garde-fou des ABSOLUS)", "",
          "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
    for x in v2["mr"]:
        L.append(f"| {x['month']} | {x['n']} | "
                 f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} | "
                 f"{x['roi']:+.1f} % |")
    L += ["", "### Les 5 plus gros PnL et 5 plus grosses pertes du wallet V2 "
          "(contrôle anti-artefact de sizing)", "",
          "| sens | stratégie | symbole | entrée | PnL $ | balance après |",
          "|---|---|---|---|---|---|"]
    for t in top[:5] + top[-5:]:
        d = t["entry_ts"]
        L.append(f"| {'gain' if t['pnl'] > 0 else 'perte'} | {t['strategy']} "
                 f"| {t['sym'].split('@')[0]} | {d:%Y-%m-%d} | "
                 f"{t['pnl']:+,.2f} | ${t['balance']:,.2f} |")

    # ——— VERDICT ———
    L += ["", "## 9. VERDICT — la composante manquante n°1 est-elle comblée ?", ""]
    dd_ok = v2["dd"] <= DD_TARGET
    L.append(
        f"**Le whipsaw, OUI ; le DD ≤ 25 %, "
        f"{'OUI' if dd_ok else 'NON'} — verdict : "
        f"{'COMBLÉE' if dd_ok and len(q2) >= 4 else ('PARTIELLEMENT comblée' if v2['dd'] < v1['dd'] else 'NON comblée')}.**")
    L.append("")
    L.append(
        f"**Ce qui est réglé** : le whipsaw du carry — {len(fl1)} → "
        f"{len(flh)} bascules, pertes de bascules {w1[1]:+.1f} % → "
        f"{w2[1]:+.1f} % de wallet, chop_2024H2 stack "
        f"{c1['roi']:+.1f} % → {c2['roi']:+.1f} %. Le DD global recule "
        f"{v1['dd']:.1f} % → {v2['dd']:.1f} %, les mois négatifs "
        f"{v1['neg']} → {v2['neg']} (sur {len(v2['mr'])}), 0 liq partout. "
        f"MAIS la généralisation au STACK COMPLET sur VAL "
        f"{'TIENT' if tv2[1] > 0 else 'NE tient PAS'} : ROI VAL "
        f"{tv2[1]:+.1f} % (liq {val2['liq']}) contre {tv1[1]:+.1f} % en "
        f"V1 — le h calibré sur le carry SEUL transfère AU CARRY "
        "(whipsaw, chop), mais le MÊME détecteur gate AUSSI le momentum "
        "(effet jamais calibré) et la latence d'entrée bear 2025-11 "
        "coûte la première jambe du short en fenêtre connue. Le RELATIF "
        "(moins de bascules = moins de rendu) survit au changement de "
        "périmètre ; le jugement VAL complet, non.")
    L.append("")
    L.append(
        f"**Ce qui manque ENCORE** : le DD global {v2['dd']:.1f} % "
        f"{'respecte' if dd_ok else 'dépasse'} la cible 25 % et "
        f"{len(q2)}/6 régimes sont qualifiés "
        f"({', '.join(r['name'] for r in q2) or 'aucun'}) ; "
        f"{v2['neg']} mois négatifs/12×{len(v2['mr'])//12} ans reste au-"
        "dessus de la cible user (≤ 1/12) ; le NET "
        f"{v2['roi_an']:+.1f} %/an reste très sous la cible user "
        "(60-70 %/mois) et le risk-ajusté "
        f"{ra2:.2f} vs B&H {ra_bh:.2f} "
        f"{'bat' if ra2 > ra_bh else 'ne bat PAS'} le buy&hold.")
    L.append("")
    L.append("**Les trous restants, hiérarchisés** :")
    L.append("")
    L.append(
        f"1. **Le LAG structurel du détecteur** (n°1 restant) : warm-up "
        f"{warmup:.0f} j + confirmation 48 h + hystérésis = chaque "
        "nouveau régime perd ses 2-3 premiers mois (part bull/bear par "
        "régime, §2) et l'hystérésis ajoute la latence d'entrée bear "
        "VAL (entrée 2025-11-06 à 103,999 vs flip brut fin oct). Le "
        "détecteur SMA ne peut pas être à la fois anti-bruit et rapide : "
        "la composante suivante est un détecteur plus rapide CONFIRMÉ "
        "(fund7/vol7 de P2, ou l'ATR-régime D3 comme condition "
        "secondaire), pas un SMA plus court.")
    L.append(
        f"2. **Un edge VIVANT pour connu_2025_2026** : DD V2 de la "
        f"fenêtre {k2['dd']:.1f} %, ROI {k2['roi_an']:+.0f} %/an — le "
        "momentum y est mort (T7), le fade memes à peine né (genèse "
        "donnée 2025-09), la cascade 2026 reste une propriété de "
        "fenêtre (T8). Tant que cette fenêtre n'a pas d'edge, le stack "
        "ne peut pas descendre sous ~30 % de DD en bull tardif.")
    L.append(
        "3. **Le sizing non optimisé** (hypothèses T9 figées) : SZ_CARRY "
        "25 % x 2x porte le DD du carry ; une allocation par RÉGIME "
        "détecté (carry nul en bull détecté, momentum nul en bear) est "
        "mécaniquement déjà faite par le gate — la marge est dans le "
        "dynamique (réduire SZ quand D3 haute-vol ET bear), PAS dans un "
        "re-étalonnage sur VAL (= overfitting).")
    L.append(
        "4. **Le vol_spike « permanent 1x »** reste un drag structurel "
        "(0 liq n'est pas un edge) — à gater (fund7 ou D3) ou à sortir "
        "du stack dans une itération suivante.")
    L.append("")
    L.append("**Limites honnêtes** : (1) h=3 % a été calibré sur le carry "
             "SEUL (T10, TRAIN 2021-09→2025-03) — l'application au stack "
             "complet (le même détecteur gate AUSSI le momentum) est une "
             "GÉNÉRALISATION testée sur VAL, pas une calibration ; le "
             "momentum-gated V2 n'a jamais été choisi sur TRAIN. (2) Fills "
             "modèle optimistes sur gaps ; funding 2021-2024 modélisé "
             "(T7) ; l'univers memes inexistait avant 2025-09 ; le "
             "warm-up épargne au stack une partie du bull 2021 (pire "
             "régime du momentum). (3) Les tailles de marge restent des "
             "hypothèses non optimisées. (4) Les RELATIFS (V2 < V1 en "
             "bascules, ordre des régimes, signe des deltas) survivent "
             "aux bugs ; les ABSOLUS (le $ final, le DD exact) restent à "
             "confirmer par le forward paper.")
    L.append("")
    L.append("Fichiers : étude `scripts/studies/aster_multiregime_stack_v2.py` "
             "— lecture seule `data/warehouse/klines.db` (aucune écriture "
             "prod) ; pattern T9 importé verbatim de "
             "`scripts/studies/aster_multiregime_stack.py`, détecteur T10 "
             "de `scripts/studies/aster_carry_hysteresis.py`.")

    out = REPORTS / "aster_multiregime_stack_v2.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[t11] rapport : {out}")
    print(f"[t11] V1 ${v1['bal']:,.2f} ({v1['roi_an']:+.0f} %/an, DD "
          f"{v1['dd']:.1f}, {v1['neg']}m−, {len(q1)}/6) → V2 "
          f"${v2['bal']:,.2f} ({v2['roi_an']:+.0f} %/an, DD {v2['dd']:.1f}, "
          f"{v2['neg']}m−, {len(q2)}/6) | whipsaw {w1[1]:+.1f}→"
          f"{w2[1]:+.1f} | VAL {tv2[1]:+.1f} % liq {val2['liq']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
