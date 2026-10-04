# x_calls_fade_test.py — LE FADE DES CALLS X (le miroir du fade premium, design 05/10).
# Hypothèse : les calls X ne sont pas des signaux, ce sont des ÉVÉNEMENTS DE LIQUIDITÉ —
# le caller est positionné avant, ses followers achètent après = l'exit liquidity.
# Le côté CHASE (suivre le call) et le côté FADE (l'inverse) sont mesurés sur LES MÊMES trades
# — le contrôle inverse est inhérent.
#
# CONFIG GELÉE AVANT MESURE :
#   - Univers : x_calls direction IN (long, short), symbol+USDT couvert en klines 1h
#   - Entrée : close de la bougie 1h CONTENANT posted_at (le pump initial de la 1re heure
#     se joue DANS cette bougie — on entre après, à son close, exécutable)
#   - Chase : d × (close[H+1]/close[H] − 1) · Fade : −d × (…) — 28 bps RT les deux côtés
#   - Split temporel 70/30 · BLOC STATS mensuel
#   - Version 15m (bonus, granularité du design) : syms avec klines 15m, entrée à l'open de
#     la bougie 15m contenant T+15 min, sortie au close +45 min
#
# CRITÈRES PASS/FAIL ÉCRITS AVANT :
#   P1 fade espérance nette VAL > 0
#   P2 fade > chase sur les mêmes trades (le côté inversé gagne)
#   P3 fade WR VAL ≥ 52 %
#   P4 TRAIN et VAL fade positifs
#   KILL : fade ≤ 0 → la famille x-calls-fade meurt au registre (le domaine X reste
#   collecteur passif, assumé).

import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

XP = "data/warehouse/x_posts.db"
KL = "data/warehouse/klines.db"
COST_BPS = 28.0


def main():
    xcon = sqlite3.connect(f"file:{XP}?mode=ro", uri=True)
    calls = pd.read_sql_query(
        "SELECT c.call_id, c.symbol, c.direction, c.entry_price, "
        "       s.posted_at "
        "FROM x_calls c JOIN x_call_scores s USING(call_id) "
        "WHERE c.direction IN ('long','short')", xcon)
    xcon.close()
    calls["sym"] = calls["symbol"].str.upper() + "USDT"
    calls["ts"] = pd.to_datetime(calls["posted_at"], utc=True, format="mixed")
    print(f"calls long/short : {len(calls):,}")

    kcon = sqlite3.connect(f"file:{KL}?mode=ro", uri=True)
    syms = set(calls["sym"])
    rows = []
    for sym in sorted(syms):
        k = pd.read_sql_query(
            "SELECT open_time, close FROM klines WHERE symbol=? AND interval='1h' "
            "ORDER BY open_time", kcon, params=(sym,))
        if len(k) < 3:
            continue
        kts = pd.to_datetime(k["open_time"], unit="ms", utc=True)
        sub = calls[calls["sym"] == sym]
        closes = k["close"].to_numpy()
        for _, c in sub.iterrows():
            i = kts.searchsorted(c["ts"], side="right") - 1  # la bougie qui contient le call
            if i < 0 or i + 1 >= len(closes):
                continue
            d = 1.0 if c["direction"] == "long" else -1.0
            ret = closes[i + 1] / closes[i] - 1.0
            rows.append((c["call_id"], sym, c["ts"], d, ret,
                         d * ret * 1e4 - COST_BPS, -d * ret * 1e4 - COST_BPS))
    kcon.close()
    tr = pd.DataFrame(rows, columns=["call_id", "sym", "ts", "d", "ret",
                                     "chase_bps", "fade_bps"])
    tr["month"] = tr["ts"].dt.to_period("M").astype(str)
    t_min, t_max = tr["ts"].min(), tr["ts"].max()
    cutoff = t_min + 0.70 * (t_max - t_min)
    tr["period"] = np.where(tr["ts"] < cutoff, "TRAIN", "VAL")
    print(f"trades mesurables (1h) : {len(tr):,} sur {tr['sym'].nunique()} syms, "
          f"split à {cutoff.date()}")

    for per in ("TRAIN", "VAL"):
        s = tr[tr["period"] == per]
        if len(s):
            print(f"{per}: n={len(s):,} | CHASE WR {(s['chase_bps']>0).mean()*100:.1f}% "
                  f"esp {s['chase_bps'].mean():+.1f} bps | FADE WR {(s['fade_bps']>0).mean()*100:.1f}% "
                  f"esp {s['fade_bps'].mean():+.1f} bps")
    m = tr.groupby("month").agg(chase=("chase_bps", "mean"), fade=("fade_bps", "mean"),
                                n=("fade_bps", "count"))
    print("\nBLOC STATS mensuel (espérances bps) :")
    print(m.round(1).to_string())

    vt = tr[tr["period"] == "TRAIN"]; vv = tr[tr["period"] == "VAL"]
    checks = [
        ("P1 fade espérance VAL > 0", vv["fade_bps"].mean() > 0,
         f"{vv['fade_bps'].mean():+.1f} bps"),
        ("P2 fade > chase (les mêmes trades)",
         vv["fade_bps"].mean() > vv["chase_bps"].mean(),
         f"fade {vv['fade_bps'].mean():+.1f} vs chase {vv['chase_bps'].mean():+.1f}"),
        ("P3 fade WR VAL ≥ 52 %", (vv["fade_bps"] > 0).mean() >= 0.52,
         f"{(vv['fade_bps']>0).mean()*100:.1f} %"),
        ("P4 TRAIN et VAL positifs",
         vt["fade_bps"].mean() > 0 and vv["fade_bps"].mean() > 0,
         f"train {vt['fade_bps'].mean():+.1f} / val {vv['fade_bps'].mean():+.1f}"),
    ]
    print("\n== CRITÈRES PRÉ-ENREGISTRÉS ==")
    for name, ok, val in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:38s} {val}")
    fade_ok = all(ok for _, ok, _ in checks)
    print(f"\nVERDICT: {'VALIDÉ (x-calls-fade candidat wallet)' if fade_ok else 'KILL (la famille fade X meurt — X reste collecteur passif)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
