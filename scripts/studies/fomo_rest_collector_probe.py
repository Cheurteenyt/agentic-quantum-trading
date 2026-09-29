#!/usr/bin/env python3
"""SONDE one-shot (29/09 soir) : formes de réponse des 6 NOUVELLES surfaces
avant intégration dans fomo_rest_collector.py. Aucune écriture DB.
Zéro appel superflu : mints et uid élite lus depuis fomo_rest.db (mode=ro).
Lecture seule partout — ne tourne JAMAIS en même temps qu'une passe collector.
"""
import json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # scripts/studies/x.py → racine
sys.path.insert(0, str(ROOT / "scripts"))
from fomo_rest_collector import Client, read_jwt, refresh_jwt_via_cdp, NETWORK_ID  # noqa: E402

REST_DB = ROOT / "data" / "fomo" / "fomo_rest.db"


def shape(tag, obj, depth=2):
    def sh(o, d):
        if isinstance(o, dict):
            if d <= 0:
                return f"dict[{len(o)}]"
            return {k: sh(v, d - 1) for k, v in list(o.items())[:12]}
        if isinstance(o, list):
            return f"list[{len(o)}]" + ("" if not o else " of " + json.dumps(sh(o[0], d - 1), default=str)[:300])
        return type(o).__name__
    print(f"== {tag} ==\n{json.dumps(sh(obj, depth), default=str)[:1200]}\n")


def main() -> int:
    jwt = read_jwt() or refresh_jwt_via_cdp()
    if not jwt:
        print("JWT indisponible")
        return 1
    cli = Client(jwt)
    ro = sqlite3.connect(f"file:{REST_DB}?mode=ro", uri=True)
    mints = json.loads(ro.execute("SELECT data FROM fomo_rest_snapshots WHERE endpoint='trending' AND entity_id='latest'").fetchone()[0])
    mints = [((t.get("token") or {}).get("address")) for t in mints[:6] if isinstance(t, dict)]
    uid = ro.execute("SELECT entity_id FROM fomo_rest_snapshots WHERE endpoint LIKE 'cursor_swaps%' LIMIT 1").fetchone()[0]
    ro.close()
    print(f"mints={mints[:3]}... uid={uid}\n")

    try:
        shape("verifiedTokens", cli.get("/proxy/verifiedTokens"), 2)
    except Exception as e:
        print(f"verifiedTokens ERR {e}\n")
    try:
        shape("leaderboard alltime", cli.get("/v2/leaderboard?window=alltime&limit=100"), 2)
    except Exception as e:
        print(f"leaderboard alltime ERR {e}\n")
    try:
        shape("tradingActivity", cli.get("/feed/tradingActivity?limit=50&threshold=1000"), 2)
        if mints:
            shape("tradingActivity +tokenAddress", cli.get(
                f"/feed/tradingActivity?limit=5&threshold=1000&tokenAddress={mints[0]}"), 2)
    except Exception as e:
        print(f"tradingActivity ERR {e}\n")
    try:
        body = [f"{m}:{NETWORK_ID}" for m in mints[:3]]
        shape(f"filterTokens body={body}", cli.post("/proxy/filterTokens", body), 2)
    except Exception as e:
        print(f"filterTokens ERR {e}\n")
    try:
        shape("v2/users/<uid>", cli.get(f"/v2/users/{uid}"), 1)
        shape("v2/users/<uid>/balances", cli.get(f"/v2/users/{uid}/balances"), 1)
        shape("v2/users/<uid>/leaderboard", cli.get(f"/v2/users/{uid}/leaderboard"), 1)
        shape("aggregatedSnapshotById", cli.get(f"/v2/userTokens/aggregatedSnapshotById?userId={uid}"), 1)
    except Exception as e:
        print(f"profils ERR {e}\n")
    print(f"[probe] {cli.n} appels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
