"""Probe pagination fomo.family profil : scroll la liste swaps + capture requetes API."""
import json, sys
sys.path.insert(0, "scripts")
from playwright.sync_api import sync_playwright

URL = "https://fomo.family/profile/unipcs"
captured = []

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.new_page()

    def on_req(req):
        u = req.url
        if "prod-api" in u and ("swap" in u.lower() or "user" in u.lower() or "trade" in u.lower() or "activ" in u.lower()):
            captured.append({"url": u, "method": req.method,
                             "post": (req.post_data or "")[:300]})
    page.on("request", on_req)

    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)

    # scroll progressif de la page ET de tout conteneur scrollable interne
    for rnd in range(12):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(1200)
        page.evaluate("""() => {
            const els = [...document.querySelectorAll('div')].filter(e => e.scrollHeight > e.clientHeight + 400);
            els.forEach(e => { e.scrollTop = e.scrollHeight; });
        }""")
        page.wait_for_timeout(800)
        if rnd in (3, 7, 11):
            urls = [c["url"] for c in captured]
            uniq = [u for i, u in enumerate(urls) if u not in urls[:i]]
            print(f"--- round {rnd}: {len(uniq)} urls API uniques")
            for u in uniq[-8:]:
                print("   ", u[:220])

    # chercher un bouton "Load more" / "View more"
    btns = page.evaluate("""() => [...document.querySelectorAll('button, a, [role=button]')]
        .map(e => (e.textContent||'').trim()).filter(t => /more|load|view all|show/i.test(t) && t.length < 40)""")
    print("BUTTONS more-like:", btns[:10])
    if btns:
        try:
            page.get_by_text(btns[0], exact=False).first.click(timeout=5000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print("click err:", e)

    urls = [c["url"] for c in captured]
    uniq = []
    for u in urls:
        if u not in uniq:
            uniq.append(u)
    print("=== TOTAL urls API uniques:", len(uniq))
    for u in uniq:
        print("REQ", u[:300], "| POST:", next((c["post"] for c in captured if c["url"] == u and c["post"]), "")[:200])
    json.dump(uniq, open("/tmp/fomo_pagination_urls.json", "w"))
    page.close()
