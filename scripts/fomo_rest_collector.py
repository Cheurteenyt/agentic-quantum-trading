#!/usr/bin/env python3
"""LE COLLECTEUR REST FOMO (29/09, v2 « toute la carte ») — la sonde RE
(scripts/studies/fomo_rest_probe.py puis fomo_rest_map.md) a prouvé que TOUTES
les surfaces des onglets (holders, thèses, swaps élite, trades fermés,
leaderboard 24h/all-time, clans, trending, verified, feed d'activité, profils,
About/launchpad, pré-graduation) sont des endpoints REST de prod-api.fomo.family,
et que le WAF (Cloudflare) ne bloque que le fingerprint TLS : curl_cffi
impersonate chrome131 + Bearer JWT = 200 partout. Le collector devient LA
collecte, le DOM (fomo_dom_worker) le fallback. Base DÉDIÉE data/fomo/fomo_rest.db
(un seul écrivain — la leçon du lock du 29/09), JWT partagé (ws_jwt_cache.txt +
jwt_cache.json, fallback CDP). Pacing 1,0 s : passe ~60 appels ≈ 1,5-2,5 min,
timer 30 min.
STRUCTURE DÉCLARATIVE : COLLECTES = liste (nom, cadence_en_passes, fonction)
exécutée dans l'ordre (leaderboard→trending fournissent elite/mints au ctx).
La fraîcheur est lue dans fomo_rest_snapshots (captured_at par endpoint+entité) :
un snapshot plus récent que `cadence` passes (×30 min, marge 0,9) → skip.
Cadence 1 = à chaque passe (comportement historique inchangé).
PAGINATION (preuves fomo_rest_cursor_probe.py) : swaps = &lastSwapId, trades =
&lastTradeId, curseurs persistés (endpoint='cursor_<kind>_<uid>'), backfill
BORNÉ par passe (SWAPS_PAGES/TRADES_PAGES) et INCRÉMENTAL, flux épuisé → cycle
neuf. INSERT OR IGNORE = idempotent par swap id.
NOUVEAUTÉS v2 (formes validées par fomo_rest_collector_probe.py) :
- /proxy/verifiedTokens → liste brute (tri par `holders` À LA LECTURE) ;
- /v2/leaderboard?window=alltime&limit=100 → {leaderboard:[100×dict27]} ;
- /feed/tradingActivity?limit=50&threshold=1000 → {items, hasNextPage}, items
  portent tokenAddress/userId/tradeId/body — et `&tokenAddress=<mint>` FILTRE
  (validé) → itération par token possible à l'itération suivante ;
- profils élite : /v2/users/<uid> (+balances,/leaderboard) et
  /v2/userTokens/aggregatedSnapshotById?userId=<uid>&snapshotId=1 — SANS
  snapshotId = 400 ; réponse observée dégénérée {snapshotId,pnl,equity}, à creuser ;
- /proxy/filterTokens avec body = TABLEAU ["mint:networkId",…] (BATCH 12 mints
  en 1 appel) → token{address,totalSupply…,info}, createdAt, holders, activity,
  launchpad{launchpadName,graduationPercent} (null si déjà gradué) ;
- bonding : les 12 mints les plus récents de fomo.db fomo_pre_graduated
  (lecture mode=ro, JAMAIS d'écriture) → filterTokens → snapshot par mint."""
import json, os, time, sys, sqlite3
from pathlib import Path
from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[1]
JWT_CACHE = ROOT / "data" / "fomo" / "ws_jwt_cache.txt"
FOMO_DB = ROOT / "data" / "fomo" / "fomo.db"          # lecture seule (mode=ro)
DB = ROOT / "data" / "fomo" / "fomo_rest.db"          # LA base du collector
BASE = "https://prod-api.fomo.family"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
NETWORK_ID = 1399811149  # solana
PACING = 1.0
PASS_SECONDS = 30 * 60   # cadence du timer systemd
N_TOKENS = 12
N_ELITE = 5
N_PROFILES = 4           # uids profilés par passe (des 5 élite en rotation)
SWAPS_PAGES = max(1, int(os.environ.get("FOMO_SWAPS_PAGES", "5")))
TRADES_PAGES = max(1, int(os.environ.get("FOMO_TRADES_PAGES", "3")))
PROFILE_KINDS = (  # (endpoint de snapshot, chemin GET) — {uid} formaté
    ("user", "/v2/users/{uid}"),
    ("balances", "/v2/users/{uid}/balances"),
    ("leaderboard", "/v2/users/{uid}/leaderboard"),
    ("aggregated", "/v2/userTokens/aggregatedSnapshotById?userId={uid}&snapshotId=1"),
)


def jwt_exp(jwt: str) -> float:
    import base64
    try:
        p = jwt.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p)).get("exp", 0)
    except Exception:
        return 0


def read_jwt() -> str | None:
    """Le plus frais des 2 caches : ws_jwt_cache.txt (le daemon WS) et
    jwt_cache.json (le top-up mobula) — même token privy pour les deux."""
    best, best_exp = None, 0
    for p in (JWT_CACHE, ROOT / "data" / "fomo" / "jwt_cache.json"):
        try:
            raw = p.read_text().strip()
            jwt = (json.loads(raw).get("jwt") or json.loads(raw).get("token")
                   if raw.startswith("{") else raw.strip('"'))
            e = jwt_exp(jwt) if jwt else 0
            if e > best_exp:
                best, best_exp = jwt, e
        except Exception:
            continue
    return best if best_exp > time.time() + 600 else None


def refresh_jwt_via_cdp() -> str | None:
    """Le fallback de dernière main : la source de vérité = le localStorage
    du navigateur (privy:token, re-minté par le site lui-même) — le même
    mécanisme que le ws_daemon. On écrit le cache, ce qui sert aussi le
    daemon. Jamais de re-auth forcée : si les navigateurs sont down, None."""
    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        for port in ("9223", "9222"):
            try:
                lg = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=8000)
            except Exception:
                continue
            cx = lg.contexts[0] if lg.contexts else lg
            pg = next((p for p in cx.pages if "fomo.family" in (p.url or "")), None)
            if pg is None:
                continue
            jwt = (pg.evaluate("() => localStorage.getItem('privy:token')")
                   or "").strip().strip('"')
            if len(jwt) > 100:
                JWT_CACHE.write_text(jwt)
                return jwt
        return None
    finally:
        pw.stop()


class Client:
    def __init__(self, jwt: str):
        self.h = {"user-agent": UA, "authorization": f"Bearer {jwt}",
                  "origin": "https://fomo.family", "referer": "https://fomo.family/"}
        self.n = 0

    def get(self, path: str):
        r = cffi.get(BASE + path, headers=self.h, impersonate="chrome131", timeout=15)
        self.n += 1
        time.sleep(PACING)
        if r.status_code != 200:
            raise RuntimeError(f"{r.status_code} {path[:80]}")
        return r.json().get("responseObject")

    def post(self, path: str, body):
        r = cffi.post(BASE + path, headers=self.h, json=body,
                      impersonate="chrome131", timeout=15)
        self.n += 1
        time.sleep(PACING)
        if r.status_code != 200:
            raise RuntimeError(f"{r.status_code} {path[:80]}")
        return r.json().get("responseObject")


def snap(con, endpoint: str, entity_id: str, obj):
    con.execute("""INSERT INTO fomo_rest_snapshots (captured_at, endpoint, entity_id, data)
                   VALUES (?,?,?,?) ON CONFLICT(endpoint, entity_id)
                   DO UPDATE SET captured_at=excluded.captured_at, data=excluded.data""",
                (int(time.time()), endpoint, entity_id,
                 json.dumps(obj, ensure_ascii=False)))


def fresh(con, endpoint: str, entity_id: str, cadence: int) -> bool:
    """Snapshot (endpoint, entity_id) plus récent que `cadence` passes → skip.
    Cadence 1 = jamais frais (collecte à chaque passe, comme avant)."""
    if cadence <= 1:
        return False
    try:
        row = con.execute("SELECT captured_at FROM fomo_rest_snapshots "
                          "WHERE endpoint=? AND entity_id=?",
                          (endpoint, entity_id)).fetchone()
        return bool(row) and (time.time() - row[0]) < cadence * PASS_SECONDS * 0.9
    except Exception:
        return False


def cursor_load(con, kind: str, uid: str) -> dict:
    """High-water mark de reprise (fomo_rest_snapshots, endpoint='cursor_<kind>_<uid>')."""
    try:
        row = con.execute("SELECT data FROM fomo_rest_snapshots WHERE endpoint=? AND entity_id=?",
                          (f"cursor_{kind}_{uid}", uid)).fetchone()
        st = json.loads(row[0]) if row else {}
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def cursor_save(con, kind: str, uid: str, cursor, pages: int, exhausted: bool) -> None:
    snap(con, f"cursor_{kind}_{uid}", uid,
         {"cursor": cursor, "pages": pages, "exhausted": bool(exhausted),
          "updated_at": int(time.time())})


def _rows_of(d):
    return (d.get("leaderboard") if isinstance(d, dict) else d) or []


# ---------------------------------------------------------------- collectes

def col_leaderboard(con, cli, cadence, ctx):
    lb = cli.get("/v2/leaderboard/24h") or {}
    rows = _rows_of(lb)
    snap(con, "leaderboard", "24h", rows)
    elite = []
    for row in (rows or [])[:N_ELITE]:
        uid = (row.get("user") or {}).get("id") if isinstance(row, dict) else None
        uid = uid or (row.get("id") if isinstance(row, dict) else None)
        if uid:
            elite.append(uid)
    ctx["elite"] = elite
    return f"leaderboard={len(rows or [])}"


def col_leaderboard_alltime(con, cli, cadence, ctx):
    if fresh(con, "leaderboard_alltime", "alltime", cadence):
        return "alltime frais, skip"
    d = cli.get("/v2/leaderboard?window=alltime&limit=100") or {}
    rows = _rows_of(d)
    snap(con, "leaderboard_alltime", "alltime", rows)
    return f"leaderboard_alltime={len(rows or [])}"


def col_trending(con, cli, cadence, ctx):
    trend = cli.post("/proxy/trendingTokens", {}) or []
    mints = []
    for t in trend:
        if isinstance(t, dict):
            tok = t.get("token") or {}
            m = tok.get("address") if isinstance(tok, dict) else None
            if m and m not in mints:
                mints.append(m)
        if len(mints) >= N_TOKENS:
            break
    ctx["mints"] = mints
    snap(con, "trending", "latest", trend)
    return f"trending={len(trend)} mints={len(mints)}"


def col_verified(con, cli, cadence, ctx):
    if fresh(con, "verified_tokens", "latest", cadence):
        return "verified frais, skip"
    vt = cli.get("/proxy/verifiedTokens") or []
    snap(con, "verified_tokens", "latest", vt)
    return f"verified={len(vt)}"


def col_trading_activity(con, cli, cadence, ctx):
    if fresh(con, "trading_activity_feed", "latest", cadence):
        return "activity frais, skip"
    d = cli.get("/feed/tradingActivity?limit=50&threshold=1000") or {}
    items = d.get("items") if isinstance(d, dict) else d
    snap(con, "trading_activity_feed", "latest", d)  # hasNextPage gardé
    return f"activity={len(items or [])}"


def _filter_batch(con, cli, endpoint, mints, cadence):
    """POST /proxy/filterTokens batch (1 appel pour N mints) → 1 snapshot/mint."""
    todo = [m for m in mints if not fresh(con, endpoint, m, cadence)]
    if not todo:
        return f"{endpoint} frais, skip"
    items = cli.post("/proxy/filterTokens",
                     [f"{m}:{NETWORK_ID}" for m in todo]) or []
    n = 0
    for it in items:
        m = (it.get("token") or {}).get("address") if isinstance(it, dict) else None
        if m:
            snap(con, endpoint, m, it)
            n += 1
    return f"{endpoint}={n}/{len(todo)}"


def col_token_about(con, cli, cadence, ctx):
    mints = ctx.get("mints") or []
    if not mints:
        return "about: pas de mints"
    return _filter_batch(con, cli, "token_about", mints, cadence)


def pre_graduated_mints(limit: int) -> list:
    """Les mints pré-graduation les plus récents de fomo.db (LECTURE mode=ro —
    jamais d'écriture sur la base des autres services)."""
    try:
        src = sqlite3.connect(f"file:{FOMO_DB}?mode=ro", uri=True, timeout=10)
        try:
            rows = src.execute("""SELECT mint FROM fomo_pre_graduated
                                  WHERE mint NOT LIKE '0x%'
                                  GROUP BY mint ORDER BY MAX(captured_at) DESC
                                  LIMIT ?""", (limit,)).fetchall()
        finally:
            src.close()
        return [r[0] for r in rows if r and r[0]]
    except Exception:
        return []


def col_bonding(con, cli, cadence, ctx):
    mints = pre_graduated_mints(N_TOKENS)
    if not mints:
        return "bonding: fomo_pre_graduated vide"
    return _filter_batch(con, cli, "bonding_snapshot", mints, cadence)


def col_hodlers_thesis(con, cli, cadence, ctx):
    out = []
    for mint in ctx.get("mints") or []:
        if fresh(con, "hodlers_top", mint, cadence) and \
           fresh(con, "thesis_sorted", mint, cadence):
            continue
        try:
            q = f"/hodlers/top?tokens=%5B%7B%22address%22%3A%22{mint}%22%2C%22networkId%22%3A{NETWORK_ID}%7D%5D"
            wrap = cli.get(q) or []
            tok = (wrap[0] if isinstance(wrap, list) and wrap else {}) or {}
            holders = tok.get("topHolders") or []
            snap(con, "hodlers_top", mint, tok)
            out.append(f"holders {mint[:6]}={len(holders)}/{tok.get('totalHolders')}")
        except Exception as e:
            out.append(f"holders {mint[:6]} ERR {str(e)[:40]}")
        try:
            now_ms = int(time.time() * 1000)
            th = cli.get(f"/feed/token/sortedThesis?tokenAddress={mint}&networkId={NETWORK_ID}"
                         f"&afterTime={now_ms - 86_400_000}&beforeTime={now_ms}&limit=500&threshold=0") or {}
            items = th.get("items") if isinstance(th, dict) else th
            snap(con, "thesis_sorted", mint, items or th)
            out.append(f"thesis {mint[:6]}={len(items or [])}")
        except Exception as e:
            out.append(f"thesis {mint[:6]} ERR {str(e)[:40]}")
    return " ".join(out) or "hodlers/thesis frais, skip"


def col_profiles(con, cli, cadence, ctx):
    """Remplaçant de do_profiles : 4 endpoints REST par uid (swaps/trades déjà
    couverts par col_swaps_trades — non dupliqués). Fraîcheur PAR KIND :
    un échec isolé se re-collecte à la passe suivante."""
    out = []
    for uid in (ctx.get("elite") or [])[:N_PROFILES]:
        for kind, path in PROFILE_KINDS:
            if fresh(con, f"profile_{kind}", uid, cadence):
                continue
            try:
                snap(con, f"profile_{kind}", uid, cli.get(path.format(uid=uid)))
                out.append(f"{kind} {str(uid)[:8]}")
            except Exception as e:
                out.append(f"{kind} {str(uid)[:8]} ERR {str(e)[:40]}")
    return " ".join(out) or "profiles frais, skip"


def col_swaps_trades(con, cli, cadence, ctx):
    out = []
    for uid in ctx.get("elite") or []:
        # --- swaps élite : backfill BORNÉ (SWAPS_PAGES) et INCRÉMENTAL —
        # curseur lastSwapId=<dernier id page n>, preuve sonde du 29/09.
        # INSERT OR IGNORE = idempotent par swap id. ---
        try:
            st = cursor_load(con, "swaps", uid)
            cur = None if st.get("exhausted") else st.get("cursor")
            new, done, exhausted = 0, 0, False
            while done < SWAPS_PAGES:
                q = f"/v2/users/{uid}/swaps?limit=100" + (f"&lastSwapId={cur}" if cur else "")
                d = cli.get(q) or {}
                rows = d.get("swaps") if isinstance(d, dict) else (d if isinstance(d, list) else [])
                rows = rows or []
                now = int(time.time())
                for s in rows:
                    sid = s.get("id") if isinstance(s, dict) else None
                    if not sid:
                        continue
                    rc = con.execute("""INSERT OR IGNORE INTO fomo_rest_swaps
                                        (swap_id, user_id, captured_at, data)
                                        VALUES (?,?,?,?)""",
                                     (sid, uid, now,
                                      json.dumps(s, ensure_ascii=False))).rowcount
                    new += 1 if rc and rc > 0 else 0
                done += 1
                nxt = rows[-1].get("id") if rows and isinstance(rows[-1], dict) else None
                if not rows or d.get("hasNextPage") is False or not nxt or nxt == cur:
                    cur = nxt or cur
                    exhausted = True
                else:
                    cur = nxt
                cursor_save(con, "swaps", uid, cur, done, exhausted)
                if exhausted:
                    break
            out.append(f"swaps {str(uid)[:8]}=+{new} p={done}{' E' if exhausted else ''}")
        except Exception as e:
            out.append(f"swaps {str(uid)[:8]} ERR {str(e)[:40]}")
        # --- trades fermés : page 1 snapshotée puis backfill BORNÉ
        # (TRADES_PAGES) par lastTradeId=closedTrades[-1].trade.id. ---
        try:
            tr = cli.get(f"/trades?userId={uid}&orderBy=closedAt")
            snap(con, "trades_closed", uid, tr)
            st = cursor_load(con, "trades", uid)
            cur = None if st.get("exhausted") else st.get("cursor")
            done, exhausted = 0, False
            while done < TRADES_PAGES:
                if cur is None:
                    d, rows = tr, ((tr or {}).get("closedTrades") or [])
                else:
                    d = cli.get(f"/trades?userId={uid}&orderBy=closedAt&lastTradeId={cur}")
                    rows = (d or {}).get("closedTrades") or []
                done += 1
                nxt = (rows[-1].get("trade") or {}).get("id") \
                    if rows and isinstance(rows[-1], dict) else None
                if not rows or (d or {}).get("hasNextPage") is False or not nxt or nxt == cur:
                    cur = nxt or cur
                    exhausted = True
                else:
                    cur = nxt
                cursor_save(con, "trades", uid, cur, done, exhausted)
                if exhausted:
                    break
            out.append(f"trades {str(uid)[:8]} p={done}{' E' if exhausted else ''}")
        except Exception as e:
            out.append(f"trades {str(uid)[:8]} ERR {str(e)[:40]}")
    return " ".join(out)


def col_clans(con, cli, cadence, ctx):
    if fresh(con, "clans", "24h", cadence):
        return "clans frais, skip"
    clans = cli.get("/v2/clans/leaderboard?window=24h&limit=50") or {}
    rows = _rows_of(clans)
    snap(con, "clans", "24h", rows)
    return f"clans={len(rows or [])}"


# La passe : (nom, cadence_en_passes, fonction). L'ordre compte :
# leaderboard→elite et trending→mints alimentent le ctx des suivantes.
COLLECTES = (
    ("leaderboard_24h", 1, col_leaderboard),
    ("leaderboard_alltime", 6, col_leaderboard_alltime),   # top100 : 1/6 passes
    ("trending", 1, col_trending),
    ("verified_tokens", 2, col_verified),                  # 1/2 passes
    ("trading_activity", 1, col_trading_activity),
    ("token_about", 1, col_token_about),                   # batch 12 mints
    ("bonding", 1, col_bonding),                           # batch 12 pré-grad
    ("hodlers_thesis", 1, col_hodlers_thesis),
    ("profiles", 2, col_profiles),                         # 4 uids × 4 kinds
    ("swaps_trades", 1, col_swaps_trades),
    ("clans", 2, col_clans),                               # 1/2 passes
)


def main() -> int:
    jwt = read_jwt()
    if jwt is None:
        jwt = refresh_jwt_via_cdp()
    if jwt is None:
        print("[rest] JWT absent/périmé et CDP sans page fomo — passe skippée")
        return 1
    cli = Client(jwt)
    con = sqlite3.connect(str(DB), timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_rest_snapshots (
                     captured_at INTEGER, endpoint TEXT, entity_id TEXT,
                     data TEXT, PRIMARY KEY (endpoint, entity_id))""")
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_rest_swaps (
                     swap_id TEXT PRIMARY KEY, user_id TEXT, captured_at INTEGER,
                     data TEXT)""")
    ctx, stats = {}, []
    t0 = time.time()
    for name, cadence, fn in COLLECTES:
        try:
            stats.append(fn(con, cli, cadence, ctx) or name)
        except Exception as e:
            stats.append(f"{name} ERR {str(e)[:50]}")
    con.commit()
    con.close()
    print(f"[rest] passe OK : {cli.n} appels en {time.time() - t0:.0f}s | "
          + " | ".join(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
