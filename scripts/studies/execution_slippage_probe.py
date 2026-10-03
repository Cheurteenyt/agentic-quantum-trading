# execution_slippage_probe.py — la PREMIÈRE mesure réelle du slippage d'exécution humaine.
# Contexte : le ledger paper suppose entry_price = l'open de la bougie d'exécution ; la tape
# réelle (11,6 M prints) permet de mesurer ce qu'un humain taker aurait VRAIMENT obtenu.
# C'est un PROBE descriptif (aucun verdict, aucun budget) — le protocole définitif et les
# seuils kill viennent du pré-enregistrement qui suit (Bonsai + agent, lun 05/10).

import sqlite3
import numpy as np
import pandas as pd

DB = "data/warehouse/klines.db"
WINDOWS_S = [5, 30, 60]   # la fenêtre de "faisabilité" après entry_ts


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    pt = pd.read_sql_query(
        "SELECT symbol, direction, signal_ts, entry_ts, entry_price, status "
        "FROM paper_trades WHERE entry_ts IS NOT NULL AND entry_price > 0", con)
    print(f"paper_trades exploitables : {len(pt)}")

    # entry_ts en ms ? normalisation défensive (le champ a déjà menti une fois)
    for col, scale in (("entry_ts", 1), ("signal_ts", 1)):
        v = pt[col]
        pt[col] = np.where(v < 1e11, v * 1000, np.where(v < 1e14, v, v // 1000))
    t0, t1 = pt["entry_ts"].min(), pt["entry_ts"].max()
    print(f"fenêtre entries : {pd.Timestamp(t0, unit='ms')} → {pd.Timestamp(t1, unit='ms')}")

    syms = set(pt["symbol"].unique())
    tape_syms = set(r[0] for r in con.execute("SELECT DISTINCT symbol FROM aster_tape"))
    pt = pt[pt["symbol"].isin(tape_syms)].copy()
    print(f"couverture tape : {len(set(pt['symbol']))}/{len(syms)} symboles, {len(pt)} trades")

    rows = []
    for _, tr in pt.iterrows():
        e_ts, e_px, d = int(tr["entry_ts"]), float(tr["entry_price"]), int(tr["direction"])
        if e_px <= 0 or d == 0:
            continue
        w0 = e_ts  # le fill humain démarre À l'open (latence humaine bornée à part)
        q = con.execute(
            "SELECT ts_ms, price, qty FROM aster_tape WHERE symbol=? AND ts_ms>=? AND ts_ms<=? "
            "ORDER BY ts_ms", (tr["symbol"], w0, w0 + 60_000)).fetchall()
        if not q:
            continue
        ts = np.array([x[0] for x in q]); px = np.array([x[1] for x in q])
        qty = np.array([x[2] for x in q])
        row = {"symbol": tr["symbol"], "dir": d, "status": tr["status"],
               "ttf_s": (ts[0] - e_ts) / 1000.0}
        # taker immédiat : le premier print (on traverse le spread au pire)
        row["slip_taker_bps"] = d * (px[0] / e_px - 1) * 1e4
        for w in WINDOWS_S:
            m = ts <= e_ts + w * 1000
            if m.any():
                vwap = (px[m] * qty[m]).sum() / qty[m].sum()
                row[f"slip_vwap{w}_bps"] = d * (vwap / e_px - 1) * 1e4
                row[f"depth{w}_qty"] = qty[m].sum()
            else:
                row[f"slip_vwap{w}_bps"] = np.nan
                row[f"depth{w}_qty"] = 0.0
        rows.append(row)
    r = pd.DataFrame(rows)
    if r.empty:
        print("0 trade mesurable — étendre la fenêtre tape ?")
        return
    print(f"\n== SONDAGE SANS VERDICT : {len(r):,} trades mesurés sur la tape réelle ==")
    for per in (("taker", "slip_taker_bps"), ("vwap30", "slip_vwap30_bps"), ("vwap60", "slip_vwap60_bps")):
        s = r[per[1]].dropna()
        if len(s):
            print(f"{per[0]:8s}: médiane {s.median():+.1f} bps | moyenne {s.mean():+.1f} "
                  f"| p90 {s.quantile(0.9):+.1f} | p99 {s.quantile(0.99):+.1f} (n={len(s):,})")
    print(f"\ntime-to-first-print : médiane {r['ttf_s'].median():.2f} s | p95 {r['ttf_s'].quantile(0.95):.2f} s")
    d30 = r["depth30_qty"]
    print(f"profondeur 30 s (qty imprimée) : médiane {d30.median():.0f} | p10 {d30.quantile(0.1):.0f}")
    print("\npar direction :")
    print(r.groupby("dir")[["slip_taker_bps", "slip_vwap30_bps"]].median().round(1))
    print("\nles 10 pires taker :")
    worst = r.nlargest(10, "slip_taker_bps")[["symbol", "dir", "slip_taker_bps", "ttf_s", "depth5_qty" if "depth5_qty" in r else "depth30_qty"]]
    print(worst.to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
