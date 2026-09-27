"""Grep cible : swaps-v2-*.js -> construction exacte de l'URL /users/../swaps."""
import json, re, sys
sys.path.insert(0, "scripts")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = b.contexts[0].new_page()
    page.goto("https://fomo.family/profile/unipcs", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2000)
    urls = page.evaluate("""() => performance.getEntriesByType('resource').map(e => e.name)
        .filter(u => u.includes('fomo.family') && u.endsWith('.js'))""")
    targets = [u for u in urls if "swaps-v2" in u or "useUser" in u or "UserPositionModal" in u or "profile" in u.lower()]
    print("targets:", [t.split("/")[-1] for t in targets])
    for u in targets:
        r = page.evaluate("""async (u) => { const r = await fetch(u); return await r.text(); }""", u)
        body = r
        name = u.split("/")[-1]
        # toute occurrence de "swaps" suivie d'un template literal ou query
        for m in re.finditer(r".{60}(users/\$\{[^}]{1,50}\}/swaps|/swaps\?|swaps\?|`/v2/users|userSwaps|cursor|Cursor).{300}", body):
            frag = m.group(0)
            if "cursor" in frag.lower() or "/swaps" in frag:
                print(f"\n### {name}\n{frag[:400]}")
    page.close()
