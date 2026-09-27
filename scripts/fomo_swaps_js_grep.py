"""Tentative 3 : grep des bundles JS fomo.family autour de /swaps + test POST/header."""
import json, re, sys, time
sys.path.insert(0, "scripts")
from fomo_ohlcv_backfill import fresh_jwt
from playwright.sync_api import sync_playwright

UID = "36adb85a-c0fd-5fa8-916d-8fdc32fe4237"
tok = fresh_jwt()
JS = """async ([tok, url, opts]) => {
    const r = await fetch(url, Object.assign({headers: {authorization: 'Bearer ' + tok, 'content-type': 'application/json'}}, opts || {}));
    const t = await r.text();
    return {status: r.status, body: t.slice(0, 900000)};
}"""
BASE = f"https://prod-api.fomo.family/v2/users/{UID}/swaps"

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = b.contexts[0].new_page()
    page.goto("https://fomo.family/profile/unipcs", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    # 1. ressources JS du domaine fomo.family
    urls = page.evaluate("""() => performance.getEntriesByType('resource')
        .map(e => e.name).filter(u => u.includes('fomo.family') && u.endsWith('.js'))""")
    print("JS bundles:", len(urls))
    found = []
    seen = set()
    for u in urls[:40]:
        if u in seen: continue
        seen.add(u)
        r = page.evaluate(JS, ["", u])  # pas de bearer pour les JS
        body = r["body"]
        # le slice 900000 peut tronquer -> fetch complet si /swaps pas trouve mais fichier gros
        for m in re.finditer(r".{120}(/v2/users/[^\"']{0,40}swaps|users/\$\{[^}]+\}/swaps|\"/swaps\"|\\?cursor|swaps\\?.{0,60}).{260}", body):
            frag = m.group(0)
            if "prod-api" in frag or "swaps" in frag:
                found.append((u.split("/")[-1], frag[:380]))
        if len(found) > 12: break
    print("=== FRAGMENTS autour de /swaps :")
    for f_, frag in found[:14]:
        print("---", f_, ":", frag.replace("\\n", " ")[:380])

    # 2. test POST + header cursor
    st, p1, _ = page.evaluate(JS, [tok, f"{BASE}?limit=100"]), None, None
    r1 = page.evaluate(JS, [tok, f"{BASE}?limit=100"])
    j1 = json.loads(r1["body"]); ids1 = [s["id"] for s in j1["responseObject"]["swaps"]]
    last_id = ids1[-1]
    tests = [
        ("POST body cursor", f"{BASE}?limit=100", {"method": "POST", "body": json.dumps({"cursor": last_id, "limit": 100})}),
        ("POST body before", f"{BASE}?limit=100", {"method": "POST", "body": json.dumps({"before": j1["responseObject"]["swaps"][-1]["createdAt"]})}),
        ("header x-cursor", f"{BASE}?limit=100", {"headers": {"authorization": "Bearer " + tok, "x-cursor": last_id}}),
        ("header cursor", f"{BASE}?limit=100", {"headers": {"authorization": "Bearer " + tok, "cursor": last_id}}),
        ("limit=200", f"{BASE}?limit=200", None),
        ("limit=1000", f"{BASE}?limit=1000", None),
    ]
    for name, url, opts in tests:
        o = dict(opts or {})
        o.setdefault("headers", {"authorization": "Bearer " + tok, "content-type": "application/json"})
        r = page.evaluate(JS, [tok, url, o])
        try:
            j = json.loads(r["body"])
            sw = j.get("responseObject", {}).get("swaps", []) if isinstance(j, dict) else []
            ov = len(set(x["id"] for x in sw) & set(ids1))
            print(f"{name:18s} st={r['status']} nb={len(sw)} overlap={ov} first={(sw[0]['id'][:8] if sw else '-')}")
        except Exception as e:
            print(f"{name:18s} st={r['status']} parse-err {r['body'][:120]}")
        time.sleep(0.7)
    page.close()
