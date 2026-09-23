#!/usr/bin/env python3
"""Registre X — recolte headless des profils de la watchlist (playwright).

Contrairement a l'extraction via la session ZCode, ce script est autonome :
il fait tourner Chromium avec un profil persistant (data/x_browser_profile/)
dans lequel l'utilisateur se connecte UNE fois. Les runs suivants sont
headless et silencieux.

Contrainte connue (docs/14-registre-x.md) : X soft-throttle la navigation
rapide. Ce harvester donc :
  - peu de profils par run, pause aleatoire de 18-32 s entre chaque ;
  - detection de rebond (URL verifiee deux fois) -> profil saute ;
  - 2 rebonds consecutifs -> abort propre (respecter le throttle, pas le
    forcer).

    python scripts/x_harvest.py --login          # UNE fois : fenetre visible, se connecter
    python scripts/x_harvest.py --profiles thatdevlr,lookonchain
    python scripts/x_harvest.py --status         # le profil a-t-il une session valide ?

Sortie : data/x_harvest/registre-<ts>.json (compatible --ingest-json).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "data" / "x_browser_profile"
OUT_DIR = ROOT / "data" / "x_harvest"

PAUSE_RANGE_S = (18, 32)
LOGIN_TIMEOUT_S = 15 * 60


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_METRIC_WORDS = {
    "replies": "replies", "réponses": "replies",
    "reposts": "reposts",
    "likes": "likes", "j'aime": "likes", "j’aime": "likes",
    "bookmarks": "bookmarks", "signets": "bookmarks",
    "views": "views", "vues": "views",
}


def _parse_metrics(label: str | None) -> dict:
    """'13 réponses, 16 reposts, 322 J'aime, 12107 vues' -> dict bilingue FR/EN."""
    out: dict[str, int] = {}
    if not label:
        return out
    for part in label.split(","):
        m = re.match(r"\s*([\d\u202f\s.,]+)\s*(.+?)\s*$", part)
        if not m:
            continue
        key = _METRIC_WORDS.get(m.group(2).strip().lower())
        if key:
            out[key] = int(re.sub(r"[^\d]", "", m.group(1)) or 0)
    return out


def extract_articles(page) -> list[dict]:
    """Extraction DOM : faits reels, pas de parsing d'etiquettes."""
    posts: list[dict] = []
    for art in page.locator("article[data-testid='tweet']").all():
        try:
            href = art.locator("a[href*='/status/']").first.get_attribute(
                "href", timeout=2000
            )
        except Exception:
            href = None
        if not href:
            continue
        m = re.search(r"^/([^/]+)/status/(\d+)", href)
        if not m:
            continue
        handle, post_id = m.group(1), m.group(2)
        try:
            dt = art.locator("time").first.get_attribute("datetime", timeout=1500)
        except Exception:
            dt = None
        try:
            txt = art.locator("[data-testid='tweetText']").first.inner_text(
                timeout=1500
            )
        except Exception:
            txt = ""
        try:
            group_label = art.locator("[role='group']").first.get_attribute(
                "aria-label", timeout=1000
            )
        except Exception:
            group_label = None
        posts.append({
            "post_id": post_id,
            "author_handle": handle,
            "status_url": f"https://x.com/{handle}/status/{post_id}",
            "posted_at_iso": dt,
            "text": txt.strip(),
            "metrics": _parse_metrics(group_label),
            "source": "headless_profile",
        })
    return posts


def goto_profile(page, handle: str) -> bool:
    """Navigue vers le profil et verifie la stabilite (anti-rebond)."""
    page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2600)
    u1 = page.url
    page.wait_for_timeout(1500)
    u2 = page.url
    return f"/{handle}" in u1 and f"/{handle}" in u2


def harvest_profiles(handles: list[str], scrolls: int) -> int:
    from patchright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("[harvest] aucun profil navigateur. Lance d'abord : --login", file=sys.stderr)
        return 1
    out_posts: list[dict] = []
    consecutive_bounces = 0
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for handle in handles:
            if not goto_profile(page, handle):
                consecutive_bounces += 1
                print(f"[harvest] @{handle} : rebond (throttle ?) — saute")
                if consecutive_bounces >= 2:
                    print("[harvest] 2 rebonds consecutifs : abort, on respecte le throttle")
                    break
                continue
            consecutive_bounces = 0
            for _ in range(scrolls):
                page.mouse.wheel(0, 1600)
                page.wait_for_timeout(1100)
            posts = extract_articles(page)
            print(f"[harvest] @{handle} : {len(posts)} posts")
            out_posts.extend(posts)
            if handle != handles[-1]:
                time.sleep(random.uniform(*PAUSE_RANGE_S))
        ctx.close()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = _now_utc().replace(":", "").replace("-", "")
    out = OUT_DIR / f"registre-{ts}.json"
    out.write_text(
        json.dumps({"posts": out_posts}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    # chemin fixe pour l'ingestion automatique (timer nocturne)
    (OUT_DIR / "latest.json").write_text(
        json.dumps({"posts": out_posts}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"[harvest] total {len(out_posts)} posts -> {out}")
    return 0


def extract_profile_meta(page, handle: str) -> dict:
    """En-tête du profil : portée (followers/following), bio, date d'adhésion."""
    meta = {"handle": handle, "followers": None, "following": None,
            "bio": None, "joined": None}
    for key, suffix in (("followers", "verified_followers"), ("following", "following")):
        try:
            el = page.locator(f"a[href$='/{suffix}']").first
            txt = (el.inner_text(timeout=2000).strip() or "").split()
            meta[key] = txt[0] if txt else None
        except Exception:  # noqa: BLE001
            pass
    try:
        el = page.locator("[data-testid='UserDescription']").first
        meta["bio"] = el.inner_text(timeout=2000).strip() or None
    except Exception:  # noqa: BLE001
        pass
    try:
        body = page.evaluate("document.body.innerText") or ""
        m = re.search(r"(?:Joined|A rejoint)\s+([^\n]+)", body)
        if m:
            meta["joined"] = m.group(1).strip()
        for key, label in (("followers", "Followers"), ("following", "Following")):
            if meta[key] is None:
                m2 = re.search(r"([\d.,]+[KMB]?)\s+" + label, body)
                if m2:
                    meta[key] = m2.group(1)
    except Exception:  # noqa: BLE001
        pass
    return meta


def _db():
    import sqlite3
    return sqlite3.connect(ROOT / "data" / "warehouse" / "x_posts.db")


def top_registry_handles(n: int = 15) -> list[str]:
    """Les comptes les plus actifs du registre — la portée X se mesure là
    où il y a déjà du signal."""
    con = _db()
    rows = con.execute(
        "SELECT author_handle, COUNT(*) c FROM x_posts "
        "GROUP BY author_handle ORDER BY c DESC LIMIT ?", (n,)).fetchall()
    con.close()
    return [r[0] for r in rows if r[0]]


def harvest_meta(handles: list[str]) -> int:
    """Portée X des comptes suivis — un call de @x avec 500K followers
    ne pèse pas comme un call à 800."""
    from patchright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("[harvest] aucun profil navigateur. Lance d'abord : --login", file=sys.stderr)
        return 1
    out: list[dict] = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for handle in handles:
            if not goto_profile(page, handle):
                print(f"[meta] @{handle} : rebond — saute", file=sys.stderr)
                continue
            meta = extract_profile_meta(page, handle)
            out.append(meta)
            print(f"[meta] @{handle}: {meta['followers']} followers", file=sys.stderr)
            if handle != handles[-1]:
                time.sleep(random.uniform(*PAUSE_RANGE_S))
        ctx.close()
    import sqlite3
    con = _db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS x_profiles (
        handle TEXT PRIMARY KEY, followers TEXT, following TEXT,
        bio TEXT, joined TEXT, captured_at REAL NOT NULL);
    """)
    now = time.time()
    for m in out:
        con.execute("INSERT OR REPLACE INTO x_profiles VALUES (?,?,?,?,?,?)",
                    (m["handle"], m["followers"], m["following"],
                     m["bio"], m["joined"], now))
    con.commit()
    con.close()
    print(f"[meta] {len(out)} profils -> x_posts.db:x_profiles", file=sys.stderr)
    return 0


def harvest_replies(urls: list[str], scrolls: int) -> int:
    """Réponses sous des statuts : on ouvre la conversation et on extrait
    les articles (les réponses sont des tweets, extract_articles les voit)."""
    from patchright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("[harvest] aucun profil navigateur. Lance d'abord : --login", file=sys.stderr)
        return 1
    out_posts: list[dict] = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for url in urls:
            m = re.search(r"/status/(\d+)", url)
            root_id = m.group(1) if m else None
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)
                for _ in range(scrolls):
                    page.mouse.wheel(0, 1600)
                    page.wait_for_timeout(1100)
                posts = [p0 for p0 in extract_articles(page)
                         if p0["post_id"] != root_id]
                print(f"[replies] {url.rsplit('/', 1)[-1]} : {len(posts)} réponses",
                      file=sys.stderr)
                out_posts.extend(posts)
            except Exception as exc:  # noqa: BLE001 — un statut mort ne bloque pas
                print(f"[replies] échec {url}: {str(exc)[:60]}", file=sys.stderr)
            time.sleep(random.uniform(*PAUSE_RANGE_S))
        ctx.close()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = _now_utc().replace(":", "").replace("-", "")
    (OUT_DIR / f"registre-{ts}.json").write_text(
        json.dumps({"posts": out_posts}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "latest-replies.json").write_text(
        json.dumps({"posts": out_posts}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[replies] total {len(out_posts)} -> latest-replies.json", file=sys.stderr)
    return 0


def harvest_trends() -> int:
    """Tendances mondiales X — un ticker qui trende AVANT d'être dans notre
    univers est l'alpha le plus tôt qui existe. -> x_posts.db:x_trends
    /explore est vide en headless : repli sur le rail « Tendances » du home."""
    from patchright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("[harvest] aucun profil navigateur. Lance d'abord : --login", file=sys.stderr)
        return 1
    trends: list[dict] = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://x.com/explore/tabs/trending",
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        trends = page.evaluate("""
        () => {
          const out = [];
          document.querySelectorAll('[data-testid="trend"]').forEach(t => {
            const lines = (t.innerText || "").split("\\n").map(s => s.trim())
              .filter(Boolean);
            const k = lines.findIndex(l => /\\d[\\d.,]*\\s*posts?$/i.test(l));
            if (k >= 1) out.push({ name: lines[k - 1], count: lines[k],
                                   category: lines[0] || null });
          });
          return out;
        }""") or []
        if not trends:
            page.goto("https://x.com/home", wait_until="domcontentloaded",
                      timeout=30000)
            page.wait_for_timeout(5000)
            body = page.evaluate("document.body.innerText") or ""
            i = max(body.find("Tendances"), body.find("What's happening"))
            if i >= 0:
                j_end = min([x for x in (body.find("Suggestions", i),
                                         body.find("Voir plus", i),
                                         body.find("Show more", i),
                                         i + 1500) if x > 0])
                zone = body[i:j_end]
                lines = [l.strip() for l in zone.split("\n") if l.strip()]
                skip = re.compile(r"· (Tendances|Trending)|^(Tendances|What's happening|Voir plus|Show more|Suivre|Follow)$|@|^Tendance dans|^Trending in", re.I)
                count = re.compile(r"^(?:[\d.,]+\s*[kKmM]?\s*)?posts$", re.I)
                last_name = None
                for l in lines[1:]:
                    if skip.search(l):
                        continue
                    if count.match(l):
                        if last_name:
                            for t in trends:
                                if t["name"] == last_name and not t.get("count"):
                                    t["count"] = l
                            last_name = None
                        continue
                    if l.startswith("#") or l.startswith("$") or len(l) <= 40:
                        trends.append({"name": l, "count": None, "category": None})
                        last_name = l
        ctx.close()
    import sqlite3
    con = sqlite3.connect(ROOT / "data" / "warehouse" / "x_posts.db")
    con.execute("""CREATE TABLE IF NOT EXISTS x_trends (
        name TEXT NOT NULL, count TEXT, category TEXT,
        captured_at REAL NOT NULL, PRIMARY KEY (name, captured_at))""")
    now = time.time()
    for t in trends:
        con.execute("INSERT OR IGNORE INTO x_trends VALUES (?,?,?,?)",
                    (t["name"], t.get("count"), t.get("category"), now))
    con.commit()
    con.close()
    # signal fort : une tendance qui matche notre univers de tickers
    universe = set()
    try:
        from scripts.x_aster_pulse import _universe
        universe = {u.upper() for u in _universe()}
    except Exception:  # noqa: BLE001
        pass
    hits = [t for t in trends if t["name"].upper().lstrip("$#") in universe]
    print(f"[trends] {len(trends)} tendances", file=sys.stderr)
    for t in trends[:10]:
        print(f"[trends]   {t['name']}" + (f" — {t['count']}" if t.get("count") else ""),
              file=sys.stderr)
    for t in hits:
        print(f"[trends] *** {t['name']} TRENDING — dans notre univers", file=sys.stderr)
    return 0


def goto_search(page, query: str) -> bool:
    """Navigue vers une recherche live et verifie la stabilite (anti-rebond)."""
    from urllib.parse import quote

    url = f"https://x.com/search?q={quote(query)}&src=typed_query&f=live"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2600)
    u1 = page.url
    page.wait_for_timeout(1500)
    u2 = page.url
    return "/search" in u1 and "/search" in u2


def harvest_searches(queries: list[str], scrolls: int) -> int:
    """Peche aux calls : les recherches live regorgent de $CASHTAG + direction.

    Les pages /search rebondissent plus vite que les profils (throttle) —
    d'ou le meme abort apres 2 rebonds consecutifs.
    """
    from playwright.sync_api import sync_playwright

    if not PROFILE_DIR.exists():
        print("[harvest] aucun profil navigateur. Lance d'abord : --login", file=sys.stderr)
        return 1
    out_posts: list[dict] = []
    consecutive_bounces = 0
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for query in queries:
            if not goto_search(page, query):
                consecutive_bounces += 1
                print(f"[harvest] recherche {query!r} : rebond — saute")
                if consecutive_bounces >= 2:
                    print("[harvest] 2 rebonds consecutifs : abort")
                    break
                continue
            consecutive_bounces = 0
            for _ in range(scrolls):
                page.mouse.wheel(0, 1600)
                page.wait_for_timeout(1100)
            posts = extract_articles(page)
            posts = [dict(item, search_query=query) for item in posts]
            print(f"[harvest] {query!r} : {len(posts)} posts")
            out_posts.extend(posts)
            if query != queries[-1]:
                time.sleep(random.uniform(*PAUSE_RANGE_S))
        ctx.close()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = _now_utc().replace(":", "").replace("-", "")
    out = OUT_DIR / f"registre-search-{ts}.json"
    out.write_text(
        json.dumps({"posts": out_posts}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (OUT_DIR / "latest-searches.json").write_text(
        json.dumps({"posts": out_posts}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"[harvest] total {len(out_posts)} posts -> {out}")
    return 0


def run_login() -> int:
    from patchright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE_DIR), headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded")
        # déjà connecté (session existante) : X redirige vers /home avec le fil
        page.wait_for_timeout(3000)
        deadline = time.time() + LOGIN_TIMEOUT_S
        print("[login] fenetre ouverte — connecte-toi (accepte la banniere cookies"
              " si elle apparait). Detection auto de la reussite…", flush=True)
        while time.time() < deadline:
            try:
                if page.locator("article[data-testid='tweet']").count() > 0:
                    print("[login] session X valide — profil sauvegarde. Fermeture.",
                          flush=True)
                    time.sleep(2)
                    ctx.close()
                    return 0
            except Exception:
                pass
            time.sleep(3)
        print("[login] timeout : pas de session detectee en 15 min", file=sys.stderr)
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
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        ok = page.locator("article[data-testid='tweet']").count() > 0
        ctx.close()
    print(f"[status] session X : {'VALIDE' if ok else 'EXPIREE/ABSENTE — relance --login'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Recolte headless des profils X (registre)")
    ap.add_argument("--login", action="store_true", help="connexion manuelle unique (fenetre visible)")
    ap.add_argument("--profiles", metavar="H1,H2", help="handles a recolter (sans @)")
    ap.add_argument("--searches", metavar='"Q1,Q2"', help="recherches live a pecher (sans virgule dans une query)")
    ap.add_argument("--scrolls", type=int, default=1, help="scrolls par profil (1 scroll ≈ 4-6 posts)")
    ap.add_argument("--status", action="store_true", help="verifie la session du profil")
    ap.add_argument("--meta", metavar="AUTO|H1,H2",
                    help="portee X des profils (followers/bio) -> x_profiles")
    ap.add_argument("--replies", metavar="U1,U2",
                    help="reponses sous des statuts (URLs completees)")
    ap.add_argument("--trends", action="store_true",
                    help="tendances mondiales X -> x_trends (radar de narratif)")
    args = ap.parse_args()
    if args.login:
        return run_login()
    if args.status:
        return check_status()
    if args.meta:
        if args.meta == "AUTO" or args.meta.isdigit():
            handles = top_registry_handles(int(args.meta) if args.meta.isdigit() else 15)
        else:
            handles = [h.strip().lstrip("@") for h in args.meta.split(",") if h.strip()]
        return harvest_meta(handles)
    if args.replies:
        urls = [u.strip() for u in args.replies.split(",") if u.strip()]
        return harvest_replies(urls, args.scrolls)
    if args.trends:
        return harvest_trends()
    if args.profiles:
        handles = [h.strip().lstrip("@") for h in args.profiles.split(",") if h.strip()]
        return harvest_profiles(handles, args.scrolls)
    if args.searches:
        queries = [q.strip() for q in args.searches.split(",") if q.strip()]
        return harvest_searches(queries, args.scrolls)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
