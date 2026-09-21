#!/usr/bin/env python3
"""Registre X — ingestion et stockage des posts crypto Twitter (phase 1).

Le principe : tout le monde publie des calls sur X, personne ne tient le score.
Ce script est la moitie "tenir le score" : il stocke les posts recoltes
(extraction navigateur, voir docs/14-registre-x.md), la watchlist de comptes,
et une premiere passe de parsing deterministe des calls (v0).

    python scripts/fetch_x_posts.py --init-db
    python scripts/fetch_x_posts.py --ingest-json posts.json --query "$BTC (long OR short)"
    python scripts/fetch_x_posts.py --parse-calls
    python scripts/fetch_x_posts.py --stats
    python scripts/fetch_x_posts.py --add-account lookonchain --category data --reason "tracking whales Aster"

La watchlist est volontairement diverse des la creation : ajouter un compte
APRES avoir vu ses resultats recreerait le biais de survie que le registre
existe justement pour demasquer. La correction de multiplicite s'appliquera
aux track records comme elle s'applique aux strategies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "warehouse" / "x_posts.db"

PARSER_VERSION = "v1-regex"

SCHEMA = """
CREATE TABLE IF NOT EXISTS x_posts (
    post_id        TEXT PRIMARY KEY,
    author_handle  TEXT NOT NULL,
    author_name    TEXT,
    status_url     TEXT,
    posted_at_raw  TEXT,
    text           TEXT NOT NULL,
    metrics        TEXT,
    search_query   TEXT,
    source         TEXT NOT NULL DEFAULT 'browser_live',
    fetched_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_posts_handle ON x_posts(author_handle);
CREATE INDEX IF NOT EXISTS idx_posts_fetched ON x_posts(fetched_at);

CREATE TABLE IF NOT EXISTS x_accounts (
    handle        TEXT PRIMARY KEY,
    display_name  TEXT,
    category      TEXT,
    added_at      TEXT NOT NULL,
    added_reason  TEXT,
    active        INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS x_calls (
    call_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id        TEXT NOT NULL REFERENCES x_posts(post_id),
    symbol         TEXT,
    direction      TEXT,
    entry_price    REAL,
    horizon        TEXT,
    confidence     TEXT NOT NULL DEFAULT 'low',
    parser_version TEXT NOT NULL,
    parsed_at      TEXT NOT NULL,
    UNIQUE(post_id, parser_version)
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.executescript(SCHEMA)
    return con


def cmd_init_db() -> int:
    con = _connect()
    con.close()
    print(f"[x-registre] base prete : {DB_PATH}")
    return 0


def cmd_ingest_json(path: str, query: str) -> int:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw.get("posts", [])
    now = _utc_now()
    con = _connect()
    inserted = 0
    skipped = 0
    for item in raw:
        raw_label = str(item.get("raw_label") or "").strip()
        clean_text = str(item.get("text") or "").strip()
        handle = str(item.get("author_handle") or "").strip().lstrip("@").lower()
        post_id = str(item.get("post_id") or "").strip()
        if not handle or not (raw_label or clean_text):
            skipped += 1
            continue
        if not post_id:
            post_id = "h-" + hashlib.sha1((raw_label or clean_text).encode()).hexdigest()[:16]
        if item.get("posted_at_iso"):
            # format harvester headless : texte deja propre + ISO reel
            posted_at_raw = str(item["posted_at_iso"])
            text = clean_text
        else:
            # format extraction live : label ARIA brut -> entete a retirer
            m = re.search(TIME_RE, raw_label)
            posted_at_raw = m.group(0) if m else None
            hm = re.search(r"@[A-Za-z0-9_]{1,15}", raw_label)
            text = raw_label
            if hm:
                tail = raw_label[hm.end():]
                tm = re.search(TIME_RE, tail)
                if tm:
                    text = tail[tm.end():].strip()
        cur = con.execute(
            """
            INSERT OR IGNORE INTO x_posts
              (post_id, author_handle, author_name, status_url, posted_at_raw,
               text, metrics, search_query, source, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                handle,
                item.get("author_name"),
                item.get("status_url"),
                posted_at_raw,
                text,
                json.dumps(item.get("metrics") or {}, ensure_ascii=False),
                query or item.get("search_query"),
                item.get("source") or "browser_live",
                now,
            ),
        )
        inserted += 1 if cur.rowcount else 0
        if not cur.rowcount:
            skipped += 1
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM x_posts").fetchone()[0]
    con.close()
    print(f"[x-registre] ingere : {inserted} nouveaux, {skipped} ignores, total {total}")
    return 0


_DIRECTION = r"\b(long|short|bullish|bearish|achat|vente|achete|vend)\b"
_PRICE = r"(?:@|at\b|a\s|à\s|entr[ée]e\s)(\d{1,3}(?:[ ,]\d{3})*(?:[.,]\d+)?)([kKmM])?\b"
# horodatage X relatif ou date courte — unité précise, sinon le motif glouton
# avalerait le texte suivant ("Il y a 17 minutes Today $BTC flipped…")
TIME_RE = r"(Il y a \d+ (?:seconde|minute|heure|jour|semaine)s?|\d{1,2} \w{3,5}\.?(?: \d{4})?)"


def _parse_calls(con: sqlite3.Connection) -> int:
    """Passe deterministe : ne score que ce qu'on sait lire sans ambiguite.

    Confiance 'high' uniquement si symbole + direction explicites dans une
    fenetre de texte courte. Tout le reste reste non parse : le registre ne
    devine pas, sinon il ment.
    v1 : seul un $CASHTAG identifie l'actif sans ambiguite. Les tickers nus
    ('l'EGLD a 500$') generaient des faux positifs — le registre ne score
    que ce qu'il lit sans ambiguite.
    """
    now = _utc_now()
    rows = con.execute(
        """
        SELECT post_id, text FROM x_posts
        WHERE post_id NOT IN (SELECT post_id FROM x_calls WHERE parser_version = ?)
        """,
        (PARSER_VERSION,),
    ).fetchall()
    calls = 0
    for post_id, text in rows:
        cashtag = re.search(r"\$([A-Za-z]{2,10})\b", text)
        direction_m = re.search(_DIRECTION, text, re.IGNORECASE)
        if not cashtag or not direction_m:
            continue
        symbol = cashtag.group(1).upper()
        direction = direction_m.group(1).lower()
        direction = {
            "bullish": "long", "bearish": "short", "achat": "long", "vente": "short",
            "achete": "long", "vend": "short",
        }.get(direction, direction)
        confidence = "medium"
        entry_price = None
        horizon = None
        price_m = re.search(_PRICE, text, re.IGNORECASE)
        if price_m:
            raw_price = price_m.group(1).replace(" ", "")
            # "83,000" = separateur de milliers, pas une decimale
            if re.fullmatch(r"\d{1,3}(,\d{3})+", raw_price):
                value = float(raw_price.replace(",", ""))
            else:
                value = float(raw_price.replace(",", "."))
            mult = {"k": 1e3, "m": 1e6}.get((price_m.group(2) or "").lower(), 1.0)
            entry_price = value * mult
            confidence = "high"
        if re.search(r"\b(daily|4h|1h|15m|intraday|day)\b", text, re.IGNORECASE):
            horizon = "intraday"
        elif re.search(r"\b(week|hebdo|swing|month)\b", text, re.IGNORECASE):
            horizon = "swing"
        else:
            horizon = "none"
        con.execute(
            """
            INSERT OR IGNORE INTO x_calls
              (post_id, symbol, direction, entry_price, horizon, confidence,
               parser_version, parsed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (post_id, symbol, direction, entry_price, horizon, confidence,
             PARSER_VERSION, now),
        )
        calls += 1
    con.commit()
    return calls


def cmd_parse_calls() -> int:
    con = _connect()
    calls = _parse_calls(con)
    total = con.execute("SELECT COUNT(*) FROM x_calls").fetchone()[0]
    con.close()
    print(f"[x-registre] calls parses : {calls} nouveaux ({PARSER_VERSION}), total {total}")
    return 0


def cmd_stats() -> int:
    con = _connect()
    posts = con.execute("SELECT COUNT(*) FROM x_posts").fetchone()[0]
    accounts = con.execute(
        "SELECT COUNT(*) FROM x_accounts WHERE active = 1"
    ).fetchone()[0]
    calls = con.execute("SELECT COUNT(*) FROM x_calls").fetchone()[0]
    high = con.execute(
        "SELECT COUNT(*) FROM x_calls WHERE confidence = 'high'"
    ).fetchone()[0]
    top = con.execute(
        """
        SELECT author_handle, COUNT(*) AS n FROM x_posts
        GROUP BY author_handle ORDER BY n DESC LIMIT 5
        """
    ).fetchall()
    con.close()
    print(f"[x-registre] {DB_PATH.name} : {posts} posts | {accounts} comptes actifs")
    print(f"[x-registre] calls parses : {calls} (dont {high} haute confiance)")
    for handle, n in top:
        print(f"  · @{handle} : {n} posts")
    return 0


def cmd_add_account(handle: str, category: str, reason: str) -> int:
    con = _connect()
    con.execute(
        """
        INSERT OR REPLACE INTO x_accounts
          (handle, category, added_at, added_reason, active)
        VALUES (?, ?, ?, ?, 1)
        """,
        (handle.lstrip("@").lower(), category, _utc_now(), reason),
    )
    con.commit()
    con.close()
    print(f"[x-registre] compte ajoute : @{handle.lstrip('@')} ({category})")
    return 0


def cmd_list_accounts() -> int:
    con = _connect()
    rows = con.execute(
        "SELECT handle, category, added_reason FROM x_accounts WHERE active = 1"
    ).fetchall()
    con.close()
    for handle, category, reason in rows:
        print(f"  @{handle:<20} [{category or '?'}] {reason or ''}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Registre X — posts, watchlist, calls")
    p.add_argument("--init-db", action="store_true")
    p.add_argument("--ingest-json", metavar="FILE")
    p.add_argument("--query", default="", help="query de recherche associee a l'ingestion")
    p.add_argument("--parse-calls", action="store_true")
    p.add_argument("--stats", action="store_true")
    p.add_argument("--add-account", metavar="HANDLE")
    p.add_argument("--category", default="retail")
    p.add_argument("--reason", default="")
    p.add_argument("--list-accounts", action="store_true")
    args = p.parse_args()

    if args.init_db:
        return cmd_init_db()
    if args.ingest_json:
        return cmd_ingest_json(args.ingest_json, args.query)
    if args.parse_calls:
        return cmd_parse_calls()
    if args.add_account:
        return cmd_add_account(args.add_account, args.category, args.reason)
    if args.list_accounts:
        return cmd_list_accounts()
    if args.stats:
        return cmd_stats()
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
