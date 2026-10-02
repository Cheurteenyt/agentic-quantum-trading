#!/usr/bin/env python
"""Heatmap de liquidité Aster — rendu PDF vectoriel depuis depth.db.

MMT style (temps × prix, couleur = liquidité au repos) mais sur NOS données
Aster collectées 24/7 par scripts/depth_collector.py. Goût visuel : note de
recherche claire (fond blanc, encre navy), PDF vectoriel — jamais de HTML.

Usage :
  .venv/bin/python scripts/depth_heatmap.py                        # 3 symboles, 12h
  .venv/bin/python scripts/depth_heatmap.py --symbol BTCUSDT --hours 24
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "depth.db"
REPORTS = ROOT / "reports"

INK = "#0F172A"
ACCENT = "#0369A1"
CMAP = LinearSegmentedColormap.from_list("liq", ["#FFFFFF", "#BFDBFE", "#0369A1", "#0F172A"])
CMAP.set_bad("#F8FAFC")  # pas de carnet à ce prix/moment (gris très pâle)


def load_grid(db_path: Path | str, symbol: str, hours: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float] | None:
    """Retourne (times[], bin_prices[], Z[time x price], mid) ou None si vide."""
    con = sqlite3.connect(db_path, timeout=60)
    try:
        cutoff = int(datetime.now(tz=timezone.utc).timestamp() - hours * 3600)
        meta = con.execute(
            "SELECT ts, mid FROM depth_meta WHERE symbol = ? AND ts >= ? ORDER BY ts", (symbol, cutoff)
        ).fetchall()
        if len(meta) < 5:
            return None
        times = [m[0] for m in meta]
        mids = [m[1] for m in meta]
        rows = con.execute(
            "SELECT ts, bin_price, qty FROM depth_bins WHERE symbol = ? AND ts >= ?",
            (symbol, cutoff),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        return None
    mid_ref = mids[len(mids) // 2]
    bin_prices = sorted({r[1] for r in rows})
    # limiter à ±1.5 % autour du mid de référence (les bins suivent le prix dans le temps)
    lo, hi = mid_ref * 0.985, mid_ref * 1.015
    bin_prices = [b for b in bin_prices if lo <= b <= hi][:400]
    if not bin_prices:
        return None
    idx = {b: i for i, b in enumerate(bin_prices)}
    t_idx = {t: i for i, t in enumerate(times)}
    Z = np.full((len(times), len(bin_prices)), np.nan)
    for ts, bp, qty in rows:
        i = t_idx.get(ts)
        j = idx.get(bp)
        if i is not None and j is not None:
            Z[i, j] = qty
    return times, np.array(bin_prices), Z, mid_ref


def render(symbol: str, hours: float, db_path: Path | str = DB_PATH, out_dir: Path = REPORTS) -> Path | None:
    grid = load_grid(db_path, symbol, hours)
    if grid is None:
        return None
    times, bin_prices, Z, mid_ref = grid
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=120)
    fig.patch.set_facecolor("white")
    dt = [datetime.fromtimestamp(t, tz=timezone.utc) for t in times]
    masked = np.ma.masked_invalid(Z)
    mesh = ax.pcolormesh(dt, bin_prices, masked.T, cmap=CMAP, shading="auto")
    cbar = fig.colorbar(mesh, ax=ax, pad=0.015)
    cbar.set_label("Quantité au repos", color=INK, fontsize=9)
    cbar.ax.tick_params(colors=INK, labelsize=8)
    ax.set_title(
        f"Heatmap de liquidité — {symbol} (Aster natif, {hours:g}h)",
        color=INK, fontsize=12, loc="left", pad=10,
    )
    ax.set_ylabel("Prix", color=INK, fontsize=9)
    ax.tick_params(colors=INK, labelsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M", tz=timezone.utc))
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_color(INK)
        spine.set_linewidth(0.6)
    fig.text(
        0.995, 0.01,
        f"bacs 0.01 % · source depth.db · {datetime.now(tz=timezone.utc):%d/%m/%Y %H:%M} UTC",
        ha="right", va="bottom", fontsize=7, color="#64748B",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    out = out_dir / f"depth-heatmap-{symbol.lower()}-{stamp}.pdf"
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Rendu heatmap de liquidité Aster (PDF)")
    p.add_argument("--symbol", default="BTCUSDT,ETHUSDT,ASTERUSDT")
    p.add_argument("--hours", type=float, default=12.0)
    p.add_argument("--db", default=str(DB_PATH))
    args = p.parse_args()
    made = []
    for sym in [s.strip().upper() for s in args.symbol.split(",") if s.strip()]:
        out = render(sym, args.hours, args.db)
        if out:
            made.append(out)
            print(f"[ok] {out}")
        else:
            print(f"[skip] {sym} : pas assez de données (capteur trop récent ?)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
