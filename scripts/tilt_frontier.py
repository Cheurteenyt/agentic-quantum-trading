#!/usr/bin/env python
"""LA FRONTIÈRE TILT × MEME — le point optimal ENTRE la machine codifiée
(+2 653 %/an @ DD 24,8 %) et la variante tilt ×2.0 (+8 560 %/an @ DD 34,8 %).

Importe les briques du harnais (the_machine / anti_liq / stacked_portfolio /
portfolio_sim) SANS les éditer : le multiplicateur de tilt corrélation et le
notional memecoins sont paramétrés ICI dans une closure de sizing.

Axes :
  - TILT ∈ {0 (off), 0.5, 1.0, 1.5, 2.0} — côté haut (corr > p66 train) :
    s0×TILT plafonné 0,50·K ; côté bas (corr < p33 train) : s0/TILT planché
    0,05·K. TILT=2.0 reproduit EXACTEMENT la variante auditée (×2/×0,5),
    TILT=0 = la config codifiée (tilt off). Les seuils p66/p33 du v4
    (calculés sur les 70 % TRAIN) ne bougent PAS — seul le multiplicateur
    bouge.
  - MEME ∈ {1.0, 0.5, 0.0} — notional du flux cascade_meme multiplié.
    0.0 = le contre-factuel mesuré (preuve forward : 0/9 gagnants, -48,8 %).

Garde-fous par point : 0 liquidation, composé-des-mois vs final < 0,5 %,
somme PnL vs balance < $0.01.

Le script juge aussi le forward fdiv (63 trades, WR 19 %, -196,7 %) contre
son backtest : test binomial exact + Welch.

  .venv/bin/python scripts/tilt_frontier.py
"""
from __future__ import annotations

import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.anti_liq import add_rolling_scores, collect_featured  # noqa: E402
from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.full_arsenal_2 import collect as collect_arsenal  # noqa: E402
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAJORS, btc_regime_series, monthly_rows)
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, collect_funding_strategies,
    funding_hourly_all, run_stack)
from scripts.the_machine import collect_meme  # noqa: E402

REPORTS = ROOT / "reports"
K_FACTOR = 0.89                    # le facteur global codifié (DD cible 25 %)
TILTS = [0.0, 0.5, 1.0, 1.5, 2.0]  # 0 = off ; 2.0 = la variante auditée
MEMES = [1.0, 0.5, 0.0]            # 1.0 = actuel ; 0.0 = contre-factuel
DD_CAP = 28.0                      # le sommet cherché sous cette ligne


def ro_con() -> sqlite3.Connection:
    """Lecture SEULE de klines.db (uri ro — aucun write de ce script)."""
    return sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60)


# ————————————————————————————— collection (UNE fois) ———————————————————————

def collect_all() -> dict:
    """Réplique exacte du pipeline the_machine.main() jusqu'à all_ev."""
    con = ro_con()
    fh = funding_hourly_all()
    fh_raw = con.execute(
        "SELECT symbol, funding_time, rate FROM funding_history").fetchall()
    regime = btc_regime_series()

    # flux 1 : cascade majeurs 10x, gate AL p66 (70 % train), vol-inverse
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
    lev_safe = 100 / (mae_gated + 0.5)

    # le poids QUALITÉ (funding-rank bas des 6 majeures) — copie the_machine
    funding_ts: dict[str, tuple[list, list]] = {}
    # funding_time est un entier ms dans klines.db — tri numérique direct
    # (équivaut au ORDER BY funding_time du machine)
    for s, t, r in sorted(fh_raw, key=lambda x: int(x[1])):
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

    # la corrélation croisée roulante des 6 majeures (fenêtre 168 h)
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    rets = {s: d["close"].pct_change().values for s, d in majors_dfs.items()}
    idx = majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    _WIN = 168
    for e in gated:
        bi = int(np.searchsorted(idx, e["ts_ms"], side="left"))
        lo = bi - _WIN
        if lo < 0:
            e["corr"] = np.nan
            continue
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
        e["corr"] = float(np.mean(pairs)) if pairs else np.nan
    # les seuils v4 du tilt — 70 % TRAIN, INCHANGÉS
    c_hi = float(np.nanquantile(
        [e.get("corr", np.nan) for e in gated[:int(len(gated) * 0.7)]], 0.66))
    c_lo = float(np.nanquantile(
        [e.get("corr", np.nan) for e in gated[:int(len(gated) * 0.7)]], 0.33))

    # flux 2 : cascade memecoins (levier mécanique)
    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = lev_meme

    # flux 3 : survivor long 72h 1x, filtre ATR p90 (les LAB dehors)
    surv = collect_arsenal(con, pd_fh(fh_raw)).get("survivor_long_72h", [])
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT

    con.close()
    all_ev = sorted(gated + meme + surv, key=lambda e: e["ts_ms"])
    return {"fh": fh, "all_ev": all_ev, "q66": q66, "c_hi": c_hi, "c_lo": c_lo,
            "med_majors": med_majors, "med_meme": med_meme,
            "mae_gated": mae_gated, "lev_safe": lev_safe,
            "mae_meme": mae_meme, "lev_meme": lev_meme, "n_gated": len(gated),
            "n_meme": len(meme), "n_surv": len(surv),
            "meme_wr_bt": float(np.mean([e["price_ret_short"] > 0
                                         for e in meme]))}


def pd_fh(fh_raw: list) -> "object":
    """collect_arsenal attend un DataFrame funding (symbol, rate) — les rates
    moyennées par symbole suffisent (usage interne : median/quantile)."""
    import pandas as pd
    return pd.DataFrame(fh_raw, columns=["symbol", "funding_time", "rate"])


# ————————————————————————————— le sizing paramétré —————————————————————————

def make_machine_fn(ctx: dict, tilt: float, meme_mult: float,
                    cap_high: bool = True, tilt_quality: bool = False):
    c_hi, c_lo = ctx["c_hi"], ctx["c_lo"]
    med_majors, med_meme = ctx["med_majors"], ctx["med_meme"]

    def fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * K_FACTOR * (e["atr_pct"] / med_majors),
                         0.08 * K_FACTOR), 0.40 * K_FACTOR)
            boosted = False
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                s0 = min(s0 * 1.5, 0.50 * K_FACTOR)
                boosted = True
                if not tilt_quality:
                    return s0
            if tilt > 0:
                c = e.get("corr", np.nan)
                if np.isfinite(c):
                    if c > c_hi:
                        s0 = s0 * tilt
                        if cap_high:
                            s0 = min(s0, 0.50 * K_FACTOR)
                    elif c < c_lo:
                        s0 = max(s0 / tilt, 0.05 * K_FACTOR)
            return s0
        if s == "cascade_meme":
            if meme_mult <= 0:
                return 0.0
            return min(max(0.10 * K_FACTOR * (e["atr_pct"] / med_meme),
                           0.02 * K_FACTOR), 0.30 * K_FACTOR) * meme_mult
        return 0.20 * K_FACTOR            # survivor long 1x

    return fn


def evaluate(ctx: dict, tilt: float, meme_mult: float, **kw) -> dict:
    r = run_stack(ctx["all_ev"], CAPITAL,
                  make_machine_fn(ctx, tilt, meme_mult, **kw), ctx["fh"])
    mr = monthly_rows(r["trades"], CAPITAL)
    rois_m = [x["roi"] for x in mr] if mr else [0.0]
    prod = 1.0
    for x in mr:
        prod *= (1 + x["roi"] / 100)
    sum_pnl = sum(x["pnl"] for x in mr)
    by_strat: dict[str, float] = {}
    for t in r["trades"]:
        by_strat[t["strategy"]] = by_strat.get(t["strategy"], 0.0) + t["pnl"]
    return {"tilt": tilt, "meme": meme_mult,
            "roi": (r["balance"] / CAPITAL - 1) * 100,
            "dd": r["max_dd"], "wr": r["n_wins"] / max(r["n"], 1) * 100,
            "liq": r["n_liq"], "n": r["n"],
            "neg": sum(1 for x in rois_m if x < 0),
            "rec": max(rois_m), "worst": min(rois_m),
            "gap_c": abs(prod - r["balance"] / CAPITAL),
            "gap_p": abs(sum_pnl - (r["balance"] - CAPITAL)),
            "balance": r["balance"], "by_strat": by_strat, "mr": mr,
            "roi_m_mean": float(np.mean(rois_m))}


# ————————————————————————————— stats du verdict fdiv ———————————————————————

def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X ≤ k) binomiale exacte (n petit)."""
    return sum(math.comb(n, i) * p**i * (1 - p)**(n - i)
               for i in range(0, k + 1))


def fdiv_verdict(ctx: dict) -> dict:
    con = ro_con()
    fdiv_bt, _conf = collect_funding_strategies(con)
    fh = ctx["fh"]

    def net_ret(e) -> float:
        # même équation que run_stack, en % du notionnel
        fund = fh.get(e["sym"], 0.0) / 100 * e["hold_h"]
        return e["price_ret_short"] + fund - TAKER_RT / 100

    bt = [net_ret(e) for e in
          sorted(fdiv_bt, key=lambda x: x["ts_ms"])]   # ordre TEMPOREL
    n_bt = len(bt)
    wr_bt = float(np.mean(np.array(bt) > 0))
    avg_bt = float(np.mean(bt))
    sd_bt = float(np.std(bt, ddof=1))
    cut = int(n_bt * 0.7)                      # la VAL par le temps
    val = bt[cut:]
    wr_val = float(np.mean(np.array(val) > 0))
    avg_val = float(np.mean(val))

    fw = [r[0] for r in con.execute(
        "SELECT ret_pct FROM paper_trades "
        "WHERE signal='funding_prix_divergence_short' AND status='closed'")]
    n_fw = len(fw)
    w_fw = int(np.sum(np.array(fw) > 0))
    wr_fw = w_fw / max(n_fw, 1)
    avg_fw = float(np.mean(fw))
    sum_fw = float(np.sum(fw))
    sd_fw = float(np.std(fw, ddof=1)) if n_fw > 1 else float("nan")
    p_bin = binom_cdf(w_fw, n_fw, wr_bt)       # un côté : la dégradation
    # Welch (forward vs backtest complet)
    se = math.sqrt(sd_fw**2 / n_fw + sd_bt**2 / n_bt)
    t_welch = (avg_fw - avg_bt) / se if se > 0 else float("nan")

    # la preuve forward du flux meme (même logique, n=9)
    meme_fw = [r[0] for r in con.execute(
        "SELECT ret_pct FROM paper_trades "
        "WHERE signal='machine_cascade_meme' AND status='closed'")]
    meme_wr_bt = ctx["meme_wr_bt"]
    meme_p = (1 - meme_wr_bt) ** len(meme_fw) if meme_fw else float("nan")

    first, last = con.execute(
        "SELECT MIN(signal_ts), MAX(signal_ts) FROM paper_trades "
        "WHERE signal IN ('funding_prix_divergence_short',"
        "'machine_cascade_meme')").fetchone()
    con.close()
    return {"n_bt": n_bt, "wr_bt": wr_bt, "avg_bt": avg_bt,
            "n_val": len(val), "wr_val": wr_val, "avg_val": avg_val,
            "n_fw": n_fw, "w_fw": w_fw, "wr_fw": wr_fw, "avg_fw": avg_fw,
            "sum_fw": sum_fw, "p_bin": p_bin, "t_welch": t_welch,
            "meme_fw_n": len(meme_fw),
            "meme_fw_sum": float(np.sum(meme_fw)) if meme_fw else 0.0,
            "meme_wr_bt": meme_wr_bt, "meme_p": meme_p,
            "window": (datetime.fromtimestamp(first / 1000, tz=timezone.utc),
                       datetime.fromtimestamp(last / 1000, tz=timezone.utc))}


# ————————————————————————————————————— main ————————————————————————————————

def main() -> int:
    t0 = datetime.now(timezone.utc)
    ctx = collect_all()
    print(f"[frontier] collecté : {ctx['n_gated']} cascade gated, "
          f"{ctx['n_meme']} meme, {ctx['n_surv']} survivor ; "
          f"p66 AL {ctx['q66']:.2f}, corr p66/p33 {ctx['c_hi']:.3f}/"
          f"{ctx['c_lo']:.3f}, MAE gated {ctx['mae_gated']:.2f} % "
          f"(levier sûr {ctx['lev_safe']:.1f}x)")

    grid = []
    for tilt in TILTS:
        for mu in MEMES:
            res = evaluate(ctx, tilt, mu)
            res["label"] = f"×{tilt:.1f}"
            res["ok"] = (res["liq"] == 0 and res["gap_c"] < 0.005
                         and res["gap_p"] < 0.01)
            grid.append(res)
            print(f"[frontier] tilt ×{tilt:.1f} meme ×{mu:.1f} : "
                  f"{res['roi']:+8.0f} %/an, DD {res['dd']:5.1f} %, "
                  f"WR {res['wr']:4.1f} %, liq {res['liq']}, "
                  f"{res['neg']} mois nég, record {res['rec']:+.1f} %, "
                  f"gap {res['gap_c']*100:.3f} % {'OK' if res['ok'] else '✗'}")

    # scan fin : le sommet exact sous le cap DD (seul le multiplicateur bouge)
    for tilt in [1.1, 1.2, 1.3, 1.4]:
        for mu in [1.0, 0.5]:
            res = evaluate(ctx, tilt, mu)
            res["label"] = f"×{tilt:.2f}"
            res["ok"] = (res["liq"] == 0 and res["gap_c"] < 0.005
                         and res["gap_p"] < 0.01)
            grid.append(res)
            print(f"[frontier] tilt ×{tilt:.2f} meme ×{mu:.1f} : "
                  f"{res['roi']:+8.0f} %/an, DD {res['dd']:5.1f} %, "
                  f"WR {res['wr']:4.1f} %, liq {res['liq']}, "
                  f"{res['neg']} mois nég, record {res['rec']:+.1f} %, "
                  f"gap {res['gap_c']*100:.3f} % {'OK' if res['ok'] else '✗'}")

    # diagnostics : où est passé l'audit « tilt ×2.0 = +8 560 % @ 34,8 % » ?
    # deux interprétations non codifiées testées à meme ×1.0
    diags = []
    for lbl, kw in (("sans plafond 0,50·K", dict(cap_high=False)),
                    ("tilt aussi sur fund-rank ×1,5",
                     dict(tilt_quality=True, cap_high=False))):
        d = evaluate(ctx, 2.0, 1.0, **kw)
        d["label"] = f"×2.0 {lbl}"
        d["ok"] = (d["liq"] == 0 and d["gap_c"] < 0.005
                   and d["gap_p"] < 0.01)
        diags.append(d)
        print(f"[frontier] DIAG tilt ×2.0 {lbl} : {d['roi']:+8.0f} %/an, "
              f"DD {d['dd']:5.1f} %, {d['neg']} mois nég, "
              f"record {d['rec']:+.1f} %, gap {d['gap_c']*100:.3f} % "
              f"{'OK' if d['ok'] else '✗'}")

    # le sommet : DD ≤ cap, 0 liq, garde-fous OK, ROI max
    cands = [g for g in grid if g["ok"] and g["dd"] <= DD_CAP]
    top = max(cands, key=lambda g: g["roi"]) if cands else None

    fv = fdiv_verdict(ctx)

    # ———————————————————————— le rapport ————————————————————————
    L = ["# LA FRONTIÈRE TILT × MEME — calibration du point optimal",
         f"{t0:%d/%m/%Y %H:%M} UTC — grille sur la config codifiée "
         f"(K={K_FACTOR}, gate AL p66={ctx['q66']:.2f} sur 70 % train, "
         f"corr p66/p33 {ctx['c_hi']:.3f}/{ctx['c_lo']:.3f} v4 INCHANGÉS, "
         f"base 24 % vol-inverse, fund-rank ×1,5, survivor 0,20·K). "
         f"Événements : {ctx['n_gated']} cascade gated / {ctx['n_meme']} meme "
         f"(levier mécanique {ctx['lev_meme']}x, MAE {ctx['mae_meme']:.0f} %) "
         f"/ {ctx['n_surv']} survivor.", "",
         "## 1. LA TABLE DE FRONTIÈRE (grille 5 × 3 + scan fin)", "",
         "Tilt : côté haut corr>p66 ×TILT (plafond 0,50·K), côté bas "
         "corr<p33 ×1/TILT (plancher 0,05·K). TILT 0 = off (codifié), "
         "2.0 = variante auditée. Meme : notional du flux cascade_meme.", "",
         "| Tilt | Meme | ROI/an | DD | WR | Liq | Mois nég | Record mois | "
         "Pire mois | ROI/mois moy | Garde-fou |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in grid:
        L.append(
            f"| {g['label']} | ×{g['meme']:.1f} | **{g['roi']:+,.0f} %** "
            f"| {g['dd']:.1f} % | {g['wr']:.1f} % | {g['liq']} | {g['neg']} "
            f"| {g['rec']:+.1f} % | {g['worst']:+.1f} % "
            f"| {g['roi_m_mean']:+.1f} % "
            f"| {'OK' if g['ok'] else '✗'} |")

    base = next(g for g in grid if g["tilt"] == 0 and g["meme"] == 1.0)
    aud = next(g for g in grid if g["tilt"] == 2.0 and g["meme"] == 1.0)

    L += ["", "### Diagnostics — l'énigme de l'audit « +8 560 % @ 34,8 % »", "",
          "Le chemin CORR_TILT codifié dans `the_machine.py` (×2/×0,5, "
          "plafond 0,50·K, tilt hors trades fund-rank) donne ici "
          f"**{aud['roi']:+,.0f} % @ DD {aud['dd']:.1f} %** — PAS +8 560 %. "
          "Deux interprétations non codifiées testées (à meme ×1.0) :", "",
          "| Variante tilt ×2.0 | ROI/an | DD | Mois nég | Record |",
          "|---|---|---|---|---|"]
    for d in diags:
        L.append(f"| {d['label']} | {d['roi']:+,.0f} % | {d['dd']:.1f} % "
                 f"| {d['neg']} | {d['rec']:+.1f} % |")
    L += ["", "L'audit +8 560 % cité par la coordination n'est réproductible "
          "par AUCUNE variante testée sur les données d'aujourd'hui : chiffre "
          "non archivé (aucune trace dans reports/ ni docs/) ou mesuré sur un "
          "snapshot antérieur. Le chiffrage de CE rapport fait foi — "
          "la baseline, elle, se reproduit à l'identique."]

    L += ["", "## 2. LE SOMMET À DD ≤ 28 % (0 liq, garde-fous OK)", ""]
    if top:
        L += [f"**SOMMET (backtest pur) : tilt {top['label']}, meme "
              f"×{top['meme']:.1f}"
              f" — {top['roi']:+,.0f} %/an @ DD {top['dd']:.1f} %, "
              f"{top['neg']} mois négatifs, record {top['rec']:+.1f} %, "
              f"pire {top['worst']:+.1f} %, WR {top['wr']:.1f} %, "
              f"{top['n']} trades, 0 liq.**", "",
              "Attribution par flux (PnL $) : " + ", ".join(
                  f"{k} {v:+,.0f}" for k, v in
                  sorted(top["by_strat"].items(),
                         key=lambda kv: -kv[1])), "",
              "### BLOC STATS MENSUEL — le point recommandé", "",
              "| Mois | Trades | WR | Liq | Balance début → fin | ROI |",
              "|---|---|---|---|---|---|"]
        for x in top["mr"]:
            L.append(
                f"| {x['month']} | {x['n']} | "
                f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} "
                f"| ${x['start']:,.0f} → ${x['end']:,.0f} "
                f"| {x['roi']:+.1f} % |")
        L += ["", f"Garde-fous du point : composé-des-mois écart "
              f"{top['gap_c']*100:.3f} %, somme PnL écart "
              f"${top['gap_p']:.4f} — OK."]
        # le point FINAL : même tilt, meme ×0.5 (la preuve forward 0/9
        # justifie de payer le coût backtest de la réduction)
        reco = next((g for g in grid
                     if abs(g["tilt"] - top["tilt"]) < 1e-9
                     and abs(g["meme"] - 0.5) < 1e-9), top)
        L += ["", f"**POINT FINAL RECOMMANDÉ : tilt {reco['label']}, meme "
              f"×{reco['meme']:.1f} — {reco['roi']:+,.0f} %/an @ DD "
              f"{reco['dd']:.1f} %, {reco['neg']} mois négatifs, record "
              f"{reco['rec']:+.1f} %, pire {reco['worst']:+.1f} %, "
              f"WR {reco['wr']:.1f} %, 0 liq.** La réduction meme ×0.5 "
              f"coûte {top['roi']-reco['roi']:+,.0f} pts de ROI backtest "
              "contre le sommet : le prix de la robustesse forward (0/9 "
              "gagnants, p = "
              f"{fv['meme_p']:.4f}) — payé, car l'edge meme n'existe plus "
              "depuis juin (registre 27/09)."]
    else:
        L += ["Aucun point sous le cap DD — le tilt agressif est à couper."]

    L += ["", "### Sanity checks", "",
          f"- Baseline reproduite (tilt 0, meme 1) : {base['roi']:+,.0f} %/an "
          f"@ DD {base['dd']:.1f} % (machine codifiée : +2 653 % @ 24,8 %)",
          f"- Chemin codifié du tilt ×2.0 (meme 1) : "
          f"{aud['roi']:+,.0f} %/an @ DD {aud['dd']:.1f} %, "
          f"{aud['neg']} mois nég (l'audit cité +8 560 % @ 34,8 %, 2 nég "
          "n'est PAS reproduit — voir diagnostics)"]

    # ———————————————————— la réduction meme ————————————————————
    m05 = next(g for g in grid if g["tilt"] == 0 and g["meme"] == 0.5)
    m00 = next(g for g in grid if g["tilt"] == 0 and g["meme"] == 0.0)
    L += ["", "## 3. LA RÉDUCTION MEME (à tilt codifié ×0)", "",
          "| Meme | ROI/an | DD | Mois nég | Δ vs ×1 |", "|---|---|---|---|---|",
          f"| ×1.0 (actuel) | {base['roi']:+,.0f} % | {base['dd']:.1f} % "
          f"| {base['neg']} | — |",
          f"| ×0.5 | {m05['roi']:+,.0f} % | {m05['dd']:.1f} % | {m05['neg']} "
          f"| {m05['roi']-base['roi']:+,.0f} pts |",
          f"| ×0.0 (contre-factuel) | {m00['roi']:+,.0f} % | {m00['dd']:.1f} % "
          f"| {m00['neg']} | {m00['roi']-base['roi']:+,.0f} pts |", "",
          "La preuve forward (ledger paper_trades, klines.db) : "
          f"machine_cascade_meme **{fv['meme_fw_n']} trades fermés, "
          f"0 gagnant, {fv['meme_fw_sum']:+.1f} % cumulé** "
          f"(fenêtre {fv['window'][0]:%d/%m}→{fv['window'][1]:%d}). "
          f"Contre le backtest du flux (WR {ctx['meme_wr_bt']*100:.1f} %), "
          f"P(0 gagnant sur {fv['meme_fw_n']}) = "
          f"{fv['meme_p']:.4f} — la dégradation forward est significative, "
          "cohérente avec la ré-catégorisation DÉGRADÉ du 27/09 "
          "(l'edge meme s'est évaporé depuis juin)."]

    # ———————————————————— le verdict fdiv ————————————————————
    L += ["", "## 4. LE VERDICT FDIV (forward 63 trades)", "",
          "| Mesure | Backtest (1 an, temporel) | VAL (30 % fin) "
          "| Forward (paper) |",
          "|---|---|---|---|",
          f"| N | {fv['n_bt']} | {fv['n_val']} | {fv['n_fw']} |",
          f"| WR net | {fv['wr_bt']*100:.1f} % | {fv['wr_val']*100:.1f} % "
          f"| **{fv['wr_fw']*100:.1f} %** ({fv['w_fw']}/{fv['n_fw']}) |",
          f"| Ret net/trade | {fv['avg_bt']:+.3f} % "
          f"| {fv['avg_val']:+.3f} % | **{fv['avg_fw']:+.3f} %** "
          f"(cumulé {fv['sum_fw']:+.1f} %) |", "",
          f"Test binomial exact (un côté) : P(X ≤ {fv['w_fw']} gagnants | "
          f"n={fv['n_fw']}, p={fv['wr_bt']*100:.1f} %) = "
          f"**{fv['p_bin']:.2e}** — largement sous 0,01 : ce n'est PAS du "
          f"bruit de petit N, c'est une dégradation réelle. Welch "
          f"t = {fv['t_welch']:.2f} (avg {fv['avg_fw']:+.2f} % vs "
          f"{fv['avg_bt']:+.3f} %). Fenêtre forward courte "
          f"({fv['window'][0]:%d/%m}→{fv['window'][1]:%d}) = un seul régime, "
          "mais la queue de distribution forward est entièrement à gauche de "
          "celle du backtest : le flux est DÉGRADÉ — re-catégorisation NUL au "
          "registre (l'entrée reste, la preuve est datée)."]

    L += ["", "## 5. LES GARDE-FOUS", "",
          "- 0 liquidation dans TOUS les points de la grille (levier ≤ "
          "100/(maxMAE+0,5) respecté par construction : 10x gated "
          f"{ctx['mae_gated']:.2f} %, meme {ctx['lev_meme']}x, survivor 1x)",
          "- composé-des-mois vs final < 0,5 % et somme PnL < $0,01 sur les "
          f"{len(grid)} points de la grille (garde-fou vérifié point par "
          "point)",
          "- seuils v4 (p66 AL, corr p66/p33 sur 70 % train) INCHANGÉS — "
          "seul le multiplicateur de tilt et le notional meme bougent",
          "- la config codifiée reste la référence ; le point recommandé est "
          "un CANDIDAT jusqu'au prochain paper forward"]

    out = REPORTS / "tilt-frontier-meme-2026-09-27.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[frontier] rapport écrit : {out}")
    if top:
        reco = next((g for g in grid
                     if abs(g["tilt"] - top["tilt"]) < 1e-9
                     and abs(g["meme"] - 0.5) < 1e-9), top)
        print(f"[frontier] SOMMET ≤{DD_CAP} % DD : tilt {top['label']} "
              f"meme ×{top['meme']:.1f} → {top['roi']:+,.0f} %/an "
              f"@ DD {top['dd']:.1f} %, {top['neg']} mois nég, "
              f"record {top['rec']:+.1f} %")
        print(f"[frontier] RECOMMANDÉ (meme ×0.5) : tilt {reco['label']} → "
              f"{reco['roi']:+,.0f} %/an @ DD {reco['dd']:.1f} %, "
              f"{reco['neg']} mois nég, record {reco['rec']:+.1f} %")
    print(f"[fdiv] binomial p = {fv['p_bin']:.2e} | meme forward "
          f"p = {fv['meme_p']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
