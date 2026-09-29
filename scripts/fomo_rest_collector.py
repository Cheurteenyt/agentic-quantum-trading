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
Tables : fomo_rest_snapshots (le dernier état par entité, JSON brut intégral
— l'extraction typée se fait quand une étude en a besoin) et fomo_rest_swaps
(append idempotent par swap id, la rotation élite)."""
import json, time, sys, sqlite3
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


def main() -> int:
    jwt = read_jwt()
    if jwt is None:
        print("[rest] JWT absent/périmé (ws_jwt_cache.txt) — passe skippée")
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
        try:
            sw = cli.get(f"/v2/users/{uid}/swaps?limit=100") or {}
            rows = sw.get("swaps") if isinstance(sw, dict) else (sw if isinstance(sw, list) else [])
            for s in rows or []:
                con.execute("""INSERT OR IGNORE INTO fomo_rest_swaps
                               (swap_id, user_id, captured_at, data)
                               VALUES (?,?,?,?)""",
                            (s.get("id"), uid, int(time.time()),
                             json.dumps(s, ensure_ascii=False)))
            stats.append(f"swaps {str(uid)[:8]}={len(rows or [])}")
        except Exception as e:
            stats.append(f"swaps {str(uid)[:8]} ERR {str(e)[:40]}")
        try:
            tr = cli.get(f"/trades?userId={uid}&orderBy=closedAt")
            snap(con, "trades_closed", uid, tr)
            stats.append(f"trades {str(uid)[:8]}")
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
