#!/usr/bin/env python3
"""LE HARVESTER DE TOKEN D'ACCÈS (29/09) — la solution ingénieuse au mur
d'auth : l'app fomo elle-même rafraîchit son token d'accès en continu
(son propre polling) → le harvester capte ces tokens via le CDP Network
et les met à disposition des collecteurs (access_token_live.json).
Le user se logge UNE FOIS, le harvester garde le token frais pour toujours."""
import sys, json, time, base64
from pathlib import Path
from patchright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "fomo" / "access_token_live.json"
CDP_LOGIN = "http://127.0.0.1:9223"    # la fenêtre de login (l'app + le user connecté)
CDP_DAEMON = "http://127.0.0.1:9222"   # le daemon (les collecteurs)


def decode_exp(tok: str) -> int:
    try:
        p = tok.split(".")[1].replace("-", "+").replace("_", "/")
        return int(json.loads(base64.b64decode(p + "=" * (-len(p) % 4))).get("exp", 0))
    except Exception:
        return 0


def harvest_once(seconds: float = 45.0) -> str | None:
    """La capture des Bearer tokens de l'app pendant `seconds` — le dernier gagne."""
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(CDP_LOGIN, timeout=8000)
        ctx = browser.contexts[0] if browser.contexts else browser
        page = next((p for p in ctx.pages if "fomo.family" in (p.url or "")), None)
        if not page:
            print("[harvest] pas de page fomo.family dans la fenêtre de login")
            return None
        # L'INJECTION PERSISTANTE : le patch survit aux reloads et s'exécute
        # AVANT le code de l'app (addScriptToEvaluateOnNewDocument) — les
        # appels initiaux de l'app sont capturés dès le chargement.
        PATCH_JS = """() => {
            window.__harvest_tokens = [];
            const capture = (auth) => {
                if (auth && auth.startsWith && auth.startsWith('Bearer ey')) {
                    window.__harvest_tokens.push({t: auth.slice(7), ts: Date.now()});
                }
            };
            const origFetch = window.fetch;
            window.fetch = function(...args) {
                try {
                    const req = args[0], opts = args[1] || {};
                    let auth = null;
                    if (req && req.headers) {
                        if (req.headers.get) auth = req.headers.get('authorization');
                        else if (req.headers.authorization) auth = req.headers.authorization;
                    }
                    if (!auth && opts && opts.headers) {
                        const hh = opts.headers;
                        if (hh.get) auth = hh.get('authorization');
                        else if (hh.authorization) auth = hh.authorization;
                        else if (typeof hh === 'object') auth = hh['Authorization'] || hh['authorization'];
                    }
                    capture(auth);
                } catch(e) {}
                return origFetch.apply(this, args);
            };
            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, ...rest) {
                this.addEventListener('send', function() {
                    try { capture(this.getRequestHeader('Authorization') || this.getRequestHeader('authorization')); } catch(e) {}
                });
                return origOpen.apply(this, [method, url, ...rest]);
            };
        }"""
        cdp = ctx.new_cdp_session(page)
        cdp.send("Page.enable")
        cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": PATCH_JS})
        # le reload → le patch s'exécute avant l'app → les appels initiaux capturés
        try: page.reload(timeout=25000, wait_until="domcontentloaded")
        except Exception: pass
        time.sleep(6)
        best = {"tok": None, "exp": 0}

        def read_tokens():
            try:
                toks = page.evaluate("() => window.__harvest_tokens || []")
                for t in toks:
                    exp = decode_exp(t["t"])
                    if exp > best["exp"]:
                        best["tok"], best["exp"] = t["t"], exp
            except Exception: pass

        t0 = time.time()
        while time.time() - t0 < seconds:
            read_tokens()
            if best["tok"] and time.time() - t0 > 3:
                break
            time.sleep(1)
        # la sauvegarde
        if best["tok"]:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            prev = {}
            if OUT.exists():
                try:
                    prev = json.loads(OUT.read_text())
                    if prev.get("exp", 0) > best["exp"]:
                        best["tok"] = prev["token"]; best["exp"] = prev["exp"]
                except Exception: pass
            OUT.write_text(json.dumps({"token": best["tok"], "exp": best["exp"],
                                       "harvested_at": time.time()}))
        return best["tok"]
    finally:
        pw.stop()


def main() -> int:
    tok = harvest_once()
    if not tok:
        print("[harvest] aucun token capturé — l'app ne fait pas d'appels authentifiés")
        return 1
    exp = decode_exp(tok)
    mins = int((exp - time.time()) / 60)
    print(f"[harvest] token capturé : {tok[:25]}… len={len(tok)} | exp dans {mins} min")
    return 0


if __name__ == "__main__":
    sys.exit(main())
