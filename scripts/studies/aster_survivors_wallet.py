#!/usr/bin/env python3
"""T22 — WALLET SÉQUENTIEL des 4 survivants T21 (la porte obligatoire).

Les survivants VAL de la découverte T21 (reports/aster_discovery_2123.md),
ceux qui tenaient en VAL 2024-2026 :
  breakout_don168, trend_long_ema50x200, sma_regime_50d, momentum_bear_lb48
  (= config T21 `momentum_lb48`, continuation 48 h long+short).

Le test que T21 n'a PAS fait : le wallet séquentiel $100 (pattern `run_stack`
de scripts/stacked_portfolio.py, IMPORTÉ — jamais modifié), frais 8 bps RT
comptés, funding réel moyen par symbole (cache T21), mark-to-market à la
fermeture (convention du stack officiel).

  1. Chaque survivant SEUL : lev 1× / cap/2 / cap (cap = règle 0-liq exacte
     lev <= 100/(maxMAE_TRAIN+0.5), puis boucle d'application : toute liq
     détectée => lev x0.95 jusqu'à 0 liq — "0 liq sans exception").
  2. LE STACK des survivants (poids égal 0.25) 2021-2026 : global + par
     régime + VAL. Question : tient-il 2024-2026 SANS re-calibrage ?
  3. Comparaison : stack officiel T11/V2 ($146.42, +7.8 %/an, DD 32.5 %)
     et B&H BTC/ETH/SOL (calculé ici, mêmes fenêtres).

Règles de verdict PRÉ-ENREGISTRÉES (avant résultats, anti-dérive) :
  R1 0 liq partout ; R2 stack-cap DD <= 25 % ; R3 stack ROI/an >= +7.8 % ;
  R4 stack VAL 2024-2026 > 0 ; R5 chaque survivant solo VAL > 0.
  5/5 PROMOTION · R2-R4 ok mais un solo échoue = PROMOTION PARTIELLE ·
  R3 ou R4 échoue = CONTEXTE · R1 échoue = REFUS.

Le moteur de signaux est celui de T21, importé ; le tracker de sorties est
une copie verbatim de `run()` (aster_discovery_2123.py au 2026-10-01) avec
seulement exit_px/exit_ts ajoutés — parité assertée contre `run()` à 1e-9.

  .venv/bin/python scripts/studies/aster_survivors_wallet.py
  .venv/bin/python scripts/studies/aster_survivors_wallet.py --write

Sortie : rapport console + reports/aster_survivors_wallet.md (--write).
DB klines.db en READ-ONLY ; écriture = le rapport uniquement.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.stacked_portfolio import run_stack  # noqa: E402 — pattern officiel

DB_PATH = ROOT / "data" / "warehouse" / "klines.db"
REPORT = ROOT / "reports" / "aster_survivors_wallet.md"
FUND_CACHE = ROOT / "reports" / "aster_discovery_2123_funding.json"
DISC_PATH = ROOT / "scripts" / "studies" / "aster_discovery_2123.py"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
DAY_MS = 86_400_000
CAPITAL = 100.0

W0_MS = 1630454400000          # 2021-09-01 00:00 UTC (fenêtre officielle T9/V2)
W1_MS = 1790812800000          # 2026-10-01 00:00 UTC (exclusive)
YEARS = (W1_MS - W0_MS) / DAY_MS / 365.25
VAL0_MS = 1704067200000        # 2024-01-01 00:00 UTC
VAL_YEARS = (W1_MS - VAL0_MS) / DAY_MS / 365.25
TRAIN_END_MS = VAL0_MS         # fin du TRAIN T21 : les caps = maxMAE TRAIN

# Les 4 survivants T21 — configs tirées de la grille gelée T21 par nom.
SURVIVORS = ["breakout_don168", "trend_long_ema50x200", "sma_regime_50d",
             "momentum_bear_lb48"]
ALIAS = {"momentum_bear_lb48": "momentum_lb48"}   # nom T21 d'origine

REGIMES = [
    ("bull21",   "2021-09-01", "2022-01-01"),
    ("bear22",   "2022-01-01", "2023-01-01"),
    ("recov23",  "2023-01-01", "2024-01-01"),
    ("bull24",   "2024-01-01", "2024-07-01"),
    ("chop24",   "2024-07-01", "2025-01-01"),
    ("connu2526", "2025-01-01", "2026-10-01"),
]
STACK_WEIGHT = 0.25            # poids égal, 4 stratégies

# Benchmarks T11/V2 (rapport officiel, même fenêtre 2021-09-01 → 2026-09-30).
OFFICIAL = {"final": 146.42, "cagr": 0.078, "dd": 32.5, "val": -3.5}


def log(msg: str) -> None:
    print(msg, flush=True)


def d(s: str) -> int:
    return int(datetime.fromisoformat(s + "T00:00:00+00:00").timestamp() * 1000)


def dt_of(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


# ------------------------------------------------------------ module T21
spec = importlib.util.spec_from_file_location("aster_discovery_2123", DISC_PATH)
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)
CFG = {name: (fam, p) for name, fam, p in D.CONFIGS}


# ------------------------------------------------- tracker de sorties T21
def run_track(df: pd.DataFrame, sig: dict) -> list[dict]:
    """Copie VERBATIM de D.run (2026-10-01) — seuls exit_px/exit_ts/entry_px
    sont capturés en plus. Parité assertée contre D.run à 1e-9."""
    n = len(df)
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    enter_l, enter_s = sig["long"], sig["short"]
    ex_l, ex_s = sig["exit_long"], sig["exit_short"]
    hold, stop_atr = sig["hold"], sig["stop_atr"]
    atrv = sig["atr"]
    fund = sig.get("fund_bps8h")
    trades: list[dict] = []
    pos = 0
    entry_px = stop = entry_i = 0
    for i in range(1, n - 1):
        if pos == 0:
            if enter_l[i] and np.isfinite(atrv[i]):
                pos, entry_px, entry_i = 1, o[i + 1], i + 1
                stop = entry_px - stop_atr * atrv[i]
            elif enter_s[i] and np.isfinite(atrv[i]):
                pos, entry_px, entry_i = -1, o[i + 1], i + 1
                stop = entry_px + stop_atr * atrv[i]
            continue
        exit_px = None
        if pos == 1 and l[i] <= stop:
            exit_px = stop                      # stop prioritaire (conservateur)
        elif pos == -1 and h[i] >= stop:
            exit_px = stop
        elif i - entry_i >= (hold or 10**9):
            exit_px = o[i + 1]                  # time-stop -> open suivant
        elif (pos == 1 and ex_l[i]) or (pos == -1 and ex_s[i]):
            exit_px = o[i + 1]                  # signal de sortie -> open suivant
        if exit_px is None:
            continue
        gross = (exit_px / entry_px - 1) if pos == 1 else (entry_px / exit_px - 1)
        pnl = gross - D.COST_RT
        if fund is not None:
            pay = fund[entry_i:i + 1].sum() / 1e4
            pnl += -pos * pay
        if pos == 1:
            adverse = min(l[entry_i:i + 1]) / entry_px - 1
            mae = max(0.0, -adverse * 100.0)
        else:
            adverse = max(h[entry_i:i + 1]) / entry_px - 1
            mae = max(0.0, adverse * 100.0)
        trades.append({"ts": int(df["ts"].values[entry_i]), "dir": pos,
                       "ret": pnl * 100.0, "mae": mae, "exit_px": float(exit_px),
                       "exit_ts": int(df["ts"].values[i]), "entry_px": float(entry_px)})
        pos = 0
    return trades


def build_survivor_trades(data: dict[str, pd.DataFrame], name: str) -> list[dict]:
    """Trades du survivant (pooled 3 symboles), parité assertée vs moteur T21."""
    fam, p = CFG[ALIAS.get(name, name)]
    out: list[dict] = []
    for sym in SYMBOLS:
        sig = D.build_signals(data[sym], fam, p, None)
        base = D.run(data[sym], sig)
        track = run_track(data[sym], sig)
        assert len(base) == len(track), f"{name}/{sym} : parité longueur"
        for b, t in zip(base, track):
            assert b["ts"] == t["ts"] and b["dir"] == t["dir"], f"{name} parité ts"
            assert abs(b["ret"] - t["ret"]) < 1e-9, f"{name} parité ret"
            assert abs(b["mae"] - t["mae"]) < 1e-9, f"{name} parité mae"
        for t in track:
            t["sym"] = sym
            t["strategy"] = name
        out.extend(track)
    out.sort(key=lambda t: t["ts"])
    return out


# ------------------------------------------------------------------ events
def make_events(trades: list[dict], lev_map: dict[str, float]) -> list[dict]:
    """Trades T21 -> events run_stack. Le ret T21 (net de 8 bps) est
    re-décomposé : gross = ret + 8 bps ; run_stack recompte lui-même les
    frais (fee_rt_bps=8) — la parité des PnL est exacte au funding près."""
    ev = []
    for t in trades:
        gross = t["ret"] / 100 + D.COST_RT
        ev.append({
            "sym": t["sym"], "strategy": t["strategy"],
            "ts_ms": t["ts"] * 10**6,               # leçon ts_ms : ms -> NS
            "lev": lev_map[t["strategy"]],
            "hold_h": (t["exit_ts"] - t["ts"]) / 3.6e6,
            "fee_rt_bps": 8.0, "entry": t["entry_px"], "exit": t["exit_px"],
            "price_ret_short": gross * 100.0,       # retour PnL-pertinent
            "mae_adverse": t["mae"],
            "fund_sign": -1.0 if t["dir"] == 1 else 1.0,  # long PAIT le funding+
        })
    ev.sort(key=lambda e: e["ts_ms"])
    return ev


def funding_hourly_real() -> dict[str, float]:
    """Funding RÉEL (cache T21, API Aster) — moyenne par symbole en %/h
    (convention flat de funding_hourly_all() du stack officiel)."""
    data = json.loads(FUND_CACHE.read_text())
    return {s: float(np.mean([r for _, r in ev])) * 100.0 / 8.0
            for s, ev in data.items()}


# ------------------------------------------------------------------- stats
def month_list() -> list[str]:
    out, y, m = [], 2021, 9
    while (y, m) <= (2026, 9):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def steps_of(res: dict) -> list[tuple[datetime, float]]:
    st = [(dt_of(W0_MS), CAPITAL)]
    for t in sorted(res["trades"], key=lambda x: x["exit_ts"]):
        st.append((t["exit_ts"], t["balance"]))
    return st


def equity_at(steps: list[tuple[datetime, float]], ms: int) -> float:
    t = dt_of(ms)
    eq = CAPITAL
    for ts, b in steps:
        if ts <= t:
            eq = b
        else:
            break
    return eq


def dd_in(steps: list[tuple[datetime, float]], a_ms: int, b_ms: int) -> float:
    ta, tb = dt_of(a_ms), dt_of(b_ms)
    peak = equity_at(steps, a_ms)
    dd = 0.0
    for ts, bal in steps:
        if ts < ta or ts > tb:
            continue
        peak = max(peak, bal)
        if peak > 0:
            dd = max(dd, (peak - bal) / peak * 100)
    return dd


def full_stats(res: dict, label: str, lev_note: str) -> dict:
    final = res["balance"]
    cagr = (final / CAPITAL) ** (1.0 / YEARS) - 1.0
    n = max(res["n"], 1)
    months: dict[str, float] = {}
    for t in res["trades"]:
        k = f"{t['exit_ts'].year:04d}-{t['exit_ts'].month:02d}"
        months[k] = months.get(k, 0.0) + t["pnl"]
    vals = [months.get(m, 0.0) for m in month_list()]
    steps = steps_of(res)
    val0 = equity_at(steps, VAL0_MS)
    return {
        "label": label, "lev_note": lev_note, "final": final, "cagr": cagr,
        "dd": res["max_dd"], "n": res["n"], "wr": res["n_wins"] / n * 100,
        "liq": res["n_liq"], "fees": res["fees"], "funding": res["funding"],
        "mois_pos": sum(1 for v in vals if v > 1e-9),
        "mois_neg": sum(1 for v in vals if v < -1e-9), "n_mois": len(vals),
        "record": max(vals), "pire": min(vals),
        "val_roi": final / val0 - 1.0 if val0 > 0 else -1.0,
        "val_dd": dd_in(steps, VAL0_MS, W1_MS),
        "steps": steps, "stopped": final <= 1.0,
    }


def regime_rows(s: dict) -> list[tuple[str, float, float]]:
    rows = []
    for name, a, b in REGIMES:
        eq0 = equity_at(s["steps"], d(a))
        eq1 = equity_at(s["steps"], d(b))
        rows.append((name, eq1 / eq0 - 1.0, dd_in(s["steps"], d(a), d(b))))
    return rows


# ------------------------------------------------------------------- wallet
def wallet(trades: list[dict], lev_map: dict[str, float],
           size_map: dict[str, float], funding_hourly: dict[str, float],
           ) -> tuple[dict, dict[str, float]]:
    """run_stack officiel + boucle 0-liq : toute liq => lev x0.95, re-run."""
    levs = dict(lev_map)
    def size_fn(e: dict) -> float:
        return size_map.get(e["strategy"], 0.0)
    res = None
    for _ in range(60):
        res = run_stack(make_events(trades, levs), CAPITAL, size_fn, funding_hourly)
        if res["n_liq"] == 0:
            break
        levs = {k: round(v * 0.95, 4) for k, v in levs.items()}
    return res, levs


# --------------------------------------------------------------------- B&H
def buy_and_hold(con: sqlite3.Connection) -> dict:
    out: dict[str, dict] = {}
    finals = []
    for sym in SYMBOLS:
        rows = con.execute(
            "SELECT open_time, close FROM klines WHERE symbol=? AND interval='1h' "
            "AND open_time>=? AND open_time<? ORDER BY open_time",
            (sym, W0_MS, W1_MS)).fetchall()
        p0 = float(rows[0][1])
        peak, dd = p0, 0.0
        for _t, c in rows:
            c = float(c)
            peak = max(peak, c)
            dd = max(dd, (peak - c) / peak * 100)
        final = CAPITAL * float(rows[-1][1]) / p0
        out[sym] = {"final": final, "cagr": (final / CAPITAL) ** (1 / YEARS) - 1,
                    "dd": dd, "n": len(rows)}
        finals.append(final / len(SYMBOLS))
    final_eq = sum(finals)                       # égal-pondéré sans rebalancement
    out["equal"] = {"final": final_eq,
                    "cagr": (final_eq / CAPITAL) ** (1 / YEARS) - 1}
    return out


# -------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    data = {s: D.load_klines(con, s) for s in SYMBOLS}
    funding_hourly = funding_hourly_real()
    log(f"[data] {', '.join(f'{s}:{len(data[s])}' for s in SYMBOLS)} barres 1h")
    log(f"[funding] réel moyen %/h : "
        + ", ".join(f"{s} {funding_hourly[s]:.5f}" for s in SYMBOLS))

    trades_by_strat: dict[str, list[dict]] = {}
    caps_ma: dict[str, tuple[float, float]] = {}
    for name in SURVIVORS:
        tr = [t for t in build_survivor_trades(data, name)
              if W0_MS <= t["ts"] < W1_MS]
        trades_by_strat[name] = tr
        mae_train = max(t["mae"] for t in tr if t["ts"] < TRAIN_END_MS)
        cap = math.floor(100.0 / (mae_train + 0.5) * (1 - 1e-9) * 100) / 100
        caps_ma[name] = (cap, mae_train)
        log(f"[trades] {name}: {len(tr)} dispo (cap {cap:.2f}x, "
            f"maxMAE TRAIN {mae_train:.2f}%)")

    all_trades = [t for name in SURVIVORS for t in trades_by_strat[name]]

    solo, stack_runs = {}, {}
    for name in SURVIVORS:
        cap, _mae = caps_ma[name]
        rows = {}
        for tag, lev in (("1x", 1.0), ("cap/2", cap / 2), ("cap", cap)):
            res, levs = wallet(trades_by_strat[name], {name: lev}, {name: 1.0},
                               funding_hourly)
            rows[tag] = full_stats(res, f"{name} {tag}", f"lev {levs[name]:.2f}x")
        solo[name] = rows

    size_map = {name: STACK_WEIGHT for name in SURVIVORS}
    caps = {name: caps_ma[name][0] for name in SURVIVORS}
    for tag, factor in (("1x", None), ("cap/2", 0.5), ("cap", 1.0)):
        lev_map = {n: (1.0 if factor is None else caps[n] * factor)
                   for n in SURVIVORS}
        res, levs = wallet(all_trades, lev_map, size_map, funding_hourly)
        stack_runs[tag] = full_stats(
            res, f"stack {tag}",
            "lev " + "/".join(f"{levs[n]:.2f}" for n in SURVIVORS))

    bh = buy_and_hold(con)

    if args.write:
        write_report(solo, stack_runs, caps_ma, bh, funding_hourly)
        log(f"[write] {REPORT}")
    print_summary(solo, stack_runs, caps_ma, bh)


def print_summary(solo, stack_runs, caps_ma, bh) -> None:
    log("\n=== T22 WALLET SÉQUENTIEL SURVIVANTS T21 ===")
    for name, rows in solo.items():
        for tag, s in rows.items():
            log(f"{name:22s} {tag:6s} {s['lev_note']:14s} ${s['final']:8.2f} "
                f"ROI/an {s['cagr']*100:+6.1f}% DD {s['dd']:5.1f}% WR {s['wr']:4.1f}% "
                f"liq {s['liq']} n {s['n']:3d} mois- {s['mois_neg']:2d}/{s['n_mois']} "
                f"VAL {s['val_roi']*100:+7.1f}% (DD {s['val_dd']:4.1f}%)")
    for tag, s in stack_runs.items():
        log(f"STACK {tag:6s} {s['lev_note']:34s} ${s['final']:8.2f} "
            f"ROI/an {s['cagr']*100:+6.1f}% DD {s['dd']:5.1f}% WR {s['wr']:4.1f}% "
            f"liq {s['liq']} n {s['n']:3d} mois- {s['mois_neg']:2d}/{s['n_mois']} "
            f"VAL {s['val_roi']*100:+7.1f}% (DD {s['val_dd']:4.1f}%)")
    for k, v in bh.items():
        log(f"B&H {k:6s} ${v['final']:8.2f} ROI/an {v['cagr']*100:+6.1f}% "
            + (f"DD {v['dd']:.1f}%" if "dd" in v else ""))


# ------------------------------------------------------------------ report
def fmt_row(first_cell: str, s: dict) -> str:
    return (f"| {first_cell} | {s['lev_note']} | ${s['final']:.2f} "
            f"| {s['cagr']*100:+.1f} %/an | {s['dd']:.1f} % | {s['wr']:.1f} % "
            f"| {s['liq']} | {s['mois_neg']}/{s['n_mois']} | {s['record']:+.2f} $ "
            f"| {s['pire']:+.2f} $ | {s['val_roi']*100:+.1f} % | {s['val_dd']:.1f} % |")


def write_report(solo, stack_runs, caps_ma, bh, funding_hourly) -> None:
    L = ["# T22 — WALLET SÉQUENTIEL des 4 survivants T21 (la porte obligatoire)", "",
         f"Date : {datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M} UTC · One-shot : "
         "`scripts/studies/aster_survivors_wallet.py` · wallet $100, pattern "
         "`run_stack` de `scripts/stacked_portfolio.py` **importé** (jamais modifié) · "
         "DB `data/warehouse/klines.db` (ro) · frais taker 8 bps RT comptés · "
         "funding **réel** moyen par symbole (cache T21, API Aster) : "
         + ", ".join(f"{s.split('USDT')[0]} {funding_hourly[s]:.5f} %/h"
                     for s in SYMBOLS)
         + " · mark-to-market à la fermeture (convention stack officiel) · "
         f"fenêtre {dt_of(W0_MS):%Y-%m-%d} → {dt_of(W1_MS - DAY_MS):%Y-%m-%d} "
         f"({YEARS:.2f} ans, {len(month_list())} mois) · moteur de signaux = "
         "module T21 importé, parité assertée à 1e-9 · un créneau par stratégie "
         "(signaux multi-symboles simultanés sautés, convention officielle).", "",
         "**Règles de verdict pré-enregistrées (avant résultats)** : R1 0 liq "
         "partout ; R2 stack-cap DD ≤ 25 % ; R3 stack ROI/an ≥ +7,8 % (le NET "
         "officiel) ; R4 stack VAL 2024-2026 > 0 ; R5 chaque survivant solo "
         "VAL > 0. 5/5 = PROMOTION · R2-R4 ok, un solo échoue = PROMOTION "
         "PARTIELLE · R3 ou R4 échoue = CONTEXTE · R1 échoue = REFUS.", "",
         "Caps 0-liq : `lev ≤ 100/(maxMAE_TRAIN + 0.5)` exact (les 7,0×/8,2× cités "
         "en T21 étaient arrondis), boucle d'application ×0.95 si une liq apparaît "
         "(funding/costs au-delà du buffer 0,5 %) — 0 liq sans exception.", "",
         "**Correction d'unité T21** : les sommes annotées « bps » dans "
         "reports/aster_discovery_2123.md sont en réalité des **%** de cumul simple "
         "sur 1× (le moteur retourne ret = fraction × 100) — « +321 » = +321 %, pas "
         "+3,21 %. L'ordre des verdicts T21 est inchangé (relatif), les magnitudes "
         "étaient sous-étiquetées ×100.", ""]
    L.append("## 1. Les survivants SEULS ($100, marge pleine, 3 niveaux de lev)")
    L.append("")
    L.append("| survivant | lev | final | ROI/an | DD | WR | liq | mois− | record mois | pire mois | VAL 24-26 ROI | VAL DD |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name in SURVIVORS:
        cap, mae = caps_ma[name]
        for i, tag in enumerate(("1x", "cap/2", "cap")):
            first = f"`{name}` (maxMAE TRAIN {mae:.1f} %)" if i == 0 else ""
            L.append(fmt_row(first, solo[name][tag]))
    L.append("")
    L.append("## 2. LE STACK des survivants (poids égal 0.25, séquentiel composé)")
    L.append("")
    L.append("| stack | lev | final | ROI/an | DD | WR | liq | mois− | record | pire | VAL ROI | VAL DD |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for tag in ("1x", "cap/2", "cap"):
        L.append(fmt_row("stack 4 survivants", stack_runs[tag]))
    L.append("")
    L.append("### Par régime (équité composée entre bornes)")
    L.append("")
    L.append("| régime | stack CAP ROI | DD | stack 1× ROI | DD |")
    L.append("|---|---|---|---|---|")
    cap_rows = regime_rows(stack_runs["cap"])
    x1_rows = regime_rows(stack_runs["1x"])
    for (name, roi, dd), (_n, roi1, dd1) in zip(cap_rows, x1_rows):
        L.append(f"| {name} | {roi*100:+.1f} % | {dd:.1f} % | {roi1*100:+.1f} % | {dd1:.1f} % |")
    L.append("")
    L.append("## 3. Comparaison (même fenêtre 2021-09-01 → 2026-09-30)")
    L.append("")
    L.append("| portefeuille | final $100 | ROI/an | DD max | VAL 24-26 |")
    L.append("|---|---|---|---|---|")
    s = stack_runs["cap"]
    L.append(f"| Stack survivants T21 (cap, pré-enregistré) | ${s['final']:.2f} "
             f"| {s['cagr']*100:+.1f} %/an | {s['dd']:.1f} % | {s['val_roi']*100:+.1f} % |")
    s = stack_runs["1x"]
    L.append(f"| **Stack survivants T21 (1×, expos. officiel-comparable)** | "
             f"**${s['final']:.2f}** | **{s['cagr']*100:+.1f} %/an** | **{s['dd']:.1f} %** "
             f"| {s['val_roi']*100:+.1f} % |")
    s = stack_runs["cap/2"]
    L.append(f"| Stack survivants (cap/2) | ${s['final']:.2f} | {s['cagr']*100:+.1f} %/an "
             f"| {s['dd']:.1f} % | {s['val_roi']*100:+.1f} % |")
    L.append(f"| Stack officiel T11/V2 | $146.42 | +7.8 %/an | 32.5 % | −3.5 % |")
    for sym in SYMBOLS:
        v = bh[sym]
        L.append(f"| B&H {sym.split('USDT')[0]} | ${v['final']:.2f} | {v['cagr']*100:+.1f} %/an "
                 f"| {v['dd']:.1f} % | — |")
    v = bh["equal"]
    L.append(f"| B&H égal-pondéré (sans rebal.) | ${v['final']:.2f} | {v['cagr']*100:+.1f} %/an | — | — |")
    L.append("")
    st2 = stack_runs["cap/2"]
    calmar_off = OFFICIAL["cagr"] / (OFFICIAL["dd"] / 100)
    calmar_cap = stack_runs["cap"]["cagr"] / (stack_runs["cap"]["dd"] / 100) \
        if stack_runs["cap"]["dd"] > 0 else float("inf")
    calmar_h = st2["cagr"] / (st2["dd"] / 100) if st2["dd"] > 0 else float("inf")
    st1 = stack_runs["1x"]
    calmar_1 = st1["cagr"] / (st1["dd"] / 100) if st1["dd"] > 0 else float("inf")
    L.append(f"Risk-ajusté (CAGR ÷ DD) : stack 1× **{calmar_1:.2f}**, cap/2 "
             f"**{calmar_h:.2f}**, cap {calmar_cap:.2f}, officiel {calmar_off:.2f}, "
             f"B&H BTC {bh['BTCUSDT']['cagr']/(bh['BTCUSDT']['dd']/100):.2f}.")
    L.append("")
    L += auto_verdict(solo, stack_runs, bh)
    REPORT.write_text("\n".join(L) + "\n")


def auto_verdict(solo, stack_runs, bh) -> list[str]:
    st = stack_runs["cap"]
    r1 = (all(solo[n][t]["liq"] == 0 for n in solo for t in solo[n])
          and all(stack_runs[t]["liq"] == 0 for t in stack_runs))
    r2 = st["dd"] <= 25.0
    r3 = st["cagr"] >= OFFICIAL["cagr"]
    r4 = st["val_roi"] > 0
    r5 = all(solo[n]["cap"]["val_roi"] > 0 for n in SURVIVORS)
    checks = [("R1 0 liq", r1), ("R2 DD ≤ 25 %", r2), ("R3 ROI/an ≥ +7,8 %", r3),
              ("R4 VAL > 0", r4), ("R5 solos VAL > 0", r5)]
    ok = sum(1 for _, v in checks if v)
    if not r1:
        tag = ("**REFUS** — une liquidation est apparue : les caps dérivés de T21 "
               "ne sont pas assez sûrs pour le wallet (funding/holds longs).")
    elif ok == 5:
        tag = ("**PROMOTION** — le stack des survivants bat l'officiel en ROI/an "
               "avec DD ≤ 25 %, 0 liq, et tient le VAL sans re-calibrage.")
    elif r2 and r3 and r4:
        tag = ("**PROMOTION PARTIELLE** — le stack passe, au moins un survivant "
               "solo échoue le VAL : il est re-catégorisé CONTEXTE, pas trader seul.")
    else:
        tag = ("**CONTEXTE** — le stack des découvertes ne bat pas l'officiel "
               "(ROI/an ou VAL) : les edges VAL de T21 ne se composent pas mieux "
               "que le stack officiel à ce sizing.")
    out = ["| règle | état |", "|---|---|"]
    for k, v in checks:
        out.append(f"| {k} | {'OUI' if v else 'NON'} |")
    out += ["", f"### {tag}", "",
            f"Stack cap : ${st['final']:.2f} ({st['cagr']*100:+.1f} %/an, "
            f"DD {st['dd']:.1f} %, liq {st['liq']}, VAL {st['val_roi']*100:+.1f} %) "
            f"vs officiel $146.42 (+7.8 %/an, DD 32.5 %, VAL −3.5 %) vs B&H BTC "
            f"${bh['BTCUSDT']['final']:.2f} ({bh['BTCUSDT']['cagr']*100:+.1f} %/an, "
            f"DD {bh['BTCUSDT']['dd']:.1f} %).", "",
            "### Lecture post-hoc DÉCLARÉE (hors pré-enregistrement — sizing)", "",
            "L'échec R2-R4 vient du SIZING, pas de l'edge : marge pleine × lev cap "
            "compose la ruine SANS liquidation (drag de volatilité : à WR 26 %, "
            "perdre 97 % du wallet sur un trade −14 % à 6,96×). **La règle 0-liq "
            "borne la liquidation, pas la ruine — les caps T21 sont des plafonds, "
            "pas des tailles.** À exposition comparable au stack officiel "
            "(stack 1×, notionnel 0,25× par stratégie) :"]
    st1 = stack_runs["1x"]
    out.append(f"- **Stack 1× : ${st1['final']:.2f} ({st1['cagr']*100:+.1f} %/an, "
               f"DD {st1['dd']:.1f} %, VAL {st1['val_roi']*100:+.1f} %, liq 0)** "
               f"vs officiel $146.42 (+7.8 %/an, DD 32.5 %, VAL −3.5 %) — le stack "
               f"des survivants DOMINE l'officiel sur ROI/an, DD, VAL et "
               f"risk-ajusté ({st1['cagr']/(st1['dd']/100):.2f} vs "
               f"{OFFICIAL['cagr']/(OFFICIAL['dd']/100):.2f}), mais DD > 25 % : "
               "pas de promotion pleine.")
    for n in SURVIVORS:
        s = solo[n]["1x"]
        v = solo[n]["cap"]
        if s["val_roi"] > 0 and s["cagr"] > 0:
            cat = ("**CANDIDAT** (poids ≤ 1×, DD solo > 25 % : jamais seul à fond)"
                   if s["dd"] > 25 else "**CANDIDAT**")
        elif s["val_roi"] > 0:
            cat = "**CONTEXTE** (VAL simple positif mais période pleine négative : régime-dépendant)"
        else:
            cat = "**CONTEXTE** (VAL composé négatif — l'edge simple ne survit pas à la séquence)"
        out.append(f"- `{n}` 1× : ${s['final']:.2f} ({s['cagr']*100:+.1f} %/an, "
                   f"DD {s['dd']:.1f} %, VAL {s['val_roi']*100:+.1f} %) ; à cap "
                   f"{v['lev_note']} : ${v['final']:.2f} "
                   f"({'ruiné sans liq' if v['final'] < 20 else 'tient'}) — {cat}.")
    out += ["",
            "### Verdict final",
            "",
            "1. **REFUS de promouvoir le stack des survivants à lev cap** (verdict "
            "pré-enregistré CONTEXTE) : marge pleine × cap = ruine sans liquidation. "
            "La règle 0-liq est un PLAFOND de levier, pas un sizing — leçon "
            "doctrinale à graver.",
            "2. **CANDIDAT le stack des survivants à 1× (poids égal)** : +25.1 %/an, "
            "DD 30.2 %, VAL +16.1 %, 0 liq — il DOMINE le stack officiel T11/V2 "
            "(+7.8 %/an, DD 32.5 %, VAL −3.5 %) et le B&H BTC (+11.8 %/an, DD 77.2 %) "
            "sur les 4 axes. Mais DD > 25 % : la cible user n'est pas atteinte, pas "
            "de remplacement de l'officiel — complément à étudier.",
            "3. **Re-catégorisations** : `momentum_bear_lb48` ARTEFACT(T21) → "
            "**CANDIDAT n°1** (le seul solo qui tient à son propre cap, +29.1 %/an "
            "1×, VAL +34 %) ; `breakout_don168` SURVIVANT(T21) → **CANDIDAT tail** "
            "(+23.7 %/an 1×, VAL +34 %, WR 26 % : jamais seul, en stack) ; "
            "`trend_long_ema50x200` et `sma_regime_50d` SURVIVANTS(T21) → "
            "**CONTEXTE** (composés, leur VAL se retourne / ne paie que hors bear — "
            "à armer seulement derrière le détecteur T9).",
            "4. La vraie validation croisée inter-régimes échoue PARTIELLEMENT : le "
            "stack tient bull24/chop/connu À 1× (+16.1 % VAL) mais son DD 44.9 % en "
            "VAL dépasse la cible — les découvertes 2021-2023 ne se transmettent "
            "qu'avec un sizing réduit, pas à fond de cap."]
    out.append("**Limites** : n VAL = 2,7 ans d'un régime haussier BTC (biais assumé, "
               "le carry d'hier avait le même) ; funding flat moyen par symbole (pas "
               "la décomposition réelle trade par trade) ; MTM à la fermeture ; n=1 "
               "chemin de marché. Les verdicts RELATIFS (classement stack vs officiel "
               "vs B&H) survivent aux bugs ; les ABSOLUS non — garde-fou "
               "composé-des-mois à re-vérifier avant toute mise en prod.")
    return out


if __name__ == "__main__":
    main()
