"""Les commandes de consultation — l'état du projet, lu en lecture seule dans la warehouse."""
from __future__ import annotations

import sqlite3

import discord
from discord import app_commands

from .. import config


def _kdb() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{config.KDB}?mode=ro", uri=True)


@app_commands.command(name="ping", description="Le bot répond — le test de vie")
async def ping(inter: discord.Interaction) -> None:
    await inter.response.send_message("pong — Hermes est réveillé 🐺")


@app_commands.command(name="etat", description="L'état du projet : ledger, budget, machine, X")
async def etat(inter: discord.Interaction) -> None:
    await inter.response.defer()
    lines = ["**Hermes — l'état du projet**"]
    try:
        con = _kdb()
        r = con.execute("SELECT COUNT(*), MAX(entry_ts) FROM aster_survivors_paper").fetchone()
        lines.append(f"• paper survivants : {r[0]} entrées, dernière {r[1] or '—'}")
        led = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='paper_trades'").fetchone()
        if led:
            n = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
            lines.append(f"• paper_trades : {n:,} lignes")
        xcon = sqlite3.connect(f"file:{config.XPDB}?mode=ro", uri=True)
        posts = xcon.execute("SELECT COUNT(*) FROM x_posts").fetchone()[0]
        calls = xcon.execute("SELECT COUNT(*) FROM x_calls").fetchone()[0]
        lines.append(f"• domaine X : {posts:,} posts, {calls} calls parsés")
        xcon.close()
        con.close()
    except Exception as exc:  # noqa: BLE001 — la commande ne crashe jamais le bot
        lines.append(f"• erreur lecture DB : {exc}")
    await inter.followup.send("\n".join(lines))


async def setup(bot: discord.Client) -> None:
    bot.tree.add_command(ping)
    bot.tree.add_command(etat)
