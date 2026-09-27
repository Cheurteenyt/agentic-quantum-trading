"""Tentative 2 : hunt du parametre de pagination /swaps par elimination directe in-page."""
import json, sys, time
sys.path.insert(0, "scripts")
from fomo_ohlcv_backfill import fresh_jwt
from playwright.sync_api import sync_playwright

UID = "36adb85a-c0fd-5fa8-916d-8fdc32fe4237"
tok = fresh_jwt()
JS = """async ([tok, url]) => {
    const r = await fetch(url, {headers: {authorization: 'Bearer ' + tok, 'content-type': 'application/json'}});
    const t = await r.text();
    return {status: r.status, body: t.slice(0, 900000)};
}"""
BASE = f"https://prod-api.fomo.family/v2/users/{UID}/swaps"

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = b.contexts[0].new_page()
    page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)

    def get(url):
        r = page.evaluate(JS, [tok, url])
        try:
            j = json.loads(r["body"])
            ro = j.get("responseObject", {}) if isinstance(j, dict) else {}
            sw = ro.get("swaps", []) if isinstance(ro, dict) else (j if isinstance(j, list) else [])
        except Exception:
            sw = []
        return r["status"], sw, ro if isinstance(ro, dict) else {}

    st, p1, ro1 = get(f"{BASE}?limit=100")
    print(f"page1: status={st} nb={len(p1)} keys={list(ro1.keys())} hasNext={ro1.get('hasNextPage')}")
    if not p1:
        sys.exit("pas de swaps")
    ids1 = [s["id"] for s in p1]
    last_id, last_created = p1[-1]["id"], p1[-1]["createdAt"]
    first_created = p1[0]["createdAt"]
    print(f"first={first_created} last={last_created} last_id={last_id}")

    cands = [f"cursor={last_id}", f"cursor={last_created}", f"lastId={last_id}",
             f"before={last_created}", f"beforeId={last_id}", f"endingBefore={last_id}",
             f"after={first_created}", f"offset=100", f"page=2", f"startAfter={last_id}",
             f"swapCursor={last_id}", f"from={last_created}", f"until={last_created}",
             f"beforeTimestamp={last_created}", f"olderThan={last_created}"]
    hits = []
    for c in cands:
        st2, p2, ro2 = get(f"{BASE}?limit=100&{c}")
        n2 = len(p2)
        diff = (not p2) or (p2[0]["id"] != ids1[0]) or (n2 != len(p1))
        tag = "CHANGED" if diff else "same"
        overlap = len(set(x["id"] for x in p2) & set(ids1))
        print(f"{c:60s} st={st2} nb={n2} overlap={overlap} hasNext={ro2.get('hasNextPage')} -> {tag}")
        if diff and overlap < 90:
            hits.append((c, n2, overlap, [x["id"] for x in p2[:3]]))
        time.sleep(0.7)
    print("HITS:", json.dumps(hits, indent=1))
    page.close()
