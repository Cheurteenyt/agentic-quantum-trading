#!/usr/bin/env python3
"""CENSUS ASTERDEX (nuit 30/09) — la carte complète du site au-delà de la page
de trade pro déjà sondée (aster_ui_probe.py). Deux phases :
  1) DISCOVERY : home + extraction de TOUS les <a href> du DOM → carte des routes ;
  2) CENSUS : navigation séquentielle de chaque route (pacing 3 s, un census
     pas un scan), capture par page des frames WS (page.on websocket,
     framesent/framereceived) et des XHR (request/response, statut local
     req.headers — le fix anti-réentrance du probe).
Sortie : reports/aster_site_census_capture.json + résumé stdout par page.
Paramétrable : MAX_PAGES=26 HEADLESS=1 .venv/bin/python scripts/studies/aster_site_census.py
"""
import json, os, re, shutil, sys, time
from pathlib import Path
from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "aster_site_census_capture.json"
PROFILE = Path("/tmp/aster-site-census-profile")
HEADLESS = os.environ.get("HEADLESS", "1") != "0"
BASE = "https://www.asterdex.com"
PACE_S = 3.0            # pacing entre navigations (census, pas scan)
WAIT_MS = 7000          # temps d'observation par page
MAX_FRAMES = 9000
MAX_PAGES = int(os.environ.get("MAX_PAGES", "26"))
NOISE = ("sentry", "posthog", "analytics", "googletag", "doubleclick",
         "clarity.ms", "hotjar", "facebook", "cloudflareinsights",
         "challenges.cloudflare", "auth.privy.io", "walletconnect",
         "nodereal.io", "ninicoin.io", "bscrpc.com", "rpc.ankr.com",
         "space.id", "cloudfront.net/flags", "dk8ppttyqe644")
CANDIDATES = os.environ.get("PAGES", "|".join([
    # issues du sitemap.xml officiel (la vraie carte du site)
    "/en/trade/pro/futures/BTCUSDT", "/en/trade/pro/spot/BTCUSDT",
    "/en/spot/BTCUSDT", "/en/trade/1001x/futures/BTCUSD",
    "/en/trade/shield/futures/BTCUSDT", "/en/futures/BTCUSDT",
    "/en/trading-leaderboard", "/en/stage0/leaderboard", "/en/stage1/team",
    "/en/stage5/statistics", "/en/rewards", "/en/rewards_hub",
    "/en/trade-and-earn", "/en/earn", "/en/earn/alp", "/en/earn/astoken",
    "/en/earn/ecosystem", "/en/portfolio/overview", "/en/portfolio/pro",
    "/en/referral", "/en/rocket-launch", "/en/usdf", "/en/api-management",
    "/en/aster-code", "/en/builder-center", "/",
])).split("|")


def extract_hrefs(page):
    try:
        return page.evaluate("""() => {
            const out = new Set();
            for (const a of document.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href') || '';
                if (h && !h.startsWith('#') && !h.startsWith('javascript')
                        && !h.startsWith('mailto')) out.add(h);
            }
            return [...out];
        }""")
    except Exception:
        return []


def main() -> int:
    frames, reqs, pages = [], {}, []
    phase = ["?"]

    def on_request(req):
        u = req.url
        if req.resource_type not in ("xhr", "fetch") or any(n in u for n in NOISE):
            return
        r = reqs.setdefault(u, {"method": req.method, "status": None,
                                "ctype": None, "body": None,
                                "post": (req.post_data or None) if req.method == "POST" else None,
                                "phases": {phase[0]}})
        r["phases"].add(phase[0])
        try:
            r["headers"] = {k: v[:120] for k, v in req.headers.items()
                            if k.lower() in ("origin", "referer", "user-agent",
                                             "authorization", "content-type")}
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
                r["body"] = resp.text()[:2000]
        except Exception:
            pass

    def ws_handler(ws):
        frames.append({"phase": phase[0], "dir": "open", "url": ws.url, "data": ""})
        def mk(direction):
            def h(p):
                if len(frames) < MAX_FRAMES:
                    frames.append({"phase": phase[0], "dir": direction,
                                   "url": ws.url, "data": str(p)[:2200]})
            return h
        ws.on("framesent", mk("send"))
        ws.on("framereceived", mk("recv"))

    if PROFILE.exists():
        shutil.rmtree(PROFILE, ignore_errors=True)
    pw = sync_playwright().start()
    ctx = None
    try:
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE), headless=HEADLESS, viewport={"width": 1680, "height": 940},
            locale="en-US", timezone_id="UTC",
            args=["--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("websocket", ws_handler)
        page.on("request", on_request)
        page.on("response", on_response)

        def goto(url, wait=WAIT_MS, label=""):
            phase[0] = label or url
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(wait)
                title = ""
                try: title = page.title()
                except Exception: pass
                ok = "cloudflare" not in title.lower() and "moment" not in title.lower()
                print(f"[{phase[0]}] goto {url} OK title={title[:60]!r} "
                      f"frames={len(frames)} cf_wall={not ok}", flush=True)
                return ok, title
            except Exception as e:
                print(f"[{phase[0]}] goto ERR {url}: {str(e)[:70]}", flush=True)
                return False, ""

        # ---- PHASE DISCOVERY : home + tous les hrefs
        ok, title = goto(BASE + "/en", 8000, "discovery:home")
        all_hrefs = set(extract_hrefs(page))
        pages.append({"phase": "discovery:home", "url": BASE + "/en",
                      "ok": ok, "title": title, "n_hrefs": len(all_hrefs)})
        time.sleep(PACE_S)

        # normaliser les routes internes
        routes = set()
        for h in all_hrefs:
            if h.startswith("http"):
                m = re.match(r"https?://(?:[a-z0-9.-]*\.)?asterdex\.com(/.*)?$", h)
                if m:
                    routes.add((m.group(1) or "/").split("?")[0])
                elif "docs.asterdex" in h:
                    routes.add(h)  # sous-domaine docs, noté tel quel
            elif h.startswith("/"):
                routes.add(h.split("?")[0])
        print(f"discovery: {len(all_hrefs)} hrefs → {len(routes)} routes asterdex", flush=True)

        # fusion candidats (au cas où la nav est JS-only), cap MAX_PAGES
        routes.update(CANDIDATES)
        ordered = sorted(routes, key=lambda x: (0 if x.startswith("http") else 1, x))
        print("routes candidates:", ordered[:60], flush=True)

        # ---- PHASE CENSUS : chaque page
        for r in ordered[:MAX_PAGES]:
            url = r if r.startswith("http") else BASE + r
            label = "census:" + (r if len(r) < 60 else r[:57] + "…")
            ok, title = goto(url, WAIT_MS, label)
            hrefs = extract_hrefs(page)
            all_hrefs.update(hrefs)
            pages.append({"phase": label, "url": url, "ok": ok, "title": title,
                          "n_hrefs": len(hrefs)})
            time.sleep(PACE_S)

        return 0
    finally:
        rows = []
        for u, r in reqs.items():
            row = dict(r)
            row["phases"] = sorted(row.pop("phases", []))
            rows.append({"url": u, **row})
        OUT.write_text(json.dumps({"pages": pages, "frames": frames,
                                   "requests": rows}, ensure_ascii=False, indent=1))
        print(f"\n=== {len(pages)} pages, {len(frames)} frames WS, {len(rows)} XHR → {OUT} ===", flush=True)
        by_page = {}
        for f in frames:
            by_page.setdefault(f["phase"], {"frames": 0, "kinds": {}})
            b = by_page[f["phase"]]
            b["frames"] += 1
            if f["dir"] != "recv":
                continue
            try:
                j = json.loads(f["data"])
                key = str(j.get("stream") or j.get("s") or j.get("e") or
                          j.get("method") or (f"ARR[{len(j)}]" if isinstance(j, list) else "?"))[:44]
            except Exception:
                key = "RAW:" + f["data"][:20]
            b["kinds"][key] = b["kinds"].get(key, 0) + 1
        for p in pages:
            b = by_page.get(p["phase"], {"frames": 0, "kinds": {}})
            print(f"\n--- {p['phase']}  ok={p['ok']}  frames={b['frames']}")
            for k, v in sorted(b["kinds"].items(), key=lambda x: -x[1])[:8]:
                print(f"    {v:5d} recv {k}")
            n_x = 0
            for r in rows:
                if p["phase"] in r["phases"]:
                    n_x += 1
                    print(f"      XHR {r['method']:4} {r.get('status')} {r['url'][:110]}")
            print(f"    xhr dédiés: {n_x}")
        try:
            if ctx: ctx.close()
        except Exception: pass
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
