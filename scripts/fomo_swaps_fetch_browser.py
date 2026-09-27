import json, sys
sys.path.insert(0, "scripts")
from fomo_ohlcv_backfill import fresh_jwt
from playwright.sync_api import sync_playwright

tok = fresh_jwt()
USERS = {"unipcs": "36adb85a-c0fd-5fa8-916d-8fdc32fe4237",
         "pointfarmcap": "6d8c0bf3-5d42-506c-a0ea-9e1e75ff38af"}

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.new_page()
    page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)
    out = {}
    for h, uid in USERS.items():
        js = """async ([tok, uid]) => {
            const r = await fetch(`https://prod-api.fomo.family/v2/users/${uid}/swaps`, {
                headers: {authorization: 'Bearer ' + tok, 'content-type': 'application/json'}});
            const t = await r.text();
            return {status: r.status, body: t.slice(0, 400000)};
        }"""
        res = page.evaluate(js, [tok, uid])
        print(f"=== {h} ({uid}): {res['status']} len={len(res['body'])}")
        try:
            d = json.loads(res["body"])
            out[h] = d
            items = d if isinstance(d, list) else next((d[k] for k in ("swaps","items","data","results") if k in d), [])
            print("type:", type(d).__name__, "nb:", len(items) if isinstance(items, list) else "?")
            print("top keys:", list(d.keys())[:15] if isinstance(d, dict) else "LIST")
            if isinstance(items, list) and items:
                print("item0:", json.dumps(items[0], indent=1)[:2200])
        except Exception as e:
            print("parse err:", e, res["body"][:300])
            out[h] = {"raw": res["body"][:5000], "status": res["status"]}
    json.dump(out, open("/tmp/fomo_swaps_browser.json", "w"))
    page.close()
