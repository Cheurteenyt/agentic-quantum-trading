import json, sys, sqlite3, time, datetime
sys.path.insert(0, "scripts")
from fomo_ohlcv_backfill import fresh_jwt
from playwright.sync_api import sync_playwright

QUOTE = {"So11111111111111111111111111111111111111112",  # SOL
         "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
         "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
         "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs"}  # WETH
tok = fresh_jwt()
USERS = {"unipcs": "36adb85a-c0fd-5fa8-916d-8fdc32fe4237",
         "pointfarmcap": "6d8c0bf3-5d42-506c-a0ea-9e1e75ff38af"}

# --- 1. resolution handle->userId documentee (endpoint exact)
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    page = b.contexts[0].new_page()
    page.goto("https://fomo.family/", wait_until="domcontentloaded", timeout=45000); page.wait_for_timeout(3000)
    def f(u):
        r = page.evaluate("""async ([tok, u]) => { const r = await fetch(u, {headers: {authorization: 'Bearer ' + tok}}); return {status: r.status, body: await r.text()}; }""", [tok, u])
        try: return r['status'], json.loads(r['body'])
        except Exception: return r['status'], r['body'][:200]
    st, res = f("https://prod-api.fomo.family/v2/users/userHandle/unipcs")
    print("RESOLUTION /v2/users/userHandle/unipcs:", st, json.dumps(res)[:600])
    print("responseObject keys:", list(res.get('responseObject', {}).keys()) if isinstance(res, dict) else '?')

    # --- 2. fetch page1 limit=100 des 2 profils + stockage
    db = sqlite3.connect("data/fomo/fomo_swaps.db", timeout=30)
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
    total = {}
    for h, uid in USERS.items():
        st, j = f(f"https://prod-api.fomo.family/v2/users/{uid}/swaps?limit=100")
        ro = j.get('responseObject', {}) if isinstance(j, dict) else {}
        sw = ro.get('swaps', [])
        n = 0
        for s in sw:
            raw = json.dumps(s)
            in_m, out_m = s.get('inTokenAddress'), s.get('outTokenAddress')
            side = 'sell' if out_m in QUOTE else ('buy' if in_m in QUOTE else 'swap')
            mint = in_m if side == 'buy' else out_m
            ca = s.get('createdAt'); ts = int(datetime.datetime.fromisoformat(ca.replace('Z', '+00:00')).timestamp()) if ca else None
            db.execute("""INSERT OR IGNORE INTO fomo_swaps VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (s['id'], uid, h, None, mint, side, in_m, s.get('inHumanAmount'), out_m, s.get('outHumanAmount'),
                 s.get('humanUsdAmountOut') or s.get('humanUsdAmountIn'), None, None,
                 s.get('provider'), s.get('networkId'), int(bool(s.get('isOffPlatform'))), int(bool(s.get('isCrossmint'))),
                 ca, ts, raw, time.time()))
            n += 1
        db.execute("INSERT OR REPLACE INTO _swaps_meta VALUES (?,?,?,?,?)", (uid, h, time.time(), sw[-1]['createdAt'] if sw else None, 1))
        db.commit()  # COMMIT explicite par page
        total[h] = (len(sw), ro.get('hasNextPage'))
        print(f"STORED {h}: page1 nb={len(sw)} hasNext={ro.get('hasNextPage')}")
    db.close()
    page.close()

# --- 3. verification
db = sqlite3.connect("data/fomo/fomo_swaps.db")
print("TOTAL fomo_swaps:", db.execute("SELECT COUNT(*) FROM fomo_swaps").fetchone()[0])
for r in db.execute("SELECT user_handle, side, COUNT(*), MIN(datetime(ts,'unixepoch')), MAX(datetime(ts,'unixepoch')), ROUND(SUM(size_usd)) FROM fomo_swaps GROUP BY user_handle, side"):
    print("  ", r)
