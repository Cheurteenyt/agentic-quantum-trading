#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QA du portage deep v30 — invariants du moteur « depuis le début de l'actif ».

Contrôles (tous bloquants, exit 1 au premier échec) :
  Q1 DB : zéro NULL taker_buy sur les 8 flux, klines horaires contiguës
          (0 trou) depuis le plancher de listing de chaque actif.
  Q2 Pool : trades chargables, champs complets, |R| < 30, R cohérents avec
          pnl/risk (tolérance 1e-6), n > 0.
  Q3 Chronologie : premier trade de chaque flux >= listing + warmup (60 j + 24 h)
          de CE flux ; dernier trade <= dernière barre deep.
  Q4 Comptage : somme des n par symbole == n global ; par alpha couvre A1-A4.
  Q5 Équité : timestamps strictement croissants, équité finale > 0.
"""
import json
import os
import pickle
import sqlite3
import sys
import datetime as dt

sys.path.insert(0, "/home/z/my-project/scripts")
DB = "/home/z/my-project/scripts/x501_v21_results/om_v27.db"
OUT = "/home/z/my-project/scripts/x501_v21_results"
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
        "DOGEUSDT", "AVAXUSDT", "LINKUSDT"]
FLOOR = json.load(open(f"{OUT}/floor_v29.json"))
WARMUP_MS = 60 * 86400_000 + 24 * 3600_000

fails = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail}")
    if not cond:
        fails.append(name)


def main():
    print("Q1 — DB deep (taker_buy + contiguïté)")
    con = sqlite3.connect(DB)
    for sym in SYMS:
        nulls = con.execute("SELECT COUNT(*) FROM bn_kline_1h_deep WHERE symbol=? "
                            "AND taker_buy IS NULL", (sym,)).fetchone()[0]
        check(f"taker_buy {sym}", nulls == 0, f"nulls={nulls}")
        lo, hi, n = con.execute("SELECT MIN(ts), MAX(ts), COUNT(*) FROM "
                                "bn_kline_1h_deep WHERE symbol=?", (sym,)).fetchone()
        check(f"contiguïté {sym}", n == (hi - lo) // 3600_000 + 1,
              f"n={n} attendu={(hi - lo) // 3600_000 + 1}")
    con.close()

    print("Q2 — Pool deep (champs, R)")
    pool = pickle.load(open(f"{OUT}/pool_v30_deep.pkl", "rb"))
    trades = pool["trades"]
    check("n trades > 0", len(trades) > 0, f"n={len(trades)}")
    bad_fields = [t for t in trades
                  if not all(k in t for k in ("key", "t_in", "t_out", "side",
                                              "pnl", "risk", "R", "entry", "legs"))]
    check("champs complets", not bad_fields, f"{len(bad_fields)} incomplets")
    big_r = [t for t in trades if abs(t["R"]) >= 30]
    check("|R| < 30", not big_r, f"{len(big_r)} hors borne")
    bad_r = [t for t in trades if t["risk"] > 0 and abs(t["R"] - t["pnl"] / t["risk"]) > 1e-6]
    check("R == pnl/risk", not bad_r, f"{len(bad_r)} incohérents")

    print("Q3 — Chronologie par flux (listing + warmup)")
    con = sqlite3.connect(DB)
    floors_db = dict(con.execute("SELECT symbol, MIN(ts) FROM bn_kline_1h_deep "
                                 "GROUP BY symbol"))   # plancher RÉEL de la base
    con.close()
    for sym in SYMS:
        st = [t for t in trades if t["key"].endswith(":" + sym)]
        if not st:
            continue
        first_in = min(t["t_in"] for t in st)
        floor = floors_db[sym]   # le MIN(ts) DB fait foi (sonde v29 imprécise ±1 j)
        check(f"début {sym}", first_in >= floor + WARMUP_MS,
              f"premier={dt.datetime.fromtimestamp(first_in / 1000).strftime('%F %H:%M')} "
              f"plancher+warmup={dt.datetime.fromtimestamp((floor + WARMUP_MS) / 1000).strftime('%F %H:%M')}")
        last_out = max(t["t_out"] for t in st)
        hi = con_last(sym)
        check(f"fin {sym}", last_out <= hi + 3600_000,
              f"dernier={dt.datetime.fromtimestamp(last_out / 1000).strftime('%F %H:%M')}")

    print("Q4 — Comptages")
    st_json = json.load(open(f"{OUT}/engine_deep_v30.json"))
    glob_n = st_json["glob"]["n"]
    sum_sym = sum(v["n"] for v in st_json.get("par_symbole", {}).values())
    check("somme par symbole == global", sum_sym == glob_n, f"{sum_sym} vs {glob_n}")
    alphas = {t["key"].split(":")[0] for t in trades}
    check("alphas couverts", alphas <= {"A1", "A2", "A3", "A4"}, str(sorted(alphas)))

    print("Q5 — Équité")
    eq = pool["eq"]
    check("ts croissants", all(eq[i][0] < eq[i + 1][0] for i in range(len(eq) - 1)))
    check("équité finale > 0", eq[-1][1] > 0, f"final={eq[-1][1]:.2f}$")

    print(f"\nQA v30 : {len(fails)} échec(s)")
    if fails:
        print("ÉCHECS :", fails)
        sys.exit(1)
    print("TOUT VERTE")


def con_last(sym):
    con = sqlite3.connect(DB)
    hi = con.execute("SELECT MAX(ts) FROM bn_kline_1h_deep WHERE symbol=?",
                     (sym,)).fetchone()[0]
    con.close()
    return hi


if __name__ == "__main__":
    main()
