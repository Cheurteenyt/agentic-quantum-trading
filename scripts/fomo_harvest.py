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
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "fomo_browser_profile"
BASE = "https://fomo.family"
LOGIN_TIMEOUT_S = 900
CDP_PORT = 9222


def _ctx_of(browser):
    """CDP Browser -> .contexts[0] ; persistent context -> lui-même."""
    ctxs = getattr(browser, "contexts", None)
    if ctxs:
        return ctxs[0]
    return browser


def _connect_cdp():
    """Se connecte au navigateur daemon (headed, session persistée) s'il tourne."""
    from patchright.sync_api import sync_playwright

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}", timeout=5000)
        return pw, browser
    except Exception:
        pw.stop()
        return None, None

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


def _open_page(page, url: str, initial_wait: int = 3000) -> None:
    """Goto + résilience « Couldn't load your account » (réinit Privy après
    redémarrage du navigateur) : Try again / reload jusqu'à 4 fois."""
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    for _ in range(4):
        page.wait_for_timeout(initial_wait)
        body = page.evaluate("document.body.innerText") or ""
        if "Couldn" not in body:
            return
        try:
            btn = page.locator("button:has-text('Try again')")
            if btn.count() > 0:
                btn.first.click()
            else:
                page.reload(wait_until="domcontentloaded")
        except Exception:
            page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(4000)


EXTRACT_SOCIAL_JS = """
() => {
  // Bandeau social du profil : "N Mutuals / N Following / X Followers" +
  // bio via la ligne "Follow @handle on x // bio"
  const body = document.body.innerText || "";
  const lines = body.split("\\n").map(l => l.trim());
  const grabCount = (label) => {
    const i = lines.indexOf(label);
    if (i >= 1 && /^[\\d.,]+[KMB]?$/.test(lines[i - 1] || "")) return lines[i - 1];
    const j = lines.findIndex(l =>
      new RegExp("^([\\d.,]+[KMB]?) " + label + "$").test(l));
    if (j >= 0) return lines[j].split(" ")[0];
    return null;
  };
  let bio = null, x_ref = null;
  const mX = body.match(/Follow @(\\w+) on x ?(?:\\/\\/ ?([\\s\\S]{0,220}))?/);
  if (mX) { x_ref = mX[1]; bio = (mX[2] || "").split("\\n")[0].slice(0, 220) || null; }
  return { followers: grabCount("Followers"), following: grabCount("Following"),
           mutuals: grabCount("Mutuals"), x_ref, bio };
}
"""


def mine_positions(handle: str, scrolls: int = 10) -> dict:
    """Positions d'un trader — via le navigateur daemon (CDP) si présent,
    sinon headed éphémère (session persistée)."""
    pw = browser = ctx = None
    via = "cdp"
    pw, browser = _connect_cdp()
    if browser is None:
        from patchright.sync_api import sync_playwright

        _require_profile()
        via = "headed éphémère"
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False,
            args=["--window-position=0,0", "--window-size=1280,800"])
        browser = ctx
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else \
            ctx.new_page()
        seen: dict = {}
        declared = None
        # 2 passes max : la 1re peut tomber avant l'init Privy (profils à 0
        # après un restart du daemon) — on réessaie seulement si suspect.
        for attempt in (1, 2):
            _open_page(page, f"{BASE}/profile/{handle}",
                       initial_wait=3000 if attempt == 1 else 6000)
            seen = {}
            for _ in range(scrolls):
                for ticker, v in (page.evaluate(EXTRACT_POSITIONS_JS) or {}).items():
                    seen.setdefault(ticker, v)
                page.evaluate("window.scrollBy(0, 700)")
                page.wait_for_timeout(500)
            declared = page.evaluate(
                "() => { const m = (document.body.innerText||'').match(/Positions\\s*(\\d+)/);"
                " return m ? parseInt(m[1]) : null; }"
            )
            if attempt == 2:
                break
            if declared is not None and declared == 0:
                break  # profil réellement vide
            if declared is not None and len(seen) >= declared:
                break  # compte déclaré atteint : minage fiable
            if declared is not None:
                scrolls = min(scrolls + declared // 5, scrolls + 20)
            print(f"[mine] {handle}: {len(seen)}/{declared} positions — 2e passe",
                  file=sys.stderr, flush=True)
        return {"handle": handle, "via": via, "declared_positions": declared,
                "mined": seen, "attempts": attempt,
                "social": page.evaluate(EXTRACT_SOCIAL_JS) or {}}
    finally:
        if ctx is not None:
            ctx.close()
        else:
            pw.stop()


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


EXTRACT_TOKEN_PANEL_JS = """
() => {
  const body = document.body.innerText || "";
  const grab = (re) => { const m = body.match(re); return m ? m[1] : null; };
  const num = (s) => s ? parseFloat(s.replace(/,/g, "")) : null;
  // ——— panneau FLUX token : "3,166 buys / 2,857 sells" ———
  const buys = num(grab(/([\\d,]+) buys/));
  const sells = num(grab(/([\\d,]+) sells/));
  // volumes : deux lignes "$X vol." — buy puis sell (ordre du DOM)
  const vols = [...document.querySelectorAll("div")].map(d => d.innerText || "")
    .filter(t => /^\\$[\\d.,]+[KkMm]? vol\\.$/.test(t.trim()))
    .map(t => t.trim());
  // ——— panneau POSITION (?tradeId=) — séquence normalisée du corps ———
  // "$7.2M + $3.5M 10.9M PONS ▲ 96.53% Avg. entry $156.7M MC Invested $3.7M
  //  Transactions (255)" — chaque libellé est sur sa propre ligne dans le DOM.
  const nbody = body.replace(/\\s+/g, " ");
  let txs = null, posValue = null, posQty = null, posUnit = null;
  let pnlPct = null, posDir = null, avgEntryMc = null, invested = null;
  const loc = nbody.indexOf("Avg. entry");
  if (loc >= 0) {
    const win = nbody.slice(Math.max(0, loc - 220), loc + 200);
    const pm = win.match(/\\$([\\d.,]+)\\s*\\+\\s*\\$[\\d.,]+\\s+([\\d.,]+[KkMm]?) ([A-Z0-9]+)/);
    if (pm) { posValue = num(pm[1]); posQty = pm[2]; posUnit = pm[3]; }
    const pp = win.match(/([▲▼])\\s+([\\d.,]+)%/);
    if (pp) { posDir = pp[1]; pnlPct = num(pp[2]); }
    avgEntryMc = (win.match(/Avg\\. entry\\s*\\$([\\d.,]+[KMB]?)\\s*MC/) || [])[1] || null;
    invested = num((win.match(/Invested\\s*\\$([\\d.,]+)/) || [])[1]);
    txs = num((win.match(/Transactions \\(([\\d,]+)\\)/) || [])[1]);
  }
  if (txs === null) txs = num(grab(/Transactions \\(([\\d,]+)\\)/));
  // thèses : "auteur / Thesis / heure / texte..." — une heure relative est
  // exigée pour exclure la case à cocher "Thesis" de la charte
  const lines = body.split("\\n").map(l => l.trim());
  const theses = [];
  for (let i = 1; i < lines.length - 2; i++) {
    if (lines[i] !== "Thesis") continue;
    const author = lines[i - 1], when = lines[i + 1];
    if (!/^(\\d+[hmd]|now)/.test(when || "")) continue;
    const after = lines.slice(i + 2, i + 10);
    const stop = after.findIndex(l => /^♡/.test(l) || /^\\d+$/.test(l) || l === "Thesis");
    const raw = (stop >= 0 ? after.slice(0, stop) : after.slice(0, 4)).join(" ");
    const text = raw.slice(0, 220);
    if (text && !theses.some(t0 => t0.text === text))
      theses.push({ author, when, text });
  }
  // stats token (carte info : Volume 24hr / Holders / Top 10 / Contract)
  let vol24 = null, holders = null, top10 = null, contract = null;
  for (const d of document.querySelectorAll("div")) {
    const t = (d.innerText || "").trim();
    if (t.includes("Top 10 holding") && t.length < 300) {
      vol24 = (t.match(/Volume 24hr\\n\\$?([\\d.,]+[KkMm]?)/) || [])[1] || null;
      holders = (t.match(/Holders\\n([\\d.,]+[KkMm]?)/) || [])[1] || null;
      top10 = (t.match(/Top 10 holding\\n([\\d.]+%)/) || [])[1] || null;
      contract = (t.match(/(0x[a-fA-F0-9]{6,})/) || [])[1] || null;
      break;
    }
  }
  const mc = grab(/\\$([\\d.,]+[KMB]?) MC/);
  // liens sociaux hors footer (le footer pointe x.com/fomo)
  let xHandle = null, searchOnX = null, website = null;
  for (const a of document.querySelectorAll("a[href*='x.com'], a[href*='twitter.com']")) {
    const href = a.getAttribute("href") || "";
    if (href.includes("/search?")) { searchOnX = href; continue; }
    if (/twitter\\.com\\/fomo|x\\.com\\/fomo$/.test(href)) continue;
    const m = href.match(/(?:x|twitter)\\.com\\/([A-Za-z0-9_]+)/);
    if (m && m[1].toLowerCase() !== "fomo") xHandle = m[1];
  }
  for (const a of document.querySelectorAll("a")) {
    const t = (a.innerText || "");
    if (/website/i.test(t)) website = a.getAttribute("href");
  }
  const tickerEl = [...document.querySelectorAll("button")].find(b =>
    /^Buy /.test((b.innerText || "").trim()));
  let panel_kind = null;
  if (buys !== null) panel_kind = "token";
  else if (avgEntryMc !== null || txs !== null) panel_kind = "position";
  return {
    panel_kind,
    buys, sells,
    buy_vol: vols[0] || null, sell_vol: vols[1] || null,
    buyers: num(grab(/([\\d,]+) buyers/)),
    sellers: num(grab(/([\\d,]+) sellers/)),
    pos_value: posValue, pos_qty: posQty, pos_unit: posUnit,
    pnl_pct: pnlPct, pos_dir: posDir,
    avg_entry_mc: avgEntryMc, invested, txs,
    theses: theses.slice(0, 8),
    vol_24h: vol24, holders, top_10_holding: top10, contract, mc,
    x_handle: xHandle, search_on_x: searchOnX, website,
    tradable_ticker: tickerEl ? tickerEl.innerText.trim().replace("Buy ", "") : null,
  };
}
"""


def mine_token_panel(handle: str, ticker: str, scrolls: int = 4) -> dict:
    """Ouvre le profil d'un tenant, clique sa position `ticker`, extrait le
    panneau token (flux d'ordres, socials, metadata) via CDP/headed."""
    pw = browser = ctx = None
    pw, browser = _connect_cdp()
    if browser is None:
        from patchright.sync_api import sync_playwright

        _require_profile()
        pw = sync_playwright().start()
        ctx = pw.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False,
            args=["--window-position=0,0", "--window-size=1280,800"])
        browser = ctx
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else \
            ctx.new_page()
        pattern = re.compile(rf"{re.escape(ticker)}\s+[\d.,]+[KkMm]?\s+{re.escape(ticker)}")
        intel: dict = {}
        opened = clicked = False
        # machine à états : profil propre -> clic position -> PREUVE d'ouverture
        # (panel_kind renseigné : flux token OU position ?tradeId) sinon retour
        # à un état propre, 3 fois max.
        for attempt in (1, 2, 3):
            _open_page(page, f"{BASE}/profile/{handle}",
                       initial_wait=3000 if attempt == 1 else 5000)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(800)
            clicked = False
            for _ in range(scrolls + 3):
                for b in page.locator("button").all():
                    txt = b.inner_text() or ""
                    if pattern.search(txt.replace("\n", " ")):
                        clicked = True
                        b.click()  # le clic centre ouvre le panneau position (?tradeId=)
                        break
                if clicked:
                    break
                page.evaluate("window.scrollBy(0, 650)")
                page.wait_for_timeout(500)
            if not clicked:
                continue
            # le panneau est ouvert seulement si l'extracteur identifie son type
            for _ in range(12):
                page.wait_for_timeout(1000)
                probe = page.evaluate(EXTRACT_TOKEN_PANEL_JS)
                if probe.get("panel_kind"):
                    intel = probe
                    opened = True
                    break
            if opened:
                break
        if clicked and not opened:
            intel["debug_body"] = (page.evaluate("document.body.innerText") or "")[:500].replace("\n", " | ")
            intel["debug_url"] = page.url
            try:
                page.screenshot(path="/tmp/panel_debug.png")
            except Exception:  # noqa: BLE001 — le diagnostic ne doit pas masquer l'échec
                pass
        return {"ticker": ticker, "via_holder": handle, "panel_opened": opened, **intel}
    finally:
        if ctx is not None:
            ctx.close()
        else:
            pw.stop()


def _persist_token_intel(ticker: str, intel: dict) -> None:
    """Entrepôt cumulatif des panneaux (flux, position, thèses, stats token)
    — le diff entre captures = le signal frais."""
    if not intel.get("panel_opened"):
        return
    import sqlite3
    db = ROOT / "data" / "fomo" / "fomo.db"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_token_intel (
        ticker TEXT NOT NULL, panel_kind TEXT, holder TEXT,
        buys INTEGER, sells INTEGER, buy_vol TEXT, sell_vol TEXT,
        buyers INTEGER, sellers INTEGER,
        pos_value REAL, pos_qty TEXT, pos_unit TEXT, pnl_pct REAL,
        pos_dir TEXT, avg_entry_mc TEXT, invested REAL, txs INTEGER,
        vol_24h TEXT, holders TEXT, top_10_holding TEXT,
        contract TEXT, mc TEXT, x_handle TEXT,
        theses_json TEXT, captured_at REAL NOT NULL,
        PRIMARY KEY (ticker, holder, captured_at));
    """)
    con.execute("INSERT OR IGNORE INTO fomo_token_intel VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (ticker, intel.get("panel_kind"), intel.get("via_holder"),
                 intel.get("buys"), intel.get("sells"), intel.get("buy_vol"),
                 intel.get("sell_vol"), intel.get("buyers"), intel.get("sellers"),
                 intel.get("pos_value"), intel.get("pos_qty"), intel.get("pos_unit"),
                 intel.get("pnl_pct"), intel.get("pos_dir"), intel.get("avg_entry_mc"),
                 intel.get("invested"), intel.get("txs"), intel.get("vol_24h"),
                 intel.get("holders"), intel.get("top_10_holding"),
                 intel.get("contract"), intel.get("mc"), intel.get("x_handle"),
                 json.dumps(intel.get("theses") or [], ensure_ascii=False),
                 time.time()))
    con.commit()
    con.close()


def _open_tokens_panel(page, tab: str = "trending") -> bool:
    """Ouvre le panneau Tokens (bouton du shell app, pas de route /tokens)
    et sélectionne l'onglet. Retourne True si le clic d'onglet a réussi."""
    _open_page(page, f"{BASE}/leaderboard", initial_wait=4000)
    try:
        page.get_by_text("Tokens", exact=True).first.click()
        page.wait_for_timeout(3000)
    except Exception:  # noqa: BLE001 — on minera la vue par défaut
        pass
    labels = {"trending": "Trending", "most_held": "Most held",
              "graduated": "Graduated", "bonding": "Bonding", "new": "New"}
    clicked = False
    if tab in labels:
        try:
            page.get_by_text(labels[tab], exact=True).first.click()
            clicked = True
            page.wait_for_timeout(2500)
        except Exception:  # noqa: BLE001
            pass
    return clicked


def mine_tokens(tab: str = "trending", scrolls: int = 8, debug: bool = False) -> dict:
    """Panneau Tokens : découverte des coins (trending / most held /
    graduated / bonding) — la couche amont de listing_watcher : un coin qui
    monte ici peut lister sur Aster demain."""
    pw, browser = _connect_cdp()
    if browser is None:
        raise RuntimeError("daemon CDP requis pour --tokens")
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        tab_clicked = _open_tokens_panel(page, tab)
        for _ in range(scrolls):
            page.evaluate("window.scrollBy(0, 700)")
            page.wait_for_timeout(400)
        rows = page.evaluate(EXTRACT_TOKENS_JS) or []
        out = {"tab": tab, "tab_clicked": tab_clicked, "rows": rows, "n": len(rows)}
        if debug or not rows:
            out["debug_body"] = (page.evaluate("document.body.innerText") or "")[:3500]
            out["debug_url"] = page.url
        return out
    finally:
        pw.stop()


def mine_token_flow(ticker: str, tab: str = "trending", steps: int = 14) -> dict:
    """Panneau FLUX d'un token : sidebar Tokens -> scroll de LA SIDEBAR (son
    propre conteneur, la page ne bouge pas) -> clic sur la ligne du ticker ->
    flux d'ordres global + thèses de tous les traders du coin."""
    pw, browser = _connect_cdp()
    if browser is None:
        raise RuntimeError("daemon CDP requis pour --flow")
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open_tokens_panel(page, tab)
        # la sidebar virtualise : scroller SON conteneur jusqu'à trouver le ticker
        scroll_sidebar = """
        () => {
          for (const e of document.querySelectorAll("div")) {
            if (e.scrollHeight > e.clientHeight + 100 && e.clientHeight > 150
                && e.clientWidth < 420 && /MC/.test(e.innerText || "")) {
              e.scrollTop += 450;
              return true;
            }
          }
          return false;
        }"""
        clicked = False
        for _ in range(steps):
            loc = page.get_by_text(ticker, exact=True)
            try:
                if loc.count() > 0:
                    loc.first.click()
                    clicked = True
                    break
            except Exception:  # noqa: BLE001 — élément détaché, on rescrolle
                pass
            page.evaluate(scroll_sidebar)
            page.wait_for_timeout(400)
        if not clicked:
            return {"ticker": ticker, "via_tab": tab, "panel_opened": False,
                    "note": "ticker introuvable dans la sidebar"}
        # preuve d'ouverture : le flux d'ordres est extrait
        for _ in range(12):
            page.wait_for_timeout(1000)
            probe = page.evaluate(EXTRACT_TOKEN_PANEL_JS)
            if probe.get("panel_kind") == "token":
                return {"ticker": ticker, "via_tab": tab,
                        "panel_opened": True, **probe}
        return {"ticker": ticker, "via_tab": tab, "panel_opened": False,
                "debug_url": page.url,
                "debug_body": (page.evaluate("document.body.innerText") or "")[:400]}
    finally:
        pw.stop()


EXTRACT_TOKENS_JS = """
() => {
  // Trois formats de lignes dans le panneau Tokens :
  //  trending/most_held : TICKER $prix $MC [MC] "MC" ▲|▼ pct%
  //  bonding            : TICKER âge $vol "Vol" $mc "MC" pct%   (pct = courbe)
  //  graduated          : TICKER âge $vol "Vol" $mc [MC] "MC" ▲|▼ pct%
  const lines = (document.body.innerText || "").split("\\n").map(l => l.trim());
  const STOP = new Set(["Alerts","Tokens","Leaderboard","Feed","Watchlist",
    "Crypto","Trending","Most held","Graduated","Bonding","cash","Deposit more",
    "MC","Vol","New","Clans","View all","Your rank","PnL"]);
  const isMoney = (s) => /^\\$[\\d.,]+[KMB]?$/.test(s);
  const isAge = (s) => /^\\d+(m|h|d|w|mo|y)$/.test(s);
  const rows = [];
  const seen = new Set();
  for (let i = 0; i < lines.length - 4; i++) {
    const t = lines[i];
    if (!/^[A-Za-z0-9$][A-Za-z0-9$.]{1,13}$/.test(t) || STOP.has(t)) continue;
    if (isMoney(t) || isAge(t)) continue;
    if (seen.has(t)) continue;
    // — format trending : le prix suit directement —
    if (isMoney(lines[i + 1] || "")) {
      let k = -1;
      for (let j = i + 2; j < Math.min(i + 6, lines.length); j++) {
        if (lines[j] === "MC" || /^\\$[\\d.,]+[KMB]? MC$/.test(lines[j])) { k = j; break; }
      }
      if (k < 0) continue;
      let mc = null;
      for (let j = k - 1; j > i + 1; j--) {
        if (isMoney(lines[j])) { mc = lines[j].slice(1); break; }
      }
      if (mc === null) {
        const one = (lines[k] || "").match(/^\\$([\\d.,]+[KMB]?) MC$/);
        if (one) mc = one[1];
      }
      let dir = null, chg = null;
      for (let q = k + 1; q < Math.min(k + 3, lines.length); q++) {
        if (lines[q] === "▲" || lines[q] === "▼") {
          dir = lines[q];
          const pct = (lines[q + 1] || "").match(/^([\\d.,]+)%$/);
          if (pct) chg = pct[1];
          break;
        }
      }
      if (mc === null || chg === null) continue;
      seen.add(t);
      rows.push({ ticker: t, mc, price: lines[i + 1].slice(1), dir, change_pct: chg });
      continue;
    }
    // — formats bonding / graduated : l'âge suit —
    if (!isAge(lines[i + 1] || "")) continue;
    let vol = null, mc = null, dir = null, pctAfter = null;
    let stage = 0;  // 0: avant Vol, 1: entre Vol et MC, 2: après MC
    for (let j = i + 2; j < Math.min(i + 10, lines.length); j++) {
      const l = lines[j];
      let m;
      if (l === "Vol") { stage = 1; continue; }
      if ((m = l.match(/^\\$([\\d.,]+[KMB]?) Vol$/))) { vol = m[1]; stage = 1; continue; }
      if (l === "MC") { stage = 2; continue; }
      if ((m = l.match(/^\\$([\\d.,]+[KMB]?) MC$/))) {
        if (stage <= 1) mc = m[1];
        stage = 2; continue;
      }
      if (isMoney(l)) {
        if (stage === 0) vol = l.slice(1);
        else if (stage === 1) mc = l.slice(1);
        continue;
      }
      if (stage === 2 && (l === "▲" || l === "▼")) { dir = l; continue; }
      const pct = l.match(/^([\\d.,]+)%$/);
      if (pct && stage === 2) { pctAfter = pct[1]; break; }
    }
    if (vol === null || mc === null) continue;
    seen.add(t);
    const row = { ticker: t, mc, vol, age: lines[i + 1] };
    if (dir) { row.dir = dir; row.change_pct = pctAfter; }
    else { row.bonding_pct = pctAfter; }
    rows.push(row);
  }
  return rows;
}
"""


def _persist_tokens(tab: str, rows: list) -> None:
    """Entrepôt cumulatif des couches découverte (bonding/graduated/trending)
    — un ticker absent de la capture précédente = une nouveauté à surveiller."""
    import sqlite3
    db = ROOT / "data" / "fomo" / "fomo.db"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_new_coins (
        ticker TEXT NOT NULL, tab TEXT NOT NULL,
        mc TEXT, price TEXT, vol TEXT, age TEXT, dir TEXT,
        change_pct TEXT, bonding_pct TEXT, captured_at REAL NOT NULL,
        PRIMARY KEY (ticker, tab, captured_at));
    """)
    now = time.time()
    for r in rows:
        con.execute("INSERT OR IGNORE INTO fomo_new_coins VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (r.get("ticker"), tab, r.get("mc"), r.get("price"), r.get("vol"),
                     r.get("age"), r.get("dir"), r.get("change_pct"),
                     r.get("bonding_pct"), now))
    con.commit()
    con.close()


PROBE_CLICKS = {
    # nom -> (URL de départ, [textes à cliquer en séquence], attente finale ms)
    "clans": (f"{BASE}/leaderboard", ["Clans"], 3000),
    "clans_all": (f"{BASE}/leaderboard", ["View all"], 3500),
    "alerts": (f"{BASE}/leaderboard", ["Alerts"], 3000),
    "alerts_filter": (f"{BASE}/leaderboard", ["Alerts", "$1K"], 2500),
    "closed": (f"{BASE}/profile/ogle", ["Closed"], 3500),
    "feed": (f"{BASE}/leaderboard", ["Feed"], 3000),
    "followers": (f"{BASE}/profile/ogle", ["Followers"], 3000),
    "clan_tech": (f"{BASE}/leaderboard", ["View all", "Tech Dungeon"], 3500),
    "clan_members": (f"{BASE}/clans/47e167b6-14e0-449b-806b-c8476afcc724", [], 3000),
}


def probe(name: str) -> dict:
    """Sonde visuelle : ouvre une surface (clics de texte en séquence),
    capture écran + corps — pour cartographier avant d'écrire un mineur."""
    if name not in PROBE_CLICKS:
        return {"error": f"sonde inconnue: {name} ({list(PROBE_CLICKS)})"}
    url, texts, wait = PROBE_CLICKS[name]
    pw, browser = _connect_cdp()
    if browser is None:
        raise RuntimeError("daemon CDP requis")
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open_page(page, url, initial_wait=4000)
        clicked = []
        for text in texts:
            try:
                page.get_by_text(text, exact=True).first.click()
                clicked.append(text)
                page.wait_for_timeout(2500)
            except Exception:  # noqa: BLE001 — le dump dira où on en est
                pass
        page.wait_for_timeout(max(0, wait - 2500 * len(clicked)))
        shot = f"/tmp/probe_{name}.png"
        try:
            page.screenshot(path=shot)
        except Exception:  # noqa: BLE001
            shot = None
        return {"probe": name, "clicked": clicked, "url": page.url,
                "screenshot": shot,
                "body": (page.evaluate("document.body.innerText") or "")[:2500]}
    finally:
        pw.stop()


EXTRACT_ALERTS_JS = """
() => {
  // Flux Alerts : "handle / Buy|Sell|Thesis / âge / corps" répétés.
  // Le corps arrive ÉCLATÉ sur plusieurs lignes (ticker, $X, at, $Y, MC) —
  // on collecte tout puis on reparse chaque événement.
  const isMoney = (s) => /^\\$[\\d.,]+[KMB]?$/.test(s);
  const isAge = (s) => /^\\d+(m|h|d|w|mo|y)$/.test(s);
  const lines = (document.body.innerText || "").split("\\n").map(l => l.trim());
  const events = [];
  let cur = null;
  const flush = () => {
    if (cur && cur.handle && cur.badge) {
      // reparse du corps éclaté
      const r = cur.text;
      for (let i = 0; i < r.length; i++) {
        if (r[i] === "at" && isMoney(r[i - 1] || "") && isMoney(r[i + 1] || "")
            && r[i + 2] === "MC") {
          cur.amount = r[i - 1].slice(1);
          cur.entry_mc = r[i + 1].slice(1);
          cur.ticker = r.slice(0, i - 1).reverse().find(x =>
            x && x !== "?" && !isMoney(x) && !isAge(x) && !/^[▲▼]$/.test(x)) || null;
        }
        const pos = r[i].match(/^\\$([\\d.,]+[KMB]?) \\(([+-]?[\\d.,]+)%\\)$/);
        if (pos) { cur.pos_value = pos[1]; cur.pos_pct = pos[2]; }
        if (/^♡ ?[\\d,]+$/.test(r[i])) cur.likes = r[i].replace(/\\D/g, "");
      }
      cur.text = cur.text.filter(x => x !== "at" && x !== "MC" && !isMoney(x)
        && !/^\\?/.test(x));
      events.push(cur);
    }
    cur = null;
  };
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    const badge = l === "Buy" || l === "Sell" || l === "Thesis" ? l : null;
    if (badge && i >= 1 && isAge(lines[i + 1] || "")) {
      flush();
      cur = { handle: lines[i - 1], badge, age: lines[i + 1], text: [],
              ticker: null, amount: null, entry_mc: null, pos_value: null,
              pos_pct: null, likes: null, links: [] };
      i += 1;  // sauter l'âge
      continue;
    }
    if (cur) {
      if (/^x\\.com\\//.test(l) || /^https:\\/\\/x\\.com\\//.test(l)) {
        cur.links.push(l);
        continue;
      }
      if (l && cur.text.length < 14) cur.text.push(l.slice(0, 140));
    }
  }
  flush();
  return events;
}
"""


def mine_alerts(steps: int = 10) -> dict:
    """Flux Alerts (sidebar) : événements Buy/Sell/Thesis des traders avec
    MC d'entrée — le temps réel de fomo. Scroll de la sidebar elle-même."""
    pw, browser = _connect_cdp()
    if browser is None:
        raise RuntimeError("daemon CDP requis pour --alerts")
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open_page(page, f"{BASE}/leaderboard", initial_wait=4000)
        try:
            page.get_by_text("Alerts", exact=True).first.click()
            page.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001 — la vue par défaut peut suffire
            pass
        scroll_sidebar = """
        () => {
          for (const e of document.querySelectorAll("div")) {
            if (e.scrollHeight > e.clientHeight + 100 && e.clientHeight > 150
                && e.clientWidth < 420) {
              e.scrollTop += 500;
              return true;
            }
          }
          return false;
        }"""
        seen: dict = {}
        for _ in range(steps):
            for ev in page.evaluate(EXTRACT_ALERTS_JS) or []:
                key = (ev.get("handle"), ev.get("badge"), ev.get("age"),
                       ev.get("ticker") or (ev.get("text") or [""])[0])
                if key not in seen:
                    seen[key] = ev
            page.evaluate(scroll_sidebar)
            page.wait_for_timeout(400)
        return {"events": list(seen.values()), "n": len(seen)}
    finally:
        pw.stop()


def _persist_events(events: list) -> None:
    """Entrepôt du flux Alerts — les événements frais (Buy/Sell/Thesis avec
    MC d'entrée) = le signal temps réel, diff entre captures."""
    import sqlite3
    db = ROOT / "data" / "fomo" / "fomo.db"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_events (
        handle TEXT NOT NULL, badge TEXT NOT NULL, age TEXT,
        ticker TEXT, amount TEXT, entry_mc TEXT,
        pos_value TEXT, pos_pct TEXT, likes TEXT,
        text TEXT, links TEXT, captured_at REAL NOT NULL,
        PRIMARY KEY (handle, badge, age, ticker, captured_at));
    """)
    now = time.time()
    import json as _json
    for ev in events:
        con.execute("INSERT OR IGNORE INTO fomo_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (ev.get("handle"), ev.get("badge"), ev.get("age"),
                     ev.get("ticker"), ev.get("amount"), ev.get("entry_mc"),
                     ev.get("pos_value"), ev.get("pos_pct"), ev.get("likes"),
                     " ".join(ev.get("text") or [])[:300] or None,
                     _json.dumps(ev.get("links") or []), now))
    con.commit()
    con.close()


EXTRACT_CLOSED_JS = """
() => {
  // Positions Closed : "TICKER / $X invested • âge / +|− / $Y / ▲|▼ / %"
  const lines = (document.body.innerText || "").split("\\n").map(l => l.trim());
  const isMoney = (s) => /^\\$[\\d.,]+[KMB]?$/.test(s);
  const STOP = new Set(["Positions","Top trades","Open","Closed","Token","PnL",
    "Total cash","invested"]);
  const rows = [];
  const seen = new Set();
  for (let i = 0; i < lines.length - 4; i++) {
    const t = lines[i];
    if (!t || isMoney(t) || STOP.has(t) || /^\\d+(m|h|d|w|mo|y)$/.test(t)) continue;
    const inv = (lines[i + 1] || "")
      .match(/^\\$([\\d.,]+[KMB]?) invested(?: • (\\d+[a-z]{1,2}))?$/);
    if (!inv) continue;
    if (seen.has(t)) continue;
    let pnl = null, dir = null, pct = null, sign = null;
    for (let j = i + 2; j < Math.min(i + 8, lines.length); j++) {
      const l = lines[j];
      if (l === "+" || l === "−" || l === "-") { sign = l === "+" ? "+" : "-"; continue; }
      if (pnl === null && isMoney(l)) { pnl = l.slice(1); continue; }
      if (l === "▲" || l === "▼") { dir = l; continue; }
      const m = l.match(/^([\\d.,]+)%$/);
      if (m && dir) { pct = m[1]; break; }
    }
    if (pnl === null || pct === null) continue;
    seen.add(t);
    rows.push({ ticker: t, invested: inv[1], pnl: (sign || "") + pnl,
                dir, pct, age: inv[2] || null });
  }
  return rows;
}
"""


def mine_closed(handle: str, steps: int = 8) -> dict:
    """Positions Closed d'un trader : historique RÉALISÉ (PnL par trade
    clôturé) — la compétence prouvée du baleine, pour pondérer son signal."""
    pw, browser = _connect_cdp()
    if browser is None:
        raise RuntimeError("daemon CDP requis pour --closed")
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open_page(page, f"{BASE}/profile/{handle}", initial_wait=4000)
        try:
            page.get_by_text("Closed", exact=True).first.click()
            page.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001 — pas de section Closed = 0 trades
            return {"handle": handle, "closed": [], "n": 0, "cash": None}
        cash = None
        seen: dict = {}
        for _ in range(steps):
            body = page.evaluate("document.body.innerText") or ""
            if cash is None:
                m = re.search(r"Total cash\n\$([\d.,]+)", body)
                cash = m.group(1) if m else None
            for row in page.evaluate(EXTRACT_CLOSED_JS) or []:
                seen.setdefault(row["ticker"], row)
            page.evaluate("window.scrollBy(0, 700)")
            page.wait_for_timeout(400)
        return {"handle": handle, "closed": list(seen.values()), "n": len(seen),
                "cash": cash,
                "debug_body": (page.evaluate("document.body.innerText") or "")[:2000]}
    finally:
        pw.stop()


def _persist_closed(handle: str, rows: list, cash: str | None) -> None:
    """Historique réalisé par baleine — base du win rate qui pondère le radar."""
    import sqlite3
    db = ROOT / "data" / "fomo" / "fomo.db"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_closed (
        handle TEXT NOT NULL, ticker TEXT NOT NULL,
        invested TEXT, pnl TEXT, dir TEXT, pct TEXT, age TEXT,
        captured_at REAL NOT NULL,
        PRIMARY KEY (handle, ticker, age, captured_at));
    """)
    now = time.time()
    for r in rows:
        con.execute("INSERT OR IGNORE INTO fomo_closed VALUES (?,?,?,?,?,?,?,?)",
                    (handle, r.get("ticker"), r.get("invested"), r.get("pnl"),
                     r.get("dir"), r.get("pct"), r.get("age"), now))
    con.commit()
    con.close()


EXTRACT_CLANS_JS = """
() => {
  // Liste des clans : "NOM / N members / +$PnL" + hrefs /clans/<uuid>
  const lines = (document.body.innerText || "").split("\\n").map(l => l.trim());
  const rows = [];
  for (let i = 0; i < lines.length - 2; i++) {
    const m = (lines[i + 1] || "").match(/^(\\d+) members?$/);
    if (!m) continue;
    const name = lines[i];
    if (!name || name === "Clans" || /^\\d+$/.test(name)) continue;
    const pnl = (lines[i + 2] || "").match(/^\\+\\$([\\d.,]+[KMB]?)$/);
    rows.push({ name, members: parseInt(m[1]),
                pnl: pnl ? pnl[1] : null });
  }
  // uuid de chaque clan via les liens
  for (const a of document.querySelectorAll("a[href*='/clans/']")) {
    const href = a.getAttribute("href") || "";
    const id = (href.match(/\\/clans\\/([0-9a-f-]{20,})/) || [])[1];
    if (!id) continue;
    const txt = (a.innerText || "").split("\\n")[0].trim();
    for (const r of rows) if (r.name === txt && !r.uuid) r.uuid = id;
  }
  return rows;
}
"""

EXTRACT_CLAN_PAGE_JS = """
() => {
  // Page clan : profit + holdings combinés + MEMBRES "Nom @handle +/- $X"
  const body = document.body.innerText || "";
  const lines = body.split("\\n").map(l => l.trim());
  const out = { holdings: [], members: [], n_members: null, trades: null, profit: null };
  const mMem = body.match(/(\\d+) members/);
  if (mMem) out.n_members = parseInt(mMem[1]);
  const mTr = body.match(/([\\d.,]+[KMB]?) trades/);
  if (mTr) out.trades = mTr[1];
  const mPr = body.match(/\\+\\$([\\d.,]+[KMB]?) past/);
  if (mPr) out.profit = mPr[1];
  // zone holdings : après "Clan holdings" jusqu'à "Members"
  const i0 = body.indexOf("Clan holdings");
  const i1 = body.indexOf("Members", i0 + 5);
  const zone = (i0 >= 0 ? lines.slice(
    body.slice(0, i0).split("\\n").length,
    i1 >= 0 ? body.slice(0, i1).split("\\n").length : lines.length) : []);
  for (let i = 0; i < zone.length - 1; i++) {
    const t = zone[i];
    if (!/^[A-Za-z0-9$][A-Za-z0-9$.]{1,15}$/.test(t) || t === "Token") continue;
    const v = zone[i + 1].match(/^\\$([\\d.,]+[KMB]?)$/);
    if (!v) continue;
    const p = (zone[i + 2] || "").match(/^([+-]\\$[\\d.,]+[KMB]?)$/);
    out.holdings.push({ ticker: t, value: v[1], pnl: p ? p[1] : null });
    i += p ? 2 : 1;
  }
  // membres : "@handle (-- | +/- $X)" combiné OU éclaté sur 2-3 lignes
  for (let i = 1; i < lines.length; i++) {
    let handle = null, name = null, pnl = null, done = false, j = i;
    let m = lines[i].match(/^@(\\w+) (?:(--)|([+-]) \\$([\\d.,]+[KMB]?))$/);
    if (m) {
      handle = m[1]; name = lines[i - 1];
      if (!m[2]) pnl = m[3] + m[4];
      done = true;
    } else if ((m = lines[i].match(/^@(\\w+)$/))) {
      handle = m[1]; name = lines[i - 1]; j = i + 1;
      for (let k = j; k < Math.min(j + 3, lines.length) && !done; k++) {
        if (lines[k] === "--") { done = true; break; }
        if (lines[k] === "+" || lines[k] === "-") {
          const mv = (lines[k + 1] || "").match(/^\\$([\\d.,]+[KMB]?)$/);
          if (mv) pnl = lines[k] + mv[1];
          done = true;
          break;
        }
        const mm = lines[k].match(/^([+-]) \\$([\\d.,]+[KMB]?)$/);
        if (mm) { pnl = mm[1] + mm[2]; done = true; break; }
      }
    }
    if (handle && done && !out.members.some(x => x.handle === handle))
      out.members.push({ handle, name, pnl });
  }
  return out;
}
"""


def mine_clans(top: int = 6) -> dict:
    """Clans fomo : liste complète + page de chaque clan (holdings combinés
    par token) — la conviction COLLECTIVE, au-dessus des baleines seules."""
    pw, browser = _connect_cdp()
    if browser is None:
        raise RuntimeError("daemon CDP requis pour --clans")
    try:
        ctx = _ctx_of(browser)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        _open_page(page, f"{BASE}/leaderboard", initial_wait=4000)
        try:
            page.get_by_text("View all", exact=True).first.click()
            page.wait_for_timeout(3000)
        except Exception:  # noqa: BLE001
            pass
        clans = page.evaluate(EXTRACT_CLANS_JS) or []
        for c in clans[:top]:
            if not c.get("uuid"):
                continue
            try:
                _open_page(page, f"{BASE}/clans/{c['uuid']}", initial_wait=3500)
                # la liste des holdings virtualise : scroller et fusionner
                merged: dict = {}
                merged_m: dict = {}
                for _ in range(7):
                    d = page.evaluate(EXTRACT_CLAN_PAGE_JS) or {}
                    for h in d.get("holdings") or []:
                        merged.setdefault(h["ticker"], h)
                    for m in d.get("members") or []:
                        merged_m.setdefault(m["handle"], m)
                    c["detail"] = {"n_members": d.get("n_members"),
                                   "trades": d.get("trades"),
                                   "profit": d.get("profit"),
                                   "holdings": list(merged.values()),
                                   "members": list(merged_m.values())}
                    page.evaluate("window.scrollBy(0, 800)")
                    page.wait_for_timeout(350)
            except Exception:  # noqa: BLE001 — un clan en échec ne bloque pas
                c["detail"] = None
        return {"clans": clans, "n": len(clans)}
    finally:
        pw.stop()


def _persist_clans(clans: list) -> None:
    """Conviction COLLECTIVE : clans (PnL combiné) + holdings par token."""
    import sqlite3
    db = ROOT / "data" / "fomo" / "fomo.db"
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_clans (
        name TEXT NOT NULL, uuid TEXT, members INTEGER, pnl TEXT,
        profit TEXT, trades TEXT, captured_at REAL NOT NULL,
        PRIMARY KEY (name, captured_at));
    CREATE TABLE IF NOT EXISTS fomo_clan_holdings (
        clan TEXT NOT NULL, ticker TEXT NOT NULL, value TEXT, pnl TEXT,
        captured_at REAL NOT NULL,
        PRIMARY KEY (clan, ticker, captured_at));
    CREATE TABLE IF NOT EXISTS fomo_clan_members (
        clan TEXT NOT NULL, handle TEXT NOT NULL, name TEXT, pnl TEXT,
        captured_at REAL NOT NULL,
        PRIMARY KEY (clan, handle, captured_at));
    """)
    now = time.time()
    for c in clans:
        d = c.get("detail") or {}
        con.execute("INSERT OR IGNORE INTO fomo_clans VALUES (?,?,?,?,?,?,?)",
                    (c.get("name"), c.get("uuid"), d.get("n_members", c.get("members")),
                     c.get("pnl"), d.get("profit"), d.get("trades"), now))
        for h in d.get("holdings") or []:
            con.execute("INSERT OR IGNORE INTO fomo_clan_holdings VALUES (?,?,?,?,?)",
                        (c.get("name"), h.get("ticker"), h.get("value"),
                         h.get("pnl"), now))
        for m in d.get("members") or []:
            con.execute("INSERT OR IGNORE INTO fomo_clan_members VALUES (?,?,?,?,?)",
                        (c.get("name"), m.get("handle"), m.get("name"),
                         m.get("pnl"), now))
            # le membre devient un handle connu (radar futur), PnL à miner
            con.execute("INSERT OR IGNORE INTO fomo_traders (handle, first_seen, last_seen) "
                        "VALUES (?, ?, ?)", (m.get("handle"), now, now))
    con.commit()
    con.close()


def run_daemon() -> int:
    """Chromium headed lancé DIRECTEMENT (port CDP natif, pas de pipe) —
    UNE fenêtre à minimiser ; tous les minages se connectent via CDP."""
    import subprocess
    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        exe = p.chromium.executable_path
    proc = subprocess.Popen(
        [exe, f"--user-data-dir={PROFILE_DIR}",
         f"--remote-debugging-port={CDP_PORT}",
         "--no-first-run", "--no-default-browser-check",
         "--window-position=60,60", "--window-size=1280,800",
         "--class=fomo-whale", "--wayland-app-id=fomo-whale",
         f"{BASE}/leaderboard"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"[daemon] chromium direct prêt sur CDP :{CDP_PORT} (pid {proc.pid})"
          " — minimise la fenêtre, elle reste branchée.", flush=True)
    try:
        while proc.poll() is None:
            time.sleep(30)
        print("[daemon] navigateur fermé", flush=True)
        return 0
    except KeyboardInterrupt:
        proc.terminate()
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Harvester fomo.family headless")
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--daemon", action="store_true",
                    help="navigateur headed persistant + CDP (minimiser une fois)")
    ap.add_argument("--positions", metavar="HANDLE")
    ap.add_argument("--token", metavar="TICKER,HOLDER",
                    help="panneau token : via la position d'un tenant")
    ap.add_argument("--leaderboard", action="store_true")
    ap.add_argument("--tokens", metavar="TAB", nargs="?", const="trending",
                    help="panneau découverte (trending|most_held|graduated|bonding)")
    ap.add_argument("--flow", metavar="TICKER[,TAB]",
                    help="panneau flux d'un token (buys/sells + thèses de tous)")
    ap.add_argument("--probe", metavar="NAME",
                    help=f"sonde visuelle d'une surface: {','.join(PROBE_CLICKS)}")
    ap.add_argument("--alerts", action="store_true",
                    help="flux Alerts (Buy/Sell/Thesis avec MC d'entrée)")
    ap.add_argument("--clans", metavar="TOP", nargs="?", const="6",
                    help="clans : liste + holdings combinés par token")
    ap.add_argument("--closed", metavar="H1,H2",
                    help="positions Closed (historique réalisé -> win rate)")
    args = ap.parse_args()
    if args.login:
        return run_login()
    if args.status:
        return check_status()
    if args.daemon:
        return run_daemon()
    if args.positions:
        print(json.dumps(mine_positions(args.positions), indent=1, ensure_ascii=False))
        return 0
    if args.token:
        ticker, holder = args.token.split(",", 1)
        intel = mine_token_panel(holder.strip(), ticker.strip())
        _persist_token_intel(ticker.strip(), intel)
        print(json.dumps(intel, indent=1, ensure_ascii=False))
        return 0
    if args.leaderboard:
        print(json.dumps(mine_leaderboard(["24h", "7d", "30d"]), indent=1, ensure_ascii=False))
        return 0
    if args.tokens:
        res = mine_tokens(args.tokens, debug=True)
        _persist_tokens(args.tokens, res["rows"])
        print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0
    if args.probe:
        print(json.dumps(probe(args.probe), indent=1, ensure_ascii=False))
        return 0
    if args.clans:
        res = mine_clans(top=int(args.clans))
        _persist_clans(res["clans"])
        print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0
    if args.closed:
        outs = []
        for h in [x.strip() for x in args.closed.split(",") if x.strip()]:
            res = mine_closed(h)
            _persist_closed(h, res["closed"], res.get("cash"))
            wins = sum(1 for r in res["closed"] if r.get("dir") == "▲")
            n = res["n"]
            wr = f"{wins}/{n} = {wins * 100 // n}%" if n else "0 trade"
            print(f"{h}: {wr} closed | cash ${res.get('cash')}", file=sys.stderr)
            outs.append(res)
        print(json.dumps(outs, indent=1, ensure_ascii=False))
        return 0
    if args.alerts:
        res = mine_alerts()
        _persist_events(res["events"])
        print(json.dumps(res, indent=1, ensure_ascii=False))
        return 0
    if args.flow:
        parts = args.flow.split(",", 1)
        print(json.dumps(mine_token_flow(parts[0].strip(),
                                         parts[1].strip() if len(parts) > 1 else "trending"),
                         indent=1, ensure_ascii=False))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
