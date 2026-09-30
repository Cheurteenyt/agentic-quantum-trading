#!/usr/bin/env python3
"""STABILITÉ LEADERBOARD ASTER (T2) — compare deux crawls (run1 vs run2)
par combo : jaccard des adresses, corrélation de rang Spearman sur les
adresses communes, chevauchement du top-10, drift moyen de rang.
Usage : aster_leaderboard_stability.py --a run1.json --b run2.json --out out.json"""
import argparse, json, sys
from pathlib import Path


def ranks_by_addr(doc, period, sort):
    out = {}
    for r in doc["rows"]:
        if r["period"] == period and r["sort"] == sort:
            out[r["address"]] = int(r["rank"])
    return out


def spearman(pairs):
    n = len(pairs)
    if n < 3:
        return None
    def rank(v):
        s = sorted(range(n), key=lambda i: v[i])
        rk = [0.0] * n
        for pos, i in enumerate(s):
            rk[i] = pos + 1
        return rk
    ra = rank([p[0] for p in pairs]); rb = rank([p[1] for p in pairs])
    ma, mb = sum(ra)/n, sum(rb)/n
    num = sum((ra[i]-ma)*(rb[i]-mb) for i in range(n))
    da = sum((ra[i]-ma)**2 for i in range(n))**0.5
    db = sum((rb[i]-mb)**2 for i in range(n))**0.5
    return num/(da*db) if da and db else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True); ap.add_argument("--b", required=True)
    ap.add_argument("--periods", nargs="+", default=["d7", "d30"])
    ap.add_argument("--sorts", nargs="+", default=["pnl_rank", "volume_rank"])
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    A = json.loads(Path(args.a).read_text())
    B = json.loads(Path(args.b).read_text())
    res = {"a": A["tag"], "b": B["tag"],
           "delta_min": None, "combos": {}}
    try:
        from datetime import datetime
        ta = datetime.fromisoformat(A["started_utc"])
        tb = datetime.fromisoformat(B["started_utc"])
        res["delta_min"] = round((tb - ta).total_seconds() / 60, 1)
    except Exception:
        pass
    for period in args.periods:
        for sort in args.sorts:
            ra, rb = ranks_by_addr(A, period, sort), ranks_by_addr(B, period, sort)
            ka, kb = set(ra), set(rb)
            common = ka & kb
            pairs = [(ra[x], rb[x]) for x in common]
            top10_b = set(sorted(rb, key=rb.get)[:10])
            top10_a = set(sorted(ra, key=ra.get)[:10])
            res["combos"][f"{period}/{sort}"] = {
                "n_a": len(ka), "n_b": len(kb), "n_common": len(common),
                "jaccard": round(len(common) / len(ka | kb), 4),
                "spearman": round(spearman(pairs), 4) if spearman(pairs) is not None else None,
                "top10_overlap": len(top10_a & top10_b),
                "mean_abs_rank_drift": round(sum(abs(x-y) for x, y in pairs) / len(pairs), 1) if pairs else None}
    print(json.dumps(res, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
