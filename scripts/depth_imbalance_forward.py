#!/usr/bin/env python3
"""Harnais FORWARD — DEPTH-IMB : l'imbalance du carnet (spec pré-enregistrée).

Spec : `research/hypotheses/depth-imbalance.md` (pré-enregistrée le 02/10).
Mécanisme : l'excès d'ordres bid vs ask signale un déséquilibre de liquidité
qui précède les mouvements courts. Prédiction : imbalance > 0,25 → haussier
≥ 0,8 % en 15 min.

⚠️ **FORWARD-ONLY** — la spec l'impose (« pas de rétrospectif ») : la matière
première (`depth.db`) était immature (10 j) au gel. Le harnais ne juge donc
QUE les signaux postérieurs à son propre premier commit (`--gel` l'affiche).
`--include-past` montre l'historique — c'est une MESURE, jamais un verdict.

Garde-fous (spec) :
  - PASS si WR ≥ 65 % ET ratio bénéfice/coût ≥ 1,8 sur n ≥ 100 ;
  - FAIL si WR < 55 % ;
  - contrôles : inverse (imbalance < −0,25 → baissier), hors liquidations,
    par symbole.

Usage :
    .venv/bin/python scripts/depth_imbalance_forward.py --gel
    .venv/bin/python scripts/depth_imbalance_forward.py            # forward
    .venv/bin/python scripts/depth_imbalance_forward.py --include-past
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data" / "warehouse" / "depth.db"
KDB = ROOT / "data" / "warehouse" / "klines.db"
SELF_REL = "scripts/depth_imbalance_forward.py"

# --- les constantes de la SPEC (pré-enregistrées — ne pas tuner) -------------
BAND_PCT = 0.5        # ± % du mid (la « convention harnais » du dépôt)
TOP_N = 10            # la spec dit « top-10 niveaux »
MA_MIN = 30           # « moyenne glissante 30 min »
THRESHOLD = 0.25      # « DepthImbalance > 0,25 »
HORIZON_MIN = 15      # « en 15 min »
TARGET_PCT = 0.8      # « mouvement haussier ≥ 0,8 % »
EXLIQ_MIN = 5.0       # contrôle « hors liquidations » : ± 5 min autour d'une liq
PASS_WR, FAIL_WR = 65.0, 55.0
RATIO_MIN, N_MIN = 1.8, 100


def gel_start_ms() -> int | None:
    """Le GEL = le timestamp du commit qui a INTRODUIT ce fichier.

    C'est la définition de « gel au commit du harnais forward » : le harnais
    est l'état, pas l'intention. Renvoie None si git ne connaît pas le fichier
    (arbre de travail non commité) — dans ce cas le mode forward est refusé.
    """
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ct", "--", SELF_REL],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        lines = [ln for ln in out.stdout.split() if ln.strip().isdigit()]
        return int(lines[-1]) * 1000 if lines else None
    except Exception:  # noqa: BLE001 — pas de git : pas de gel, donc pas de forward
        return None


def load_imbalance(con: sqlite3.Connection, sym: str, mode: str) -> pd.DataFrame | None:
    """(ts, mid, imb) par snapshot. mode = 'band' (±0,5 %) ou 'top10' (spec)."""
    mids = pd.read_sql_query(
        "SELECT ts, mid FROM depth_meta WHERE symbol = ? ORDER BY ts",
        con, params=(sym,))
    if len(mids) < 500:
        return None
    mid_of = dict(zip(mids.ts.values, mids.mid.values))
    parts = []
    for chunk in pd.read_sql_query(
            "SELECT ts, side, bin_price, qty FROM depth_bins WHERE symbol = ?",
            con, params=(sym,), chunksize=2_000_000):
        m = chunk.ts.map(mid_of)
        ok = m.notna() & (m > 0)
        if not ok.any():
            continue
        c = chunk[ok.values].copy()
        c["mid"] = m[ok.values].values
        c["dist"] = (c.bin_price - c.mid).abs() / c.mid
        c["notional"] = c.bin_price.values * c.qty.values
        parts.append(c[["ts", "side", "notional", "dist"]])
    if not parts:
        return None
    bins = pd.concat(parts, ignore_index=True)
    if mode == "band":
        bins = bins[bins.dist <= BAND_PCT / 100]
    else:  # top10 : les 10 niveaux les plus proches du mid, par côté
        bins = (bins.sort_values(["ts", "side", "dist"])
                    .groupby(["ts", "side"], sort=False).head(TOP_N))
    if bins.empty:
        return None
    g = bins.groupby(["ts", "side"])["notional"].sum().unstack(fill_value=0.0)
    for col in ("bid", "ask"):
        if col not in g.columns:
            g[col] = 0.0
    tot = g["bid"] + g["ask"]
    g = g[tot > 0]
    if g.empty:
        return None
    g["imb"] = (g["bid"] - g["ask"]) / (g["bid"] + g["ask"])
    out = mids[mids.ts.isin(g.index)].reset_index(drop=True)
    out["imb"] = out.ts.map(g["imb"])
    return out


def add_ma(df: pd.DataFrame) -> pd.DataFrame:
    """La moyenne glissante 30 min de l'imbalance (la spec). ts en SECONDES."""
    t = pd.to_datetime(df.ts.values, unit="s", utc=True)
    s = pd.Series(df.imb.values, index=t)
    df = df.copy()
    df["ma"] = s.rolling(f"{MA_MIN}min").mean().values
    return df


def outcomes(df: pd.DataFrame, horizon_min: int) -> np.ndarray:
    """Le drift du mid à t+horizon (%), aligné sur df. NaN si l'avenir manque."""
    ts = df.ts.values.astype(np.int64)
    mid = df.mid.values
    h = horizon_min * 60
    j = np.searchsorted(ts, ts + h, side="right") - 1
    valid = (j > np.arange(len(ts))) & (ts[j] - ts <= int(h * 1.5))
    drift = np.where(valid, (mid[j] / mid - 1) * 100, np.nan)
    return drift


def liq_times(sym: str) -> np.ndarray:
    """Les timestamps (s) des liquidations du symbole — pour le contrôle hors-liq."""
    if not KDB.exists():
        return np.array([], dtype=np.int64)
    try:
        con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True, timeout=30)
        rows = con.execute(
            "SELECT event_time FROM liq_events WHERE symbol = ?", (sym,)).fetchall()
        con.close()
        return np.array([int(r[0]) // 1000 for r in rows], dtype=np.int64)
    except Exception:  # noqa: BLE001
        return np.array([], dtype=np.int64)


def _stats(drift: np.ndarray, cost_pct: float) -> dict:
    d = drift[~np.isnan(drift)]
    n = len(d)
    if n == 0:
        return {"n": 0}
    mean = float(d.mean())
    return {
        "n": n,
        "mean_pct": round(mean, 4),
        "median_pct": round(float(np.median(d)), 4),
        "wr_pos": round(float((d > 0).mean() * 100), 2),
        "wr_target": round(float((d >= TARGET_PCT).mean() * 100), 2),
        "ratio": round(mean / cost_pct, 3) if cost_pct > 0 else None,
        "cost_pct": cost_pct,
        "breakeven_bps": round((mean + cost_pct) * 100, 2),
    }


def verdict_of(agg: dict) -> str:
    """PASS / FAIL / INSUFFISANT — les seuils ÉCRITS dans la spec."""
    if agg.get("n", 0) < N_MIN:
        return f"INSUFFISANT (n={agg.get('n', 0)} < {N_MIN})"
    wr, ratio = agg["wr_pos"], agg.get("ratio")
    if wr < FAIL_WR:
        return f"FAIL (WR {wr}% < {FAIL_WR}%)"
    if wr >= PASS_WR and ratio is not None and ratio >= RATIO_MIN:
        return f"PASS (WR {wr}% ≥ {PASS_WR}% et ratio {ratio} ≥ {RATIO_MIN})"
    return f"ENTRE-DEUX (WR {wr}%, ratio {ratio}) — ni PASS ni FAIL"


def run(mode: str, forward_only: bool, symbols: list[str] | None) -> dict:
    from scripts.costs import cout_rt_pct  # noqa: PLC0415 — dépendance locale

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    syms = symbols or [r[0] for r in con.execute(
        "SELECT symbol, COUNT(*) n FROM depth_meta GROUP BY symbol "
        "ORDER BY n DESC").fetchall()]
    gel = gel_start_ms()
    rows, per_sym, controls = [], {}, {}
    for sym in syms:
        df = load_imbalance(con, sym, mode)
        if df is None or df.empty:
            continue
        df = add_ma(df)
        drift = outcomes(df, HORIZON_MIN)
        # FORWARD-ONLY : sans gel (fichier non commité), on ne juge RIEN —
        # un harnais sans état est une intention, pas un gel.
        if forward_only:
            base = (np.zeros(len(df), dtype=bool) if gel is None
                    else df.ts.values >= gel)
        else:
            base = np.ones(len(df), dtype=bool)
        liq = liq_times(sym)
        near_liq = (np.zeros(len(df), dtype=bool) if len(liq) == 0
                    else np.array([np.any(np.abs(liq - t) <= EXLIQ_MIN * 60)
                                   for t in df.ts.values]))
        cost = cout_rt_pct(sym, None)
        for side, mask in (("long", df.ma.values > THRESHOLD),
                           ("short", df.ma.values < -THRESHOLD)):
            m = mask & base & ~np.isnan(drift)
            st = _stats(drift[m], cost)
            if st.get("n"):
                st.update(symbol=sym, side=side)
                rows.append(st)
            st_ex = _stats(drift[m & ~near_liq], cost)
            if st_ex.get("n"):
                controls[f"{sym}:{side}:hors-liq"] = st_ex
        if rows:
            per_sym[sym] = {r["side"]: r for r in rows if r["symbol"] == sym}
    con.close()
    all_long = [r for r in rows if r["side"] == "long"]
    all_short = [r for r in rows if r["side"] == "short"]
    return {
        "mode": mode,
        "forward_only": forward_only,
        "gel_ms": gel,
        "horizon_min": HORIZON_MIN,
        "threshold": THRESHOLD,
        "per_symbol": per_sym,
        "LONG (la prédiction)": all_long,
        "SHORT (contrôle inverse)": all_short,
        "hors_liq": controls,
    }


def _fmt(rep: dict) -> str:
    lines = [f"=== DEPTH-IMB — imbalance → drift {rep['horizon_min']} min "
             f"(seuil {rep['threshold']}, mode {rep['mode']}) ==="]
    gel = rep["gel_ms"]
    if rep["forward_only"]:
        if gel is None:
            lines.append("⚠️  FORWARD-ONLY demandé mais AUCUN gel (fichier non "
                         "commité) — aucun signal jugé.")
        else:
            lines.append(f"FORWARD-ONLY : gel = {pd.to_datetime(gel, unit='ms', utc=True)}")
    else:
        lines.append("⚠️  --include-past : MESURE rétrospective, NON un verdict "
                     "(la spec est FORWARD-ONLY).")
    for key in ("LONG (la prédiction)", "SHORT (contrôle inverse)"):
        rows = rep[key]
        lines.append(f"\n--- {key} ---")
        if not rows:
            lines.append("  (aucun signal)")
            continue
        lines.append(f"  {'sym':14s} {'n':>5s} {'mean%':>8s} {'WR>0':>7s} "
                     f"{'WR>=0.8':>8s} {'ratio':>7s} {'bk-bps':>8s}")
        for r in sorted(rows, key=lambda x: -x["n"]):
            lines.append(f"  {r['symbol']:14s} {r['n']:5d} {r['mean_pct']:+8.4f} "
                         f"{r['wr_pos']:6.1f}% {r['wr_target']:7.1f}% "
                         f"{r['ratio']:7.3f} {r['breakeven_bps']:8.2f}")
    agg = _aggregate(rep["LONG (la prédiction)"])
    lines.append(f"\nLONG agrégé : {agg}")
    lines.append(f"VERDICT (seuils de la spec) : {verdict_of(agg)}")
    return "\n".join(lines)


def _aggregate(rows: list[dict]) -> dict:
    """Agrège en repondérant par n (l'agrégat des symboles, pas la moyenne des moyennes)."""
    tot = sum(r["n"] for r in rows)
    if not tot:
        return {"n": 0}
    mean = sum(r["mean_pct"] * r["n"] for r in rows) / tot
    wr = sum(r["wr_pos"] * r["n"] for r in rows) / tot
    wrt = sum(r["wr_target"] * r["n"] for r in rows) / tot
    cost = sum(r["cost_pct"] * r["n"] for r in rows) / tot
    return {"n": tot, "mean_pct": round(mean, 4), "wr_pos": round(wr, 2),
            "wr_target": round(wrt, 2), "cost_pct": round(cost, 4),
            "ratio": round(mean / cost, 3) if cost > 0 else None,
            "breakeven_bps": round((mean + cost) * 100, 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Harnais forward DEPTH-IMB")
    ap.add_argument("--mode", choices=["band", "top10"], default="band",
                    help="band = ±0,5 %% du mid (convention harnais) · top10 = la spec")
    ap.add_argument("--include-past", action="store_true",
                    help="MESURE rétrospective (NON un verdict)")
    ap.add_argument("--gel", action="store_true", help="affiche le gel et sort")
    ap.add_argument("--json", action="store_true", help="sortie JSON")
    ap.add_argument("--symbol", action="append", help="restreindre (répétable)")
    a = ap.parse_args()
    if a.gel:
        g = gel_start_ms()
        print("gel_ms:", g)
        print("gel:", pd.to_datetime(g, unit="ms", utc=True) if g else
              "AUCUN — le harnais n'est pas encore commité")
        return 0
    rep = run(a.mode, forward_only=not a.include_past, symbols=a.symbol)
    if a.json:
        print(json.dumps(rep, indent=1, default=str))
    else:
        print(_fmt(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
