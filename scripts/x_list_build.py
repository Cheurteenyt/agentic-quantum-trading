#!/usr/bin/env python3
"""Crée la liste X PRIVÉE 'trading-agent' et y ajoute la watchlist.

La liste privée = la couverture temps réel des 49 comptes en UNE page
(minable par x_harvest --list sans throttle). Le compte connecté dans
data/x_browser_profile (patchright) exécute les clics — autorisation
explicite de l'utilisateur (2026-09-23).

  .venv/bin/python scripts/x_list_build.py            # crée + ajoute tout
  .venv/bin/python scripts/x_list_build.py --members  # complète seulement
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.x_harvest import PROFILE_DIR  # noqa: E402

ID_FILE = ROOT / "data" / "x_list_id.txt"
LIST_NAME = "trading-agent"


def log(msg: str) -> None:
    print(f"[liste] {msg}", file=sys.stderr, flush=True)


def watchlist_handles() -> list[str]:
    """Union des --profiles des unités trading-agent-* (nuit + midi)."""
    out: list[str] = []
    for p in (Path.home() / ".config" / "systemd" / "user").glob("trading-agent-*.service"):
        for line in p.read_text().splitlines():
            m = re.search(r"--profiles (\S+)", line)
            if m:
                out += [h.strip().lstrip("@") for h in m.group(1).split(",") if h.strip()]
    seen: set[str] = set()
    uni: list[str] = []
    for h in out:
        if h.lower() not in seen:
            seen.add(h.lower())
            uni.append(h)
    return uni


def _click_private_and_create(page) -> None:
    """Écran 2 : choisir Privé puis Créer (reconnaît FR/EN)."""
    for label in ("Privé", "Private"):
        try:
            r = page.get_by_text(label, exact=True).first
            if r.count() > 0:
                r.click()
                log(f"visibilité : {label}")
                break
        except Exception:  # noqa: BLE001
            continue
    for label in ("Créer", "Create"):
        try:
            b = page.get_by_role("button", name=label).first
            if b.count() > 0:
                b.click()
                log(f"bouton : {label}")
                return
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("bouton Créer introuvable")


def create_list(page) -> str:
    page.goto("https://x.com/i/lists/create",
              wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3500)
    page.fill('input[name="name"]', LIST_NAME)
    page.wait_for_timeout(600)
    nxt = page.get_by_role("button", name=re.compile("Suivant|Next")).first
    nxt.click()
    page.wait_for_timeout(2000)
    _click_private_and_create(page)
    for _ in range(20):
        page.wait_for_timeout(1000)
        m = re.search(r"/i/lists/(\d+)", page.url)
        if m:
            log(f"liste créée : {m.group(1)}")
            return m.group(1)
    raise RuntimeError(f"pas d'URL de liste après création : {page.url}")


ADD_JS = """
async ([handle, listId]) => {
  const ct0 = (document.cookie.split('; ').find(c => c.startsWith('ct0=')) || '').split('=')[1];
  const r = await fetch('/i/api/1.1/lists/members/create.json', {
    method: 'POST', credentials: 'include',
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'x-csrf-token': ct0,
      'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
    },
    body: 'list_id=' + listId + '&screen_name=' + encodeURIComponent(handle),
  });
  return r.status;
}
"""


def add_member(page, handle: str, list_id: str) -> int:
    """Ajoute via l'API web v1.1 avec la session loguée (0 si rate-limit 403/429)."""
    return int(page.evaluate(ADD_JS, [handle, list_id]))


def main() -> int:
    from patchright.sync_api import sync_playwright

    handles = watchlist_handles()
    log(f"watchlist : {len(handles)} comptes")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        list_id = ID_FILE.read_text().strip() if ID_FILE.exists() else ""
        if not list_id:
            list_id = create_list(page)
            ID_FILE.write_text(list_id)
        page.goto("https://x.com/home", wait_until="domcontentloaded",
                  timeout=30000)
        page.wait_for_timeout(2500)

        ok = fail = 0
        for h in handles:
            try:
                status = add_member(page, h, list_id)
                if status == 200:
                    ok += 1
                    log(f"  + @{h}")
                else:
                    fail += 1
                    log(f"  ! @{h} : HTTP {status}")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                log(f"  ! @{h} : {str(exc)[:60]}")
            time.sleep(0.8)
        log(f"terminé : {ok} ajoutés, {fail} échecs")
        ctx.close()
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
