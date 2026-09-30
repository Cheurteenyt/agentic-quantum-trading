#!/usr/bin/env python3
"""LE REGISTRE LONGITUDINAL DES TRADERS ASTER (30/09) — le pendant Aster du
suivi derek518 : un tir QUOTIDIEN du leaderboard (le classement est quasi
figé à 10 min, jaccard 0,98 → 1 tir/jour suffit) pour construire dans le
temps qui persiste au top, qui fade, qui entre — la matière de la chasse aux
traders skillés.

Crawls :
  1. POST bapi/futures/v1/public/campaign/trade/pro/leaderboard — les 4 combos
     (d7/d30 x pnl_rank/volume_rank), page par page (rows=100) jusqu'à épuisement
     (la page 2 est vide : le top 100 seul par combo → ~400 lignes, ~244 adresses).
  2. POST bapi/futures/v1/public/future/points/getAllFuturePoints — la pagination
     sur `total` (pattern T1) : {rank, address, au}, les points de campagne par
     adresse (au en STRING géante → float). Cap --max-points-pages (100 pages =
     10 000 premières adresses AU, couvre les top volume, ~40 s).

Table aster_traders (data/warehouse/klines.db, append-only, INSERT OR IGNORE,
rétention infinie — c'est de la décision) :
  PRIMARY KEY (captured_day, address, period, sort)
  Pièges T2 gravés : rank arrive en STRING ("1") → cast INTEGER ; volume=0 est
  LÉGITIME (45/400 lignes sur le sort pnl_rank) → 0.0 stocké, jamais NULL ;
  twitter null est LÉGITIME → None stocké.

Diff longitudinal loggué au 1er tir du jour : ENTRANTS (adresses jamais vues),
SORTANTS (top-100 d'hier absentes aujourd'hui), PERSISTANTS (>= 7 jours
consécutifs — les candidats skillés). État : data/warehouse/aster_traders_state
.json (la dernière journée crawlée → reprise/idempotence si re-run).
Journal [aster-traders]. Unit : aster-traders-registry.timer 06:53 (hors des
passes oi-collector :00/:15/:30/:45 et funding-bulk :07/:37 ; klines.db est en
journal delete → 1 écrivain/base, un seul commit court)."""
import json, sqlite3, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from curl_cffi import requests as cffi

ROOT = Path(__file__).resolve().parents[1]
KL = ROOT / "data" / "warehouse" / "klines.db"
STATE = ROOT / "data" / "warehouse" / "aster_traders_state.json"
LEADERBOARD = "https://www.asterdex.com/bapi/futures/v1/public/campaign/trade/pro/leaderboard"
POINTS = "https://www.asterdex.com/bapi/futures/v1/public/future/points/getAllFuturePoints"
HEADERS = {"Origin": "https://www.asterdex.com",
           "Referer": "https://www.asterdex.com/en/trading-leaderboard",
           "Accept": "application/json"}
COMBOS = [("d7", "pnl_rank"), ("d7", "volume_rank"),
          ("d30", "pnl_rank"), ("d30", "volume_rank")]
PERSIST_MIN_DAYS = 7

DDL = """CREATE TABLE IF NOT EXISTS aster_traders (
  captured_day TEXT NOT NULL,
  address      TEXT NOT NULL,
  handle       TEXT,
  period       TEXT NOT NULL,
  sort         TEXT NOT NULL,
  pnl          REAL,
  volume       REAL,
  rank         INTEGER,
  points       REAL,
  twitter      TEXT,
  PRIMARY KEY (captured_day, address, period, sort))"""


def log(m):
    print(f"[aster-traders] {m}", flush=True)


def to_f(v):
    """float tolérant (volume=0 légitime, '' / None → None)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_i(v):
    """rank en STRING côté API ("1") → INTEGER ; cast raté → None, jamais crash."""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def crawl_combo(s, period, sort, rows, max_pages, pacing):
    """Pagine un combo jusqu'à page vide / doublons (l'API repart en boucle).
    Retourne les lignes brutes dédupliquées par adresse."""
    seen, out = set(), []
    for page in range(1, max_pages + 1):
        body = {"period": period, "sort": sort, "order": "asc",
                "page": page, "rows": rows, "symbol": "", "address": ""}
        r = s.post(LEADERBOARD, json=body, headers=HEADERS)
        try:
            j = r.json()
        except Exception:
            log(f"  [{period}/{sort}] page {page}: HTTP {r.status_code} non-JSON, stop")
            break
        data = j.get("data") or []
        new = [x for x in data if x.get("address") and x["address"] not in seen]
        log(f"  [{period}/{sort}] page {page}: {len(data)} rows ({len(new)} nouvelles)")
        for x in new:
            seen.add(x["address"])
        out.extend(new)
        if not data or not new:
            break
        time.sleep(pacing)
    return out


def crawl_points(s, rows, max_pages, pacing):
    """Pagination sur `total` (pattern T1) : {rank, address, au}. Retourne
    address → (au float, rank int)."""
    got, total = {}, None
    for page in range(1, max_pages + 1):
        r = s.post(POINTS, json={"page": page, "rows": rows}, headers=HEADERS)
        try:
            j = r.json()
        except Exception:
            log(f"  points page {page}: HTTP {r.status_code} non-JSON, stop")
            break
        data = j.get("data") or []
        total = j.get("total")
        for x in data:
            a = x.get("address")
            if a and a not in got:
                got[a] = (to_f(x.get("au")), to_i(x.get("rank")))
        log(f"  points page {page}: {len(data)} rows (cumul {len(got)}, total_api={total})")
        if not data or (total and len(got) >= int(total)):
            break
        time.sleep(pacing)
    return got, total


def streak_days(day_sets, addr, today_d):
    """Streak en jours calendaires consécutifs finissant aujourd'hui."""
    s, d = 1, today_d - timedelta(days=1)
    while d.isoformat() in day_sets.get(addr, ()):
        s += 1
        d -= timedelta(days=1)
    return s


def main() -> int:
    today = datetime.now(timezone.utc).astimezone().date()  # date locale du tir (timer 06:50)
    captured_day = today.isoformat()

    s = cffi.Session(impersonate="chrome131", timeout=15)
    log(f"tir {captured_day} — leaderboard 4 combos")
    rows = []
    for period, sort in COMBOS:
        rows.extend(crawl_combo(s, period, sort, 100, 3, 0.6))
    n_rows = len(rows)
    if n_rows == 0:
        log("0 ligne leaderboard (réseau / Cloudflare ?) — rien inséré, exit 1")
        return 1

    log("points de campagne (getAllFuturePoints, pagination total)")
    pts, pts_total = crawl_points(s, 100, 100, 0.4)

    con = sqlite3.connect(KL, timeout=45)
    con.execute("PRAGMA busy_timeout=45000")
    con.execute(DDL)  # le DDL AVANT toute lecture d'état : sur une base vierge
    # la table n'existe pas encore et l'état la lit (le crash du 30/09 21:06)
    try:
        # l'état d'AVANT : la dernière journée crawlée (pour le diff)
        last_day = con.execute(
            "SELECT MAX(captured_day) FROM aster_traders").fetchone()[0]
        prev_addr = set()
        if last_day:
            prev_addr = {r[0] for r in con.execute(
                "SELECT DISTINCT address FROM aster_traders WHERE captured_day=?",
                (last_day,)).fetchall()}
        seen_ever = {r[0] for r in con.execute(
            "SELECT DISTINCT address FROM aster_traders").fetchall()}

        con.execute(DDL)
        ins = 0
        for x in rows:
            addr = x["address"]
            au = pts.get(addr)
            cur = con.execute(
                "INSERT OR IGNORE INTO aster_traders (captured_day, address, "
                "handle, period, sort, pnl, volume, rank, points, twitter) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (captured_day, addr, x.get("name") or None, period, sort,
                 to_f(x.get("pnl")), to_f(x.get("volume")), to_i(x.get("rank")),
                 au[0] if au else None, x.get("twitterUsername") or None))
            ins += cur.rowcount
        con.commit()  # 1 écrivain/base : un seul commit court (journal delete)

        n_addr = con.execute("SELECT COUNT(DISTINCT address) FROM aster_traders "
                             "WHERE captured_day=?", (captured_day,)).fetchone()[0]
        n_pts = con.execute("SELECT COUNT(DISTINCT address) FROM aster_traders "
                            "WHERE captured_day=? AND points IS NOT NULL",
                            (captured_day,)).fetchone()[0]
        log(f"inséré {ins}/{n_rows} lignes (OR IGNORE), {n_addr} adresses, "
            f"points d7 couverts {n_pts}/{n_addr} (pool AU {len(pts)}, total_api={pts_total})")

        # ── le diff longitudinal (1er tir du jour seulement — idempotence) ──
        if last_day == captured_day:
            log(f"re-run {captured_day} : déjà crawlé aujourd'hui, diff non recalculé")
        else:
            today_addr = {r[0] for r in con.execute(
                "SELECT DISTINCT address FROM aster_traders WHERE captured_day=?",
                (captured_day,)).fetchall()}
            entrants = sorted(today_addr - seen_ever)
            sortants = sorted(prev_addr - today_addr)
            log(f"ENTRANTS {len(entrants)} (jamais vus) : "
                + (", ".join(entrants[:10]) + ("…" if len(entrants) > 10 else "")
                   if entrants else "aucun"))
            log(f"SORTANTS {len(sortants)} (top-100 {last_day} absents) : "
                + (", ".join(sortants[:10]) + ("…" if len(sortants) > 10 else "")
                   if sortants else "aucun"))
            # persistants : >= 7 jours CALENDAIRES consécutifs finissant aujourd'hui
            cutoff = (today - timedelta(days=PERSIST_MIN_DAYS + 3)).isoformat()
            day_sets = {}
            for a, d in con.execute(
                    "SELECT DISTINCT address, captured_day FROM aster_traders "
                    "WHERE captured_day >= ? AND captured_day <= ?",
                    (cutoff, captured_day)).fetchall():
                day_sets.setdefault(a, set()).add(d)
            persist = sorted(a for a in today_addr
                             if streak_days(day_sets, a, today) >= PERSIST_MIN_DAYS)
            log(f"PERSISTANTS >= {PERSIST_MIN_DAYS} j consécutifs : {len(persist)}"
                + (f" — ex: {', '.join(persist[:5])}" if persist else ""))
    except Exception:
        con.rollback()  # jamais de txn fantôme qui tient le write-lock
        raise
    finally:
        con.close()

    STATE.write_text(json.dumps({
        "last_captured_day": captured_day,
        "last_run_epoch": round(time.time(), 1),
        "n_rows": n_rows, "n_addresses": n_addr, "points_pool": len(pts),
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
