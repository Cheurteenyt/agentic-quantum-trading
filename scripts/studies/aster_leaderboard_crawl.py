#!/usr/bin/env python3
"""CRAWL LEADERBOARD ASTER (T2, nuit 30/09) — pagination complète du POST
bapi/futures/v1/public/campaign/trade/pro/leaderboard : period(s) x sort(s),
page par page (rows=100) jusqu'à épuisement (page vide OU adresses déjà vues
OU max-pages). Dédup par adresse, stats de distribution PnL, recouvrement
pnl_rank vs volume_rank. Réutilisable : --periods d7 d30 --sorts pnl_rank
volume_rank --tag run1 --out reports/aster_leaderboard_full.json
Pacing >= 0.5 s entre requêtes (header de poids absent sur bapi)."""
import argparse, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[2]
URL = "https://www.asterdex.com/bapi/futures/v1/public/campaign/trade/pro/leaderboard"


def pct(sorted_vals, q):
    """Percentile q (0-100) sur liste déjà triée."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q / 100.0
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def crawl_combo(s, period, sort, rows, max_pages, pacing, log):
    """Pagine un combo (period, sort). Retourne dict + rows uniques."""
    seen_addrs, pages_meta, all_rows = {}, [], []
    reason = "max_pages"
    for page in range(1, max_pages + 1):
        body = {"period": period, "sort": sort, "order": "asc",
                "page": page, "rows": rows, "symbol": "", "address": ""}
        r = s.post(URL, json=body, headers={
            "Origin": "https://www.asterdex.com",
            "Referer": "https://www.asterdex.com/en/trading-leaderboard",
            "Accept": "application/json"})
        try:
            j = r.json()
        except Exception:
            pages_meta.append({"page": page, "status": r.status_code, "n": 0,
                               "error": r.text[:100]})
            log(f"  [{period}/{sort}] page {page}: HTTP {r.status_code} non-JSON, stop")
            reason = "http_error"
            break
        data = j.get("data") or []
        new = [x for x in data if x.get("address") and x["address"] not in seen_addrs]
        pages_meta.append({"page": page, "status": r.status_code,
                           "n": len(data), "n_new": len(new),
                           "total_reported": j.get("total")})
        log(f"  [{period}/{sort}] page {page}: {len(data)} rows "
            f"({len(new)} nouvelles, total_api={j.get('total')})")
        for x in new:
            seen_addrs[x["address"]] = True
        all_rows.extend(new)
        if not data:
            reason = "empty"
            break
        if len(new) == 0:
            reason = "duplicate"  # l'API repart en boucle sur la page 1
            break
        time.sleep(pacing)
    return {"period": period, "sort": sort, "pages": pages_meta,
            "n_unique": len(seen_addrs), "exhausted_by": reason}, all_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--periods", nargs="+", default=["d7", "d30"])
    ap.add_argument("--sorts", nargs="+", default=["pnl_rank", "volume_rank"])
    ap.add_argument("--rows", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--pacing", type=float, default=0.6)
    ap.add_argument("--tag", default="run1")
    ap.add_argument("--out", default=str(ROOT / "reports" / "aster_leaderboard_full.json"))
    args = ap.parse_args()

    def log(m):
        print(m, flush=True)

    s = cffi.Session(impersonate="chrome131", timeout=15)
    out = {"tag": args.tag, "url": URL, "rows_per_page": args.rows,
           "started_utc": datetime.now(timezone.utc).isoformat(),
           "combos": {}, "rows": []}
    for period in args.periods:
        for sort in args.sorts:
            meta, rows = crawl_combo(s, period, sort, args.rows,
                                     args.max_pages, args.pacing, log)
            out["combos"][f"{period}/{sort}"] = meta
            for x in rows:
                tw = {k: v for k, v in x.items()
                      if "twitter" in k.lower() or "twitt" in k.lower()}
                out["rows"].append({
                    "period": period, "sort": sort, "address": x.get("address"),
                    "rank": x.get("rank"), "pnl": x.get("pnl"),
                    "volume": x.get("volume"), "twitter": tw or None,
                    "symbol": x.get("symbol") or None,
                    "raw": x})
            time.sleep(args.pacing)

    # --- stats distribution PnL par période (depuis le sort pnl_rank) ---
    out["stats"] = {}
    for period in args.periods:
        pnl_rows = [r for r in out["rows"]
                    if r["period"] == period and r["sort"] == "pnl_rank"
                    and isinstance(r.get("pnl"), (int, float))]
        vals = sorted(r["pnl"] for r in pnl_rows)
        if vals:
            top1_cut = pct(vals, 99)
            out["stats"][period] = {
                "n_pnl_sorted": len(vals),
                "pnl_min": vals[0], "pnl_max": vals[-1],
                "pnl_p50": pct(vals, 50), "pnl_p90": pct(vals, 90),
                "pnl_p99": top1_cut,
                "frac_pnl_gt0": round(sum(v > 0 for v in vals) / len(vals), 4),
                "n_top1pct": max(1, round(len(vals) * 0.01)),
                "top1pct_cutoff": top1_cut}
    # --- recouvrement pnl_rank vs volume_rank par période ---
    out["overlap"] = {}
    for period in args.periods:
        a = {r["address"] for r in out["rows"]
             if r["period"] == period and r["sort"] == "pnl_rank"}
        b = {r["address"] for r in out["rows"]
             if r["period"] == period and r["sort"] == "volume_rank"}
        if a and b:
            inter = a & b
            out["overlap"][period] = {
                "n_pnl": len(a), "n_vol": len(b), "n_both": len(inter),
                "jaccard": round(len(inter) / len(a | b), 4)}
    out["n_addresses_global"] = len({r["address"] for r in out["rows"]})
    out["finished_utc"] = datetime.now(timezone.utc).isoformat()
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False))
    log(f"\n== {args.tag}: {out['n_addresses_global']} adresses uniques globales")
    for k, v in out["combos"].items():
        log(f"  {k}: n_unique={v['n_unique']} pages={len(v['pages'])} "
            f"stop={v['exhausted_by']}")
    for k, v in out["stats"].items():
        log(f"  stats {k}: p50={v['pnl_p50']:.0f} p90={v['pnl_p90']:.0f} "
            f"p99={v['pnl_p99']:.0f} frac>0={v['frac_pnl_gt0']}")
    log(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
