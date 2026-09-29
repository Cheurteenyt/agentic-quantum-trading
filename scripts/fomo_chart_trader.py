#!/usr/bin/env python3
"""AUDIT DE PRÉCISION « chart fomo ↔ trader » — la preuve par la courbe.

Pour UN token : reconstruire LA courbe que fomo affiche (MC si supply
reconstruisible, sinon prix) et y placer chaque trader connu :
  - la courbe  : fomo.db/fomo_ohlcv (1m, time en MILLISECONDES) sinon fomo_ticks
  - la MC      : supply = marketCap/priceUSD (trending, token_about, ws_swaps)
  - les trades : ws_swaps (WS direct), fomo_swaps (REST backfill),
                 fomo_rest_swaps (REST JSON), hodlers (entry_price lignes)
Read-only absolu (mode=ro) : aucune écriture dans les DB de prod.
Sortie : reports/fomo_chart_trader_<mint>.pdf (note de recherche, fond blanc).
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parent.parent
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"
REST_DB = ROOT / "data" / "fomo" / "fomo_rest.db"
OUT_DIR = ROOT / "reports"

NAVY, INK, GREY = "#1B2A4A", "#33415C", "#8D99AE"
BUY, SELL, ENTRY = "#2F6B4F", "#8C3A3A", GREY


def ro(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")  # les backfills tiennent des
    # transactions d'écriture de plusieurs secondes (journal rollback)
    return con


def iso_to_s(ts):
    if not ts:
        return None
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S") \
            .replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return None


def fmt_usd(x):
    if x is None:
        return "?"
    for u, d in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(x) >= d:
            return f"{x/d:.1f}{u}$"
    return f"{x:.0f}$"


def load_trending_supply(mint):
    """supply = marketCap/priceUSD du dernier snapshot trending (ou token_about)."""
    con = ro(REST_DB)
    row = con.execute(
        "SELECT captured_at, data FROM fomo_rest_snapshots "
        "WHERE endpoint='trending' ORDER BY captured_at DESC LIMIT 1").fetchone()
    if row:
        try:
            j = json.loads(row["data"])
            arr = j if isinstance(j, list) else j.get("data") or []
            for it in arr:
                mc, p = it.get("marketCap"), it.get("priceUSD")
                if ((it.get("token") or {}).get("address") == mint
                        and mc and p):
                    con.close()
                    return float(mc) / float(p), f"trending@{row['captured_at']}"
        except Exception:
            pass
    row = con.execute(
        "SELECT captured_at, data FROM fomo_rest_snapshots "
        "WHERE endpoint='token_about' AND entity_id=? "
        "ORDER BY captured_at DESC LIMIT 1", (mint,)).fetchone()
    if row:
        try:
            j = json.loads(row["data"])
            if j.get("marketCap") and j.get("priceUSD"):
                con.close()
                return (float(j["marketCap"]) / float(j["priceUSD"]),
                        f"token_about@{row['captured_at']}")
        except Exception:
            pass
    con.close()
    return None, None


def load_swaps_supply(mint):
    """supply implicite via ws_swaps (mc/price) — médiane robuste."""
    con = ro(SWAPS_DB)
    rows = con.execute(
        "SELECT market_cap, price FROM ws_swaps "
        "WHERE token_addr=? AND market_cap>0 AND price>0", (mint,)).fetchall()
    con.close()
    rats = sorted(mc / p for mc, p in rows)
    if not rats:
        return None, None
    return rats[len(rats) // 2], f"ws_swaps×{len(rats)}"


def load_curve(mint):
    """fomo_ohlcv 1m (time en MILLISECONDES) + fomo_ticks (ts_s) fusionnés
    (les ticks comblent les trous du backfill 1m). -> (t_s, px, label)."""
    con = ro(FOMO_DB)
    rows = con.execute(
        "SELECT time, close FROM fomo_ohlcv WHERE asset=? AND period='1m' "
        "ORDER BY time", (mint,)).fetchall()
    pts = {r[0] // 1000: r[1] for r in rows}
    n_oh = len(pts)
    rows = con.execute(
        "SELECT ts_s, priceUsd FROM fomo_ticks WHERE mint=? ORDER BY ts_s",
        (mint,)).fetchall()
    con.close()
    for t, p in rows:
        pts.setdefault(t, p)
    ts = sorted(pts)
    return (ts, [pts[t] for t in ts],
            f"fomo_ohlcv 1m ×{n_oh} + fomo_ticks ×{len(ts) - n_oh}")


def load_trades(mint):
    """Toutes les traces de trades connues pour CE token."""
    out = []  # (t_s, side, usd, source, handle)
    con = ro(SWAPS_DB)
    for sid, typ, usd, ca, h in con.execute(
            "SELECT swap_id, type, usd_amount, created_at, handle FROM ws_swaps "
            "WHERE token_addr=?", (mint,)):
        t = iso_to_s(ca)
        if t:
            out.append((t, "buy" if typ == "swap_buy" else "sell",
                        usd or 0.0, "ws_swaps", h or "?"))
    for ts, side, usd, h in con.execute(
            "SELECT ts, side, size_usd, user_handle FROM fomo_swaps "
            "WHERE mint=? AND ts>0", (mint,)):
        if side in ("buy", "sell"):
            out.append((ts, side, usd or 0.0, "fomo_swaps", h or "?"))
    con.close()
    con = ro(REST_DB)
    for (data,) in con.execute(
            "SELECT data FROM fomo_rest_swaps WHERE data LIKE ?",
            (f"%{mint[:24]}%",)):
        try:
            j = json.loads(data)
        except Exception:
            continue
        if mint not in (j.get("inTokenAddress"), j.get("outTokenAddress")):
            continue
        t = iso_to_s(j.get("createdAt"))
        if not t:
            continue
        side = ("sell" if j.get("inTokenAddress") == mint
                else "buy" if j.get("outTokenAddress") == mint else None)
        if side:
            usd = j.get("humanUsdAmountOut" if side == "buy" else "humanUsdAmountIn") \
                or j.get("humanUsdAmountIn") or 0.0
            out.append((t, side, float(usd), "fomo_rest_swaps", "?"))
    con.close()
    return out


def load_holder_entries(mint):
    """Les prix d'entrée des holders connus -> lignes horizontales."""
    ents = []
    con = ro(SWAPS_DB)
    for h, p in con.execute(
            "SELECT handle, entry_price FROM fomo_token_holders "
            "WHERE mint=? AND entry_price>0", (mint,)):
        ents.append((h or "?", p, "fomo_token_holders"))
    con.close()
    con = ro(REST_DB)
    row = con.execute(
        "SELECT data, captured_at FROM fomo_rest_snapshots "
        "WHERE endpoint='hodlers_top' AND entity_id=? "
        "ORDER BY captured_at DESC LIMIT 1", (mint,)).fetchone()
    con.close()
    if row:
        try:
            j = json.loads(row["data"])
            arr = j if isinstance(j, list) else j.get("topHolders") or []
            for it in arr:
                p = it.get("averageEntryPrice")
                u = it.get("user")
                h = (u.get("handle") if isinstance(u, dict) else u) or "?"
                if p:
                    ents.append((h, float(p), "hodlers_top"))
        except Exception:
            pass
    return ents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mint", default=None,
                    help="mint du token (défaut : plus gros MC du dernier trending)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    mint, ticker = args.mint, None
    if not mint:
        con = ro(REST_DB)
        row = con.execute("SELECT data FROM fomo_rest_snapshots "
                          "WHERE endpoint='trending' ORDER BY captured_at DESC "
                          "LIMIT 1").fetchone()
        con.close()
        arr = json.loads(row[0])
        arr = arr if isinstance(arr, list) else arr.get("data") or []
        best = max(arr, key=lambda x: float(x.get("marketCap") or 0))
        mint = best["token"]["address"]
    con = ro(SWAPS_DB)
    t = con.execute("SELECT ticker FROM ws_swaps WHERE token_addr=? AND ticker "
                    "IS NOT NULL LIMIT 1", (mint,)).fetchone()
    if not t:
        t = con.execute("SELECT ticker FROM fomo_swaps WHERE mint=? AND ticker "
                        "IS NOT NULL LIMIT 1", (mint,)).fetchone()
    con.close()
    ticker = t[0] if t else mint[:8]

    supply, supply_src = load_trending_supply(mint)
    if supply is None:
        supply, supply_src = load_swaps_supply(mint)
    ts, px, curve_src = load_curve(mint)
    trades = load_trades(mint)
    entries = load_holder_entries(mint)

    print(f"token  : {ticker} {mint}")
    print(f"courbe : {curve_src}  {len(ts)} pts", end="")
    if ts:
        print(f"  {datetime.fromtimestamp(ts[0], timezone.utc):%m-%d %H:%M} -> "
              f"{datetime.fromtimestamp(ts[-1], timezone.utc):%m-%d %H:%M}")
    else:
        print()
    print(f"supply : {supply} ({supply_src})")
    print(f"trades : {len(trades)}  entries: {len(entries)}")
    if not ts:
        sys.exit("aucune courbe pour ce mint")

    # ---- MC(t) = prix(t) × supply (supply supposée constante sur la fenêtre)
    mc = [p * supply for p in px] if supply else None

    OUT_DIR.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / f"fomo_chart_trader_{mint[:10]}.pdf"

    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(11.7, 8.3), sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08})
    fig.patch.set_facecolor("white")

    label = f"MC(t) = prix × supply" if mc else "PRIX — MC indisponible (supply manquante)"
    ax.plot([datetime.fromtimestamp(t, timezone.utc) for t in ts],
            mc if mc else px, color=NAVY, lw=0.9, label=label)
    if not mc:
        ax.text(0.5, 0.5, "MC indisponible — supply manquante",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=13, color=SELL, alpha=0.75)
    ax.set_yscale("log")
    ax.set_ylabel("Market cap USD (log)" if mc else "Prix USD (log)",
                  color=INK, fontsize=10)

    # les trades : triangles buys (pleins) / sells (creux)
    dts = [datetime.fromtimestamp(t, timezone.utc) for t, *_ in trades]
    for side, mark, col in (("buy", "^", BUY), ("sell", "v", SELL)):
        xs = [d for d, tr in zip(dts, trades) if tr[1] == side]
        ys = []
        for d, tr in zip(dts, trades):
            if tr[1] != side:
                continue
            i = min(range(len(ts)), key=lambda k: abs(ts[k] - tr[0]))
            base = (mc if mc else px)[i]
            ys.append(base * (1.06 if side == "buy" else 0.94))
        ax.scatter(xs, ys, marker=mark, s=28, facecolor=col if side == "buy"
                   else "none", edgecolor=col, linewidths=0.9, zorder=5,
                   label=f"{side} ×{len(xs)}")
    # les entrées des holders connus
    for h, p, src in entries:
        ax.axhline(p * (supply or 1.0), color=ENTRY, lw=0.5, ls=":", alpha=0.55)
    ax.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=INK)
    ax.grid(True, color="#E5E9F0", lw=0.5)
    for s in ax.spines.values():
        s.set_color(GREY)

    # panneau 2 : la taille USD des trades par source
    srcs = sorted({tr[3] for tr in trades})
    cols = {"ws_swaps": BUY, "fomo_swaps": NAVY, "fomo_rest_swaps": GREY}
    for i, src in enumerate(srcs):
        xs = [d for d, tr in zip(dts, trades) if tr[3] == src]
        ys = [max(tr[2], 1.0) for tr in trades if tr[3] == src]
        ax2.scatter(xs, ys, s=10, color=cols.get(src, INK), label=src, alpha=0.8)
    ax2.set_yscale("log")
    ax2.set_ylabel("Taille USD (log)", color=INK, fontsize=9)
    ax2.grid(True, color="#E5E9F0", lw=0.5)
    ax2.legend(loc="upper left", fontsize=7, frameon=False, labelcolor=INK)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    for lbl in ax2.get_xticklabels():
        lbl.set_rotation(20), lbl.set_fontsize(7), lbl.set_color(INK)

    n_ws = sum(1 for tr in trades if tr[3] == "ws_swaps")
    n_rest = sum(1 for tr in trades if tr[3] != "ws_swaps")
    fig.suptitle(
        f"{ticker} — chart fomo ↔ trader  |  {mint[:16]}…",
        color=NAVY, fontsize=13, fontweight="bold", y=0.97)
    ax.set_title(
        f"courbe: {curve_src} | supply: {fmt_usd(supply)} ({supply_src}) | "
        f"trades: ws={n_ws} rest={n_rest} | entrées holders: {len(entries)} | "
        f"MC = prix × supply (constante sur la fenêtre)",
        color=INK, fontsize=8.5, loc="left", pad=6)
    fig.text(0.01, 0.005,
             "Audit chart↔trader — sources: fomo.db(fomo_ohlcv/fomo_ticks), "
             "fomo_swaps.db(ws_swaps/fomo_swaps/fomo_token_holders), "
             "fomo_rest.db(fomo_rest_swaps/hodlers_top). Lecture read-only.",
             fontsize=6.5, color=GREY)
    fig.savefig(out, format="pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"PDF    : {out}")


if __name__ == "__main__":
    main()
