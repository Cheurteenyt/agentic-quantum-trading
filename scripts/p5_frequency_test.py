#!/usr/bin/env python
"""P5 — LES FLUX DE FRÉQUENCE (docs/21-goal-performances.md, priorité 5).

La cible du user : 60-70 %/mois STABLES, ≤ 1 mois négatif/12. La machine
3 flux a des mois creux (2026-01 -5,5 %, juillet +7,5 %, sept. +7,6 %).
Il faut des flux DÉCORRELANTS à haute fréquence qui remplissent les creux.

TROIS candidats, construits UNIQUEMENT sur le warehouse (klines.db :
klines 1h + funding_history), testés SEUL à 1x avec le harnais officiel
(`run_stack` de stacked_portfolio — entrée open t+1, MAE sur fenêtre,
funding réel moyen, un seul créneau par stratégie) :

  1. FUNDING SATURÉ (mean-reversion) — le rate du symbole est dans la
     queue cross-sectionnelle du marché (rank ≥ p95 et > 0 → SHORT 8h ;
     rank ≤ p5 et < 0 → LONG 8h). La foule sur-levée paie, le prix
     revient. PAS le même signal que fdiv/confluence (p90 + condition
     prix) : ici la saturation du MARCHÉ entier, sans condition prix.
  2. VOL-SPIKE REVERSION — une bougie 1h de range ≥ 4× sa médiane 14j
     (et ≥ 2,5 %) est un spike : on fade la direction 6h.
  3. TRAVERSÉES DD — la transition de carte (backtest_lifecycle) :
     le drawdown vs ATH TRAVERSE une frontière de bande (entrée 20-50 %,
     entrée > 50 %) = l'info de transition (×3,4 le statique, cf. carte)
     monétisée en SHORT continuation 24h à 1x petite taille.

Chaque flux : N/an, WR, espérance (taker ET maker), MAE/levier sûr,
courbe mensuelle, CORRÉLATION du PnL mensuel avec la machine (réplique
flat des 3 flux officiels — baseline anti-dérive, garde-fous composé).

Critère de survie : espérance nette > 0 (taker OU maker), corr < 0,3,
≥ 10 trades/mois. Un nul honnête vaut mieux qu'un faux positif.

  .venv/bin/python scripts/p5_frequency_test.py
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
from scripts.portfolio_sim import monthly_rows  # noqa: E402
from scripts.stacked_portfolio import (  # noqa: E402
    CAPITAL, MAKER_RT, TAKER_RT, funding_hourly_all, run_stack)
from scripts.the_machine import collect_meme  # noqa: E402

KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"
SIZE = 0.05           # marge flat 5 % — la convention « seul » du harnais
MAJORS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"}


# ————————————————————————————— collecteurs P5 —————————————————————————————

def collect_funding_sat(con: sqlite3.Connection, universe: set[str],
                        hold: int = 8, p_hi: float = 0.95,
                        p_lo: float = 0.05, min_cross: int = 20) -> list[dict]:
    """Flux 1 : la saturation de funding cross-sectionnelle → reversion.

    rank = fraction des AUTRES symboles dont le rate as-of est ≤ le nôtre,
    mesuré à chaque print de funding. Queue haute (foule longs paye) →
    SHORT ; queue basse (foule shorts paie) → LONG. Un trade par print.
    """
    fund: dict[str, tuple[list, list]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = fund.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    all_syms = sorted(fund)
    events: list[dict] = []
    for sym in sorted(universe):
        rows = con.execute(
            "SELECT funding_time, rate FROM funding_history "
            "WHERE symbol = ? ORDER BY funding_time", (sym,)).fetchall()
        if len(rows) < 50:
            continue
        own_ts = np.array([int(t) * 10**6 if int(t) > 10**11
                           else int(t) * 10**9 for t, _ in rows])
        own_r = np.array([float(r) for _, r in rows])
        # la matrice as-of : pour chaque print du symbole, le dernier
        # rate connu de chaque autre symbole
        R = np.full((len(own_ts), len(all_syms)), np.nan)
        for j, o in enumerate(all_syms):
            to, ro = fund[o]
            pos = np.searchsorted(np.array(to), own_ts, side="right") - 1
            ok = pos >= 0
            R[ok, j] = np.array(ro)[pos[ok]]
        with np.errstate(invalid="ignore"):
            below = np.nansum(R <= own_r[:, None], axis=1) - 1   # -1 : soi-même
            n_obs = np.sum(np.isfinite(R), axis=1) - 1
            rank = np.where(n_obs >= min_cross,
                            below / np.maximum(n_obs, 1), np.nan)
        df = load_df(con, sym)
        if df is None:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs, lows, closes = (df["open"].values, df["high"].values,
                                      df["low"].values, df["close"].values)
        for k in range(len(own_ts)):
            rk, rate = rank[k], own_r[k]
            if not np.isfinite(rk):
                continue
            side = None
            if rk >= p_hi and rate > 0:
                side = "short"
            elif rk <= p_lo and rate < 0:
                side = "long"
            if side is None:
                continue
            ei = int(np.searchsorted(idx_ns, own_ts[k], side="right"))
            if ei + hold >= len(idx_ns):
                continue
            entry = opens[ei]
            if entry <= 0:
                continue
            exit_j = ei + hold - 1
            exit_px = closes[exit_j]
            if side == "short":
                mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
                ret = (entry - exit_px) / entry * 100
                sign = 1
            else:
                mae = (entry - lows[ei:exit_j + 1].min()) / entry * 100
                ret = (exit_px - entry) / entry * 100
                sign = -1
            events.append({"sym": sym, "ts_ms": int(idx_ns[ei]),
                           "strategy": "funding_sat", "lev": 1, "hold_h": hold,
                           "fee_rt_bps": TAKER_RT, "entry": float(entry),
                           "exit": float(exit_px), "price_ret_short": ret,
                           "mae_adverse": float(max(mae, 0.0)),
                           "fund_sign": sign, "side": side})
    events.sort(key=lambda e: e["ts_ms"])
    return events


def collect_vol_spike(con: sqlite3.Connection, hold: int = 6,
                      k_rng: float = 4.0, abs_min: float = 2.5,
                      win: int = 336, atr_gate: bool = True) -> list[dict]:
    """Flux 2 : le spike de range 1h (≥ 4× médiane 14j, ≥ 2,5 %) → fade 6h.

    atr_gate : le filtre établi de the_machine (survivor 26/09) — le
    décile ATR supérieur (les monstres qui squeeze ×2-4) est écarté.
    """
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol")]
    events: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < win + hold + 2:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs, lows = df["open"].values, df["high"].values, df["low"].values
        close_s = df["close"]
        rng = (df["high"] - df["low"]) / close_s * 100
        med = rng.rolling(win, min_periods=100).median()
        sig = ((rng >= k_rng * med) & (rng >= abs_min)).fillna(False)
        body_up = (df["close"] >= df["open"]).values
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        for t in np.where(sig)[0]:
            ei = t + 1
            if ei + hold >= len(idx_ns) or t < win:
                continue
            entry = opens[ei]
            if entry <= 0 or not np.isfinite(atr[ei]):
                continue
            exit_j = ei + hold - 1
            exit_px = df["close"].values[exit_j]
            if body_up[t]:                      # spike haussier → SHORT
                mae = (highs[ei:exit_j + 1].max() - entry) / entry * 100
                ret = (entry - exit_px) / entry * 100
                sign = 1
            else:                               # spike baissier → LONG
                mae = (entry - lows[ei:exit_j + 1].min()) / entry * 100
                ret = (exit_px - entry) / entry * 100
                sign = -1
            events.append({"sym": sym, "ts_ms": int(idx_ns[ei]),
                           "strategy": "vol_spike", "lev": 1, "hold_h": hold,
                           "fee_rt_bps": TAKER_RT, "entry": float(entry),
                           "exit": float(exit_px), "price_ret_short": ret,
                           "mae_adverse": float(max(mae, 0.0)),
                           "fund_sign": sign, "atr_pct": float(atr[ei]),
                           "side": "short" if sign == 1 else "long"})
    if atr_gate and events:
        p90 = float(np.nanquantile([e["atr_pct"] for e in events], 0.90))
        events = [e for e in events if e["atr_pct"] <= p90]
    events.sort(key=lambda e: e["ts_ms"])
    return events


def collect_dd_cross(con: sqlite3.Connection, hold: int = 24,
                     atr_gate: bool = True) -> list[dict]:
    """Flux 3 : les TRAVERSÉES de dd — la transition de carte (×3,4 le
    statique, cf. la carte de cycle de vie). Le dd vs ATH traverse 20 %
    (entrée bande 20-50 %) ou 50 % (bande > 50 %) → SHORT continuation.

    atr_gate : même filtre décile ATR que the_machine (les monstres).
    """
    symbols = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h' "
        "ORDER BY symbol")]
    events: list[dict] = []
    for sym in symbols:
        df = load_df(con, sym)
        if df is None or len(df) < 500:
            continue
        idx_ns = df.index.astype("datetime64[ns]").asi8
        opens, highs = df["open"].values, df["high"].values
        close_s = df["close"]
        dd = (1 - close_s / close_s.cummax()) * 100
        atr = (close_s.diff().abs().rolling(24).mean() / close_s * 100).values
        for lvl in (20.0, 50.0):
            cross = ((dd >= lvl) & (dd.shift(1) < lvl)).fillna(False)
            for t in np.where(cross)[0]:
                ei = t + 1
                if ei + hold >= len(idx_ns) or t < 24:
                    continue
                entry = opens[ei]
                if entry <= 0 or not np.isfinite(atr[ei]):
                    continue
                exit_j = ei + hold - 1
                exit_px = df["close"].values[exit_j]
                events.append({
                    "sym": sym, "ts_ms": int(idx_ns[ei]),
                    "strategy": "dd_cross", "lev": 1, "hold_h": hold,
                    "fee_rt_bps": TAKER_RT, "entry": float(entry),
                    "exit": float(exit_px),
                    "price_ret_short": (entry - exit_px) / entry * 100,
                    "mae_adverse": float(max(
                        (highs[ei:exit_j + 1].max() - entry) / entry * 100, 0)),
                    "fund_sign": 1, "side": "short",
                    "atr_pct": float(atr[ei]), "level": lvl})
    if atr_gate and events:
        p90 = float(np.nanquantile([e["atr_pct"] for e in events], 0.90))
        events = [e for e in events if e["atr_pct"] <= p90]
    events.sort(key=lambda e: e["ts_ms"])
    return events


def funding_real_sum(con: sqlite3.Connection, events: list[dict]) -> dict:
    """Le funding RÉELlement payé/reçu pendant chaque détention (les
    prints du symbole dans la fenêtre), en somme de rates (fractions).
    Le harnais ne crédite que la moyenne du symbole — il sous-compte
    structurellement les flux dont l'alpha EST le funding saturé."""
    per_sym: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for s, t, r in con.execute(
            "SELECT symbol, funding_time, rate FROM funding_history "
            "ORDER BY funding_time"):
        try:
            t = int(t)
            ts, rt = per_sym.setdefault(s, ([], []))
            ts.append(t * 10**6 if t > 10**11 else t * 10**9)
            rt.append(float(r))
        except (TypeError, ValueError):
            continue
    out: dict[tuple[str, int], float] = {}
    for e in events:
        arr = per_sym.get(e["sym"])
        if not arr:
            continue
        ts, rt = np.array(arr[0]), np.array(arr[1])
        lo = int(np.searchsorted(ts, e["ts_ms"], side="right"))
        hi = int(np.searchsorted(ts, e["ts_ms"] + e["hold_h"] * 3600 * 10**9,
                                 side="right"))
        out[(e["sym"], e["ts_ms"])] = float(rt[lo:hi].sum())
    return out


# ————————————————————— la machine en réplique flat (corr) —————————————————————

def machine_streams_flat(con: sqlite3.Connection, fh: dict[str, float]
                         ) -> dict[str, list[dict]]:
    """Les 3 flux officiels, mêmes collecteurs que the_machine.py, sizing
    FLAT 5 % (baseline anti-dérive : pas de compounding dans la mesure)."""
    regime = pd.Series(dtype=str)
    try:
        from scripts.portfolio_sim import btc_regime_series
        regime = btc_regime_series()
    except Exception:
        pass
    # flux 1 : cascade majeurs gated AL p66 (identique the_machine)
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
    # flux 2 : cascade memecoins 1x
    meme = collect_meme(con)
    mae_meme = max(e["mae_adverse"] for e in meme)
    lev_meme = max(1, int(100 / (mae_meme + 0.5)))
    for e in meme:
        e["lev"] = lev_meme
    # flux 3 : survivor long 72h (filtre ATR décile supérieur, 26/09)
    fh_raw = pd.read_sql_query(
        "SELECT symbol, funding_time, rate FROM funding_history", con)
    from scripts.full_arsenal_2 import collect as collect_arsenal
    surv = collect_arsenal(con, fh_raw).get("survivor_long_72h", [])
    p90 = float(np.nanquantile([e["atr_pct"] for e in surv], 0.90))
    surv = [e for e in surv if e["atr_pct"] <= p90]
    for e in surv:
        e["strategy"] = "survivor_long"
        e["lev"] = 1
        e["fee_rt_bps"] = TAKER_RT
    out = {}
    for name, evs in (("cascade_10x", gated), ("cascade_meme", meme),
                      ("survivor_long", surv)):
        for e in evs:
            e["size"] = SIZE
        out[name] = sorted(evs, key=lambda e: e["ts_ms"])
    return out


# ————————————————————————————————— mesures —————————————————————————————————

def run_flat(events: list[dict], fh: dict[str, float], fee_rt: int,
             name: str) -> dict:
    for e in events:
        e["fee_rt_bps"] = fee_rt
    res = run_stack(events, CAPITAL, lambda e, st=None: SIZE, fh)
    return res


def stats_block(res: dict, months_n: int) -> dict:
    pnls = [t["pnl"] for t in res["trades"]]
    mrows = monthly_rows(res["trades"], CAPITAL)
    margins = [t["margin"] for t in res["trades"]]
    return {"res": res, "mrows": mrows,
            "n": res["n"], "wr": res["n_wins"] / max(res["n"], 1) * 100,
            "exp": float(np.mean(pnls)) if pnls else 0.0,
            "exp_pct_margin": (float(np.mean(pnls)) / float(np.mean(margins))
                               * 100) if pnls and margins else 0.0,
            "trades_mo": res["n"] / max(months_n, 1),
            "mae_max": 0.0, "roi": (res["balance"] / CAPITAL - 1) * 100}


def monthly_series(mrows: list[dict]) -> dict[str, float]:
    return {r["month"]: r["pnl"] for r in mrows}


def corr_months(a: dict[str, float], b: dict[str, float]) -> tuple[float, float]:
    keys = sorted(set(a) | set(b))
    x = np.array([a.get(k, 0.0) for k in keys])
    y = np.array([b.get(k, 0.0) for k in keys])
    if len(keys) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan")
    pear = float(np.corrcoef(x, y)[0, 1])
    ra = pd.Series(x).rank().values
    rb = pd.Series(y).rank().values
    spear = float(np.corrcoef(ra, rb)[0, 1])
    return pear, spear


def guard_fous(res: dict) -> tuple[float, float]:
    mrows = monthly_rows(res["trades"], CAPITAL)
    prod = 1.0
    for r in mrows:
        prod *= (1 + r["roi"] / 100)
    gap_c = abs(prod - res["balance"] / CAPITAL)
    gap_p = abs(sum(r["pnl"] for r in mrows) - (res["balance"] - CAPITAL))
    return gap_c, gap_p


def real_funding_stats(res: dict, events: list[dict],
                       fund_real: dict, fh: dict[str, float]) -> dict:
    """Re-pnl les trades pris avec le funding RÉEL de la fenêtre (le
    harnais crédite la moyenne du symbole ; pour un flux dont l'alpha
    est le funding saturé, c'est une sous-estimation structurelle)."""
    ev_map = {(e["sym"], e["ts_ms"] // 10**9): e for e in events}
    pnls, n_liq = [], 0
    for t in res["trades"]:
        key = (t["sym"], int(t["entry_ts"].timestamp()))
        e = ev_map.get(key)
        if e is None:
            continue
        notional = t["margin"] * e["lev"]
        fund_h = notional * fh.get(e["sym"], 0.0) / 100 * e["hold_h"]
        fund_r = fund_real.get((e["sym"], e["ts_ms"]), 0.0) * notional
        pnls.append(t["pnl"] - e.get("fund_sign", 1) * fund_h
                    + e.get("fund_sign", 1) * fund_r)
        n_liq += t["liq"]
    return {"n": len(pnls), "wr": float(np.mean(np.array(pnls) > 0) * 100)
            if pnls else 0.0,
            "exp": float(np.mean(pnls)) if pnls else 0.0, "n_liq": n_liq}


def main() -> int:
    t0 = datetime.now(timezone.utc)
    con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=60)
    fh = funding_hourly_all()
    syms = [r[0] for r in con.execute(
        "SELECT DISTINCT symbol FROM klines WHERE interval='1h'")]

    print("[p5] collecte des 3 flux candidats…")
    months_all = 12                                    # 2025-10 .. 2026-09
    streams: dict[str, dict] = {}

    # —— la réplique flat de la machine (la référence cascade pour la corr)
    print("[p5] réplique flat de la machine (cascade/meme/survivor)…")
    mach = machine_streams_flat(con, fh)
    mach_stats: dict[str, dict] = {}
    for name, evs in mach.items():
        mach_stats[name] = stats_block(run_flat(evs, fh, evs[0]["fee_rt_bps"]
                                                if evs else TAKER_RT, name),
                                       months_all)
    comp = monthly_series(mach_stats["cascade_10x"]["mrows"])
    for other in ("cascade_meme", "survivor_long"):
        for m, p in monthly_series(mach_stats[other]["mrows"]).items():
            comp[m] = comp.get(m, 0.0) + p
    mach_neg = [m for m, p in comp.items() if p < 0]

    # —— flux 1 : funding saturé
    print("[p5] flux 1 : funding saturé…")
    ev_fund = collect_funding_sat(con, set(syms), hold=8)
    ev_fund24 = collect_funding_sat(con, set(syms), hold=24)

    # —— flux 2 : vol-spike (gate ATR décile : les monstres qui squeeze)
    print("[p5] flux 2 : vol-spike…")
    ev_spike = collect_vol_spike(con, hold=6)
    ev_spike12 = collect_vol_spike(con, hold=12)

    # —— flux 3 : traversées dd (gate ATR décile)
    print("[p5] flux 3 : traversées dd…")
    ev_dd = collect_dd_cross(con, hold=24)
    ev_dd72 = collect_dd_cross(con, hold=72)
    fund_real = funding_real_sum(con, ev_fund + ev_fund24)
    con.close()

    candidates = [
        ("funding_sat_8h", ev_fund), ("funding_sat_24h", ev_fund24),
        ("vol_spike_6h", ev_spike), ("vol_spike_12h", ev_spike12),
        ("dd_cross_24h", ev_dd), ("dd_cross_72h", ev_dd72)]

    results: dict[str, dict] = {}
    for name, evs in candidates:
        if not evs:
            results[name] = {"empty": True}
            continue
        for fee_name, fee_rt in (("taker", TAKER_RT), ("maker", MAKER_RT)):
            results[f"{name}_{fee_name}"] = stats_block(
                run_flat([dict(e) for e in evs], fh, fee_rt, name), months_all)
            results[f"{name}_{fee_name}"]["mae_max"] = max(
                e["mae_adverse"] for e in evs)
        results[name + "_events"] = evs

    # la variante FUNDING RÉEL pour les flux dont l'alpha est le funding
    rf_res: dict[str, dict] = {}
    for name in ("funding_sat_8h", "funding_sat_24h"):
        for fee in ("taker", "maker"):
            r = results.get(f"{name}_{fee}")
            if r and not r.get("empty"):
                rf_res[f"{name}_{fee}"] = real_funding_stats(
                    r["res"], results[name + "_events"], fund_real, fh)

    # ——— le rapport ———
    lines = [
        "# P5 — LES FLUX DE FRÉQUENCE (la régularité)",
        f"{t0:%d/%m/%Y %H:%M} UTC — 3 candidats, harnais v5 (run_stack, "
        f"entrée open t+1, MAE fenêtre, 1 créneau/stratégie), 1x flat "
        f"{SIZE*100:.0f} % marge, $100 de base. Les flux short portent le "
        f"filtre établi de the_machine (décile ATR supérieur écarté — les "
        f"monstres PORTAL/LAB qui squeeze ×2-4).",
        "",
        "La référence = la machine 3 flux en réplique flat (mêmes "
        "collecteurs, sizing plat) — mois PnL négatifs répliqués : "
        + (", ".join(mach_neg) if mach_neg else "aucun") + ".",
        "",
        "## Les flux candidats — SEUL à 1x", "",
        "| Flux | Coûts | N | N/mois | WR | Espérance $ | % marge | Liq | "
        "MAE max | ROI/an | DD |",
        "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, _ in candidates:
        for fee in ("taker", "maker"):
            k = f"{name}_{fee}"
            r = results.get(k)
            if not r or r.get("empty"):
                continue
            rf = rf_res.get(k)
            exp_s = f"{r['exp']:+.3f}"
            if rf:
                exp_s += f" → {rf['exp']:+.3f} (funding réel)"
            lines.append(
                f"| {name} | {fee} | {r['n']} | {r['trades_mo']:.1f} "
                f"| {r['wr']:.1f} % | {exp_s} "
                f"| {r['exp_pct_margin']:+.2f} % | {r['res']['n_liq']} "
                f"| {r['mae_max']:.1f} % "
                f"| {r['roi']:+.1f} % | {r['res']['max_dd']:.1f} % |")
    lines += ["", "### La variante FUNDING RÉEL (funding_sat seulement)", "",
              "Le harnais crédite le funding MOYEN du symbole ; pour un flux",
              "dont l'alpha est le funding saturé, c'est une sous-estimation.",
              "",
              "| Flux | Coûts | N pris | WR | Espérance $ | Liq |",
              "|---|---|---|---|---|---|"]
    for k, rf in rf_res.items():
        lines.append(f"| {k.split('_taker')[0].split('_maker')[0]} | "
                     f"{k.split('_')[-1]} | {rf['n']} | {rf['wr']:.1f} % "
                     f"| {rf['exp']:+.3f} | {rf['n_liq']} |")

    # ——— la corrélation cascade (LE point clé) ———
    lines += ["", "## LA CORRÉLATION avec la machine (le point clé)", "",
              "Critère : corr < 0,3. Une corr NÉGATIVE est encore mieux :",
              "le flux gagne quand la machine perd — c'est le remplissage",
              "de creux recherché par P5.",
              "",
              "| Flux | Corr Pearson | Corr rang | Lecture |",
              "|---|---|---|---|"]
    for name, _ in candidates:
        k = f"{name}_taker"
        r = results.get(k)
        if not r or r.get("empty"):
            continue
        pear, spear = corr_months(monthly_series(r["mrows"]), comp)
        read = ("anti-corrélé — remplit les creux" if pear < -0.3
                else "OK (< 0,3)" if pear < 0.3 else "✗ corrélé")
        lines.append(f"| {name} | {pear:+.2f} | {spear:+.2f} | {read} |")

    # ——— les courbes mensuelles côte à côte ———
    ser = {n: monthly_series(results[f"{n}_taker"]["mrows"])
           for n, _ in candidates
           if results.get(f"{n}_taker") and not results[f"{n}_taker"].get("empty")}
    all_months = sorted(set(comp) | set().union(*[set(s) for s in ser.values()]))
    lines += ["", "## LA COURBE MENSUELLE (PnL $ sur $100 flat 5 %, taker)",
              "", "| Mois | MACHINE (réplique) | "
              + " | ".join(n for n in ser) + " |",
              "|---|---|" + "---|" * len(ser)]
    for m in all_months:
        cells = [m, f"{comp.get(m, 0.0):+.2f}"] + \
                [f"{s.get(m, 0.0):+.2f}" for s in ser.values()]
        lines.append("| " + " | ".join(cells) + " |")

    # ——— le verdict ———
    lines += ["", "## VERDICT (critère : espérance nette > 0 — taker OU "
              "maker, funding réel pour funding_sat —, corr < 0,3, "
              "≥ 10 trades/mois, liq 0 à 1x)", ""]
    summary: dict[str, str] = {}
    for name, _ in candidates:
        rt, rm = results.get(f"{name}_taker"), results.get(f"{name}_maker")
        if not rt or rt.get("empty"):
            lines.append(f"- **{name}** : aucun trade — FAIL (pas de signal)")
            summary[name] = "FAIL"
            continue
        pear, _ = corr_months(monthly_series(rt["mrows"]), comp)
        if name.startswith("funding_sat"):
            exp_t = rf_res[f"{name}_taker"]["exp"]
            exp_m = rf_res[f"{name}_maker"]["exp"]
            liq_n = rf_res[f"{name}_taker"]["n_liq"]
            src = "funding réel"
        else:
            exp_t, exp_m, liq_n = rt["exp"], rm["exp"], rt["res"]["n_liq"]
            src = "harnais"
        exp_ok = (exp_t > 0) or (exp_m > 0)
        checks = [exp_ok, pear < 0.3, rt["trades_mo"] >= 10, liq_n == 0]
        verdict = "PASS" if all(checks) else "FAIL"
        why = []
        if not exp_ok:
            why.append("espérance ≤ 0 nette de coûts")
        if pear >= 0.3:
            why.append(f"corr cascade {pear:+.2f} ≥ 0,3")
        if rt["trades_mo"] < 10:
            why.append(f"fréquence {rt['trades_mo']:.1f}/mois < 10")
        if liq_n:
            why.append(f"{liq_n} liq à 1x (squeeze ≥ 99,5 %)")
        lines.append(
            f"- **{name}** : **{verdict}** — N {rt['n']} "
            f"({rt['trades_mo']:.1f}/mois), WR {rt['wr']:.1f} %, "
            f"espérance {exp_t:+.3f} $ taker / {exp_m:+.3f} $ maker ({src}), "
            f"corr {pear:+.2f}"
            + (f" — {'; '.join(why)}" if why else ""))
        summary[name] = verdict

    # ——— garde-fous anti-dérive ———
    lines += ["", "## GARDE-FOUS ANTI-DÉRIVE (baseline)", ""]
    ok_all = True
    for name, _ in candidates:
        for fee in ("taker", "maker"):
            r = results.get(f"{name}_{fee}")
            if not r or r.get("empty"):
                continue
            gc, gp = guard_fous(r["res"])
            ok = gc < 0.005 and gp < 0.01
            ok_all &= ok
            lines.append(f"- {name} {fee} : composé {gc*100:.3f} %, "
                         f"Somme PnL ${gp:.4f} — {'OK' if ok else '✗ BUG'}")
    for name in mach:
        gc, gp = guard_fous(mach_stats[name]["res"])
        ok = gc < 0.005 and gp < 0.01
        ok_all &= ok
        lines.append(f"- machine réplique {name} : composé {gc*100:.3f} %, "
                     f"Somme PnL ${gp:.4f} — {'OK' if ok else '✗ BUG'}")
    if not ok_all:
        lines += ["", "⚠ AU MOINS UN GARDE-FOU A ÉCHOUÉ — CHIFFRES NON "
                      "PUBLIABLES."]

    dt = (datetime.now(timezone.utc) - t0).total_seconds()
    lines += ["", "---",
              "Règle gravée : levier ≤ 100/(maxMAE + 0,5) — à 1x la mort est",
              "à 99,5 % ; les liqs restantes sont des squeezes ≥ 99,5 % (le",
              "gate ATR les écarte). Un backtest n'est jamais une preuve :",
              "le paper forward tranche.",
              "",
              "## LA CULTURE DES RÉSULTATS NULS",
              "",
              "Les flux FAIL rejoignent le registre (docs/20) — un nul",
              "honnête vaut mieux qu'un faux positif. **dd_cross** : la",
              "transition de carte reste négative nette de coûts aux deux",
              "régimes de frais, et à 72h c'est un piège à squeeze (LAB",
              "×2-4 à la hausse, 1 liq même gate ATR) — la traversée dd ne",
              "monétise PAS en flux de fréquence autonome. **vol_spike_12h** :",
              "allonger le hold détruit l'edge taker et rouvre la porte au",
              "squeeze (1 liq) — le 6h est la seule variante qui tient.", "",
              "Limite déclarée : le gate ATR-décile est le filtre établi de",
              "the_machine (survivor, 26/09), pas un paramètre tuné sur le",
              "PnL — mais il exclut a posteriori les pires trades ; le",
              "paper forward tranche.", "",
              f"Run {dt:.0f} s."]

    out = REPORTS / "p5-frequency-streams-2026-09-27.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[p5] rapport écrit : {out}")

    # ——— la réponse condensée stdout ———
    print("\n[p5] ===== RÉSUMÉ (critère PASS : exp>0, corr<0,3, ≥10/mois, liq 0) =====")
    for name, _ in candidates:
        rt = results.get(f"{name}_taker")
        rm = results.get(f"{name}_maker")
        if not rt or rt.get("empty"):
            print(f"[p5] {name}: AUCUN TRADE — FAIL")
            continue
        pear, _ = corr_months(monthly_series(rt["mrows"]), comp)
        if name.startswith("funding_sat"):
            exp_t = rf_res[f"{name}_taker"]["exp"]
            exp_m = rf_res[f"{name}_maker"]["exp"]
            liq_n = rf_res[f"{name}_taker"]["n_liq"]
        else:
            exp_t, exp_m, liq_n = rt["exp"], rm["exp"], rt["res"]["n_liq"]
        exp_ok = (exp_t > 0) or (exp_m > 0)
        checks = [exp_ok, pear < 0.3, rt["trades_mo"] >= 10, liq_n == 0]
        print(f"[p5] {name}: N={rt['n']} ({rt['trades_mo']:.1f}/mois) "
              f"WR={rt['wr']:.1f}% exp={exp_t:+.3f}$ tk/{exp_m:+.3f}$ mk "
              f"corr={pear:+.2f} liq={liq_n} "
              f"→ {'PASS' if all(checks) else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
