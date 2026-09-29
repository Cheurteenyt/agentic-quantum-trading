#!/usr/bin/env python3
"""LE MARCHEUR DE SITE FOMO UNIFIÉ (29/09) — la collecte structurée des
pages fomo via la fenêtre loggée (:9223) : chaque route (les onglets de
la sidebar) visitée en rotation avec son parseur validé, la data dans
les tables unifiées. SANS API, SANS ban possible : le DOM de la session
loggée. Les routes : trending (5 min), bonding (15 min), graduated
(30 min), alerts (5 min), leaderboard (60 min)."""
import sys, re, time, sqlite3, json
from pathlib import Path
from datetime import datetime, timezone
from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "fomo" / "fomo.db"
CDP = "http://127.0.0.1:9223"

ROUTES = [
    {"name": "trending",  "button": "Trending",   "cadence": 5,  "parser": "tokens"},
    {"name": "bonding",   "button": "Bonding",    "cadence": 15, "parser": "bonding"},
    {"name": "graduated", "button": "Graduated",  "cadence": 30, "parser": "tokens"},
    {"name": "alerts",    "button": "Alerts",     "cadence": 5,  "parser": "alerts"},
    {"name": "leaderboard", "button": "Leaderboard", "cadence": 60, "parser": "leaderboard"},
]


def money(s):
    m = re.match(r"^\$?([\d.,]+)([KMB]?)$", s.replace(",", ""))
    if not m: return None
    v = float(m.group(1).rstrip("."))
    return v * {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2), 1)


def parse_tokens(lines):
    """TICKER → $prix → $MC → MC → ▲/▼ → % — le parse validé."""
    tokens, i = [], 0
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
                tokens.append({"ticker": ticker, "price": price, "mc": mc,
                               "change": chg or 0})
                i += 7; continue
        i += 1
    return tokens


def parse_bonding(lines):
    """Le tab bonding : TICKER âge $vol VOL $mc MC pct% — le bonding_pct."""
    tokens, i = [], 0
    while i < len(lines):
        l = lines[i]
        if re.match(r"^[A-Z0-9\u4e00-\u9fff]{1,18}$", l) and "$" not in l:
            block = lines[i:i+10]
            age = next((b for b in block if re.match(r"^\d+[mhdw]$", b)), None)
            pct = next((re.match(r"^([\d.,]+)%$", b) for b in block
                        if re.match(r"^[\d.,]+%$", b)), None)
            vol = next((money(b) for b in block if b.startswith("$VOL") or (b.startswith("$") and "M" in b)), None)
            if age and pct:
                tokens.append({"ticker": l, "age": age,
                               "bonding_pct": float(pct.group(1).replace(",", "")),
                               "volume": vol or 0})
                i += 10; continue
        i += 1
    return tokens


def parse_alerts(lines):
    """Les alertes : handle → action → âge → token → $montant → at → $MC → MC."""
    alerts = []
    for i, l in enumerate(lines):
        if l in ("Buy", "Sell") and 0 < i < len(lines) - 6:
            handle = lines[i-1]
            if not re.match(r"^[a-zA-Z0-9_]{2,22}$", handle): continue
            age = lines[i+1]
            token, j = None, i+2
            while j < min(i+5, len(lines)):
                if re.match(r"^[A-Z0-9\u4e00-\u9fff]{2,18}$", lines[j]) and lines[j] not in ("at", "MC"):
                    token = lines[j]; break
                j += 1
            amount = next((lines[k] for k in range(j, min(j+3, len(lines)))
                           if lines[k].startswith("$")), None)
            at_idx = next((k for k in range(j, min(j+6, len(lines)))
                           if lines[k] == "at"), None)
            mc = lines[at_idx+1] if at_idx and at_idx+1 < len(lines) and lines[at_idx+1].startswith("$") else None
            if token and amount:
                alerts.append({"handle": handle, "action": l, "age": age,
                               "token": token, "amount": amount, "mc": mc})
    return alerts


def parse_leaderboard(lines):
    """Le leaderboard : les rangs des traders avec leurs PnL — le pattern harvest."""
    # le parse simple : les blocs nom → PnL → les stats (le raffinement à venir)
    return {"raw_lines": len(lines), "note": "le parse leaderboard à raffiner"}


def store_tokens(con, route, tokens):
    now_ts = time.time()
    for t in tokens:
        try:
            if route == "bonding":
                con.execute("""INSERT INTO fomo_new_coins (ticker, tab, bonding_pct, captured_at)
                               VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                            (t["ticker"], "bonding_walker", t.get("bonding_pct"), now_ts))
            else:
                con.execute("""INSERT OR REPLACE INTO fomo_price_history (ticker, captured_at, mc, price, change)
                               VALUES (?,?,?,?,?)""",
                            (t["ticker"], now_ts, t.get("mc"), t.get("price"), t.get("change")))
        except Exception as e:
            print(f"    store err {t.get('ticker','?')} : {e}")


def store_alerts(con, alerts):
    now_ts = time.time()
    cols = [d[1] for d in con.execute("PRAGMA table_info(fomo_events)").fetchall()]
    for a in alerts:
        try:
            row = {c: a.get(c) for c in cols if c in a}
            row.setdefault("captured_at", now_ts)
            keys = ",".join(row); qs = ",".join("?" * len(row))
            con.execute(f"INSERT OR IGNORE INTO fomo_events ({keys}) VALUES ({qs})",
                        list(row.values()))
        except Exception as e:
            print(f"    alert store err : {str(e)[:60]}")


def visit_route(page, route) -> tuple[str, list]:
    """La navigation vers la route + l'extraction du texte.
    Les onglets (Trending/Bonding/…) = dans la VUE Tokens : l'activer
    d'abord, sinon le clic atterrit sur le titre de la sidebar → 0 lignes."""
    try:
        # les guillemets = la correspondance EXACTE (text=Trending matchait le
        # titre « Trending tokens » de la sidebar au lieu de l'onglet)
        page.locator('text="Tokens"').first.click(timeout=5000)
        time.sleep(2)
    except Exception:
        pass  # déjà sur la vue Tokens (ou le bouton = absent)
    try:
        page.locator(f'text="{route["button"]}"').first.click(timeout=5000)
    except Exception as e:
        return f"nav err {str(e)[:30]}", []
    time.sleep(5)
    text = page.evaluate("""() => {
        for (const el of document.querySelectorAll('div,section')) {
            const t = el.innerText || '';
            if (t.includes('MC') && 400 < t.length && t.length < 8000) return t;
        }
        return document.body.innerText.slice(0, 6000);
    }""")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    parser = {"tokens": parse_tokens, "bonding": parse_bonding,
              "alerts": parse_alerts, "leaderboard": parse_leaderboard}[route["parser"]]
    return lines, parser(lines)


def main() -> int:
    con = sqlite3.connect(str(DB), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    # l'état des routes : la dernière visite
    state_f = ROOT / "data" / "fomo" / "walker_state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {}

    pw = sync_playwright().start()
    page = None
    try:
        browser = pw.chromium.connect_over_cdp(CDP, timeout=8000)
        ctx = browser.contexts[0] if browser.contexts else browser
        # page DÉDIÉE — les routes se naviguent ICI, jamais dans un onglet du user
        page = ctx.new_page()
        page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        now = time.time()
        routes_due = [r for r in ROUTES
                      if now - state.get(r["name"], 0) > r["cadence"] * 60]
        if not routes_due:
            print("[walker] aucune route due — tout est frais")
            return 0

        for route in routes_due:
            print(f"[walker] {route['name']} (tous les {route['cadence']} min)…")
            lines, parsed = visit_route(page, route)
            if route["parser"] in ("tokens", "bonding"):
                store_tokens(con, route["name"], parsed)
            elif route["parser"] == "alerts":
                store_alerts(con, parsed)
            else:
                print(f"  {route['name']} : {parsed}")
            state[route["name"]] = now
            print(f"  → {len(parsed)} entrées parsées")
            time.sleep(2)

        state_f.write_text(json.dumps(state))
        print(f"[walker] la rotation complète : {len(routes_due)} routes")
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
