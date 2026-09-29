#!/usr/bin/env python3
"""CAPTURE DES FRAMES WS REÇUES PENDANT LES CLICS (RE, 29/09) — le one-shot
qui décide du refactor « mieux que du DOM » : page neuve sur :9222, collecte
CDP des frames via page.on('websocket') (framereceived/framesent — au niveau
navigateur, insensible aux mondes isolés de patchright), ouverture d'un token
puis clics Holders/Thesis/Swaps. Si holders/theses/swaps-history viennent
d'un topicType natif de prod-api, le worker DOM peut mourir (extension du
daemon). Sortie : reports/fomo_ws_frames_capture.json + résumé stdout.
Le dump est en finally : un crash ne perd plus les frames."""
import json, sys
from pathlib import Path
from patchright.sync_api import sync_playwright

# parents[2] : le script vit dans scripts/studies/ → la racine du repo
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "fomo_ws_frames_capture.json"
CDP = "http://127.0.0.1:9222"
SKIP_WORDS = {"MC", "BUY", "SELL", "TOKENS", "TRENDING", "GRADUATED", "BONDING",
              "MONITOR", "LIVE", "NEW", "MOST", "HELD", "WATCHLIST", "CRYPTO",
              "VOL", "SI", "AT", "AGE"}


def summarize(frames):
    socks = {}
    for f in frames:
        s = socks.setdefault(f["url"], {"send": 0, "recv": 0})
        s[f["dir"]] += 1
    kinds = {}
    for f in frames:
        if f["dir"] != "recv":
            continue
        key = "?"
        try:
            j = json.loads(f["data"])
            if isinstance(j, dict):
                key = str(j.get("topicType") or j.get("type") or j.get("event") or "?")
                tid = j.get("topicId")
                if isinstance(tid, str) and ":" in tid:
                    key += f" [*:{tid.rsplit(':', 1)[1]}]"
            else:
                key = f"ARR[{len(j)}]"
        except Exception:
            key = "RAW:" + f["data"][:26]
        kinds[key] = kinds.get(key, 0) + 1
    return socks, kinds


def main() -> int:
    frames = []

    def on_ws(ws):
        ws.on("framesent", lambda p: frames.append(
            {"dir": "send", "url": ws.url, "data": str(p)[:3000]}))
        ws.on("framereceived", lambda p: frames.append(
            {"dir": "recv", "url": ws.url, "data": str(p)[:3000]}))

    pw = sync_playwright().start()
    page = None
    try:
        browser = pw.chromium.connect_over_cdp(CDP, timeout=8000)
        ctx = browser.contexts[0] if browser.contexts else browser
        page = ctx.new_page()
        page.on("websocket", on_ws)
        try:
            page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(7000)
            print("frames homepage:", len(frames))

            tickers = page.evaluate("""() => {
                const out = [];
                for (const l of document.body.innerText.split('\\n')) {
                    const t = l.trim();
                    if (/^[A-Z0-9]{2,10}$/.test(t)) out.push(t);
                    if (out.length >= 20) break;
                }
                return out;
            }""")
            tickers = [t for t in tickers if t.upper() not in SKIP_WORDS]
            print("tickers candidats:", tickers)
            clicked = None
            for t in tickers[:6]:
                try:
                    loc = page.locator(f'text="{t}"')
                    for i in range(min(loc.count(), 5)):
                        try:
                            # force=True : les listes virtualisées cachent les
                            # éléments — on clique quand même par position
                            loc.nth(i).click(timeout=2500, force=True)
                            clicked = t
                            break
                        except Exception:
                            continue
                except Exception:
                    pass
                page.wait_for_timeout(1500)
                if len(frames) > 700 or clicked:
                    break
            print("token ouvert:", clicked, "| frames:", len(frames))
            page.wait_for_timeout(6000)
            for label in ("Holders", "Thesis", "Swaps"):
                try:
                    page.get_by_text(label, exact=False).first.click(timeout=4000, force=True)
                    print(f"clic {label}: OK")
                except Exception as e:
                    print(f"clic {label}: ERR {str(e)[:50]}")
                page.wait_for_timeout(3500)
        except Exception as e:
            print(f"phase clic interrompue: {str(e)[:80]}")
        finally:
            OUT.write_text(json.dumps(frames, ensure_ascii=False, indent=1))
            socks, kinds = summarize(frames)
            print("=== sockets ===")
            for u, s in socks.items():
                print(f"  {u[:80]} {s}")
            print("=== recv par topicType/type ===")
            for k, v in sorted(kinds.items(), key=lambda x: -x[1])[:30]:
                print(f"  {v:5d}  {k}")
            print(f"total frames: {len(frames)} → {OUT}")
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
