#!/usr/bin/env python3
"""La question qui vaut les ×1000 : mobula inclut-il la phase BONDING ?

Méthode : pour 6-8 tokens variés (2 très anciens, 2 moyens, 2 récents,
+ les plus gros de fomo_ohlcv), on compare
  - pool_created_at (GT : api.geckoterminal.com …/pools/<pool>)
  - MIN(time) des bougies mobula déjà en DB (1m et 1h).
Si mobula_first_candle < pool_created_at de façon systématique → la phase
bonding (AVANT la création du pool, là où se jouent les ×10-×100) est
COUVERTE → les ×1000 redeviennent backtestables.

GT free tier = 30 appels/min → SLEEP 2.1s, cooldown 65s sur 429.
Lecture seule sur fomo.db (top-up éventuellement en parallèle : WAL).
Rapport : reports/fomo-bonding-coverage-YYYY-MM-DD.md
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fomo" / "fomo.db"
GT = "https://api.geckoterminal.com/api/v2/networks/solana/pools/{}"

INTEL = [
    ("2 très anciens", "SELECT ticker, mint, pool, resolved_at FROM fomo_tokens "
                       "WHERE pool IS NOT NULL AND pool != '' "
                       "ORDER BY resolved_at ASC LIMIT 2"),
    ("2 moyens", "SELECT ticker, mint, pool, resolved_at FROM fomo_tokens "
                 "WHERE pool IS NOT NULL AND pool != '' "
                 "ORDER BY resolved_at ASC LIMIT 2 OFFSET "
                 "(SELECT COUNT(*)/2 FROM fomo_tokens)"),
    ("2 récents", "SELECT ticker, mint, pool, resolved_at FROM fomo_tokens "
                  "WHERE pool IS NOT NULL AND pool != '' "
                  "ORDER BY resolved_at DESC LIMIT 2"),
    ("2 gros ohlcv", "SELECT t.ticker, t.mint, t.pool, t.resolved_at "
                     "FROM fomo_tokens t JOIN fomo_ohlcv o ON o.asset = t.mint "
                     "WHERE t.pool IS NOT NULL AND t.pool != '' "
                     "GROUP BY t.ticker ORDER BY COUNT(*) DESC LIMIT 2"),
]


def gt_pool_created_at(pool: str) -> str:
    """pool_created_at (ISO) via GT ; 429 → cooldown 65s (free tier)."""
    req = urllib.request.Request(GT.format(pool), headers={"accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)["data"]["attributes"]["pool_created_at"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                print("  GT 429 → cooldown 65s", flush=True)
                time.sleep(65)
                continue
            raise
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3)
    raise RuntimeError("GT indisponible")


QUOTE_TICKERS = frozenset({
    "weth", "cbbtc", "wbtc", "sol", "wsol", "usdc", "usdt", "usds", "jupsol"})


def verdict_for(created_ms: int | None, first1m: int | None,
                first1h: int | None, now_ms: int) -> tuple[str, bool]:
    """(verdict, couvert) — un vieux token dont même la 1h ne redescend
    pas jusqu'au pool = profondeur de backfill, pas un trou mobula."""
    if not created_ms or not first1m:
        return "données manquantes", False
    if first1m <= created_ms:
        return "COUVERT (bonding inclus)", True
    if first1h and first1h > created_ms and now_ms - created_ms > 60 * 86400_000:
        return "inconclusif (profondeur backfill 1h épuisée)", False
    if first1h and first1h <= created_ms:
        return "PAS couvert en 1m (1h couvre)", False
    return "PAS couvert (après pool)", False


def iso_ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00"))
               .timestamp() * 1000)


def fmt_ms(ms: int | None) -> str:
    if not ms:
        return "n/a"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    picked: dict[str, tuple] = {}
    for label, sql in INTEL:
        for row in con.execute(sql):
            picked.setdefault(row[0], (row[1], row[2], label))
    tokens = sorted(picked.items(), key=lambda kv: kv[1][2])
    print(f"[bonding] {len(tokens)} tokens sélectionnés", flush=True)

    lines, n_covered, n_pas = [], 0, 0
    now_ms = int(time.time() * 1000)
    for ticker, (mint, pool, label) in tokens:
        if ticker.lstrip("$").lower() in QUOTE_TICKERS:
            print(f"  {ticker}: collatéral/quote — exclu du test", flush=True)
            continue
        first = {}
        for period in ("1m", "1h"):
            r = con.execute("SELECT MIN(time) FROM fomo_ohlcv "
                            "WHERE asset=? AND period=?", (mint, period)).fetchone()
            first[period] = r[0] if r else None
        try:
            created_iso = gt_pool_created_at(pool)
            created_ms = iso_ms(created_iso)
        except Exception as e:
            print(f"  {ticker}: GT échec ({e})", flush=True)
            created_iso, created_ms = f"ERREUR: {e}", None
        time.sleep(2.1)  # GT free tier 30/min
        verdict, covered = verdict_for(created_ms, first["1m"],
                                       first["1h"], now_ms)
        n_covered += covered
        if verdict.startswith("PAS couvert"):
            n_pas += 1
        lines.append((ticker, label, created_iso, created_ms, first, verdict))
        print(f"  {ticker:12s} pool={fmt_ms(created_ms)} | 1m={fmt_ms(first['1m'])} "
              f"| 1h={fmt_ms(first['1h'])} | {verdict}", flush=True)

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = ROOT / "reports" / f"fomo-bonding-coverage-{date}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    verdict_global = ("COUVERT — la phase bonding EST dans mobula"
                      if n_pas == 0 and n_covered
                      else f"PARTIEL : {n_covered}/{len(lines)} couverts"
                      if n_covered else "PAS COUVERT")
    with open(out, "w") as f:
        f.write(f"# Couverture phase bonding — mobula vs GT ({date})\n\n"
                f"Question : mobula inclut-il les bougies AVANT la création du pool "
                f"(phase bonding, là où se jouent les ×10-×100) ?\n\n"
                f"Source GT : `GET api.geckoterminal.com/api/v2/networks/solana/pools/<pool>` "
                f"→ `attributes.pool_created_at`. Source bougies : `MIN(time)` de "
                f"`fomo_ohlcv` (backfill mobula du {date}).\n\n"
                f"| ticker | profil | pool_created_at (GT) | 1re bougie 1m | 1re bougie 1h | verdict |\n"
                f"|---|---|---|---|---|---|\n")
        for ticker, label, cis, cms, first, verdict in lines:
            f.write(f"| {ticker} | {label} | {cis} | {fmt_ms(first['1m'])} | "
                    f"{fmt_ms(first['1h'])} | {verdict} |\n")
        f.write(f"\n## Verdict global : **{verdict_global}** ({n_covered}/{len(lines)} "
                f"tokens avec 1re bougie 1m < pool_created_at)\n\n")
        if n_covered == len(lines):
            f.write("Les ×10-×100 de la phase bonding sont backtestables : le backfill "
                    "mobula couvre la vie complète du token, bonding comprise.\n")
    print(f"[bonding] {verdict_global} → rapport : {out}", flush=True)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
