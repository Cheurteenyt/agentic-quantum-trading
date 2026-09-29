#!/usr/bin/env python3
"""Le worker DOM résident — l'exploitation COMPLÈTE du site fomo.

Un service, UNE page dédiée permanente dans la fenêtre de login (:9223),
la rotation de TOUTES les surfaces (trending, bonding, graduated, alerts,
leaderboard, clans, feed, profils top-10) + le LISTENER WS passif : chaque
navigation déclenche les souscriptions naturelles de l'app, leurs frames
sont capturées → l'inventaire automatique des topics qu'on ne connaît pas
(zéro sonde, zéro 429).

Les règles (gravées) : jamais d'itération des onglets du user ; la page
dédiée = créée au boot, détenue par le worker ; le parse des surfaces
connues = réutilisé du walker et du mineur top-traders.
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from fomo_site_walker import ROUTES, visit_route, store_tokens, store_alerts, DB as WDB
from fomo_top_traders_miner import mine_profile, ensure_db as ensure_swaps_db
from patchright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"
DB_TICKS = ROOT / "data" / "fomo" / "fomo.db"
DB_SWAPS = ROOT / "data" / "fomo" / "fomo_swaps.db"
STATE_F = ROOT / "data" / "fomo" / "dom_worker_state.json"
FRAMES_F = ROOT / "data" / "fomo" / "ws_frame_parking.jsonl"
LOCK = ROOT / "data" / "fomo" / ".dom_worker.lock"

TOP_HANDLES = ["unipcs", "pointfarmcap", "DumbCrayonEater", "Salem1299534",
               "The__Solstice", "theveeman", "AvgJoesCrypto", "frankdegods"]

CADENCES = {r["name"]: r["cadence"] for r in ROUTES}
CADENCES.update({"clans": 30, "profiles": 60, "feed": 15})

def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def ensure_tables():
    con = sqlite3.connect(str(WDB), timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS clans_raw (
        snapshot_ts INTEGER PRIMARY KEY, text TEXT, parsed INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS feed_raw (
        snapshot_ts INTEGER PRIMARY KEY, text TEXT, parsed INTEGER DEFAULT 0)""")
    con.commit(); con.close()
    con = ensure_swaps_db()
    con.close()


def ensure_page(ctx, page):
    """La santé de la page : si morte (fermée/crash), ré-acquérir — le worker
    ne doit JAMAIS tourner en zombie sur une page fermée."""
    try:
        page.evaluate("() => 1")
        return page
    except Exception:
        log("page morte → ré-acquisition")
        for attempt in range(4):
            try:
                np = ctx.new_page()
                np.goto("https://fomo.family/", wait_until="domcontentloaded",
                        timeout=30000)
                np.wait_for_timeout(4000)
                log("page ré-acquise ✓")
                return np
            except Exception:
                # libérer puis réutiliser une page existante
                for p2 in list(ctx.pages):
                    if "fomo.family" in (p2.url or ""):
                        try:
                            p2.close()
                        except Exception:
                            pass
                time.sleep(5)
        existing = next((p2 for p2 in ctx.pages if "fomo.family" in (p2.url or "")), None)
        if existing:
            log("réutilisation de la page existante")
            return existing
        raise RuntimeError("page irécupérable")


def visit_clans(page):
    """La page clans : les groupes de baleines — le dump structuré brut
    (le parse fin arrive quand le format réel est vu en production)."""
    page.goto("https://fomo.family/clans", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4500)
    text = page.evaluate("() => document.body.innerText")
    con = sqlite3.connect(str(WDB), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("INSERT OR REPLACE INTO clans_raw VALUES (?,?,0)",
                (int(time.time()), text))
    con.commit(); con.close()
    return len(text)


def visit_feed(page):
    """Le feed social : les trades et les thèses des comptes suivis/trending."""
    page.goto("https://fomo.family/feed", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4500)
    text = page.evaluate("() => document.body.innerText")
    con = sqlite3.connect(str(WDB), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("INSERT OR REPLACE INTO feed_raw VALUES (?,?,0)",
                (int(time.time()), text))
    con.commit(); con.close()
    return len(text)


class FrameListener:
    """Le listener WS passif : les frames de NOTRE page = l'inventaire des
    topics naturels de l'app, sans émettre une seule requête."""

    def __init__(self, page):
        self.counts = {}
        self.n_frames = 0
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.send("Network.enable")
        self.cdp.on("Network.webSocketFrameReceived", self._on_frame)
        self.cdp.on("Network.webSocketFrameSent", self._on_sent)
        self.sent_log = []

    def _on_sent(self, e):
        """Les messages envoyés par l'app = le FORMAT de souscription
        des topics (la clé pour les répliquer dans le daemon)."""
        try:
            data = e.get("response", {}).get("payloadData", "")
            if data and self.sent_log.count(data[:80]) < 2:  # le dédoupe léger
                self.sent_log.append(data[:80])
                with open(FRAMES_F, "a") as fh:
                    fh.write(json.dumps({"ts": int(time.time()), "topicType": "__SENT__",
                                         "payload": data[:2000]}) + "\n")
        except Exception:
            pass

    def _on_frame(self, e):
        try:
            data = e.get("response", {}).get("payloadData", "")
            obj = json.loads(data)
            tt = obj.get("topicType") or obj.get("type") or "?"
            self.counts[tt] = self.counts.get(tt, 0) + 1
            self.n_frames += 1
            # le parking : les topics NON-prices (les prices = déjà dans le daemon)
            if tt not in ("prices",):
                with open(FRAMES_F, "a") as fh:
                    fh.write(json.dumps({"ts": int(time.time()), "topicType": tt,
                                         "payload": data[:2000]}) + "\n")
        except Exception:
            pass

    def summary(self):
        return f"{self.n_frames} frames ({json.dumps(self.counts)})"


def main():
    import fcntl
    lk = open(LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("déjà en cours — stop")
        return 0

    ensure_tables()
    con_mig = ensure_swaps_db()
    for col in ("mutuals INTEGER", "following REAL", "followers REAL"):
        try:
            con_mig.execute(f"ALTER TABLE ws_traders ADD COLUMN {col}")
        except Exception:
            pass  # déjà présentes
    con_mig.commit(); con_mig.close()
    state = json.loads(STATE_F.read_text()) if STATE_F.exists() else {}
    last_visit = state.get("last_visit", {})
    profile_idx = state.get("profile_idx", 0)

    pw = sync_playwright().start()
    page = None
    listener = None
    con_swaps = ensure_swaps_db()
    con_walker = sqlite3.connect(str(WDB), timeout=30)
    con_walker.execute("PRAGMA busy_timeout=30000")
    try:
        browser, ctx = None, None
        for port in ("9223", "9222"):  # le login window du user, puis le nôtre
            try:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}",
                                                       timeout=8000)
                ctx = browser.contexts[0] if browser.contexts else browser
                log(f"CDP attaché sur :{port}")
                break
            except Exception:
                continue
        if ctx is None:
            raise RuntimeError("aucun navigateur CDP disponible (:9223/:9222)")
        # :9222 = NOTRE navigateur dédié (le user = sur son chromium à lui) :
        # la propriété totale — toutes les pages fomo = purgées au boot,
        # le worker = le SEUL créateur de pages (zéro flash, zéro fuite)
        for p2 in list(ctx.pages):
            if "fomo.family" in (p2.url or ""):
                try:
                    p2.close()
                except Exception:
                    pass
        log("les pages fomo purgées — le worker = seul propriétaire du navigateur")
        # la page DÉDIÉE : le retry avec l'ESCALADE — au 2e échec, le
        # navigateur dédié = HS → restart du service fomo-browser + re-connexion
        page = None
        for attempt in range(4):
            try:
                page = ctx.new_page()
                break
            except Exception:
                log(f"new_page échoué ({attempt + 1}/4) — libération des pages fomo")
                for p2 in list(ctx.pages):
                    if "fomo.family" in (p2.url or ""):
                        try:
                            p2.close()
                        except Exception:
                            pass
                if attempt >= 1:
                    log("le navigateur dédié = HS → restart fomo-browser.service")
                    import subprocess
                    subprocess.run(["systemctl", "--user", "restart",
                                    "fomo-browser.service"], timeout=90)
                    time.sleep(12)
                    for port2 in ("9222", "9223"):
                        try:
                            browser = pw.chromium.connect_over_cdp(
                                f"http://127.0.0.1:{port2}", timeout=8000)
                            ctx = browser.contexts[0] if browser.contexts else browser
                            log(f"CDP re-attaché sur :{port2}")
                            break
                        except Exception:
                            continue
                time.sleep(5)
        if page is None:
            page = next((p for p in ctx.pages if "fomo.family" in (p.url or "")), None)
        if page is None:
            raise RuntimeError("aucune page fomo possible sur le navigateur dédié")
        # l'accueil = l'app rendue ; le clic « Tokens » active la vue à onglets
        # (Trending/Bonding/Graduated) — la route /tokens directe = morte (« Go home »)
        page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)
        try:
            page.locator("text=Tokens").first.click(timeout=8000)
            page.wait_for_timeout(4000)
            log("vue Tokens activée")
        except Exception as e:
            log(f"clic Tokens ERR {str(e)[:60]} — les routes en cliquent quand même")
        listener = FrameListener(page)
        log(f"worker DOM résident démarré — la page dédiée, "
            f"{len(CADENCES)} surfaces, le listener WS passif actif")

        while True:
            now = time.time()
            page = ensure_page(ctx, page)
            # 0) la sidebar trending de l'ACCUEIL → fomo_price_history
            #    (le pattern du miner : MC/prix/▲% — la route du walker = les
            #    lignes de la page Tokens, une autre structure)
            if now - last_visit.get("home_trending", 0) > 5 * 60:
                try:
                    from fomo_top_traders_miner import SWAPS_RE
                    from login_window_miner import parse_trending
                    page.goto("https://fomo.family/", wait_until="domcontentloaded",
                              timeout=30000)
                    page.wait_for_timeout(4500)
                    text = page.evaluate("() => document.body.innerText")
                    parsed = parse_trending(text)
                    con_h = sqlite3.connect(str(WDB), timeout=30)
                    con_h.execute("PRAGMA busy_timeout=30000")
                    n_ins = 0
                    for pk in parsed:
                        con_h.execute(
                            "INSERT OR REPLACE INTO fomo_price_history "
                            "(ticker, captured_at, mc, price, change) VALUES (?,?,?,?,?)",
                            (pk["ticker"], int(time.time()), pk["mc"], pk["price"], pk["change"]))
                        n_ins += 1
                    con_h.commit(); con_h.close()
                    last_visit["home_trending"] = now
                    log(f"[sidebar] {n_ins} tokens → fomo_price_history")
                except Exception as e:
                    log(f"[sidebar] ERR {str(e)[:80]}")
                time.sleep(2)
            # 0b) l'onglet Most held de la sidebar (ce que les baleines détiennent)
            if now - last_visit.get("most_held", 0) > 30 * 60:
                try:
                    from login_window_miner import parse_trending
                    page.locator('text="Most held"').first.click(timeout=6000)
                    page.wait_for_timeout(4000)
                    text = page.evaluate("() => document.body.innerText")
                    parsed = parse_trending(text)
                    con_h = sqlite3.connect(str(WDB), timeout=30)
                    con_h.execute("PRAGMA busy_timeout=30000")
                    for pk in parsed:
                        con_h.execute(
                            "INSERT OR REPLACE INTO fomo_price_history "
                            "(ticker, captured_at, mc, price, change) VALUES (?,?,?,?,?)",
                            (pk["ticker"], int(time.time()), pk["mc"], pk["price"], pk["change"]))
                    con_h.commit(); con_h.close()
                    last_visit["most_held"] = now
                    log(f"[most_held] {len(parsed)} tokens")
                except Exception as e:
                    log(f"[most_held] ERR {str(e)[:70]}")
                time.sleep(2)
            # 1) les routes du walker dues
            for route in ROUTES:
                name = route["name"]
                if now - last_visit.get(name, 0) > CADENCES[name] * 60:
                    try:
                        lines, parsed = visit_route(page, route)
                        if route["parser"] in ("tokens", "bonding"):
                            store_tokens(con_walker, name, parsed)
                        elif route["parser"] == "alerts":
                            store_alerts(con_walker, parsed)
                        last_visit[name] = now
                        log(f"[{name}] {len(parsed)} entrées")
                    except Exception as e:
                        log(f"[{name}] ERR {str(e)[:80]}")
                    time.sleep(2)
            # 1b) le leaderboard top-100 (le parse du harvester, intégré)
            if now - last_visit.get("top100", 0) > 60 * 60:
                try:
                    from fomo_leaderboard_harvester import parse_leaderboard_text, CONFIG, knum as _k
                    page.goto("https://fomo.family/leaderboard",
                              wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)
                    text = page.evaluate("() => document.body.innerText")
                    rows = parse_leaderboard_text(text)
                    now_i = int(time.time())
                    con_lb = sqlite3.connect(str(ROOT / "data" / "fomo" / "fomo_swaps.db"), timeout=30)
                    con_lb.execute("PRAGMA busy_timeout=30000")
                    con_lb.execute("DELETE FROM dom_leaderboard")
                    for rank, name, handle, pnl, trades in rows:
                        con_lb.execute(
                            "INSERT OR REPLACE INTO dom_leaderboard VALUES (?,?,?,?,?,?)",
                            (rank, name, handle, pnl, trades, now_i))
                    con_lb.commit()
                    top = [h for _, _, h, _, _ in
                           sorted(rows, key=lambda r: r[3] or 0, reverse=True)[:20]]
                    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
                    cfg["top_handles"] = top
                    cfg["top_handles_updated_at"] = now_i
                    CONFIG.write_text(json.dumps(cfg, indent=1))
                    con_lb.close()
                    last_visit["top100"] = now
                    log(f"[top100] {len(rows)} traders, l'élite régénérée")
                except Exception as e:
                    log(f"[top100] ERR {str(e)[:80]}")
                time.sleep(2)
            # 1c) la santé de session (le moniteur intégré)
            if now - last_visit.get("session", 0) > 30 * 60:
                try:
                    import base64 as _b64
                    tok = (page.evaluate("() => localStorage.getItem('privy:token')")
                           or "").strip().strip('"')
                    alive = False
                    if len(tok) > 100:
                        pl = tok.split(".")[1]; pl += "=" * (-len(pl) % 4)
                        exp = json.loads(_b64.urlsafe_b64decode(pl)).get("exp", 0)
                        alive = exp - time.time() > 900
                    if not alive:
                        log("session faible → reload de sauvetage")
                        page.goto("https://fomo.family/", wait_until="domcontentloaded",
                                  timeout=30000)
                        page.wait_for_timeout(6000)
                    last_visit["session"] = now
                    log(f"[session] {'OK' if alive else 're-authentifiée au reload'}")
                except Exception as e:
                    log(f"[session] ERR {str(e)[:80]}")
                time.sleep(2)
            # 1d) les HOLDERS des tokens chauds (l'élite + le trending) :
            #     qui détient, son PnL, son MC d'entrée, sa thèse — le filtre
            #     anti-rug (top-10 holding) et la carte des baleines par token
            if now - last_visit.get("holders", 0) > 30 * 60:
                try:
                    from fomo_holders_parser import parse_holders, parse_token_header
                    con_s = sqlite3.connect(str(DB_SWAPS), timeout=30)
                    con_s.execute("PRAGMA busy_timeout=30000")
                    mints = [r[0] for r in con_s.execute(
                        """SELECT DISTINCT token_addr FROM ws_swaps
                        WHERE top_trader=1 AND token_addr IS NOT NULL
                        ORDER BY captured_at DESC LIMIT 8""")]
                    con_s.close()
                    con_t = sqlite3.connect(str(WDB), timeout=30)
                    con_t.execute("PRAGMA busy_timeout=30000")
                    for (m,) in con_t.execute(
                            """SELECT DISTINCT t.mint FROM fomo_price_history ph
                            JOIN fomo_tokens t ON t.ticker = ph.ticker
                            WHERE t.mint IS NOT NULL ORDER BY ph.captured_at DESC LIMIT 4"""):
                        if m not in mints:
                            mints.append(m)
                    con_t.close()
                    captured = 0
                    for mint in mints[:12]:
                        chain = "ethereum" if mint.startswith("0x") else "solana"
                        try:
                            page.goto(f"https://fomo.family/tokens/{chain}/{mint}",
                                      wait_until="domcontentloaded", timeout=25000)
                            page.wait_for_timeout(5000)
                            page.locator('text="Holders"').first.click(timeout=6000)
                            page.wait_for_timeout(3000)
                            txt = page.evaluate("() => document.body.innerText")
                            rows = parse_holders(txt, "")
                            hdr = parse_token_header(txt)
                            now_i = int(time.time())
                            con_h = sqlite3.connect(str(WDB), timeout=30)
                            con_h.execute("PRAGMA busy_timeout=30000")
                            con_h.execute("""CREATE TABLE IF NOT EXISTS fomo_token_holders (
                                mint TEXT, handle TEXT, position_usd REAL, qty TEXT,
                                ticker TEXT, pnl_usd REAL, pnl_pct REAL, entry_mc TEXT,
                                entry_price REAL, avg_hold TEXT, thesis_likes INTEGER,
                                thesis TEXT, captured_at INTEGER,
                                PRIMARY KEY (mint, handle, captured_at))""")
                            con_h.execute("""CREATE TABLE IF NOT EXISTS fomo_token_header (
                                mint TEXT PRIMARY KEY, market_cap TEXT, holders TEXT,
                                liquidity TEXT, top10_holding_pct REAL, buys INTEGER,
                                sells INTEGER, buyers INTEGER, sellers INTEGER,
                                captured_at INTEGER)""")
                            for r in rows:
                                con_h.execute(
                                    """INSERT OR REPLACE INTO fomo_token_holders
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                    (mint, r["handle"], r["position_usd"], r["qty"],
                                     r["ticker"], r["pnl_usd"], r["pnl_pct"],
                                     r["entry_mc"], r["entry_price"], r["avg_hold"],
                                     r["thesis_likes"], r["thesis"], now_i))
                            con_h.execute(
                                """INSERT OR REPLACE INTO fomo_token_header
                                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                (mint, hdr["market_cap"], hdr["holders"],
                                 hdr["liquidity"], hdr["top10_holding_pct"],
                                 hdr["buys"], hdr["sells"], hdr["buyers"],
                                 hdr["sellers"], now_i))
                            con_h.commit(); con_h.close()
                            captured += 1
                        except Exception as e:
                            log(f"  holders {mint[:10]} ERR {str(e)[:60]}")
                    last_visit["holders"] = now
                    log(f"[holders] {captured}/{len(mints[:12])} tokens capturés")
                except Exception as e:
                    log(f"[holders] ERR {str(e)[:80]}")
                time.sleep(2)
            # 1e) l'ARCHIVE DES THÈSES par token (le tab « Thesis » = le filtre
            #     holders-avec-thèse : le texte + les likes = le score social)
            if now - last_visit.get("theses", 0) > 30 * 60:
                try:
                    from fomo_holders_parser import parse_holders
                    con_s2 = sqlite3.connect(str(DB_SWAPS), timeout=30)
                    con_s2.execute("PRAGMA busy_timeout=30000")
                    mints = [r[0] for r in con_s2.execute(
                        """SELECT DISTINCT token_addr FROM ws_swaps
                        WHERE top_trader=1 AND token_addr IS NOT NULL
                        ORDER BY captured_at DESC LIMIT 8""")]
                    con_s2.close()
                    captured = 0
                    for mint in mints[:8]:
                        chain = "ethereum" if mint.startswith("0x") else "solana"
                        try:
                            page.goto(f"https://fomo.family/tokens/{chain}/{mint}",
                                      wait_until="domcontentloaded", timeout=25000)
                            page.wait_for_timeout(5000)
                            page.locator('text="Thesis"').first.click(timeout=6000)
                            page.wait_for_timeout(3000)
                            txt = page.evaluate("() => document.body.innerText")
                            rows = parse_holders(txt, "")
                            if not rows:
                                continue
                            now_i = int(time.time())
                            con_th = sqlite3.connect(str(WDB), timeout=30)
                            con_th.execute("PRAGMA busy_timeout=30000")
                            con_th.execute("""CREATE TABLE IF NOT EXISTS fomo_token_theses (
                                mint TEXT, handle TEXT, position_usd REAL,
                                pnl_pct REAL, entry_mc TEXT, avg_hold TEXT,
                                thesis_likes INTEGER, thesis TEXT, captured_at INTEGER,
                                PRIMARY KEY (mint, handle, captured_at))""")
                            for r in rows:
                                if not r["thesis"] or r["thesis"] == "—":
                                    continue
                                con_th.execute(
                                    """INSERT OR REPLACE INTO fomo_token_theses
                                    VALUES (?,?,?,?,?,?,?,?,?)""",
                                    (mint, r["handle"], r["position_usd"],
                                     r["pnl_pct"], r["entry_mc"], r["avg_hold"],
                                     r["thesis_likes"], r["thesis"], now_i))
                            con_th.commit(); con_th.close()
                            captured += 1
                        except Exception as e:
                            log(f"  theses {mint[:10]} ERR {str(e)[:50]}")
                    last_visit["theses"] = now
                    log(f"[theses] {captured} tokens archivés")
                except Exception as e:
                    log(f"[theses] ERR {str(e)[:80]}")
                time.sleep(2)
            # 2) les clans / le feed
            for name, fn in (("clans", visit_clans), ("feed", visit_feed)):
                if now - last_visit.get(name, 0) > CADENCES[name] * 60:
                    try:
                        n = fn(page)
                        last_visit[name] = now
                        log(f"[{name}] {n} chars capturés")
                    except Exception as e:
                        log(f"[{name}] ERR {str(e)[:80]}")
                    time.sleep(2)
            # 3) les profils : l'élite + les holders skilles DÉCOUVERTS
            #    (la boucle auto-nourrie : un holder avec un bon PnL = un
            #    candidat élite qui entre automatiquement dans la rotation)
            if now - last_visit.get("profiles", 0) > CADENCES["profiles"] * 60:
                candidates = list(TOP_HANDLES)
                try:
                    con_d = sqlite3.connect(str(WDB), timeout=30)
                    con_d.execute("PRAGMA busy_timeout=30000")
                    for (h,) in con_d.execute(
                            """SELECT handle FROM fomo_token_holders
                            WHERE pnl_pct > 100 AND position_usd > 3000
                              AND handle NOT IN (SELECT handle FROM dom_leaderboard)
                            GROUP BY handle ORDER BY AVG(pnl_pct) DESC LIMIT 20"""):
                        if h not in candidates:
                            candidates.append(h)
                    con_d.close()
                except Exception:
                    pass
                handle = candidates[profile_idx % len(candidates)]
                try:
                    con_swaps2 = ensure_swaps_db()
                    now_i = int(time.time())
                    log_fn = lambda m: log(f"  [profil {handle}] {m}")
                    base, open_rows, closed_rows = _mine_profile_light(
                        page, handle, con_swaps2, now_i)
                    con_swaps2.close()
                    log(f"[profiles] {handle} : {len(open_rows)} courantes + "
                        f"{len(closed_rows)} top trades")
                    profile_idx += 1
                except Exception as e:
                    log(f"[profiles] {handle} ERR {str(e)[:80]}")
                last_visit["profiles"] = now
                time.sleep(2)
            # 4) le résumé toutes les 10 min
            if now - state.get("last_summary", 0) > 600:
                log(f"résumé : {listener.summary()}")
                state["last_summary"] = now
                STATE_F.write_text(json.dumps(
                    {"last_visit": last_visit, "profile_idx": profile_idx,
                     "last_summary": state["last_summary"]}))
            time.sleep(30)
    finally:
        try:
            if listener and listener.cdp:
                listener.cdp.detach()
        except Exception:
            pass
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        con_swaps.close()
        con_walker.close()
        pw.stop()


def _mine_profile_light(page, handle, con, now):
    """Le profil sans le mineur CLI : la même recette, la page du worker."""
    from fomo_top_traders_miner import mouse_click_text, TRADES_RE, POS_RE, knum, STATS_RE
    page.goto("about:blank")
    time.sleep(0.4)
    page.goto(f"https://fomo.family/profile/{handle}?r={now}",
              wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    text = page.evaluate("() => document.body.innerText")
    rows = [(tk, knum(i), h.strip(), knum(p), float(pc.replace(",", "")))
            for tk, i, h, p, pc in TRADES_RE.findall(text)]
    # la vue investie (les top trades fermés)
    mouse_click_text(page, "Open", pick="first")
    text = page.evaluate("() => document.body.innerText")
    for tk, inv, h, pnl, pc in TRADES_RE.findall(text):
        try:
            rows.append((tk, knum(inv), h.strip(), knum(pnl), float(pc.replace(",", ""))))
        except Exception:
            pass
    for tk, inv, h, pnl, pc in rows:
        con.execute("INSERT OR IGNORE INTO dom_profile_trades VALUES (?,?,?,?,?,?,?,?)",
                    (handle, tk, inv, h, pnl, pc, 1, now))
    # les positions courantes (la vue par défaut)
    page.goto("about:blank"); time.sleep(0.4)
    page.goto(f"https://fomo.family/profile/{handle}?c={now}",
              wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)
    text2 = page.evaluate("() => document.body.innerText")
    cur = POS_RE.findall(text2)
    # le graphe social : mutuals / following / followers → ws_traders
    import re as _re
    m_mut = _re.search(r"(\d+)\s*\nMutuals", text2) or _re.search(r"(\d+) Mutuals", text2)
    m_fol = _re.search(r"(\d+)\s*\nFollowing", text2) or _re.search(r"([\d.,]+[KMB]?) Following", text2)
    m_fers = _re.search(r"([\d.,]+[KMB]?)\s*\nFollowers", text2) or _re.search(r"([\d.,]+[KMB]?) Followers", text2)
    try:
        def _knum(s):
            if not s: return None
            s = s.replace(",", "")
            mult = {"K": 1e3, "M": 1e6, "B": 1e9}.get(s[-1], 1) if s and s[-1].isalpha() else 1
            return float(s.rstrip("KMB")) * mult
        con.execute(
            "UPDATE ws_traders SET mutuals=?, following=?, followers=? WHERE handle=?",
            (int(m_mut.group(1)) if m_mut else None,
             _knum(m_fol.group(1)) if m_fol else None,
             _knum(m_fers.group(1)) if m_fers else None, handle))
        con.commit()
    except Exception:
        pass
    for tk, q, v, pc in cur:
        con.execute("INSERT OR REPLACE INTO dom_profile_positions VALUES (?,?,?,?,?,?,?)",
                    (handle, tk, q, knum(v), float(pc), "current", now))
    return [], rows, cur


if __name__ == "__main__":
    sys.exit(main())
