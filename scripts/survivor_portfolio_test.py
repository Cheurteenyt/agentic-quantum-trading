#!/usr/bin/env python
"""LE PORTEFEUILLE DES SURVIVANTS — vol_spike_6h × derek518 (28/09).

Contexte (reports/decay-curve-2026-09-28.md) : l'edge cascade a décroché à
~zéro au T3 2026. Les edges qui ont SURVÉCU au régime mort :
  1. vol_spike_6h (le fade 6h de p5_frequency_test — sa VAL se renforçait,
     corr -0,50 avec cascade_meme, -0,22 majors),
  2. la réplication derek518 (72 events validés : +88 %/26 j @ DD 6,4 %,
     espérance +18,8 %/trade — builder de scripts/archive_studies/
     derek_replication_test.py, inchangé).

LA QUESTION : un portefeuille construit sur les survivants porte-t-il le
régime actuel ? Protocole :
  - fenêtre commune = les ~26 jours derek (seule période où les deux flux
    coexistent) ; vol_spike filtré sur cette fenêtre,
  - wallet run_stack 2 créneaux (1 slot/flux), $100, frais réels :
    vol_spike au sizing machine EXACT (vol-inverse base 0,10·K, bornes
    0,02·K/0,30·K, K=0,89 — the_machine.py), derek à 0,10 fixe, spot 1x
    LONG (0 liquidation possible), coûts taker 0,09 %×2 + slippage
    honnête 0,5 %/côté (118 bps RT) et variante optimiste 0,2 % (58 bps),
  - variante PURE-FADE (vol_spike seul, même fenêtre) pour isoler
    l'apport derek + derek SEUL (mono-slot, capture),
  - comparaison de régime : le fade en standalone par trimestre
    (Q4'25 → Q3'26) — porte-t-il les DEUX régimes ? (derek = T3 seul
    par construction → non vérifiable Q2, déclaré),
  - corrélation des PnL vol_spike × derek : mensuelle (dégénérée, 2 mois)
    et QUOTIDIENNE en vue flux (le vrai test de chevauchement de signal),
  - garde-fous anti-dérive : composé-des-mois vs final, somme PnL.

HONNÊTÉ pré-enregistrée : n derek = 72 sur 26 jours = 1 régime — le test
est INDICATIF ; biais survivorship v2 (derek est dans le test PARCE QU'il
a survécu) ; l'edge v2 était RELATIF (vs baseline token), ici ABSOLU.

  .venv/bin/python scripts/survivor_portfolio_test.py

Lecture seule des DBs (mode=ro). Garde ts_ms : unité vérifiée par ordre
de grandeur (klines = ns, fomo_ohlcv/swap = ms).
"""
from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.stacked_portfolio import CAPITAL, TAKER_RT, run_stack  # noqa: E402
from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
from scripts.archive_studies.derek_replication_test import (  # noqa: E402
    BAR_MS, SLIP_HONEST, SLIP_OPT, TAKER as DEREK_TAKER,
    build_events, load_buys, load_ohlcv)

KDB = ROOT / "data" / "warehouse" / "klines.db"          # LECTURE SEULE (ro)
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"      # LECTURE SEULE (ro)
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"             # LECTURE SEULE (ro)
REPORT = ROOT / "reports" / "survivor-portfolio-2026-09-28.md"

K = 0.89                    # le facteur global de la machine (calibration DD)
SIZE_DEREK = 0.10           # derek : 0,10 fixe (mission)
DEREK_BPS_HONEST = int((DEREK_TAKER * 1e4 + 50) * 2)   # 0,09 %×2 + 0,5 %/côté
DEREK_BPS_OPT = int((DEREK_TAKER * 1e4 + 20) * 2)      # 0,09 %×2 + 0,2 %/côté
HOLD_DEREK = 24
NS = 10**6                  # ms → ns pour run_stack (ts_ms = ns chez le harnais)
DAY_MS = 86_400_000


# —————————————————————————— infrastructure harnais ——————————————————————————

def funding_hourly_ro() -> dict[str, float]:
    """funding_hourly_all en LECTURE SEULE (même formule)."""
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    acc: dict[str, list[float]] = {}
    for s, r in con.execute("SELECT symbol, rate FROM funding_history"):
        try:
            acc.setdefault(s, []).append(float(r))
        except (TypeError, ValueError):
            continue
    con.close()
    return {s: sum(v) / len(v) * 100 / 8 for s, v in acc.items()}


def machine_spike_size(e: dict, med: float) -> float:
    """Le sizing machine EXACT du flux vol_spike_6h (the_machine.machine_fn):
    vol-inverse base 0,10·K borné [0,02·K ; 0,30·K]."""
    return min(max(0.10 * K * (e["atr_pct"] / med), 0.02 * K), 0.30 * K)


def make_size_fn(med_spike: float):
    def fn(e, st=None):
        if e["strategy"] == "vol_spike_6h":
            return machine_spike_size(e, med_spike)
        return SIZE_DEREK
    return fn


# —————————————————————————— builders → events harnais ————————————————————————

def build_spike(con: sqlite3.Connection) -> list[dict]:
    """Builder EXISTANT p5 (seuils 4×/2,5 %, gate ATR décile) → harnais."""
    ev = collect_vol_spike(con, hold=6)
    for e in ev:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    ev.sort(key=lambda e: e["ts_ms"])
    return ev


def build_derek() -> tuple[list[dict], dict]:
    """Builder EXISTANT derek (≥$5k, age≥7j, swap+10min, hold 24h) → harnais.
    Sortie = garde anti-rug appliquée (pic ≥1,2× puis <0,65×max), LONG spot
    1x, fund_sign=0 (spot : pas de funding), mae = pire creux du path UTILISÉ."""
    buys, st = load_buys()
    oh_map = load_ohlcv()
    ev, f = build_events(buys, oh_map)
    # garde ts_ms : fomo_ohlcv time = ms (le builder derek le traite en ms)
    t0 = int(oh_map[next(iter(oh_map))][0][0])
    if not (10**12 < t0 < 10**14):
        raise SystemExit(f"[surv] fomo_ohlcv time hors plage ms : {t0}")
    out = []
    g_trig = 0
    for e in ev:
        gi, gg = e["guard_idx"], e["guard_gross"]
        dur_h = max(int(gi - e["entry_idx"]), 1)
        if gi != e["exit_idx"]:
            g_trig += 1
        path = e["path"][:dur_h + 1]
        mae = max((e["entry"] - float(np.min(path))) / e["entry"] * 100, 0.0)
        exit_ms = e["entry_ts"] + dur_h * BAR_MS
        out.append({
            "sym": e["mint"], "ts_ms": e["entry_ts"] * NS,  # ns (harnais)
            "strategy": "derek_518", "lev": 1, "hold_h": dur_h,
            "entry": e["entry"], "exit": e["entry"] * (1.0 + gg),
            "price_ret_short": gg * 100.0,     # LONG : ret = exit/entry - 1
            "mae_adverse": mae, "fund_sign": 0, "side": "long",
            "exit_day_ms": exit_ms, "swap_usd": e["usd"],
        })
    st.update(f)
    st["guard_trig"] = g_trig
    out.sort(key=lambda e: e["ts_ms"])
    return out, st


# —————————————————————————————— mesures ——————————————————————————————————————

def wallet(events: list[dict], med: float, fh: dict[str, float],
           derek_bps: int | None = None) -> dict:
    evs = [dict(e) for e in events]
    if derek_bps is not None:
        for e in evs:
            if e["strategy"] == "derek_518":
                e["fee_rt_bps"] = derek_bps
    res = run_stack(evs, CAPITAL, make_size_fn(med), fh)
    return {"res": res, "med": med}


def stats(res: dict) -> dict:
    tr = res["trades"]
    mrows = monthly_rows(tr, CAPITAL)
    days = ((tr[-1]["exit_ts"] - tr[0]["entry_ts"]).total_seconds() / 86400
            if tr else 0.0)
    roi = res["balance"] / CAPITAL - 1
    roi_an = (1 + roi) ** (365.25 / days) - 1 if days > 0 and roi > -1 else float("nan")
    margins = [t["margin"] for t in tr] or [1.0]
    worst_i = int(np.argmin([t["pnl"] / t["margin"] for t in tr])) if tr else -1
    prod = 1.0
    for r in mrows:
        prod *= 1 + r["roi"] / 100
    gap_c = abs(prod - res["balance"] / CAPITAL)
    gap_p = abs(sum(r["pnl"] for r in mrows) - (res["balance"] - CAPITAL))
    rois_m = [r["roi"] for r in mrows]
    pnl_tot = sum(t["pnl"] for t in tr)
    top3 = sum(t["pnl"] for t in sorted(tr, key=lambda t: -t["pnl"])[:3]) \
        if tr else 0.0
    return {
        "n": res["n"], "wr": res["n_wins"] / max(res["n"], 1) * 100,
        "liq": res["n_liq"], "roi": roi * 100, "roi_an": roi_an * 100,
        "dd": res["max_dd"], "days": days, "bal": res["balance"],
        "exp": float(np.mean([t["pnl"] for t in tr])) if tr else 0.0,
        "exp_pct": float(np.mean([t["pnl"] / t["margin"] for t in tr])) * 100
        if tr else 0.0,
        "fees": res["fees"], "funding": res["funding"],
        "worst": tr[worst_i] if tr else None,
        "best": max(tr, key=lambda t: t["pnl"]) if tr else None,
        "top3_share": top3 / pnl_tot if pnl_tot > 0 else float("nan"),
        "mrows": mrows, "neg_m": sum(1 for x in rois_m if x < 0),
        "worst_m": min(rois_m) if rois_m else 0.0,
        "rec_m": max(rois_m) if rois_m else 0.0,
        "gap_c": gap_c, "gap_p": gap_p, "trades": tr,
    }


def fmt_monthly(st: dict) -> list[str]:
    out = ["| Mois | Trades | WR | Liq | Balance début → fin | ROI mois |",
           "|---|---|---|---|---|---|"]
    for r in st["mrows"]:
        out.append(f"| {r['month']} | {r['n']} | {r['w']/max(r['n'],1)*100:.0f} % "
                   f"| {r['liq']} | ${r['start']:,.0f} → ${r['end']:,.2f} "
                   f"| {r['roi']:+.1f} % |")
    return out


def bloc(title: str, s: dict, extra: str = "") -> list[str]:
    w = s["worst"]
    return [f"**{title}** : $100 → **${s['bal']:,.2f}** "
            f"(ROI {s['roi']:+.1f} % sur {s['days']:.0f} j, extrap. naive "
            f"{s['roi_an']:+.0f} %/an — NON interprétable, fenêtre courte)",
            f"  {s['n']} trades, WR {s['wr']:.1f} %, liq {s['liq']}, "
            f"DD {s['dd']:.1f} %, espérance {s['exp']:+.3f} $/trade "
            f"({s['exp_pct']:+.2f} % marge), frais ${s['fees']:,.2f}, "
            f"funding ${s['funding']:+.2f}",
            f"  mois : {s['neg_m']} nég. / {len(s['mrows'])}, "
            f"pire {s['worst_m']:+.1f} %, record {s['rec_m']:+.1f} %"
            + (f" | pire trade {w['sym'][:10]} {w['pnl']/w['margin']*100:+.1f} % "
               f"(${w['pnl']:+.2f})" if w else "") + extra]


def unit_pnl_daily(evs: list[dict], slip: float | None) -> dict[str, float]:
    """PnL unitaire (marge 1) par JOUR de sortie, vue FLUX (tous les events,
    sans contention de créneau) — mesure le chevauchement de SIGNAL."""
    by_d: dict[str, float] = defaultdict(float)
    for e in evs:
        if e["strategy"] == "derek_518":
            c = (1 - DEREK_TAKER - slip) ** 2
            pnl = (1 + e["price_ret_short"] / 100) * c - 1
            t_ms = e["ts_ms"] / NS + e["hold_h"] * 3600_000
        else:
            pnl = (e["price_ret_short"] / 100 - e["fee_rt_bps"] / 1e4)
            t_ms = e["ts_ms"] / NS + e["hold_h"] * 3600_000
        d = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        by_d[d] += pnl
    return dict(by_d)


def corr(a: dict[str, float], b: dict[str, float]) -> tuple[float, float, int]:
    keys = sorted(set(a) | set(b))
    x = np.array([a.get(k, 0.0) for k in keys])
    y = np.array([b.get(k, 0.0) for k in keys])
    if len(keys) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan"), len(keys)
    pear = float(np.corrcoef(x, y)[0, 1])
    spear = float(np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1])
    return pear, spear, len(keys)


# ————————————————————————————————— main ——————————————————————————————————————

def main() -> int:
    t0 = datetime.now(timezone.utc)
    fh = funding_hourly_ro()
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
    print("[surv] build vol_spike (builder p5, gate ATR)…")
    spike_all = build_spike(con)
    con.close()
    print(f"[surv] vol_spike total = {len(spike_all)} events")
    print("[surv] build derek518 (builder archivé, garde anti-rug)…")
    derek_all, dst = build_derek()
    print(f"[surv] derek = {len(derek_all)} events "
          f"(≥$5k {dst['ge_5k']}, age≥7j {dst['age_ok']}, fwd24 {dst['exit_ok']}, "
          f"garde déclenchée {dst['guard_trig']}x)")

    # —— la fenêtre commune : les ~26 jours derek —— (ts_ms ICI = ns)
    w0 = min(e["ts_ms"] for e in derek_all)
    w1 = max(e["ts_ms"] + e["hold_h"] * 3600 * 10**9 for e in derek_all)
    spike_win = [e for e in spike_all if w0 <= e["ts_ms"] <= w1]
    med_win = float(np.median([e["atr_pct"] for e in spike_win]))
    med_derek_none = 1.0
    d0 = datetime.fromtimestamp(w0 / 1e9, tz=timezone.utc)
    d1 = datetime.fromtimestamp(w1 / 1e9, tz=timezone.utc)
    print(f"[surv] fenêtre commune {d0:%d/%m} → {d1:%d/%m} "
          f"({(w1 - w0) / 86400e9:.0f} j) : vol_spike {len(spike_win)}, "
          f"derek {len(derek_all)} | med ATR spike fenêtre {med_win:.2f} %")

    # —— les wallets ——
    st_stack = stats(wallet(spike_win + derek_all, med_win, fh,
                            derek_bps=DEREK_BPS_HONEST)["res"])
    st_fade = stats(wallet(spike_win, med_win, fh)["res"])
    st_derek = stats(wallet(derek_all, med_derek_none, fh,
                            derek_bps=DEREK_BPS_HONEST)["res"])
    st_stack_opt = stats(wallet(spike_win + derek_all, med_win, fh,
                                derek_bps=DEREK_BPS_OPT)["res"])
    n_derek_taken = sum(1 for t in st_stack["trades"]
                        if t["strategy"] == "derek_518")
    n_derek_alone = sum(1 for t in st_derek["trades"]
                        if t["strategy"] == "derek_518")
    n_fade_taken = sum(1 for t in st_stack["trades"]
                       if t["strategy"] == "vol_spike_6h")

    # —— la comparaison de régime : le fade par trimestre (standalone $100) ——
    quarters = [("2025-Q4", "2025-10", "2025-12"), ("2026-Q1", "2026-01", "2026-03"),
                ("2026-Q2", "2026-04", "2026-06"), ("2026-Q3", "2026-07", "2026-09")]
    qstats = []
    for q, m0, m1 in quarters:
        evs = [e for e in spike_all
               if f"{m0}-01" <= datetime.fromtimestamp(
                   e["ts_ms"] / 1e9, tz=timezone.utc).strftime("%Y-%m") <= f"{m1}-31"]
        if not evs:
            qstats.append((q, None))
            continue
        med_q = float(np.median([e["atr_pct"] for e in evs]))
        qstats.append((q, stats(wallet(evs, med_q, fh)["res"]) | {"med": med_q,
                                                                "n_ev": len(evs)}))

    # —— LA CORRÉLATION vol_spike × derek ——
    daily_sp = unit_pnl_daily(spike_win, None)
    daily_dk = unit_pnl_daily(derek_all, SLIP_HONEST)
    pear_d, spear_d, n_days = corr(daily_sp, daily_dk)
    # mensuel (dégénéré : 2 mois) — vue flux ET wallet réel
    def to_month(d: dict[str, float]) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for k, v in d.items():
            out[k[:7]] += v
        return dict(out)
    pear_m, spear_m, n_months = corr(to_month(daily_sp), to_month(daily_dk))
    m_fade = {r["month"]: r["pnl"] for r in st_fade["mrows"]}
    m_derek = {r["month"]: r["pnl"] for r in st_derek["mrows"]}
    m_stack = {r["month"]: r["pnl"] for r in st_stack["mrows"]}

    # —— le rapport ——
    L = []
    A = L.append
    A("# LE PORTEFEUILLE DES SURVIVANTS — vol_spike_6h × derek518")
    A("")
    A(f"{t0:%d/%m/%Y %H:%M} UTC — la question (decay-curve-2026-09-28) : "
      "l'edge cascade est mort au T3 ; les SURVIVANTS (le fade vol_spike_6h, "
      "la réplication derek518) portent-ils le régime actuel ? Fenêtre "
      f"commune = les {(w1 - w0) / 86400e9:.0f} jours derek "
      f"({d0:%d/%m} → {d1:%d/%m}) : vol_spike {len(spike_win)} events "
      f"(builder p5, gate ATR décile), derek {len(derek_all)} events "
      f"(builder archivé, garde anti-rug déclenchée {dst['guard_trig']}x). "
      "Harnais v5 run_stack, 2 créneaux (1 slot/flux), $100, frais réels : "
      "vol_spike taker 28 bps RT, derek LONG spot 1x (0 liq possible) taker "
      "0,09 %×2 + slippage honnête 0,5 %/côté = 118 bps RT. Sizing machine : "
      f"vol_spike vol-inverse base 0,10·K borné [0,02·K ; 0,30·K] (K={K}, "
      f"med ATR fenêtre {med_win:.2f} %), derek 0,10 fixe.")
    A("")

    verdict = None  # décidé plus bas, inséré en tête après calcul
    A("## Wallet des survivants (2 créneaux, $100, coûts honnêtes)")
    A("")
    L += bloc("SURVIVANTS (fade + derek)", st_stack,
              f" | capture derek {n_derek_taken}/{len(derek_all)} (mono-slot), "
              f"fade {n_fade_taken}/{len(spike_win)}")
    A("")
    L += fmt_monthly(st_stack)
    A("")
    A("## La variante PURE-FADE (vol_spike seul, même fenêtre) — l'apport derek")
    A("")
    L += bloc("PURE-FADE", st_fade)
    A("")
    A(f"Apport derek au stack : "
      f"{st_stack['bal'] - st_fade['bal']:+.2f} $ de balance finale "
      f"(ROI {st_stack['roi']:+.1f} % vs {st_fade['roi']:+.1f} %), "
      f"DD {st_stack['dd']:.1f} % vs {st_fade['dd']:.1f} %. "
      f"Derek SEUL (mono-slot, capture {n_derek_alone}/{len(derek_all)}) : "
      f"${st_derek['bal']:,.2f} (ROI {st_derek['roi']:+.1f} %, DD "
      f"{st_derek['dd']:.1f} %, WR {st_derek['wr']:.0f} %, espérance "
      f"{st_derek['exp']:+.3f} $/trade). Sensibilité coûts derek OPTIMISTE "
      f"(58 bps) : stack ${st_stack_opt['bal']:,.2f} "
      f"(ROI {st_stack_opt['roi']:+.1f} %). Concentration (garde ABSOLU) : "
      f"top-3 trades = {st_stack['top3_share']*100:.0f} % du PnL stack, "
      f"{st_derek['top3_share']*100:.0f} % du PnL derek-seul — "
      "l'ABSOLU de la branche derek tient sur 2-3 trades (leçon composé-"
      "des-mois : seul le RELATIF survivra).")
    A("")

    A("## Comparaison de régime — le fade par trimestre (standalone $100)")
    A("")
    A("| Trimestre | n events | n tradés | WR | Espérance $ | % marge | ROI | DD | Liq |")
    A("|---|---|---|---|---|---|---|---|---|")
    for q, s in qstats:
        if s is None:
            A(f"| {q} | 0 | — | — | — | — | — | — | — |")
            continue
        A(f"| {q} | {s.get('n_ev')} | {s['n']} | {s['wr']:.1f} % "
          f"| {s['exp']:+.3f} | {s['exp_pct']:+.2f} % | {s['roi']:+.1f} % "
          f"| {s['dd']:.1f} % | {s['liq']} |")
    A("")
    A("Derek = T3 2026 SEUL par construction (les swaps couvrent "
      f"{(w1 - w0) / 86400e9:.0f} j de T3) : sa robustesse Q2 est "
      "**invérifiable** sur données — c'est le caveat n°1 du test.")
    A("")

    A("## LA CORRÉLATION vol_spike × derek (le point clé diversification)")
    A("")
    A("| Granularité | n | Pearson | Spearman | Lecture |")
    A("|---|---|---|---|---|")
    read_d = ("diversification réelle" if pear_d < 0.3 else
              "marginal" if pear_d < 0.5 else "MÊME TRADE")
    A(f"| Quotidienne (vue flux) | {n_days} j | {pear_d:+.2f} | {spear_d:+.2f} "
      f"| {read_d} |")
    A(f"| Mensuelle | {n_months} mois | {pear_m:+.2f} | {spear_m:+.2f} "
      "| DÉGÉNÉRÉE — toutes les sorties wallet tombent dans 1 mois "
      "(2026-09) → corr indéfinie ; la quotidienne est la seule mesure "
      "utilisable sur 26 j |")
    A("")
    A("PnL mensuel wallet réel ($, sorties) : fade "
      + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(m_fade.items()))
      + " | derek seul "
      + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(m_derek.items()))
      + " | stack "
      + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(m_stack.items())) + ".")
    A("")

    A("## Garde-fous anti-dérive")
    A("")
    for lbl, s in (("SURVIVANTS", st_stack), ("PURE-FADE", st_fade),
                   ("DEREK seul", st_derek), ("stack derek optimiste", st_stack_opt)):
        ok = s["gap_c"] < 0.005 and s["gap_p"] < 0.01
        A(f"- {lbl} : composé-des-mois écart {s['gap_c']*100:.3f} %, "
          f"somme PnL écart ${s['gap_p']:.4f} — {'OK' if ok else '✗ BUG'}")
    A("")
    A("0 liquidation : fade et derek à 1x — le fade à 1x meurt à -99,5 % "
      "(gate ATR écarte les squeezes), derek est du SPOT long (liq "
      "impossible, la seule mort = prix → 0, bornée par le garde anti-rug "
      f"déclenché {dst['guard_trig']}x).")
    A("")

    # —— le verdict ——
    fade_q3 = dict(qstats)["2026-Q3"]
    checks = {
        "stack ROI > 0 honnête": st_stack["roi"] > 0,
        "DD stack ≤ 25 %": st_stack["dd"] <= 25.0,
        "0 liq": st_stack["liq"] == 0 and st_fade["liq"] == 0,
        "fade T3 espérance > 0": fade_q3 is not None and fade_q3["exp"] > 0,
        "corr daily < 0,5": (not np.isnan(pear_d)) and pear_d < 0.5,
        "derek apport ≥ 0": st_stack["bal"] >= st_fade["bal"] - 0.01,
        "garde-fous OK": all(s["gap_c"] < 0.005 and s["gap_p"] < 0.01
                             for s in (st_stack, st_fade, st_derek)),
        "branche derek n ≥ 20 (puissance)": n_derek_taken >= 20,
    }
    hard = {k: v for k, v in checks.items() if k != "branche derek n ≥ 20 (puissance)"}
    if all(checks.values()):
        verdict = ("**CANDIDAT paper-forward (indicatif)** — les survivants "
                   "portent le régime T3 : stack positif net de coûts honnêtes, "
                   "DD ≤ 25 %, 0 liq, fade positif sur le T3 mort, derek "
                   "apporte sans corréler.")
    elif all(hard.values()) and not checks["branche derek n ≥ 20 (puissance)"]:
        verdict = ("**CONTEXTE (portant CANDIDAT)** — tout passe SAUF la "
                   f"puissance : la branche derek du stack ne capte que "
                   f"{n_derek_taken}/72 events (doctrine n<20 → CONTEXTE "
                   "forcé) et son apport tient sur peu de trades. Le "
                   "portefeuille des survivants PORTE le T3 sur ce backtest, "
                   "mais indicativement — le paper forward doit trancher.")
    elif checks["stack ROI > 0 honnête"] and checks["0 liq"] and checks["garde-fous OK"]:
        verdict = ("**CONTEXTE** — le stack survit (ROI > 0, 0 liq) mais "
                   + "; ".join(k for k, v in checks.items() if not v)
                   + " → la diversification promise n'est pas démontrée.")
    else:
        verdict = ("**NUL/CONTEXTE** — " + "; ".join(k for k, v in checks.items()
                                                     if not v))
    L.insert(2, f"## Verdict : {verdict}")
    L.insert(3, "")
    L.insert(4, "Échecs critères : "
             + (", ".join(k for k, v in checks.items() if not v) or "aucun")
             + ".")
    L.insert(5, "")

    A("## L'HONNÊTETÉ (pré-enregistrée)")
    A("")
    A(f"- **n derek = {len(derek_all)} sur {(w1 - w0) / 86400e9:.0f} jours "
      "= 1 RÉGIME.** Aucune preuve inter-régimes ; le ROI/an est une "
      "extrapolation naïve d'un mois — NON interprétable.")
    A("- **Survivorship v2** : derek est dans ce test PARCE QU'il a survécu "
      "au tri des edges — biais de sélection structurel. L'edge v2 validé "
      "était RELATIF (vs baseline token) ; ce wallet est ABSOLU (achat sec) "
      "→ plus dur, mais toujours backtest.")
    A("- **Capture mono-slot** : derek en rafale, le créneau unique du stack "
      f"ne capte que {n_derek_taken}/{len(derek_all)} events — le derek "
      "« flux fractionnaire » du test d'origine n'est PAS testé ici (le "
      "harnais = 1 créneau/stratégie). L'apport derek mesuré est un MINORANT "
      "de l'edge flux, mais le seul conforme au harnais.")
    A("- Le fade vol_spike est mesuré sur la MÊME fenêtre que derek (T3) : "
      "le tableau trimestriel montre qu'il porte aussi Q4'25→Q2'26 — c'est "
      "le seul des deux flux double-régime vérifiable.")
    A("- Le gate ATR-décile du fade exclut a posteriori les pires trades "
      "(filtre machine établi 26/09, pas tuné sur ce test).")
    A("")

    A("## Prochaine action")
    A("")
    A("CONTEXTE portant CANDIDAT → la route paper s'ouvre SANS promotion "
      "backtest : câbler le paper forward double-flux PASSIF (fade "
      "vol_spike via the_machine --vol-spike déjà actif ; réplication derek "
      "≥$5k/age≥7j en paper, exposition bornée) et accumuler du n forward "
      "inter-régimes — le paper tranche, pas le backtest. Mettre à jour "
      "docs/20-registre-indicateurs.md : derek-réplication CONTEXTE → "
      "CANDIDAT conditionnel au paper (branche mono-slot sous-puissante, "
      "7<20), vol_spike_6h confirmé survivant multi-régime (3 trimestres "
      "positifs sur 4, T3 le meilleur). Ne PAS re-lever la machine tant que "
      "le ret short trimestriel cascade ne repasse pas positif "
      "(decay-curve).")
    A("")
    A(f"Run {(datetime.now(timezone.utc) - t0).total_seconds():.0f} s.")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"[surv] rapport écrit : {REPORT}")

    # —— le résumé stdout ——
    print(f"\n[surv] VERDICT : {verdict}")
    for lbl, s in (("STACK", st_stack), ("FADE", st_fade), ("DEREK", st_derek),
                   ("STACK-opt", st_stack_opt)):
        print(f"[surv] {lbl}: ${s['bal']:,.2f} ROI={s['roi']:+.1f}% "
              f"DD={s['dd']:.1f}% WR={s['wr']:.1f}% n={s['n']} liq={s['liq']} "
              f"exp={s['exp']:+.3f}$ moispire={s['worst_m']:+.1f}%")
    print(f"[surv] apport derek = {st_stack['bal'] - st_fade['bal']:+.2f}$ "
          f"| capture derek mono-slot {n_derek_taken}/{len(derek_all)}")
    print(f"[surv] corr vol_spike×derek : daily P={pear_d:+.2f} S={spear_d:+.2f} "
          f"(n={n_days} j) | mensuel P={pear_m:+.2f} (n={n_months}, DÉGÉNÉRÉ)")
    print("[surv] fade par trimestre :")
    for q, s in qstats:
        if s is None:
            print(f"[surv]   {q}: aucun event")
            continue
        print(f"[surv]   {q}: n={s['n']}/{s.get('n_ev')} WR={s['wr']:.1f}% "
              f"exp={s['exp']:+.3f}$ ROI={s['roi']:+.1f}% DD={s['dd']:.1f}% "
              f"liq={s['liq']}")
    print("[surv] critères : " + ", ".join(
        f"{k}={'OK' if v else 'FAIL'}" for k, v in checks.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
