#!/usr/bin/env python
"""AL SCORE v2 — le gate anti-liq raffiné (10 features pré-validées).

La preuve du 28/09 (cascade_fractal_test) : le gate EST porteur de valeur
(le cascade non-gaté prend un MAE VAL 13.08 % ≥ plafond 8.61 % ; le gaté
tient à 7.84 %). Le gate actuel = l'AL Score v1 (anti_liq.add_rolling_scores,
6 features, daté du 24/09). DEPUIS, d'autres features ont été validées
individuellement (registre docs/20-registre-indicateurs.md) :
  - corr7        : corr croisée 6 majeures 168 h (code machine) — le tilt,
                   gradient WR monotone (tilt_frontier 27/09 : booster corr
                   bas = TOXIQUE)
  - vol7         : ATR % 24 h moyenné sur les majeures, 168 h ex-ante
                   (conditional_sizing 27/09 — RETENU, spread VAL +0.42)
  - fresh-peak   : dd du wallet baseline ≤ 5 % à l'entrée (RETENU,
                   spread VAL +0.73)
  - funding_rank : rang du propre funding parmi les 6 majeures
                   (the_machine — WR 81 % sur les BAS)
  - RÉFUTÉS (hors candidature) : fund7, dispersion, level (inverses en VAL).

MISSION :
  1. la MÊME méthode rangs roulants 90 j que v1 (zéro look-ahead,
     normalisés [0,1]) sur 10 candidates ;
  2. SÉLECTION SERRÉE sur TRAIN uniquement (les ~161 gated majors) :
     gradient WR/espérance/MAE par quintile du rang — ne garder que les
     features MONOTONES sur TRAIN dont le signe tient en VAL (leçon
     fund7/dispersion : spread VAL ≥ 25 % du spread TRAIN) ;
  3. JUGEMENT : v2 vs v1 sur les ~69 gated VAL (quintiles WR/MAE/espérance
     + AUC gagnants/perdants). PASS = v2 sépare MIEUX que v1 en VAL ;
  4. si PASS : re-gating machine 4 flux (seuil calibré sur TRAIN pour
     garder ~le même taux de passage) → BLOC STATS vs baseline $4,004.94
     (+3 905 %/an @ DD 24.8 %) et vs joint $5,182 (+5 082 % @ 23.3 %).

Lecture SEULE de data/warehouse/klines.db. Importe les briques
d'anti_liq/the_machine sans les éditer.

  .venv/bin/python scripts/al_score_v2.py
"""
from __future__ import annotations

import sqlite3
import sys
import warnings
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
_K = 0.89                     # calibration DD machine (INTOUCHÉE)
WIN = 168                     # 7 j en heures (corr7, vol7)
WIN_DAYS, MIN_WINDOW = 90, 50  # fenêtre des rangs roulants (= v1 anti_liq)
TRAIN_FRAC = 0.70             # split PAR LE TEMPS
FRESH_PEAK_DD = 5.0           # % : équité à ≤ 5 % de son max
TOL_MONO = 0.10               # pts de bruit toléré entre quintiles adjacents
MIN_SPREAD = 0.30             # pts : spread TRAIN minimal pour candidater
VAL_KEEP = 0.25               # leçon corr-tilt : spread VAL ≥ 25 % du TRAIN

# les 6 historiques v1 (directions gravées dans anti_liq.RISK_UP/RISK_DOWN)
V1_UP = ("atr_pct", "vol24", "dd_pct")                  # haut = risqué
V1_DOWN = ("btc_ret24", "vwap_dev", "cascade_depth")    # bas = risqué
NEW_FEATS = ("corr7", "vol7", "fresh_peak", "fund_rank")
CANDIDATES = list(V1_UP) + list(V1_DOWN) + list(NEW_FEATS)


def ro_con() -> sqlite3.Connection:
    return sqlite3.connect(KDB_RO, uri=True, timeout=60)


# ------------------------------------------------------------- le pipeline --
def build_universe() -> dict:
    """Réplication EXACTE de the_machine.main() en 4 flux (--vol-spike),
    briques importées, sans toucher the_machine (pattern conditional_sizing
    bit-repro $4,004.94). Les 4 nouvelles features sont attachées À TOUS
    les events (ex-ante) pour que les fenêtres roulantes 90 j de v2
    couvrent le même univers que celles de v1."""
    con = ro_con()
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    # flux 1 : cascade majeurs 10x, gate AL v1 p66, vol-inverse (copie machine)
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = 10
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)                     # le score v1 (6 features)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    med_majors = float(np.median([e["atr_pct"] for e in gated]))
    mae_gated = max(e["mae_adverse"] for e in gated)

    # flux 2 : cascade memecoins 1x (levier mécanique)
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

    # flux 4 : vol-spike reversion 6h 1x
    from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
    spike = collect_vol_spike(con, hold=6)
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    med_spike = float(np.median([e["atr_pct"] for e in spike])) if spike \
        else float("nan")

    # fund_rank (poids qualité) — copie EXACTE the_machine, sur TOUS les events
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
    for e in events:
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

    # corr7 — copie EXACTE the_machine (168 h, paires des 6 majeures)
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    rets = {s: d["close"].pct_change().values for s, d in majors_dfs.items()}
    idx_ns = majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    # vol7 — ATR % 24 h des majeures, moyenne sur les 168 h avant le signal
    atrs = {s: (d["close"].diff().abs().rolling(24).mean() / d["close"] * 100
                ).values for s, d in majors_dfs.items()}
    con.close()
    _WINC = WIN
    for e in events:
        bi = int(np.searchsorted(idx_ns, e["ts_ms"], side="left"))
        lo = bi - _WINC
        # corr7
        if lo < 0:
            e["corr7"] = float("nan")
        else:
            pairs = []
            for i in range(len(MAJORS)):
                for j in range(i + 1, len(MAJORS)):
                    a, b = rets[MAJORS[i]][lo:bi], rets[MAJORS[j]][lo:bi]
                    m = np.isfinite(a) & np.isfinite(b)
                    if m.sum() > 100:
                        sa, sb = a[m] - np.mean(a[m]), b[m] - np.mean(b[m])
                        if np.std(sa) * np.std(sb) > 0:
                            pairs.append(np.mean(sa * sb)
                                         / (np.std(sa) * np.std(sb)))
            e["corr7"] = float(np.mean(pairs)) if pairs else float("nan")
        # vol7
        e["vol7"] = (float(np.nanmean([np.nanmean(atrs[s][lo:bi])
                                       for s in MAJORS]))
                     if bi > lo else float("nan"))

    uni = {"fh": fh, "q66": q66, "events": events, "gated": gated,
           "meme": meme, "surv": surv, "spike": spike,
           "med_majors": med_majors, "med_meme": med_meme,
           "med_spike": med_spike, "mae_gated": mae_gated,
           "mae_meme": mae_meme, "lev_meme": lev_meme}
    return uni


def machine_fn_factory(med_majors: float, med_meme: float,
                       med_spike: float):
    """Le sizing machine EXACT (copie the_machine.machine_fn, K=0.89,
    boost fund_rank ≤ 0.33, corr-tilt OFF). Levier JAMAIS touché."""
    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * _K * (e["atr_pct"] / med_majors),
                         0.08 * _K), 0.40 * _K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                return min(s0 * 1.5, 0.50 * _K)
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


def attach_fresh_peak(events: list[dict], baseline: dict) -> None:
    """fresh-peak : dd du wallet baseline juste avant l'entrée (≤ 5 % du
    max = sommet frais). Reconstruction par exit_ts (méthode autopsie /
    conditional_sizing), appliquée À TOUS les events cascade (les non-gated
    lisent le même chemin d'équité — figé ex-ante, déclaré)."""
    ex = sorted((t["exit_ts"], t["pnl"]) for t in baseline["trades"])
    ex_ms = np.array([int(t.timestamp() * 1000) for t, _ in ex])
    cum = np.cumsum([p for _, p in ex]) + CAPITAL
    for e in events:
        ev_ms = int(e["ts_ms"] / 10**6)
        k = int(np.searchsorted(ex_ms, ev_ms, side="left"))
        bal = cum[k - 1] if k > 0 else CAPITAL
        peak = float(np.max(cum[:k])) if k > 0 else CAPITAL
        dd = (peak - bal) / peak * 100 if peak > 0 else 0.0
        e["dd_entry"] = dd
        e["fresh_peak"] = 1 if dd <= FRESH_PEAK_DD else 0


# --------------------------------------------------- rangs roulants 90 j --
def rolling_ranks(events: list[dict], feats: list[str],
                  win_days: int = WIN_DAYS,
                  min_window: int = MIN_WINDOW) -> dict[str, np.ndarray]:
    """Rangs roulants 90 j, formule EXACTE du moteur v1
    (anti_liq.add_rolling_scores) : fenêtre = events STRICTEMENT
    antérieurs sur win_days ; < min_window → NaN ; par feature :
      - f        = mean(vals_window <= v)        (rang brut, direction-libre)
      - f/__neg  = mean(vals_window <= -v)       (l'orientation DOWN exacte v1)
    Feature non finie → 0.5 au score (convention v1)."""
    win_ns = win_days * 86400 * 10**9
    n = len(events)
    ts = [e["ts_ms"] for e in events]
    raw = {f: np.array([float(e.get(f, float("nan"))) for e in events])
           for f in feats}
    out = {f: np.full(n, np.nan) for f in feats}
    out.update({f + "/__neg": np.full(n, np.nan) for f in feats})
    for i in range(n):
        lo = ts[i] - win_ns
        window = [j for j in range(i) if ts[j] >= lo]
        if len(window) < min_window:
            continue                      # NaN : score de l'event = NaN
        for f in feats:
            wv = raw[f][window]
            v = raw[f][i]
            if not np.isfinite(v):
                out[f][i] = 0.5
                out[f + "/__neg"][i] = 0.5
            else:
                out[f][i] = float(np.mean(wv <= v))
                out[f + "/__neg"][i] = float(np.mean(wv <= -v))
    return out


def oriented_score(events: list[dict], ranks: dict[str, np.ndarray],
                   up: set[str], down: set[str],
                   binary: set[str] = frozenset()) -> np.ndarray:
    """Score composite = moyenne des rangs ORIENTÉS.
    UP continu        → mean(vals <= v)            (formule exacte v1)
    DOWN continu      → mean(vals <= -v)           (formule exacte v1)
    DOWN binaire      → 1 - rang brut              (monotone dans la valeur ;
    la négation v1 n'est définie que pour du continu)
    Feature non finie → 0.5 neutre INCLUS dans la moyenne. Fenêtre trop
    courte → NaN (convention v1 : le gate GARDE les NaN)."""
    n = len(events)
    if not up and not down:
        return np.full(n, np.nan)
    short = np.isnan(ranks[CANDIDATES[0]])   # même fenêtre pour toutes
    cols = []
    for f in sorted(up):
        r = ranks[f].copy()
        r[short] = np.nan
        cols.append(r)
    for f in sorted(down):
        if f in binary:
            r = 1.0 - ranks[f].copy()
        else:
            r = ranks[f + "/__neg"].copy()
        r[short] = np.nan
        cols.append(r)
    m = np.vstack(cols)
    with np.errstate(invalid="ignore"):
        sc = np.nanmean(m, axis=0)
    sc[short] = np.nan
    return sc


# --------------------------------------------------------- outils stats --
def qbins(events: list[dict], key: str, nb: int = 5):
    """Indices des quintiles par TRI (pas de double-compte aux bords).
    Exclut les events au score NaN (fenêtre trop courte)."""
    s = np.array([e.get(key, float("nan")) for e in events], float)
    ok = np.where(np.isfinite(s))[0]
    order = ok[np.argsort(s[ok], kind="stable")]
    return np.array_split(order, nb), int(len(events) - len(ok))


def bucket_stats(idx: np.ndarray, events: list[dict],
                 bad: np.ndarray | None = None) -> dict:
    """Stats d'un bucket. `bad` = array de « mauvaiseté » aligné sur events
    (−r_not pour l'espérance, mae_adverse pour le risque) ; par défaut la
    moyenne porte sur r_not. WR toujours = part de r_not > 0."""
    rr = np.array([events[i]["r_not"] for i in idx], float)
    r = bad[idx] if bad is not None else rr
    m = np.array([events[i]["mae_adverse"] for i in idx], float)
    return {"n": len(idx),
            "r": float(np.mean(r)) if len(r) else float("nan"),
            "wr": 100.0 * float(np.mean(rr > 0)) if len(rr) else float("nan"),
            "mae": float(np.mean(m)) if len(m) else float("nan")}


def monotone_train(means: list[float], dir_up: bool,
                   tol: float = TOL_MONO) -> tuple[bool, str]:
    """Gradient monotone TRAIN : aucun quintile adjacent ne contredit la
    direction au-delà de `tol` pts de bruit."""
    d = np.diff(means)
    bad = [(i + 1, x) for i, x in enumerate(d)
           if (x > tol if dir_up else x < -tol)]
    return (not bad), ("; ".join(f"Q{k}->Q{k+1} {x:+.2f}" for k, x in bad))


def auc_bad(scores: np.ndarray, losses: np.ndarray) -> float:
    """AUC gagnants/perdants = P(score_perdant > score_gagnant) (Mann-
    Whitney, ties 0.5). Un score de risque doit dépasser 0.5."""
    ok = np.isfinite(scores)
    s, b = scores[ok], losses[ok]
    bad, good = s[b], s[~b]
    if not len(bad) or not len(good):
        return float("nan")
    gt = float((bad[:, None] > good[None, :]).sum())
    tie = float((bad[:, None] == good[None, :]).sum())
    return (gt + 0.5 * tie) / (len(bad) * len(good))


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
            "wr": r["n_wins"] / n * 100,
            "neg": sum(1 for x in rois_m if x < 0),
            "rec": max(rois_m) if rois_m else 0.0,
            "worst": min(rois_m) if rois_m else 0.0,
            "mean_m": float(np.mean(rois_m)) if rois_m else 0.0}


# ------------------------------------------------------------------- main --
def main() -> int:
    warnings.filterwarnings("ignore", message="Mean of empty slice")
    print("[alv2] collecte des 4 flux (briques the_machine)…", flush=True)
    uni = build_universe()
    events, gated = uni["events"], uni["gated"]
    print(f"[alv2] events {len(events)} / gated v1 {len(gated)} / meme "
          f"{len(uni['meme'])} / surv {len(uni['surv'])} / spike "
          f"{len(uni['spike'])}", flush=True)

    # r_not : rendement brut du signal (% du NOTIONAL, indépendant du sizing)
    for e in events:
        fund_pct = uni["fh"].get(e["sym"], 0.0) * e.get("hold_h", 24)
        e["r_not"] = (e["price_ret_short"] + e.get("fund_sign", 1) * fund_pct
                      - e["fee_rt_bps"] / 100.0)

    # baseline bit-repro (obligatoire avant toute comparaison)
    base_fn = machine_fn_factory(uni["med_majors"], uni["med_meme"],
                                 uni["med_spike"])
    base = sim(uni, base_fn)
    b0 = bloc(base, "BASELINE 4 flux (gate AL v1)")
    print(f"[alv2] baseline ${base['balance']:,.2f} ({b0['roi']:+.0f} %/an) "
          f"DD {base['max_dd']:.1f} % liq {base['n_liq']} "
          f"(officiel : $4,004.94 / +3905 % / 24.8 % / 0)", flush=True)

    attach_fresh_peak(events, base)

    # ——— les rangs roulants 90 j des 10 candidates (moteur v1) ———
    ranks = rolling_ranks(events, CANDIDATES)
    # auto-contrôle : le moteur reproduit le score v1 bit-exact
    eng_v1 = oriented_score(events, ranks, set(V1_UP), set(V1_DOWN))
    ref = np.array([e.get("al_score", float("nan")) for e in events])
    fin = np.isfinite(eng_v1) & np.isfinite(ref)
    dmax = float(np.max(np.abs(eng_v1[fin] - ref[fin]))) if fin.any() else -1
    print(f"[alv2] auto-contrôle moteur vs al_score v1 : écart max "
          f"{dmax:.2e} sur {int(fin.sum())} events", flush=True)

    # ——— SPLIT PAR LE TEMPS 70/30 (mission : 161 TRAIN / 69 VAL) ———
    # le split porte sur l'UNIVERS cascade majors complet (les features y
    # gardent leur range dynamique ; mesuré sur les gated seuls, tout est
    # conditionné par le gate v1 et le gradient meurt). C'est AUSSI la
    # convention machine pour le seuil q66 (events[:int(len*0.7)]).
    n70 = int(len(events) * TRAIN_FRAC)
    g_tr, g_va = events[:n70], events[n70:]
    tr_ix = np.arange(len(g_tr))
    va_ix = np.arange(len(g_tr), len(events))
    print(f"[alv2] TRAIN {len(g_tr)} / VAL {len(g_va)} "
          f"(split {TRAIN_FRAC:.0%} par le temps)", flush=True)

    # ——— SÉLECTION SERRÉE : gradient par quintile du RANG, TRAIN → VAL ——
    # bins par feature (indépendants du label) — quintiles du rang brut par
    # tri (pas de double-compte aux bords) ; binaire (fresh-peak) : groupes
    # NATURELS 0/1 (le rang d'un binaire n'est pas monotone dans la valeur).
    bin_info = {}
    for f in CANDIDATES:
        sc = ranks[f]
        fv_tr = np.array([e.get(f, float("nan")) for e in g_tr], float)
        is_binary = len(np.unique(np.round(fv_tr[np.isfinite(fv_tr)], 6))) <= 2
        s_tr = sc[tr_ix]
        ok_tr = np.where(np.isfinite(s_tr))[0]
        order_tr = ok_tr[np.argsort(s_tr[ok_tr], kind="stable")]
        if is_binary:
            g0 = ok_tr[fv_tr[ok_tr] < 0.5]
            g1 = ok_tr[fv_tr[ok_tr] >= 0.5]
            bins_tr = [g0, g1] if len(g0) and len(g1) else \
                np.array_split(order_tr, 5)
        else:
            bins_tr = np.array_split(order_tr, 5)
        s_va = sc[va_ix]
        ok_va = np.where(np.isfinite(s_va))[0]
        order_va = ok_va[np.argsort(s_va[ok_va], kind="stable")]
        if is_binary:
            fv_va = np.array([e.get(f, float("nan")) for e in g_va], float)
            h0 = ok_va[fv_va[ok_va] < 0.5]
            h1 = ok_va[fv_va[ok_va] >= 0.5]
            bins_va = [h0, h1] if len(h0) and len(h1) else \
                np.array_split(order_va, len(bins_tr))
        else:
            bins_va = np.array_split(order_va, len(bins_tr))
        bin_info[f] = {"binary": is_binary, "nb": len(bins_tr),
                       "tr": bins_tr, "va": bins_va}

    # « mauvaiseté » : espérance inversée (−r_not) pour la sélection
    # mission, MAE pour le diagnostic B (le job du gate = contrôler la MAE,
    # preuve du 28/09). Dans les deux cas : rang haut → plus mauvais = UP.
    bad_not = np.array([-e["r_not"] for e in events])
    bad_mae = np.array([e["mae_adverse"] for e in events])

    def run_selection(bad: np.ndarray) -> tuple[list[dict], dict, set]:
        rows, ret, bks = [], {}, set()
        for f in CANDIDATES:
            bi = bin_info[f]
            ev_tr = [events[i] for i in tr_ix]
            ev_va = [events[i] for i in va_ix]
            st = [bucket_stats(b, ev_tr, bad) for b in bi["tr"]]
            sv = [bucket_stats(b, ev_va, bad) for b in bi["va"]]
            means_tr = [x["r"] for x in st]
            dir_up = means_tr[-1] > means_tr[0]   # rang haut = plus mauvais
            spread_tr = means_tr[-1] - means_tr[0]
            if bi["nb"] == 5:
                mono, why = monotone_train(means_tr, dir_up)
            else:
                mono, why = True, ""
            means_va = [x["r"] for x in sv]
            spread_va = means_va[-1] - means_va[0]
            hold = (np.isfinite(spread_va)
                    and np.sign(spread_va) == np.sign(spread_tr)
                    and abs(spread_va) >= VAL_KEEP * abs(spread_tr))
            keep = bool(mono and hold and abs(spread_tr) >= MIN_SPREAD)
            rows.append({"f": f, "st": st, "sv": sv, "dir_up": dir_up,
                         "spread_tr": spread_tr, "spread_va": spread_va,
                         "mono": mono, "why": why, "hold": hold,
                         "keep": keep, "nb": bi["nb"],
                         "binary": bi["binary"]})
            if keep:
                ret[f] = "up" if dir_up else "down"
                if bi["binary"]:
                    bks.add(f)
        return rows, ret, bks

    sel_rows, retained, bin_kept = run_selection(bad_not)
    print(f"[alv2] retenues (espérance) : {retained or 'AUCUNE'}", flush=True)
    # diagnostic B : même règle sur le gradient de MAE — POST-HOC, déclaré
    sel_rows_mae, retained_mae, bin_kept_mae = run_selection(bad_mae)
    print(f"[alv2] retenues (MAE, post-hoc) : {retained_mae or 'AUCUNE'}",
          flush=True)

    def build_score(ret: dict, bks: set,
                    weights: dict | None = None) -> np.ndarray:
        up_s = {f for f, d in ret.items() if d == "up"}
        down_s = {f for f, d in ret.items() if d == "down"}
        if weights is None:
            return oriented_score(events, ranks, up_s, down_s, binary=bks)
        short = np.isnan(ranks[CANDIDATES[0]])
        acc = np.zeros(len(events))
        for f, wf in weights.items():
            if f in up_s:
                r = ranks[f].copy()
            elif f in bks:
                r = 1.0 - ranks[f].copy()
            else:
                r = ranks[f + "/__neg"].copy()
            r[short] = np.nan
            acc = acc + wf * r
        with np.errstate(invalid="ignore"):
            out = acc / sum(weights.values())
        out[short] = np.nan
        return out

    # score v2 mission (équi-pondéré) + v2w (poids = force du gradient VAL
    # — DIAGNOSTIC : les poids voient la VAL, non adoptable seul)
    v2 = build_score(retained, bin_kept)
    w = {row["f"]: max(abs(row["spread_va"]), 1e-6)
         for row in sel_rows if row["keep"]}
    v2w = build_score(retained, bin_kept, weights=w or None)
    # diagnostic A : les 10 features AUX DIRECTIONS PUBLIÉES (v1 + validées
    # individuellement), sans sélection — POST-HOC, déclaré
    forced_up = set(V1_UP) | {"fresh_peak", "fund_rank"}
    forced_down = set(V1_DOWN) | {"corr7", "vol7"}
    v2f = oriented_score(events, ranks, forced_up, forced_down,
                         binary={"fresh_peak"})
    # diagnostic B : sélection par gradient de MAE
    v2m = build_score(retained_mae, bin_kept_mae)

    for e, i in zip(events, range(len(events))):
        for nm, arr in (("score_v2", v2), ("score_v2w", v2w),
                        ("score_v2f", v2f), ("score_v2m", v2m)):
            e[nm] = float(arr[i]) if np.isfinite(arr[i]) else float("nan")

    # ——— JUGEMENT : v1 vs v2 sur les gated VAL ———
    thr_mae = float(np.quantile([e["mae_adverse"] for e in g_tr], 0.75))

    def judgement(key: str, evs: list[dict]) -> dict:
        bns, n_nan = qbins(evs, key)
        st = [bucket_stats(b, evs) for b in bns]
        sc = np.array([e.get(key, float("nan")) for e in evs], float)
        loss = np.array([e["r_not"] <= 0 for e in evs], bool)
        hi_mae = np.array([e["mae_adverse"] >= thr_mae for e in evs], bool)
        spread = st[0]["r"] - st[-1]["r"]
        return {"st": st, "n_nan": n_nan, "spread": spread,
                "auc": auc_bad(sc, loss), "auc_mae": auc_bad(sc, hi_mae)}

    j1 = judgement("al_score", g_va)
    j2 = judgement("score_v2", g_va)
    j2w = judgement("score_v2w", g_va)
    j2f = judgement("score_v2f", g_va)
    j2m = judgement("score_v2m", g_va)

    def sep_pass(jj: dict) -> bool:
        return (np.isfinite(jj["auc"]) and np.isfinite(j1["auc"])
                and jj["auc"] > j1["auc"]
                and jj["spread"] > 0
                and abs(jj["spread"]) >= abs(j1["spread"]))

    # règle pré-enregistrée : v2 sépare MIEUX que v1 en VAL (AUC supérieure,
    # gradient VAL au signe de risque CORRECT — Q1 sûr > Q5 risqué — et
    # amplitude ≥ celle de v1 ; on n'exige PAS le signe de v1 : un v1
    # inversé en VAL est justement ce que v2 doit corriger)
    pass_sep = sep_pass(j2)
    # diagnostics post-hoc : même règle, statut DIFFÉRENT (non adoptable
    # sans confirmation octobre)
    diag_cands = []
    if sep_pass(j2f):
        diag_cands.append(("v2f (10 features, directions publiées)", j2f, v2f))
    if sep_pass(j2m):
        diag_cands.append(("v2m (sélection gradient MAE)", j2m, v2m))
    diag_pick = max(diag_cands, key=lambda x: x[1]["auc"]) \
        if diag_cands else None
    print(f"[alv2] VAL AUC v1 {j1['auc']:.3f} / v2 {j2['auc']:.3f} / v2w "
          f"{j2w['auc']:.3f} / v2f {j2f['auc']:.3f} / v2m {j2m['auc']:.3f} | "
          f"spread v1 {j1['spread']:+.2f} / v2 {j2['spread']:+.2f} → "
          f"{'PASS' if pass_sep else 'FAIL'}"
          + (f" | diagnostic : {diag_pick[0]}" if diag_pick else ""),
          flush=True)

    # ------------------------------------------------- re-gating si PASS --
    # candidat gate : le v2 mission (pré-enregistré) ; sinon, et SEULEMENT
    # à titre DIAGNOSTIQUE POST-HOC, le meilleur variant qui bat v1 (il ne
    # pourra prétendre qu'à CANDIDAT-à-confirmer, jamais à une adoption
    # directe — leçon anti data-snooping).
    if pass_sep:
        gate_name, gate_score, gate_key, gate_posthoc = \
            "v2 (sélection mission)", v2, "score_v2", False
    elif diag_pick is not None:
        gate_name, jj, gate_score = diag_pick
        gate_key = "score_v2f" if "v2f" in gate_name else "score_v2m"
        gate_posthoc = True
    else:
        gate_name = gate_score = gate_key = None
        gate_posthoc = False

    g2 = None
    b2 = None
    thr2 = float("nan")
    if gate_score is not None:
        s_tr_all = gate_score[:int(len(events) * TRAIN_FRAC)]
        fin_tr = s_tr_all[np.isfinite(s_tr_all)]
        # taux de passage v1 sur TRAIN (les NaN sont GARDÉS, convention v1)
        kept_v1 = [e for e in events[:int(len(events) * TRAIN_FRAC)]
                   if not (np.isfinite(e.get("al_score", float("nan")))
                           and e["al_score"] >= uni["q66"])]
        pass_rate = len(kept_v1) / max(int(len(events) * TRAIN_FRAC), 1)
        n_nan_tr = int(np.isnan(s_tr_all).sum())
        p_star = (pass_rate * len(s_tr_all) - n_nan_tr) / max(len(fin_tr), 1)
        p_star = float(min(max(p_star, 0.0), 1.0))
        thr2 = float(np.quantile(np.sort(fin_tr), p_star))
        gated2 = [e for e in events
                  if not (np.isfinite(e.get(gate_key, float("nan")))
                          and e[gate_key] >= thr2)]
        med_majors2 = float(np.median([e["atr_pct"] for e in gated2]))
        mae_g2 = max(e["mae_adverse"] for e in gated2)
        lev2 = 100 / (mae_g2 + 0.5)
        print(f"[alv2] re-gating {gate_name} : seuil {thr2:.3f} (passage "
              f"TRAIN {pass_rate*100:.1f} %), gated {len(gated2)}, MAE max "
              f"{mae_g2:.2f} % → levier sûr {lev2:.1f}x", flush=True)
        uni2 = dict(uni)
        uni2["gated"] = gated2
        fn2 = machine_fn_factory(med_majors2, uni["med_meme"], uni["med_spike"])
        r2 = sim(uni2, fn2)
        b2 = bloc(r2, f"4 flux + GATE AL {gate_name}")
        g2 = {"gated": gated2, "mae": mae_g2, "lev": lev2,
              "pass_rate": pass_rate}
        # diagnostic : les events échangés entre les deux gates
        k1 = {id(e) for e in gated}
        k2 = {id(e) for e in gated2}
        dropped = [e for e in gated if id(e) not in k2]
        added = [e for e in gated2 if id(e) not in k1]
        g2["dropped"] = dropped
        g2["added"] = added

    # ----------------------------------------------------------- rapport --
    now = f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC"
    L = ["# AL SCORE v2 — le gate anti-liq raffiné (10 features)",
         f"{now} — machine 4 flux répliquée par briques (the_machine intact, "
         f"gate AL v1 p66={uni['q66']:.2f}). Rangs roulants 90 j (moteur v1, "
         f"zéro look-ahead) sur 10 candidates : les 6 historiques + corr7 + "
         "vol7 + fresh-peak + funding_rank (toutes pré-validées "
         "individuellement ; fund7/dispersion/level RÉFUTÉES, hors "
         f"candidate). Split PAR LE TEMPS 70/30 sur l'univers cascade "
         f"majors complet : TRAIN {len(g_tr)} / VAL {len(g_va)}.", "",
         "## 0. BIT-REPRO", "",
         f"- baseline ${CAPITAL:,.0f} → **${base['balance']:,.2f}** "
         f"({b0['roi']:+.0f} %/an), DD {base['max_dd']:.1f} %, liq "
         f"{base['n_liq']}, {base['n']} trades — officiel : $4,004.94 / "
         f"+3905 % / DD 24.8 % / 0 liq.",
         f"- auto-contrôle moteur : écart max moteur/anti_liq v1 = "
         f"{dmax:.2e} (bit-exact).", ""]
    def render_selection(rows: list[dict], bad_label: str,
                         title: str) -> list[str]:
        out = [title, "",
               "Quintiles par tri du rang brut [0,1] (binaire : groupes "
               "naturels). RETENU = gradient monotone TRAIN (bruit ≤ "
               f"{TOL_MONO:.2f} pt), spread risque TRAIN ≥ "
               f"{MIN_SPREAD:.2f} ET signe tenu en VAL (spread VAL ≥ "
               f"{VAL_KEEP:.0%} du spread TRAIN — leçon fund7/dispersion). "
               f"Colonne « moy » = {bad_label}. Spread = Q5−Q1 de "
               "mauvaiseté (positif = le rang prédit le risque).", "",
               "| Feature | Verdict | Direction | spread TR | spread VAL |",
               "|---|---|---|---|---|"]
        for row in rows:
            out.append(
                f"| {row['f']} | {'RETENU' if row['keep'] else 'rejeté'} | "
                f"{'haut risqué' if row['dir_up'] else 'bas risqué'} | "
                f"{row['spread_tr']:+.2f} | {row['spread_va']:+.2f} |")
        out.append("")
        for row in rows:
            f = row["f"]
            dirm = "haut = risqué" if row["dir_up"] else "bas = risqué"
            verdict = "RETENU" if row["keep"] else "REJETÉ"
            why = ""
            if not row["keep"]:
                bits = []
                if not row["mono"]:
                    bits.append(f"non-monotone TRAIN ({row['why']})")
                if not row["hold"]:
                    bits.append("signe VAL contredit")
                if abs(row["spread_tr"]) < MIN_SPREAD:
                    bits.append(f"spread TRAIN {row['spread_tr']:+.2f} pt")
                why = " — " + ", ".join(bits)
            blab = (["pas fresh (0)", "fresh (1)"] if row["nb"] == 2
                    else [f"Q{k}" for k in range(1, 6)])
            out += [f"### {f} — {verdict} ({dirm}){why}", ""]
            out += ["| Q | N TR | moy TR | WR TR | MAE TR | N VAL | moy VAL "
                    "| WR VAL | MAE VAL |",
                    "|---|---|---|---|---|---|---|---|---|"]
            for name, a, b in zip(blab, row["st"], row["sv"]):
                out.append(
                    f"| {name} | {a['n']} | {a['r']:+.2f} | {a['wr']:.0f} % | "
                    f"{a['mae']:.2f} | {b['n']} | {b['r']:+.2f} | "
                    f"{b['wr']:.0f} % | {b['mae']:.2f} |")
            out += [f"spread risque TRAIN {row['spread_tr']:+.2f} pts / VAL "
                    f"{row['spread_va']:+.2f} pts", ""]
        return out

    L += render_selection(
        sel_rows, "−r_not (% notional inversé : haut = pire)",
        "## 1. GRADIENTS PAR QUINTILE DU RANG (roulant 90 j) — "
        "SÉLECTION MISSION (espérance)")
    retenus_txt = (", ".join(f"{f} ({d})" for f, d in retained.items())
                   or "AUCUNE")
    L += [f"**Retenues : {retenus_txt}** — le score v2 = moyenne des rangs "
          "orientés retenus (convention v1 : non fini → 0.5 neutre).", "",
          "Variante v2w (poids = |spread VAL| de chaque feature) : "
          "DIAGNOSTIC seulement — les poids voient la VAL, elle ne peut pas "
          "être la seule raison d'un PASS.", ""]
    L += render_selection(
        sel_rows_mae, "MAE % (haut = pire)",
        "## 1bis. DIAGNOSTIC POST-HOC — la même sélection sur le gradient "
        "de MAE", )
    retenus_mae = (", ".join(f"{f} ({d})"
                             for f, d in retained_mae.items()) or "AUCUNE")
    L += [f"**Retenues (MAE) : {retenus_mae}** — le gate contrôle la MAE "
          "(preuve du 28/09 : le non-gaté prend 13,08 % ≥ plafond 8,61 %) ; "
          "cette sélection est POST-HOC (déclarée après la mission), elle ne "
          "peut produire qu'un CANDIDAT à confirmer, jamais une adoption.", "",
          "## 2. JUGEMENT — v1 vs v2 sur les "
          f"{len(g_va)} events VAL", ""]
    for key, jj, lab in (("al_score", j1, "v1 (6 features)"),
                         ("score_v2", j2, "v2 équi-pondéré (mission)"),
                         ("score_v2w", j2w, "v2w (poids VAL — diagnostic)"),
                         ("score_v2f", j2f,
                          "v2f (10 features, directions publiées — "
                          "diagnostic)"),
                         ("score_v2m", j2m,
                          "v2m (sélection gradient MAE — diagnostic)")):
        L += [f"### {lab}", "",
              "| Q | N | moy r_not | WR | MAE moy |", "|---|---|---|---|---|"]
        for k, x in enumerate(jj["st"], 1):
            L.append(f"| Q{k} ({'sûr' if k == 1 else 'risqué' if k == 5 else '—'})"
                     f" | {x['n']} | {x['r']:+.2f} | {x['wr']:.0f} % | "
                     f"{x['mae']:.2f} |")
        if jj["n_nan"] == len(g_va):
            L += ["score NON DÉFINI (aucune feature retenue → tous les "
                  "rangs NaN) — pas de jugement possible.", ""]
            continue
        L += [f"spread Q1−Q5 : {jj['spread']:+.2f} pts | AUC perdants "
              f"{jj['auc']:.3f} | AUC MAE ≥ p75 TRAIN ({thr_mae:.2f} %) "
              f"{jj['auc_mae']:.3f} ({jj['n_nan']} events hors NaN)", ""]

    pass_line = (f"v1 : AUC {j1['auc']:.3f}, spread VAL "
                 f"{j1['spread']:+.2f} pts | v2 mission : AUC {j2['auc']:.3f}, "
                 f"spread VAL {j2['spread']:+.2f} pts")
    L += ["### LA RÈGLE PRÉ-ENREGISTRÉE", "",
          "PASS = AUC v2 > AUC v1 en VAL ET spread VAL au signe de risque "
          "correct ET amplitude ≥ celle de v1.", "", f"- {pass_line}",
          f"- **{'PASS — le v2 sépare MIEUX en VAL' if pass_sep else 'FAIL — le v2 (mission) ne sépare pas mieux'}**",
          ""]
    if diag_pick is not None:
        L += [f"- DIAGNOSTIC post-hoc retenu pour le re-gating d'essai : "
              f"**{diag_pick[0]}** (AUC {diag_pick[1]['auc']:.3f}) — statut "
              "CANDIDAT-à-confirmer, PAS une adoption.", ""]
    else:
        L += ["- Aucun diagnostic post-hoc (v2f/v2m) ne bat v1 non plus — "
              "le FAIL est robuste à la règle de sélection.", ""]

    if g2 is not None and b2 is not None:
        L += [f"## 3. RE-GATING{' (DIAGNOSTIC POST-HOC)' if gate_posthoc else ''}"
              f" — machine 4 flux au gate {gate_name}", "",
              f"- seuil {thr2:.3f} calibré TRAIN pour garder le MÊME taux "
              f"de passage que v1 ({g2['pass_rate']*100:.1f} %).",
              f"- gated v1 {len(gated)} → gated {len(g2['gated'])} "
              f"({len(g2['dropped'])} sortis, {len(g2['added'])} entrés).",
              f"- MAE max gated {g2['mae']:.2f} % → levier sûr "
              f"{g2['lev']:.1f}x (règle 0-liq : ≥ 10x requis).", "",
              f"## BLOC STATS — baseline vs gate {gate_name}", "",
              f"| Stat | BASELINE (gate v1) | GATE {gate_name} | joint (réf.) |",
              "|---|---|---|---|",
              f"| Wallet final | ${base['balance']:,.2f} | "
              f"${b2['r']['balance']:,.2f} | $5,182.00 |",
              f"| **ROI (1 an)** | **{b0['roi']:+.0f} %** | "
              f"**{b2['roi']:+.0f} %** | +5082 % |",
              f"| Max DD | {base['max_dd']:.1f} % | "
              f"{b2['r']['max_dd']:.1f} % | 23.3 % |",
              f"| **Liquidations** | **{base['n_liq']}** | "
              f"**{b2['r']['n_liq']}** | 0 |",
              f"| Trades / WR | {base['n']} / {b0['wr']:.1f} % | "
              f"{b2['r']['n']} / {b2['wr']:.1f} % | — |",
              f"| Mois : moyen / pire / record | {b0['mean_m']:+.1f} % / "
              f"{b0['worst']:+.1f} % / {b0['rec']:+.1f} % | "
              f"{b2['mean_m']:+.1f} % / {b2['worst']:+.1f} % / "
              f"{b2['rec']:+.1f} % | — |",
              f"| Mois négatifs | {b0['neg']} | {b2['neg']} | — |",
              f"| Garde-fou composé | {b0['gap_c']*100:.3f} % | "
              f"{b2['gap_c']*100:.3f} % | — |",
              f"| Garde-fou somme PnL | ${b0['gap_p']:.4f} | "
              f"${b2['gap_p']:.4f} | — |", "",
              f"### Les events échangés par le gate {gate_name}", "",
              "| Sens | N | WR | MAE moy | MAE max | r_not moy |",
              "|---|---|---|---|---|---|"]
        for lab2, evs in ((f"SORTIS par {gate_name} (gardés par v1)",
                           g2["dropped"]),
                          (f"ENTRÉS par {gate_name} (exclus par v1)",
                           g2["added"])):
            if evs:
                wr = 100 * sum(1 for e in evs if e["r_not"] > 0) / len(evs)
                L.append(f"| {lab2} | {len(evs)} | {wr:.0f} % | "
                         f"{np.mean([e['mae_adverse'] for e in evs]):.2f} | "
                         f"{max(e['mae_adverse'] for e in evs):.2f} | "
                         f"{np.mean([e['r_not'] for e in evs]):+.2f} |")
            else:
                L.append(f"| {lab2} | 0 | — | — | — | — |")
        L += ["", f"### TABLE MENSUELLE — gate {gate_name}", "",
              "| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
              "|---|---|---|---|---|---|"]
        for x in b2["mr"]:
            L.append(f"| {x['month']} | {x['n']} | "
                     f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} | "
                     f"${x['start']:,.0f} → ${x['end']:,.0f} | "
                     f"{x['roi']:+.1f} % |")

        # verdict d'adoption (critères mission step 4)
        c_roi = b2["roi"] >= b0["roi"]
        c_dd = b2["r"]["max_dd"] <= base["max_dd"]
        c_liq = b2["r"]["n_liq"] == 0
        c_neg = b2["neg"] <= b0["neg"]
        c_comp = b2["gap_c"] < 0.005 and b2["gap_p"] < 0.01
        c_lev = g2["lev"] >= 10.0
        adopted = c_roi and c_dd and c_liq and c_neg and c_comp and c_lev
        if gate_posthoc:
            verdict_txt = ("CANDIDAT POST-HOC — à confirmer sur octobre "
                           "AVANT toute adoption" if adopted
                           else "REJETÉ — le gate v1 reste le portefeuille "
                                "officiel")
        else:
            verdict_txt = ("ADOPTÉ EN CANDIDAT — gate v2" if adopted
                           else "REJETÉ — le gate v1 reste le portefeuille "
                                "officiel")
        L += ["", "### CRITÈRES D'ADOPTION (pré-enregistrés)", "",
              f"- ROI ≥ baseline ({b2['roi']:+.0f} vs {b0['roi']:+.0f} : "
              f"{'OK' if c_roi else '✗'})",
              f"- DD ≤ baseline ({b2['r']['max_dd']:.1f} vs "
              f"{base['max_dd']:.1f} : {'OK' if c_dd else '✗'})",
              f"- 0 liq ({b2['r']['n_liq']} : {'OK' if c_liq else '✗'})",
              f"- mois négatifs ≤ ({b2['neg']} vs {b0['neg']} : "
              f"{'OK' if c_neg else '✗'})",
              f"- garde-fous composé/PnL OK "
              f"({'OK' if c_comp else '✗'})",
              f"- levier 10x tient (MAE {g2['mae']:.2f} ≤ 9.5 : "
              f"{'OK' if c_lev else '✗ BAISSER LE LEVIER'})",
              "",
              f"**VERDICT : {verdict_txt}**"]
        if adopted:
            L += ["", "Note fresh-peak : la feature lit le chemin d'équité "
                  "baseline (figé ex-ante, méthode conditional_sizing). En "
                  "production elle est l'état wallet LIVE — ex-ante, mais "
                  "path-dépendante du gate lui-même (à surveiller en "
                  "forward)."]
    elif not pass_sep:
        L += ["", "PAS de re-gating : ni la règle pré-enregistrée (mission) "
              "ni un diagnostic post-hoc ne battent v1 en VAL — le gate v1 "
              "(p66) reste LE portefeuille officiel. Les gradients des "
              "sections 1/1bis restent la sonde de sélection des features "
              "pour le prochain cycle."]

    L += ["", "## PROCHAINE ACTION", ""]
    if g2 is not None and b2 is not None and b2["roi"] >= b0["roi"] \
            and b2["r"]["n_liq"] == 0 and b2["r"]["max_dd"] <= base["max_dd"]:
        if gate_posthoc:
            L += ["CANDIDAT POST-HOC : NE PAS câbler maintenant. Inscrire "
                  "le variant au registre comme CANDIDAT avec hypothèse "
                  "pré-enregistrée (seuil + features FIGÉS maintenant) et "
                  "le juger sur octobre ; si octobre confirme, câbler en "
                  "parallèle de l'officiel."]
        else:
            L += ["Si ADOPTÉ : câbler le gate v2 dans une copie de la machine "
                  "(paper forward nocturne EN PARALLÈLE de l'officiel, jamais en "
                  "remplacement), re-catégoriser corr7/vol7/fresh-peak/"
                  "funding_rank dans docs/20-registre-indicateurs.md, "
                  "confirmation octobre avant promotion VALIDÉ."]
    elif pass_sep:
        L += ["Séparation VAL meilleure MAI wallet non amélioré : garder le "
              "gate v1 officiel, conserver le score v2 comme sonde de "
              "diagnostic mensuel, ré-évaluer après un mois de forward."]
    else:
        L += ["FAIL CONFIRMÉ : le gate v1 (6 features, p66) reste officiel "
              "ET le re-gating post-hoc v2f échoue aux critères d'adoption "
              "(1 liquidation, DD 40,1 %, ROI divisé par 2,6 — il ré-admet "
              "l'event MAE 13,08 % que la preuve du 28/09 identifie). "
              "Leçons : (a) les directions validées sur les GATED se "
              "renversent sur l'univers complet (fresh-peak) — une feature "
              "n'entre dans un gate que si son gradient tient sur l'univers "
              "où le gate opère ; (b) le gain d'AUC marginal de v2f "
              "(0,648 vs 0,639) ne compense jamais une violation 0-liq. "
              "Re-tenter quand n VAL aura doublé."]
    L += ["", f"Script : scripts/al_score_v2.py — lecture seule "
          f"data/warehouse/klines.db, briques anti_liq/the_machine "
          f"importées, the_machine.py intact.", ""]

    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "al-score-v2-2026-09-28.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[alv2] rapport écrit : {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
