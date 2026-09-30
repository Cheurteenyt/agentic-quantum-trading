#!/usr/bin/env python3
"""SONDE BALEINES ON-CHAIN ASTER (T2, nuit 30/09) — poll du GET
bapi/futures/v1/public/future/broad-cast/list-latest-trade-event (10 derniers
trades on-chain publics, adresses wallet) toutes les --every secondes pendant
--minutes minutes. Dédup des events par tuple complet, stats : trades uniques,
adresses distinctes, tailles, symboles, sides, open/close, leviers.
Réutilisable : --minutes 18 --every 30 --out reports/aster_broadcast_probe.json
Pacing respecté (1 req / 30 s par défaut)."""
import argparse, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[2]
URL = ("https://www.asterdex.com/bapi/futures/v1/public/future/"
       "broad-cast/list-latest-trade-event")

FIELDS = ("p", "A", "a", "R", "s", "S", "t", "e", "L")


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=18)
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--out", default=str(ROOT / "reports" / "aster_broadcast_probe.json"))
    args = ap.parse_args()

    s = cffi.Session(impersonate="chrome131", timeout=15)
    t_end = time.monotonic() + args.minutes * 60
    uniq = {}          # tuple event -> first_seen_utc
    polls, errors = [], []
    n_polls = 0
    while time.monotonic() < t_end:
        t0 = datetime.now(timezone.utc).isoformat()
        try:
            r = s.get(URL, headers={
                "Origin": "https://www.asterdex.com",
                "Referer": "https://www.asterdex.com/en/futures/BTCUSDT",
                "Accept": "application/json"})
            data = r.json().get("data") or []
            new = 0
            for x in data:
                key = tuple(x.get(f) for f in FIELDS)
                if key not in uniq:
                    uniq[key] = t0
                    new += 1
            polls.append({"utc": t0, "status": r.status_code,
                          "n": len(data), "n_new": new})
            print(f"[{t0[11:19]}] HTTP {r.status_code} n={len(data)} "
                  f"new={new} cumul={len(uniq)}", flush=True)
        except Exception as ex:
            errors.append({"utc": t0, "err": str(ex)[:120]})
            print(f"[{t0[11:19]}] ERREUR {ex}", flush=True)
        n_polls += 1
        time.sleep(args.every)

    events = [dict(zip(("price", "action", "address", "size", "symbol",
                        "side", "margin", "etype", "leverage"), k),
                   first_seen=v)
              for k, v in uniq.items()]
    addrs = {e["address"] for e in events if e["address"]}
    sizes = sorted(x for x in (fnum(e["size"]) for e in events) if x is not None)
    prices = sorted(x for x in (fnum(e["price"]) for e in events) if x is not None)
    out = {
        "url": URL, "minutes": args.minutes, "every_s": args.every,
        "started_utc": polls[0]["utc"] if polls else None,
        "ended_utc": t0, "n_polls": n_polls, "n_errors": len(errors),
        "n_events_seen": sum(p["n"] for p in polls),
        "n_unique_events": len(uniq), "n_unique_addresses": len(addrs),
        "symbols": sorted({e["symbol"] for e in events if e["symbol"]}),
        "actions": sorted({e["action"] for e in events if e["action"]}),
        "sides": sorted({e["side"] for e in events if e["side"]}),
        "etypes": sorted({e["etype"] for e in events if e["etype"]}),
        "leverages": sorted({e["leverage"] for e in events if e["leverage"]},
                            key=lambda v: fnum(v) or 0),
        "size_min": sizes[0] if sizes else None,
        "size_p50": sizes[len(sizes)//2] if sizes else None,
        "size_max": sizes[-1] if sizes else None,
        "price_min": prices[0] if prices else None,
        "price_max": prices[-1] if prices else None,
        "polls": polls, "errors": errors, "events": events,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False))
    print(f"\n== {n_polls} polls, {len(uniq)} events uniques, "
          f"{len(addrs)} adresses, {len(out['symbols'])} symboles")
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
