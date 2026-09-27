#!/usr/bin/env python3
"""La boucle bonding : tickers fomo_new_coins(tab='bonding') → mints → OHLCV mobula.

Résolution ticker→mint (les tickers fomo NE sont PAS uniques) :
  (a) prod-api : PROBÉ le 27/09 — filterTokensSearch/trendingTokens = 404,
      filterTokens POST = enrichissement par ADRESSE (array de strings),
      pas de search par ticker → chemin mort, documenté ici ;
  (b) le CDP fetch reste le transport (REST Python = 430 Cloudflare) ;
  (c) DexScreener search avec le désambiguïseur éprouvé (fomo_history_
      collector) : dexId=='fomo' (le token NATIF) gagne, sinon recence +
      liquidité max — un vieux token raydium 2024 du même ticker = un faux.
Le mint choisi → fomo_tokens (pool = pairAddress), puis backfill mobula
1m×6 + 15m×3 + 1h×3 (la vie complète du token SUR la courbe).
Le tick collector n'est PAS arrêté (interdit) : busy_timeout + commit/mint.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "fomo" / "fomo.db"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


def bonding_tickers(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute(
        """SELECT n.ticker, n.bonding_pct, n.mc, n.captured_at
           FROM fomo_new_coins n
           JOIN (SELECT ticker, MAX(captured_at) m FROM fomo_new_coins
                 WHERE tab='bonding' GROUP BY ticker) x
             ON x.ticker=n.ticker AND x.m=n.captured_at
           WHERE n.tab='bonding' ORDER BY n.bonding_pct DESC""").fetchall()
    return [{"ticker": t, "bonding_pct": b, "mc": mc} for t, b, mc, _ in rows]


def dexscreener_pairs(ticker: str) -> list[dict]:
    t = ticker.lstrip("$")
    req = urllib.request.Request(
        f"https://api.dexscreener.com/latest/dex/search?q={t}",
        headers={"user-agent": UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get("pairs") or []


def pick_fomo_pair(pairs: list[dict], ticker: str) -> dict | None:
    """Le désambiguïseur : base OU quote fomo (le token peut être en quote
    de sa propre paire fomo). Score : dexId=='fomo' > dex ON-COURBE
    (pumpfun/meteoradbc, liq=0 = sur la courbe) > liquidité max. Une paire
    SANS pairCreatedAt d'un dex à pool = faux jumeau non datable."""
    t = ticker.lstrip("$").upper()
    on_curve = ("pumpfun", "meteoradbc", "fomo")
    base = [p for p in pairs if p.get("chainId") == "solana" and
            str((p.get("baseToken") or {}).get("symbol", "")).upper() == t]
    quote = [p for p in pairs if p.get("chainId") == "solana" and
             str((p.get("quoteToken") or {}).get("symbol", "")).upper() == t]
    for cands in (base, quote):
        if not cands:
            continue
        dated = [p for p in cands
                 if p.get("pairCreatedAt")
                 or p.get("dexId") in on_curve]
        pool = dated or []
        if not pool:
            continue

        def score(x: dict):
            liq = (x.get("liquidity") or {}).get("usd", 0) or 0
            rank = (2 if x.get("dexId") == "fomo"
                    else 1 if x.get("dexId") == "pumpfun"
                    else 0)
            return (rank, liq)

        return max(pool, key=score)
    return None


def resolve_dexscreener(ticker: str, max_age_s: float = 14 * 86400) -> dict | None:
    try:
        pairs = dexscreener_pairs(ticker)
    except Exception as e:
        print(f"    [{ticker}] dexscreener err {type(e).__name__}", flush=True)
        return None
    p = pick_fomo_pair(pairs, ticker)
    if not p:
        return None
    is_quote = str((p.get("quoteToken") or {}).get("symbol", "")).upper() \
        == ticker.lstrip("$").upper()
    bt = p.get("quoteToken") if is_quote else p.get("baseToken")
    age = p.get("pairCreatedAt") or 0
    if age and age < (time.time() - max_age_s) * 1000:
        print(f"    [{ticker}] paire trop vieille "
              f"({int((time.time()*1000-age)/86400000)}j) = faux jumeau",
              flush=True)
        return None
    return {"mint": bt.get("address", ""), "symbol": bt.get("symbol", ""),
            "pool": p.get("pairAddress") or "",
            "dex": p.get("dexId"),
            "liq_usd": (p.get("liquidity") or {}).get("usd"),
            "created": age / 1000 if age else None}


def main() -> int:
    from scripts.fomo_ohlcv_backfill import backfill_period, fresh_jwt
    con = sqlite3.connect(DB, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    tickers = bonding_tickers(con)
    print(f"[bonding] N tickers distincts tab=bonding : {len(tickers)}",
          flush=True)
    known = {r[0]: r[1] for r in
             con.execute("SELECT ticker, mint FROM fomo_tokens")}

    resolved: dict[str, dict] = {}
    failed: list[tuple[str, str]] = []
    for i, x in enumerate(tickers):
        tk = x["ticker"]
        if tk in known:
            resolved[tk] = {"mint": known[tk], "source": "cache fomo_tokens"}
            continue
        r = resolve_dexscreener(tk)
        if not r or not r["mint"]:
            failed.append((tk, "pas de paire fomo/recence DexScreener"))
            continue
        con.execute("INSERT OR REPLACE INTO fomo_tokens VALUES (?,?,?,?)",
                    (tk, r["mint"], r["pool"] or None, time.time()))
        con.commit()
        resolved[tk] = {"mint": r["mint"], "source": "dexscreener",
                        "dex": r["dex"], "liq_usd": r["liq_usd"]}
        print(f"  [{i+1}/{len(tickers)}] {tk} ({x['bonding_pct']}%) -> "
              f"{r['mint'][:12]}… dex={r['dex']} liq=${r['liq_usd'] or 0:.0f}",
              flush=True)
        time.sleep(0.8)

    # le backfill mobula : 1m×6 + 15m×3 + 1h×3 par mint (commit par mint)
    jwt = fresh_jwt()
    if not jwt:
        print("ERREUR : pas de JWT mobula — résolution sauvegardée", flush=True)
        (ROOT / "data" / "fomo" / "bonding_resolution.json").write_text(
            json.dumps({"resolved": resolved, "failed": failed}, indent=1))
        return 1
    plan = (("1m", 6), ("15m", 3), ("1h", 3))
    total_candles = 0
    per_token: dict[str, int] = {}
    for tk, info in resolved.items():
        mint, n_tok = info["mint"], 0
        for period, pages in plan:
            try:
                n_tok += backfill_period(con, jwt, mint, period, pages)
            except Exception as e:
                print(f"    [{tk}] {period} err {type(e).__name__} "
                      f"{str(e)[:60]}", flush=True)
            time.sleep(1.2)
        per_token[tk] = n_tok
        total_candles += n_tok
        print(f"  [bf] {tk}: {n_tok} bougies", flush=True)

    (ROOT / "data" / "fomo" / "bonding_resolution.json").write_text(
        json.dumps({"resolved": resolved, "failed": failed,
                    "per_token_candles": per_token,
                    "total_candles": total_candles}, indent=1))
    print(f"[bilan] résolus {len(resolved)}/{len(tickers)} ; échecs "
          f"{len(failed)} ; backfillés {len(per_token)} ; bougies "
          f"{total_candles}", flush=True)
    for tk, why in failed:
        print(f"  ECHEC {tk}: {why}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
