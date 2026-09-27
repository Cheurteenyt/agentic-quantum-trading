"""Collector swaps baleines fomo — pagination lastSwapId (decouverte 2026-09-27).
Pour chaque trader: resolve userId (in-page CDP, cache _swaps_meta), fetch les
pages (?limit=100&lastSwapId=<dernier id page precedente>), INSERT OR IGNORE,
commit par page. DB: data/fomo/fomo_swaps.db. Lecture seule fomo.db (tickers).
--fresh : mode RECURRENT page-1-only (100 swaps les plus frais par trader,
pas de pagination) — cadence proposee : horaire (timer systemd user)."""
import argparse, json, sqlite3, sys, time, datetime
sys.path.insert(0, "scripts")
from fomo_ohlcv_backfill import fresh_jwt
from playwright.sync_api import sync_playwright

QUOTE = {"So11111111111111111111111111111111111111112",
         "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
         "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
         "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs"}
HANDLES = ["unipcs", "pointfarmcap", "ogle", "RugDalio", "frankdegods",
           "frogmanhaha", "dingalingts", "picadura", "ethersole", "cryptolyxe",
           "heeshilio", "derek518", "sadcrissy"]  # 10 utiles, backups si resolve fail
ap = argparse.ArgumentParser(description="Collector swaps baleines fomo")
ap.add_argument("--fresh", action="store_true",
                help="page 1 uniquement (100 swaps les plus frais par trader) "
                     "— mode recurrent, INSERT OR IGNORE, cadence horaire")
ARGS = ap.parse_args()
MAX_PAGES, PAGE = (1 if ARGS.fresh else 40), 100
SWDB = "/run/media/cheurteen/Jeux SSD/trading-agent/data/fomo/fomo_swaps.db"
FDB = "/run/media/cheurteen/Jeux SSD/trading-agent/data/fomo/fomo.db"

db = sqlite3.connect(SWDB, timeout=30)
db.execute("PRAGMA busy_timeout=30000")
db.execute("""CREATE TABLE IF NOT EXISTS fomo_swaps (
    swap_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, user_handle TEXT,
    ticker TEXT, mint TEXT, side TEXT,
    in_mint TEXT, in_amount REAL, out_mint TEXT, out_amount REAL,
    size_usd REAL, price TEXT, pnl REAL,
    provider TEXT, network_id INTEGER,
    is_off_platform INTEGER, is_crossmint INTEGER,
    created_at TEXT, ts INTEGER,
    raw_json TEXT NOT NULL, fetched_at REAL NOT NULL)""")
db.execute("CREATE INDEX IF NOT EXISTS ix_swaps_uid_ts ON fomo_swaps(user_id, ts)")
db.execute("CREATE TABLE IF NOT EXISTS _swaps_meta (user_id TEXT PRIMARY KEY, handle TEXT, last_fetch REAL, last_created_at TEXT, pages INTEGER)")
db.commit()

fdb = sqlite3.connect(f"file:{FDB}?mode=ro", uri=True, timeout=15)
mint2tick = dict(fdb.execute("SELECT mint, ticker FROM fomo_tokens").fetchall())
fdb.close()

JS = """async ([tok, url]) => {
    const r = await fetch(url, {headers: {authorization: 'Bearer ' + tok, 'content-type': 'application/json'}});
    return {status: r.status, body: await r.text()};
}"""
tok = fresh_jwt()

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = b.contexts[0].new_page()
    page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(3000)

    def f(url):
        r = page.evaluate(JS, [tok, url])
        try:
            j = json.loads(r["body"])
            return r["status"], (j.get("responseObject") or {}) if isinstance(j, dict) else {}
        except Exception:
            return r["status"], {}

    # 1. resolution handle -> userId (--fresh : cache _swaps_meta d'abord,
    #    on ne resolve en live que les handles inconnus)
    users = {}
    cached = dict(db.execute("SELECT handle, user_id FROM _swaps_meta").fetchall()) \
        if ARGS.fresh else {}
    for h in HANDLES:
        if cached.get(h):
            users[h] = cached[h]
            continue
        st, ro = f(f"https://prod-api.fomo.family/v2/users/userHandle/{h}")
        uid = ro.get("id") or (ro.get("user") or {}).get("id")
        if uid:
            users[h] = uid
        time.sleep(0.4)
    print(f"RESOLVED {len(users)}/{len(HANDLES)}:", {k: v[:8] for k, v in users.items()})

    # 2. backfill complet par trader
    for h, uid in users.items():
        total, pages, cursor, oldest = 0, 0, None, None
        while pages < MAX_PAGES:
            url = f"https://prod-api.fomo.family/v2/users/{uid}/swaps?limit={PAGE}"
            if cursor:
                url += f"&lastSwapId={cursor}"
            st, ro = f(url)
            sw = ro.get("swaps", []) if isinstance(ro, dict) else []
            if st != 200 or not sw:
                print(f"  {h}: stop p{pages+1} st={st} nb={len(sw)}")
                break
            n = 0
            for s in sw:
                in_m, out_m = s.get("inTokenAddress"), s.get("outTokenAddress")
                side = "sell" if out_m in QUOTE else ("buy" if in_m in QUOTE else "swap")
                mint = out_m if side == "buy" else in_m  # buy = quote en in -> token recu = out
                ca = s.get("createdAt")
                ts = int(datetime.datetime.fromisoformat(ca.replace("Z", "+00:00")).timestamp()) if ca else None
                db.execute("""INSERT OR IGNORE INTO fomo_swaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (s["id"], uid, h, mint2tick.get(mint), mint, side, in_m, s.get("inHumanAmount"),
                     out_m, s.get("outHumanAmount"), s.get("humanUsdAmountOut") or s.get("humanUsdAmountIn"),
                     None, None, s.get("provider"), s.get("networkId"),
                     int(bool(s.get("isOffPlatform"))), int(bool(s.get("isCrossmint"))),
                     ca, ts, json.dumps(s), time.time()))
                n += 1
            total += n
            pages += 1
            oldest = sw[-1].get("createdAt")
            cursor = sw[-1]["id"]
            db.commit()  # COMMIT explicite par page
            if len(sw) < PAGE or not ro.get("hasNextPage"):
                break
            time.sleep(0.6)
        db.execute("INSERT OR REPLACE INTO _swaps_meta VALUES (?,?,?,?,?)", (uid, h, time.time(), oldest, pages))
        db.commit()
        print(f"DONE {h}: pages={pages} nouveaux={total} oldest={oldest}")
    page.close()

# 3. signaux
now = int(time.time())
wk = now - 7 * 86400
print("\n=== SIGNALS par trader (7j) ===")
rows = db.execute("""SELECT user_handle, COUNT(*),
    SUM(CASE WHEN side='buy' THEN 1 ELSE 0 END), SUM(CASE WHEN side='sell' THEN 1 ELSE 0 END),
    ROUND(SUM(CASE WHEN ts>=? THEN size_usd ELSE 0 END)), MAX(created_at), MIN(created_at)
    FROM fomo_swaps GROUP BY user_handle ORDER BY COUNT(*) DESC""", (wk,)).fetchall()
for r in rows:
    print(f"  {r[0]:14s} n={r[1]:4d} buy={r[2]:4d} sell={r[3]:4d} vol7j=${r[4] or 0:>12,.0f} recent={r[5]} oldest={r[6]}")
print("\n=== TOP tickers achetes 7j (tous traders) ===")
for r in db.execute("""SELECT COALESCE(ticker, substr(mint,1,8)), COUNT(*), ROUND(SUM(size_usd)), COUNT(DISTINCT user_handle)
    FROM fomo_swaps WHERE side='buy' AND ts>=? GROUP BY mint ORDER BY COUNT(*) DESC LIMIT 12""", (wk,)).fetchall():
    print(f"  {r[0]:12s} buys={r[1]:4d} vol=${r[2] or 0:>12,.0f} traders={r[3]}")
print("TOTAL:", db.execute("SELECT COUNT(*) FROM fomo_swaps").fetchone()[0])
db.close()
