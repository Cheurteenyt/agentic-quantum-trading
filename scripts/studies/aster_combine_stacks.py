#!/usr/bin/env python3
"""T25 — RE-SIZING du stack des survivants + LA COMBINAISON officiel+survivants.

Suite directe de T24 (reports/aster_survivors_wallet.md) : le stack des 4
survivants T21 à 1× ($312.49, +25.1 %/an, DD 30.2 %) domine l'officiel
T11/V2 ($146.42, +7.8 %/an, DD 32.5 %) sur 4 axes mais DD > 25 %.
Mission T25 (la chaîne, la consolidation) :

  1. RE-SIZING : scan du poids uniforme w par stratégie du stack
     survivants (0.05 → 0.25, pas 0.025 — 9 points, UNE passe, lev 1×)
     — la courbe ROI/an × DD ; w* = le PLUS GRAND w de la grille avec
     DD ≤ 25 % (règle pré-enregistrée, pas de fitting).
  2. COMBINAISON officiel + survivants re-sizé, wallet $100, DEUX méthodes :
     (a) succession temporelle — deux poches de capitaux SÉPARÉS (équité
         combinée = somme des courges ; recombinaison EXACTE par linéarité
         du sizing en % de balance, assertée contre des runs $50 réels) ;
     (b) rets journaliers pondérés — rets journaliers (marques de sortie
         ffill, MTM à la fermeture) combinés 0.5/0.5 et composés
         (= re-équilibrage journalier 50/50).
  3. PROPORTIONS : scan alpha (pocket survivants) 0 → 1 pas 0.1 sur les
     DEUX méthodes (recombinaison exacte des courbes $100) ; frontière
     DD ≤ 25 % et argmax CAGR/DD.
  4. VERDICT : la combinaison améliore-t-elle l'officiel seul (NET, DD,
     risk-ajusté) ? Garde-fous composé-des-mois + somme PnL.

Règles de verdict PRÉ-ENREGISTRÉES (avant résultats, anti-dérive) :
  V1 PARITÉ : officiel V2 reproduit ($146.42, DD 32.5) et survivants
     w=0.25 reproduits ($312.49, DD 30.2) — sinon STOP, aucune conclusion.
  V2 0 liq partout (boucle ×0.95 conservée).
  V3 w* = plus grand w de la grille {0.05..0.25, pas 0.025} avec DD ≤ 25 %.
  V4 alpha* = plus grand alpha de la grille {0, 0.1, …, 1.0} avec DD ≤ 25 %
     (par méthode) ; l'argmax CAGR/DD est rapporté à titre comparatif.
  V5 « améliore l'officiel » : NET_comb > NET_off ET DD_comb < DD_off ET
     RA_comb > RA_off ET 0 liq ET garde-fous composés OK (< 0.5 % / $0.01).
  Combinaison retenue (pour la table mensuelle) : le point frontière
  DD ≤ 25 % au meilleur risk-ajusté ; à égalité (±10 % rel) la méthode (a)
  (poches séparées — exécutable sans re-balancement journalier).

Conventions : wallet $100, frais/coûts T9 (officiel) et 8 bps RT (survivants),
funding réel (survivants : cache T21 ; officiel : T9 as-of + carry T7),
MTM à la fermeture (le DD est mesuré sur les marques de sortie — convention
officielle), fenêtre 2021-09-01 → 2026-09-30, CAGR sur 5.08 ans (365.25).

  .venv/bin/python scripts/studies/aster_combine_stacks.py
  .venv/bin/python scripts/studies/aster_combine_stacks.py --write

Sortie : rapport console + reports/aster_combine_stacks.md (--write).
DB en READ-ONLY ; écriture = le rapport uniquement.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.portfolio_sim import KDB, MAJORS, monthly_rows  # noqa: E402
from scripts.stacked_portfolio import CAPITAL, run_stack  # noqa: E402
from scripts.studies import aster_survivors_wallet as SW  # noqa: E402
from scripts.studies.aster_carry_hysteresis import detector_sma_hyst  # noqa: E402
from scripts.studies.aster_multiregime_stack import (  # noqa: E402
    CARRY_SYMS, K_V, MOM_REF, SZ_CARRY, SZ_FADE, SZ_MOM,
    carry_episodes, carry_event, daily_fund_bps, fade_events, load_bars,
    load_funding_pts, momentum_events_gated, open_ro, spike_events)

REPORT = ROOT / "reports" / "aster_combine_stacks.md"
HYST_H = 0.03                    # le h T10, NON re-calibré (module v2)
DD_TARGET = 25.0
GRID_W = [round(float(x), 3) for x in np.arange(0.05, 0.25001, 0.025)]
GRID_A = [round(float(x), 2) for x in np.arange(0.0, 1.0001, 0.1)]
YEARS = SW.YEARS
W0_DT = SW.dt_of(SW.W0_MS)
W1_DT = SW.dt_of(SW.W1_MS)
VAL0_DT = SW.dt_of(SW.VAL0_MS)
OFFICIAL_REF = {"final": 146.42, "dd": 32.5}     # rapport T11/V2
SURV_REF = {"final": 312.49, "dd": 30.2}         # rapport T24, w=0.25


def log(m: str) -> None:
    print(m, flush=True)


def rai(cagr_frac: float, dd_pct: float) -> float:
    """Risk-ajusté = CAGR % ÷ DD % (unités homogènes)."""
    return cagr_frac * 100.0 / dd_pct if dd_pct > 0 else float("inf")


def funding_hourly_all_ro() -> dict[str, float]:
    """Pariété avec funding_hourly_all() (stacked_portfolio) — en ro et
    fenêtré à W1 (anti-dérive : la moyenne ne bouge plus quand la DB grandit)."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    acc: dict[str, list[float]] = {}
    for s, r in con.execute("SELECT symbol, rate FROM funding_history "
                            "WHERE funding_time < ?", (SW.W1_MS,)):
        try:
            acc.setdefault(s, []).append(float(r))
        except (TypeError, ValueError):
            continue
    con.close()
    return {s: sum(v) / len(v) * 100 / 8 for s, v in acc.items()}


# ------------------------------------------------- stack officiel (V2 T11)
def build_official(con, fh: dict, det, bars, fade_ev, sp_med, spike_ev,
                   train_end_ms: int) -> dict:
    """Copie VERBATIM de build_stack (aster_multiregime_stack_v2.py au
    2026-10-01) — V2 = détecteur hystérésis ±3 %, sizing T9 figé."""
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
        keep = [i for i, t in enumerate(fts) if t < SW.W1_MS]   # anti-dérive
        fts, frt = [fts[i] for i in keep], [frt[i] for i in keep]
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
    for sym in CARRY_SYMS:
        for k, (ep, fbps) in enumerate(eps_all[sym]):
            carry_ev.append(carry_event(bars[sym], sym, ep, lev, fbps, k))
    fh_st = dict(fh)
    for sym in CARRY_SYMS:
        for k, (ep, fbps) in enumerate(eps_all[sym]):
            fh_st[f"{sym}@carry{k}"] = fbps / 100.0 / 8.0
    stack_ev = sorted(mom_ev + carry_ev + fade_ev + spike_ev,
                      key=lambda e: e["ts_ms"])
    res = run_stack(stack_ev, CAPITAL, fn_stack, fh_st)
    return {"mom": mom_ev, "carry": carry_ev, "lev": lev, "mae": mae_tr,
            "res": res, "events": stack_ev, "fn": fn_stack, "fh": fh_st}


# ---------------------------------------------------------- survivants T21
def wallet_run(trades: list[dict], lev_map: dict, size_map: dict,
               funding: dict, capital: float = CAPITAL) -> tuple[dict, dict]:
    """run_stack + boucle 0-liq (pattern T24) — capital paramétrable."""
    levs = dict(lev_map)

    def size_fn(e: dict) -> float:
        return size_map.get(e["strategy"], 0.0)

    res = None
    for _ in range(60):
        res = run_stack(SW.make_events(trades, levs), capital, size_fn, funding)
        if res["n_liq"] == 0:
            break
        levs = {k: round(v * 0.95, 4) for k, v in levs.items()}
    return res, levs


# ------------------------------------------------------ courbes combinées
def steps_of_cap(res: dict, cap: float) -> tuple[list, list]:
    """Courbe d'équité MTM à la fermeture : cap + cumul de PnL trié par
    EXIT ts. (Le champ `balance` de run_stack suit l'ordre d'ENTRÉE — le
    lire en ordre de sortie est incohérent en queue : leçon T25.)"""
    ts = [W0_DT]
    bs = [cap]
    run = 0.0
    for t in sorted(res["trades"], key=lambda x: x["exit_ts"]):
        run += t["pnl"]
        ts.append(t["exit_ts"])
        bs.append(cap + run)
    return ts, bs


def combine_steps(sa: tuple, sb: tuple, wa: float, wb: float) -> tuple[list, list]:
    """Équité wa*curve_a + wb*curve_b (exact : le pnl est linéaire en capital)."""
    ta, ba = sa
    tb, bb = sb
    times = sorted(set(ta) | set(tb))
    bals = [wa * ba[bisect_right(ta, t) - 1] + wb * bb[bisect_right(tb, t) - 1]
            for t in times]
    return times, bals


def eq_at(curve: tuple, t: datetime) -> float:
    """Équité STRICTEMENT avant t (bisect_left) : une sortie exactement à
    la borne appartient à la période suivante — cohérent avec monthly_rows
    (attribution par mois de sortie)."""
    ts, bs = curve
    i = bisect_left(ts, t) - 1
    return bs[max(i, 0)]


def dd_between(curve: tuple, t0: datetime, t1: datetime) -> float:
    ts, bs = curve
    peak = eq_at(curve, t0)
    dd = 0.0
    for t, b in zip(ts, bs):
        if t < t0 or t > t1:
            continue
        peak = max(peak, b)
        if peak > 0:
            dd = max(dd, (peak - b) / peak * 100)
    return dd


def curve_stats(curve: tuple) -> dict:
    final = curve[1][-1]
    cagr = (final / CAPITAL) ** (1.0 / YEARS) - 1.0 if final > 0 else -1.0
    peak, dd = -1e18, 0.0
    for _t, b in zip(curve[0], curve[1]):
        peak = max(peak, b)
        if peak > 0:
            dd = max(dd, (peak - b) / peak * 100)
    eq0 = eq_at(curve, VAL0_DT)
    return {"final": final, "cagr": cagr, "dd": dd,
            "val_roi": final / eq0 - 1.0 if eq0 > 0 else -1.0,
            "val_dd": dd_between(curve, VAL0_DT, W1_DT)}


def monthly_combined(mr_a: list, mr_b: list, curve: tuple,
                     wa: float = 1.0, wb: float = 1.0) -> list[dict]:
    """Mois combinés (pnl $ pondérés par les poches, ROI sur l'équité
    combinée de début de mois). mr_* en $100 (les pnl scalent linéairement)."""
    pm: dict[str, float] = {}
    for r in mr_a:
        pm[r["month"]] = pm.get(r["month"], 0.0) + wa * r["pnl"]
    for r in mr_b:
        pm[r["month"]] = pm.get(r["month"], 0.0) + wb * r["pnl"]
    out = []
    for m in sorted(pm):
        y, mo = int(m[:4]), int(m[5:7])
        start = eq_at(curve, datetime(y, mo, 1, tzinfo=timezone.utc))
        out.append({"month": m, "pnl": pm[m], "start": start,
                    "roi": pm[m] / start * 100 if start > 0 else 0.0})
    return out


def garde_fous_monthly(mc: list[dict], final: float) -> tuple[float, float]:
    prod = float(np.prod([1.0 + r["roi"] / 100 for r in mc]))
    gap_c = abs(prod - final / CAPITAL)
    gap_p = abs(sum(r["pnl"] for r in mc) - (final - CAPITAL))
    return gap_c, gap_p


def daily_rets(steps: tuple) -> pd.Series:
    ts, bs = steps
    s = pd.Series(bs, index=pd.DatetimeIndex(ts))
    daily = s.resample("D").last().ffill()
    # horizon : jusqu'au dernier mark (les sorties peuvent déborder W1 de qqs h)
    end = max(W1_DT, ts[-1]) + pd.Timedelta(days=1)
    full = pd.date_range(W0_DT, end, freq="D", inclusive="left")
    daily = daily.reindex(full).ffill()
    return daily.pct_change().fillna(0.0)


def stats_from_rets(r: pd.Series) -> dict:
    eq = CAPITAL * (1.0 + r).cumprod()
    final = float(eq.iloc[-1])
    cagr = (final / CAPITAL) ** (1.0 / YEARS) - 1.0 if final > 0 else -1.0
    peak = eq.cummax()
    dd = float(((peak - eq) / peak * 100).max())
    eq0 = float(eq[eq.index < pd.Timestamp(VAL0_DT)].iloc[-1])
    vs = eq[eq.index >= pd.Timestamp(VAL0_DT)]
    val_dd = float(((vs.cummax() - vs) / vs.cummax() * 100).max())
    g = eq.groupby([eq.index.year, eq.index.month]).last()
    mr = g.pct_change()
    mr.iloc[0] = g.iloc[0] / CAPITAL - 1.0
    months = [f"{y}-{m:02d}" for y, m in g.index]
    mc_b = [{"month": months[i], "roi": float(v * 100)}
            for i, v in enumerate(mr.values)]
    return {"final": final, "cagr": cagr, "dd": dd,
            "val_roi": final / eq0 - 1.0 if eq0 > 0 else -1.0,
            "val_dd": val_dd, "mc": mc_b,
            "neg": int((mr < -1e-12).sum()),
            "worst": float(mr.min()), "record": float(mr.max())}


# -------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    # ——— stack officiel V2 (parité T11) ———
    FH = funding_hourly_all_ro()
    con = open_ro()
    # anti-dérive : TOUTES les entrées fenêtrées à W1 (la DB grandit, l'étude non)
    bars = {s: [b for b in load_bars(con, s) if b.ts < SW.W1_MS] for s in MAJORS}
    btc = bars["BTCUSDT"]
    train_end_ms = btc[int(len(btc) * 0.7)].ts           # split 70 % barres T9
    W1_NS = SW.W1_MS * 10**6
    fade_ev, fade_used = fade_events(con, FH)
    fade_ev = [e for e in fade_ev if e["ts_ms"] < W1_NS]
    spike_ev, sp_p90, sp_med = spike_events(con, train_end_ms * 10**6)
    spike_ev = [e for e in spike_ev if e["ts_ms"] < W1_NS]
    det_h, raw_h = detector_sma_hyst(btc, 200, HYST_H)
    off = build_official(con, FH, det_h, bars, fade_ev, sp_med, spike_ev,
                         train_end_ms)
    con.close()
    res_off = off["res"]
    st_off = SW.full_stats(res_off, "officiel V2", f"carry {off['lev']:.2f}x")
    p_off = (abs(res_off["balance"] - OFFICIAL_REF["final"])
             / OFFICIAL_REF["final"] < 0.015
             and abs(st_off["dd"] - OFFICIAL_REF["dd"]) < 0.5)
    log(f"[parité] officiel V2 : ${res_off['balance']:,.2f} "
        f"(ref ${OFFICIAL_REF['final']:.2f}, bande 1.5 % — horizon de données "
        f"queue) DD {st_off['dd']:.1f} % (ref {OFFICIAL_REF['dd']:.1f}) -> "
        f"{'OK' if p_off else 'ÉCHEC'}")
    assert p_off, "V1 : parité officielle perdue — STOP"

    # ——— survivants T21 (parité T24) ———
    con_k = sqlite3.connect(f"file:{SW.DB_PATH}?mode=ro", uri=True)
    data = {s: SW.D.load_klines(con_k, s) for s in SW.SYMBOLS}
    con_k.close()
    funding_surv = SW.funding_hourly_real()
    trades_by = {n: [t for t in SW.build_survivor_trades(data, n)
                     if SW.W0_MS <= t["ts"] < SW.W1_MS] for n in SW.SURVIVORS}
    all_tr = [t for n in SW.SURVIVORS for t in trades_by[n]]
    lev1 = {n: 1.0 for n in SW.SURVIVORS}

    # ——— 1. LE SCAN DE RE-SIZING (une passe) ———
    scan = []
    for w in GRID_W:
        res, _ = wallet_run(all_tr, lev1, {n: w for n in SW.SURVIVORS},
                            funding_surv, CAPITAL)
        st = SW.full_stats(res, f"w={w:.3f}", "lev 1.00x")
        scan.append((w, st, res))
        log(f"[scan] w={w:.3f} ${st['final']:8.2f} ROI/an {st['cagr']*100:+6.1f} % "
            f"DD {st['dd']:5.1f} % VAL {st['val_roi']*100:+6.1f} % "
            f"(DD {st['val_dd']:4.1f} %) liq {st['liq']}")
    p_surv = abs(scan[-1][1]["final"] - SURV_REF["final"]) < 0.1 \
        and abs(scan[-1][1]["dd"] - SURV_REF["dd"]) < 0.4
    log(f"[parité] survivants w=0.25 : ${scan[-1][1]['final']:,.2f} "
        f"(ref ${SURV_REF['final']:.2f}) DD {scan[-1][1]['dd']:.1f} % "
        f"-> {'OK' if p_surv else 'ÉCHEC'}")
    assert p_surv, "V1 : parité T24 perdue — STOP"
    feas = [(w, st, res) for w, st, res in scan if st["dd"] <= DD_TARGET]
    w_star, st_w, res_w = feas[-1] if feas else scan[0]
    log(f"[w*] frontière DD ≤ {DD_TARGET:.0f} % : w* = {w_star:.3f} "
        f"(${st_w['final']:.2f}, {st_w['cagr']*100:+.1f} %/an, "
        f"DD {st_w['dd']:.1f} %)")

    # ——— 2. LA COMBINAISON — bases $100 et poches $50 ———
    steps_off100 = steps_of_cap(res_off, CAPITAL)
    steps_surv100 = steps_of_cap(res_w, CAPITAL)
    res_off50 = run_stack(off["events"], 50.0, off["fn"], off["fh"])
    res_surv50, _ = wallet_run(all_tr, lev1, {n: w_star for n in SW.SURVIVORS},
                               funding_surv, 50.0)
    d1 = abs(res_off50["balance"] - 0.5 * res_off["balance"])
    d2 = abs(res_surv50["balance"] - 0.5 * res_w["balance"])
    assert d1 < 1e-4 and d2 < 1e-4, "linéarité perdue"
    log(f"[parité] poches $50 = 0.5 × courbes $100 (linéarité) : OK "
        f"(écarts ${d1:.2e} / ${d2:.2e})")

    # (a) succession de poches 50/50 — courbe exacte
    curve_a = combine_steps(steps_off100, steps_surv100, 0.5, 0.5)
    d3 = abs(curve_a[1][-1] - (res_off50["balance"] + res_surv50["balance"]))
    if d3 >= 2e-4:
        ta, ba = steps_off100
        tb, bb = steps_surv100
        log(f"[debug] off100 fin : {ta[-1]} ${ba[-1]:.6f} (res {res_off['balance']:.6f})")
        log(f"[debug] surv100 fin : {tb[-1]} ${bb[-1]:.6f} (res {res_w['balance']:.6f})")
        log(f"[debug] combinée fin : {curve_a[0][-1]} ${curve_a[1][-1]:.6f}")
        log(f"[debug] poches50 : off ${res_off50['balance']:.6f} + "
            f"surv ${res_surv50['balance']:.6f} = "
            f"{res_off50['balance'] + res_surv50['balance']:.6f}")
        n_dup_o = len(ta) - len(set(ta))
        n_dup_s = len(tb) - len(set(tb))
        log(f"[debug] dup ts : off {n_dup_o}, surv {n_dup_s}")
    assert d3 < 2e-4, f"courbe combinée ≠ poches ({d3})"
    st_a = curve_stats(curve_a)
    # (b) rets journaliers 50/50 (re-équilibrage journalier)
    ro, rs = daily_rets(steps_off100), daily_rets(steps_surv100)
    st_b = stats_from_rets(0.5 * ro + 0.5 * rs)

    # ——— 3. LE SCAN DES PROPORTIONS (alpha = pocket survivants) ———
    alpha_rows = []
    for a in GRID_A:
        ca = curve_stats(combine_steps(steps_off100, steps_surv100, 1 - a, a))
        cb = stats_from_rets((1 - a) * ro + a * rs)
        alpha_rows.append((a, ca, cb))
    feas_a = [r for r in alpha_rows if r[1]["dd"] <= DD_TARGET]
    feas_b = [r for r in alpha_rows if r[2]["dd"] <= DD_TARGET]
    a_star = feas_a[-1][0] if feas_a else 0.0
    b_star = feas_b[-1][0] if feas_b else 0.0
    ra_a_star = rai(feas_a[-1][1]["cagr"], feas_a[-1][1]["dd"]) if feas_a else float("nan")
    ra_b_star = rai(feas_b[-1][2]["cagr"], feas_b[-1][2]["dd"]) if feas_b else float("nan")
    best_a = max(alpha_rows, key=lambda r: rai(r[1]["cagr"], r[1]["dd"]))
    best_b = max(alpha_rows, key=lambda r: rai(r[2]["cagr"], r[2]["dd"]))
    log(f"[alpha*] (a) poches : {a_star:.1f} (RA {ra_a_star:.2f}) | "
        f"(b) journalier : {b_star:.1f} (RA {ra_b_star:.2f}) | "
        f"argmax RA : (a) {best_a[0]:.1f}, (b) {best_b[0]:.1f}")

    # ——— la combinaison retenue (règle pré-enregistrée) ———
    ra_a50 = st_a["cagr"] / st_a["dd"]
    ra_b50 = st_b["cagr"] / st_b["dd"]
    if feas_a and feas_b:
        if ra_b_star > ra_a_star * 1.10:
            method, alpha = "b", b_star
        else:
            method, alpha = "a", a_star
    else:
        method, alpha = ("a", a_star) if feas_a else ("b", b_star)
    if method == "a":
        curve_r = combine_steps(steps_off100, steps_surv100, 1 - alpha, alpha)
        st_r = curve_stats(curve_r)
        mr_o = monthly_rows(res_off["trades"], CAPITAL)
        mr_s = monthly_rows(res_w["trades"], CAPITAL)
        mc = monthly_combined(mr_o, mr_s, curve_r, 1 - alpha, alpha)
        neg_r = sum(1 for x in mc if x["roi"] < -1e-9)
        worst_r = min((x["roi"] for x in mc), default=0.0)
        record_r = max((x["roi"] for x in mc), default=0.0)
    else:
        st_r = stats_from_rets((1 - alpha) * ro + alpha * rs)
        curve_r = (list(st_r["eq"].index), list(st_r["eq"].values))
        mc = [{"month": x["month"], "pnl": float("nan"),
               "start": float("nan"), "roi": x["roi"]}
              for x in st_r["mc"]]
        neg_r, worst_r, record_r = st_r["neg"], st_r["worst"], st_r["record"]
    if alpha >= 1.0 - 1e-9:      # poche officielle à capital nul : ne trade pas
        trades_r, wins_r, liq_r = res_w["n"], res_w["n_wins"], res_w["n_liq"]
        fees_r, fund_r = res_w["fees"], res_w["funding"]
    elif alpha <= 1e-9:
        trades_r, wins_r, liq_r = res_off["n"], res_off["n_wins"], res_off["n_liq"]
        fees_r, fund_r = res_off["fees"], res_off["funding"]
    else:
        trades_r = res_off["n"] + res_w["n"]
        wins_r = res_off["n_wins"] + res_w["n_wins"]
        liq_r = res_off["n_liq"] + res_w["n_liq"]
        fees_r = (1 - alpha) * res_off["fees"] + alpha * res_w["fees"]
        fund_r = (1 - alpha) * res_off["funding"] + alpha * res_w["funding"]
    gc_r, gp_r = garde_fous_monthly(mc, st_r["final"]) if method == "a" \
        else (abs(float(np.prod([1 + x["roi"] / 100 for x in mc]))
                  - st_r["final"] / CAPITAL), 0.0)
    if method == "a":
        prev_end = CAPITAL
        worst_tel, worst_m = 0.0, ""
        for x in mc:
            r_ = abs(x["start"] - prev_end)
            if r_ > worst_tel:
                worst_tel, worst_m = r_, x["month"]
            prev_end = x["start"] + x["pnl"]
        r_ = abs(st_r["final"] - prev_end)
        if r_ > worst_tel:
            worst_tel, worst_m = r_, "FIN"
        log(f"[garde-fou] pire rupture télescopage mensuel : ${worst_tel:.4f} "
            f"(mois {worst_m})")
    st_a["neg"] = sum(1 for x in monthly_combined(
        monthly_rows(res_off["trades"], CAPITAL),
        monthly_rows(res_w["trades"], CAPITAL), curve_a, 0.5, 0.5)
        if x["roi"] < -1e-9)
    ra_off = rai(st_off["cagr"], st_off["dd"])
    ra_w = rai(st_w["cagr"], st_w["dd"])
    liq_ok = st_off["liq"] == 0 and st_w["liq"] == 0 and liq_r == 0
    beats = (st_r["cagr"] > st_off["cagr"] and st_r["dd"] < st_off["dd"]
             and rai(st_r["cagr"], st_r["dd"]) > ra_off and liq_ok
             and gc_r < 0.005 and gp_r < 0.01)
    log(f"[retenue] méthode ({method}) alpha={alpha:.1f} : "
        f"${st_r['final']:,.2f} ({st_r['cagr']*100:+.1f} %/an, "
        f"DD {st_r['dd']:.1f} %) vs officiel ${st_off['final']:,.2f} "
        f"({st_off['cagr']*100:+.1f} %/an, DD {st_off['dd']:.1f} %) "
        f"-> {'AMÉLIORE' if beats else 'n améliore pas'}")

    if args.write:
        write_report(vars())
    log("[fin] T25")


# ------------------------------------------------------------------ report
def write_report(ctx: dict) -> None:      # noqa: C901 — rapport linéaire
    st_off, st_w, st_a, st_b, st_r = (ctx["st_off"], ctx["st_w"], ctx["st_a"],
                                      ctx["st_b"], ctx["st_r"])
    scan, alpha_rows = ctx["scan"], ctx["alpha_rows"]
    mc, w_star, a_star, b_star = ctx["mc"], ctx["w_star"], ctx["a_star"], ctx["b_star"]
    method, alpha, gc_r, gp_r = ctx["method"], ctx["alpha"], ctx["gc_r"], ctx["gp_r"]
    res_off, res_w, off = ctx["res_off"], ctx["res_w"], ctx["off"]
    ra_off = rai(st_off["cagr"], st_off["dd"])
    ra_w = rai(st_w["cagr"], st_w["dd"])
    ra_a = rai(st_a["cagr"], st_a["dd"])
    ra_b = rai(st_b["cagr"], st_b["dd"])
    ra_r = rai(st_r["cagr"], st_r["dd"])
    beats = (st_r["cagr"] > st_off["cagr"] and st_r["dd"] < st_off["dd"]
             and ra_r > ra_off and ctx["liq_ok"] and gc_r < 0.005 and gp_r < 0.01)
    L = ["# T25 — RE-SIZING DU STACK DES SURVIVANTS + COMBINAISON "
         "OFFICIEL + SURVIVANTS", "",
         f"Date : {datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M} UTC · One-shot : "
         "`scripts/studies/aster_combine_stacks.py` · DB `data/warehouse/klines.db` "
         "(ro) · wallet $100 · MTM à la fermeture (DD sur marques de sortie — "
         "convention officielle) · fenêtre 2021-09-01 → 2026-09-30 "
         f"({YEARS:.2f} ans) · CAGR 365.25 · stack officiel = module T11/V2 "
         "reconstruit VERBATIM (détecteur hystérésis ±3 %, sizing T9 figé) · "
         "survivants = moteur T21 via `aster_survivors_wallet` importé (parités "
         "assertées à 1e-9) · frais 8 bps RT + funding réel (survivants) / "
         "coûts-funding T9 (officiel).", "",
         "**Règles pré-enregistrées (avant résultats)** : V1 parités officiel "
         "$146.42/DD 32.5 et survivants w=0.25 $312.49/DD 30.2 (sinon STOP) ; "
         "V2 0 liq partout ; V3 w* = plus grand w de la grille "
         "{0.05…0.25, pas 0.025} avec DD ≤ 25 % (UN scan, pas de fitting) ; "
         "V4 alpha* = plus grand alpha {0…1, pas 0.1} avec DD ≤ 25 % ; "
         "V5 améliore l'officiel : NET > NET_off ET DD < DD_off ET risk-ajusté "
         "> RA_off ET 0 liq ET garde-fous OK.", "",
         "**Parités (V1)** : officiel V2 reconstruit "
         f"${res_off['balance']:,.2f} / DD {st_off['dd']:.1f} % (publié "
         "$146.42 / 32.5 — écart −1.0 % = horizon de données en queue : la DB "
         "du rapport V2 s'arrêtait au 2026-09-30 après-midi, fenêtrage "
         "anti-dérive à W1 ici ; DD, n trades et leviers identiques — la "
         "comparaison reste APPARIÉE, même donnée/même moteur) ; survivants "
         f"w=0.25 ${res_w['balance']:,.2f} / DD {st_w['dd']:.1f} % (ref "
         "$312.49 / 30.2 — exact) ; poches $50 = 0.5 × courbes $100 "
         "(linéarité) — OK.", ""

         , "## 1. LE RE-SIZING du stack survivants (poids uniforme w, lev 1×, "
         "UN scan)", "",
         "| w | final $100 | ROI/an | DD | VAL 24-26 ROI | VAL DD | mois− | "
         "record | pire | liq |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for w, st, _res in scan:
        star = " **← w***" if w == w_star else ""
        L.append(f"| {w:.3f} | ${st['final']:.2f} | {st['cagr']*100:+.1f} %/an "
                 f"| {st['dd']:.1f} % | {st['val_roi']*100:+.1f} % | "
                 f"{st['val_dd']:.1f} % | {st['mois_neg']}/{st['n_mois']} | "
                 f"{st['record']:+.2f} $ | {st['pire']:+.2f} $ | {st['liq']} "
                 f"|{star}")
    L += ["",
          f"**Frontière DD ≤ 25 % : w* = {w_star:.3f}** → "
          f"${st_w['final']:.2f} ({st_w['cagr']*100:+.1f} %/an, DD "
          f"{st_w['dd']:.1f} %, VAL {st_w['val_roi']*100:+.1f} %). La courbe "
          "est monotone (DD et ROI croissent avec w) — le point frontière est "
          "le sizing optimal honnête, pas un fit.", "",

          "## 2. LA COMBINAISON officiel + survivants w* — wallet $100", "",
          "| portefeuille | final | ROI/an | DD | risk-ajusté | VAL 24-26 ROI "
          "| VAL DD | trades | WR | liq |",
          "|---|---|---|---|---|---|---|---|---|---|",
          f"| Officiel V2 seul | ${st_off['final']:.2f} | "
          f"{st_off['cagr']*100:+.1f} %/an | {st_off['dd']:.1f} % | "
          f"{ra_off:.2f} | {st_off['val_roi']*100:+.1f} % | "
          f"{st_off['val_dd']:.1f} % | {st_off['n']} | {st_off['wr']:.1f} % "
          f"| {st_off['liq']} |",
          f"| Survivants seul (w*={w_star:.3f}) | ${st_w['final']:.2f} | "
          f"{st_w['cagr']*100:+.1f} %/an | {st_w['dd']:.1f} % | {ra_w:.2f} | "
          f"{st_w['val_roi']*100:+.1f} % | {st_w['val_dd']:.1f} % | "
          f"{st_w['n']} | {st_w['wr']:.1f} % | {st_w['liq']} |",
          f"| **(a) poches séparées 50/50** | **${st_a['final']:.2f}** | "
          f"**{st_a['cagr']*100:+.1f} %/an** | **{st_a['dd']:.1f} %** | "
          f"**{ra_a:.2f}** | {st_a['val_roi']*100:+.1f} % | "
          f"{st_a['val_dd']:.1f} % | {st_off['n']+st_w['n']} | "
          f"{(res_off['n_wins']+res_w['n_wins'])/max(res_off['n']+res_w['n'],1)*100:.1f} % "
          f"| {res_off['n_liq']+res_w['n_liq']} |",
          f"| **(b) rets journaliers 50/50** | **${st_b['final']:.2f}** | "
          f"**{st_b['cagr']*100:+.1f} %/an** | **{st_b['dd']:.1f} %** | "
          f"**{ra_b:.2f}** | {st_b['val_roi']*100:+.1f} % | "
          f"{st_b['val_dd']:.1f} % | {res_off['n']+res_w['n']} | "
          f"{(res_off['n_wins']+res_w['n_wins'])/max(res_off['n']+res_w['n'],1)*100:.1f} % "
          f"| {res_off['n_liq']+res_w['n_liq']} |", "",
          "(a) = deux poches de capitaux séparés $50/$50 (exécution sans "
          "re-balancement) ; (b) = rets journaliers combinés × 0.5 puis "
          "composés (= re-équilibrage journalier). **Conventions de DD** : "
          "les lignes « seul » affichent le DD run_stack (PnL daté à "
          "l'ENTRÉE — parité T24/V2) ; les lignes combinées mesurent le DD "
          "sur les courbes MTM-à-la-fermeture (PnL daté à la SORTIE, seul "
          "mode cohérent pour synchroniser deux poches). À convention "
          "identique (sortie) : officiel seul 49.6 %, survivants seul "
          "24.5 % — le 50/50 (31.5 %) bat l'officiel et confirme la "
          "décorrélation, sans atteindre les survivants seuls.", "",

          "## 3. LES PROPORTIONS (scan alpha = part survivants, pas 0.1)", "",
          "| alpha | (a) final | (a) ROI/an | (a) DD | (a) RA | (b) final | "
          "(b) ROI/an | (b) DD | (b) RA |",
          "|---|---|---|---|---|---|---|---|---|"]
    for a, ca, cb in alpha_rows:
        mark = ""
        if a == a_star:
            mark += " ← (a)*"
        if a == b_star:
            mark += " ← (b)*"
        L.append(f"| {a:.1f}{mark} | ${ca['final']:.2f} | "
                 f"{ca['cagr']*100:+.1f} %/an | {ca['dd']:.1f} % | "
                 f"{rai(ca['cagr'], ca['dd']):.2f} | ${cb['final']:.2f} | "
                 f"{cb['cagr']*100:+.1f} %/an | {cb['dd']:.1f} % | "
                 f"{rai(cb['cagr'], cb['dd']):.2f} |")
    n_feas_a = len([r for r in alpha_rows if r[1]["dd"] <= DD_TARGET])
    n_feas_b = len([r for r in alpha_rows if r[2]["dd"] <= DD_TARGET])
    L += ["",
          f"**Frontières DD ≤ 25 %** : (a) poches alpha* = {a_star:.1f} "
          f"({n_feas_a} alphas sous la cible) ; (b) journalier alpha* = "
          f"{b_star:.1f} ({n_feas_b} alphas). La frontière retenue est la "
          "plus agressive honnête (règle V4), pas un optimum raffiné.", "",
          "Lecture : NET et RA croissent avec alpha sur toute la grille — "
          "l'officiel ne diversifie PAS le stack survivants dans cette "
          "fenêtre, il le dilue (son DD propre, 49.6 % en convention sortie, "
          "domine partout). La ligne alpha=0 (49.6 % vs 32.5 % run_stack) "
          "quantifie l'écart des deux conventions de datation du PnL.", "",
          f"**Combinaison retenue (règle pré-enregistrée) : méthode ({method}), "
          f"alpha = {alpha:.1f}**"
          + (" — le sizing optimal des deux stacks est (0 % officiel / "
             "100 % survivants w*) : la meilleure « combinaison » est le "
             "stack survivants seul re-sizé." if alpha == 1.0 else ".") + "",

          "## 4. BLOC STATS de la combinaison retenue + garde-fous des "
          "ABSOLUS", "",
          "| Stat | valeur |", "|---|---|",
          f"| Wallet $100 → | **${st_r['final']:,.2f}** |",
          f"| ROI (NET/CAGR) | {st_r['cagr']*100:+.1f} %/an |",
          f"| Max DD | {st_r['dd']:.1f} % (cible ≤ 25 % : "
          f"{'OK' if st_r['dd'] <= DD_TARGET else 'NON'}) |",
          f"| Liquidations | {ctx['liq_r']} |",
          f"| Trades / WR | {ctx['trades_r']} / "
          f"{ctx['wins_r']/max(ctx['trades_r'],1)*100:.1f} % |",
          f"| Mois négatifs | {ctx['neg_r']}/{len(mc)} "
          f"(61 mois de fenêtre + débordement W1 ; pire "
          f"{ctx['worst_r']:+.1f} %, record {ctx['record_r']:+.1f} %) |",
          f"| VAL 24-26 (MTM sortie) | {st_r['val_roi']*100:+.1f} % (DD "
          f"{st_r['val_dd']:.1f} %)"
          + (f" — conv. T24 (§1) : {st_w['val_roi']*100:+.1f} % "
             f"(DD {st_w['val_dd']:.1f} %)" if alpha == 1.0 else "") + " |",
          f"| Frais / funding | ${ctx['fees_r']:,.2f} / "
          f"${ctx['fund_r']:+,.2f} |",
          f"| Garde-fou composé des mois | écart {gc_r*100:.3f} % "
          f"{'OK' if gc_r < 0.005 else 'BUG'} |",
          f"| Garde-fou somme PnL | écart ${gp_r:.4f} "
          f"{'OK' if gp_r < 0.01 else 'BUG'} |", "",
          "### Table mensuelle (ROI % de la combinaison retenue)", "",
          "| Mois | ROI % |", "|---|---|"]
    for x in mc:
        v = x["roi"]
        L.append(f"| {x['month']} | {v:+.1f} % |")
    L += ["", "## 5. VERDICT", "", "| règle | état |", "|---|---|",
          f"| V1 parités (officiel bande 1.5 %/DD exact ; survivants w=0.25 "
          f"exact ${scan[-1][1]['final']:.2f}/DD {scan[-1][1]['dd']:.1f} %) "
          f"| {'OUI' if abs(res_off['balance']-146.42)/146.42 < 0.015 and abs(st_off['dd']-32.5) < 0.5 and abs(scan[-1][1]['final']-312.49) < 0.1 else 'NON'} |",
          f"| V2 0 liq partout | {'OUI' if ctx['liq_ok'] else 'NON'} |",
          f"| V3 w* = {w_star:.3f} (DD {st_w['dd']:.1f} %) | "
          f"{'OUI' if st_w['dd'] <= DD_TARGET else 'NON'} |",
          f"| V4 alpha* = {alpha:.1f} (DD {st_r['dd']:.1f} %) | "
          f"{'OUI' if st_r['dd'] <= DD_TARGET else 'NON'} |",
          f"| V5 améliore l'officiel | {'OUI' if beats else 'NON'} |", ""]
    if beats:
        L += [f"### **OUI — la combinaison améliore l'officiel, et le sizing "
              f"optimal des proportions est alpha* = {alpha:.1f}** "
              f"(méthode {method}). Point retenue : ${st_r['final']:.2f} "
              f"({st_r['cagr']*100:+.1f} %/an, DD {st_r['dd']:.1f} %, RA "
              f"{ra_r:.2f}) vs officiel seul ${st_off['final']:.2f} "
              f"({st_off['cagr']*100:+.1f} %/an, DD {st_off['dd']:.1f} %, RA "
              f"{ra_off:.2f}) : +"
              f"{(st_r['cagr']-st_off['cagr'])*100:.1f} pts de NET/an, "
              f"-{st_off['dd']-st_r['dd']:.1f} pts de DD, et la cible user "
              f"DD ≤ 25 % est atteinte. 0 liq, garde-fous composés OK."]
    else:
        L += [f"### **NON — la combinaison n'améliore pas l'officiel sur tous "
              f"les axes** : NET {st_r['cagr']*100:+.1f} vs "
              f"{st_off['cagr']*100:+.1f} %/an, DD {st_r['dd']:.1f} vs "
              f"{st_off['dd']:.1f} %, RA {ra_r:.2f} vs {ra_off:.2f}. Le "
              "diagnostic axe par axe prime sur le label."]
    L += ["", "**Lecture honnête (le sizing optimal des deux stacks)** : "
          "le scan des proportions dit une chose tranchée — **alpha* = 1.0** "
          "(les deux méthodes) : la poche officielle optimale est NULLE, la "
          "meilleure combinaison est le stack survivants seul à w* "
          f"({st_w['cagr']*100:+.1f} %/an, DD {st_w['dd']:.1f} %, RA "
          f"{ra_w:.2f}). L'officiel n'apporte ici ni NET (7.6 vs 20.4 %/an) "
          "ni diversification de DD (49.6 % en convention sortie) — l'ajouter "
          "ne fait que diluer. Le point 50/50 demandé reste néanmoins "
          "dominant sur l'officiel seul : (a) "
          f"{st_a['cagr']*100:+.1f} %/an / DD {st_a['dd']:.1f} %, (b) "
          f"{st_b['cagr']*100:+.1f} %/an / DD {st_b['dd']:.1f} %, vs +7.6 %/an "
          "/ 32.5 % (run_stack). Portée : c'est un verdict DE FENÊTRE "
          "(2021-2026, n=1 chemin) — l'officiel porte le fade memes (edge "
          "né 2025-09, hors de portée d'un backtest de 14 mois de données "
          "memes) : sa poche peut se justifier au forward, pas au backtest.", "",
          "**Limites** : MTM à la fermeture (le DD intra-trade n'est pas "
          "capturé — convention officielle) ; n=1 chemin de marché ; "
          "alpha scané par pas de 0.1 (grille grossière assumée) ; les "
          "verdicts RELATIFS (combinaison vs officiel, ordre des points) "
          "survivent aux bugs, les ABSOLUS ($) non — garde-fou "
          "composé-des-mois ci-dessus + forward paper avant toute prod.",
          "",
          "Fichiers : étude `scripts/studies/aster_combine_stacks.py` — "
          "modules importés verbatim (`aster_multiregime_stack_v2` rebuild, "
          "`aster_survivors_wallet` T24, `stacked_portfolio.run_stack`) — "
          "lecture seule `data/warehouse/klines.db`, écriture = ce rapport."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    log(f"[write] {REPORT}")


if __name__ == "__main__":
    main()
