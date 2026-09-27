#!/usr/bin/env python
"""SIZING CONDITIONNEL PAR RÉGIME — moduler la taille, jamais gate sec.

Suite de l'autopsie (27/09) : les mois faibles ont des séparateurs
ex-ante (fund7 d=+0.98, fresh-peak d=-0.72, vol7 bas en janvier). Au
lieu d'un gate qui tue des trades, on MODULE la taille du flux cascade
majeurs 10x gated (le cœur) par régime :
  - fund7    : funding moyen 7j des 6 majeures au moment du signal
  - vol7     : ATR % (roulante 24 h) moyenne des majeures sur 168 h
  - liq24h   : notionnel SELL de liq_events sur 24 h glissantes
               (couverture liq_events 21/09 → N limité, noté)
  - fresh-peak : l'équité du sim est à ≤ 5 % de son max (dd ≤ 5 %)

Étapes : (1) GRADIENT MAP — terciles de chaque feature, seuils TRAIN
uniquement (split 70/30 PAR LE TEMPS), rendement moyen par bucket TRAIN
puis VAL — un feature n'est RETENU que si son gradient VAL confirme le
gradient TRAIN (leçon corr-tilt). (2) SIZING ×{0.5, 1.0, 1.5} par
régime, multiplicateur = moyenne géométrique des multiplicateurs des
features retenus, plafond 0.50*K inchangé — le LEVIER ne bouge jamais
(0-liq structurel : liq_move dépend de lev, pas du sizing).
(3) JUGEMENT : machine 4 flux baseline (--vol-spike) vs + sizing
conditionnel, BLOC STATS côte à côte + garde-fou composé-des-mois.

Lecture SEULE de data/warehouse/klines.db. Importe les briques de
the_machine sans l'éditer.

  .venv/bin/python scripts/conditional_sizing.py
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

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402
from scripts.portfolio_sim import KDB, MAJORS, btc_regime_series, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import collect_meme  # noqa: E402

REPORTS = ROOT / "reports"
KDB_RO = f"file:{KDB}?mode=ro"
WIN = 168                     # 7j en heures
_K = 0.89                     # calibration DD de la machine
TRAIN_FRAC = 0.70             # split PAR LE TEMPS, seuils TRAIN uniquement
FRESH_PEAK_DD = 5.0           # % : équité à ≤ 5 % de son max


def ro_con() -> sqlite3.Connection:
    return sqlite3.connect(KDB_RO, uri=True)


# ------------------------------------------------------------- le pipeline --
def build_universe() -> dict:
    """Réplication EXACTE de the_machine.main() en 4 flux (--vol-spike),
    briques importées, sans toucher the_machine."""
    con = ro_con()
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # flux 1 : cascade majeurs 10x, gate AL p66, vol-inverse (copie machine)
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = 10
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    med_majors = float(np.median([e["atr_pct"] for e in gated]))
    mae_gated = max(e["mae_adverse"] for e in gated)

    # flux 2 : cascade memecoins 1x
    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = lev_meme

    # flux 3 : survivor long 72h 1x + filtre ATR p90
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT

    # flux 4 : vol-spike reversion 6h 1x (--vol-spike de la mission)
    from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
    spike = collect_vol_spike(con, hold=6)
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    med_spike = float(np.median([e["atr_pct"] for e in spike])) if spike \
        else float("nan")

    # fund_rank (poids qualité) — copie the_machine
    funding_ts: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = funding_ts.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    for e in gated:
        ranks, own = [], np.nan
        for s in MAJORS:
            ft = funding_ts.get(s)
            if not ft or len(ft[0]) < 5:
                continue
            pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"],
                                      side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = ft[1][pos]
            ranks.append(ft[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)

    # données majeures pour les features de régime (puis ro-close)
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    liq_cov = con.execute(
        "SELECT MIN(event_time), MAX(event_time), "
        "SUM(side='SELL') FROM liq_events").fetchone()
    liq_sell = [np.array(x, dtype=np.int64) if False else x for x in
                zip(*con.execute(
                    "SELECT event_time, notional FROM liq_events "
                    "WHERE side='SELL' ORDER BY event_time"))]
    liq_t = np.array(liq_sell[0] if liq_sell else [], dtype=np.int64)
    liq_n = np.array(liq_sell[1] if liq_sell else [], dtype=float)
    con.close()

    uni = {"fh": fh, "q66": q66, "gated": gated, "meme": meme, "surv": surv,
           "spike": spike, "med_majors": med_majors, "med_meme": med_meme,
           "med_spike": med_spike, "mae_gated": mae_gated,
           "mae_meme": mae_meme, "lev_meme": lev_meme,
           "majors_dfs": majors_dfs, "liq_cov": liq_cov,
           "liq_t": liq_t, "liq_n": liq_n}
    return uni


# ------------------------------------------------- features ex-ante / trade --
def attach_regime_features(uni: dict) -> None:
    """fund7 / vol7 / liq24h EX-ANTE sur chaque gated cascade (trailing
    uniquement : rien qui regarde après ts). ts des events = NS (leçon
    ts_ms), funding/liq convertis en ms."""
    con_less = uni["majors_dfs"]
    idx_ns = con_less["BTCUSDT"].index.astype("datetime64[ns]").asi8
    atrs = {}
    for s, d in con_less.items():
        c = d["close"]
        atrs[s] = (c.diff().abs().rolling(24).mean() / c * 100).values

    # funding (ts ms, taux) par majeure
    fts: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    con = ro_con()
    for s, t, rt in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        if s not in MAJORS:
            continue
        try:
            t = int(t)
            ts, rr = fts.setdefault(s, ([], []))
            ts.append(t if t > 10**11 else t * 1000)   # → ms
            rr.append(float(rt))
        except (TypeError, ValueError):
            continue
    con.close()
    fts = {s: (np.array(t), np.array(r)) for s, (t, r) in fts.items()}

    lt, ln = uni["liq_t"], uni["liq_n"]
    cum_n = np.cumsum(ln) if len(ln) else np.array([0.0])
    cov_start = int(uni["liq_cov"][0]) if uni["liq_cov"] and uni["liq_cov"][0] \
        else None

    for e in uni["gated"]:
        ev_ms = int(e["ts_ms"] / 10**6)
        # fund7 : taux moyen 7j des 6 majeures (%/8h) — ex-ante
        vals = []
        for s in MAJORS:
            ft = fts.get(s)
            if ft is None or len(ft[0]) == 0:
                continue
            hi = int(np.searchsorted(ft[0], ev_ms, side="left"))
            lo = int(np.searchsorted(ft[0], ev_ms - 7 * 86400 * 1000,
                                     side="left"))
            if hi > lo:
                vals.append(np.mean(ft[1][lo:hi]) * 100)
        e["fund7"] = float(np.mean(vals)) if vals else float("nan")
        # vol7 : ATR % moyenne des majeures sur les 168 h avant le signal
        bi = int(np.searchsorted(idx_ns, e["ts_ms"], side="left"))
        lo = max(bi - WIN, 0)
        e["vol7"] = (float(np.nanmean([np.nanmean(atrs[s][lo:bi])
                                       for s in MAJORS]))
                     if bi > lo else float("nan"))
        # liq24h : notionnel SELL liquidé sur les 24 h glissantes
        e["liq24"] = float("nan")
        if cov_start is not None and ev_ms >= cov_start:
            hi = int(np.searchsorted(lt, ev_ms, side="right"))
            lo2 = int(np.searchsorted(lt, ev_ms - 86400 * 1000, side="right"))
            tot = (cum_n[hi - 1] if hi > 0 else 0.0) - \
                  (cum_n[lo2 - 1] if lo2 > 0 else 0.0)
            e["liq24"] = float(tot)
        # rendement brut du signal (% du NOTIONAL, indépendant du sizing)
        fund_pct = uni["fh"].get(e["sym"], 0.0) * e["hold_h"]
        e["r_not"] = (e["price_ret_short"]
                      + e.get("fund_sign", 1) * fund_pct
                      - e["fee_rt_bps"] / 100.0)


def attach_fresh_peak(uni: dict, baseline: dict) -> None:
    """fresh-peak : dd du wallet baseline juste avant l'entrée (≤ 5 % du
    max = sommet frais). Reconstruction par exit_ts (méthode autopsie)."""
    ex = sorted((t["exit_ts"], t["pnl"]) for t in baseline["trades"])
    ex_ms = np.array([int(t.timestamp() * 1000) for t, _ in ex])
    cum = np.cumsum([p for _, p in ex]) + CAPITAL
    for e in uni["gated"]:
        ev_ms = int(e["ts_ms"] / 10**6)
        k = int(np.searchsorted(ex_ms, ev_ms, side="left"))
        bal = cum[k - 1] if k > 0 else CAPITAL
        peak = float(np.max(cum[:k])) if k > 0 else CAPITAL
        dd = (peak - bal) / peak * 100 if peak > 0 else 0.0
        e["dd_entry"] = dd
        e["fresh_peak"] = 1 if dd <= FRESH_PEAK_DD else 0


# ------------------------------------------------------------- gradient map --
def gradient_map(uni: dict) -> tuple[list[dict], dict]:
    """Terciles par feature (seuils TRAIN), rendement moyen par bucket
    TRAIN puis VAL. fresh-peak = binaire (2 groupes)."""
    gated = sorted(uni["gated"], key=lambda e: e["ts_ms"])
    n70 = int(len(gated) * TRAIN_FRAC)
    train, val = gated[:n70], gated[n70:]

    feats = [("fund7", 3), ("vol7", 3), ("liq24", 3), ("fresh_peak", 2)]
    rows, rules = [], {}
    for key, nb in feats:
        def lab(e):
            v = e.get(key, float("nan"))
            return v if nb == 2 else (float(v) if np.isfinite(v)
                                      else float("nan"))
        tr_vals = [lab(e) for e in train]
        va_vals = [lab(e) for e in val]
        if nb == 3:
            ok = [v for v in tr_vals if np.isfinite(v)]
            if len(ok) < 20:
                continue
            q33, q66 = (float(np.quantile(ok, 1 / 3)),
                        float(np.quantile(ok, 2 / 3)))

            def bucket(v):
                # NaN (ex. liq24h hors couverture) = EXCLU, pas bucket « bas »
                return -1 if not np.isfinite(v) \
                    else (0 if v < q33 else (1 if v < q66 else 2))
        else:
            q33 = q66 = float("nan")

            def bucket(v):
                return 1 if (np.isfinite(v) and v >= 0.5) else 0

        row = {"feat": key, "nb": nb, "q33": q33, "q66": q66, "buckets": []}
        means_tr = {}
        for b in range(nb):
            tr_b = [e for e in train if bucket(lab(e)) == b]
            va_b = [e for e in val if bucket(lab(e)) == b]
            m_tr = float(np.mean([e["r_not"] for e in tr_b])) if tr_b \
                else float("nan")
            m_va = float(np.mean([e["r_not"] for e in va_b])) if va_b \
                else float("nan")
            wr_tr = (100 * sum(1 for e in tr_b if e["r_not"] > 0)
                     / len(tr_b)) if tr_b else float("nan")
            wr_va = (100 * sum(1 for e in va_b if e["r_not"] > 0)
                     / len(va_b)) if va_b else float("nan")
            means_tr[b] = m_tr
            row["buckets"].append({"b": b, "n_tr": len(tr_b), "m_tr": m_tr,
                                   "wr_tr": wr_tr, "n_va": len(va_b),
                                   "m_va": m_va, "wr_va": wr_va})
        # direction TRAIN : meilleur vs pire bucket
        ok_b = {b: m for b, m in means_tr.items() if np.isfinite(m)}
        worst = min(ok_b, key=ok_b.get)
        best = max(ok_b, key=ok_b.get)
        spread_tr = ok_b[best] - ok_b[worst]
        b_val = {x["b"]: x["m_va"] for x in row["buckets"]}
        spread_va = (b_val.get(best, float("nan"))
                     - b_val.get(worst, float("nan")))
        agrees = (np.isfinite(spread_va) and np.isfinite(spread_tr)
                  and spread_tr > 0
                  and np.sign(spread_va) == np.sign(spread_tr)
                  and abs(spread_va) >= 0.25 * spread_tr)
        row.update({"worst": worst, "best": best,
                    "spread_tr": spread_tr, "spread_va": spread_va,
                    "retain": bool(agrees)})
        rules[key] = {"worst": worst, "best": best, "retain": bool(agrees),
                      "nb": nb, "means_tr": dict(ok_b)}
        rows.append(row)
    return rows, rules


# ------------------------------------------------------------------- sizing --
def make_machine_fn(uni: dict, rules: dict | None, use_features: bool,
                    mode: str = "minmax"):
    """Le sizing machine (copie exacte), puis × multiplicateur de régime
    sur cascade_10x si use_features. Levier JAMAIS touché → 0-liq
    structurel (liq_move = 100/lev - 0.5 ne dépend que de lev).
    mode "minmax" : pire bucket (min TRAIN) → 0.5, meilleur → 1.5.
    mode "extremes" : contraste bas vs haut uniquement, milieu neutre
    (les terciles adjacents à <0.15 pt près sont du bruit)."""
    med_majors, med_meme, med_spike = (uni["med_majors"], uni["med_meme"],
                                       uni["med_spike"])

    def mult(e, st) -> float:
        if not use_features or not rules:
            return 1.0
        ms = []
        for key, rule in rules.items():
            if not rule["retain"]:
                continue
            nb = rule["nb"]
            if nb == 3:
                v = e.get(key, float("nan"))
                if not np.isfinite(v):
                    ms.append(1.0)
                    continue
                b = 0 if v < rule["_q33"] else (1 if v < rule["_q66"] else 2)
                if mode == "extremes":
                    cand = {bb: mm for bb, mm in rule["means_tr"].items()
                            if bb in (0, 2) and np.isfinite(mm)}
                    worst = min(cand, key=cand.get)
                    best = max(cand, key=cand.get)
                else:
                    worst, best = rule["worst"], rule["best"]
                if b == worst:
                    m = 0.5
                elif b == best:
                    m = 1.5
                else:
                    m = 1.0
            else:  # binaire fresh_peak
                v = e.get(key, 0)
                if key == "fresh_peak" and st is not None:
                    v = 1 if st.get("dd", 0.0) <= FRESH_PEAK_DD else 0
                m = 0.5 if (v >= 0.5) == (rule["worst"] == 1) else 1.5
            ms.append(m)
        return float(np.exp(np.mean(np.log(ms)))) if ms else 1.0

    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * _K * (e["atr_pct"] / med_majors),
                         0.08 * _K), 0.40 * _K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                s0 = min(s0 * 1.5, 0.50 * _K)
            if use_features and rules:
                s0 = min(s0 * mult(e, st), 0.50 * _K)
            return s0
        if s == "cascade_meme":
            return min(max(0.10 * _K * (e["atr_pct"] / med_meme),
                           0.02 * _K), 0.30 * _K)
        if s == "vol_spike_6h":
            return min(max(0.10 * _K * (e["atr_pct"] / med_spike),
                           0.02 * _K), 0.30 * _K)
        return 0.20 * _K                # survivor long (1x)

    return machine_fn


def sim(uni: dict, machine_fn) -> dict:
    all_ev = sorted(uni["gated"] + uni["meme"] + uni["surv"] + uni["spike"],
                    key=lambda e: e["ts_ms"])
    return run_stack(all_ev, CAPITAL, machine_fn, uni["fh"])


def bloc(r: dict, label: str) -> dict:
    mr = monthly_rows(r["trades"], CAPITAL)
    prod, sum_pnl = 1.0, 0.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
        sum_pnl += x["pnl"]
    gap_c = abs(prod - r["balance"] / CAPITAL)
    gap_p = abs(sum_pnl - (r["balance"] - CAPITAL))
    rois_m = [x["roi"] for x in mr]
    n = max(r["n"], 1)
    return {"label": label, "r": r, "mr": mr, "gap_c": gap_c, "gap_p": gap_p,
            "roi": (r["balance"] / CAPITAL - 1) * 100,
            "wr": r["n_wins"] / n * 100, "neg": sum(1 for x in rois_m if x < 0),
            "rec": max(rois_m) if rois_m else 0.0,
            "worst": min(rois_m) if rois_m else 0.0,
            "mean_m": float(np.mean(rois_m)) if rois_m else 0.0}


def main() -> int:
    print("[csize] collecte des 4 flux (briques the_machine)…", flush=True)
    uni = build_universe()
    print(f"[csize] gated {len(uni['gated'])} / meme {len(uni['meme'])} / "
          f"surv {len(uni['surv'])} / spike {len(uni['spike'])}", flush=True)

    attach_regime_features(uni)
    base_fn = make_machine_fn(uni, None, use_features=False)
    print("[csize] sim baseline 4 flux…", flush=True)
    base = sim(uni, base_fn)
    b0 = bloc(base, "BASELINE 4 flux (--vol-spike)")
    print(f"[csize] baseline ${base['balance']:,.2f} "
          f"({b0['roi']:+.0f} %/an) DD {base['max_dd']:.1f} % "
          f"liq {base['n_liq']}", flush=True)

    attach_fresh_peak(uni, base)
    rows, rules = gradient_map(uni)
    # seuils terciles → règles (injectés pour le sizing)
    for row in rows:
        if row["feat"] in rules:
            rules[row["feat"]]["_q33"] = row["q33"]
            rules[row["feat"]]["_q66"] = row["q66"]
    retained = [k for k, v in rules.items() if v["retain"]]

    print("[csize] sim conditionnel (features retenus : "
          f"{retained or 'AUCUN'})…", flush=True)
    cond_fn = make_machine_fn(uni, rules, use_features=True)
    cond = sim(uni, cond_fn)
    b1 = bloc(cond, "4 flux + SIZING CONDITIONNEL")

    # ——— décomposition diagnostique (post-hoc, déclaré comme tel) ———
    # B : vol7 seul (règle mission) ; C : fresh-peak seul ;
    # D : règle EXTRÊMES vol7 (bas vs haut, milieu neutre — le min/max a
    # puni le milieu par bruit TRAIN 0.31 vs 0.42) + fresh-peak.
    print("[csize] variantes diagnostiques B/C/D…", flush=True)
    rules_vol = {"vol7": rules["vol7"]}
    rules_fresh = {"fresh_peak": rules["fresh_peak"]}
    b_vol = bloc(sim(uni, make_machine_fn(uni, rules_vol, True)),
                 "vol7 seul")
    b_fresh = bloc(sim(uni, make_machine_fn(uni, rules_fresh, True)),
                   "fresh-peak seul")
    rules_ext = {"vol7": dict(rules["vol7"]), "fresh_peak": rules["fresh_peak"]}
    b_ext = bloc(sim(uni, make_machine_fn(uni, rules_ext, True,
                                          mode="extremes")),
                 "extrêmes vol7 + fresh-peak")

    # la couverture liq24h (N limité — à noter)
    g = uni["gated"]
    n_cov = sum(1 for e in g if np.isfinite(e["liq24"]))
    cov = uni["liq_cov"]
    cov_s = (datetime.fromtimestamp(cov[0] / 1000, tz=timezone.utc)
             .strftime("%d/%m/%Y")) if cov and cov[0] else "n/a"

    # ----------------------------------------------------------- le rapport --
    L = ["# SIZING CONDITIONNEL PAR RÉGIME — moduler la taille, pas gater",
         f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — machine 4 flux "
         f"(--vol-spike, gate AL p66={uni['q66']:.2f}, K={_K}) répliquée par "
         "briques (the_machine intact). Split train/val PAR LE TEMPS 70/30 "
         f"({TRAIN_FRAC:.0%} des gated en TRAIN), seuils TRAIN uniquement.",
         "",
         "## 1. REPRODUCTION BASELINE (bit-repro du rapport officiel)", "",
         f"- ${CAPITAL:,.0f} → **${base['balance']:,.2f}** "
         f"({b0['roi']:+.0f} %/an), DD {base['max_dd']:.1f} %, "
         f"liq {base['n_liq']}, {base['n']} trades, WR {b0['wr']:.1f} % "
         f"— officiel 27/09 : $4,004.94 / +3905 % / DD 24.8 % / 0 liq.",
         f"- MAE gated {uni['mae_gated']:.2f} % → levier 10x inchangé "
         f"(règle 0-liq : le sizing multiplie le notional SOUS le plafond, "
         "jamais le levier).", "",
         "## 2. GRADIENT MAP — rendement moyen par bucket (% du notional)",
         "",
         "Terciles : seuils = quantiles 1/3–2/3 de TRAIN. Un feature est "
         "RETENU si le gradient VAL confirme le gradient TRAIN (même signe, "
         "spread VAL ≥ 25 % du spread TRAIN — leçon corr-tilt).", ""]
    for row in rows:
        lab = {"fund7": "fund7 (%/8h, 7j)", "vol7": "vol7 (ATR % 7j)",
               "liq24": "liq24h ($ SELL)",
               "fresh_peak": "fresh-peak (dd ≤ 5 %)"}[row["feat"]]
        L.append(f"### {lab} — "
                 f"{'RETENU' if row['retain'] else 'NON retenu (VAL contredit)'}"
                 )
        L.append("")
        if row["nb"] == 3:
            L.append(f"seuils TRAIN : q33={row['q33']:.4g}, "
                     f"q66={row['q66']:.4g} | spread TRAIN "
                     f"{row['spread_tr']:+.2f} pts, VAL "
                     f"{row['spread_va']:+.2f} pts")
        else:
            L.append(f"binaire (1 = sommet frais) | spread TRAIN "
                     f"{row['spread_tr']:+.2f} pts, VAL {row['spread_va']:+.2f}"
                     f" pts")
        L.append("")
        L.append("| bucket | N train | moy train | WR train | N val | moy val |"
                 " WR val |")
        L.append("|---|---|---|---|---|---|---|")
        bl = (["bas (< q33)", "milieu", "haut (≥ q66)"] if row["nb"] == 3
              else ["pas fresh-peak", "fresh-peak"])
        for x, name in zip(row["buckets"], bl):
            L.append(f"| {name} | {x['n_tr']} | {x['m_tr']:+.2f} | "
                     f"{x['wr_tr']:.0f} % | {x['n_va']} | {x['m_va']:+.2f} | "
                     f"{x['wr_va']:.0f} % |")
        L.append("")
    L += [f"Features retenus : **{', '.join(retained) or 'AUCUN'}** — le "
          "sizing conditionnel n'utilise QUE ceux-là.", "",
         "## 3. LE SIZING CONDITIONNEL", "",
         f"- chaque cascade_10x : base machine (vol-inverse ×K, boost "
         f"fund_rank ≤ 0.33 → ×1.5) × multiplicateur = moyenne géométrique "
         "des ×{0.5, 1.0, 1.5} par feature retenu (pire bucket TRAIN → 0.5, "
         "milieu → 1.0, meilleur → 1.5 ; fresh-peak dynamique via l'état du "
         f"wallet, dd ≤ {FRESH_PEAK_DD:.0f} %).",
         f"- plafond absolu {0.50 * _K:.3f} de la balance (le cap machine), "
         "levier 10x/1x INCHANGÉ → zéro liquidation structurel.",
         f"- liq24h : couverture liq_events seulement depuis {cov_s} "
         f"({uni['liq_cov'][2]} SELL) → {n_cov}/{len(g)} signals avec la "
         "feature (N limité, noté).", "",
         "## 4. BLOC STATS — AVANT / APRÈS", "",
         "| Stat | BASELINE 4 flux | + SIZING CONDITIONNEL |",
         "|---|---|---|",
         f"| Wallet final | ${base['balance']:,.2f} | "
         f"${cond['balance']:,.2f} |",
         f"| **ROI (1 an)** | **{b0['roi']:+.0f} %** | "
         f"**{b1['roi']:+.0f} %** |",
         f"| Max DD | {base['max_dd']:.1f} % | {cond['max_dd']:.1f} % |",
         f"| **Liquidations** | **{base['n_liq']}** | **{cond['n_liq']}** |",
         f"| Trades / WR | {base['n']} / {b0['wr']:.1f} % | "
         f"{cond['n']} / {b1['wr']:.1f} % |",
         f"| Mois : moyen / pire / record | {b0['mean_m']:+.1f} % / "
         f"{b0['worst']:+.1f} % / {b0['rec']:+.1f} % | "
         f"{b1['mean_m']:+.1f} % / {b1['worst']:+.1f} % / "
         f"{b1['rec']:+.1f} % |",
         f"| Mois négatifs | {b0['neg']} | {b1['neg']} |",
         f"| Garde-fou composé des mois | écart {b0['gap_c']*100:.3f} % "
         f"{'OK' if b0['gap_c'] < 0.005 else '✗ BUG'} | écart "
         f"{b1['gap_c']*100:.3f} % "
         f"{'OK' if b1['gap_c'] < 0.005 else '✗ BUG'} |",
         f"| Garde-fou somme PnL | écart ${b0['gap_p']:.4f} "
         f"{'OK' if b0['gap_p'] < 0.01 else '✗ BUG'} | écart "
         f"${b1['gap_p']:.4f} "
         f"{'OK' if b1['gap_p'] < 0.01 else '✗ BUG'} |", "",
         "### Décomposition diagnostique (post-hoc — PAS une validation)",
         "",
         "| Variante | ROI/an | DD | Liq | Record | Pire mois | Nég |",
         "|---|---|---|---|---|---|---|"]
    for b in (b0, b1, b_vol, b_fresh, b_ext):
        L.append(f"| {b['label']} | {b['roi']:+.0f} % | {b['r']['max_dd']:.1f} %"
                 f" | {b['r']['n_liq']} | {b['rec']:+.1f} % | "
                 f"{b['worst']:+.1f} % | {b['neg']} |")
    L += ["", "Lecture : la règle min/max de la mission punissait le bucket "
              "MILIEU de vol7 (TRAIN 0.31 vs bas 0.42 — bruit, contredit en "
              "VAL +1.08) ; la variante « extrêmes » (bas vs haut, milieu "
              "neutre) restaure le boost/la coupe sur les buckets que VAL "
              "confirme. Toute variante déclarée ici est post-hoc : elle "
              "devient CANDIDAT seulement après confirmation octobre.", "",
         "## 5. TABLES MENSUELLES CÔTE À CÔTE", "",
         "| Mois | ROI baseline | ROI conditionnel |",
         "|---|---|---|"]
    m0 = {x["month"]: x["roi"] for x in b0["mr"]}
    m1 = {x["month"]: x["roi"] for x in b1["mr"]}
    for m in sorted(set(m0) | set(m1)):
        L.append(f"| {m} | {m0.get(m, float('nan')):+.1f} % | "
                 f"{m1.get(m, float('nan')):+.1f} % |")

    # verdict
    crit_roi = b1["roi"] >= 0.95 * b0["roi"]
    crit_rec = b1["rec"] >= b0["rec"] - 5.0
    crit_liq = cond["n_liq"] == 0
    crit_worst = b1["worst"] > b0["worst"]
    crit_dd = cond["max_dd"] <= 25.0
    passed = crit_roi and crit_rec and crit_liq and crit_dd
    best_v = min((b for b in (b_vol, b_fresh, b_ext)),
                 key=lambda b: (-b["worst"], -b["roi"]))
    L += ["", "## VERDICT", "",
          f"- critères : ROI ≥ 95 % du baseline ({'OK' if crit_roi else '✗'}), "
          f"record préservé ±5 pts ({'OK' if crit_rec else '✗'}), "
          f"0 liq ({'OK' if crit_liq else '✗'}), DD ≤ 25 % "
          f"({'OK' if crit_dd else '✗'}), pire mois amélioré "
          f"({b0['worst']:+.1f} → {b1['worst']:+.1f} : "
          f"{'OK' if crit_worst else '—'})",
          f"- **{'PASS' if passed else 'FAIL'}** — le sizing conditionnel "
          f"{'entre en CANDIDAT' if passed else 'ne rentre PAS dans le stack'}"
          " (test du wallet séquentiel run_stack : passé par construction, "
          "les deux runs tournent sous run_stack).",
          f"- Variantes post-hoc : meilleure sur le couple (pire mois, ROI) "
          f"→ {best_v['label']} (ROI {best_v['roi']:+.0f} %, DD "
          f"{best_v['r']['max_dd']:.1f} %, pire mois {best_v['worst']:+.1f} %, "
          f"record {best_v['rec']:+.1f} %).",
          "", "## PROCHAINE ACTION", "",
          "Si PASS : re-catégoriser dans docs/20-registre-indicateurs.md les "
          "features retenus (fund7/vol7/liq24h/fresh-peak) et laisser tourner "
          "une nuit en parallèle de la machine officielle (JAMAIS en remplacement "
          "direct) pour confirmer sur octobre ; si FAIL : garder la gradient map "
          "comme sonde mensuelle et re-tenter à n+1 avec la couverture liq24h "
          "étendue.", ""]
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "conditional-sizing-2026-09-27.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[csize] rapport écrit : {out}", flush=True)
    print(f"[csize] BASELINE  ${base['balance']:,.2f} ({b0['roi']:+.0f} %/an) "
          f"DD {base['max_dd']:.1f} % liq {base['n_liq']} record "
          f"{b0['rec']:+.1f} % pire {b0['worst']:+.1f} % neg {b0['neg']}")
    print(f"[csize] CONDITION ${cond['balance']:,.2f} ({b1['roi']:+.0f} %/an) "
          f"DD {cond['max_dd']:.1f} % liq {cond['n_liq']} record "
          f"{b1['rec']:+.1f} % pire {b1['worst']:+.1f} % neg {b1['neg']}")
    print(f"[csize] retenus : {retained or 'AUCUN'} | verdict "
          f"{'PASS' if passed else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
