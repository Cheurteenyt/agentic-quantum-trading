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
        # la purge des onglets FANTÔMES du worker/miner (les marqueurs ?r=, ?c=,
        # ?fresh=, ?ws=, ?bot= = nos pages tuées avant le close) — JAMAIS les
        # onglets du user (sans marqueur)
        for p2 in list(ctx.pages):
            u = p2.url or ""
            marked = "fomo.family" in u and any(f"?{m}=" in u for m in ("r", "c", "fresh", "ws", "bot"))
            dead_shell = False
            if "fomo.family" in u and not marked:
                try:
                    if len(p2.evaluate("() => document.body.innerText")) < 100:
                        dead_shell = True  # une coquille morte (feed vide au crash, etc.)
                except Exception:
                    dead_shell = True
            if marked or dead_shell:
                try:
                    p2.close()
                    log(f"onglet purgé ({'marqué' if marked else 'coquille morte'}) : {u[:60]}")
                except Exception:
                    pass
        page = ctx.new_page()  # la page DÉDIÉE du worker — détenue pour toujours
        # la page Tokens = le domicile des routes (les boutons Trending/Bonding/…)
        page.goto("https://fomo.family/tokens", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)
        listener = FrameListener(page)
        log(f"worker DOM résident démarré — la page dédiée, "
            f"{len(CADENCES)} surfaces, le listener WS passif actif")

        while True:
            now = time.time()
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
            # 3) les profils top traders (1 par cycle = le round-robin, la vue investie)
            if now - last_visit.get("profiles", 0) > CADENCES["profiles"] * 60:
                handle = TOP_HANDLES[profile_idx % len(TOP_HANDLES)]
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
    for tk, q, v, pc in cur:
        con.execute("INSERT OR REPLACE INTO dom_profile_positions VALUES (?,?,?,?,?,?,?)",
                    (handle, tk, q, knum(v), float(pc), "current", now))
    return [], rows, cur


if __name__ == "__main__":
    sys.exit(main())
