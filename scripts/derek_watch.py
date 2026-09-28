#!/usr/bin/env python
"""derek_watch.py — le détecteur TEMPS RÉEL de derek518 (latence ~1-2 min).

La demi-vie mesurée (docs/20, 02baa1e) : l'edge derek décroît 5× en 24h
(+21,2 % @+1h → +7,8 % @+24h). La chaîne actuelle (swaps-fresh HORAIRE +
passe paper 15 min) = latence ~1h15. Ici : le swap API direct via fetch
IN-PAGE CDP (le REST Python = 430 Cloudflare), 1 passe/minute.

Détection : buy ≥ $5k, token âgé ≥ 7j (1re bougie 1h de fomo.db), pas déjà
répliqué (idempotence par swap_id, l'index unique de fomo_paper.db) →
OPEN rule='replication_derek' IMMÉDIAT (entry = dernier close 1m/tick,
entry_ts=now) + l'état derek_last_ts avancé. Mêmes CONSTANTES que la règle
validée de fomo_paper_forward.py ; INSERT OR IGNORE + busy_timeout — jamais
bloquer la passe paper forward (elle écrit la même DB toutes les 15 min).
"""
import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fomo_ohlcv_backfill import fresh_jwt  # retry ×3 + cache disque

from playwright.sync_api import sync_playwright

# ── les DB ──
LIVE_DB = ROOT / "data" / "fomo" / "fomo.db"          # lecture (mode=ro)
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"   # lecture (mode=ro)
PAPER_DB = ROOT / "data" / "fomo" / "fomo_paper.db"   # écriture (OR IGNORE)

# ── les CONSTANTES de la règle replication_derek (fomo_paper_forward.py) ──
REPL_RULE = "replication_derek"
DEREK_HANDLE = "derek518"
REPL_MIN_USD = 5000.0
REPL_MIN_AGE_S = 7 * 86400
REPL_ENTRY_WINDOW_S = 900        # entrée ≤ 15 min après le swap (règle validée)
REPL_MAX_OPEN = 10
PRICE_MAX_STALE_S = 2 * 3600     # pas de prix vivant = pas d'entrée

QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",  # SOL wrappé
    "7vfCXTUXxzBN6xej7ucn7NNvi3orD1vs8HN4cBwpfA2Z",  # WETH Wormhole
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",  # cbBTC Coinbase
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC
})

JS_FETCH = """async ([tok, uid]) => {
    const r = await fetch(
        `https://prod-api.fomo.family/v2/users/${uid}/swaps?limit=100`,
        {headers: {authorization: 'Bearer ' + tok,
                   'content-type': 'application/json'}});
    const t = await r.text();
    return {status: r.status, body: t.slice(0, 900000)};
}"""


def is_tradeable_mint(mint) -> bool:
    """Les faux mints (stables, SOL wrappé, 0x EVM) = jamais des tokens fomo."""
    if not mint or not isinstance(mint, str):
        return False
    if mint in QUOTE_MINTS or mint.startswith("0x"):
        return False
    return True


def open_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=45)
    con.execute("PRAGMA busy_timeout=45000")
    return con


def open_paper_rw() -> sqlite3.Connection:
    """Écriture paper : busy_timeout + WAL + le schéma/idempotence swap_id
    (le MÊME index unique que fomo_paper_forward.open_paper). Transactions
    sub-ms par swap → la passe 15 min n'attend jamais derrière nous."""
    con = sqlite3.connect(PAPER_DB, timeout=45)
    con.execute("PRAGMA busy_timeout=45000")
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        pass
    con.execute("""CREATE TABLE IF NOT EXISTS fomo_paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mint TEXT NOT NULL, ticker TEXT, rule TEXT NOT NULL,
        horizon TEXT, entry_ts REAL, entry_price REAL,
        exit_ts REAL, exit_price REAL,
        multiple REAL, max_multiple REAL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        opened_at REAL NOT NULL, closed_at REAL)""")
    cols = {r[1] for r in con.execute("PRAGMA table_info(fomo_paper_trades)")}
    if "swap_id" not in cols:
        con.execute("ALTER TABLE fomo_paper_trades ADD COLUMN swap_id TEXT")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_paper_swap "
                "ON fomo_paper_trades (swap_id) WHERE swap_id IS NOT NULL")
    con.execute("CREATE TABLE IF NOT EXISTS fomo_paper_state "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    return con


def unwrap_swaps(d):
    """Le shape réel (collector) : {'responseObject': {'swaps': [...]}} —
    sinon swaps/items/data/results au top, sinon liste directe."""
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        ro = d.get("responseObject")
        if isinstance(ro, dict):
            for k in ("swaps", "items", "data", "results"):
                if k in ro:
                    return ro[k]
        for k in ("swaps", "items", "data", "results"):
            if k in d:
                return d[k]
    return []


def fetch_swaps_cdp(jwt: str, uid: str, retries: int = 2):
    """Le fetch sur le daemon CDP — zéro page créée (la leçon des flashs).
    Voie 1 : fetch IN-PAGE sur la page fomo.family existante (le pattern
    fomo_swaps_fetch_browser.py). Voie 2 (repli si l'API droppe CORS) :
    ctx.request = la pile TLS du MÊME Chromium, insensible au CORS.
    Retries courts : la passe suivante (60 s) retente de toute façon."""
    last = None
    for attempt in range(retries):
        try:
            with sync_playwright() as p:
                b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
                ctx = b.contexts[0]
                page = next((c for c in ctx.pages
                             if "fomo.family" in (c.url or "")), None)
                if page is not None:
                    try:
                        res = page.evaluate(JS_FETCH, [jwt, uid])
                        if res.get("status") == 200:
                            return unwrap_swaps(json.loads(res["body"]))
                        last = RuntimeError(f"in-page HTTP {res.get('status')}")
                    except Exception as e:  # CORS/edge → la voie 2
                        last = e
                url = (f"https://prod-api.fomo.family/v2/users/{uid}"
                       f"/swaps?limit=100")
                r = ctx.request.get(url, headers={
                    "authorization": f"Bearer {jwt}",
                    "content-type": "application/json",
                    "referer": "https://fomo.family/"}, timeout=25000)
                if r.status == 200:
                    return unwrap_swaps(json.loads(r.text()))
                raise RuntimeError(f"HTTP {r.status}: {r.text()[:80]}")
        except Exception as e:  # noqa: BLE001 — retry puis la boucle 60 s
            last = e
            time.sleep(5.0 * (attempt + 1))
    raise last


def parse_swap(it: dict):
    """→ (swap_id, mint, side, ts_s, size_usd) | None. buy = quote en entrée."""
    sid = it.get("id")
    try:
        cta = it.get("createdAt")
        ts = (datetime.fromisoformat(cta.replace("Z", "+00:00")).timestamp()
              if cta else None)
    except Exception:
        ts = None
    if not sid or ts is None:
        return None
    in_t, out_t = it.get("inTokenAddress"), it.get("outTokenAddress")
    if in_t in QUOTE_MINTS and out_t not in QUOTE_MINTS:
        side, mint = "buy", out_t
    elif out_t in QUOTE_MINTS and in_t not in QUOTE_MINTS:
        side, mint = "sell", in_t
    else:
        return None
    usd = it.get("humanUsdAmountIn") or it.get("humanUsdAmountOut") or 0.0
    return str(sid), mint, side, float(ts), float(usd)


def last_price_fast(con_live, mint, now):
    """Le dernier close 1m → tick → 1h (fraîcheur ≤ 2h = garde fake-forward)."""
    for sql, ms in (
            ("SELECT time, close FROM fomo_ohlcv WHERE asset=? "
             "AND period='1m' ORDER BY time DESC LIMIT 1", True),
            ("SELECT ts_s, priceUsd FROM fomo_ticks WHERE mint=? "
             "ORDER BY ts_s DESC LIMIT 1", False),
            ("SELECT time, close FROM fomo_ohlcv WHERE asset=? "
             "AND period='1h' ORDER BY time DESC LIMIT 1", True)):
        r = con_live.execute(sql, (mint,)).fetchone()
        if r and r[1]:
            ts = float(r[0]) / 1000.0 if ms else float(r[0])
            px = float(r[1])
            if px > 0 and now - ts <= PRICE_MAX_STALE_S:
                return ts, px
    return None, None


def derek_uid(con_swaps) -> str:
    r = con_swaps.execute("SELECT user_id FROM _swaps_meta WHERE handle=?",
                          (DEREK_HANDLE,)).fetchone()
    if not r:
        raise RuntimeError("derek518 absent du cache _swaps_meta")
    return r[0]


def detect_pass(now: float) -> dict:
    """Une passe : API → filtres règle → OPEN immédiat → derek_last_ts."""
    con_swaps, con_live, con_paper = open_ro(SWAPS_DB), open_ro(LIVE_DB), open_paper_rw()
    try:
        uid = derek_uid(con_swaps)
        items = fetch_swaps_cdp(fresh_jwt(), uid)
        parsed = sorted((x for x in (parse_swap(i) for i in items) if x),
                        key=lambda x: x[3])
        last = con_paper.execute("SELECT value FROM fomo_paper_state "
                                 "WHERE key='derek_last_ts'").fetchone()
        since = float(last[0]) if last else now - REPL_ENTRY_WINDOW_S
        seen = {x[0] for x in con_paper.execute(
            "SELECT swap_id FROM fomo_paper_trades WHERE swap_id IS NOT NULL")}
        n_open = con_paper.execute(
            "SELECT COUNT(*) FROM fomo_paper_trades "
            "WHERE rule=? AND status='OPEN'", (REPL_RULE,)).fetchone()[0]
        opened = skipped = capped = 0
        newest = since
        log = []
        for sid, mint, side, ts, usd in parsed:
            newest = max(newest, ts)
            if ts <= since - 120 or sid in seen or side != "buy":
                continue
            if usd < REPL_MIN_USD or not is_tradeable_mint(mint):
                continue
            if now - ts > REPL_ENTRY_WINDOW_S:
                skipped += 1
                continue
            if n_open >= REPL_MAX_OPEN:
                capped += 1
                continue
            age_r = con_live.execute(
                "SELECT MIN(time) FROM fomo_ohlcv WHERE asset=? AND period='1h'",
                (mint,)).fetchone()
            if not age_r or not age_r[0] or \
                    now - age_r[0] / 1000.0 < REPL_MIN_AGE_S:
                skipped += 1
                continue
            px_ts, px = last_price_fast(con_live, mint, now)
            if not px or not px_ts:
                skipped += 1
                continue
            tk = con_live.execute(
                "SELECT ticker FROM fomo_tokens WHERE mint=? "
                "ORDER BY resolved_at DESC LIMIT 1", (mint,)).fetchone()
            tk = ((tk[0] or mint[:10]).upper()) if tk else mint[:10]
            cur = con_paper.execute(
                "INSERT OR IGNORE INTO fomo_paper_trades (mint, ticker, rule, "
                "horizon, entry_ts, entry_price, status, opened_at, swap_id) "
                "VALUES (?,?,?,?,?,?, 'OPEN', ?, ?)",
                (mint, tk, REPL_RULE, "24h", now, px, now, sid))
            con_paper.commit()  # COMMIT explicite par swap
            if cur.rowcount:
                seen.add(sid)
                n_open += 1
                opened += 1
                log.append(f"OPEN {tk} {mint[:12]}… swap={usd:.0f}$ "
                           f"@{px:.8g} (lat {now - ts:.0f}s)")
            else:
                skipped += 1  # déjà répliqué (course paper forward) = idempotent
        if newest > since:
            con_paper.execute(
                "INSERT INTO fomo_paper_state (key, value) "
                "VALUES ('derek_last_ts', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(newest),))
            con_paper.commit()
        return {"items": len(parsed), "opened": opened, "skipped": skipped,
                "capped": capped, "log": log}
    finally:
        for c in (con_swaps, con_live, con_paper):
            c.close()


def close_1m_at(con_live, mint, t_s, tol=120):
    """Le close 1m couvrant t_s (bougie ≤ t, ≤ tol s avant) → px | None."""
    r = con_live.execute(
        "SELECT time, close FROM fomo_ohlcv WHERE asset=? AND period='1m' "
        "AND time<=? ORDER BY time DESC LIMIT 1",
        (mint, int(t_s * 1000))).fetchone()
    if r and r[0] and r[1] and t_s - r[0] / 1000.0 <= tol:
        return float(r[1])
    return None


def measure_palier(now: float, days: int = 3) -> dict:
    """LE TEST DU PALIER : ret 24h entrée @+2 min vs @+1h sur les achats
    derek récents couverts 1m. n petit, indicatif."""
    con_swaps, con_live = open_ro(SWAPS_DB), open_ro(LIVE_DB)
    try:
        uid = derek_uid(con_swaps)
        rows = con_swaps.execute(
            "SELECT swap_id, mint, ts, size_usd FROM fomo_swaps "
            "WHERE user_id=? AND side='buy' AND size_usd>=? AND ts>? "
            "ORDER BY ts DESC", (uid, REPL_MIN_USD, now - days * 86400)
        ).fetchall()
        extended = False
        if not rows:  # n=0 sur la fenêtre → élargi pour le signal
            extended = True
            rows = con_swaps.execute(
                "SELECT swap_id, mint, ts, size_usd FROM fomo_swaps "
                "WHERE user_id=? AND side='buy' AND size_usd>=? "
                "ORDER BY ts DESC LIMIT 10", (uid, REPL_MIN_USD)).fetchall()
        out = []
        for sid, mint, ts, usd in rows:
            if not is_tradeable_mint(mint):
                continue
            px2 = close_1m_at(con_live, mint, ts + 120)
            px1h = close_1m_at(con_live, mint, ts + 3600, tol=600)
            p2f = close_1m_at(con_live, mint, ts + 120 + 86400, tol=3600)
            p1f = close_1m_at(con_live, mint, ts + 3600 + 86400, tol=3600)
            if not (px2 and px1h and p2f and p1f):
                continue  # pas la couverture 1m aux 4 points = hors mesure
            out.append({"swap": sid[:8], "mint": mint[:10], "usd": usd,
                        "dt": datetime.fromtimestamp(ts, timezone.utc)
                              .strftime("%m-%d %H:%M"),
                        "ret2m": p2f / px2 - 1, "ret1h": p1f / px1h - 1})
        return {"n": len(out), "extended": extended, "rows": out}
    finally:
        con_swaps.close()
        con_live.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--passes", type=int, default=0, help="0 = infini")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--palier", action="store_true",
                    help="la mesure +2 min vs +1 h (puis sort)")
    a = ap.parse_args()
    if a.palier:
        m = measure_palier(time.time())
        tag = " (fenêtre ÉLARGIE, n=0 sur 3 j)" if m["extended"] else ""
        print(f"PALIER{tag} : n={m['n']}")
        for r in m["rows"]:
            print(f"  {r['dt']} {r['mint']}… {r['usd']:.0f}$ "
                  f"+2m→{r['ret2m'] * 100:+.1f}%  +1h→{r['ret1h'] * 100:+.1f}%")
        if m["n"]:
            med = (sorted(x["ret2m"] for x in m["rows"])[m["n"] // 2],
                   sorted(x["ret1h"] for x in m["rows"])[m["n"] // 2])
            print(f"  médiane : +2m {med[0] * 100:+.1f}% vs +1h {med[1] * 100:+.1f}%")
        return
    i = 0
    while True:
        now = time.time()
        t0 = time.time()
        try:
            r = detect_pass(now)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] passe "
                  f"items={r['items']} open={r['opened']} "
                  f"skip={r['skipped']} cap={r['capped']} "
                  f"({time.time() - t0:.1f}s)", flush=True)
            for line in r["log"]:
                print("  " + line, flush=True)
        except Exception as e:  # noqa: BLE001 — la boucle survit aux pannes
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ERREUR passe: "
                  f"{type(e).__name__}: {e}", flush=True)
        i += 1
        if not a.loop or (a.passes and i >= a.passes):
            break
        time.sleep(max(1, a.interval - (time.time() - t0)))


if __name__ == "__main__":
    main()
