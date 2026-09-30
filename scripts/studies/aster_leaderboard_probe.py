#!/usr/bin/env python3
"""PROBE LEADERBOARD ASTER (nuit 30/09) — contre-test du POST
bapi/futures/v1/public/campaign/trade/pro/leaderboard découvert par le census
: est-ce que l'API HONORE ses paramètres (period/sort/symbol/address/rows)
ou les ignore-t-elle (leçon fomo tradingActivity = placebo) ? Variantes
rejouées curl_cffi chrome131, comparaison des réponses (adresses différentes ?).
Sortie : reports/aster_leaderboard_probe.json + stdout."""
import json, sys
from pathlib import Path
from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "aster_leaderboard_probe.json"
URL = "https://www.asterdex.com/bapi/futures/v1/public/campaign/trade/pro/leaderboard"


def call(s, body):
    r = s.post(URL, json=body, headers={
        "Origin": "https://www.asterdex.com",
        "Referer": "https://www.asterdex.com/en/trading-leaderboard",
        "Accept": "application/json"})
    try:
        j = r.json()
    except Exception:
        return {"status": r.status_code, "raw": r.text[:120]}
    d = j.get("data") or []
    return {"status": r.status_code, "total": j.get("total"),
            "n": len(d), "first3": [{"rank": x.get("rank"), "addr": x.get("address", "")[:14],
                                     "pnl": round(x.get("pnl") or 0, 2),
                                     "vol": round(x.get("volume") or 0, 2),
                                     "symbol": x.get("symbol")}
                                    for x in d[:3]]}


def main() -> int:
    s = cffi.Session(impersonate="chrome131", timeout=15)
    tests = [
        ("base d30", {"period": "d30", "sort": "pnl_rank", "order": "asc",
                      "page": 1, "rows": 10, "symbol": "", "address": ""}),
        ("rows=100", {"period": "d30", "sort": "pnl_rank", "order": "asc",
                      "page": 1, "rows": 100, "symbol": "", "address": ""}),
        ("rows=1000", {"period": "d30", "sort": "pnl_rank", "order": "asc",
                       "page": 1, "rows": 1000, "symbol": "", "address": ""}),
        ("period=d1", {"period": "d1", "sort": "pnl_rank", "order": "asc",
                       "page": 1, "rows": 10, "symbol": "", "address": ""}),
        ("period=d7", {"period": "d7", "sort": "pnl_rank", "order": "asc",
                       "page": 1, "rows": 10, "symbol": "", "address": ""}),
        ("period=all", {"period": "all", "sort": "pnl_rank", "order": "asc",
                        "page": 1, "rows": 10, "symbol": "", "address": ""}),
        ("sort=volume_rank", {"period": "d30", "sort": "volume_rank", "order": "desc",
                              "page": 1, "rows": 10, "symbol": "", "address": ""}),
        ("symbol=BTCUSDT", {"period": "d30", "sort": "pnl_rank", "order": "asc",
                            "page": 1, "rows": 10, "symbol": "BTCUSDT", "address": ""}),
        ("page=2", {"period": "d30", "sort": "pnl_rank", "order": "asc",
                    "page": 2, "rows": 10, "symbol": "", "address": ""}),
    ]
    results, base_addrs = [], None
    for name, body in tests:
        r = call(s, body)
        if name == "base d30":
            base_addrs = {x["addr"] for x in r["first3"]}
        results.append({"test": name, "body": body, **r})
        print(f"[{name:16s}] {r.get('status')} total={r.get('total')} n={r.get('n')} "
              f"first={r.get('first3', [{}])[0] if r.get('first3') else '-'}")
    # discriminations
    by = {r["test"]: r for r in results}
    print("\n--- VERDICTS ---")
    if by["period=d1"]["first3"] != by["base d30"]["first3"]:
        print("period HONORÉ (d1 ≠ d30)")
    else:
        print("!! period IGNORÉ (d1 == d30) — placebo")
    if by["sort=volume_rank"]["first3"] != by["base d30"]["first3"]:
        print("sort HONORÉ (volume_rank ≠ pnl_rank)")
    else:
        print("!! sort IGNORÉ")
    if by["symbol=BTCUSDT"]["first3"] != by["base d30"]["first3"]:
        print("symbol HONORÉ")
    else:
        print("!! symbol IGNORÉ")
    if by["page=2"]["first3"] != by["base d30"]["first3"]:
        print("page HONORÉE")
    else:
        print("!! page IGNORÉE")
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\n→ {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
