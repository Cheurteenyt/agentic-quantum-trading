#!/usr/bin/env python3
"""Le backfill OHLCV fomo via l'endpoint mobula de l'app (le crack 27/09).

L'app charge l'historique complet d'un token en ~2 s — l'agent a capturé
l'appel exact (data/fomo/getbars_capture_2026-09-27.json) :

GET https://mobula-api.fomo.family/api/2/token/ohlcv-history
    ?address=<mint>&chainId=solana&period=1m&usd=true&from=<ms>&to=<ms>&amount=<n>
    Authorization: Bearer <JWT privy frais du daemon (localStorage, exp ~1h)>

2000 bougies/appel (cap), fenêtre renvoyée = les PLUS RÉCENTES de la
plage → pagination descendante : to = première_bougie - 1 ms.
Le backfill GT (12+ min, 30 appels/min à vie) devient ~2 min pour tout.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DB = ROOT / "data" / "fomo" / "fomo.db"
BASE = "https://mobula-api.fomo.family/api/2/token/ohlcv-history"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
PERIOD_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
             "1h": 3_600_000, "1d": 86_400_000}
CAP = 2000

# les faux mints (devise de cotation/collatéral, jamais des tokens fomo)
QUOTE_MINTS = frozenset({
    "So11111111111111111111111111111111111111112",  # SOL wrappé
    "7vfCXTUXxzBN6xej7ucn7NNvi3orD1vs8HN4cBwpfA2Z",  # WETH Wormhole
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij",  # cbBTC Coinbase
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh",  # WBTC
})


def _jwt_exp(tok: str) -> int:
    """Le exp du payload JWT (0 si indéchiffrable = rejeté)."""
    import base64
    try:
        payload = tok.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload)).get("exp", 0))
    except Exception:
        return 0


_JWT_CACHE = ROOT / "data" / "fomo" / "jwt_cache.json"


def _fresh_jwt_daemon() -> str:
    """Le JWT privy frais du daemon fomo (CDP :9222, localStorage).

    ⚠️ le plus LONG n'est pas le bon : privy:id_token est périmé —
    priorité privy:token puis privy:pat, et exp décodé > maintenant."""
    from patchright.sync_api import sync_playwright
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222",
                                               timeout=8000)
        ctx = browser.contexts[0] if browser.contexts else browser
        page = ctx.new_page()
        try:
            page.goto("https://fomo.family", wait_until="domcontentloaded",
                      timeout=20000)
            page.wait_for_timeout(1500)
        except Exception:
            pass
        vals = page.evaluate(
            "() => Object.entries(localStorage)"
            ".filter(([k, v]) => v && v.length < 5000)")
        page.close()
    finally:
        pw.stop()
    now = time.time()
    cand: dict = {}
    for k, v in vals or []:
        for tok in re.findall(r"eyJhbGciOi[A-Za-z0-9_\-\.]{80,}", str(v)):
            exp = _jwt_exp(tok)
            if exp > now + 60:
                cand.setdefault(k, (exp, tok))
    for key in ("privy:token", "privy:pat"):
        if key in cand:
            return cand[key][1]
    return cand[sorted(cand, key=lambda k: -cand[k][0])[0]][1] if cand else ""


def fresh_jwt(retries: int = 3) -> str:
    """Le JWT frais AVEC résilience : le daemon browser crash et se
    relance en ~15 s (7 restarts au compteur) — retry CDP ×3 puis repli
    sur le cache disque tant que l'exp est valide."""
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            tok = _fresh_jwt_daemon()
            if tok:
                try:
                    _JWT_CACHE.write_text(json.dumps(
                        {"token": tok, "exp": _jwt_exp(tok)}))
                except Exception:
                    pass
                return tok
        except Exception as e:
            last_err = e
        time.sleep(10)
    try:
        d = json.loads(_JWT_CACHE.read_text())
        if d.get("exp", 0) > time.time() + 60:
            print("[mobula] daemon CDP injoignable — JWT du cache (valide)",
                  flush=True)
            return d["token"]
    except Exception:
        pass
    if last_err:
        raise last_err
    return ""


def call(jwt: str, mint: str, period: str, frm: int, to: int,
         amount: int = CAP) -> list:
    q = (f"?address={mint}&chainId=solana&period={period}&usd=true"
         f"&from={frm}&to={to}&amount={amount}")
    req = urllib.request.Request(BASE + q, headers={
        "accept": "*/*", "origin": "https://fomo.family",
        "referer": "https://fomo.family/", "user-agent": UA,
        "authorization": f"Bearer {jwt}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r).get("data") or []
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(20.0 * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2.0)
    return []


def rows_to_candles(rows: list) -> list:
    """Le format de ligne mobula : listes [t(ms), o, h, l, c, v] (vu en
    capture) — le dict accepté par prudence pour un changement d'API."""
    out = []
    for row in rows:
        if isinstance(row, list) and len(row) >= 5:
            t, o, h, l, c = row[0], row[1], row[2], row[3], row[4]
            v = row[5] if len(row) > 5 else 0
        elif isinstance(row, dict):
            t = row.get("t") or row.get("time")
            o = row.get("o", row.get("open"))
            h = row.get("h", row.get("high"))
            l = row.get("l", row.get("low"))
            c = row.get("c", row.get("close"))
            v = row.get("v", row.get("volume", 0))
        else:
            continue
        if not all(isinstance(x, (int, float)) for x in (t, o, h, l, c)):
            continue
        out.append((int(t), float(o), float(h), float(l), float(c),
                    float(v or 0)))
    return out


def backfill_period(con: sqlite3.Connection, jwt: str, mint: str,
                    period: str, pages: int = 15) -> int:
    """Paginé descendant : chaque page = les 2000 plus récentes sous le
    `to` courant ; commit par page (une transaction fantôme = tout perdu)."""
    to = int(time.time() * 1000)
    total = 0
    prev_min: int | None = None
    for _ in range(pages):
        rows = call(jwt, mint, period, 0, to)
        candles = rows_to_candles(rows)
        if not candles:
            break
        con.executemany(
            "INSERT OR REPLACE INTO fomo_ohlcv VALUES (?,?,?,?,?,?,?,?,?)",
            [(mint, period, t, o, h, l, c, v, time.time())
             for t, o, h, l, c, v in candles])
        con.commit()
        if prev_min is not None:
            total += sum(1 for t, *_ in candles if t < prev_min)
        else:
            total += len(candles)
        prev_min = min(t for t, *_ in candles)
        if len(candles) < CAP:
            break
        new_to = prev_min - 1
        if new_to >= to:
            # l'API ignore `to` (earliest ne descend pas) : les pages suivantes
            # seraient les mêmes 2000 bougies re-upsertées et comptées en double
            print(f"  pagination bloquée à to={new_to} (earliest ne descend plus)",
                  flush=True)
            break
        to = new_to
        time.sleep(0.3)
    return total


def token_list(con: sqlite3.Connection) -> list:
    mints = {r[0] for r in con.execute("SELECT DISTINCT asset FROM fomo_ohlcv")}
    mints |= {r[0] for r in con.execute("SELECT mint FROM fomo_tokens")}
    return sorted(m for m in mints
                  if m and not m.startswith("0x") and m not in QUOTE_MINTS
                  and len(m) >= 32)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="tous les mints connus")
    ap.add_argument("--mints", type=str, default="",
                    help="mints séparés par des virgules")
    ap.add_argument("--periods", type=str, default="1m,15m,1h")
    ap.add_argument("--pages", type=int, default=15)
    ap.add_argument("--no-stop", action="store_true",
                    help="laisser le tick collector tourner (risque de lock)")
    args = ap.parse_args()
    periods = [p.strip() for p in args.periods.split(",") if p.strip()]
    for p in periods:
        if p not in PERIOD_MS:
            print(f"période inconnue : {p}")
            return 1

    import subprocess
    stopped = False
    if not args.no_stop:
        # fenêtre exclusive comme fomo_master_backfill : le timer top-up tire
        # toutes les 15 min (passe ~93s) — sans ce stop, 2 écrivains lourds
        # se croisent sur fomo.db pendant un backfill de 25+ min
        subprocess.run(["systemctl", "--user", "stop",
                        "fomo-tick-collector.service",
                        "fomo-mobula-topup.timer",
                        "fomo-mobula-topup.service"], capture_output=True)
        for _ in range(15):
            r = subprocess.run(["systemctl", "--user", "is-active",
                                "fomo-tick-collector.service"],
                               capture_output=True, text=True)
            if r.stdout.strip() != "active":
                stopped = True
                break
            time.sleep(2)
        if not stopped:
            print("ERREUR : le tick collector refuse de s'arrêter — abort")
            subprocess.run(["systemctl", "--user", "start",
                            "fomo-tick-collector.service"], capture_output=True)
            return 1
    try:
        con = sqlite3.connect(DB, timeout=30)
        con.execute("PRAGMA busy_timeout=30000")
        mints = (token_list(con) if args.all
                 else [m.strip() for m in args.mints.split(",") if m.strip()])
        print(f"[mobula] {len(mints)} mints × {periods} — JWT frais…",
              flush=True)
        jwt = fresh_jwt()
        if not jwt:
            print("ERREUR : aucun JWT frais dans le localStorage du daemon")
            return 1
        t0, tot = time.time(), 0
        for i, mint in enumerate(mints):
            n_tok = 0
            for p in periods:
                try:
                    n_tok += backfill_period(con, jwt, mint, p, args.pages)
                except Exception as e:
                    print(f"  ERR {mint[:10]}… {p} : {e}", flush=True)
            tot += n_tok
            print(f"  [{i+1}/{len(mints)}] {mint[:10]}… : +{n_tok} bougies",
                  flush=True)
        print(f"[mobula] TERMINÉ : {tot} bougies en {time.time()-t0:.0f}s",
              flush=True)
    finally:
        if not args.no_stop:
            subprocess.run(["systemctl", "--user", "start",
                            "fomo-tick-collector.service"], capture_output=True)
            subprocess.run(["systemctl", "--user", "start",
                            "fomo-mobula-topup.timer"], capture_output=True)
            print("collector + top-up timer relancés", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
