#!/usr/bin/env python
"""Harvester fomo.family headless — le Whale Radar automatisable.

Même discipline que x_harvest : profil patchright persistant (login manuel
UNE fois), ensuite tout tourne headless (systemd-ready). Le DOM fomo
virtualise ses listes : l'extraction des positions utilise la signature de
ligne (ticker × quantité × ticker × $valeur ▲/▼ %) + scroll accumulé.

Usage :
  python scripts/fomo_harvest.py --login              # UNE fois : fenêtre visible
  python scripts/fomo_harvest.py --status             # session valide ?
  python scripts/fomo_harvest.py --positions unipcs   # positions d'un trader (JSON)
  python scripts/fomo_harvest.py --leaderboard        # top 150 × 3 fenêtres (JSON)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "fomo_browser_profile"
BASE = "https://fomo.family"
LOGIN_TIMEOUT_S = 900

EXTRACT_POSITIONS_JS = """
() => {
  const out = {};
  const re = /^(\\S.{0,22}?)\\s+([\\d.,]+[KkMm]?)\\s+\\1\\s+\\$([\\d,.]+)\\s+([▲▼])(?:\\s+[-−]?([\\d.,]+)%)?/;
  for (const el of document.querySelectorAll("button, div")) {
    const txt = (el.innerText || "").replace(/\\n+/g, " ").trim();
    if (txt.length > 90) continue;
    const m = txt.match(re);
    if (!m) continue;
    const ticker = m[1].trim();
    if (ticker === "+" || out[ticker]) continue;
    out[ticker] = { qty: m[2], value_usd: parseFloat(m[3].replace(/,/g, "")), dir: m[4],
                    pnl_pct: m[5] ? parseFloat(m[5].replace(/,/g, "")) : null };
  }
  return out;
}
"""

EXTRACT_LEADERBOARD_JS = """
() => {
  const rows = [];
  for (const a of document.querySelectorAll('a[href*="/profile/"]')) {
    const handle = a.getAttribute("href").split("/profile/")[1].split(/[?#]/)[0];
    const txt = (a.innerText || "").replace(/\\n+/g, "|");
    const m = txt.match(/@([^|]+)\\|\\+\\s*\\|\\$([\\d,.]+)(?:\\|(\\d+)\\+)?/);
    if (m && handle !== "DizzyOnlyClam")
      rows.push({ handle, pnl: parseFloat(m[2].replace(/,/g, "")),
                  trades: m[3] ? parseInt(m[3]) : null });
  }
  return rows;
}
"""


def _require_profile() -> None:
    if not PROFILE_DIR.exists():
        print("[fomo] profil absent — lance d'abord : --login", file=sys.stderr)
        raise SystemExit(1)


def _logged_in(page) -> bool:
    """Preuve POSITIVE de session (le bouton nav 'Leaderboard' n'existe que
    connecté ; l'absence du bouton Login seule est un faux positif de rendu)."""
    try:
        if page.locator("button:has-text('Login')").count() > 0:
            return False
        return (
            page.locator("button:has-text('Leaderboard')").count() > 0
            or page.locator("text=Deposit more").count() > 0
            or page.locator('a[href*="/profile/"]').count() > 0
        )
    except Exception:
        return False


def run_login() -> int:
    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        print("[login] fenêtre ouverte — connecte-toi à fomo. Détection auto…", flush=True)
        deadline = time.time() + LOGIN_TIMEOUT_S
        while time.time() < deadline:
            try:
                if _logged_in(page):
                    # double-confirmation après 3 s (le SPA peut finir de rendre)
                    page.wait_for_timeout(3000)
                    if _logged_in(page):
                        print("[login] session fomo valide — profil sauvegardé. Fermeture.",
                              flush=True)
                        time.sleep(2)
                        ctx.close()
                        return 0
            except Exception:
                pass
            time.sleep(3)
        print("[login] timeout : pas de session détectée en 15 min", file=sys.stderr)
        ctx.close()
        return 1


def check_status() -> int:
    from patchright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("[status] profil absent — --login requis")
        return 1
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE}/leaderboard", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)
        ok = _logged_in(page)
        ctx.close()
    print(f"[status] session fomo : {'VALIDE' if ok else 'EXPIREE/ABSENTE — relance --login'}")
    return 0 if ok else 1


def mine_positions(handle: str, scrolls: int = 10) -> dict:
    from patchright.sync_api import sync_playwright

    _require_profile()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(f"{BASE}/profile/{handle}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        seen: dict = {}
        for _ in range(scrolls):
            for ticker, v in (page.evaluate(EXTRACT_POSITIONS_JS) or {}).items():
                seen.setdefault(ticker, v)
            page.evaluate("window.scrollBy(0, 700)")
            page.wait_for_timeout(500)
        declared = page.evaluate(
            "() => { const m = (document.body.innerText||'').match(/Positions\\s*(\\d+)/);"
            " return m ? parseInt(m[1]) : null; }"
        )
        ctx.close()
    return {"handle": handle, "declared_positions": declared, "mined": seen}


def mine_leaderboard(windows: list[str]) -> dict:
    from patchright.sync_api import sync_playwright

    _require_profile()
    out: dict[str, list] = {}
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        labels = {"24h": "24H", "7d": "7D", "30d": "30D"}
        for w in windows:
            page.goto(f"{BASE}/leaderboard?range={w}", wait_until="domcontentloaded",
                      timeout=30000)
            page.wait_for_timeout(3500)
            # s'assurer que la bonne fenêtre est sélectionnée
            btn = page.locator(f"button:has-text('{labels.get(w, w)}')").first
            try:
                if btn.count() > 0 and btn.get_attribute("aria-pressed") != "true":
                    btn.click()
                    page.wait_for_timeout(2500)
            except Exception:
                pass
            out[w] = page.evaluate(EXTRACT_LEADERBOARD_JS)
        ctx.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Harvester fomo.family headless")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--positions", metavar="HANDLE")
    ap.add_argument("--leaderboard", action="store_true")
    args = ap.parse_args()
    if args.login:
        return run_login()
    if args.status:
        return check_status()
    if args.positions:
        print(json.dumps(mine_positions(args.positions), indent=1, ensure_ascii=False))
        return 0
    if args.leaderboard:
        print(json.dumps(mine_leaderboard(["24h", "7d", "30d"]), indent=1, ensure_ascii=False))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
