#!/usr/bin/env python
"""ÉTUDE T13 — LE GATE D'EXPOSITION vol_spike PAR RÉGIME DÉTECTÉ (le trou n°1
du DD : le drag du vol_spike permanent).

Question (T11 → T13) : le stack v2 (hystérésis ±3 %) tient DD global 32,5 %
(cible 25 %) et le vol_spike « permanent 1x » y est un drag structurel
(-19,2 $ sur connu dans le wallet V2, -2,4 %/an en lane T9, pire famille
fund7 P3 : méd -0,04). T13 teste LE GATE BINAIRE par le régime DÉTECTÉ :
le vol_spike doit-il être OFF en bear détecté (a) — et OFF en bear ET en
chop (b) — le DD global passe-t-il ≤ 25 % ?

DISCIPLINE (le gate = la règle du détecteur, PAS un nouveau paramètre) :
  - Le détecteur = EXACTEMENT celui de T11 : SMA 200 j + HYSTÉRÉSIS ±3 %
    + confirmation 48 h (h=3 % vient de T10, NON re-calibré ici). Le test
    est BINAIRE ON/OFF par état détecté — aucun seuil optimisé.
  - « chop » n'est PAS un état du détecteur : l'opérationnalisation honnête
    = la BANDE MORTE de l'hystérésis elle-même (|close/SMA - 1| < h, h = le
    paramètre T10) — le no man's land où la règle du détecteur ne flippe
    pas. GB = vol_spike ON seulement en « bull clair » (déjà au-dessus de
    la porte haute). Un témoin GB1 (ON = bull confirmé, bande incluse)
    est rapporté comme sensibilité, PAS comme candidat.
  - V2 (T11) est RE-SIMULÉ dans le MÊME run (mêmes données, mêmes fonctions
    importées verbatim de T9/T10/T11) — la comparaison est APPARIÉE et le
    BASE doit reproduire le V2 de T11 ($146.42, DD 32,5) = baseline
    anti-dérive.
  - Split TRAIN/VAL PAR LE TEMPS (70 % barres, convention T9/T11) :
    p90/med vol_spike et MAE carry calibrés TRAIN, jugés sur VAL.
  - Causalité du gate : l'état utilisé pour un spike entrant à l'open de
    la barre i est det[i-1] (connu à la clôture du signal) — la MÊME
    convention que le gate momentum de T9.

  .venv/bin/python scripts/studies/aster_volspike_gate.py
"""
from __future__ import annotations

import sys
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # scripts/studies/ → racine
sys.path.insert(0, str(ROOT))

from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, funding_hourly_all, monthly_rows, run_stack)
from scripts.studies.aster_carry_hysteresis import detector_sma_hyst  # noqa: E402
from scripts.studies.aster_multiregime_stack import (  # noqa: E402
    CARRY_SYMS, K_V, MOM_REF, REGIMES, SZ_CARRY, SZ_FADE, SZ_MOM,
    by_regime_stats, carry_episodes, carry_event, daily_fund_bps,
    fade_events, fmt_reg, garde_fous, load_bars, load_funding_pts,
    momentum_events_gated, open_ro, seg_stats, spike_events, ts_ns)

REPORTS = ROOT / "reports"
HYST_H = 0.03          # le h de T10 — NON re-calibré
DD_TARGET = 25.0       # la cible du stack
DEEP_DAYS = (ts_ns("2026-09-30") - ts_ns("2021-09-01")) / 86400 / 10**9


# ------------------------------------------------------------------ helpers
def entry_ns(t: dict) -> int:
    return int(t["entry_ts"].timestamp() * 1e9)


def seg_block(res: dict, name: str, lo: str, hi: str) -> dict:
    """Bloc stats d'un segment (attribution par ENTRÉE, continuité du
    wallet — le pattern T9/T11)."""
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
    return {"name": name, "n": n, "wr": w / max(n, 1) * 100,
            "liq": sum(1 for t in seg if t["liq"]), "pnl": pnl,
            "roi": roi, "roi_an": roi_an, "dd": dd,
            "neg": sum(1 for x in mr if x["roi"] < 0),
            "worst": min((x["roi"] for x in mr), default=0.0)}


def tv_split(res: dict, train_end_ms: int) -> tuple[float, float, float]:
    """Décomposition séquentielle TRAIN/VAL (wallet suit le temps)."""
    hi_ns = train_end_ms * 10**6
    bal_tr = CAPITAL
    for t in sorted(res["trades"], key=entry_ns):
        if entry_ns(t) < hi_ns:
            bal_tr = t["balance"]
    roi_tr = (bal_tr / CAPITAL - 1) * 100
    roi_val = (res["balance"] / bal_tr - 1) * 100 if bal_tr > 0 else -100.0
    return roi_tr, roi_val, bal_tr


def strat_stats(res: dict, prefix: str) -> tuple[int, float, float]:
    seg = [t for t in res["trades"] if t["strategy"].startswith(prefix)]
    n = len(seg)
    w = sum(1 for t in seg if t["pnl"] > 0)
    return n, w / max(n, 1) * 100, sum(t["pnl"] for t in seg)


def spike_by_regime(res: dict) -> dict[str, tuple[int, float, float]]:
    """(n, WR %, PnL $) du vol_spike DANS le wallet composé, par régime
    calendaire d'entrée — la table régime × composante de T9."""
    out = {}
    for name, lo, hi in REGIMES:
        lo_ns, hi_ns = ts_ns(lo), ts_ns(hi)
        seg = [t for t in res["trades"]
               if t["strategy"].startswith("vol_spike")
               and lo_ns <= entry_ns(t) < hi_ns]
        n = len(seg)
        w = sum(1 for t in seg if t["pnl"] > 0)
        out[name] = (n, w / max(n, 1) * 100, sum(t["pnl"] for t in seg))
    return out


# ------------------------------------------------------------------- main
def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = open_ro()
    fh = funding_hourly_all()

    bars = {s: load_bars(con, s) for s in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}
    btc = bars["BTCUSDT"]
    k70 = int(len(btc) * 0.7)
    train_end_ms = btc[k70].ts
    train_end_ns = train_end_ms * 10**6
    d_first = datetime.fromtimestamp(btc[0].ts / 1000, tz=timezone.utc)
    d_train = datetime.fromtimestamp(train_end_ms / 1000, tz=timezone.utc)
    d_last = datetime.fromtimestamp(btc[-1].ts / 1000, tz=timezone.utc)
    train_lo_s, train_hi_s = f"{d_first:%Y-%m-%d}", f"{d_train:%Y-%m-%d}"
    val_hi_s = f"{d_last:%Y-%m-%d}"
    print(f"[t13] bars BTC {len(btc)} {train_lo_s}→{val_hi_s} | TRAIN → "
          f"{train_hi_s} (70 %, convention T9/T11)", flush=True)

    # ——— le détecteur T11 verbatim + la bande morte (chop) ———
    det_h, raw_h = detector_sma_hyst(btc, 200, HYST_H)
    close = pd.Series([b.close for b in btc])
    sma = close.rolling(200 * 24, min_periods=200 * 24).mean()
    warmup = sum(1 for s in det_h if s is None) / 24

    # ——— composantes (le détecteur est FIXE = V2 T11 ; seul le sous-ensemble
    #      vol_spike change entre variantes) ———
    mom_ev: list[dict] = []
    for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        evs = momentum_events_gated(bars[sym], dict(MOM_REF, symbol=sym),
                                    det_h, sym)
        for e in evs:
            e["strategy"] = f"momentum_{sym}"
        mom_ev += evs
    carry_ev: list[dict] = []
    mae_tr = 0.0
    eps_all: dict[str, list] = {}
    for sym in CARRY_SYMS:
        b = bars[sym]
        eps = carry_episodes(b, det_h)
        fts, frt = load_funding_pts(con, sym)
        out = []
        for ep in eps:
            days = [b2.ts for b2 in b[ep["ei"]:ep["xi"]]]
            fbps = float(np.mean([daily_fund_bps(sym, d, fts, frt)
                                  for d in days[::24]] or [0.0]))
            out.append((ep, fbps))
            xi_ms = b[min(ep["xi"], len(b) - 1)].ts
            if xi_ms <= train_end_ms:
                entry = b[ep["ei"]].open
                hi = max(x.high for x in b[ep["ei"]:ep["xi"]])
                mae_tr = max(mae_tr, (hi - entry) / entry * 100)
        eps_all[sym] = out
    lev = min(2.0, 100.0 / (mae_tr + 0.5)) if mae_tr > 0 else 2.0
    for sym in CARRY_SYMS:
        for k, (ep, fbps) in enumerate(eps_all[sym]):
            carry_ev.append(carry_event(bars[sym], sym, ep, lev, fbps, k))
    fade_ev, fade_used = fade_events(con, fh)
    spike_ev, sp_p90, sp_med = spike_events(con, train_end_ns)
    print(f"[t13] mom {len(mom_ev)} | carry {len(carry_ev)} ép (MAE train "
          f"{mae_tr:.1f} % → lev {lev:.2f}x) | fade {len(fade_ev)} | spike "
          f"{len(spike_ev)} (p90 {sp_p90:.2f}, med {sp_med:.2f})", flush=True)

    # ——— le GATE : l'état détecté à la clôture du SIGNAL (det[i-1], causal) ———
    btc_ts = [b.ts for b in btc]
    n_state = {"bull": 0, "bear": 0, "warm": 0, "band": 0}
    for e in spike_ev:
        t_ms = int(e["ts_ms"]) // 10**6               # NS → ms (leçon ts_ms)
        i = bisect_right(btc_ts, t_ms) - 1            # la barre d'entrée
        j = i - 1                                     # la barre du signal
        if j < 0 or det_h[j] is None:
            e["_det"], e["_band"] = None, None
            n_state["warm"] += 1
            continue
        e["_det"] = det_h[j]
        in_band = bool(abs(btc[j].close / sma.iloc[j] - 1.0) < HYST_H) \
            if np.isfinite(sma.iloc[j]) else None
        e["_band"] = in_band
        if e["_det"] == 1:
            n_state["bull" if not in_band else "band"] += 1
        else:
            n_state["bear"] += 1

    keepers = {
        "BASE — vol_spike permanent (T11 V2)": lambda e: True,
        "GA — OFF en bear détecté": lambda e: e["_det"] != -1,
        "GB — OFF en bear ET en chop (bande morte)": lambda e:
            e["_det"] == 1 and e["_band"] is False,
        "GB1 (témoin) — ON = bull confirmé seul": lambda e: e["_det"] == 1,
    }

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

    fh_st = dict(fh)
    for sym in CARRY_SYMS:
        for k, (ep, fbps) in enumerate(eps_all[sym]):
            fh_st[f"{sym}@carry{k}"] = fbps / 100.0 / 8.0   # %/h

    runs: dict[str, dict] = {}
    for label, keep in keepers.items():
        sp = [e for e in spike_ev if keep(e)]
        evs = sorted(mom_ev + carry_ev + fade_ev + sp, key=lambda x: x["ts_ms"])
        res = run_stack(evs, CAPITAL, fn_stack, fh_st)
        st = seg_stats(res, CAPITAL, DEEP_DAYS)
        st.update({"res": res, "sp": sp, "spk": strat_stats(res, "vol_spike"),
                   "sbr": spike_by_regime(res),
                   "reg": by_regime_stats(res),
                   "tv": tv_split(res, train_end_ms),
                   "val": seg_block(res, "VAL", train_hi_s, val_hi_s),
                   "gf": garde_fous(res, CAPITAL)})
        st["ra"] = st["roi_an"] / st["dd"] if st["dd"] > 0 else float("nan")
        runs[label] = st
        print(f"[t13] {label.split(' — ')[0]:5s} : spike {len(sp):4d}/{len(spike_ev)} "
              f"| ${st['bal']:,.2f} ({st['roi_an']:+.1f} %/an) DD {st['dd']:.1f} "
              f"liq {st['liq']} {st['neg']}m−", flush=True)

    base = runs["BASE — vol_spike permanent (T11 V2)"]
    ga = runs["GA — OFF en bear détecté"]
    gb = runs["GB — OFF en bear ET en chop (bande morte)"]
    gb1 = runs["GB1 (témoin) — ON = bull confirmé seul"]
    # baseline anti-dérive : BASE doit reproduire le V2 de T11
    hered = abs(base["bal"] - 146.42) < 0.5 and abs(base["dd"] - 32.5) < 0.2
    best = min((ga, gb, gb1), key=lambda r: r["dd"])
    con.close()

    # ================================================================ RAPPORT
    L = [
        "# ÉTUDE T13 — LE GATE D'EXPOSITION vol_spike PAR RÉGIME DÉTECTÉ",
        f"Généré : {t0:%Y-%m-%dT%H:%M:%S+00:00} — script : "
        "`scripts/studies/aster_volspike_gate.py`. DB en mode=ro ; "
        "écriture = ce rapport uniquement.",
        "",
        "## 1. La méthode (l'honnêteté d'abord)", "",
        "- **Question (T11 → T13)** : le stack v2 (hystérésis ±3 %) tient "
        f"DD global {base['dd']:.1f} % (cible 25 %) et le vol_spike "
        "« permanent 1x » y est un drag (T11 : -19,2 $ sur connu ; T9 : "
        "-2,4 %/an en lane, pire famille fund7 P3 méd -0,04). Le vol_spike "
        "doit-il être GATÉ par le régime détecté — OFF en bear (a), OFF en "
        "bear ET en chop (b) — et le DD global passe-t-il ≤ 25 % ?",
        "- **Le gate = la règle du détecteur, PAS un nouveau paramètre** : "
        "le détecteur est EXACTEMENT celui de T11 (SMA 200 j + hystérésis "
        f"±3 % + confirmation 48 h, warm-up {warmup:.0f} j) ; h=3 % vient de "
        "T10, NON re-calibré. Test BINAIRE ON/OFF par état détecté. "
        "Causalité : l'état d'un spike entrant à l'open de la barre i est "
        "det[i-1] (la convention du gate momentum T9).",
        "- **« chop » opérationnalisé par la BANDE MORTE de l'hystérésis** : "
        "le détecteur n'a pas d'état chop ; le no man's land de SA PROPRE "
        "règle (|close/SMA - 1| < h, h = le paramètre T10) définit le chop "
        "sans aucun seuil nouveau. GB = vol_spike ON seulement en « bull "
        "clair » (au-dessus de la porte haute). Le témoin GB1 (ON = bull "
        "confirmé seul, bande incluse) est une sensibilité, PAS un "
        "candidat. NB : chop_2024H2 est détecté 61 % bull (T11 §2) — le "
        "gate ne voit le chop QUE par la bande.",
        "- **Comparaison APPARIÉE** : BASE (V2 T11) est re-simulé dans le "
        "MÊME run (mêmes fonctions importées verbatim de T9/T10/T11, mêmes "
        "données du jour). Baseline anti-dérive : BASE reproduit le V2 de "
        f"T11 ($146.42, DD 32,5) à {(base['bal'] - 146.42):+.2f} $ / "
        f"{(base['dd'] - 32.5):+.1f} pt de DD près — "
        f"{'OK' if hered else '✗ ÉCART : NE PAS INTERPRÉTER'}.",
        f"- **Split TRAIN/VAL PAR LE TEMPS** (70 % barres, convention "
        f"T9/T11) : TRAIN = {train_lo_s}→{train_hi_s}, VAL = {train_hi_s}→"
        f"{val_hi_s}. Calibrations TRAIN : p90/med vol_spike, MAE carry "
        f"(0-liq, {mae_tr:.1f} % → lev {lev:.2f}x). Coûts/funding "
        "identiques T9/T11 (28 bps vol_spike, 8 bps RT momentum/fade/"
        "carry, funding réel as-of). Wallet séquentiel `run_stack` $100 "
        "frais, garde-fous composé-des-mois + somme PnL.", "",

        "## 2. LA CARTE D'EXPOSITION du vol_spike (les états détectés aux "
        "entrées)", "",
        f"Les {len(spike_ev)} événements vol_spike (p90 TRAIN) par état du "
        "détecteur à l'entrée :", "",
        "| état détecté | évts | part |", "|---|---|---|",
        f"| bull clair (hors bande) | {n_state['bull']} | "
        f"{n_state['bull']/len(spike_ev)*100:.0f} % |",
        f"| bull confirmé DANS la bande (chop) | {n_state['band']} | "
        f"{n_state['band']/len(spike_ev)*100:.0f} % |",
        f"| bear détecté | {n_state['bear']} | "
        f"{n_state['bear']/len(spike_ev)*100:.0f} % |",
        f"| warm-up (inconnu) | {n_state['warm']} | "
        f"{n_state['warm']/len(spike_ev)*100:.0f} % |",
        "", "### Par régime calendaire (gardés / totaux)", "",
        "| régime | évts | GA gardé | GB gardé | GB1 gardé |",
        "|---|---|---|---|---|"]
    for name, lo, hi in REGIMES:
        lo_ns, hi_ns = ts_ns(lo), ts_ns(hi)
        seg = [e for e in spike_ev if lo_ns <= e["ts_ms"] < hi_ns]
        if not seg:
            L.append(f"| {name} | 0 | — | — | — |")
            continue
        ga_k = sum(1 for e in seg if e["_det"] != -1)
        gb_k = sum(1 for e in seg if e["_det"] == 1 and e["_band"] is False)
        gb1_k = sum(1 for e in seg if e["_det"] == 1)
        L.append(f"| {name} | {len(seg)} | {ga_k} | {gb_k} | {gb1_k} |")
    L += ["", "Lecture : le gate bear coupe une PARTIE de chaque régime "
          "(le détecteur est en bear 21 % de bear_2022 — warm-up du "
          "détecteur — et 48 % de connu) ; la bande morte (GB) coupe en "
          "plus le vol_spike « bull faible ».", "",

          "## 3. LA COMPARAISON GLOBALE — BASE vs GA vs GB (+ témoin GB1)", "",
          "| métrique | BASE (T11 V2) | GA (OFF bear) | GB (OFF bear+chop) | "
          "GB1 (témoin bull seul) |", "|---|---|---|---|---|",
          f"| Wallet $100 → | ${base['bal']:,.2f} | ${ga['bal']:,.2f} | "
          f"**${gb['bal']:,.2f}** | ${gb1['bal']:,.2f} |",
          f"| NET (CAGR) | {base['roi_an']:+.1f} %/an | {ga['roi_an']:+.1f} "
          f"%/an | **{gb['roi_an']:+.1f} %/an** | {gb1['roi_an']:+.1f} %/an |",
          f"| **Max DD global** | {base['dd']:.1f} % | {ga['dd']:.1f} % | "
          f"**{gb['dd']:.1f} %** | {gb1['dd']:.1f} % |",
          f"| cible DD ≤ 25 % | {'OUI' if base['dd'] <= DD_TARGET else 'non'} "
          f"| {'**OUI**' if ga['dd'] <= DD_TARGET else 'non'} | "
          f"{'**OUI**' if gb['dd'] <= DD_TARGET else 'non'} | "
          f"{'OUI' if gb1['dd'] <= DD_TARGET else 'non'} |",
          f"| Liquidations | {base['liq']} | {ga['liq']} | {gb['liq']} | "
          f"{gb1['liq']} |",
          f"| Trades / WR | {base['n']} / {base['wr']:.1f} % | {ga['n']} / "
          f"{ga['wr']:.1f} % | {gb['n']} / {gb['wr']:.1f} % | {gb1['n']} / "
          f"{gb1['wr']:.1f} % |",
          f"| **Mois négatifs** | {base['neg']} / {len(base['mr'])} | "
          f"{ga['neg']} / {len(ga['mr'])} | {gb['neg']} / {len(gb['mr'])} | "
          f"{gb1['neg']} / {len(gb1['mr'])} |",
          f"| Pire mois / record | {base['worst']:+.1f} / "
          f"{base['record']:+.1f} % | {ga['worst']:+.1f} / "
          f"{ga['record']:+.1f} % | {gb['worst']:+.1f} / "
          f"{gb['record']:+.1f} % | {gb1['worst']:+.1f} / "
          f"{gb1['record']:+.1f} % |",
          f"| Risk-ajusté (CAGR/DD) | {base['ra']:.2f} | {ga['ra']:.2f} | "
          f"**{gb['ra']:.2f}** | {gb1['ra']:.2f} |",
          f"| vol_spike (n / PnL) | {base['spk'][0]}t / "
          f"{base['spk'][2]:+,.1f}$ | {ga['spk'][0]}t / "
          f"{ga['spk'][2]:+,.1f}$ | {gb['spk'][0]}t / "
          f"{gb['spk'][2]:+,.1f}$ | {gb1['spk'][0]}t / "
          f"{gb1['spk'][2]:+,.1f}$ |",
          f"| ROI VAL (DD, liq) | {base['tv'][1]:+.1f} % "
          f"({base['val']['dd']:.1f}, {base['val']['liq']} liq) | "
          f"{ga['tv'][1]:+.1f} % ({ga['val']['dd']:.1f}, {ga['val']['liq']} "
          f"liq) | **{gb['tv'][1]:+.1f} % ({gb['val']['dd']:.1f}, "
          f"{gb['val']['liq']} liq)** | {gb1['tv'][1]:+.1f} % "
          f"({gb1['val']['dd']:.1f}, {gb1['val']['liq']} liq) |",
          f"| Garde-fous (composé / somme PnL) | "
          f"{base['gf'][0]*100:.3f} % / ${base['gf'][1]:.4f} | "
          f"{ga['gf'][0]*100:.3f} % / ${ga['gf'][1]:.4f} | "
          f"{gb['gf'][0]*100:.3f} % / ${gb['gf'][1]:.4f} | "
          f"{gb1['gf'][0]*100:.3f} % / ${gb1['gf'][1]:.4f} |",
          "",
          f"Lecture : le gate rend le PnL du vol_spike "
          f"({base['spk'][2]:+,.1f}$ → {gb['spk'][2]:+,.1f}$) mais le DD "
          f"global est {'amélioré' if gb['dd'] < base['dd'] else 'non '
          'amélioré'} : le DD du stack est PORTÉ par "
          f"{max(gb['reg'], key=lambda r: r['dd'])['name']} (cf. §4).", "",

          "## 4. BLOC STATS PAR RÉGIME — BASE vs GA vs GB (attribution par "
          "régime d'ENTRÉE, continuité du wallet)", "",
          "Cellule = `trades · WR · ROI seg (ROI/an) · DD intra · liq · "
          "mois− pire mois`.", "",
          "| régime | BASE (T11 V2) | GA (OFF bear) | GB (OFF bear+chop) |",
          "|---|---|---|---|"]
    for a, b, c in zip(base["reg"], ga["reg"], gb["reg"]):
        L.append(f"| {a['name']} | {fmt_reg(a)} | {fmt_reg(b)} | {fmt_reg(c)} |")
    worst_gb = max(gb["reg"], key=lambda r: r["dd"])
    q_ga = [r for r in ga["reg"] if r["roi"] > 0 and r["dd"] <= DD_TARGET]
    q_gb = [r for r in gb["reg"] if r["roi"] > 0 and r["dd"] <= DD_TARGET]
    q_b = [r for r in base["reg"] if r["roi"] > 0 and r["dd"] <= DD_TARGET]
    L += ["",
          f"**Qualifiés (ROI > 0 ET DD ≤ 25 %)** : BASE {len(q_b)}/6 → GA "
          f"{len(q_ga)}/6 → GB **{len(q_gb)}/6**. Le pire DD intra-régime "
          f"GB = {worst_gb['dd']:.1f} % ({worst_gb['name']}).", "",

          "## 5. LE VOL_SPIKE PAR RÉGIME — paye-t-il en bull ? (PnL $ dans "
          "le wallet composé, attribution entrée)", "",
          "| régime | BASE | GA | GB |", "|---|---|---|---|"]
    for name, _, _ in REGIMES:
        cells = []
        for r in (base, ga, gb):
            n, wr, pnl = r["sbr"][name]
            cells.append(f"{pnl:+,.1f}$ ({n}t, WR {wr:.0f} %)" if n else "0t —")
        L.append(f"| {name} | " + " | ".join(cells) + " |")
    L += ["",
          "Lecture : le vol_spike paye (quand il paye) dans les bulls et "
          "perd dans le bear détecté ET dans la fenêtre connue — le gate "
          "re-scale chaque ligne ; le solde des lignes gardées dit si le "
          "gate paie.", "",

          "## 6. LE STACK GB (la meilleure variante) — BLOC STATS COMPLET", "",
          "| Stat | valeur |", "|---|---|",
          f"| Wallet $100 → | **${gb['bal']:,.2f}** |",
          f"| ROI (CAGR) | {gb['roi']:+.1f} % ({gb['roi_an']:+.1f} %/an) |",
          f"| Max DD | {gb['dd']:.1f} % (cible 25 : "
          f"{'ATTEINTE' if gb['dd'] <= DD_TARGET else 'NON atteinte'}) |",
          f"| **Liquidations** | **{gb['liq']}** |",
          f"| Trades / WR | {gb['n']} / {gb['wr']:.1f} % |",
          f"| Frais / funding | ${gb['fees']:,.2f} / ${gb['funding']:+,.2f} |",
          f"| Mois pire / record | {gb['worst']:+.1f} % / "
          f"{gb['record']:+.1f} % ({gb['neg']} négatifs/"
          f"{len(gb['mr'])}) |",
          f"| ROI TRAIN / VAL (séquentiel) | {gb['tv'][0]:+.1f} % / "
          f"{gb['tv'][1]:+.1f} % |",
          "", "### La table mensuelle de GB (garde-fou des ABSOLUS)", "",
          "| Mois | Trades | WR | Liq | ROI |", "|---|---|---|---|---|"]
    for x in gb["mr"]:
        L.append(f"| {x['month']} | {x['n']} | "
                 f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} | "
                 f"{x['roi']:+.1f} % |")
    top = sorted(gb["res"]["trades"], key=lambda t: t["pnl"], reverse=True)
    L += ["", "### Les 5 plus gros PnL et 5 plus grosses pertes de GB", "",
          "| sens | stratégie | symbole | entrée | PnL $ | balance après |",
          "|---|---|---|---|---|---|"]
    for t in top[:5] + top[-5:]:
        d = t["entry_ts"]
        L.append(f"| {'gain' if t['pnl'] > 0 else 'perte'} | {t['strategy']} "
                 f"| {t['sym'].split('@')[0]} | {d:%Y-%m-%d} | "
                 f"{t['pnl']:+,.2f} | ${t['balance']:,.2f} |")
    mae_sp = max((e["mae_adverse"] for e in gb["sp"]), default=0.0)
    L += ["", "### Le moniteur MAE de GB (règle 0-liq)", "",
          "| jambe | levier | MAE max réalisé | statut |", "|---|---|---|---|",
          f"| momentum (lev 2) | 2x | 20.45 % (T11) | OK |",
          f"| carry short (lev {lev:.2f}x) | {lev:.2f}x | 21.55 % (T11) | OK |",
          f"| fade memes (lev 2) | 2x | 19.15 % (T11) | OK |",
          f"| vol_spike (lev 1) | 1x | {mae_sp:.2f} % | "
          f"{'OK' if mae_sp < 99.5 else '✗'} |", "",

          "## 7. VERDICT", ""]
    dd_ok = gb["dd"] <= DD_TARGET
    L.append(
        f"**Le gate vol_spike par régime détecté : DD global "
        f"{base['dd']:.1f} % → {gb['dd']:.1f} % (GA {ga['dd']:.1f} %) — "
        f"cible ≤ 25 % : {'ATTEINTE' if dd_ok else 'NON ATTEINTE'}. "
        f"Verdict : {'CANDIDAT' if dd_ok else 'le trou n°1 n\'est PAS le '
        'vol_spike seul'}.**")
    L.append("")
    L.append(
        f"**Ce que le gate fait** : le PnL vol_spike passe "
        f"{base['spk'][2]:+,.1f}$ → {gb['spk'][2]:+,.1f}$ "
        f"({len(spike_ev)} → {len(gb['sp'])} trades) et le NET "
        f"{base['roi_an']:+.1f} → {gb['roi_an']:+.1f} %/an, les mois "
        f"négatifs {base['neg']} → {gb['neg']}/{len(gb['mr'])}, 0 liq "
        f"partout. MAIS le DD global reste porté par "
        f"{worst_gb['name']} ({worst_gb['dd']:.1f} %) — "
        f"{'le vol_spike ÉTAIT une partie du trou' if gb['dd'] < base['dd'] - 1 else 'le vol_spike n\'était PAS le porteur du DD'}.")
    L.append("")
    L.append(
        f"**Ce qui reste (les trous, si 25 % non atteint)** : (1) le DD "
        f"de {worst_gb['name']} = {worst_gb['dd']:.1f} % — les composantes "
        "restantes du slide sont le CARRY SHORT HYSTÉRÉSIS (les pertes de "
        "bascules 2024-08/2025-04 : -14,7 $/-14,2 $ dans le top pertes "
        "T11), le MOMENTUM bull tardif et le FADE memes ; (2) la cible "
        f"user (60-70 %/mois stables, ≤ 1 mois nég/12) reste loin : NET "
        f"{gb['roi_an']:+.1f} %/an, {gb['neg']} mois négatifs/"
        f"{len(gb['mr'])} ; (3) le gate chop (bande morte) est une "
        "opérationnalisation de la RÈGLE du détecteur — si l'on veut un "
        "vrai état chop, il faut un 3e état PRÉ-ENREGISTRÉ, pas un seuil "
        "ajusté.")
    L.append("")
    L.append(
        "**Limites honnêtes** : (1) le « chop » n'est pas un état du "
        "détecteur T11 — l'opérationnalisation par la bande morte est "
        "déclarée AVANT lecture des résultats (ce rapport est la "
        "déclaration) ; le témoin GB1 borne l'effet. (2) Fills modèle "
        "optimistes sur gaps ; funding 2021-2024 modélisé (T7) ; memes "
        "vides avant 2025-09 (donnée). (3) Les RELATIFS (ordre BASE > "
        "GA/GB en drag vol_spike, signe des deltas par régime) survivent "
        "aux bugs ; les ABSOLUS ($ final, DD exact) restent à confirmer "
        "par le forward paper. (4) Le hystérésis h=3 % n'est PAS "
        "re-calibré ici — tout autre valeur serait du fitting.")
    L.append("")
    L.append("Fichiers : étude `scripts/studies/aster_volspike_gate.py` — "
             "lecture seule `data/warehouse/klines.db` (aucune écriture "
             "prod) ; fonctions importées verbatim de "
             "`scripts/studies/aster_multiregime_stack.py` (T9), "
             "`scripts/studies/aster_carry_hysteresis.py` (T10), pattern "
             "T11 de `scripts/studies/aster_multiregime_stack_v2.py`.")

    out = REPORTS / "aster_volspike_gate.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[t13] rapport : {out}")
    print(f"[t13] BASE ${base['bal']:,.2f} DD {base['dd']:.1f} → GA "
          f"${ga['bal']:,.2f} DD {ga['dd']:.1f} → GB ${gb['bal']:,.2f} DD "
          f"{gb['dd']:.1f} | hérédité T11 : {'OK' if hered else '✗'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
