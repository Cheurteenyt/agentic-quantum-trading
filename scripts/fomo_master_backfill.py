#!/usr/bin/env python
"""LE BACKFILL MAÎTRE fomo — la passe complète : chaque mint → ticker →
historique profond → le rapport de couverture.

La garantie de fiabilité :
  - reprise sur interruption : les bougies existantes sont sautées
  - les rate-limits GT respectés (le 429 → 65s, les sleeps entre les calls)
  - chaque token : la résolution ticker (DexScreener) + l'OHLCV 1m/15m/1h
  - le rapport de couverture : les bougies, la plage, les trous par token

  .venv/bin/python scripts/fomo_master_backfill.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import fomo_history_collector as fc  # noqa: E402
from scripts import fomo_ohlcv_backfill as mob  # noqa: E402

REPORTS = ROOT / "reports"


# les actifs de cotation/collatéral : jamais des tokens fomo
QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",  # SOL wrappé
    "7vfCXTUXxzBN6xej7ucn7NNvi3orD1vs8HN4cBwpfA2Z",  # WETH Wormhole
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",  # cbBTC Coinbase
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC
})


def main() -> int:
    import subprocess
    # la fenêtre exclusive : le tick collector 24/7 stoppé pendant la passe
    subprocess.run(["systemctl", "--user", "stop",
                    "fomo-tick-collector.service",
                    "fomo-mobula-topup.timer",
                    "fomo-mobula-topup.service"], capture_output=True)
    # l'arrêt VÉRIFIÉ : on attend l'inactivité réelle (max 30s) — un stop
    # non vérifié = le collector écrit encore = « database is locked »
    stopped = False
    for _ in range(15):
        r = subprocess.run(["systemctl", "--user", "is-active",
                            "fomo-tick-collector.service"],
                           capture_output=True, text=True)
        if r.stdout.strip() != "active":
            stopped = True
            break
        time.sleep(2)
    if not stopped:
        print("[master] ERREUR : le tick collector refuse de s'arrêter — abort",
              flush=True)
        return 1
    time.sleep(3)
    try:
        return _run()
    finally:
        subprocess.run(["systemctl", "--user", "start",
                        "fomo-tick-collector.service"], capture_output=True)
        subprocess.run(["systemctl", "--user", "start",
                        "fomo-mobula-topup.timer"], capture_output=True)
        print("[master] tick collector + top-up timer relancés", flush=True)


def _run() -> int:
    con = sqlite3.connect(fc.DB, timeout=30)
    for attempt in range(6):                 # le verrou : le tick 24/7 écrit toutes les 30s
        try:
            con.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError:
            print(f"[master] base verrouillée, attente {attempt+1}/6…", flush=True)
            time.sleep(15)
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

    mints = [r[0] for r in con.execute(
        "SELECT DISTINCT asset FROM fomo_ohlcv ORDER BY asset")]
    _n0 = len(mints)
    mints = [m for m in mints
             if not m.startswith("0x")
             and m not in QUOTE_MINTS
             and len(m) >= 32]
    if len(mints) < _n0:
        print(f"[master] {_n0 - len(mints)} faux mints filtrés (SOL wrappé/EVM)",
              flush=True)
    print(f"[master] {len(mints)} mints à traiter", flush=True)

    jwt = mob.fresh_jwt()
    if not jwt:
        print("[master] pas de JWT mobula — repli GT intégral",
              flush=True)
    coverage = []
    t0 = time.time()
    skipped = 0
    for idx, mint in enumerate(mints):
        try:
            # le TOP-UP SÉLECTIF : un token frais (15m < 2h) et déjà profond
            # = skip — le budget GT (30 appels/min) va aux nouveaux/secs.
            # Sans ça, chaque passe re-télécharge 35 vies complètes = 30 min.
            _row = con.execute(
                "SELECT MAX(time), COUNT(*) FROM fomo_ohlcv "
                "WHERE asset=? AND period='15m'", (mint,)).fetchone()
            _last, _n15 = (_row[0] or 0), _row[1] or 0
            if _last and _n15 >= 100 and (time.time() - _last / 1000) < 7200:
                skipped += 1
                continue
            # le ticker : le mapping existant ou DexScreener
            tk_row = con.execute("SELECT ticker FROM fomo_tokens WHERE mint=?",
                                 (mint,)).fetchone()
            ticker = tk_row[0] if tk_row else (fc.resolve_ticker(mint) or mint[:10])
            pool_row = con.execute("SELECT pool FROM fomo_tokens WHERE mint=?",
                                   (mint,)).fetchone()
            pool = pool_row[0] if pool_row else fc.top_pool(mint)
            if not pool:
                coverage.append({"mint": mint, "ticker": ticker,
                                 "status": "pas de pool"})
                continue
            con.execute("INSERT OR REPLACE INTO fomo_tokens VALUES (?,?,?,?)",
                        (ticker.upper(), mint, pool, time.time()))
            con.commit()

            # l'OHLCV profond : MOBULA d'abord (l'endpoint du chart de
            # l'app, 2000 bougies/appel — 347k bougies en 2 min au 1er run,
            # la profondeur remonte 16 mois avant GT), GT en repli.
            n1m = n15 = n1h = 0
            if jwt:
                try:
                    n1m = mob.backfill_period(con, jwt, mint, "1m", 6)
                    n15 = mob.backfill_period(con, jwt, mint, "15m", 3)
                    n1h = mob.backfill_period(con, jwt, mint, "1h", 3)
                except Exception:
                    n1m = n15 = n1h = 0
            if not (n1m or n15 or n1h):
                n1m = fc.fetch_ohlcv(con, mint, pool, 1, "1m", 6)
                n15 = fc.fetch_ohlcv(con, mint, pool, 15, "15m", 3)
                n1h = fc.fetch_ohlcv(con, mint, pool, 60, "1h", 3)
            tot = con.execute(
                "SELECT COUNT(*), datetime(MIN(time)/1000,'unixepoch'), "
                "datetime(MAX(time)/1000,'unixepoch') FROM fomo_ohlcv "
                "WHERE asset=? AND period='1m'", (mint,)).fetchone()
            coverage.append({"mint": mint, "ticker": ticker, "status": "ok",
                             "candles_1m": tot[0], "range": f"{tot[1]} → {tot[2]}"})
            print(f"[master] {idx+1}/{len(mints)} {ticker} ({mint[:10]}…) : "
                  f"+1m {tot[0]}, +15m {n15}, +1h {n1h}", flush=True)
        except Exception as e:
            coverage.append({"mint": mint, "status": f"ERREUR {e}"})
            print(f"[master] {mint[:10]}… : ERREUR {e}", flush=True)
        time.sleep(fc.SLEEP)

    con.close()

    ok = [c for c in coverage if c.get("status") == "ok"]
    total_candles = sum(c.get("candles_1m", 0) for c in ok)
    lines = [
        "# LE BACKFILL MAÎTRE fomo — le rapport de couverture",
        f"{datetime.now(timezone.utc):%d/%m/%Y %H:%M} UTC — "
        f"{len(mints)} mints traités en {time.time()-t0:.0f}s.", "",
        f"| Statut | Tokens | Bougies 1m cumulées |",
        f"|---|---|---|",
        f"| OK | {len(ok)} | {total_candles:,} |",
        f"| Erreur/pas de pool | {len(mints) - len(ok)} | — |", "",
        "| Token | Mint | Bougies 1m | Plage |", "|---|---|---|---|",
    ]
    for c in sorted(coverage, key=lambda x: -x.get("candles_1m", 0)):
        tk = c.get("ticker", c["mint"][:10])
        if c.get("status") == "ok":
            lines.append(f"| {tk} | {c['mint'][:14]}… "
                         f"| {c['candles_1m']:,} | {c['range']} |")
        else:
            lines.append(f"| {tk} | {c['mint'][:14]}… | — | {c['status']} |")

    out = REPORTS / f"master-backfill-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    REPORTS.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[master] {len(ok)}/{len(mints)} tokens avec l'historique ({skipped} frais skippés), "
          f"{total_candles:,} bougies 1m cumulées → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
