# execution_depth_floor.py — le PLANCHER de coût taker depuis le carnet réel (depth.db).
# Complète le protocole d'exécution (research/hypotheses/execution-slippage-protocol.md) là où
# la tape ne peut pas aller : le half-spread au moment des entries = le coût minimal
# qu'un taker humain paie SUR UN AUTRE SYMBOLE (15/36 couverts par la depth).
# Descriptif uniquement — aucun verdict, aucun budget. Read-only sur depth.db (102 M bins).

import sqlite3
import numpy as np
import pandas as pd

KL = "data/warehouse/klines.db"
DP = "data/warehouse/depth.db"
TOL_S = 30          # le snapshot depth le plus proche de l'entry (± 30 s = la cadence)
MAJORS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ASTERUSDT", "DOGEUSDT"}


def main():
    dk = sqlite3.connect(f"file:{KL}?mode=ro", uri=True)
    dd = sqlite3.connect(f"file:{DP}?mode=ro", uri=True)
    pt = pd.read_sql_query(
        "SELECT symbol, direction, entry_ts, entry_price FROM paper_trades "
        "WHERE entry_ts IS NOT NULL AND entry_price > 0", dk)
    dk.close()
    pt["entry_s"] = pt["entry_ts"] // 1000
    dsyms = set(r[0] for r in dd.execute("SELECT DISTINCT symbol FROM depth_meta"))
    pt = pt[pt["symbol"].isin(dsyms)].copy()
    print(f"paper trades sur symboles depth-couverts : {len(pt)} ({len(set(pt['symbol']))} syms)")

    # match : le snapshot depth le plus proche ≤ ±30 s
    meta = pd.read_sql_query("SELECT symbol, ts, mid FROM depth_meta", dd)
    matched = []
    for sym, g in meta.groupby("symbol"):
        sub = pt[pt["symbol"] == sym]
        if sub.empty:
            continue
        ts_arr = g["ts"].to_numpy()
        idx = np.searchsorted(ts_arr, sub["entry_s"].to_numpy())
        for (_, tr), j in zip(sub.iterrows(), idx):
            for jj in (j, j - 1):
                if 0 <= jj < len(ts_arr) and abs(ts_arr[jj] - tr["entry_s"]) <= TOL_S:
                    matched.append((sym, int(ts_arr[jj]), tr["direction"],
                                    float(tr["entry_price"]), int(ts_arr[jj]) - int(tr["entry_s"])))
                    break
    need = pd.DataFrame(matched, columns=["symbol", "ts", "dir", "entry_px", "dt_s"])
    print(f"entries appariées à un snapshot depth ≤±{TOL_S}s : {len(need)}")

    # UN SEUL scan des 102 M bins pour les snapshots appariés
    dd.execute("CREATE TEMP TABLE need(symbol TEXT, ts INTEGER)")
    dd.executemany("INSERT INTO need VALUES (?,?)", need[["symbol", "ts"]].values.tolist())
    q = dd.execute(
        "SELECT b.symbol, b.ts, b.side, MIN(b.bin_price), MAX(b.bin_price) "
        "FROM depth_bins b JOIN need n ON b.symbol=n.symbol AND b.ts=n.ts "
        "GROUP BY b.symbol, b.ts, b.side").fetchall()
    dd.close()
    book = pd.DataFrame(q, columns=["symbol", "ts", "side", "px_min", "px_max"])
    asks = book[book["side"] == "ask"].set_index(["symbol", "ts"])["px_min"]  # best ask
    bids = book[book["side"] == "bid"].set_index(["symbol", "ts"])["px_max"]  # best bid
    need = need.set_index(["symbol", "ts"])
    need["best_ask"] = asks
    need["best_bid"] = bids
    need = need.dropna(subset=["best_ask", "best_bid"])
    need["spread_bps"] = (need["best_ask"] - need["best_bid"]) / ((need["best_ask"] + need["best_bid"]) / 2) * 1e4

    print(f"\n== PLANCHER TAKER (spread du carnet, descriptif, n={len(need)}) ==")
    print(f"global : médiane {need['spread_bps'].median():.1f} bps | p90 {need['spread_bps'].quantile(0.9):.1f} "
          f"| max {need['spread_bps'].max():.1f}")
    need["classe"] = np.where(need.index.get_level_values(0).isin(MAJORS), "majors", "autres")
    for cl, g in need.groupby("classe"):
        print(f"  {cl:7s}: médiane {g['spread_bps'].median():.1f} | p90 {g['spread_bps'].quantile(0.9):.1f} "
              f"| n={len(g)} | syms {g.index.get_level_values(0).nunique()}")
    print("\npar symbole :")
    print(need.groupby(need.index.get_level_values(0))["spread_bps"].agg(
        ["median", "max", "count"]).round(1).to_string())
    print("\n(Ce spread = le coût MINIMAL d'un taker. Le seuil kill pire-30s du protocole "
          "est un plafond ADVERSE ; ici on vérifie le plancher : un spread médian > seuil/2 "
          "rendrait le flux intenable même avant le drift.)")


if __name__ == "__main__":
    main()
