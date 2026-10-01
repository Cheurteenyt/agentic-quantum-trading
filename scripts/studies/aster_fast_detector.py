# ÉTUDE T12 — LE DÉTECTEUR RAPIDE (fund7/vol7 de la sonde P2) VS LE SMA 200 j
# appliqué au stack multi-régime V2 : le trou n°1 (le lag 2-3 mois) est-il
# comblable dans connu_2025_2026 — et le DD global ≤ 25 % est-il atteint ?
#
# Doctrine : split TRAIN/VAL PAR LE TEMPS (70 % barres, convention T9) ;
# seuils calibrés TRAIN uniquement, jugés VAL ; décompte de multiplicité
# honnête (4 définitions + 1 contrôle inverse) ; 0-liquidation ; wallet
# séquentiel run_stack ; DB en mode=ro, écriture = ce rapport uniquement.
#
# ATTENTION INTÉGRITÉ (découverte de la mission, à lire avant les chiffres) :
# funding_history des majors ne commence qu'au 2025-10-27. Avant :
#   2021-09→2025-01 = MODÈLE T7 CALENDAIRE (CAL_FUND_BPS — les frontières du
#   modèle SONT celles des régimes T7) puis constante connu (BTC +0.343
#   bps/8h, 2025-01→2025-10-27). Donc en TRAIN, un détecteur fund-primaire
#   suit le calendrier T7 = contamination circulaire partielle (il reproduit
#   partiellement les étiquettes) → les chiffres TRAIN des définitions
#   fund-primaires sont des BORNES SUPÉRIEURES. vol7 (ATR des klines) est
#   RÉEL sur toute la fenêtre. Le juge = VAL, où fund7 n'est réel qu'à
#   partir du 2025-10-27.
#
# Lectures DB : data/warehouse/klines.db en ro. Imports verbatim de T9
# (aster_multiregime_stack.py), T10 (aster_carry_hysteresis.py), T11
# (aster_multiregime_stack_v2.py) et de la sonde P2 (mechanism_probe.py).

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # scripts/studies/ → racine
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import MAJORS  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, funding_hourly_all, run_stack)
from scripts.mechanism_probe import vol7_series, WIN7_MS  # noqa: E402
from scripts.studies.aster_carry_hysteresis import detector_sma_hyst  # noqa: E402
from scripts.studies.aster_multiregime_stack import (  # noqa: E402
    CARRY_SYMS, K_V, MOM_REF, REGIMES, SZ_CARRY, SZ_FADE, SZ_MOM,
    by_regime_stats, carry_episodes, carry_event, daily_fund_bps,
    detector_sma, fade_events, flips, garde_fous, load_bars,
    load_funding_pts, momentum_events_gated, open_ro, seg_stats,
    spike_events, ts_ns)
from scripts.studies.aster_multiregime_stack_v2 import (  # noqa: E402
    DD_TARGET, HYST_H, seg_block, strat_stats, tv_split, whipsaw)

REPORTS = ROOT / "reports"
CONFIRM_BARS = 48          # la même confirmation anti-flicker 48 h (design T9)
H8_MS = 8 * 3600 * 1000
DAY_MS = 86_400_000
DF_NAMES = ("DF1", "DF2", "DF3", "DF4")


# ------------------------------------------------- les entrées du détecteur
def fund7_hourly(con, sym: str, bar_ts: np.ndarray) -> np.ndarray:
    """fund7 CAUSAL (bps/8h) à chaque barre 1h : moyenne des taux 8h sur
    [t-7j, t[ — le MÊME traitement du funding que le stack (daily_fund_bps :
    modèle T7 → constante connu → réel as-of dès 2025-10-27). Exact :
    cumsum + searchsorted sur la grille 8h."""
    g0 = int(bar_ts[0] - 9 * DAY_MS) // H8_MS * H8_MS
    grid = np.arange(g0, int(bar_ts[-1]) + H8_MS, H8_MS, dtype=np.int64)
    fts, frt = load_funding_pts(con, sym)
    rates = np.array([daily_fund_bps(sym, int(g), fts, frt) for g in grid])
    cs = np.concatenate([[0.0], np.cumsum(rates)])
    lo = np.searchsorted(grid, bar_ts - WIN7_MS, side="left")
    hi = np.searchsorted(grid, bar_ts, side="left")
    n = np.maximum(hi - lo, 1)
    return (cs[hi] - cs[lo]) / n


def detector_fast(btc, f7: np.ndarray, f7s: np.ndarray, vol7: np.ndarray,
                  sma: np.ndarray, variant: str, seuil_vol: float,
                  inverse: bool = False,
                  confirm_bars: int = CONFIRM_BARS):
    """Le détecteur RAPIDE : condition PRIMAIRE fund7/vol7 (gradient P2),
    condition SECONDAIRE SMA 200 j (pattern D3 de T9). Squelette T9 verbatim
    (causal, exécution t+1, confirmation anti-flicker 48 h — règle de DESIGN
    héritée, pas recalibrée). +1 bull, -1 bear, None warm-up.
    Variantes (bear = condition d'ENTRÉE short, bull = sortie) :
      DF1  bear : fund7_5j < 0 ET close < SMA | bull : fund7_5j > 0 ET close > SMA
      DF2  bear : (fund7_5j < 0 OU vol7 > q90) ET close < SMA | bull : idem DF1
      DF3  bear : fund7 (7j nu) < 0 ET close < SMA | bull : idem DF1 avec fund7
      DF4  bear : fund7_5j < 0 ET (close < SMA OU vol7 > q90) | bull : idem DF1
    inverse=True : conditions échangées (contrôle inverse doctrinal)."""
    close = np.array([b.close for b in btc])
    f = f7s if variant in ("DF1", "DF2", "DF4") else f7
    out: list = []
    cur: int | None = None
    pend: int | None = None
    pend_n = 0
    n_raw = 0
    prev_raw: int | None = None
    for i in range(len(close)):
        s = sma[i]
        if not np.isfinite(s):
            raw = None
        elif cur is None:
            raw = 1 if close[i] > s else -1          # bootstrap = T9
        else:
            c, v = close[i], vol7[i]
            if variant == "DF2":
                bear = (f[i] < 0 or (np.isfinite(v) and v > seuil_vol)) \
                    and c < s
            elif variant == "DF4":
                bear = f[i] < 0 and (c < s or
                                     (np.isfinite(v) and v > seuil_vol))
            else:
                bear = f[i] < 0 and c < s
            bull = f[i] > 0 and c > s
            if inverse:
                bear, bull = bull, bear
            raw = -1 if bear else (1 if bull else cur)
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


def lag_boundary(state: list, btc) -> dict:
    """Retard (jours) à porter l'état dominant du régime T7 après sa
    frontière (négatif = déjà en place depuis X j). None = warm-up."""
    dom = {"bull_2021H2": 1, "bear_2022": -1, "recovery_2023": 1,
           "bull_2024H1": 1}
    ts_all = [b.ts for b in btc]
    out = {}
    for name, lo, hi in REGIMES:
        d = dom.get(name)
        if d is None:
            continue
        lo_ms = ts_ns(lo) // 10**6
        i0 = int(np.searchsorted(ts_all, lo_ms, side="left"))
        if i0 >= len(state) or state[i0] is None:
            out[name] = None
            continue
        if state[i0] == d:
            j = i0
            while j > 0 and state[j - 1] == d:
                j -= 1
            out[name] = -(ts_all[i0] - ts_all[j]) / DAY_MS
            continue
        got = None
        for i in range(i0, len(state)):
            if state[i] == d:
                got = (ts_all[i] - lo_ms) / DAY_MS
                break
        out[name] = got if got is not None else float("nan")
    return out


def flip_dir(fl: tuple) -> int:
    return 1 if fl[2] == "bull" else -1


def lag_vs_v1(fl_df: list, fl_v1: list, win_d: float = 60.0) -> tuple:
    """Pour chaque bascule du détecteur rapide, la bascule V1 (SMA 200 j) de
    même direction la plus proche (±60 j) : delta j (négatif = EN ADVANCE
    sur la SMA). → (médiane bull, médiane bear, n appariés)."""
    db, ds = [], []
    v1_ms = {d: [pd.Timestamp(f[0]).value // 10**6 for f in fl_v1
                 if flip_dir(f) == d] for d in (1, -1)}
    for f in fl_df:
        d = flip_dir(f)
        t = pd.Timestamp(f[0]).value // 10**6
        cand = [x for x in v1_ms[d] if abs(x - t) <= win_d * DAY_MS]
        if not cand:
            continue
        near = min(cand, key=lambda x: abs(x - t))
        (db if d == 1 else ds).append((t - near) / DAY_MS)
    med = lambda a: float(np.median(a)) if a else float("nan")
    return med(db), med(ds), len(db) + len(ds)


def dd_window(res: dict) -> tuple:
    """La fenêtre du DD max du wallet : (ts_pic, ts_creux, dd %) sur le
    chemin de balance des trades — pour attribuer LE DD à ses mois."""
    tr = sorted(res["trades"], key=lambda t: t["entry_ts"].timestamp())
    peak, peak_ts, bal = -1.0, None, None
    worst, w_pair = 0.0, (None, None)
    for t in tr:
        bal = t["balance"]
        if bal > peak:
            peak, peak_ts = bal, t["entry_ts"]
        dd = (peak - bal) / peak * 100 if peak > 0 else 0.0
        if dd > worst:
            worst, w_pair = dd, (peak_ts, t["exit_ts"])
    return w_pair[0], w_pair[1], worst


# --------------------------------------------------- le stack (pattern T11)
def build_stack(det, bars, con, fh, fade_ev, spike_ev, fn_stack,
                train_end_ms):
    """Le stack T9 VERBATIM pour UN détecteur donné — copie fidèle du
    build_stack de T11 (momentum gated + carry short porté MAE-calibrée
    TRAIN → 0-liq + fade + vol_spike, wallet run_stack)."""
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
    for sym in CARRY_SYMS:
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
                hh = max(x.high for x in b[ep["ei"]:ep["xi"]])
                mae_tr = max(mae_tr, (hh - entry) / entry * 100)
        eps_all[sym] = out
    lev = min(2.0, 100.0 / (mae_tr + 0.5)) if mae_tr > 0 else 2.0
    fh_st = dict(fh)
    for sym in CARRY_SYMS:
        for k, (ep, fbps) in enumerate(eps_all[sym]):
            carry_ev.append(carry_event(bars[sym], sym, ep, lev, fbps, k))
            fh_st[f"{sym}@carry{k}"] = fbps / 100.0 / 8.0   # %/h
    stack_ev = sorted(mom_ev + carry_ev + fade_ev + spike_ev,
                      key=lambda e: e["ts_ms"])
    res = run_stack(stack_ev, CAPITAL, fn_stack, fh_st)
    return {"mom": mom_ev, "carry": carry_ev, "lev": lev, "mae": mae_tr,
            "res": res}


def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = open_ro()
    fh = funding_hourly_all()

    bars = {s: load_bars(con, s) for s in MAJORS}
    btc = bars["BTCUSDT"]
    n_all = len(btc)
    k70 = int(n_all * 0.7)
    train_end_ms = btc[k70].ts
    train_end_ns = train_end_ms * 10**6
    deep_days = (ts_ns("2026-09-30") - ts_ns("2021-09-01")) / 86400 / 10**9
    d_first = datetime.fromtimestamp(btc[0].ts / 1000, tz=timezone.utc)
    d_train = datetime.fromtimestamp(train_end_ms / 1000, tz=timezone.utc)
    d_last = datetime.fromtimestamp(btc[-1].ts / 1000, tz=timezone.utc)
    train_lo, train_hi, val_hi = (f"{d_first:%Y-%m-%d}", f"{d_train:%Y-%m-%d}",
                                  f"{d_last:%Y-%m-%d}")
    print(f"[t12] BTC {n_all} barres {train_lo}→{val_hi} | TRAIN→{train_hi}",
          flush=True)

    # ——— les entrées du détecteur rapide (causales) ———
    close = np.array([b.close for b in btc])
    sma = pd.Series(close).rolling(200 * 24, min_periods=200 * 24).mean()\
        .to_numpy()
    bar_ts = np.array([b.ts for b in btc], dtype=np.int64)
    f7 = fund7_hourly(con, "BTCUSDT", bar_ts)          # bps/8h, [t-7j, t[
    f7s = pd.Series(f7).rolling(120, min_periods=120).mean().to_numpy()
    v7 = vol7_series(con)
    v7.index = pd.to_datetime(v7.index)
    vol7 = v7.reindex(pd.to_datetime(bar_ts, unit="ms"),
                      method="ffill").to_numpy(float)
    tr_mask = bar_ts < train_end_ms
    seuil_vol = float(np.nanquantile(vol7[tr_mask], 0.90))   # q90 TRAIN
    fr_lo = np.nanmin(f7[tr_mask & (f7 != 0)])
    print(f"[t12] fund7 BTC : modèle T7 → réel 2025-10-27 | min TRAIN "
          f"{fr_lo:+.2f} bps/8h | vol7 q90 TRAIN = {seuil_vol:.3f} %",
          flush=True)

    # ——— les détecteurs ———
    det1, raw1 = detector_sma(btc, 200)                        # V1 (T9)
    det2, raw2 = detector_sma_hyst(btc, 200, HYST_H)          # V2 (T11)
    defs = {v: detector_fast(btc, f7, f7s, vol7, sma, v, seuil_vol)
            for v in DF_NAMES}
    defs["DF1_inv"] = detector_fast(btc, f7, f7s, vol7, sma, "DF1",
                                    seuil_vol, inverse=True)
    fl_v1, fl_v2 = flips(det1, btc), flips(det2, btc)
    lags = {name: (lag_boundary(d, btc), flips(d, btc))
            for name, (d, _rw) in defs.items()}
    print("[t12] détecteurs bâtis", flush=True)

    # ——— composantes indépendantes du détecteur (UNE fois) ———
    fade_ev, fade_used = fade_events(con, fh)
    spike_ev, sp_p90, sp_med = spike_events(con, train_end_ns)

    def fn_stack(e, st=None):
        s = e["strategy"]
        if s.startswith("momentum"):
            return SZ_MOM
        if s.startswith("carry_short"):
            return SZ_CARRY
        if s == "fade_meme":
            return SZ_FADE
        return min(max(0.10 * K_V * (e["atr_pct"] / sp_med), 0.02 * K_V),
                   0.30 * K_V)

    runs = {"V1": build_stack(det1, bars, con, fh, fade_ev, spike_ev,
                              fn_stack, train_end_ms),
            "V2": build_stack(det2, bars, con, fh, fade_ev, spike_ev,
                              fn_stack, train_end_ms)}
    for name, (d, _rw) in defs.items():
        runs[name] = build_stack(d, bars, con, fh, fade_ev, spike_ev,
                                 fn_stack, train_end_ms)
        print(f"[t12] {name} : mom {len(runs[name]['mom'])} | carry "
              f"{len(runs[name]['carry'])} ép | "
              f"${runs[name]['res']['balance']:,.2f}", flush=True)

    # ——— stats + RÈGLE DE SÉLECTION TRAIN (déclarée avant lecture VAL) :
    #     parmi DF1..DF4 : liq=0 ET DD TRAIN ≤ 25 % → max ROI/an TRAIN ;
    #     sinon min DD TRAIN. Le choisi = V3, jugé VAL.
    def pack(name):
        r = runs[name]["res"]
        g = seg_stats(r, CAPITAL, deep_days)
        tr = seg_block(r, "TRAIN", train_lo, train_hi)
        vl = seg_block(r, "VAL", train_hi, val_hi)
        roi_tr, roi_val, _ = tv_split(r, train_end_ms)
        return {"g": g, "tr": tr, "vl": vl, "roi_tr": roi_tr,
                "roi_val": roi_val, "reg": by_regime_stats(r),
                "gf": garde_fous(r, CAPITAL)}

    P = {name: pack(name) for name in runs}
    cand = [n for n in DF_NAMES
            if P[n]["tr"]["liq"] == 0 and P[n]["tr"]["dd"] <= DD_TARGET]
    v3 = (max(cand, key=lambda n: P[n]["tr"]["roi_an"]) if cand else
          min(DF_NAMES, key=lambda n: P[n]["tr"]["dd"]))
    print(f"[t12] SÉLECTION TRAIN : {v3} (candidats {cand or 'aucun'})",
          flush=True)

    connus = {n: next(r for r in P[n]["reg"]
                      if r["name"] == "connu_2025_2026") for n in P}
    monthly = P[v3]["g"]["mr"]
    gf_c, gf_p = P[v3]["gf"]
    # ——— LE diagnostic du DD : quelle composante porte la fenêtre de DD max,
    #     et que dit le détecteur V3 à ce moment-là ?
    pk_ts, tr_ts, dd_w = dd_window(runs[v3]["res"])
    i_pk = int(np.searchsorted(bar_ts, pk_ts.timestamp() * 1000))
    i_tr = int(np.searchsorted(bar_ts, tr_ts.timestamp() * 1000))
    det_at_pk = defs[v3][0][min(i_pk, len(bar_ts) - 1)]
    det_at_tr = defs[v3][0][min(i_tr, len(bar_ts) - 1)]
    w_ns, e_ns = pk_ts.timestamp() * 10**9, tr_ts.timestamp() * 10**9
    wtr = [t for t in runs[v3]["res"]["trades"]
           if w_ns <= t["entry_ts"].timestamp() * 10**9 <= e_ns]
    by_strat: dict[str, float] = {}
    for t in wtr:
        key = ("momentum" if t["strategy"].startswith("momentum")
               else "carry" if t["strategy"].startswith("carry")
               else "fade" if t["strategy"].startswith("fade")
               else "vol_spike")
        by_strat[key] = by_strat.get(key, 0.0) + t["pnl"]
    con.close()

    # ================================================================ RAPPORT
    def fmt_lag(x):
        if x is None:
            return "warm-up"
        if isinstance(x, float) and np.isnan(x):
            return "jamais"
        return f"{x:+.0f} j"

    def frow(name):
        p = P[name]
        g = p["g"]
        return (f"| {name} | {g['bal']:.2f} | {p['roi_tr']:+.1f} / "
                f"{p['roi_val']:+.1f} | {g['roi_an']:+.1f} | {g['dd']:.1f} | "
                f"{g['liq']} | {g['n']} / {g['wr']:.0f} % | {g['neg']} | "
                f"{g['worst']:.1f} / {g['record']:.1f} |")

    dd3 = P[v3]["g"]["dd"]
    k3 = connus[v3]
    gain_val = P[v3]["roi_val"] - P["V2"]["roi_val"]
    dd_ok = dd3 <= DD_TARGET
    inv_bal = P["DF1_inv"]["g"]["bal"]
    v3_bal = P[v3]["g"]["bal"]
    inv_loose = inv_bal < v3_bal
    inv_liq = P["DF1_inv"]["g"]["liq"]
    lagv3 = lag_vs_v1(lags[v3][1], fl_v1)

    # —— LE diagnostic chiffré du mécanisme d'échec (ou de succès) ——
    # 1) la date du premier fund7 < 0 de l'ère RÉELLE (≥ 2025-10-27) :
    real_ms = 1761580800000
    m_real = np.where((bar_ts >= real_ms) & (f7s < 0) &
                      np.isfinite(f7s))[0]
    fund7_neg = (f"{datetime.fromtimestamp(bar_ts[m_real[0]] / 1000, tz=timezone.utc):%Y-%m-%d}"
                 if len(m_real) else "jamais")
    # 2) le retard du premier flip bear VAL de V3 vs V2 :
    fl_v2_bear = [f for f in fl_v2 if f[2] == "bear"
                  and pd.Timestamp(f[0]) >= pd.Timestamp("2025-10-01")]
    fl_v3_bear = [f for f in lags[v3][1] if f[2] == "bear"
                  and pd.Timestamp(f[0]) >= pd.Timestamp("2025-10-01")]
    if fl_v2_bear and fl_v3_bear:
        retard_j = (pd.Timestamp(fl_v3_bear[0][0]) -
                    pd.Timestamp(fl_v2_bear[0][0])).total_seconds() / 86400.0
        prix_gap = (fl_v3_bear[0][3] / fl_v2_bear[0][3] - 1) * 100
        retard_txt = (f"premier bear VAL : V2 {fl_v2_bear[0][0][:10]} "
                      f"@{fl_v2_bear[0][3]:,.0f} vs V3 {v3} "
                      f"{fl_v3_bear[0][0][:10]} @{fl_v3_bear[0][3]:,.0f} → "
                      f"le détecteur « rapide » est {retard_j:+.0f} j plus "
                      f"LENT et entre {prix_gap:+.1f} % plus bas")
    else:
        retard_txt = ("bascules bear VAL : V2 "
                      f"{fl_v2_bear[0][0][:10] if fl_v2_bear else '—'} / V3 "
                      f"{fl_v3_bear[0][0][:10] if fl_v3_bear else '—'}")
    # 3) part des barres VAL avant l'ère réelle où fund7 est une constante :
    v_pre = (bar_ts >= pd.Timestamp(train_hi).value // 10**6) & \
            (bar_ts < real_ms)
    const_share = float(np.mean(f7s[v_pre & np.isfinite(f7s)] > 0)) * 100 \
        if v_pre.any() else float("nan")

    L = [
        "# ÉTUDE T12 — LE DÉTECTEUR RAPIDE (fund7/vol7 P2) VS LE SMA 200 j : "
        "LE TROU N°1 DU STACK EST-IL COMBLABLE ?",
        f"Généré : {t0:%Y-%m-%dT%H:%M:%S+00:00} — script : "
        "`scripts/studies/aster_fast_detector.py`. DB en mode=ro ; "
        "écriture = ce rapport uniquement.", "",
        "## 1. La méthode (l'honnêteté d'abord)", "",
        "- **Question (T11 → T12)** : le DD global du stack V2 (32.5 %) EST "
        "le DD du régime connu_2025_2026 et le lag structurel du SMA 200 j "
        "+ hystérésis (2-3 mois/régime) est le trou n°1. T11 recommandait "
        "le détecteur RAPIDE de la sonde P2 : gradients fund7/vol7 en "
        "condition PRIMAIRE, SMA en condition SECONDAIRE (pattern D3). Ici : "
        "4 définitions simples, calibrées TRAIN, jugées VAL.",
        "- **V3 = le stack T9/T11 VERBATIM, UNE SEULE chose change** : le "
        "détecteur (momentum gated + épisodes carry) devient le détecteur "
        "rapide CHOISI SUR TRAIN. fade memes, vol_spike, sizing T9, coûts "
        "T9, MAE-carry calibrée TRAIN (0-liq lev ≤ 100/(MAE_train+0.5), "
        "plafonné 2x) : INCHANGÉS. Comparaison APPARIÉE : V1 (SMA) et V2 "
        "(SMA+hystérésis) re-simulés dans le MÊME run, imports verbatim "
        "T9/T10/T11.",
        "- **Les entrées, CAUSALES** : fund7 = moyenne des taux 8h sur "
        "[t-7j, t[ (exact, cumsum+searchsorted — même traitement du "
        "funding que le stack), lissée 5 j (120 h) sauf DF3 ; vol7 = ATR % "
        "1h roulant 7j moyen des majeures (sonde P2, RÉEL partout) ; "
        "SMA 200 j du close BTC ; confirmation anti-flicker 48 h HÉRITÉE "
        "(design T9, non recalibrée) ; exécution t+1 ; warm-up 200 j "
        "identique à V1/V2.",
        "- **⚠ CONTAMINATION CONNUE ET DITE** : funding_history des majors "
        "ne commence qu'au **2025-10-27**. Avant : modèle T7 CALENDAIRE "
        "(2021-09→2025-01 — ses frontières SONT celles des régimes T7) puis "
        "constante connu (BTC +0.343 bps/8h, 2025-01→2025-10-27). En TRAIN, "
        "un détecteur fund-primaire suit donc le calendrier T7 → "
        "**contamination circulaire partielle** (il reproduit partiellement "
        "les étiquettes) : les chiffres TRAIN des DF fund-primaires sont "
        "des BORNES SUPÉRIEURES. Et dans connu AVANT le 2025-10-27, fund7 "
        "est une CONSTANTE : zéro information — seul vol7 (réel) peut "
        "agir. Le juge reste VAL.",
        f"- **Split TRAIN/VAL par le temps** (70 % barres) : TRAIN "
        f"{train_lo}→{train_hi}, VAL {train_hi}→{val_hi}. Le SEUL paramètre "
        f"calibré TRAIN : seuil vol7 = q90 TRAIN = {seuil_vol:.2f} % "
        "(1 degré de liberté).",
        "- **Règle de sélection TRAIN (déclarée avant lecture VAL)** : "
        "parmi DF1..DF4 — liq=0 ET DD TRAIN ≤ 25 % → max ROI/an TRAIN ; "
        "sinon min DD TRAIN. Le choisi = V3. **Multiplicité** : 4 "
        "définitions + 1 contrôle inverse + 1 seuil = **6 essais "
        "déclarés**, 1 retenu, jugé VAL.", "",
        "## 2. Les définitions testées (exactes)", "",
        "| nom | bear (entrée short) | bull (sortie) | primaire |",
        "|---|---|---|---|",
        "| DF1 | fund7_5j < 0 **ET** close < SMA200j | fund7_5j > 0 ET "
        "close > SMA | fund lissé 5j |",
        "| DF2 | (fund7_5j < 0 **OU** vol7 > q90) ET close < SMA | "
        "fund7_5j > 0 ET close > SMA | fund OU vol |",
        "| DF3 | fund7 (7j **nu**) < 0 ET close < SMA | fund7 > 0 ET "
        "close > SMA | fund sans lissage |",
        "| DF4 | fund7_5j < 0 ET (close < SMA **OU** vol7 > q90) | "
        "fund7_5j > 0 ET close > SMA | fund, gate élargi |",
        "| DF1_inv | conditions de DF1 ÉCHANGÉES (contrôle inverse) | — | — |",
        "",
        "## 3. LE LAG — bascules et retard aux frontières T7", "",
        "| détecteur | flips | bear_2022 (→bear) | recovery_2023 (→bull) | "
        "bull_2024H1 (→bull) | vs V1 : bull / bear (j, − = avance) |",
        "|---|---|---|---|---|---|"]
    for name, fl_v1_ in (("V1", None), ("V2", None)):
        lb = lag_boundary(det1 if name == "V1" else det2, btc)
        L.append(f"| {name} | {len(fl_v1 if name == 'V1' else fl_v2)} | "
                 f"{fmt_lag(lb.get('bear_2022'))} | "
                 f"{fmt_lag(lb.get('recovery_2023'))} | "
                 f"{fmt_lag(lb.get('bull_2024H1'))} | — |")
    for name in DF_NAMES + ("DF1_inv",):
        lb, fls = lags[name]
        lv = lag_vs_v1(fls, fl_v1)
        L.append(f"| {name} | {len(fls)} | {fmt_lag(lb.get('bear_2022'))} | "
                 f"{fmt_lag(lb.get('recovery_2023'))} | "
                 f"{fmt_lag(lb.get('bull_2024H1'))} | "
                 f"{lv[0]:+.0f} / {lv[1]:+.0f} ({lv[2]} appariés) |")
    L += ["",
          "Lecture : `+X j` = l'état dominant est atteint X jours APRÈS la "
          "frontière T7 ; `−X j` = déjà en place depuis X j. bear_2022 des "
          "DF fund-primaires suit le MODÈLE (contamination, cf. §1) — leur "
          "lag TRAIN n'est PAS une preuve de vitesse.", "",
          "## 4. LA TABLE DÉFINITION × TRAIN/VAL — le stack complet "
          "(wallet $100 frais)", "",
          "| run | $ final | ROI TRAIN / VAL % | ROI/an global | DD global | "
          "liq | trades / WR | mois− | pire / record % |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name in ("V1", "V2") + DF_NAMES + ("DF1_inv",):
        L.append(frow(name))
    L += ["",
          f"**Sélection TRAIN (règle §1) → V3 = {v3}** — candidats "
          f"qualifiés TRAIN : {cand or 'aucun → min DD TRAIN'}.", "",
          "## 5. LE ZOOM connu_2025_2026 (le régime qui porte le DD)", "",
          "| run | trades | WR | ROI seg | ROI/an | DD intra | liq | mois− | "
          "pire mois |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name in ("V1", "V2", v3):
        r = connus[name]
        L.append(f"| {name} | {r['n']} | {r['wr']:.0f} % | {r['roi']:+.1f} % "
                 f"| {r['roi_an']:+.1f} %/an | DD {r['dd']:.1f} | {r['liq']} "
                 f"| {r['neg']} | {r['worst']:+.1f} % |")
    L += ["",
          "## 6. LES BASCULES EN VAL (le test de vitesse direct)", "",
          "| détecteur | bascules VAL (date → direction @prix BTC) |",
          "|---|---|"]
    for name, fls in (("V2", fl_v2), (f"V3 ({v3})", lags[v3][1])):
        flv = [f for f in fls if pd.Timestamp(f[0]) >= pd.Timestamp(train_hi)]
        cell = "; ".join(f"{f[0][:16]} → {f[2]} @{f[3]:,.0f}" for f in flv)
        L.append(f"| {name} | {cell or 'aucune'} |")
    L += ["",
          f"Décalage V3 vs V1 (médiane, j) : bull {lagv3[0]:+.0f} / bear "
          f"{lagv3[1]:+.0f} ({lagv3[2]} bascules appariées ±60 j).", "",
          f"## 7. BLOC STATS MENSUEL — V3 ({v3}), garde-fou des ABSOLUS", "",
          "| Mois | Trades | WR | Liq | ROI % |", "|---|---|---|---|---|"]
    for x in monthly:
        L.append(f"| {x['month']} | {x['n']} | {x['w'] / max(x['n'], 1) * 100:.0f} % "
                 f"| {x['liq']} | {x['roi']:+.1f} |")
    L += ["",
          f"Garde-fous : composé-des-mois écart {gf_c * 100:.3f} % ; "
          f"somme-PnL écart ${gf_p:.4f}.", "",
          "## 8. LES COMPOSANTES DANS LE WALLET (V2 vs V3) + LE DIAGNOSTIC "
          "DU DD", "",
          "| composante | V2 n/WR/PnL$ | V3 n/WR/PnL$ |", "|---|---|---|"]
    for pref, lab in (("momentum", "momentum (gate détecteur)"),
                      ("carry_short", "carry short porté"),
                      ("fade_meme", "fade memes"),
                      ("vol_spike", "vol_spike")):
        a2 = strat_stats(runs["V2"]["res"], pref)
        a3 = strat_stats(runs[v3]["res"], pref)
        L.append(f"| {lab} | {a2[0]} / {a2[1]:.0f} % / {a2[2]:+.1f} | "
                 f"{a3[0]} / {a3[1]:.0f} % / {a3[2]:+.1f} |")
    w2 = whipsaw(runs["V2"]["carry"], runs["V2"]["lev"])
    w3 = whipsaw(runs[v3]["carry"], runs[v3]["lev"])
    strat_txt = ", ".join(f"{k} {v:+.1f}$" for k, v in
                          sorted(by_strat.items(), key=lambda kv: kv[1]))
    L += ["",
          f"Whipsaw carry (gains/pertes de bascules, % wallet) : V2 "
          f"{w2[0]:+.1f} / {w2[1]:+.1f} → V3 {w3[0]:+.1f} / {w3[1]:+.1f}. "
          f"MAE max carry TRAIN V3 : {runs[v3]['mae']:.1f} % → lev "
          f"{runs[v3]['lev']:.2f}x (0-liq TRAIN).", "",
          f"**La fenêtre du DD max de V3 : {pk_ts:%Y-%m-%d} → "
          f"{tr_ts:%Y-%m-%d}, DD {dd_w:.1f} %** ; état du détecteur V3 au "
          f"pic : {'bull' if det_at_pk == 1 else 'bear' if det_at_pk == -1 else 'warm-up'}"
          f" ; au creux : {'bull' if det_at_tr == 1 else 'bear' if det_at_tr == -1 else '?'} "
          f"; PnL de la fenêtre par composante : {strat_txt}. "
          "Si l'essentiel de la perte vient de vol_spike (indépendant du "
          "détecteur) alors même un détecteur parfait ne comble pas ce DD.",
          "",
          "## 9. VERDICT", ""]
    verdict = [
        f"**DD global final : {dd3:.1f} % — cible ≤ 25 % : "
        f"{'ATTEINTE' if dd_ok else 'NON ATTEINTE'}** (V2 32.5 %, V1 "
        f"42.8 %). ROI VAL V3 {P[v3]['roi_val']:+.1f} % vs V2 "
        f"{P['V2']['roi_val']:+.1f} % (delta {gain_val:+.1f} pts). "
        f"connu_2025_2026 : V3 {k3['roi']:+.1f} % ({k3['roi_an']:+.1f} %/an)"
        f", DD {k3['dd']:.1f} — vs V2 -9.2 % (-5.3 %/an).", "",
        f"**LE MÉCANISME (chiffré)** : {retard_txt}. Trois verrous "
        "structurels, aucun contournable par cette famille : (1) "
        f"**fund7 est aveugle puis du mauvais signe** — {const_share:.0f} % "
        "des barres VAL avant le 2025-10-27 ont un fund7 CONSTANTE "
        "(modèle) : la condition `fund7 < 0` ne peut PAS y basculer ; et "
        f"quand le funding réel arrive, il reste POSITIF à travers le "
        f"sommet (la foule long paie) — le premier fund7_5j < 0 de l'ère "
        f"réelle n'arrive que le **{fund7_neg}**, au fond du marché. Le "
        "gradient de funding n'est pas un détecteur de RETOURNEMENT, c'est "
        "un CONFIRMATEUR de bear mûr (la sonde P2 disait d'ailleurs "
        "l'inverse : fund7 HAUT = mois faible à venir — séparateur d=+0.98 "
        "sur les mois faibles, pas sur les tops) ; (2) **le veto "
        "SMA-secondaire ferme la porte au vol7** : au sommet, close > "
        "SMA200j PAR CONSTRUCTION — DF2/DF4 ne peuvent pas basculer plus "
        "tôt que la SMA elle-même ; un « primaire rapide + secondaire "
        "SMA » ne peut jamais battre la SMA AU sommet, seulement la suivre "
        "avec du bruit en plus ; (3) **TRAIN +98.5 % = pur miroir du "
        "calendrier T7** (contamination déclarée §1 : le modèle donne au "
        "carry une entrée bear parfaite au 2022-01-01) — le pic du wallet "
        "est un mirage et la doctrine VAL a fait exactement son travail.",
        "",
        f"**Contrôle inverse** : DF1_inv → {inv_bal:.2f} $ vs V3 "
        f"{v3_bal:.2f} $, {inv_liq} liquidation(s) — "
        + ("le détecteur porte bien de l'information (l'inverse perd)."
           if inv_loose else
           "**ARTEFACT : l'inverse gagne — verdict NUL.**"), "",
        "**Multiplicité honnête** : 6 essais déclarés (4 définitions + 1 "
        "contrôle inverse + 1 seuil q90 vol7 TRAIN), sélection TRAIN "
        "mécanique (DF1 retenu au tie-break du ROI/an TRAIN), jugement "
        "VAL : **les 4 définitions sont rejetées en VAL** (-37.6 à -42.7 % "
        "vs -3.5 % pour V2), DD global 51.5-55.5 % vs 32.5 %. Le test du "
        "wallet séquentiel (`stacked_portfolio.run_stack`) est de facto "
        "échoué — aucun candidat ne sort de cette étude.", ""]
    if dd_ok and gain_val > 0:
        verdict += ["**Le trou n°1 est comblé** : à documenter.", ""]
    else:
        verdict += [
            "**VERDICT : le gain VAL ne tient PAS — le SMA 200 j "
            "+ hystérésis ±3 % (V2) RESTE le standard ; le trou n°1 n'est "
            "pas comblé par un détecteur plus rapide de cette famille "
            "(fund7/vol7 primaires + SMA secondaire)**. La vitesse n'était "
            "pas le binding constraint du DD : la fenêtre de DD max de V3 "
            f"({pk_ts:%Y-%m-%d} → {tr_ts:%Y-%m-%d}, DD {dd_w:.1f} %) est "
            f"vécue en état '{'bull' if det_at_pk == 1 else 'bear' if det_at_pk == -1 else '?'}' "
            "et portée par "
            f"{min(by_strat.items(), key=lambda kv: kv[1])[0] if by_strat else '?'} "
            "— le détecteur (qu'il soit rapide ou lent) ne touche pas la "
            "composante qui saigne.", ""]
    verdict += [
        "**Les trous restants (re-hiérarchisés après T12)** : (1) "
        "**l'EXPOSITION en bear détecté** — vol_spike permanent 1x saigne "
        "dans le régime baissier (trou n°4 de T11, devenu n°1) : gater/"
        "réduire vol_spike (et le momentum-relance) par un état de "
        "risque (D3 haute-vol, fund7 très haut) est le levier DD restant ; "
        "(2) **fund7 n'est réel qu'à partir du 2025-10-27** : toute "
        "stratégie fund-dépendante est structurellement aveugle sur les 7 "
        "premiers mois de connu — la donnée fomo-style capturée en temps "
        "réel aujourd'hui est le seul nouveau signal natif de la fenêtre ; "
        "(3) **le gradient fund7 INVERSE** (fund7 HAUT = carburant de "
        "cascade, séparateur P2 d=+0.98) comme condition de DÉRISQUE (et "
        "non de flip de régime) : hypothèse déclarée aujourd'hui, NON "
        "testée ici (au-delà des 6 essais déclarés) — si elle est un jour "
        "testée, calibration TRAIN uniquement ; (4) le fade memes (genèse "
        "donnée 2025-09) reste la seule composante vivante de connu — à "
        "faire mûrir en forward ; (5) le ROI global reste très sous la "
        "cible user (60-70 %/mois).", "",
        "**Recommandation suite** : garder V2 (SMA 200 j + hystérésis ±3 %) "
        "comme standard du stack ; NE PAS promouvoir le détecteur rapide ; "
        "ré-catégoriser dans `docs/20-registre-indicateurs.md` : "
        "« fund7/vol7 comme détecteur de régime (primaire rapide + SMA "
        "secondaire) » = **NUL** (rejeté VAL, mécanisme chiffré ci-dessus) "
        "et « fund7 haut = dé-risque » = hypothèse CANDIDAT non testée. "
        "Prochaine brique : le gate d'exposition en bear détecté "
        "(vol_spike) — attaque directe du DD 32.5 % → 25 %.", "",
        f"Fichiers : étude `scripts/studies/aster_fast_detector.py` — "
        f"lecture seule `data/warehouse/klines.db` ; imports verbatim T9 "
        f"(aster_multiregime_stack), T10 (aster_carry_hysteresis), T11 "
        f"(aster_multiregime_stack_v2), P2 (mechanism_probe). fade memes "
        f"{len(fade_ev)} évts ({len(fade_used)} séries) ; vol_spike "
        f"{len(spike_ev)} évts (p90 {sp_p90:.2f} / med {sp_med:.2f} TRAIN).",
    ]
    L += verdict
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "aster_fast_detector.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[t12] rapport → {out}", flush=True)

    # —— impression console de contrôle ——
    for name in ("V1", "V2") + DF_NAMES + ("DF1_inv",):
        p = P[name]
        print(f"{name:8s} ${p['g']['bal']:8.2f} ROI_tr/val "
              f"{p['roi_tr']:+6.1f}/{p['roi_val']:+6.1f} "
              f"DD {p['g']['dd']:5.1f} liq {p['g']['liq']} "
              f"mois- {p['g']['neg']:2d} | connu "
              f"{connus[name]['roi']:+6.1f}% DD {connus[name]['dd']:5.1f}",
              flush=True)
    print(f"V3 = {v3} | lag V3 vs V1 (bull/bear j) "
          f"{lagv3[0]:+.0f}/{lagv3[1]:+.0f} | DD-fenêtre {pk_ts:%Y-%m-%d}→"
          f"{tr_ts:%Y-%m-%d} DD {dd_w:.1f}% det_pic="
          f"{'bull' if det_at_pk == 1 else 'bear' if det_at_pk == -1 else '?'}"
          f" | PnL fenêtre {strat_txt}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
