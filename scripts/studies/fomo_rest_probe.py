#!/usr/bin/env python3
"""SONDE REST FOMO (RE, 29/09) — la suite de fomo_ws_frame_capture : le site
ne souscrit AUCUN topic WS pour holders/theses/swaps → ces listes viennent
d'appels HTTPS. Ce one-shot (1) capture les réponses JSON de prod-api pendant
la navigation token + clics d'onglets, (2) rejoue les endpoints data en
PYTHON PUR avec le JWT volé au challengeResponse + les mêmes headers — si
200, le worker DOM devient inutile ; si 401/429, l'« API bloquée » est
confirmée et le DOM (ou scrapling) reste. Sortie :
reports/fomo_rest_probe.json + verdict stdout."""
import json, re, sys
from pathlib import Path
from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "fomo_rest_probe.json"
CDP = "http://127.0.0.1:9222"
SKIP_WORDS = {"MC", "BUY", "SELL", "TOKENS", "TRENDING", "GRADUATED", "BONDING",
              "MONITOR", "LIVE", "NEW", "MOST", "HELD", "WATCHLIST", "CRYPTO",
              "VOL", "SI", "AT", "AGE"}
NOISE = ("posthog", "sentry", "sentry", "analytics", "google", "sentry.io")


def main() -> int:
    reqs, jwt_holder = {}, {"jwt": None, "headers": None}

    pw = sync_playwright().start()
    page = None
    try:
        browser = pw.chromium.connect_over_cdp(CDP, timeout=8000)
        ctx = browser.contexts[0] if browser.contexts else browser
        page = ctx.new_page()

        def on_request(req):
            u = req.url
            if "prod-api.fomo.family" in u and not any(n in u for n in NOISE):
                reqs[u] = {"method": req.method, "status": None,
                           "ctype": None, "body": None,
                           "headers": None}
                if req.method in ("GET", "POST") and jwt_holder["headers"] is None:
                    try:
                        reqs[u]["headers"] = {k: v for k, v in req.all_headers().items()
                                              if k.lower() in ("authorization", "cookie",
                                                               "origin", "referer",
                                                               "user-agent", "accept")}
                    except Exception:
                        pass

        def on_response(resp):
            u = resp.url
            r = reqs.get(u)
            if r is None or r["status"] is not None:
                return
            r["status"] = resp.status
            try:
                ct = resp.headers.get("content-type", "")
                r["ctype"] = ct
                if "json" in ct:
                    r["body"] = resp.text()[:1500]
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(7000)
        tickers = [t for t in page.evaluate("""() => {
            const out = [];
            for (const l of document.body.innerText.split('\\n')) {
                const t = l.trim();
                if (/^[A-Z0-9]{2,10}$/.test(t)) out.push(t);
                if (out.length >= 20) break;
            }
            return out;
        }""") if t.upper() not in SKIP_WORDS]
        print("tickers:", tickers[:8])
        clicked = None
        for t in tickers[:6]:
            try:
                loc = page.locator(f'text="{t}"')
                for i in range(min(loc.count(), 5)):
                    try:
                        loc.nth(i).click(timeout=2500, force=True)
                        clicked = t
                        break
                    except Exception:
                        continue
            except Exception:
                pass
            page.wait_for_timeout(1200)
            if clicked:
                break
        print("token ouvert:", clicked)
        page.wait_for_timeout(6000)
        for label in ("Holders", "Thesis", "Swaps"):
            try:
                page.get_by_text(label, exact=False).first.click(timeout=4000, force=True)
                print(f"clic {label}: OK")
            except Exception as e:
                print(f"clic {label}: ERR {str(e)[:50]}")
            page.wait_for_timeout(4000)

        # le JWT du challengeResponse (frame WS) — via une capture request WS
        # impossible ici : on le prend dans le dump de la capture précédente
        cap = ROOT / "reports" / "fomo_ws_frames_capture.json"
        if cap.exists():
            for f in json.loads(cap.read_text()):
                if f["dir"] == "send" and "challengeResponse" in f["data"]:
                    m = re.search(r'"jwt":"([^"]+)"', f["data"])
                    if m:
                        jwt_holder["jwt"] = m.group(1)
                        break

        rows = [{"url": u, **r} for u, r in reqs.items()]
        OUT.write_text(json.dumps({"requests": rows, "jwt": jwt_holder["jwt"]},
                                  ensure_ascii=False, indent=1))
        print(f"\n=== {len(rows)} requêtes prod-api capturées ===")
        for r in rows:
            b = (r.get("body") or "")[:60].replace("\n", " ")
            print(f"  {r['method']:4d} {r['status']} {r['url'][:95]}")
            if b:
                print(f"        ↳ {b}")

        # === REJOUE PYTHON PUR (sans navigateur) ===
        print("\n=== REJOUE python pur (requests + JWT/headers du site) ===")
        import urllib.request
        import urllib.error
        replayable = [r for r in rows if r["status"] == 200 and r.get("ctype", "")
                      and "json" in r["ctype"] and r.get("headers")
                      and r["headers"].get("authorization")]
        if not replayable and rows:
            replayable = [r for r in rows if r.get("headers")] [:3]
        for r in replayable[:6]:
            h = dict(r["headers"])
            h.setdefault("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
            if jwt_holder["jwt"] and "authorization" not in {k.lower() for k in h}:
                h["Authorization"] = f"Bearer {jwt_holder['jwt']}"
            req = urllib.request.Request(r["url"], headers=h)
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read(300)
                    print(f"  REPLAY {resp.status} {r['url'][:90]}")
                    print(f"        ↳ {body[:200]}")
            except urllib.error.HTTPError as e:
                print(f"  REPLAY {e.code} {r['url'][:90]}  ({e.reason})")
            except Exception as e:
                print(f"  REPLAY ERR {r['url'][:90]}  {str(e)[:60]}")
        return 0
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
