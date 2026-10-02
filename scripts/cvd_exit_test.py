#!/usr/bin/env python
"""L'EXIT INFORMÉ PAR LE FLUX — le CVD pendant la détention (28/09/2026).

Mécanisme pré-enregistré : un short cascade perd quand le prix bounce —
le bounce commence par le RETOUR DE LA PRESSION D'ACHAT (le taker buy
ratio remonte) AVANT que le prix ne parte. Un exit CVD pourrait couper
les pires trades 4-8h avant leur pire MAE, sans le coût du trailing
prix (qui coupe tout).

Corpus : la construction EXACTE des tests précédents
(scripts/breadth_cascade_test.py) — collect_featured majors → AL gate
p66 (TRAIN 70 %) → 165 gated (TRAIN 115 / VAL 50), hold 24h.
Feature de détention : à chaque heure h ∈ {2,4,8,12}, buy_ratio moyen
des 2 dernières bougies 1h clôturées (closes t+h-1, t+h) vs buy_ratio
des 2 bougies PRÉ-entrée (closes t-2h, t-1h) → le delta. Flag :
delta > seuil (choisi sur TRAIN uniquement, jugé sur VAL).
buy_ratio = taker_buy_volume / volume (klines.db 1h, couverture 100 %).

PASS = le flag identifie les trades qui finissent PIRE : Δespérance
(% marge, 10x) flag vs non-flag ≤ -1.0 pt sur TRAIN ET VAL.
SI PASS : règle « flag à h → sortir à la close suivante » sur la
machine 4 flux (--vol-spike ON) vs baseline $4,004.94 — BLOC STATS.
Le coût mesuré : les trades flaggés qui auraient fini gagnants.

  .venv/bin/python scripts/cvd_exit_test.py
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
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"
K = 0.89
LEV = 10
LIQ_MOVE = 100.0 / LEV - 0.5        # 9.5 %
HOURS = (2, 4, 8, 12)
MAX_HOLD = 24


# ---------------------------------------------------------------- corpus
def build_gated() -> tuple[list[dict], sqlite3.Connection]:
    """La construction EXACTE de breadth_cascade_test.phase_a."""
    from scripts.portfolio_sim import btc_regime_series
    con = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"), timeout=60)
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = LEV
        e["hold_h"] = MAX_HOLD
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    n_tr0 = int(len(events) * 0.7)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan")) for e in events[:n_tr0]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    print(f"[cvd-exit] events majors={len(events)}, gated (AL p66={q66:.2f}) "
          f"= {len(gated)}")
    return gated, con


class Bars:
    """Klines 1h + buy_ratio (taker_buy_volume/volume) par majeure."""

    def __init__(self, con: sqlite3.Connection, symbols: list[str]):
        self.dfs, self.idxs, self.br = {}, {}, {}
        for s in symbols:
            df = load_df(con, s)
            if df is None:
                continue
            rows = con.execute(
                "SELECT open_time, taker_buy_volume, volume FROM klines "
                "WHERE symbol=? AND interval='1h' ORDER BY open_time",
                (s,)).fetchall()
            tb = pd.DataFrame(rows, columns=["ts", "tbv", "vol"]).drop_duplicates("ts")
            tb = tb.set_index(pd.to_datetime(tb["ts"], unit="ms")).sort_index()
            ratio = pd.to_numeric(tb["tbv"]) / pd.to_numeric(tb["vol"]).clip(lower=1e-12)
            self.dfs[s] = df
            self.idxs[s] = df.index.astype("datetime64[ns]").asi8
            self.br[s] = ratio.reindex(df.index).to_numpy(float)

    def attach(self, events: list[dict]) -> None:
        """delta_h, ret_h, subs_mae_h, subs_ret_h par event (zéro look-ahead)."""
        for e in events:
            s = e["sym"]
            if s not in self.dfs:
                continue
            idx = self.idxs[s]
            ei = int(np.searchsorted(idx, e["ts_ms"], side="left"))
            if ei < 2 or ei + MAX_HOLD > len(idx):
                continue
            br = self.br[s]
            pre = br[ei - 2:ei]
            if not np.all(np.isfinite(pre)):
                continue
            entry = e["entry"]
            closes = self.dfs[s]["close"].values
            highs = self.dfs[s]["high"].values
            e["_ei"] = ei
            e["pre_br"] = float(np.mean(pre))
            for h in HOURS:
                det = br[ei + h - 2:ei + h]        # closes t+h-1, t+h
                ok = bool(np.all(np.isfinite(det)))
                e[f"delta_{h}"] = float(np.mean(det) - e["pre_br"]) if ok else np.nan
                e[f"ret_{h}"] = (entry - closes[ei + h - 1]) / entry * 100
                e[f"subs_mae_{h}"] = (highs[ei + h:ei + MAX_HOLD].max()
                                      - entry) / entry * 100
                e[f"subs_ret_{h}"] = e["price_ret_short"] - e[f"ret_{h}"]


# ---------------------------------------------------------------- phase A
def exp_pct(e: dict, fh: dict[str, float]) -> float:
    """Espérance % de marge à 10x, hold 24h (formules breadth)."""
    return (e["price_ret_short"] * LEV
            + fh.get(e["sym"], 0.0) / 100 * LEV * MAX_HOLD
            - LEV * MAKER_RT / 1e4)


def grad_split(events: list[dict], h: int, thr: float | None,
               fh: dict[str, float]) -> list[str]:
    out = []
    if thr is None:
        out += ["| Split | Groupe | n | WR | ret24 moy | subs-ret moy | "
                "subs-MAE moy | Esp. %marge |", "|---|---|---|---|---|---|---|---|"]
    else:
        out += [f"| Split | Groupe (delta_{h} > {thr:.3f}) | n | WR | ret24 moy | "
                "subs-ret moy | subs-MAE moy | Esp. %marge |",
                "|---|---|---|---|---|---|---|---|"]
    n_tr = int(len(events) * 0.7)
    for split, sub in (("TRAIN", events[:n_tr]), ("VAL", events[n_tr:])):
        for name, grp in _groups(sub, h, thr):
            if not grp:
                out.append(f"| {split} | {name} | 0 | - | - | - | - | - |")
                continue
            wr = sum(1 for e in grp if e["price_ret_short"] > 0) / len(grp) * 100
            r24 = float(np.mean([e["price_ret_short"] for e in grp]))
            sr = float(np.nanmean([e[f"subs_ret_{h}"] for e in grp]))
            sm = float(np.nanmean([e[f"subs_mae_{h}"] for e in grp]))
            ex = float(np.mean([e["exp"] for e in grp]))
            out.append(f"| {split} | {name} | {len(grp)} | {wr:.1f} % | "
                       f"{r24:+.2f} % | {sr:+.2f} % | {sm:.2f} % | {ex:+.2f} |")
    return out


def _groups(events: list[dict], h: int, thr: float | None):
    if thr is None:
        fin = [e for e in events if np.isfinite(e.get(f"delta_{h}", float("nan")))]
        med = float(np.nanmedian([e[f"delta_{h}"] for e in fin])) if fin else 0.0
        return [("delta>med", [e for e in fin if e[f"delta_{h}"] > med]),
                ("delta<=med", [e for e in fin if e[f"delta_{h}"] <= med])]
    return [("FLAG", [e for e in events if np.isfinite(e.get(f"delta_{h}", float("nan")))
                      and e[f"delta_{h}"] > thr]),
            ("non-flag", [e for e in events if not (
                np.isfinite(e.get(f"delta_{h}", float("nan")))
                and e[f"delta_{h}"] > thr)])]


def pick_threshold(events: list[dict], h: int, fh: dict[str, float]
                   ) -> tuple[float, dict]:
    """Seuil choisi sur TRAIN uniquement : Δespérance flag - non-flag."""
    n_tr = int(len(events) * 0.7)
    tr = events[:n_tr]
    deltas = np.array([e[f"delta_{h}"] for e in tr
                       if np.isfinite(e.get(f"delta_{h}", float("nan")))])
    grid = sorted(set(list(np.nanquantile(deltas, [0.5, 0.6, 0.7, 0.8, 0.9]))
                      + [0.02, 0.05, 0.10, 0.15, 0.25]))
    best = None
    for thr in grid:
        fl = [e for e in tr if np.isfinite(e.get(f"delta_{h}", float("nan")))
              and e[f"delta_{h}"] > thr]
        nf = [e for e in tr if not (np.isfinite(e.get(f"delta_{h}", float("nan")))
                                    and e[f"delta_{h}"] > thr)]
        if len(fl) < 8 or len(nf) < 8:
            continue
        gap = float(np.mean([e["exp"] for e in fl]) - np.mean([e["exp"] for e in nf]))
        cand = (gap, thr, len(fl))
        if best is None or gap < best[0]:
            best = cand
    if best is None:
        return float("nan"), {"ok": False}
    gap, thr, nfl = best
    fl_va = [e for e in events[n_tr:] if np.isfinite(e.get(f"delta_{h}", float("nan")))
             and e[f"delta_{h}"] > thr]
    nf_va = [e for e in events[n_tr:] if not (
        np.isfinite(e.get(f"delta_{h}", float("nan"))) and e[f"delta_{h}"] > thr)]
    gap_va = (float(np.mean([e["exp"] for e in fl_va])
                    - np.mean([e["exp"] for e in nf_va]))
              if fl_va and nf_va else float("nan"))
    return thr, {"ok": True, "gap_tr": gap, "n_flag_tr": nfl,
                 "gap_va": gap_va, "n_flag_va": len(fl_va)}


def rank_corr(events: list[dict], h: int) -> dict:
    out = {}
    n_tr = int(len(events) * 0.7)
    for split, sub in (("TRAIN", events[:n_tr]), ("VAL", events[n_tr:])):
        d = np.array([e[f"delta_{h}"] for e in sub
                      if np.isfinite(e.get(f"delta_{h}", float("nan")))])
        r = np.array([e["price_ret_short"] for e in sub
                      if np.isfinite(e.get(f"delta_{h}", float("nan")))])
        out[split] = float(np.corrcoef(np.argsort(np.argsort(d)),
                                       np.argsort(np.argsort(r)))[0, 1]) if len(d) > 10 else np.nan
    return out


# ---------------------------------------------------------------- phase B
def cvd_exit_transform(events: list[dict], bars: Bars, h: int, thr: float
                       ) -> tuple[list[dict], dict]:
    """« flag à h → sortir à la close suivante » : exit au close de la
    bougie qui clôture à t+h+1 (barre ei+h). Les non-flaggardés gardent 24h."""
    out, stats = [], {"n_flag": 0, "cut_winners": 0, "forgone_ret": [],
                      "n_liq_before": 0}
    for e in events:
        if not (np.isfinite(e.get(f"delta_{h}", float("nan")))
                and e[f"delta_{h}"] > thr and "_ei" in e):
            out.append(dict(e))
            continue
        s = e["sym"]
        ei = e["_ei"]
        exit_j = ei + h                      # close à t+h+1
        closes = bars.dfs[s]["close"].values
        highs = bars.dfs[s]["high"].values
        idx = bars.idxs[s]
        if exit_j >= len(idx):
            out.append(dict(e))
            continue
        entry = e["entry"]
        mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
        ne = dict(e)
        ne["exit"] = float(closes[exit_j])
        ne["hold_h"] = h + 1
        ne["price_ret_short"] = (entry - ne["exit"]) / entry * 100
        ne["mae_adverse"] = mae
        if mae >= LIQ_MOVE:
            ne["liq_ts_ms"] = next((int(idx[j]) for j in range(ei, exit_j + 1)
                                    if highs[j] >= entry * (1 + LIQ_MOVE / 100)),
                                   e.get("liq_ts_ms"))
            stats["n_liq_before"] += 1
        stats["n_flag"] += 1
        if e["price_ret_short"] > 0:
            stats["cut_winners"] += 1
            stats["forgone_ret"].append(e["price_ret_short"] - ne["price_ret_short"])
        out.append(ne)
    out.sort(key=lambda x: x["ts_ms"])
    return out, stats


def build_machine(cascade_events: list[dict], verbose: bool = False
                  ) -> tuple[dict, list]:
    """Machine 4 flux --vol-spike ON (réplique breadth phase_b, facteurs 1.0)."""
    from scripts.full_arsenal_2 import collect as collect_arsenal
    from scripts.p5_frequency_test import collect_vol_spike
    from scripts.portfolio_sim import MAJORS, monthly_rows
    from scripts.the_machine import collect_meme

    con = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"), timeout=60)
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
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
    for e in cascade_events:
        ranks, own = [], np.nan
        for s in MAJORS:
            ft = funding_ts.get(s)
            if not ft or len(ft[0]) < 5:
                continue
            pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"], side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = ft[1][pos]
            ranks.append(ft[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)
    med_majors = float(np.median([e["atr_pct"] for e in cascade_events]))

    meme = collect_meme(con)
    con.close()
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = 1
    con2 = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"), timeout=60)
    surv = collect_arsenal(con2, fh_raw).get("survivor_long_72h", [])
    con2.close()
    _p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= _p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    con3 = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"), timeout=60)
    spike = collect_vol_spike(con3, hold=6)
    con3.close()
    for e in spike:
        e["strategy"] = "vol_spike_6h"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    med_spike = float(np.median([e["atr_pct"] for e in spike]))

    def machine_fn(e, st=None):
        s = e.get("strategy")
        if s == "cascade_10x":
            s0 = min(max(0.24 * K * (e["atr_pct"] / med_majors), 0.08 * K), 0.40 * K)
            if (np.isfinite(e.get("fund_rank", np.nan))
                    and e["fund_rank"] <= 0.33):
                s0 = min(s0 * 1.5, 0.50 * K)
            return min(s0, 0.50 * K)
        if s == "cascade_meme":
            return min(max(0.10 * K * (e["atr_pct"] / med_meme), 0.02 * K), 0.30 * K)
        if s == "vol_spike_6h":
            return min(max(0.10 * K * (e["atr_pct"] / med_spike), 0.02 * K), 0.30 * K)
        return 0.20 * K

    all_ev = sorted(cascade_events + meme + surv + spike, key=lambda e: e["ts_ms"])
    r = run_stack(all_ev, CAPITAL, machine_fn, fh)
    mr = monthly_rows(r["trades"], CAPITAL)
    return r, mr


def bloc_stats(label: str, r: dict, mr: list[dict]) -> list[str]:
    rois_m = [x["roi"] for x in mr]
    neg = sum(1 for x in rois_m if x < 0)
    prod = float(np.prod([1 + x["roi"] / 100 for x in mr]))
    gap_c = abs(prod - r["balance"] / CAPITAL)
    gap_p = abs(sum(x["pnl"] for x in mr) - (r["balance"] - CAPITAL))
    wr = sum(1 for t in r["trades"] if t["pnl"] > 0) / max(r["n"], 1) * 100
    return [f"### {label}", "",
            "| Stat | Valeur |", "|---|---|",
            f"| Wallet 100 $ → | **${r['balance']:,.2f}** "
            f"(ROI/an {(r['balance'] / CAPITAL - 1) * 100:+.0f} %) |",
            f"| Max DD | {r['max_dd']:.1f} % |",
            f"| Trades / liq / WR | {r['n']} / {r['n_liq']} / {wr:.1f} % |",
            f"| Mois négatifs | {neg} (pire {min(rois_m):+.1f} %) |",
            f"| Record mois | {max(rois_m):+.1f} % |",
            f"| Garde-fous | composé {gap_c * 100:.3f} %, PnL ${gap_p:.4f} |", ""]


# ---------------------------------------------------------------- main
def main() -> int:
    from scripts.portfolio_sim import MAJORS
    fh = funding_hourly_all()
    gated, con = build_gated()
    bars = Bars(con, list(MAJORS))
    bars.attach(gated)
    con.close()
    for e in gated:
        e["exp"] = exp_pct(e, fh)
    n_tr = int(len(gated) * 0.7)
    missing = [e for e in gated if "_ei" not in e]
    print(f"[cvd-exit] features attachées, sans données={len(missing)}")

    lines = ["# L'EXIT INFORMÉ PAR LE FLUX — CVD pendant la détention "
             "(28/09/2026)", "",
             "Mécanisme pré-enregistré : le bounce d'un short cascade commence",
             "par le retour de la pression d'achat (taker buy ratio remonte)",
             "AVANT que le prix ne parte. Flag = delta buy_ratio (2 bougies de",
             "détention vs 2 pré-entrée) > seuil TRAIN. Corpus = construction",
             "exacte breadth : 230 majors → 165 gated AL p66 (TRAIN 115 / VAL",
             "50), hold 24h. buy_ratio = taker_buy_volume/volume (1h, 100 %).",
             ""]
    verdicts = {}
    for h in HOURS:
        rc = rank_corr(gated, h)
        lines += [f"## Gradient map — flag à h={h}h", ""]
        lines += grad_split(gated, h, None, fh)
        thr, res = pick_threshold(gated, h, fh)
        if not res.get("ok"):
            lines += [f"\nSeuil TRAIN : aucun candidat (n flag < 8).", ""]
            continue
        lines += [f"\nSeuil TRAIN retenu : delta_{h} > {thr:.3f} "
                  f"(flag TRAIN n={res['n_flag_tr']}, VAL n={res['n_flag_va']})", ""]
        lines += grad_split(gated, h, thr, fh)
        lines += [f"\n- spearman(delta_{h}, ret24) : TRAIN {rc['TRAIN']:+.2f}, "
                  f"VAL {rc['VAL']:+.2f}",
                  f"- Δespérance (flag - non-flag) : TRAIN {res['gap_tr']:+.2f} pt, "
                  f"VAL {res['gap_va']:+.2f} pt"]
        ok = (res["gap_tr"] <= -1.0 and np.isfinite(res["gap_va"])
              and res["gap_va"] <= -1.0)
        verdicts[h] = (thr, res, ok)
        lines += [f"- VERDICT h={h}h : {'PASS' if ok else 'FAIL'} "
                  f"(critère Δesp ≤ -1.0 pt TRAIN ET VAL)", ""]
    passing = [h for h in HOURS if verdicts.get(h, (0, 0, False))[2]]
    if passing:
        h_best = min(passing, key=lambda h: verdicts[h][1]["gap_va"])
        thr_best = verdicts[h_best][0]
        lines += ["## PHASE B — « flag → sortir à la close suivante » sur la "
                  f"machine 4 flux (h={h_best}h, thr={thr_best:.3f})", ""]

        r_base, mr_base = build_machine([dict(e) for e in gated])
        lines += bloc_stats("BASELINE (exit 24h fixes, réplique $4,004.94)",
                            r_base, mr_base)
        # exit CVD
        transformed, st = cvd_exit_transform(gated, bars, h_best, thr_best)
        r_cvd, mr_cvd = build_machine(transformed)
        lines += bloc_stats(f"EXIT CVD (flag {h_best}h → close suivante)",
                            r_cvd, mr_cvd)
        fg = float(np.mean(st["forgone_ret"])) if st["forgone_ret"] else 0.0
        kept = (r_cvd["balance"] >= r_base["balance"]
                and r_cvd["max_dd"] <= 25.0 and r_cvd["n_liq"] == 0)
        verdict_b = ("EXIT CVD RETENU (ROI >= baseline, DD <= 25 %, 0 liq)"
                     if kept else "EXIT CVD NE PASSE PAS LA MACHINE")
        lines += [
            f"- Trades flaggés : {st['n_flag']}, sortis gagnants (coût) : "
            f"{st['cut_winners']}, ret prix moyen abandonné par gagnant coupé : "
            f"{fg:+.2f} %, liqs déjà déclenchés avant exit : "
            f"{st['n_liq_before']}.",
            f"- Δ wallet vs baseline : ${r_cvd['balance'] - r_base['balance']:+,.2f} "
            f"({(r_cvd['balance'] / r_base['balance'] - 1) * 100:+.1f} %).",
            "",
            f"## VERDICT PHASE B : {verdict_b}",
            ""]
    else:
        lines += ["## PHASE B : NON LANCÉE — aucun horizon PASS en phase A.", ""]
    if verdicts:
        v = " | ".join(
            f"h={h}:{'PASS' if verdicts[h][2] else 'FAIL'}" for h in HOURS
            if h in verdicts)
        lines += [f"## VERDICT GLOBAL : {v}", ""]
    out = REPORTS / "cvd-exit-2026-09-28.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-6:]))
    print(f"[cvd-exit] rapport : {out}")
    return 0 if passing else 1


if __name__ == "__main__":
    raise SystemExit(main())
