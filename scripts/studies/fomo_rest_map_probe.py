#!/usr/bin/env python3
"""SNIFFER PASSIF CARTE REST (29/09) — la page neuve de fomo ne rend pas l'app
(écran 'Try again' puis blanc : 2e connexion concurrente refusée) → on n'attache
QUE des listeners CDP sur la page RÉSIDENTE du worker fomo_dom_worker (pid
actif :9222) sans la toucher. Le worker navigue lui-même les surfaces (SCHEDULE
cad 5-60 min) → on capture les XHR prod-api au fil de ses cycles.
Modes : --sniff SECONDS (append capture JSON) | --replay (rejoue en python pur
curl_cffi chrome131, verdict 200/4xx + forme). One-shot LECTURE SEULE."""
import json, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "fomo_rest_map_capture.json"
CDP = "http://127.0.0.1:9222"
NOISE = ("posthog", "sentry", "analytics", "google", "sentry.io", "doubleclick")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/153.0.0.0 Safari/537.36")
ID_PAT = re.compile(
    r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?=/|\?|$)|"
    r"/(0x[0-9a-fA-F]{8,}|[1-9A-HJ-NP-Za-km-z]{32,})(?=/|\?|$)", re.I)


def load_capture() -> dict:
    if OUT.exists():
        try:
            return json.loads(OUT.read_text())
        except Exception:
            pass
    return {"requests": {}, "replay": [], "hrefs": {}}


def template(u: str) -> str:
    t = ID_PAT.sub(lambda m: "/" + ("<uuid>" if m.group(1) else "<id>"), u)
    # normalise aussi les ids en query (tokenAddress, userId, curseurs…)
    t = re.sub(r"((?:address|Id|Time|address\b)=[0-9a-fA-Fx%.\-]{10,})", "=<qv>", t)
    return re.sub(r"=[0-9]{10,}", "=<num>", t)


def read_jwt() -> str | None:
    import base64
    best, best_exp = None, 0
    for p in (ROOT / "data/fomo/ws_jwt_cache.txt", ROOT / "data/fomo/jwt_cache.json"):
        try:
            raw = p.read_text().strip()
            jwt = (json.loads(raw).get("jwt") or json.loads(raw).get("token")
                   if raw.startswith("{") else raw.strip().strip('"'))
            b = jwt.split(".")[1] + "=" * (-len(jwt.split(".")[1]) % 4)
            e = json.loads(base64.urlsafe_b64decode(b)).get("exp", 0)
            if e > best_exp:
                best, best_exp = jwt, e
        except Exception:
            continue
    return best if best_exp > time.time() + 300 else None


def sniff(seconds: int) -> int:
    from patchright.sync_api import sync_playwright
    cap = load_capture()
    reqs = cap["requests"]
    pw = sync_playwright().start()
    t0 = time.time()

    def on_request(req):
        u = req.url
        if "prod-api.fomo.family" in u and not any(n in u for n in NOISE):
            r = reqs.setdefault(u, {"method": req.method, "status": None,
                                    "ctype": None, "body": None,
                                    "post_data": None, "seen": 0})
            r["seen"] = r.get("seen", 0) + 1
            if r["method"] == "POST" and not r["post_data"]:
                try:
                    r["post_data"] = (req.post_data or "")[:300]
                except Exception:
                    pass

    def on_response(resp):
        u = resp.url
        r = reqs.get(u)
        if r is None:
            return
        if r["status"] is None:
            print(f"  [{int(time.time() - t0):4d}s] {resp.status} "
                  f"{u.replace('https://prod-api.fomo.family', '')[:110]}",
                  flush=True)
        r["status"] = resp.status
        try:
            ct = resp.headers.get("content-type", "")
            r["ctype"] = ct
            if "json" in ct and not r["body"]:
                r["body"] = resp.text()[:2500]
        except Exception:
            pass

    def attach_all(attached) -> int:
        browser = pw.chromium.connect_over_cdp(CDP, timeout=8000)
        n = 0
        for ctx in browser.contexts:
            ctx.on("page", lambda p: (attached.add(id(p)),
                                      p.on("request", on_request),
                                      p.on("response", on_response)))
            for p in ctx.pages:
                if id(p) in attached:
                    continue
                attached.add(id(p))
                p.on("request", on_request)
                p.on("response", on_response)
                n += 1
        return n

    try:
        attached = set()
        while time.time() - t0 < seconds:
            try:
                n = attach_all(attached)
                print(f"attaché (+{n} pages) [{int(time.time() - t0)}s]",
                      flush=True)
            except Exception as e:
                print(f"CDP ERR {str(e)[:60]} — retry 10 s "
                      f"(le navigateur a pu être restart)", flush=True)
                attached.clear()
                time.sleep(10)
                continue
            # re-attachement périodique : le worker purge/recrée ses pages,
            # fomo-browser peut être restart par le worker lui-même
            time.sleep(20)
    finally:
        pw.stop()
        OUT.write_text(json.dumps(cap, ensure_ascii=False, indent=1))
        print(f"\ncapture ({len(reqs)} URLs) → {OUT}")
    return 0


def shape_of(resp) -> str:
    try:
        d = resp.json()
        body = d.get("responseObject", d) if isinstance(d, dict) else d
        if isinstance(body, list):
            k = sorted(body[0])[:12] if body and isinstance(body[0], dict) else "-"
            return f"list[{len(body)}] keys0={k}"
        if isinstance(body, dict):
            return f"dict keys={sorted(body)[:12]}"
        return f"{type(body).__name__}"
    except Exception:
        return "non-json"


def replay() -> int:
    jwt = read_jwt()
    if not jwt:
        print("JWT absent/périmé — STOP")
        return 1
    from curl_cffi import requests as cffi
    h = {"user-agent": UA, "authorization": f"Bearer {jwt}",
         "origin": "https://fomo.family", "referer": "https://fomo.family/"}
    cap = load_capture()
    reqs = cap["requests"]
    out, seen = [], set()
    print(f"=== REPLAY {len(reqs)} URLs capturées (pacing 1.2 s) ===")
    for u, r in sorted(reqs.items()):
        t = template(u)
        if r["method"] != "GET":
            out.append({"url": u, "template": t, "method": r["method"],
                        "replay": "POST non rejoué", "post_data": r.get("post_data")})
            continue
        if t in seen:
            out.append({"url": u, "template": t, "replay": "DUP"})
            continue
        seen.add(t)
        try:
            resp = cffi.get(u, headers=h, impersonate="chrome131", timeout=15)
            code, sh = resp.status_code, shape_of(resp)
        except Exception as e:
            code, sh = None, f"ERR {str(e)[:70]}"
        time.sleep(1.2)
        out.append({"url": u, "template": t, "status_dom": r["status"],
                    "replay": code, "shape": sh[:220],
                    "body_dom": (r.get("body") or "")[:900],
                    "post_data": r.get("post_data")})
        print(f"  DOM {r['status']} → REPLAY {code} {t[:95]}")
        print(f"        ↳ {sh[:160]}")
    cap["replay"] = out
    OUT.write_text(json.dumps(cap, ensure_ascii=False, indent=1))
    print(f"capture+replay → {OUT}")
    return 0


def main() -> int:
    if "--replay" in sys.argv:
        return replay()
    sec = 560
    for i, a in enumerate(sys.argv):
        if a == "--sniff" and i + 1 < len(sys.argv):
            sec = int(sys.argv[i + 1])
    return sniff(sec)


if __name__ == "__main__":
    sys.exit(main())
