#!/usr/bin/env python3
"""Le worker DOM résident — la session JWT + le listener WS passif.

Un service, UNE page dédiée permanente dans le navigateur dédié (:9222
fallback :9223). MIGRATION REST (29/09) : les 8 surfaces de collecte
(sidebar, most_held, top100, holders, theses, clans, feed, profiles) et le
walker sont couverts par fomo_rest_collector.py — il reste la santé de
session (le bootstrap JWT, do_session) + le LISTENER WS passif : les frames
des souscriptions naturelles de l'app sont capturées → l'inventaire des
topics qu'on ne connaît pas.

Les règles (gravées) : jamais d'itération des onglets du user ; le worker =
seul propriétaire du navigateur dédié ; les écritures = sur fomo_swaps.db
(fomo.db = la base chaude du daemon, verrouillée).
"""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from fomo_top_traders_miner import ensure_db as ensure_swaps_db
from patchright.sync_api import sync_playwright

DB_SWAPS = ROOT / "data" / "fomo" / "fomo_swaps.db"
STATE_F = ROOT / "data" / "fomo" / "dom_worker_state.json"
FRAMES_F = ROOT / "data" / "fomo" / "ws_frame_parking.jsonl"
LOCK = ROOT / "data" / "fomo" / ".dom_worker.lock"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def ensure_tables():
    """Les tables DOM du worker — TOUTES sur fomo_swaps.db (fomo.db = la
    base chaude du daemon : tout write = « database is locked »)."""
    con = sqlite3.connect(str(DB_SWAPS), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("""CREATE TABLE IF NOT EXISTS clans_raw (
        snapshot_ts INTEGER PRIMARY KEY, text TEXT, parsed INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS feed_raw (
        snapshot_ts INTEGER PRIMARY KEY, text TEXT, parsed INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_price_history (
        ticker TEXT, captured_at INTEGER, mc REAL, price REAL, change REAL,
        PRIMARY KEY (ticker, captured_at))""")
    # l'historique des swaps par token — la courbe de vie MC-par-trade ;
    # le schéma = le dict de parse_token_swaps + mint
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_token_swap_history (
        mint TEXT, handle TEXT, action TEXT, usd REAL, mc TEXT,
        time_rel TEXT, captured_at INTEGER,
        PRIMARY KEY (mint, handle, action, usd, mc, time_rel))""")
    # l'archive BRUTE des frames du listener (le drain du parking) — le
    # parking regonfle ~130 Mo/jour tant qu'il n'est pas drainé
    con.execute("""CREATE TABLE IF NOT EXISTS ws_parking_frames (
        line_hash TEXT PRIMARY KEY, raw TEXT)""")
    # la rétention (audit 30/09) : la table n'avait AUCUNE colonne temporelle
    # → captured_at INTEGER (SECONDES = l'unité du champ ts du frame JSON,
    # sonde 30/09 : {"ts": 1790727982, ...}) — DDL dans ensure_*
    try:
        con.execute("ALTER TABLE ws_parking_frames ADD COLUMN captured_at INTEGER")
    except sqlite3.OperationalError:
        pass  # colonne déjà présente
    rows = con.execute("SELECT rowid, raw FROM ws_parking_frames "
                       "WHERE captured_at IS NULL LIMIT 50000").fetchall()
    if rows:  # le backfill one-shot : le ts = le 1er champ du JSON brut
        buf = []
        for rid, raw in rows:
            try:
                ts = int(json.loads(raw).get("ts") or 0) or None
            except Exception:
                ts = None
            buf.append((ts, rid))
        con.executemany("UPDATE ws_parking_frames SET captured_at=? "
                        "WHERE rowid=?", buf)
        log(f"[parking] backfill captured_at : {len(buf)} frames horodatées")
    con.commit(); con.close()


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
            if data and self.sent_log.count(data[:80]) < 2:
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
            if tt not in ("prices",):
                with open(FRAMES_F, "a") as fh:
                    fh.write(json.dumps({"ts": int(time.time()), "topicType": tt,
                                         "payload": data[:2000]}) + "\n")
        except Exception:
            pass

    def summary(self):
        return f"{self.n_frames} frames ({json.dumps(self.counts)})"


# ============================ LES SURFACES ============================
# La signature uniforme : fn(page) → None (le log = à l'intérieur).
# Le scheduler appelle, horodate last_visit, ne connaît rien d'autre.


def do_session(page):
    """La santé de session : le jeton faible = reload (le Privy re-auth
    silencieux) ; mort = l'alerte explicite."""
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
    log(f"[session] {'OK' if alive else 're-authentifiée au reload'}")


def flush_parking(con):
    """Le drain du parking : les frames du listener → l'archive brute
    ws_parking_frames (fomo_swaps.db, PK = sha1 de la ligne — idempotent).
    Le truncate du fichier arrive SEULEMENT après le commit : un crash au
    milieu = re-drain sans doublon, jamais de perte (la doctrine anti-txn-
    fantôme du 29/09)."""
    import hashlib
    if not FRAMES_F.exists():
        return
    with open(FRAMES_F) as fh:
        lines = [l for l in fh.read().splitlines() if l.strip()]
    if not lines:
        return
    ch0 = con.total_changes
    for i in range(0, len(lines), 2000):
        buf = []
        for l in lines[i:i + 2000]:
            try:  # le ts (secondes) = le 1er champ du frame JSON
                ts = int(json.loads(l).get("ts") or 0) or None
            except Exception:
                ts = None
            buf.append((hashlib.sha1(l.encode()).hexdigest(), l[:4000], ts))
        con.executemany("INSERT OR IGNORE INTO ws_parking_frames "
                        "(line_hash, raw, captured_at) VALUES (?,?,?)", buf)
        con.commit()
    n_new = con.total_changes - ch0
    open(FRAMES_F, "w").close()  # le truncate APRÈS le commit
    log(f"[parking] drainé : {len(lines)} frames → archive "
        f"({n_new} nouvelles)")


# La rétention de l'archive du parking (audit 30/09) : ws_parking_frames
# > 7 j, purgée au drain. Unité VÉRIFIÉE : captured_at = les SECONDES du
# champ ts du frame JSON (colonne ajoutée + backfillée dans ensure_tables).
PARKING_RETENTION_DAYS = 7
_last_prune_day = -1


def prune_parking(con):
    """Le purge 1×/j (le dernier jour de prune en mémoire) : DELETE
    paramétré par captured_at, COMMIT explicite, compte loggué."""
    global _last_prune_day
    day = int(time.time() // 86400)
    if day == _last_prune_day:
        return
    _last_prune_day = day
    try:
        cutoff = int(time.time()) - PARKING_RETENTION_DAYS * 86400
        cur = con.execute("DELETE FROM ws_parking_frames "
                          "WHERE captured_at < ?", (cutoff,))
        con.commit()
    except sqlite3.Error as e:
        _last_prune_day = -1  # DB occupée : re-tente au prochain drain
        log(f"[prune] parking err : {str(e)[:80]}")
        return
    if cur.rowcount:
        log(f"[prune] parking : {cur.rowcount} frames > "
            f"{PARKING_RETENTION_DAYS}j supprimées de l'archive")


# La TABLE DE ROUTES : (nom, cadence_min, fn, les args extra)
# MIGRATION REST (29/09 soir) : 8 surfaces tuées — couvertes par
# fomo_rest_collector.py (la carte : scripts/studies/fomo_rest_map.md,
# 100 % des endpoints rejoués 200) : sidebar, most_held (le clic 6000 ms),
# top100, holders, theses, clans, feed, profiles. Restent : session
# (le bootstrap JWT).
# MIGRATION REST (29/09, phase 2) : walker tué — DERNIÈRE navigation DOM
# supprimée. fomo_new_coins (tab='bonding') est remplacé par le snapshot
# REST bonding (fomo_rest.db, fomo_rest_snapshots endpoint='bonding_snapshot',
# écrit par fomo_rest_collector.py) ; les 5 lecteurs migrés : daily_brief,
# bonding_signal_study, fomo_bonding_monitor, fomo_history_collector,
# fomo_bonding_resolve.
SCHEDULE = [
    # ("walker", 0, lambda page, lv=None, c=None: None, ()),  # TUÉE 29/09 (voir note ci-dessus)
    ("session", 30, do_session, ()),
]


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
            pass
    con_mig.commit(); con_mig.close()
    state = json.loads(STATE_F.read_text()) if STATE_F.exists() else {}
    last_visit = state.get("last_visit", {})

    pw = sync_playwright().start()
    page = None
    listener = None
    con_swaps = ensure_swaps_db()
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
        # :9222 = NOTRE navigateur dédié : la propriété totale — les pages
        # fomo = purgées au boot, le worker = le SEUL créateur de pages
        for p2 in list(ctx.pages):
            if "fomo.family" in (p2.url or ""):
                try:
                    p2.close()
                except Exception:
                    pass
        log("les pages fomo purgées — le worker = seul propriétaire du navigateur")
        # la page DÉDIÉE : le retry avec l'ESCALADE — au 2e échec, le
        # navigateur dédié = HS → restart du service fomo-browser
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
        page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)
        listener = FrameListener(page)
        log(f"worker DOM résident démarré — la page dédiée, "
            f"{len(SCHEDULE)} surfaces, le listener WS passif actif")

        while True:
            now = time.time()
            page = ensure_page(ctx, page)
            for name, cadence, fn, extra in SCHEDULE:
                if now - last_visit.get(name, 0) > cadence * 60:
                    try:
                        fn(page)
                    except Exception as e:
                        log(f"[{name}] ERR {str(e)[:80]}")
                    last_visit[name] = now
                    time.sleep(2)
            if now - state.get("last_parking_flush", 0) > 600:
                try:
                    flush_parking(con_swaps)
                except Exception as e:
                    log(f"[parking] ERR {str(e)[:80]}")
                state["last_parking_flush"] = now
            prune_parking(con_swaps)  # la purge 1×/j de l'archive (check date interne)
            if now - state.get("last_summary", 0) > 600:
                log(f"résumé : {listener.summary()}")
                state["last_summary"] = now
                STATE_F.write_text(json.dumps(
                    {"last_visit": last_visit,
                     "last_summary": state["last_summary"],
                     "last_parking_flush": state["last_parking_flush"]}))
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
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
