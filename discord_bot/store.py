"""Le store Discord — data/warehouse/discord.db (WAL, timeout 60, lecture séparée du reste).

La séparation des domaines du repo : ASTER ≠ FOMO ≠ X ≠ DISCORD. Ce que le bot capture
de SON serveur vit ici, jamais mélangé aux autres bases.
"""
from __future__ import annotations

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
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.row_factory = sqlite3.Row
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


def count_messages() -> int:
    con = connect()
    try:
        return con.execute("SELECT COUNT(*) FROM d_messages").fetchone()[0]
    finally:
        con.close()
