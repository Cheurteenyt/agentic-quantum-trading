"""Le store Discord — data/warehouse/discord.db (WAL, timeout 60, lecture séparée du reste).

La séparation des domaines du repo : ASTER ≠ FOMO ≠ X ≠ DISCORD. Ce que le bot capture
de SON serveur vit ici, jamais mélangé aux autres bases.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "warehouse" / "discord.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS d_messages (
    message_id      TEXT PRIMARY KEY,
    guild_id        TEXT, channel_id TEXT, channel_name TEXT,
    author_id       TEXT, author_name TEXT,
    created_at      TEXT,               -- ISO UTC (l'horodatage Discord)
    content         TEXT,
    attachment_count INTEGER,
    attachment_types TEXT,              -- JSON ["image/png", "video/mp4", ...]
    attachment_urls  TEXT,              -- JSON
    link_urls        TEXT,              -- JSON (les liens extraits du texte)
    fetched_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS d_media (
    message_id TEXT NOT NULL, media_type TEXT NOT NULL, url TEXT NOT NULL,
    filename TEXT, size INTEGER, captured_at REAL NOT NULL,
    UNIQUE(message_id, url)
);
CREATE TABLE IF NOT EXISTS d_mod_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
    action TEXT NOT NULL, guild_id TEXT, moderator_id TEXT,
    target_id TEXT, reason TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS d_cases (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
    guild_id TEXT, user_id TEXT, user_name TEXT, ctype TEXT, reason TEXT
);
CREATE TABLE IF NOT EXISTS d_access (
    channel_id TEXT PRIMARY KEY, channel_name TEXT, private INTEGER,
    synced INTEGER, access_json TEXT, viewers TEXT, updated_at REAL
);
CREATE TABLE IF NOT EXISTS d_members (
    user_id TEXT PRIMARY KEY, user_name TEXT, display_name TEXT,
    bot INTEGER, joined_at TEXT, account_created TEXT,
    roles TEXT, last_seen TEXT
);
CREATE TABLE IF NOT EXISTS d_roles (
    role_id TEXT PRIMARY KEY, name TEXT, position INTEGER,
    color TEXT, permissions TEXT, member_count INTEGER, updated_at REAL
);
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")       # la leçon 75dd088 : WAL + timeout partout
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def save_message(msg_row: dict, media_rows: list[dict]) -> None:
    con = connect()
    try:
        con.execute(
            """INSERT OR REPLACE INTO d_messages
               (message_id, guild_id, channel_id, channel_name, author_id, author_name,
                created_at, content, attachment_count, attachment_types,
                attachment_urls, link_urls, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (msg_row["message_id"], msg_row["guild_id"], msg_row["channel_id"],
             msg_row["channel_name"], msg_row["author_id"], msg_row["author_name"],
             msg_row["created_at"], msg_row["content"], msg_row["attachment_count"],
             json.dumps(msg_row["attachment_types"], ensure_ascii=False),
             json.dumps(msg_row["attachment_urls"], ensure_ascii=False),
             json.dumps(msg_row["link_urls"], ensure_ascii=False),
             time.time()))
        for m in media_rows:
            con.execute("INSERT OR IGNORE INTO d_media VALUES (?,?,?,?,?,?)",
                        (m["message_id"], m["media_type"], m["url"],
                         m.get("filename"), m.get("size"), time.time()))
        con.commit()
    finally:
        con.close()


def last_message_id(channel_id: str) -> str | None:
    """Le dernier message_id capturé d'un salon — le point de reprise du catch-up."""
    con = connect()
    try:
        row = con.execute(
            "SELECT message_id FROM d_messages WHERE channel_id=? "
            "ORDER BY CAST(message_id AS INTEGER) DESC LIMIT 1", (str(channel_id),)).fetchone()
        return row["message_id"] if row else None
    finally:
        con.close()


def count_messages() -> int:
    con = connect()
    try:
        return con.execute("SELECT COUNT(*) FROM d_messages").fetchone()[0]
    finally:
        con.close()


def mod_db(action: str, guild_id: str, moderator_id: str, target_id: str,
           reason: str, detail: str = "") -> None:
    """Chaque action de modération est tracée — « absolument tout » est auditable."""
    con = connect()
    try:
        con.execute("INSERT INTO d_mod_actions (ts, action, guild_id, moderator_id, "
                    "target_id, reason, detail) VALUES (?,?,?,?,?,?,?)",
                    (time.time(), action, guild_id, moderator_id, target_id,
                     reason or "—", detail))
        con.commit()
    finally:
        con.close()


def warns_of(guild_id: str, target_id: str) -> list[tuple]:
    con = connect()
    try:
        return con.execute(
            "SELECT ts, reason FROM d_mod_actions WHERE action='warn' AND guild_id=? "
            "AND target_id=? ORDER BY ts", (guild_id, target_id)).fetchall()
    finally:
        con.close()


# ——— le registre du serveur : les salons/rôles/règles déclarés par le user ———

def _reg_init(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS d_registry (
        guild_id TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL,
        value TEXT, updated_at REAL NOT NULL,
        UNIQUE(guild_id, kind, target))""")


def reg_set(guild_id: int | str, kind: str, target: str, value: str = "") -> None:
    con = connect()
    try:
        _reg_init(con)
        con.execute("INSERT OR REPLACE INTO d_registry VALUES (?,?,?,?,?)",
                    (str(guild_id), kind, target, value, time.time()))
        con.commit()
    finally:
        con.close()


def reg_del(guild_id: int | str, kind: str, target: str) -> None:
    con = connect()
    try:
        _reg_init(con)
        con.execute("DELETE FROM d_registry WHERE guild_id=? AND kind=? AND target=?",
                    (str(guild_id), kind, target))
        con.commit()
    finally:
        con.close()


def reg_get(guild_id: int | str, kind: str) -> list[sqlite3.Row]:
    """Toutes les entrées d'un kind — ex : reg_get(g, 'role_mod') → les rôles modérateurs."""
    con = connect()
    try:
        _reg_init(con)
        return con.execute("SELECT target, value FROM d_registry WHERE guild_id=? AND kind=?",
                           (str(guild_id), kind)).fetchall()
    finally:
        con.close()


def reg_channel(guild_id: int | str, kind: str):
    """L'id du salon déclaré pour un rôle fonctionnel (log, bienvenue, commandes...)."""
    rows = reg_get(guild_id, f"channel_{kind}")
    return int(rows[0]["target"]) if rows else None


def reg_has_role(member_roles: list[int], guild_id: int | str, kind: str) -> bool:
    """Le membre porte-t-il un rôle enregistré pour ce kind ?"""
    wanted = {int(r["target"]) for r in reg_get(guild_id, f"role_{kind}")}
    return bool(wanted & set(member_roles))


def reg_rule(guild_id: int | str, channel_id: int | str, rule: str) -> bool:
    """La règle d'un salon est-elle active ? (les règles par défaut : aucune)"""
    rows = reg_get(guild_id, f"rule_{rule}")
    return str(channel_id) in {r["target"] for r in rows}


def member_upsert(user_id: str, user_name: str, display_name: str, bot: bool,
                  joined_at: str | None, account_created: str | None,
                  roles: list[str]) -> None:
    con = connect()
    try:
        con.execute("""INSERT INTO d_members
            (user_id, user_name, display_name, bot, joined_at, account_created,
             roles, last_seen) VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET user_name=excluded.user_name,
            display_name=excluded.display_name, bot=excluded.bot,
            joined_at=excluded.joined_at, account_created=excluded.account_created,
            roles=excluded.roles, last_seen=excluded.last_seen""",
            (user_id, user_name, display_name, int(bot), joined_at, account_created,
             json.dumps(roles, ensure_ascii=False),
             dt.datetime.now(dt.UTC).isoformat()))
        con.commit()
    finally:
        con.close()


def role_upsert(role_id: str, name: str, position: int, color: str,
                permissions: str, member_count: int) -> None:
    con = connect()
    try:
        con.execute("""INSERT INTO d_roles
            (role_id, name, position, color, permissions, member_count, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(role_id) DO UPDATE SET name=excluded.name,
            position=excluded.position, color=excluded.color,
            permissions=excluded.permissions, member_count=excluded.member_count,
            updated_at=excluded.updated_at""",
            (role_id, name, position, color, permissions, member_count, time.time()))
        con.commit()
    finally:
        con.close()
