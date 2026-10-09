#!/usr/bin/env python3
"""Le harvester du leaderboard fomo — le TOP 100 des traders, toutes périodes.

Le problème qu'il règle : nos 8 « top traders » = codés en dur depuis la
capture manuelle du user. Le leaderboard = la vérité du site (le rang, le
PnL, le nombre de trades) et il BOUGE. Ce script :
  1. navigue /leaderboard, clique ALL, parse le top-100 (podium inclus),
  2. le stocke dans dom_leaderboard (fomo_swaps.db),
  3. régénère top_handles dans ws_config.json = les N meilleurs par PnL
     → le daemon les épinglera à sa prochaine reconnexion (≤ 1 h).

Le rythme : 1×/h (le timer fomo-leaderboard.timer).
"""
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
DB = ROOT / "data" / "fomo" / "fomo_swaps.db"
CONFIG = ROOT / "data" / "fomo" / "ws_config.json"
LOCK = ROOT / "data" / "fomo" / ".leaderboard.lock"
TOP_N = 20  # l'élite épinglée/déflaggée (le top-100 = stocké intégralement)


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def knum(s):
    """'1,234.5' => 1234.5 ; '1.2K'/'1.2M'/'1.2B' => échelle appliquée.

    R9 : l'UI fomo abrège les gros PnL (K/M/B) — sans échelle, une valeur
    abrégée ne matchait plus le motif de rang (rang entier perdu, chaîne
    monotone cassée)."""
    if not s:
        return None
    s = s.strip().replace(",", "")
    m = re.fullmatch(r"([+-]?[\d.]+)([KMB]?)", s, re.IGNORECASE)
    if not m:
        return None
    v = float(m.group(1))
    mult = {"k": 1e3, "m": 1e6, "b": 1e9}.get((m.group(2) or "").lower(), 1.0)
    return v * mult


# le bloc leaderboard : [rang.] nom @handle + $PnL N+
# FIX R9 : [KMB]? — l'UI abrège les gros PnL, un rang abrégé était perdu
LB_RE = re.compile(
    r"(?=(?:^|\n)(\d+)\.\n([^\n@]+)\n@([\w\-]+)\n\+\n\$([\d,]+(?:\.\d+)?[KMB]?)\n(\d+)\+\n)")
# le podium : nom @handle + $PnL N+ (sans rang devant)
POD_RE = re.compile(
    r"(?=(?:^|\n)([^\n@\.]+)\n@([\w\-]+)\n\+\n\$([\d,]+(?:\.\d+)?[KMB]?)\n(\d+)\+\n)")


def parse_leaderboard_text(text):
    """Le top-100 all-time, désambiguïsé : la page contient le classement 24H
    ET le classement ALL (deux podiums + deux listes numérotées mélangées
    dans le texte). L'ALL = la sous-suite monotone PnL-décroissante des rangs
    4→100 qui démarre au PnL global max, + le podium 1-3 au-dessus."""
    numbered = []  # (rank, pnl, name, handle, trades)
    for rank, name, handle, pnl, trades in LB_RE.findall(text):
        numbered.append((int(rank), knum(pnl), name.strip(), handle, int(trades)))
    if not numbered:
        return []
    numbered.sort(key=lambda r: (r[0], -(r[1] or 0)))
    # la liste ALL : le rang 4 = le PnL max global, puis desc monotone TOLÉRANTE
    # (les rangs désordonnés/incohérents = sautés, la chaîne ne casse pas)
    all_rows, prev_r, prev_p = [], 3, float("inf")
    for rank, pnl, name, handle, trades in numbered:
        if pnl is None:
            continue
        if rank == prev_r + 1 and pnl <= prev_p:
            all_rows.append((rank, pnl, name, handle, trades))
            prev_r, prev_p = rank, pnl
        elif rank > prev_r + 1 and pnl <= prev_p:
            # le rang sauté (un trader sorti entre la capture et le parse) :
            # on le prend quand même si le PnL reste dans la descendance
            all_rows.append((rank, pnl, name, handle, trades))
            prev_r, prev_p = rank, pnl
    if not all_rows:
        return []
    floor = all_rows[0][1]  # le PnL du rang 4
    # le podium all-time : les non-numérotés au PnL > le rang 4
    known = {h for _, _, _, h, _ in all_rows}
    podium = []
    for name, handle, pnl, trades in POD_RE.findall(text):
        p = knum(pnl)
        if handle not in known and p is not None and p > floor:
            podium.append((p, name.strip(), handle, int(trades)))
    podium.sort(reverse=True)
    rows = [(i, p, name, handle, trades)
            for i, (p, name, handle, trades) in enumerate(podium[:3], start=1)]
    rows += all_rows
    return [(r, name, handle, p, tr) for r, p, name, handle, tr in rows]


def main():
    import fcntl
    lk = open(LOCK, "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("déjà en cours — stop")
        return 0

    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    page = None
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=8000)
        ctx = browser.contexts[0] if browser.contexts else browser
        page = ctx.new_page()  # la page dédiée, fermée en fin de passe
        page.goto("https://fomo.family/leaderboard", wait_until="domcontentloaded",
                  timeout=30000)
        time.sleep(5)
        # l'onglet ALL (le classement all-time)
        try:
            for b in page.query_selector_all("button, [role='tab'], div[role='tab']"):
                if (b.inner_text() or "").strip() == "ALL":
                    b.click()
                    time.sleep(3)
                    break
        except Exception:
            pass
        text = page.evaluate("() => document.body.innerText")
        rows = parse_leaderboard_text(text)
        log(f"leaderboard parse : {len(rows)} traders")
        if len(rows) < 10:
            # FIX R9 : ABORT sans écriture — le DELETE intégral ci-dessous +
            # la régénération de top_handles écrasaient l'élite avec les 3
            # handles d'un parse partiel (onglet périodique capturé, format
            # changé). L'ancien snapshot reste en base, l'élite est gardée.
            log(f"ABORT : {len(rows)} lignes seulement (< 10) — le format a "
                f"pu changer : rien n'est écrit, l'élite précédente est gardée")
            return 1

        now = int(time.time())
        con = sqlite3.connect(DB, timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("DELETE FROM dom_leaderboard")  # le snapshot = remplacement intégral
        for rank, name, handle, pnl, trades in rows:
            con.execute("INSERT OR REPLACE INTO dom_leaderboard VALUES (?,?,?,?,?,?)",
                        (rank, name, handle, pnl, trades, now))
        con.commit()
        con.close()

        # la génération dynamique de l'élite : les TOP_N par PnL all-time
        top = [h for _, _, h, _, _ in sorted(rows, key=lambda r: r[3] or 0, reverse=True)[:TOP_N]]
        cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
        old = set(cfg.get("top_handles", []))
        cfg["top_handles"] = top
        cfg["top_handles_updated_at"] = now
        CONFIG.write_text(json.dumps(cfg, indent=1))
        log(f"top_handles régénéré : {len(top)} traders "
            f"(entrées : {sorted(set(top) - old)}, sorties : {sorted(old - set(top))})")
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
