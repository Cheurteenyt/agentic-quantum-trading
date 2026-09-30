#!/usr/bin/env python3
"""SONDE UI ASTERDEX (RE, 30/09) — transposition des patterns fomo à
asterdex.com : navigation de l'UI futures dans un chromium patchright DÉDIÉ
(profil /tmp, jamais les fomo-browser :9222/:9223), capture de TOUS les flux
au niveau navigateur — frames WS via page.on('websocket')
(framesent/framereceived, insensible aux mondes isolés) + XHR via
page.on('request'/'response') (URL exactes + params + corps JSON). Headless
d'abord (HEADLESS=0 pour basculer headed si les données ne rendent pas).
Sortie : reports/aster_ui_capture.json + résumé stdout. Dump en finally."""
import json, os, shutil, sys
from pathlib import Path
from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "aster_ui_capture.json"
PROFILE = Path("/tmp/aster-ui-probe-profile")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
NOISE = ("sentry", "posthog", "analytics", "googletag", "doubleclick",
         "clarity.ms", "hotjar", "facebook", "cloudflareinsights", "challenges.cloudflare")
HDRS = ("origin", "referer", "user-agent", "authorization", "content-type")
CANDIDATES = ["https://www.asterdex.com/en/futures/BTCUSDT",
              "https://www.asterdex.com/futures/BTCUSDT",
              "https://www.asterdex.com/en/futures/ASTERUSDT",
              "https://asterdex.com/en/futures/BTCUSDT"]
VIEWS = ("Recent Trades", "Trades", "Funding History", "Funding", "Leaderboard",
         "History", "Positions", "Depth", "Order Book")
MAX_FRAMES = 5000


def main() -> int:
    frames, reqs = [], {}

    def on_ws(ws):
        frames.append({"dir": "open", "url": ws.url, "data": ""})

        def on_frame(direction):
            def h(p):
                if len(frames) < MAX_FRAMES:
                    frames.append({"dir": direction, "url": ws.url,
                                   "data": str(p)[:2500]})
            return h
        ws.on("framesent", on_frame("send"))
        ws.on("framereceived", on_frame("recv"))

    def on_request(req):
        u = req.url
        if req.resource_type not in ("xhr", "fetch") or any(n in u for n in NOISE):
            return
        # FIX réentrance : all_headers() = roundtrip protocole qui pompe la
        # boucle d'événements → la réponse est dispatchée avant l'assignation
        # du dict et on_response la rate (status=None à vie). req.headers est
        # une propriété locale : zéro roundtrip. Assigner le dict D'ABORD.
        r = reqs.setdefault(u, {"method": req.method, "status": None,
                                "ctype": None, "body": None,
                                "post": (req.post_data or None) if req.method == "POST" else None,
                                "phase": reqs.get("_phase", "n/a")})
        try:
            r["headers"] = {k: v[:120] for k, v in req.headers.items()
                            if k.lower() in HDRS}
        except Exception:
            pass

    def on_response(resp):
        r = reqs.get(resp.url)
        if r is None or r["status"] is not None:
            return
        r["status"] = resp.status
        try:
            ct = resp.headers.get("content-type", "")
            r["ctype"] = ct
            if "json" in ct:
                r["body"] = resp.text()[:1600]
        except Exception:
            pass

    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    pw = sync_playwright().start()
    ctx = None
    try:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE), headless=HEADLESS, viewport={"width": 1680, "height": 940},
            locale="en-US", timezone_id="UTC", args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("websocket", on_ws)
        page.on("request", on_request)
        page.on("response", on_response)

        def goto(url, wait):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(wait)
                print(f"goto {url} OK | frames={len(frames)} xhr={len([k for k in reqs if k != '_phase'])}")
                return True
            except Exception as e:
                print(f"goto ERR {url}: {str(e)[:70]}")
                return False

        reqs["_phase"] = "homepage"
        goto("https://www.asterdex.com/", 7000)
        reqs.pop("_phase", None)
        title = ""
        try: title = page.title()
        except Exception: pass
        print("titre:", title)
        if "moment" in title.lower() or "cloudflare" in title.lower():
            print("!! mur Cloudflare détecté — relancer avec HEADLESS=0")

        # trouver un lien futures sur la page d'accueil
        hrefs = []
        try:
            hrefs = page.evaluate("""() => {
                const out = new Set();
                for (const a of document.querySelectorAll('a[href]')) {
                    const h = a.getAttribute('href') || '';
                    if (/futures|perp|trade|btcusdt|asterusdt/i.test(h)) out.add(h);
                }
                return [...out].slice(0, 30);
            }""")
        except Exception as e:
            print("evaluate hrefs ERR:", str(e)[:60])
        print("liens candidats:", hrefs[:12])

        target = None
        for h in hrefs:
            if re_target(h):
                target = h if h.startswith("http") else "https://www.asterdex.com" + h
                break
        if target is None:
            for c in CANDIDATES:
                if goto(c, 8000):
                    target = c
                    break
        else:
            reqs["_phase"] = "futures"
            goto(target, 8000)
            reqs.pop("_phase", None)

        # vues : clics d'onglets + scroll pour déclencher les lazy loads
        for label in VIEWS:
            n0, r0 = len(frames), len(reqs)
            try:
                page.get_by_text(label, exact=False).first.click(timeout=3000, force=True)
                page.wait_for_timeout(3500)
                print(f"clic {label}: OK (+{len(frames)-n0} frames, +{len(reqs)-r0} xhr)")
            except Exception as e:
                print(f"clic {label}: ERR {str(e)[:40]}")
        try:
            page.mouse.wheel(0, 3000); page.wait_for_timeout(2500)
            page.mouse.wheel(0, 3000); page.wait_for_timeout(2500)
        except Exception:
            pass
        page.wait_for_timeout(3000)
        return 0
    finally:
        rows = [{"url": u, **{k: v for k, v in r.items()}} for u, r in reqs.items()
                if u != "_phase"]
        OUT.write_text(json.dumps({"headless": HEADLESS, "frames": frames,
                                   "requests": rows}, ensure_ascii=False, indent=1))
        print(f"\n=== {len(frames)} frames WS, {len(rows)} XHR → {OUT} ===")
        socks = {}
        for f in frames:
            s = socks.setdefault(f["url"], {"open": 0, "send": 0, "recv": 0})
            s[f["dir"]] += 1
        for u, s in socks.items():
            print(f"  WS {u[:95]} {s}")
        kinds = {}
        for f in frames:
            if f["dir"] != "recv": continue
            try:
                j = json.loads(f["data"])
                key = (str(j.get("stream") or j.get("s") or j.get("e") or
                           j.get("method") or (f"ARR[{len(j)}]" if isinstance(j, list) else "?")))[:40]
            except Exception:
                key = "RAW:" + f["data"][:24]
            kinds[key] = kinds.get(key, 0) + 1
        for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:25]:
            print(f"  {v:5d} recv  {k}")
        for r in rows[:40]:
            b = (r.get("body") or "")[:60].replace("\n", " ")
            print(f"  XHR {r['method']:4} {r.get('status')} {r['url'][:100]}")
            if b: print(f"        ↳ {b}")
        try:
            if ctx: ctx.close()
        except Exception: pass
        pw.stop()


def re_target(h: str) -> bool:
    return ("futures" in h.lower() or "perp" in h.lower()) and "/" in h


if __name__ == "__main__":
    sys.exit(main())
