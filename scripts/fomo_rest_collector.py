#!/usr/bin/env python3
"""LE COLLECTEUR REST FOMO (29/09) — « mieux que du DOM » : la sonde RE
(scripts/studies/fomo_rest_probe.py) a prouvé que TOUTES les surfaces des
onglets (holders, thèses, swaps élite, trades fermés, leaderboard, clans,
trending) sont des endpoints REST de prod-api.fomo.family, et que le WAF
(Cloudflare) ne bloque que le fingerprint TLS : curl_cffi impersonate
chrome131 + Bearer JWT = 200 partout. Un appel REST remplace une route DOM
(hodlers/top = 97 holders + totalHolders en 1 GET, contre un clic + scroll
+ parse). Basse DÉDIÉE data/fomo/fomo_rest.db (un seul écrivain — la leçon
du lock du 29/09), JWT partagé avec le daemon (ws_jwt_cache.txt, top-up
15 min). Pacing 1,0 s : 37 appels ≈ 50 s/pass, timer 30 min.
PAGINATION (29/09, preuves scripts/studies/fomo_rest_cursor_probe.py) :
swaps = &lastSwapId=<dernier id page n> (p1→p2→p3 disjointes, zéro
chevauchement) ; trades = &lastTradeId=<closedTrades[-1].trade.id> (param
extrait du bundle fomo.family, trades-v2 : getNextPageParam = ne()).
Backfill BORNÉ par passe (SWAPS_PAGES/TRADES_PAGES, env FOMO_*_PAGES) et
INCRÉMENTAL : le curseur de reprise est persisté dans fomo_rest_snapshots
(endpoint='cursor_swaps_<uid>' / 'cursor_trades_<uid>') ; passe suivante
reprend au curseur ; flux épuisé → cycle neuf depuis le haut.
Tables : fomo_rest_snapshots (le dernier état par entité, JSON brut intégral
— l'extraction typée se fait quand une étude en a besoin) et fomo_rest_swaps
(append idempotent par swap id, la rotation élite)."""
import json, os, time, sys, sqlite3
from pathlib import Path
from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[1]
JWT_CACHE = ROOT / "data" / "fomo" / "ws_jwt_cache.txt"
DB = ROOT / "data" / "fomo" / "fomo_rest.db"
BASE = "https://prod-api.fomo.family"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
NETWORK_ID = 1399811149  # solana
PACING = 1.0
N_TOKENS = 12
N_ELITE = 5
SWAPS_PAGES = max(1, int(os.environ.get("FOMO_SWAPS_PAGES", "5")))
TRADES_PAGES = max(1, int(os.environ.get("FOMO_TRADES_PAGES", "3")))


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

    def post(self, path: str, body: dict):
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
    stats = []

    lb = cli.get("/v2/leaderboard/24h") or {}
    lb_rows = lb.get("leaderboard") if isinstance(lb, dict) else lb
    snap(con, "leaderboard", "24h", lb_rows)
    stats.append(f"leaderboard={len(lb_rows or [])}")
    elite = []
    for row in (lb_rows or [])[:N_ELITE]:
        uid = (row.get("user") or {}).get("id") if isinstance(row, dict) else None
        uid = uid or (row.get("id") if isinstance(row, dict) else None)
        if uid:
            elite.append(uid)

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
    stats.append(f"trending={len(trend)} mints={len(mints)}")
    snap(con, "trending", "latest", trend)

    for mint in mints:
        q = f"/hodlers/top?tokens=%5B%7B%22address%22%3A%22{mint}%22%2C%22networkId%22%3A{NETWORK_ID}%7D%5D"
        try:
            wrap = cli.get(q) or []
            tok = (wrap[0] if isinstance(wrap, list) and wrap else {}) or {}
            holders = tok.get("topHolders") or []
            snap(con, "hodlers_top", mint, tok)
            stats.append(f"holders {mint[:6]}={len(holders)}/{tok.get('totalHolders')}")
        except Exception as e:
            stats.append(f"holders {mint[:6]} ERR {str(e)[:40]}")
        try:
            now_ms = int(time.time() * 1000)
            th = cli.get(f"/feed/token/sortedThesis?tokenAddress={mint}&networkId={NETWORK_ID}"
                         f"&afterTime={now_ms - 86_400_000}&beforeTime={now_ms}&limit=500&threshold=0") or {}
            items = th.get("items") if isinstance(th, dict) else th
            snap(con, "thesis_sorted", mint, items or th)
            stats.append(f"thesis {mint[:6]}={len(items or [])}")
        except Exception as e:
            stats.append(f"thesis {mint[:6]} ERR {str(e)[:40]}")

    for uid in elite:
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
            stats.append(f"swaps {str(uid)[:8]}=+{new} p={done}{' E' if exhausted else ''}")
        except Exception as e:
            stats.append(f"swaps {str(uid)[:8]} ERR {str(e)[:40]}")
        # --- trades fermés : page 1 snapshotée (comportement inchangé) puis
        # backfill BORNÉ (TRADES_PAGES) par lastTradeId=closedTrades[-1].trade.id
        # (bundle fomo.family). Page 1 réutilisée si départ à neuf. ---
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
            stats.append(f"trades {str(uid)[:8]} p={done}{' E' if exhausted else ''}")
        except Exception as e:
            stats.append(f"trades {str(uid)[:8]} ERR {str(e)[:40]}")

    try:
        clans = cli.get("/v2/clans/leaderboard?window=24h&limit=50") or {}
        rows = clans.get("leaderboard") if isinstance(clans, dict) else clans
        snap(con, "clans", "24h", rows)
        stats.append(f"clans={len(rows or [])}")
    except Exception as e:
        stats.append(f"clans ERR {str(e)[:40]}")

    con.commit()
    con.close()
    print(f"[rest] passe OK : {cli.n} appels | " + " | ".join(stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
