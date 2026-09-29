#!/usr/bin/env python3
"""SONDE REST derek518 (29/09) — preuve avant re-câblage de derek_watch.
One-shot LECTURE SEULE : handle → uuid via /v2/users/userHandle/<handle>,
puis /v2/users/<uuid>/swaps?limit=100, comparé au ledger fomo_swaps.db
(_swaps_meta + fomo_swaps) et au ledger paper (fomo_paper_trades.swap_id).
Recette : curl_cffi impersonate chrome131 + Bearer (le plus frais des 2
caches JWT, gate exp > now+600 — jamais de re-auth forcée), pacing 1 s.
Aucune écriture (DB en mode=ro)."""
import json
import sqlite3
import sys
import time
from pathlib import Path

from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://prod-api.fomo.family"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
HANDLES = ["derek518"]           # variantes : grep repo → derek518 seul connu
SWAPS_DB = ROOT / "data" / "fomo" / "fomo_swaps.db"
PAPER_DB = ROOT / "data" / "fomo" / "fomo_paper.db"


def read_jwt(margin: int = 600):
    """Le plus frais des 2 caches, gate exp > now+600 (jamais de refresh)."""
    best, best_exp, src = None, 0, None
    for p, name in ((ROOT / "data/fomo/ws_jwt_cache.txt", "ws_jwt_cache.txt"),
                    (ROOT / "data/fomo/jwt_cache.json", "jwt_cache.json")):
        try:
            raw = p.read_text().strip()
            jwt = (json.loads(raw).get("jwt") or json.loads(raw).get("token")
                   if raw.startswith("{") else raw.strip('"'))
            pl = jwt.split(".")[1]
            pl += "=" * (-len(pl) % 4)
            e = json.loads(__import__("base64").urlsafe_b64decode(pl)).get("exp", 0)
            if e > best_exp:
                best, best_exp, src = jwt, e, name
        except Exception:
            continue
    if not best or best_exp <= time.time() + margin:
        return None, best_exp, src
    return best, best_exp, src


def get(cli_h, path):
    r = cffi.get(BASE + path, headers=cli_h, impersonate="chrome131", timeout=15)
    time.sleep(1.0)  # pacing ≥ 1 s
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json")
                           else r.text[:200])


def main() -> int:
    jwt, exp, src = read_jwt()
    if not jwt:
        print(f"BLOCKAGE JWT : le plus frais ({src}) exp={exp} "
              f"reste {exp - time.time():.0f}s < marge 600s — pas de re-auth forcée")
        return 1
    print(f"JWT ok : {src} exp dans {exp - time.time():.0f}s")
    h = {"user-agent": UA, "authorization": f"Bearer {jwt}",
         "origin": "https://fomo.family", "referer": "https://fomo.family/"}

    # 1. handle → uuid (derek518 + variantes connues du repo : aucune autre)
    uid = None
    for handle in HANDLES:
        st, d = get(h, f"/v2/users/userHandle/{handle}")
        ro = d.get("responseObject") if isinstance(d, dict) else None
        cand = (ro.get("id") or (ro.get("user") or {}).get("id")) \
            if isinstance(ro, dict) else None
        print(f"RESOLVE {handle}: HTTP {st} → id={cand}")
        if st == 200 and cand:
            uid = cand
        else:
            print(f"  corps: {json.dumps(d)[:300]}")
    if not uid:
        print("BLOCKAGE : handle introuvable")
        return 1

    # 2. les 100 derniers swaps REST
    st, d = get(h, f"/v2/users/{uid}/swaps?limit=100")
    ro = d.get("responseObject") if isinstance(d, dict) else {}
    swaps = (ro or {}).get("swaps") or (d.get("swaps") if isinstance(d, dict) else None) or []
    print(f"SWAPS: HTTP {st} n={len(swaps)} hasNextPage={(ro or {}).get('hasNextPage')}")
    if not swaps:
        print(f"  corps: {json.dumps(d)[:400]}")
        return 1
    rest = {s.get("id"): s for s in swaps if isinstance(s, dict) and s.get("id")}
    newest = max((s.get("createdAt") or "") for s in rest.values())
    print(f"  newest createdAt REST = {newest}")

    # 3. comparaison ledgers (lectures ro)
    con = sqlite3.connect(f"file:{SWAPS_DB}?mode=ro", uri=True, timeout=30)
    led = dict(con.execute(
        "SELECT swap_id, ts FROM fomo_swaps WHERE user_id=?", (uid,)).fetchall())
    meta = con.execute("SELECT user_id FROM _swaps_meta WHERE handle='derek518'",
                       ).fetchone()
    con.close()
    common = sorted(set(rest) & set(led))
    print(f"LEDGER fomo_swaps.db: uid_cache={meta[0] if meta else None} "
          f"match_uuid={bool(meta and meta[0] == uid)} n_ledger={len(led)} "
          f"| chevauchement REST∩ledger = {len(common)}/{len(rest)}")
    if common:
        dts = [rest[i].get("createdAt") for i in common[:3]]
        print(f"  ids communs ex: {common[0][:14]}… created {dts[0]}")
    print(f"  NOUVEAUX (absents ledger) = {len(rest) - len(common)}")

    con = sqlite3.connect(f"file:{PAPER_DB}?mode=ro", uri=True, timeout=30)
    paper = {r[0] for r in con.execute(
        "SELECT swap_id FROM fomo_paper_trades WHERE swap_id IS NOT NULL")}
    last_ts = con.execute("SELECT value FROM fomo_paper_state "
                          "WHERE key='derek_last_ts'").fetchone()
    con.close()
    print(f"PAPER fomo_paper.db: n_paper_swap_ids={len(paper)} "
          f"derek_last_ts={last_ts[0] if last_ts else None} "
          f"| REST∩paper = {len(set(rest) & paper)}")
    # cohérence de parse sur les ids communs (side/size) : quote en entrée = buy
    QUOTE = frozenset({"So11111111111111111111111111111111111111112",
                       "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                       "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"})
    ok = bad = 0
    for i in common[:40]:
        s = rest[i]
        it, ot = s.get("inTokenAddress"), s.get("outTokenAddress")
        side = "buy" if (it in QUOTE and ot not in QUOTE) else \
               "sell" if (ot in QUOTE and it not in QUOTE) else None
        ok += 1 if side else 0
        bad += 0 if side else 1
    print(f"PARSE contrôle sur {min(40, len(common))} communs: "
          f"side déterminé={ok}, indéterminé={bad}")
    print("VERDICT : " + ("PREUVE OK" if len(common) else "PAS de chevauchement"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
