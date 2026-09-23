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
                "mined": seen, "attempts": attempt}
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
