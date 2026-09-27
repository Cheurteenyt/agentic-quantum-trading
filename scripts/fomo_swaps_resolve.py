import json, time, re
from playwright.sync_api import sync_playwright

HANDLES = ["unipcs", "pointfarmcap", "DumbCrayonEater"]
results = {}

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    for h in HANDLES:
        page = ctx.new_page()
        hits = []
        def on_req(req, h=h):
            u = req.url
            if "prod-api.fomo.family" in u and ("/users" in u or "userId" in u or "user" in u.lower()):
                hits.append({"url": u, "method": req.method})
        page.on("request", on_req)
        try:
            page.goto(f"https://fomo.family/profile/{h}", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(9000)
            nd = page.evaluate("() => { const s = window.__NEXT_DATA__; return s ? JSON.stringify(s).slice(0,200000) : null }")
            # cherche tout state global JS avec un id numerique
            probe = page.evaluate("""() => {
                const out = {};
                for (const k of Object.keys(window)) {
                    try { const v = window[k]; if (v && typeof v === 'object' && JSON.stringify(v).match(/"id"\\s*:\\s*"?\\d{4,}/)) out[k] = JSON.stringify(v).slice(0,3000); } catch(e){}
                }
                out.__NEXT_DATA_keys__ = window.__NEXT_DATA__ ? Object.keys(window.__NEXT_DATA__) : null;
                return out;
            }""")
            results[h] = {"final_url": page.url, "requests": hits, "next_data": (nd or "")[:4000], "probe": probe}
            print(f"=== {h} final={page.url}")
            for r in hits: print("  REQ:", r["method"], r["url"][:160])
            if nd:
                m = re.findall(r'"(?:id|userId|user_id)"\s*:\s*"?(\d{3,})"?', nd)
                print("  NEXT_DATA ids:", list(dict.fromkeys(m))[:10])
        except Exception as e:
            results[h] = {"error": str(e)}
            print(f"=== {h} ERROR {e}")
        page.close()
        time.sleep(2)
    with open("/tmp/fomo_resolve_out.json", "w") as f:
        json.dump(results, f, indent=1)
