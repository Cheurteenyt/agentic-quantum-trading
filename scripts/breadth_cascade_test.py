#!/usr/bin/env python
"""BREADTH TRANSVERSALE AUX ENTREES DE CASCADE (28/09/2026).

Thèse corr-tilt pré-enregistrée : systémique = ça continue, idiosyncratique
= ça rebondit. Le corr7 capte la corrélation ROULANTE 7j, pas la
SYNCHRONISATION INSTANTANÉE. Ici : la breadth ex-ante au moment de
l'entrée de chaque cascade majeurs — % des 6 majeures dont le retour 24h
est négatif (closes 1h ≤ entry, zéro look-ahead), + version 2 : nombre
des autres majeures dans leur propre drawdown ≥ 3 % sur 24h.

Hypothèse pré-enregistrée : breadth HAUT = short systémique = MEILLEUR
(continuation). Buckets fixes 0-33 / 33-66 / 66-100 %, TRAIN 70 % /
VAL 30 % PAR LE TEMPS. Si PASS : sizing x{0.75, 1.0, 1.25} par bucket
sur la machine 4 flux (--vol-spike ON), BLOC STATS vs baseline $4,004.94.

  .venv/bin/python scripts/breadth_cascade_test.py            # phase A
  .venv/bin/python scripts/breadth_cascade_test.py --machine  # + phase B
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
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"
K = 0.89                       # la calibration DD du machine (identique)
LEV = 10                       # cascade majors 10x
LIQ_MOVE = 100.0 / LEV - 0.5   # 9.5 %


def _monthly(rows: list[dict], capital: float) -> list[dict]:
    from scripts.portfolio_sim import monthly_rows
    return monthly_rows(rows, capital)


def compute_breadth(events: list[dict], majors_dfs: dict[str, pd.DataFrame],
                    fh: dict[str, float]) -> None:
    """Breadth ex-ante par event : closes 1h <= entry (barre bi-1),
    zéro look-ahead. ts_ms = des NS (nom hérité)."""
    idxs = {s: d.index.astype("datetime64[ns]").asi8 for s, d in majors_dfs.items()}
    closes = {s: d["close"].values for s, d in majors_dfs.items()}
    for e in events:
        neg = dd3 = valid = 0
        dd3_others = 0
        for s in majors_dfs:
            idx_ns, cl = idxs[s], closes[s]
            bi = int(np.searchsorted(idx_ns, e["ts_ms"], side="left"))
            # la barre bi-1 est la dernière clôturée à l'instant ts_ms
            if bi - 25 < 0 or bi - 1 >= len(cl):
                continue
            c_now, c_then = cl[bi - 1], cl[bi - 25]
            if not (np.isfinite(c_now) and np.isfinite(c_then)) or c_then <= 0:
                continue
            valid += 1
            if c_now < c_then:
                neg += 1
            dd24 = (c_now / max(cl[bi - 25:bi].max(), 1e-12) - 1) * 100
            if dd24 <= -3.0:
                dd3 += 1
                if s != e["sym"]:
                    dd3_others += 1
        e["breadth_pct"] = (neg / valid * 100) if valid >= 4 else np.nan
        e["breadth_dd3"] = float(dd3) if valid >= 4 else np.nan
        e["breadth_dd3_others"] = float(dd3_others) if valid >= 4 else np.nan
        # espérance % de marge à 10x (formules run_stack)
        ret = e["price_ret_short"]
        fund = fh.get(e["sym"], 0.0)
        e["exp_pct"] = (ret * LEV + fund / 100 * LEV * e["hold_h"]
                        - LEV * MAKER_RT / 1e4)
        e["liq10"] = e["mae_adverse"] >= LIQ_MOVE


def bucket(b: float) -> str:
    if not np.isfinite(b):
        return "nan"
    if b < 33:
        return "0-33"
    if b <= 66:
        return "33-66"
    return "66-100"


def bucket2(c: float) -> str:
    """Buckets en COMPTAGE (v2 = nb autres majeures en DD 24h >= 3 %)."""
    if not np.isfinite(c):
        return "nan"
    if c < 1:
        return "0"
    if c <= 2:
        return "1-2"
    return "3+"


def grad_map(events: list[dict], key: str, label: str,
             bk_fn=bucket, order=None) -> list[str]:
    order = order or ["0-33", "33-66", "66-100"]
    out = [f"\n### {label}", "",
           "| Split | Bucket | n | WR | MAE moy | MAE max | Liq(10x) | Esp. %marge/trade |",
           "|---|---|---|---|---|---|---|---|"]
    n_tr = int(len(events) * 0.7)
    for split, sub in (("TRAIN", events[:n_tr]), ("VAL", events[n_tr:])):
        for bk in order:
            g = [e for e in sub if bk_fn(e[key]) == bk]
            if not g:
                out.append(f"| {split} | {bk} | 0 | - | - | - | - | - |")
                continue
            wr = sum(1 for e in g if e["price_ret_short"] > 0) / len(g) * 100
            maes = [e["mae_adverse"] for e in g]
            liq = sum(1 for e in g if e["liq10"])
            exp = float(np.mean([e["exp_pct"] for e in g]))
            out.append(f"| {split} | {bk} | {len(g)} | {wr:.1f} % | "
                       f"{np.mean(maes):.2f} % | {max(maes):.2f} % | {liq} | "
                       f"{exp:+.2f} |")
    # honesty : les journées breadth 100 %
    full = [e for e in events if e[key] == 100.0]
    if full:
        wr = sum(1 for e in full if e["price_ret_short"] > 0) / len(full) * 100
        exp = float(np.mean([e["exp_pct"] for e in full]))
        out.append(f"- journées breadth = 100 % : n={len(full)}, WR {wr:.1f} %, "
                   f"espérance {exp:+.2f} %/marge (rare — à rapporter honnêtement)")
    return out


def phase_a() -> int:
    from scripts.portfolio_sim import MAJORS, btc_regime_series
    con = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"))
    fh = funding_hourly_all()
    regime = btc_regime_series()
    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = LEV
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(events)
    q66 = float(np.nanquantile(
        [e.get("al_score", float("nan"))
         for e in events[:int(len(events) * 0.7)]], 2 / 3))
    gated = [e for e in events
             if not (np.isfinite(e.get("al_score", float("nan")))
                     and e["al_score"] >= q66)]
    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    con.close()
    compute_breadth(gated, majors_dfs, fh)
    print(f"[breadth] events majors={len(events)}, gated (AL gate p66={q66:.2f}) "
          f"= {len(gated)}")

    lines = ["# BREADTH TRANSVERSALE AUX CASCADES MAJEURS (28/09/2026)", "",
             "Feature ex-ante : % des 6 majeures en retour 24h négatif aux",
             "entrées cascade (closes 1h ≤ entry, zéro look-ahead). Buckets",
             "fixes 0-33/33-66/66-100. TRAIN 70 % / VAL 30 % PAR LE TEMPS.",
             f"n gated = {len(gated)} (TRAIN {int(len(gated)*0.7)} / "
             f"VAL {len(gated) - int(len(gated)*0.7)}).", ""]

    # corr7 (réplique exacte du machine, _WIN=168)
    _rets = {s: d["close"].pct_change().values for s, d in majors_dfs.items()}
    _idx = majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    _WIN = 168
    for e in gated:
        bi = int(np.searchsorted(_idx, e["ts_ms"], side="left"))
        lo = bi - _WIN
        if lo < 0:
            e["corr"] = np.nan
            continue
        pairs = []
        ms = list(MAJORS)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                a, b = _rets[ms[i]][lo:bi], _rets[ms[j]][lo:bi]
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() > 100:
                    sa, sb = a[m] - np.mean(a[m]), b[m] - np.mean(b[m])
                    if np.std(sa) * np.std(sb) > 0:
                        pairs.append(np.mean(sa * sb) / (np.std(sa) * np.std(sb)))
        e["corr"] = float(np.mean(pairs)) if pairs else np.nan
    n_tr = int(len(gated) * 0.7)
    _c_hi = float(np.nanquantile([e["corr"] for e in gated[:n_tr]], 0.66))
    _c_lo = float(np.nanquantile([e["corr"] for e in gated[:n_tr]], 0.33))
    for e in gated:
        c = e["corr"]
        e["corr7_t"] = ("hi" if np.isfinite(c) and c > _c_hi else
                        "lo" if np.isfinite(c) and c < _c_lo else "mid")

    lines += grad_map(gated, "breadth_pct", "GRADIENT breadth % (ret 24h négatif)")
    lines += grad_map(gated, "breadth_dd3_others",
                      "GRADIENT v2 : nb autres majeures en DD 24h ≥ 3 %",
                      bk_fn=bucket2, order=["0", "1-2", "3+"])

    # diagnostic : breadth et corr7 sont-ils la même info ?
    bp = np.array([e["breadth_pct"] for e in gated if np.isfinite(e["breadth_pct"])
                   and np.isfinite(e.get("corr", np.nan))])
    cc = np.array([e["corr"] for e in gated if np.isfinite(e["breadth_pct"])
                   and np.isfinite(e.get("corr", np.nan))])
    if len(bp) > 10 and np.std(bp) > 0 and np.std(cc) > 0:
        r_bc = float(np.corrcoef(bp, cc)[0, 1])
        lines.append(f"\n- corrélation breadth % vs corr7 : r={r_bc:+.2f} "
                     f"(proche de 0 = info distincte)")

    # complémentarité corr7 x breadth
    lines += ["", "## COMPLÉMENTARITÉ corr7 (terciles TRAIN) x breadth", "",
              "| Split | corr7 | breadth | n | WR | Esp. %marge |", "|---|---|---|---|---|---|"]
    for split, sub in (("TRAIN", gated[:n_tr]), ("VAL", gated[n_tr:])):
        for ct in ("lo", "mid", "hi"):
            for bk in ("0-33", "33-66", "66-100"):
                g = [e for e in sub if e["corr7_t"] == ct and bucket(e["breadth_pct"]) == bk]
                if not g:
                    continue
                wr = sum(1 for e in g if e["price_ret_short"] > 0) / len(g) * 100
                exp = float(np.mean([e["exp_pct"] for e in g]))
                lines.append(f"| {split} | {ct} | {bk} | {len(g)} | {wr:.1f} % | {exp:+.2f} |")

    # le résiduel : corr7 similaire, breadth différente (hi vs lo bucket, même tercile corr)
    lines += ["", "### Le test du résiduel (même tercile corr7, breadth 66-100 vs 0-33)", ""]
    for split, sub in (("TRAIN", gated[:n_tr]), ("VAL", gated[n_tr:])):
        for ct in ("lo", "mid", "hi"):
            g_hi = [e for e in sub if e["corr7_t"] == ct and bucket(e["breadth_pct"]) == "66-100"]
            g_lo = [e for e in sub if e["corr7_t"] == ct and bucket(e["breadth_pct"]) == "0-33"]
            if g_hi and g_lo:
                d = np.mean([e["exp_pct"] for e in g_hi]) - np.mean([e["exp_pct"] for e in g_lo])
                lines.append(f"- {split} corr7={ct} : écart espérance hi-lo breadth "
                             f"= {d:+.2f} %/marge (n_hi {len(g_hi)} / n_lo {len(g_lo)})")

    verdict = ""
    for key, lab, bfn, blo, bhi in (
            ("breadth_pct", "breadth %", bucket, "0-33", "66-100"),
            ("breadth_dd3_others", "dd3", bucket2, "0", "3+")):
        lo_tr = [e for e in gated[:n_tr] if bfn(e[key]) == blo]
        hi_tr = [e for e in gated[:n_tr] if bfn(e[key]) == bhi]
        lo_va = [e for e in gated[n_tr:] if bfn(e[key]) == blo]
        hi_va = [e for e in gated[n_tr:] if bfn(e[key]) == bhi]
        if lo_tr and hi_tr and lo_va and hi_va:
            d_tr = np.mean([e["exp_pct"] for e in hi_tr]) - np.mean([e["exp_pct"] for e in lo_tr])
            d_va = np.mean([e["exp_pct"] for e in hi_va]) - np.mean([e["exp_pct"] for e in lo_va])
            ok = d_tr > 0 and d_va > 0
            verdict += (f"{lab} : Δespérance hi-lo TRAIN {d_tr:+.2f}, VAL {d_va:+.2f} "
                        f"→ {'COHÉRENT' if ok else 'INCOHÉRENT'}; ")
    lines += ["", f"## VERDICT PHASE A : {verdict or 'n insuffisant'}", ""]
    out = REPORTS / "breadth-cascade-2026-09-28.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-8:]))
    print(f"[breadth] rapport : {out}")
    return 0 if "COHÉRENT" in verdict else 1


def phase_b(factor_lo: float, factor_hi: float, factor_mid: float = 1.0,
            verbose: bool = False) -> tuple[dict, list]:
    """Machine 4 flux --vol-spike ON, sizing breadth x{lo,1.0,hi} sur flux 1."""
    from scripts.p5_frequency_test import collect_vol_spike  # noqa: E402
    from scripts.portfolio_sim import MAJORS, btc_regime_series
    from scripts.the_machine import collect_meme

    con = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"))
    fh = funding_hourly_all()
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    regime = btc_regime_series()

    events = collect_featured(regime, "majors")
    for e in events:
        e["strategy"] = "cascade_10x"
        e["lev"] = LEV
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
            pos = int(np.searchsorted(np.array(ft[0]), e["ts_ms"], side="right")) - 1
            if pos < 0:
                continue
            if s == e["sym"]:
                own = ft[1][pos]
            ranks.append(ft[1][pos])
        e["fund_rank"] = (float(np.mean(np.array(ranks) <= own))
                          if ranks and np.isfinite(own) else np.nan)

    majors_dfs = {s: load_df(con, s) for s in MAJORS}
    _rets = {s: d["close"].pct_change().values for s, d in majors_dfs.items()}
    _idx = majors_dfs["BTCUSDT"].index.astype("datetime64[ns]").asi8
    _WIN = 168
    for e in gated:
        bi = int(np.searchsorted(_idx, e["ts_ms"], side="left"))
        lo = bi - _WIN
        if lo < 0:
            e["corr"] = np.nan
            continue
        pairs = []
        ms = list(MAJORS)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                a, b = _rets[ms[i]][lo:bi], _rets[ms[j]][lo:bi]
                m = np.isfinite(a) & np.isfinite(b)
                if m.sum() > 100:
                    sa, sb = a[m] - np.mean(a[m]), b[m] - np.mean(b[m])
                    if np.std(sa) * np.std(sb) > 0:
                        pairs.append(np.mean(sa * sb) / (np.std(sa) * np.std(sb)))
        e["corr"] = float(np.mean(pairs)) if pairs else np.nan
    compute_breadth(gated, majors_dfs, fh)   # breadth ex-ante

    meme = collect_meme(con)
    con.close()
    med_meme = float(np.median([e["atr_pct"] for e in meme]))
    for e in meme:
        e["lev"] = 1
    surv = collect_arsenal(con2 := sqlite3.connect(
        str(ROOT / "data" / "warehouse" / "klines.db")), fh_raw).get(
        "survivor_long_72h", [])
    con2.close()
    _p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= _p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    con3 = sqlite3.connect(str(ROOT / "data" / "warehouse" / "klines.db"))
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
            b = e.get("breadth_pct", np.nan)
            if np.isfinite(b):
                s0 = min(s0 * (factor_hi if b > 66 else factor_lo
                               if b < 33 else factor_mid), 0.50 * K)
            return s0
        if s == "cascade_meme":
            return min(max(0.10 * K * (e["atr_pct"] / med_meme), 0.02 * K), 0.30 * K)
        if s == "vol_spike_6h":
            return min(max(0.10 * K * (e["atr_pct"] / med_spike), 0.02 * K), 0.30 * K)
        return 0.20 * K

    all_ev = sorted(gated + meme + surv + spike, key=lambda e: e["ts_ms"])
    r = run_stack(all_ev, CAPITAL, machine_fn, fh)
    mr = _monthly(r["trades"], CAPITAL)
    rois_m = [x["roi"] for x in mr]
    neg = sum(1 for x in rois_m if x < 0)
    prod = float(np.prod([1 + x["roi"] / 100 for x in mr]))
    gap_c = abs(prod - r["balance"] / CAPITAL)
    sum_pnl = sum(x["pnl"] for x in mr)
    gap_p = abs(sum_pnl - (r["balance"] - CAPITAL))
    print(f"[machine breadth x{factor_lo}/x{factor_mid}/x{factor_hi}] "
          f"${CAPITAL:,.0f} → ${r['balance']:,.2f} "
          f"({(r['balance'] / CAPITAL - 1) * 100:+.0f} %/an), "
          f"DD {r['max_dd']:.1f} %, liq {r['n_liq']}, {r['n']} trades, "
          f"pire mois {min(rois_m):+.1f} %, record {max(rois_m):+.1f} %, "
          f"{neg} mois négatifs | garde-fous : composé {gap_c*100:.3f} %, "
          f"PnL ${gap_p:.4f}")
    if verbose:
        for x in mr:
            print(f"  | {x['month']} | {x['n']} | "
                  f"{x['w']/max(x['n'],1)*100:.0f} % | {x['liq']} | "
                  f"${x['start']:,.0f} → ${x['end']:,.0f} | {x['roi']:+.1f} % |")
    return r, mr


def main() -> int:
    rc = phase_a()
    if "--machine" in sys.argv:
        # baseline réplique (facteur 1) puis le sizing breadth pré-enregistré
        phase_b(1.0, 1.0)
        phase_b(0.75, 1.25, verbose=True)
    if "--sens" in sys.argv:
        # sensibilité : l'ordre observé sur TRAIN (mid = meilleur bucket)
        phase_b(0.75, 1.0, factor_mid=1.25, verbose=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
