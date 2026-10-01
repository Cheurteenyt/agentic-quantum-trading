#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""x501 v31 — QA de la base DEEP 40 symboles et du portage du harnais v8 (docs/38).

Contrôles (exécution complète contre la DB locale om_v27.db — hors git) :
  Q1  contiguïté bn_kline_1h_deep (40 sym, gap <= 2 h ; l'unique trou ICPUSDT
      2022-08-31 23:00 -> 2022-09-27 02:00 est DOCUMENTÉ — absent de Binance,
      vérifié API) ;
  Q2  contiguïté bb_kline_1h_deep (12 sym, gap <= 2 h) ;
  Q3  zéro NULL taker sur bn (40 sym) ;
  Q4  funding deep (40 sym) : gap <= 8 h + 120 s ;
  Q5  cohérence cross-venue overlap (9 sym) : médiane <= 5 bps ;
  Q6  pool v8 deep (si X501_DEEP_POOL défini) : 868 trades, échelle V3, gate
      None, E[R] total bit à bit ;
  Q7  research JSON : cohérence interne des compteurs.

Sans data locale, Q1-Q6 sont SKIP déclarés (la QA reste PASS en CI — même
convention que les bancs data du domaine). stdlib pure.
"""
import json, os, sqlite3, sys

DB = os.environ.get("X501_DEEP_DB",
                    "/home/z/my-project/scripts/x501_v21_results/om_v27.db")
POOL = os.environ.get("X501_DEEP_POOL",
                      "/home/z/my-project/scripts/x501_v8_results_deep_v31/pool_v8_deep.pkl")
RES = os.environ.get("X501_DEEP_RES",
                     "/home/z/my-project/scripts/x501_v8_results_deep_v31/research_v8_deep.json")
ICP_TROU = ("ICPUSDT", 1661986800000, 1664244000000)   # 2022-08-31 23:00 -> 2022-09-27 01:00 UTC
B1H = 3600 * 1000

fails, checks, skips = [], 0, 0


def check(name, cond, detail=""):
    global checks
    checks += 1
    if cond:
        print(f"  PASS {name} {detail}")
    else:
        print(f"  FAIL {name} {detail}")
        fails.append(name)


def skip(name, why):
    global skips
    skips += 1
    print(f"  SKIP {name} ({why})")


def main():
    has_db = os.path.exists(DB)
    print(f"=== QA deep40 v31 — DB {'présente' if has_db else 'ABSENTE (skips déclarés)'} ===")
    gaps_icp_ok = True
    if has_db:
        db = sqlite3.connect(DB, timeout=60)
        cur = db.cursor()
        # Q1
        syms = [r[0] for r in cur.execute(
            "SELECT DISTINCT symbol FROM bn_kline_1h_deep ORDER BY symbol")]
        check("Q1a.bn-40symboles", len(syms) == 40, f"({len(syms)})")
        bad = []
        for s in syms:
            ts = [r[0] for r in cur.execute(
                "SELECT ts FROM bn_kline_1h_deep WHERE symbol=? ORDER BY ts", (s,))]
            for a, b in zip(ts, ts[1:]):
                if b - a > 2 * B1H:
                    if s == ICP_TROU[0] and a == ICP_TROU[1] and b == ICP_TROU[2]:
                        continue           # trou documenté (absent chez Binance)
                    bad.append((s, a, b))
        check("Q1b.contiguite-bn", not bad, f"({len(bad)} trous non documentés)")
        # Q2
        syms_bb = [r[0] for r in cur.execute(
            "SELECT DISTINCT symbol FROM bb_kline_1h_deep ORDER BY symbol")]
        check("Q2a.bb-12symboles", len(syms_bb) == 12, f"({len(syms_bb)})")
        bad = []
        for s in syms_bb:
            ts = [r[0] for r in cur.execute(
                "SELECT ts FROM bb_kline_1h_deep WHERE symbol=? ORDER BY ts", (s,))]
            for a, b in zip(ts, ts[1:]):
                if b - a > 2 * B1H:
                    bad.append((s, a, b))
        check("Q2b.contiguite-bb", not bad, f"({len(bad)} trous)")
        # Q3
        nulls = cur.execute(
            "SELECT COUNT(*) FROM bn_kline_1h_deep WHERE taker_buy IS NULL").fetchone()[0]
        check("Q3.zero-null-taker", nulls == 0, f"({nulls})")
        # Q4
        bad = []
        for s in [r[0] for r in cur.execute(
                "SELECT DISTINCT symbol FROM bn_funding_deep")]:
            ts = [r[0] for r in cur.execute(
                "SELECT ts FROM bn_funding_deep WHERE symbol=? ORDER BY ts", (s,))]
            mx = max((b - a for a, b in zip(ts, ts[1:])), default=0)
            if mx > 28800 + 120:
                bad.append((s, mx))
        check("Q4.funding-contigu", not bad, f"({len(bad)} gaps > 8h)")
        # Q5
        devs_med = []
        for s in ("BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
                  "LINKUSDT", "DOGEUSDT", "SOLUSDT", "AVAXUSDT"):
            rows = cur.execute(
                "SELECT a.close, b.close FROM bb_kline_1h_deep a "
                "JOIN bn_kline_1h_deep b ON a.ts=b.ts "
                "WHERE a.symbol=? AND b.symbol=?", (s, s)).fetchall()
            if rows:
                d = sorted(abs(c1 - c2) / c1 * 1e4 for c1, c2 in rows)
                devs_med.append(d[len(d) // 2])
        check("Q5.cross-venue-med<=5bps",
              len(devs_med) == 9 and max(devs_med) <= 5.0,
              f"(méd max {max(devs_med) if devs_med else None} bps)")
        db.close()
    else:
        skip("Q1..Q5", "DB locale absente")
    # Q6 pool
    import pickle
    if os.path.exists(POOL):
        p = pickle.load(open(POOL, "rb"))
        trs = p["trades"]
        er = sum(t["R"] for t in trs) / len(trs)
        check("Q6a.pool-868", len(trs) == 868, f"({len(trs)})")
        check("Q6b.V3-gate-off", p["exit_variant"] == "V3" and p["gate_th"] is None)
        check("Q6c.ER-bit-a-bit", abs(er - 0.09253917067250746) < 1e-12, f"(E[R] {er:.15f})")
        check("Q6d.univers-40", len(p["universe"]) == 40)
    else:
        skip("Q6", "pool pkl local absent")
    # Q7 research JSON
    if os.path.exists(RES):
        r = json.load(open(RES))
        check("Q7a.research-n", r["pool"]["n"] == 868)
        check("Q7b.research-er", abs(r["pool"]["er_total"] - 0.09253917067250746) < 1e-12)
        check("Q7c.research-cadence", abs(r["pool"]["cadence_hist"] - 10.49) < 0.05)
        check("Q7d.fenetre-828mois", abs(r["fenetre"]["mois"] - 82.8) < 0.1)
    else:
        skip("Q7", "research JSON absent")
    print(f"=== {checks} contrôles, {len(fails)} échec(s), {skips} skip(s) ===")
    if fails:
        print("ECHECS:", fails)
        sys.exit(1)
    print("QA deep40 v31 : PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
