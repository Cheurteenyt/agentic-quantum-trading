#!/usr/bin/env python3
"""ONE-SHOT endurance REST Aster (T3, 30/09) — compteur de poids, latences,
limites de batchs, échelle de charge 10→1500 req/min. Sécurité : gouverneur
sur X-MBX-USED-WEIGHT-1M (hold ≥ 1400, abort ≥ 1550 — interdiction 1680),
STOP immédiat au premier 429 + sonde de récupération. Aucune écriture DB.
Sortie : reports/aster_endurance_rest.json"""
import json, time, statistics
from pathlib import Path
from curl_cffi import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "aster_endurance_rest.json"
BASE = "https://fapi.asterdex.com"
HOLD_W, ABORT_W = 1400, 1550
T0 = time.time()
rows, events = [], []
cur_session = requests.Session(impersonate="chrome131")


def probe(url, session=None, timeout=10):
    s = session or cur_session
    t = time.monotonic()
    try:
        r = s.get(url, timeout=timeout)
    except Exception as e:
        return {"exc": repr(e)[:120], "t_rel": round(time.time() - T0, 3)}
    el = (time.monotonic() - t) * 1000
    h = {k.lower(): v for k, v in r.headers.items()}
    srv = None
    if r.status_code == 200 and r.content:
        try:
            j = r.json()
            srv = j.get("serverTime") if isinstance(j, dict) else None
        except Exception:
            srv = None
    return {
        "t_rel": round(time.time() - T0, 3), "status": r.status_code,
        "w": h.get("x-mbx-used-weight-1m"), "ms": round(el, 1),
        "xrt": h.get("x-response-time"), "pop": h.get("x-amz-cf-pop"),
        "srv": srv, "len": len(r.content),
    }


def log_row(phase, url, **kw):
    d = probe(url, **kw)
    d["phase"] = phase
    d["ep"] = url.split("/fapi/")[-1].split("?")[0]
    rows.append(d)
    return d


def pct(vals, q):
    if not vals:
        return None
    vals = sorted(vals)
    i = min(len(vals) - 1, max(0, int(round(q * (len(vals) - 1)))))
    return vals[i]


def w_of(d):
    try:
        return int(d["w"]) if d.get("w") else None
    except Exception:
        return None


# ---- 1. BASELINE : dynamique du compteur, 90 s ----
print("PHASE baseline", flush=True)
for _ in range(30):
    log_row("baseline", f"{BASE}/fapi/v1/time")
    time.sleep(3)

# ---- 2. CONNTEST : compteur par connexion/pod ou global IP ? ----
print("PHASE conntest", flush=True)
sa = requests.Session(impersonate="chrome131")
sb = requests.Session(impersonate="chrome131")
wa = [w_of(log_row("conntest", f"{BASE}/fapi/v1/time", session=sa)) for _ in range(3)]
wb = w_of(log_row("conntest", f"{BASE}/fapi/v1/time", session=sb))
wa4 = w_of(log_row("conntest", f"{BASE}/fapi/v1/time", session=sa))
events.append({"ev": "conntest", "sessA": wa, "sessB": wb, "sessA_after": wa4})

# ---- 3. LATENCE : 20 échantillons chacun, 1 s de spacing ----
print("PHASE latency", flush=True)
lat_eps = [
    ("ping", f"{BASE}/fapi/v1/ping"),
    ("klines500", f"{BASE}/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=500"),
    ("depth500", f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=500"),
    ("premiumIndex", f"{BASE}/fapi/v1/premiumIndex?symbol=BTCUSDT"),
]
for name, url in lat_eps:
    for _ in range(20):
        log_row("latency", url)
        time.sleep(1.0)

# ---- 4. BATCHS : limites réelles (delta de poids propre) ----
print("PHASE batches", flush=True)
batch = []
def batch_case(name, url):
    before = w_of(probe(f"{BASE}/fapi/v1/time"))
    time.sleep(0.3)
    d = log_row("batches", url)
    after_w = w_of(d)
    body = None
    try:
        r = cur_session.get(url, timeout=15)
        body = r.json()
    except Exception:
        pass
    n = len(body) if isinstance(body, list) else None
    batch.append({"case": name, "status": d.get("status"), "w_read": after_w,
                  "w_before": before, "delta": (after_w - before) if (after_w and before) else None,
                  "n_items": n, "ms": d.get("ms"), "srv": d.get("srv")})
    print("  batch", name, batch[-1], flush=True)
    time.sleep(2)

batch_case("klines_l1000", f"{BASE}/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=1000")
batch_case("klines_l1500", f"{BASE}/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=1500")
batch_case("klines_l5000", f"{BASE}/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=5000")
batch_case("klines_l10000", f"{BASE}/fapi/v1/klines?symbol=BTCUSDT&interval=1m&limit=10000")
batch_case("depth_l1000", f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=1000")
batch_case("depth_l1001", f"{BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=1001")
batch_case("aggTrades_l1000", f"{BASE}/fapi/v1/aggTrades?symbol=BTCUSDT&limit=1000")
batch_case("aggTrades_l2000", f"{BASE}/fapi/v1/aggTrades?symbol=BTCUSDT&limit=2000")

# ---- 5. ÉCHELLE : 10→1500 req/min, 100 s par palier, gouverneur ----
print("PHASE ladder", flush=True)
ladder_meta = []
rates = [10, 300, 600, 900, 1200, 1500]
aborted = False
for rate in rates:
    if aborted:
        ladder_meta.append({"rate": rate, "skipped": "aborted_before"})
        continue
    meta = {"rate": rate, "sent": 0, "hold_s": 0.0, "max_w": None, "429": 0}
    t_end = time.time() + 100
    last_w = None
    while time.time() < t_end:
        if last_w is not None and last_w >= ABORT_W:
            events.append({"ev": "GOVERNOR_ABORT", "w": last_w, "rate": rate})
            aborted = True
            break
        if last_w is not None and last_w >= HOLD_W:
            t_hold = time.time()
            while time.time() < min(t_end, t_hold + 90):
                d = log_row(f"hold_r{rate}", f"{BASE}/fapi/v1/time")
                last_w = w_of(d)
                meta["hold_s"] += 3
                if last_w is None or last_w < 1000:
                    break
                time.sleep(3)
            continue
        d = log_row(f"r{rate}", f"{BASE}/fapi/v1/time")
        meta["sent"] += 1
        last_w = w_of(d)
        if last_w is not None:
            meta["max_w"] = max(meta["max_w"] or 0, last_w)
        if d.get("status") == 429:
            meta["429"] += 1
            events.append({"ev": "429_FIRST", "t_rel": d.get("t_rel"),
                           "last_w": last_w, "rate": rate, "row": d})
            aborted = True
            break
        time.sleep(max(0.0, 60.0 / rate))
    ladder_meta.append(meta)
    print("  ladder", meta, flush=True)
    if not aborted:
        time.sleep(10)

# ---- 6. RÉCUPÉRATION si 429 ----
if aborted and any(e.get("ev") == "429_FIRST" for e in events):
    print("PHASE recovery", flush=True)
    rec = {"probes": []}
    for i in range(60):
        d = probe(f"{BASE}/fapi/v1/time")
        rec["probes"].append(d)
        if d.get("status") == 200:
            rec["recovered_at"] = d.get("t_rel")
            rec["full"] = d
            break
        time.sleep(5)
    events.append({"ev": "RECOVERY", **rec})
    print("  recovery:", rec.get("recovered_at", "NOT_RECOVERED"), flush=True)

lat_summary = {}
by_ep = {}
for r in rows:
    if r.get("phase") == "latency" and r.get("status") == 200:
        by_ep.setdefault(r["ep"], []).append(r["ms"])
for ep, vals in by_ep.items():
    lat_summary[ep] = {"n": len(vals), "p50": pct(vals, .5), "p95": pct(vals, .95),
                       "min": min(vals), "max": max(vals)}

OUT.write_text(json.dumps({"t0": T0, "rows": rows, "events": events,
                           "ladder": ladder_meta, "batches": batch,
                           "latency_summary": lat_summary}, indent=1))
print("WROTE", OUT, "rows:", len(rows), "aborted:", aborted, flush=True)
