#!/usr/bin/env python
"""L'ARSENAL 2 — les flux funding/crash/momentum/contagion, à leur horizon.

Complète le full_arsenal (les 4 signaux de prix) avec les stratégies
créées qui dépendent d'autres dimensions :
  - funding_prix_divergence +12h (définition exacte v5 : accel + prix -3%/24h)
  - funding_extreme_contre_courant +168h (rate > p90 expanding)
  - crash_accel_short +24h (2 bougies ≤ -2σ sur les majeures)
  - survivor_momentum_long +72h (coin >90j au-dessus de son prix-90j)
  - contagion_long/short +4h (BTC ±2 %/1h → alt même sens)

Chacun : MAE max → levier mécanique 100/(maxMAE+0,5), sizing vol-inverse,
wallet seul — puis combiné avec la cascade (le noyau).

  .venv/bin/python scripts/full_arsenal_2.py
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

from scripts.backtest_indicators import load_df  # noqa: E402
from scripts.paper_forward import funding_div_mask  # noqa: E402
from scripts.portfolio_sim import (  # noqa: E402
    KDB, MAINT_PCT, MAJORS, btc_regime_series, lev_capped, liq_params,
    monthly_rows)
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)

REPORTS = ROOT / "reports"


def _atr_pct(df: pd.DataFrame) -> np.ndarray:
    """ATR de Wilder en % du prix, par bougie (calcul indépendant)."""
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    atr = np.empty(len(c))
    atr[0] = h[0] - l[0]
    for i in range(1, len(c)):
        tr = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        atr[i] = (atr[i - 1] * 13 + tr) / 14
    return atr / c * 100


# ⚠️ FIX audit v3 (C11) — caveat documenté : la sélection des flux viables
# est FULL-SAMPLE (les gagnants historiques) — le portefeuille combiné
# n'est PAS un résultat OOS. Générateur d'hypothèses, jamais une preuve
# de robustesse. Au runtime (forward), la sélection est causale.

def collect(con: sqlite3.Connection, fh: pd.DataFrame) -> dict[str, list[dict]]:
    streams: dict[str, list[dict]] = {}
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' ORDER BY symbol")]
    btc = load_df(con, "BTCUSDT")
    btc_ns = btc.index.astype("datetime64[ns]").asi8

    def push(name: str, sym: str, idx_ns, ei: int, entry: float, exit_j: int,
             direction: int, highs, lows, closes, hold: int, maker: bool,
             atr_pct: float):
        x = closes[exit_j]
        if direction > 0:
            ret_field = -(entry - x) / entry * 100
            mae = (entry - lows[ei:exit_j + 1].min()) / entry * 100
        else:
            ret_field = (entry - x) / entry * 100
            mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
        streams.setdefault(name, []).append({
            "sym": sym, "ts_ms": int(idx_ns[ei]), "strategy": name,
            "lev": 1, "hold_h": hold, "fee_rt_bps": MAKER_RT if maker else TAKER_RT,
            "entry": entry, "exit": float(x), "price_ret_short": ret_field,
            "fund_sign": -1 if direction > 0 else 1,
            # PR-171 (P1 chasse sources) : max(mae, 0) — l'ancien abs()
            # transformait une excursion FAVORABLE (le low ne descend
            # jamais sous l'entrée pour un long) en MAE adverse : un
            # trade GAGNANT pouvait être liquidé par run_stack (latent
            # aujourd'hui, s'activera sur les meilleurs trades). Même
            # pattern que p5_frequency_test.py:196
            "mae_adverse": max(mae, 0.0),
            "atr_pct": float(atr_pct),
        })

    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        close_s = pd.Series(closes, index=df.index)
        atr_pct = _atr_pct(df)
        r1 = close_s.pct_change() * 100
        sd = r1.rolling(168).std()

        # 1. funding_prix_divergence +12h (exact v5)
        fh_sym = fh[fh.symbol == sym]
        if not fh_sym.empty and len(fh_sym) > 30:
            mask = funding_div_mask(df, fh_sym)
            for t in np.where(mask)[0]:
                ei, hold = t + 1, 12
                if ei + hold >= len(idx_ns) or t < 300:
                    continue
                if opens[ei] <= 0:
                    continue
                push("funding_div_12h", sym, idx_ns, ei, opens[ei],
                     ei + hold - 1, -1, highs, lows, closes, hold, False, float(atr_pct[t]))

        # 2. crash_accel_short +24h (majeures : 2 bougies ≤ -2σ)
        if sym in MAJORS:
            crash = (r1 <= -2 * sd) & (r1.shift(1) <= -2 * sd.shift(1))
            for t in np.where(crash.fillna(False))[0]:
                ei, hold = t + 1, 24
                if ei + hold >= len(idx_ns) or t < 300:
                    continue
                if opens[ei] <= 0:
                    continue
                push("crash_accel_24h", sym, idx_ns, ei, opens[ei],
                     ei + hold - 1, -1, highs, lows, closes, hold, True, float(atr_pct[t]))

        # 3. survivor_momentum_long +72h (âge > 90j, prix > prix-90j)
        if sym not in MAJORS:
            age = (idx_ns - idx_ns[0]) / (86400 * 10**9)
            px90 = close_s.shift(90 * 24)
            mom = (age > 90) & (close_s > px90)
            for t in np.where(mom.fillna(False))[0][::24]:   # 1/jour max
                ei, hold = t + 1, 72
                if ei + hold >= len(idx_ns) or t < 300:
                    continue
                if opens[ei] <= 0:
                    continue
                push("survivor_long_72h", sym, idx_ns, ei, opens[ei],
                     ei + hold - 1, +1, highs, lows, closes, hold, False, float(atr_pct[t]))

        # 4. contagion +4h (BTC ±2 %/1h → alt même sens ; hors BTC)
        if sym not in MAJORS:
            # FIX audit v3 (C7) : join as-of — le dernier rendement BTC CONNU
            # à l'instant t ; np.interp mélangeait le rendement FUTUR.
            _btc_pct = btc["close"].pct_change().values * 100
            _pos_b = np.searchsorted(btc_ns, idx_ns, side="right") - 1
            _val = np.where(
                _pos_b >= 0,
                _btc_pct[np.clip(_pos_b, 0, len(_btc_pct) - 1)], np.nan)
            btc_r = pd.Series(_val, index=df.index)
            up = (btc_r >= 2)
            dn = (btc_r <= -2)
            for t in np.where(up | dn)[0]:
                ei, hold = t + 1, 4
                if ei + hold >= len(idx_ns) or t < 300:
                    continue
                if opens[ei] <= 0:
                    continue
                d = 1 if up.iloc[t] else -1
                push("contagion_4h", sym, idx_ns, ei, opens[ei],
                     ei + hold - 1, d, highs, lows, closes, hold, False, float(atr_pct[t]))

    # 5. funding_extreme_contre_courant +168h (rate > p90 expanding)
    for sym in symbols:
        fh_sym = fh[fh.symbol == sym]
        if len(fh_sym) < 40:
            continue
        rate = fh_sym["rate"].astype(float)
        p90 = rate.expanding(min_periods=30).quantile(0.9)
        df = load_df(con, sym)
        if df is None:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens = df["open"].values
        highs = df["high"].values
        closes = df["close"].values
        # PR-171 (P2) : lows DANS CETTE portée — l'ancien push lisait le
        # lows de la boucle précédente (NameError si aucun symbole ne
        # passait le filtre, lectures croisées sinon)
        lows = df["low"].values
        ts_ms = fh_sym["funding_time"].astype(float).values
        keep = (rate > p90).fillna(False).values
        taken = 0
        for t_ms, k in zip(ts_ms, keep):
            if not k or taken >= 40:
                continue
            ei = int(np.searchsorted(idx_ns, np.int64(t_ms * 10**6),
                                     side="right"))
            hold = 168
            if ei + hold >= len(idx_ns) or ei < 1:
                continue
            if opens[ei] <= 0:
                continue
            push("funding_extreme_168h", sym, idx_ns, ei, opens[ei],
                 ei + hold - 1, -1, highs, lows, closes, hold, False,
                 float(_atr_pct(df)[ei]))
            taken += 1
    for name in streams:
        streams[name].sort(key=lambda e: e["ts_ms"])
    return streams


def main() -> int:
    con = sqlite3.connect(KDB, timeout=60)
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    fh = funding_hourly_all()
    streams = collect(con, fh_raw)
    con.close()

    lines = [
        "# L'ARSENAL 2 — les flux funding/crash/momentum/contagion",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — horizons validés "
        f"propres, levier mécanique 100/(maxMAE+0,5), sizing vol-inverse.", "",
        "| Flux | N | WR | MAE max | Lev sûr | 100 $ → | ROI/an | DD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    viable: dict[str, list[dict]] = {}
    for name, ev in sorted(streams.items()):
        maes = np.array([e["mae_adverse"] for e in ev])
        mae_max = float(maes.max())
        # FIX F-038 — la marge de maintenance du SMOYEN de sécurité est le
        # maintMarginPercent RÉEL du symbole, pas 0,5 %. Sur les majeures
        # (2,5 %) la règle lev ≤ 100/(MAE+0,5) autorisait 10x alors que la
        # ligne de mort réelle est plus proche : le MAE observée DÉPASSAIT
        # la borne. Le levier par stream est plafonné par symbole.
        med = float(np.median([e.get("atr_pct", 2.0) or 2.0 for e in ev]))
        for e in ev:
            mm = liq_params().get(e["sym"], (MAINT_PCT, 0.0))[0]
            lev = max(1, int(100 / (mae_max + mm)))
            e["lev"] = lev_capped(e["sym"], lev)
            e["atr_ref"] = med
        def fn(e, st=None, med=med):
            a = e.get("atr_pct")
            if not a or not np.isfinite(a):
                a = med
            return min(max(0.20 * (a / med), 0.05, 0.02), 0.40)
        r = run_stack(ev, CAPITAL, fn, fh)
        wr = r["n_wins"] / max(r["n"], 1) * 100
        roi = (r["balance"] / CAPITAL - 1) * 100
        keep = roi > 5 and r["n"] >= 30
        if keep:
            viable[name] = ev
        lines.append(f"| {name} | {r['n']} | {wr:.1f} % | {mae_max:.1f} % | "
                     f"{lev}x | ${r['balance']:,.2f} | {roi:+.0f} % | "
                     f"{r['max_dd']:.1f} % |{'' if keep else ' ✗ fermé'}")

    # le combiné : cascade (le noyau) + les flux viables
    regime = btc_regime_series()
    from scripts.anti_liq import add_rolling_scores, collect_featured
    cascade = collect_featured(regime, "majors")
    for e in cascade:
        e["strategy"] = "cascade"
        e["lev"] = lev_capped(e["sym"], 10)   # FIX F-038 : 10x sur majeures
                                         # (max_leverage 20) mais la LIGNE DE
                                         # MORT est à 7,5 %, pas 9,5 %
        e["hold_h"] = 24
        e["fee_rt_bps"] = MAKER_RT
    add_rolling_scores(cascade)
    q66 = float(np.nanquantile(
        [e["al_score"] for e in cascade[:int(len(cascade) * 0.7)]], 2/3))
    casc = [e for e in cascade
            if not (np.isfinite(e.get("al_score", float("nan")))
                    and e["al_score"] >= q66)]
    con = sqlite3.connect(KDB, timeout=60)
    for e in sum(viable.values(), []):
        if e["strategy"] in ("funding_div_12h", "funding_extreme_168h",
                             "contagion_4h"):
            e["fee_rt_bps"] = TAKER_RT
    con.close()
    core = run_stack(casc, CAPITAL, lambda e: 0.30, fh)
    comb_ev = sorted(casc + sum(viable.values(), []), key=lambda e: e["ts_ms"])

    def combined_fn(e, st=None):
        if e["strategy"] == "cascade":
            return 0.30
        return 0.10
    r_comb = run_stack(comb_ev, CAPITAL, combined_fn, fh)
    roi_c = (r_comb["balance"] / CAPITAL - 1) * 100
    roi_core = (core["balance"] / CAPITAL - 1) * 100
    lines += ["", "## LE COMBINÉ — cascade 10x (30 %) + flux viables (10 %)", "",
              f"- cascade seule : ${core['balance']:,.2f} ({roi_core:+.0f} %/an, "
              f"DD {core['max_dd']:.1f} %, liq {core['n_liq']})",
              f"- combiné : ${r_comb['balance']:,.2f} ({roi_c:+.0f} %/an, "
              f"DD {r_comb['max_dd']:.1f} %, liq {r_comb['n_liq']})",
              f"- effet : {r_comb['balance'] - core['balance']:+,.2f} $ — "
              f"{'ADOPTÉ' if roi_c > roi_core else 'REFUSÉ (le noyau seul reste le roi)'}"]

    out = REPORTS / f"full-arsenal-2-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[arsenal-2] noyau ${core['balance']:,.2f} ({roi_core:+.0f} %/an) | "
          f"combiné ${r_comb['balance']:,.2f} ({roi_c:+.0f} %/an, "
          f"DD {r_comb['max_dd']:.1f} %, liq {r_comb['n_liq']})")
    print(f"[arsenal-2] effet combiné : {r_comb['balance'] - core['balance']:+,.2f} $")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
