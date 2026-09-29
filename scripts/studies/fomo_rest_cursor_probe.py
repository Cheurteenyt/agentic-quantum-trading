#!/usr/bin/env python3
"""SONDE CURSEUR (29/09) — découverte du mécanisme de pagination REST fomo.
Endpoints : /v2/users/<uid>/swaps?limit=100 et /trades?userId=<uid>&orderBy=closedAt.
One-shot LECTURE SEULE (aucune écriture fomo_rest.db). À lancer hors passe :
systemctl --user is-active fomo-rest-collector.service = inactive.
Verdict par candidat : IGNORE (param sans effet) / CHEVAUCHEMENT / CONTINUITÉ / VIDE.
Réutilise read_jwt/Client du collecteur (mêmes headers, pacing 1 s)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fomo_rest_collector import read_jwt, Client  # noqa: E402

TS_FIELDS = ("createdAt", "closedAt", "timestamp")


def ids(rows):
    """id de ligne : top-level pour swaps, niché row['trade']['id'] pour trades."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict):
            out.append(r.get("id") or (r.get("trade") or {}).get("id"))
    return out


def monotonic(rows1, rows2):
    """True si le flux reste chronologique DESC entre fin p1 et début p2."""
    for f in TS_FIELDS:
        a, b = rows1[-1].get(f), rows2[0].get(f)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return f, b < a
    return None, True


def verdict(rows1, rows2):
    if not isinstance(rows2, list) or not rows2:
        return "VIDE (aucune ligne)"
    i1, i2 = ids(rows1), ids(rows2)
    if i2 == i1:
        return "IGNORE (page2 == page1)"
    if i2[0] == i1[0]:
        return "IGNORE (même 1re ligne)"
    common = set(i1) & set(i2)
    if common:
        return f"CHEVAUCHEMENT {len(common)}/{len(i2)} ids communs (1re p2={str(i2[0])[:14]}…)"
    f, ok = monotonic(rows1, rows2)
    tag = f" ts {f} descend OK" if ok and f else (f" ts {f} NON descendant !" if f else "")
    return f"CONTINUITÉ (1re p2={str(i2[0])[:14]}… inconnue de p1, dernière p1={str(i1[-1])[:14]}…){tag}"


def auto_cands(d, exclude):
    """Candidats génériques : tout champ scalaire de la réponse (nextCursor…)."""
    out = []
    for k, v in (d or {}).items():
        if k in exclude or not isinstance(v, (str, int)) or isinstance(v, bool):
            continue
        out.append((f"auto {k}={str(v)[:18]}", f"&{k}={v}"))
    return out


def run_cands(cli, url, cands, rows1, listkey):
    for name, q in cands:
        try:
            d2 = cli.get(url + q) or {}
            v = verdict(rows1, d2.get(listkey))
        except Exception as e:
            v = f"ERR {str(e)[:60]}"
        print(f"  {name:30} -> {v}")


def probe_swaps(cli, uid):
    url = f"/v2/users/{uid}/swaps?limit=100"
    try:
        d = cli.get(url) or {}
    except Exception as e:
        print(f"=== SWAPS {uid[:8]} ERR {str(e)[:60]}")
        return
    rows1 = d.get("swaps") or []
    meta = {k: d.get(k) for k in d if k != "swaps"}
    print(f"\n=== SWAPS {uid[:8]} n1={len(rows1)} meta={meta}")
    if not rows1:
        return
    print(f"  swap keys={sorted(rows1[0])[:16]}")
    last, cl = rows1[-1].get("id"), rows1[-1].get("createdAt")
    print(f"  last_id={str(last)[:16]}… createdAt_last={cl}")
    cands = [("before=<id>", f"&before={last}"), ("after=<id>", f"&after={last}"),
             ("cursor=<id>", f"&cursor={last}"), ("beforeId=<id>", f"&beforeId={last}"),
             ("afterId=<id>", f"&afterId={last}"), ("lastSwapId=<id>", f"&lastSwapId={last}"),
             ("offset=100", "&offset=100"), ("page=2", "&page=2")]
    if isinstance(cl, (int, float)) and not isinstance(cl, bool):
        cands += [("lt=createdAt_ms", f"&lt={cl}"), ("gt=createdAt_ms", f"&gt={cl}"),
                  ("beforeMs=<ms>", f"&beforeMs={cl}"), ("afterMs=<ms>", f"&afterMs={cl}")]
    cands += auto_cands(d, {"swaps"})
    run_cands(cli, url, cands, rows1, "swaps")
    # Preuve de chaîne : p3 via le dernier id de p2 doit être disjointe de p1∪p2.
    p2 = (cli.get(url + f"&lastSwapId={last}") or {}).get("swaps") or []
    if p2:
        p3 = (cli.get(url + f"&lastSwapId={p2[-1].get('id')}") or {}).get("swaps") or []
        seen = set(ids(rows1)) | set(ids(p2))
        common = seen & set(ids(p3))
        chain = " > ".join(str(r.get("createdAt"))[:19] for r in
                           (rows1[-1], p2[0], p2[-1], p3[0] if p3 else None) if r)
        print(f"  CHAÎNE lastSwapId: p2={len(p2)} p3={len(p3)} "
              f"communs p1∪p2∩p3={len(common)} | createdAt {chain}")


def probe_trades(cli, uid):
    url = f"/trades?userId={uid}&orderBy=closedAt"
    try:
        d = cli.get(url)
    except Exception as e:
        print(f"=== TRADES {uid[:8]} ERR {str(e)[:60]}")
        return
    d = d or {}
    rows1 = d.get("closedTrades") or []
    meta = {k: d.get(k) for k in d if k not in ("closedTrades", "activeTrades")}
    print(f"\n=== TRADES {uid[:8]} closed1={len(rows1)} meta={meta}")
    if not rows1:
        return
    inner = rows1[-1].get("trade") or {}
    print(f"  trade keys={sorted(rows1[0])[:8]} inner keys={sorted(inner)[:16]}")
    last, cl = inner.get("id"), inner.get("closedAt")
    print(f"  inner last_id={str(last)[:16]}… closedAt_last={cl}")
    if not last:
        print("  pas d'id niché — STOP trades")
        return
    cands = [("before=<id>", f"&before={last}"), ("after=<id>", f"&after={last}"),
             ("cursor=<id>", f"&cursor={last}"), ("beforeId=<id>", f"&beforeId={last}"),
             ("afterId=<id>", f"&afterId={last}"), ("lastTradeId=<id>", f"&lastTradeId={last}"),
             ("offset=N", f"&offset={len(rows1)}"), ("page=2", "&page=2")]
    if cl is not None:
        num = isinstance(cl, (int, float)) and not isinstance(cl, bool)
        cands += ([("lt=closedAt_ms", f"&lt={cl}"), ("gt=closedAt_ms", f"&gt={cl}")]
                  if num else []) + [
                  ("beforeClosedAt", f"&beforeClosedAt={cl}"),
                  ("afterClosedAt", f"&afterClosedAt={cl}"),
                  ("beforeTs", f"&beforeTs={cl}"), ("afterTs", f"&afterTs={cl}"),
                  ("lastClosedAt", f"&lastClosedAt={cl}")]
    cands += auto_cands(d, {"closedTrades", "activeTrades"})
    run_cands(cli, url, cands, rows1, "closedTrades")


def jwt_margin(margin: int = 300) -> str | None:
    """Repli sonde : même sélection de cache que le collecteur, marge réduite
    (le one-shot dure < 2 min, la marge 600 s du collecteur est inutile ici)."""
    import json, time, base64
    best, best_exp = None, 0
    root = Path(__file__).resolve().parents[2]
    for p in (root / "data/fomo/ws_jwt_cache.txt", root / "data/fomo/jwt_cache.json"):
        try:
            raw = p.read_text().strip()
            jwt = (json.loads(raw).get("jwt") or json.loads(raw).get("token")
                   if raw.startswith("{") else raw.strip('"'))
            p2 = jwt.split(".")[1]
            p2 += "=" * (-len(p2) % 4)
            e = json.loads(base64.urlsafe_b64decode(p2)).get("exp", 0)
            if e > best_exp:
                best, best_exp = jwt, e
        except Exception:
            continue
    return best if best_exp > time.time() + margin else None


def main() -> int:
    jwt = read_jwt() or jwt_margin()
    if not jwt:
        print("JWT absent/périmé — STOP")
        return 1
    cli = Client(jwt)
    lb = cli.get("/v2/leaderboard/24h") or {}
    rows = lb.get("leaderboard") if isinstance(lb, dict) else lb
    uids = []
    for row in (rows or [])[:5]:
        uid = (row.get("user") or {}).get("id") if isinstance(row, dict) else None
        uid = uid or (row.get("id") if isinstance(row, dict) else None)
        if uid:
            uids.append(uid)
    print(f"élite testée: {[u[:8] for u in uids[:2]]}")
    for uid in uids[:2]:
        probe_swaps(cli, uid)
        probe_trades(cli, uid)
    print(f"\n{cli.n} appels REST, pacing 1 s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
