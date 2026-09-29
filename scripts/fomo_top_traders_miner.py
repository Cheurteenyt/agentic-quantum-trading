#!/usr/bin/env python3
"""Collecteur DOM des profils top-traders fomo.family.

Recette validée (2026-09-29) :
  - l'onglet DÉDIÉ dans la fenêtre de login (:9223), jamais les onglets du user
  - le goto avec cache-buster (le même-URL = pas de navigation réelle)
  - la vue par défaut du profil = positions COURANTES (format qty/valeur)
  - le clic souris RÉEL (page.mouse) sur le 1er élément 'Open' → le classement
    des MEILLEURS TRADES fermés, format « $X invested • hold », paginé
  - la page 1-5 = leurs top trades ; les sessions suivantes ajoutent les
    nouveaux (les pages profondes = les perdants, non prioritaires)
  - stockage fomo_swaps.db : dom_profile_trades / dom_profile_stats /
    dom_profile_positions / dom_profile_swaps / dom_leaderboard

Usage : .venv/bin/python scripts/fomo_top_traders_miner.py --handles unipcs,pointfarmcap
"""
import argparse
import fcntl
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "fomo" / "fomo_swaps.db"
LOCK = ROOT / "data" / "fomo" / ".top_traders_miner.lock"

TRADES_RE = re.compile(
    r"([^\n]+)\n\$([\d,]+(?:\.\d+)?) invested • ([\w ]+)\n[+\-−]\n\$([\d,]+(?:\.\d+)?)\n[▲▼]\n([\d.,]+)%")
SWAPS_RE = re.compile(
    r"([^\n]+)\n(Buy|Sell)\n\$([\d,]+(?:\.\d+)?)\n\$([\d.,]+[KMB]?) MC\n(\d+[smhd])\n")
POS_RE = re.compile(
    r"(?=\n([^\n]+)\n([\d.,]+[KMB]?) \1\n\$([\d,]+(?:\.\d+)?)\n[▲▼]\n([\d.]+)%\n)")
STATS_RE = re.compile(r"(\d+d \dh+) avg\. hold\n([\d.KM]+) trades\nJoined (\w+ \d{4})")
TOP5_RE = re.compile(r"#(\d) Trade\n\+\n\$([\d,]+(?:\.\d+)?)\n\(\n[▲▼]\n([\d.]+)%\n\)")
GL_RE = re.compile(r"\n\$([\d,]+(?:\.\d+)?)\n-\$([\d,]+(?:\.\d+)?)\n24h\n")


def knum(s):
    return float(s.replace(",", "")) if s else None


def ensure_db():
    con = sqlite3.connect(DB)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS dom_profile_trades (
      trader TEXT, ticker TEXT, invested_usd REAL, hold TEXT, pnl_usd REAL,
      pnl_pct REAL, page INTEGER, mined_at INTEGER,
      PRIMARY KEY (trader, ticker, invested_usd, hold, pnl_pct, page));
    CREATE TABLE IF NOT EXISTS dom_profile_stats (
      trader TEXT PRIMARY KEY, avg_hold TEXT, trades TEXT, joined TEXT,
      gains_usd REAL, losses_usd REAL, top5_json TEXT, mined_at INTEGER);
    CREATE TABLE IF NOT EXISTS dom_profile_positions (
      trader TEXT, ticker TEXT, qty TEXT, value_usd REAL, pct REAL, status TEXT,
      mined_at INTEGER, PRIMARY KEY (trader, ticker, status, mined_at));
    CREATE TABLE IF NOT EXISTS dom_leaderboard (
      rank INTEGER, name TEXT, handle TEXT PRIMARY KEY, pnl_usd REAL, trades INTEGER,
      mined_at INTEGER);
    CREATE TABLE IF NOT EXISTS dom_profile_swaps (
      trader TEXT, ticker TEXT, action TEXT, amount_usd REAL, mc_usd TEXT, time_rel TEXT,
      swap_key TEXT, mined_at INTEGER, PRIMARY KEY (swap_key, mined_at));
    """)
    return con


def mouse_click_text(page, label, pick="first"):
    """Clic souris RÉEL sur un élément au texte exact visible (les tabs Radix)."""
    cands = page.evaluate("""(label) => {
        const out = [];
        for (const b of document.querySelectorAll('*')) {
            if ((b.innerText || '').trim() === label && b.offsetParent !== null) {
                const r = b.getBoundingClientRect();
                if (r.width > 0) out.push({x: r.x + r.width/2, y: r.y + r.height/2});
            }
        }
        return out;
    }""", label)
    if not cands:
        return False
    c = cands[0] if pick == "first" else cands[-1]
    page.mouse.click(c["x"], c["y"])
    time.sleep(2.2)
    return True


def harvest_trades(page, handle, con, now, log, max_pages=5):
    """Le classement des meilleurs trades (la vue investie), pages 1..max_pages."""
    seen, total = set(), 0
    for step in range(max_pages):
        text = page.evaluate("() => document.body.innerText")
        rows = []
        for tk, inv, h, pnl, pc in TRADES_RE.findall(text):
            try:
                rows.append((tk, float(inv.replace(",", "")), h.strip(),
                             float(pnl.replace(",", "")), float(pc.replace(",", ""))))
            except ValueError:
                pass
        for r in rows:
            if r not in seen:
                seen.add(r)
                con.execute(
                    "INSERT OR IGNORE INTO dom_profile_trades VALUES (?,?,?,?,?,?,?,?)",
                    (handle, r[0], r[1], r[2], r[3], r[4], step + 1, now))
                total += 1
        nxt = page.evaluate("""(cur) => {
            const want = String(cur + 1);
            for (const el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === want && el.offsetParent !== null) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.width < 50 && r.height < 40)
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                }
            }
            return null;
        }""", step + 1)
        if not nxt:
            break
        page.mouse.click(nxt["x"], nxt["y"])
        time.sleep(2.0)
    return total


def mine_profile(page, handle, con, now, log, max_pages=5):
    page.goto("about:blank")
    time.sleep(0.4)
    page.goto(f"https://fomo.family/profile/{handle}?r={now}",
              wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    text = page.evaluate("() => document.body.innerText")

    # les stats + les positions courantes + les swaps récents
    st = STATS_RE.search(text)
    if st:
        gl = GL_RE.search(text)
        con.execute("INSERT OR REPLACE INTO dom_profile_stats VALUES (?,?,?,?,?,?,?,?)",
                    (handle, st.group(1), st.group(2), st.group(3),
                     knum(gl.group(1)) if gl else None,
                     knum(gl.group(2)) if gl else None,
                     json.dumps([dict(rank=int(r), pnl_usd=knum(p), pct=float(c))
                                 for r, p, c in TOP5_RE.findall(text)]), now))
    for tk, q, v, pc in POS_RE.findall(text):
        con.execute("INSERT OR REPLACE INTO dom_profile_positions VALUES (?,?,?,?,?,?,?)",
                    (handle, tk, q, knum(v), float(pc), "current", now))
    for tk, ac, am, mc, tr in SWAPS_RE.findall(text):
        con.execute("INSERT OR IGNORE INTO dom_profile_swaps VALUES (?,?,?,?,?,?,?,?)",
                    (handle, tk, ac, knum(am), mc, tr, f"{handle}|{tk}|{ac}|{am}|{mc}|{tr}", now))

    # le classement des meilleurs trades (le clic 'Open' = la vue investie)
    if mouse_click_text(page, "Open", pick="first"):
        n = harvest_trades(page, handle, con, now, log)
        log(f"  {handle}: {n} top trades (invested view)")
    else:
        log(f"  {handle}: l'onglet Open introuvable")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--handles", default="unipcs,pointfarmcap,DumbCrayonEater,"
                    "Salem1299534,The__Solstice,theveeman,AvgJoesCrypto,frankdegods")
    ap.add_argument("--max-pages", type=int, default=5)
    args = ap.parse_args()

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    lk = open(LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("déjà en cours — stop")
        return 0

    con = ensure_db()
    now = int(time.time())
    log = lambda m: print(m, flush=True)
    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        login = pw.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=8000)
        lctx = login.contexts[0] if login.contexts else login
        page = next((p for p in lctx.pages if "fomo.family" in (p.url or "")), None) or lctx.new_page()
        try:
            for h in [x.strip() for x in args.handles.split(",") if x.strip()]:
                try:
                    mine_profile(page, h, con, now, log, args.max_pages)
                    con.commit()
                except Exception as e:
                    log(f"  {h}: ERR {str(e)[:80]}")
            con.commit()
        finally:
            if page.url == "about:blank":
                page.close()
    finally:
        pw.stop()
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
