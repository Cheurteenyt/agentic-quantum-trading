#!/usr/bin/env python3
"""LE MINEUR RÉSIDENT (29/09) — l'extraction DOM des données fomo depuis
la fenêtre de login (:9223) — SANS API, SANS ban possible : le DOM de
ton propre navigateur loggé. Les tokens trending + les données des pages
→ fomo_new_coins + les tables dédiées. Le rythme : 1×/5 min (le doux)."""
import sys, re, time, sqlite3, json
from pathlib import Path
from datetime import datetime, timezone
from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "fomo" / "fomo.db"
CDP = "http://127.0.0.1:9223"


def parse_trending(text: str) -> list[dict]:
    """Le parse de la structure réelle : TICKER → $prix → $MC → MC → ▲/▼ → %."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    def money(s):
        m = re.match(r"^\$([\d.,]+)([KMB]?)$", s.replace(",", ""))
        if not m: return None
        v = float(m.group(1).rstrip("."))
        return v * {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2), 1)
    tokens = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if (re.match(r"^[A-Z0-9\u4e00-\u9fff]{1,18}$", l) and "$" not in l
                and i + 5 < len(lines)
                and lines[i+1].startswith("$") and lines[i+2].startswith("$")):
            ticker = l
            price = money(lines[i+1]); mc = money(lines[i+2])
            chg, d = None, 1
            for k in range(i+3, min(i+8, len(lines))):
                if lines[k] in ("▲", "▼"): d = 1 if lines[k] == "▲" else -1
                m = re.match(r"^([\d.,]+)%$", lines[k])
                if m: chg = float(m.group(1).replace(",", "")) * d; break
            if price and mc:
                tokens.append({"ticker": ticker, "price": price, "mc": mc, "change": chg or 0})
                i += 7; continue
        i += 1
    return tokens


def main() -> int:
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP, timeout=8000)
        ctx = browser.contexts[0] if browser.contexts else browser
        page = next((p for p in ctx.pages if "fomo.family" in (p.url or "")), None)
        if not page:
            print("[miner] pas de page fomo.family dans la fenêtre de login")
            return 1
        # le texte de la sidebar trending (le contenu visible)
        text = page.evaluate("""() => {
            const els = document.querySelectorAll('[class*="trending" i], [class*="Trending"] i');
            for (const el of document.querySelectorAll('div,section')) {
                const t = el.innerText || '';
                if (t.includes('MC') && t.includes('▲') && t.length < 8000 && t.length > 200) {
                    return t;
                }
            }
            return document.body.innerText.slice(0, 6000);
        }""")
        parsed = parse_trending(text)
        print(f"[miner] {len(parsed)} tokens extraits du DOM visible")
        # le stockage
        con = sqlite3.connect(str(DB), timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        now_ts = time.time()
        n_ins = 0
        for p in parsed:
            try:
                con.execute("INSERT OR REPLACE INTO fomo_price_history (ticker, captured_at, mc, price, change) VALUES (?,?,?,?,?)",
                            (p["ticker"], now_ts, p["mc"], p["price"], p["change"]))
                n_ins += 1
            except Exception as e:
                print(f"  insert err : {e}")
        con.commit()
        print(f"[miner] {n_ins}/{len(parsed)} tokens → fomo_price_history")
        con.close()
        return 0
    finally:
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
