# ARCHIVÉ (29/09) : sonde one-shot modal positions — voir docs/20-registre-indicateurs.md
"""Tentative 3 : ouvrir le modal positions -> scroller la liste trades -> capturer page 2.
Fallback: brute-force noms de params restants."""
import json, re, sys, time
sys.path.insert(0, "scripts")
from fomo_ohlcv_backfill import fresh_jwt
from playwright.sync_api import sync_playwright

UID = "36adb85a-c0fd-5fa8-916d-8fdc32fe4237"
tok = fresh_jwt()
captured = []
JS = """async ([tok, url, opts]) => {
    const r = await fetch(url, Object.assign({headers: {authorization: 'Bearer ' + tok, 'content-type': 'application/json'}}, opts || {}));
    return {status: r.status, body: await r.text()};
}"""

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = b.contexts[0].new_page()
    page.on("request", lambda r: captured.append(r.url) if "prod-api" in r.url and "/swaps" in r.url and "usdc" not in r.url else None)
    page.goto("https://fomo.family/profile/unipcs", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    # A. UI: cliquer sur une position / holding pour ouvrir le modal
    cand = page.locator("text=/Positions|Holdings|Tokens|Portfolio/i").all()
    print("sections:", [c.text_content()[:40] for c in cand[:6]])
    clicked = False
    for sel in ["[class*='position']", "[class*='holding']", "[class*='tokenRow']", "img[alt]"]:
        try:
            els = page.locator(sel)
            if els.count() > 0:
                els.first.click(timeout=3000); clicked = True
                print("clicked:", sel); break
        except Exception: pass
    page.wait_for_timeout(3500)
    if clicked:
        # scroller le modal en profondeur
        for _ in range(10):
            page.evaluate("""() => {
                const modals = [...document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal], [class*=drawer]')];
                modals.forEach(m => { m.scrollTop = m.scrollHeight; });
                const scrolls = [...document.querySelectorAll('div')].filter(e => e.scrollHeight > e.clientHeight + 300);
                scrolls.forEach(e => e.scrollTop = e.scrollHeight);
            }""")
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(1000)
    urls = [u for u in dict.fromkeys(captured)]
    print("captured /swaps urls:")
    for u in urls:
        print("  ", u)

    # B. brute-force params restants (page2 attendu = pas d'overlap avec page1)
    base = f"https://prod-api.fomo.family/v2/users/{UID}/swaps"
    r1 = page.evaluate(JS, [tok, base + "?limit=100"])
    j1 = json.loads(r1["body"]); s1 = j1["responseObject"]["swaps"]
    ids1 = set(s["id"] for s in s1)
    last = s1[-1]
    vals = {"id": last["id"], "createdAt": last["createdAt"], "ts": last["createdAt"]}
    cands = []
    for pn in ["swapId", "lastSwapId", "endId", "fromId", "next", "nextCursor", "nextToken",
               "startingAfter", "starting_after", "olderThanId", "minId", "lt", "gt", "beforeTs",
               "createdAtBefore", "lastCreatedAt", "paginationToken", "pageToken", "afterId", "skip"]:
        cands.append(f"{pn}={last['id']}")
    for pn in ["createdAt", "timestamp", "untilTs"]:
        cands.append(f"{pn}={last['createdAt']}")
    for c in cands:
        try:
            r = page.evaluate(JS, [tok, f"{base}?limit=100&{c}"])
            j = json.loads(r["body"])
            sw = j.get("responseObject", {}).get("swaps", []) if isinstance(j, dict) else []
            ov = len(set(x["id"] for x in sw) & ids1)
            if ov < 80:
                print(f"*** HIT {c} nb={len(sw)} overlap={ov} new_first={sw[0]['id'][:12] if sw else '-'}")
        except Exception as e:
            print("err", c, str(e)[:80])
        time.sleep(0.5)
    print("brute force fini")
    page.close()
