#!/usr/bin/env python3
"""LE RECENSEMENT D'INTERFACE fomo.family — la cartographie exhaustive.

Pour chaque écran : l'URL, le titre, les onglets, les composants de données
(tableaux, panneaux, listes) avec leurs CLASSES CSS et leurs attributs
data-* (les hooks stables que les parseurs doivent utiliser au lieu des
regex de texte fragiles). Sortie : data/fomo/site_census.json.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SCREENS = [
    ("home", "https://fomo.family/"),
    ("tokens_trending", "https://fomo.family/"),   # + le clic Tokens → Trending
    ("token_detail", "https://fomo.family/tokens/solana/3kmygWKZBkCYrgZHKfiuB9UFKTcDLTFFsKo3BWpmpump"),
    ("profile", "https://fomo.family/profile/unipcs"),
    ("leaderboard", "https://fomo.family/leaderboard"),
    ("alerts", "https://fomo.family/alerts"),
    ("feed", "https://fomo.family/feed"),
]

CENSUS_JS = """() => {
    const out = {title: document.title.slice(0, 60), url: location.href};
    // les onglets / boutons de navigation visibles
    out.tabs = [];
    const seen = new Set();
    for (const b of document.querySelectorAll('button, [role="tab"], a')) {
        const t = (b.innerText || '').trim().replace(/\\n/g, ' ');
        if (t && t.length > 0 && t.length < 40 && !seen.has(t)) {
            const r = b.getBoundingClientRect();
            if (r.width > 0) { seen.add(t); out.tabs.push(t.slice(0, 38)); }
        }
    }
    // les composants structurels : les conteneurs avec les classes significatives
    out.components = [];
    const cSeen = new Set();
    for (const el of document.querySelectorAll('[class]')) {
        const cls = (el.className || '').toString();
        // les classes sémantiques (pas les utilitaires tailwind atomiques seuls)
        const meaningful = cls.split(/\\s+/).filter(c =>
            /table|row|card|panel|holder|swap|thesis|position|trade|chart|sidebar|nav|tab|list|item|header|feed|alert|token|trader|profile|leader/i.test(c));
        if (meaningful.length && el.innerText && el.innerText.length > 30) {
            const r = el.getBoundingClientRect();
            const key = meaningful.slice(0, 2).join('|') + r.width.toFixed(0);
            if (!cSeen.has(key) && r.height > 20) {
                cSeen.add(key);
                out.components.push({
                    tag: el.tagName,
                    classes: meaningful.slice(0, 4),
                    w: Math.round(r.width), h: Math.round(r.height),
                    textHead: (el.innerText || '').slice(0, 80).replace(/\\n/g, '|'),
                });
            }
        }
        if (out.components.length > 25) break;
    }
    // les attributs data-* (les hooks stables de l'app)
    out.dataAttrs = {};
    for (const el of document.querySelectorAll('[data-testid], [data-id], [data-attr]')) {
        for (const a of el.attributes) {
            if (a.name.startsWith('data-')) {
                out.dataAttrs[a.name] = out.dataAttrs[a.name] || [];
                if (out.dataAttrs[a.name].length < 3) out.dataAttrs[a.name].push(el.tagName);
            }
        }
    }
    out.bodyChars = (document.body.innerText || '').length;
    return out;
}"""


def main():
    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    census = {}
    page = None
    try:
        b = pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=8000)
        lctx = b.contexts[0] if b.contexts else b
        page = next((p for p in lctx.pages if "fomo.family" in (p.url or "")), None) \
            or lctx.new_page()
        for name, url in SCREENS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(6)
                census[name] = page.evaluate(CENSUS_JS)
                print(f"[{name}] {len(census[name]['tabs'])} onglets, "
                      f"{len(census[name]['components'])} composants, "
                      f"{census[name]['bodyChars']} chars")
            except Exception as e:
                census[name] = {"error": str(e)[:120]}
                print(f"[{name}] ERR {str(e)[:80]}")
            time.sleep(1)
        # les onglets de la vue Tokens + les tabs du token detail = les clics
        try:
            page.locator('text="Tokens"').first.click(timeout=6000)
            time.sleep(4)
            census["tokens_view_tabs"] = page.evaluate(
                "() => [...document.querySelectorAll('button')]"
                ".map(b => (b.innerText||'').trim()).filter(t => t && t.length < 30).slice(0, 20)")
            print("[tokens_view_tabs]", census["tokens_view_tabs"])
        except Exception as e:
            census["tokens_view_tabs"] = {"error": str(e)[:100]}
    finally:
        pw.stop()
    out_f = ROOT / "data" / "fomo" / "site_census.json"
    out_f.write_text(json.dumps(census, indent=1, ensure_ascii=False))
    print(f"recensement → {out_f.name} ({out_f.stat().st_size // 1024} Ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
