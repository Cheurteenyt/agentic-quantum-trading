#!/usr/bin/env python
"""LE COLLECTEUR D'HISTORIQUE fomo — la donnée on-chain complète.

Sur fomo, les tokens sont des tokens SOLANA : leur historique de prix
existe ON-CHAIN et GeckoTerminal l'indexe (les bougies OHLCV de chaque
pool, paginées jusqu'à la création). C'est l'égalité de donnée avec
Aster : le backtest fomo devient possible sur du complet et impartial.

Le flux par token :
  1. GT search par ticker → le mint + le pool principal
  2. OHLCV 1m paginé (limit 1000, before_timestamp en arrière) → fomo_ohlcv
  3. OHLCV 1h paginé (l'histoire longue)
Le tout stocké dans fomo_ohlcv (la même table que le collector live).

  .venv/bin/python scripts/fomo_history_collector.py            # tous les tickers fomo
  .venv/bin/python scripts/fomo_history_collector.py --tickers GROK,DEBT
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomo" / "fomo.db"
GT = "https://api.geckoterminal.com/api/v2"
H = {"User-Agent": "trading-agent/1.0", "Accept": "application/json"}
SLEEP = 2.1          # le free tier GT : 30 appels/min


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers=H)
    for attempt in (1, 2, 3, 4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                time.sleep(65.0)          # le free tier GT : le cooldown complet
                continue
            raise
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2.0 * attempt)
    return {}



def resolve_ticker(mint: str) -> str | None:
    """DexScreener par mint → le ticker (le symbol du token)."""
    try:
        d = get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}")
    except Exception:
        return None
    pairs = d.get("pairs") or []
    for p in pairs:
        bt = p.get("baseToken", {})
        if bt.get("address") == mint and bt.get("symbol"):
            return bt["symbol"]
    for p in pairs:
        qt = p.get("quoteToken", {})
        if qt.get("address") == mint and qt.get("symbol"):
            return qt["symbol"]
    return None


def fnum(x) -> float:
    return float(str(x).replace("$", "").replace(",", "") or 0)


def resolve_mint(ticker: str) -> tuple[str | None, str | None]:
    """DexScreener search par ticker → (mint, pool principal).
    Le search GT renvoie 404 — DexScreener est la source de résolution."""
    try:
        d = get(f"https://api.dexscreener.com/latest/dex/search?q={ticker}")
    except Exception:
        return None, None
    sol_pairs = [p for p in (d.get("pairs") or [])
                 if p.get("chainId") == "solana"]
    pairs = [p for p in sol_pairs
             if p.get("baseToken", {}).get("symbol", "").upper() == ticker]
    if not pairs:
        pairs = [p for p in sol_pairs
                 if p.get("quoteToken", {}).get("symbol", "").upper() == ticker]
        if pairs:
            # le token est en QUOTE : le mint = quoteToken.address
            fomo_pairs = [p for p in pairs if p.get("dexId") == "fomo"]
            best = max(fomo_pairs or pairs,
                       key=lambda x: (x.get("liquidity") or {}).get("usd", 0))
            mint = best.get("quoteToken", {}).get("address")
            return (mint, None) if mint else (None, None)
    if not pairs:
        return None, None
    # le désambiguïsateur : plusieurs tokens portent le même ticker — le
    # token NATIF fomo (dexId == "fomo") gagne, sinon la liquidité max
    fomo_pairs = [p for p in pairs if p.get("dexId") == "fomo"]
    pool_of = fomo_pairs or pairs
    best = max(pool_of, key=lambda x: (x.get("liquidity") or {}).get("usd", 0))
    mint = best.get("baseToken", {}).get("address")
    return (mint, None) if mint else (None, None)


def top_pool(mint: str) -> str | None:
    d = get(f"{GT}/networks/solana/tokens/{mint}/pools")
    pools = d.get("data", [])
    if not pools:
        return None
    best = max(pools, key=lambda p: fnum(
        p.get("attributes", {}).get("reserve_in_usd")))
    pid = best.get("id", "")
    return pid.split("solana_")[-1] if pid.startswith("solana_") else pid


def store_candles(con: sqlite3.Connection, mint: str, period: str,
                  ohlcv_list: list) -> int:
    n = 0
    for row in ohlcv_list:
        t0, o, h, l, c = row[0], row[1], row[2], row[3], row[4]
        v = row[5] if len(row) > 5 else 0
        if not all(isinstance(x, (int, float)) for x in (t0, o, h, l, c)):
            continue
        cur = con.execute(
            "SELECT 1 FROM fomo_ohlcv WHERE asset=? AND period=? AND time=?",
            (mint, period, int(t0) * 1000)).fetchone()
        if cur:
            continue
        con.execute(
            "INSERT OR REPLACE INTO fomo_ohlcv VALUES (?,?,?,?,?,?,?,?,?)",
            (mint, period, int(t0) * 1000, o, h, l, c, v, time.time()))
        n += 1
    con.commit()
    return n


# le mapping period → (timeframe GT, aggregate GT) : minute n'accepte
# que 1/5/15 — la 1h DOIT passer par ohlcv/hour?aggregate=1 (l'URL
# « minute?aggregate=60 » était rejetée → zéro bougie 1h en silence)
_TF = {"1m": ("minute", 1), "5m": ("minute", 5), "15m": ("minute", 15),
       "1h": ("hour", 1), "4h": ("hour", 4), "1d": ("day", 1)}


def fetch_ohlcv(con: sqlite3.Connection, mint: str, pool: str,
                aggregate: int, period: str, pages: int = 8) -> int:
    total, before = 0, None
    tf, agg = _TF.get(period, ("minute", aggregate))
    for _ in range(pages):
        url = (f"{GT}/networks/solana/pools/{pool}/ohlcv/{tf}"
               f"?aggregate={agg}&limit=1000")
        if before:
            url += f"&before_timestamp={before}"
        try:
            d = get(url)
        except Exception:
            break
        lst = (d.get("data", {}).get("attributes", {}).get("ohlcv_list")
               or [])
        if not lst:
            break
        total += store_candles(con, mint, period, lst)
        before = min(row[0] for row in lst)
        time.sleep(SLEEP)
        if len(lst) < 500:
            break
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="",
                    help="csv de tickers ; défaut = les tickers fomo connus")
    ap.add_argument("--pages", type=int, default=8,
                    help="pages de 1000 bougies par token (1m)")
    ap.add_argument("--mints", default="",
                    help="csv de mints (la résolution inverse : mint → ticker)")
    ap.add_argument("--tickers-file", default="",
                    help="fichier avec un ticker par ligne (l'univers complet)")
    args = ap.parse_args()

    con = sqlite3.connect(DB, timeout=60)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_tokens (
        ticker TEXT PRIMARY KEY, mint TEXT, pool TEXT, resolved_at REAL);
    CREATE TABLE IF NOT EXISTS fomo_ohlcv (
        asset TEXT NOT NULL, period TEXT NOT NULL, time INTEGER NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume REAL,
        captured_at REAL NOT NULL,
        PRIMARY KEY (asset, period, time));
    """)
    con.commit()

    if args.mints:
        mints = [m.strip() for m in args.mints.split(",") if m.strip()]
        con2 = con
        total_m = 0
        for mint in mints:
            tk = resolve_ticker(mint)
            pool = top_pool(mint)
            if tk:
                con.execute(
                    "INSERT OR REPLACE INTO fomo_tokens VALUES (?,?,?,?)",
                    (tk.upper(), mint, pool, time.time()))
            n1m = fetch_ohlcv(con, mint, pool, 1, "1m", args.pages)
            n15 = fetch_ohlcv(con, mint, pool, 15, "15m", 3)
            n1h = fetch_ohlcv(con, mint, pool, 60, "1h", 3)
            total_m += n1m + n15 + n1h
            print(f"[fomo-hist] {tk or mint[:10]} ({mint[:10]}…) : "
                  f"+{n1m + n15 + n1h} bougies")
            time.sleep(SLEEP)
        con.commit()
        con2.close() if False else None
        print(f"[fomo-hist] mode mints terminé : {total_m} bougies")
        con.close()
        return 0
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.tickers_file:
        tf = Path(args.tickers_file)
        tickers = [t.strip().upper() for t in tf.read_text().splitlines()
                   if t.strip() and len(t.strip()) >= 2]
    else:
        # MIGRATION REST (29/09) : fomo_new_coins mort → snapshot REST
        # (fomo_rest.db, endpoints bonding_snapshot + trending, token.symbol).
        # NB : trending.data = LISTE de tokens, bonding_snapshot.data = dict.
        rcon = sqlite3.connect(
            f"file:{ROOT / 'data' / 'fomo' / 'fomo_rest.db'}?mode=ro", uri=True)
        rest_tk = []
        for (raw,) in rcon.execute(
                "SELECT data FROM fomo_rest_snapshots "
                "WHERE endpoint IN ('bonding_snapshot','trending')").fetchall():
            d = json.loads(raw)
            for e in (d if isinstance(d, list) else [d]):
                if not isinstance(e, dict):
                    continue
                sym = (e.get("token") or {}).get("symbol")
                if sym:
                    rest_tk.append(sym)
        rcon.close()
        tickers = sorted(
            {t.upper() for t in rest_tk}
            | {r[0].upper() for r in con.execute(
                "SELECT DISTINCT ticker FROM fomo_positions")})
        tickers = [t for t in tickers if t and len(t) >= 2]

    total = 0
    for tk in tickers:
        try:
            row = con.execute("SELECT mint, pool FROM fomo_tokens WHERE ticker=?",
                              (tk,)).fetchone()
            if row and row[0]:
                mint, pool = row
            else:
                mint, pool = resolve_mint(tk)
                if not mint:
                    print(f"[fomo-hist] {tk} : mint introuvable")
                    continue
                pool = top_pool(mint)
                con.execute(
                    "INSERT OR REPLACE INTO fomo_tokens VALUES (?,?,?,?)",
                    (tk, mint, pool, time.time()))
                con.commit()
                time.sleep(SLEEP)
            if not pool:
                print(f"[fomo-hist] {tk} : pool introuvable")
                continue
            n1m = fetch_ohlcv(con, mint, pool, 1, "1m", args.pages)
            n1h = fetch_ohlcv(con, mint, pool, 60, "1h", 3)
            total += n1m + n1h
            n_now = con.execute(
                "SELECT COUNT(*) FROM fomo_ohlcv WHERE asset=?", (mint,)
            ).fetchone()[0]
            print(f"[fomo-hist] {tk} ({mint[:10]}…) : +{n1m + n1h} bougies, "
                  f"total {n_now}")
        except Exception as e:
            print(f"[fomo-hist] {tk} : ERREUR {e}")
        time.sleep(SLEEP)
    con.close()
    print(f"[fomo-hist] terminé : {total} nouvelles bougies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
