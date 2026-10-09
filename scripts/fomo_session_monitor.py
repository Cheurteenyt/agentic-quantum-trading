#!/usr/bin/env python3
"""Le moniteur de session fomo — que le navigateur ne se déconnecte plus seul.

Le jeton Privy expire toutes les heures ; l'app le renouvelle via son iframe
tant que la page vit. Ce moniteur (1×/5 min) :
  1. lit l'expiration du privy:token dans notre navigateur persistant (:9222
     fallback :9223),
  2. si < 10 min de vie OU absent → page.reload() (le Privy re-authentifie
     silencieusement au boot),
  3. si toujours mort après le reload → ALERTE explicite dans le journal
     (« login manuel requis ») — l'anti-bot Privy interdit le re-login autonome.
"""
import base64
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts.secret_io import write_secret  # noqa: E402
STATE_F = ROOT / "data" / "fomo" / "session_state.json"
JWT_CACHE = ROOT / "data" / "fomo" / "ws_jwt_cache.txt"


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def token_exp(page):
    tok = (page.evaluate("() => localStorage.getItem('privy:token')") or "").strip().strip('"')
    if len(tok) < 100:
        return None, tok
    try:
        p = tok.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("exp", 0), tok
    except Exception:
        return 0, tok


def main():
    import fcntl
    lk = open(ROOT / "data" / "fomo" / ".session_monitor.lock", "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0

    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    page = None
    try:
        browser = None
        for port in ("9222", "9223"):
            try:
                browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}",
                                                       timeout=8000)
                break
            except Exception:
                continue
        if browser is None:
            log("ALERTE : aucun navigateur CDP joignable (:9222/:9223)")
            return 1
        lctx = browser.contexts[0] if browser.contexts else browser
        page = next((p for p in lctx.pages if "fomo.family" in (p.url or "")), None)
        if page is None:
            page = lctx.new_page()
            page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(6)

        exp, tok = token_exp(page)
        now = int(time.time())
        if exp and exp - now > 600:
            # la session = saine — alimenter le cache du daemon (le gratuit)
            try:
                cached = JWT_CACHE.read_text().strip().strip('"') if JWT_CACHE.exists() else ""
                if cached != tok:
                    write_secret(JWT_CACHE, tok)
            except Exception:
                pass
            state = {"status": "ok", "exp": exp, "checked_at": now}
            log(f"session OK — {exp - now}s de vie")
        else:
            # la session = faible/morte → le reload = la tentative de sauvetage
            log(f"session faible (exp={exp}, maintenant={now}) → reload de la page")
            try:
                page.reload(wait_until="domcontentloaded", timeout=30000)
                time.sleep(8)
            except Exception as e:
                log(f"reload ERR {str(e)[:80]}")
            exp2, tok2 = token_exp(page)
            if exp2 and exp2 - now > 600:
                log("session SAUVÉE par le reload — le Privy a re-authentifié silencieusement")
                try:
                    write_secret(JWT_CACHE, tok2)
                except Exception:
                    pass
                state = {"status": "revived", "exp": exp2, "checked_at": now}
            else:
                log("⚠️ ALERTE : SESSION MORTE — login manuel requis dans la fenêtre "
                    "fomo-whale (Chrome for Testing). Le flux temps réel est en pause.")
                state = {"status": "dead", "exp": exp2, "checked_at": now}
        STATE_F.write_text(json.dumps(state))
        return 0
    finally:
        pw.stop()


if __name__ == "__main__":
    sys.exit(main())
