"""Le cog de CAPTURE — chaque message du serveur (texte, images, vidéos, fichiers, liens)
tombe dans data/warehouse/discord.db, avec un backfill de l'historique au premier lancement.

Les règles : les bots sont ignorés (dont le bot lui-même), un message qui crashe ne crashe
jamais le listener, et les URL d'abord — le téléchargement des médias attend une hypothèse
vivante (le CDN Discord signe ses URL : les fichiers se re-téléchargent via l'API).
"""
from __future__ import annotations

import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands

from .. import store

LINK_RE = re.compile(r"https?://[^\s<>\")\]]+", re.I)
BACKFILL_PER_CHANNEL = 300


def _extract(message: discord.Message) -> tuple[dict, list[dict]]:
    atts = list(message.attachments)
    links = LINK_RE.findall(message.content or "")
    media_rows = [{
        "message_id": str(message.id),
        "media_type": ("video" if (a.content_type or "").startswith("video")
                       else "image" if (a.content_type or "").startswith("image")
                       else "file"),
        "url": a.url,
        "filename": a.filename,
        "size": a.size,
    } for a in atts]
    row = {
        "message_id": str(message.id),
        "guild_id": str(message.guild.id) if message.guild else "",
        "channel_id": str(message.channel.id),
        "channel_name": getattr(message.channel, "name", "dm"),
        "author_id": str(message.author.id),
        "author_name": str(message.author),
        "created_at": message.created_at.isoformat(),
        "content": (message.content or "")[:4000],
        "attachment_count": len(atts),
        "attachment_types": [a.content_type or "inconnu" for a in atts],
        "attachment_urls": [a.url for a in atts],
        "link_urls": links,
    }
    return row, media_rows


class Capture(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._backfilled = False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        # LES RÈGLES PAR SALON (la carte du registre) — les admins en sont exempts
        admin = isinstance(message.author, discord.Member) \
            and message.author.guild_permissions.administrator
        if message.guild and not admin:
            gid, cid = message.guild.id, message.channel.id
            content = message.content or ""
            if store.reg_rule(gid, cid, "commands_only") and content:
                await message.delete()
                return
            if store.reg_rule(gid, cid, "no_links") \
                    and re.search(r"https?://", content):
                await message.delete()
                return
            if store.reg_rule(gid, cid, "media_only") and not message.attachments:
                await message.delete()
                return
        try:
            row, media = _extract(message)
            store.save_message(row, media)
        except Exception as exc:  # noqa: BLE001 — jamais de crash sur un message
            print(f"[capture] échec message {message.id} : {exc}")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._backfilled:
            return
        self._backfilled = True
        if store.count_messages() > 0:
            return
        # le premier lancement : l'historique des salons texte (300/channel)
        asyncio.create_task(self._backfill_all(BACKFILL_PER_CHANNEL))

    async def _backfill_all(self, per_channel: int) -> None:
        total = 0
        try:
            await self.bot.wait_until_ready()
            for guild in self.bot.guilds:
                for channel in guild.text_channels:
                    try:
                        async for message in channel.history(limit=per_channel,
                                                             oldest_first=False):
                            if message.author.bot:
                                continue
                            row, media = _extract(message)
                            store.save_message(row, media)
                            total += 1
                    except discord.Forbidden:
                        continue  # un salon sans permission de lecture — normal
                    except Exception as exc:  # noqa: BLE001
                        print(f"[capture] backfill #{channel.name} : {exc}")
        finally:
            print(f"[capture] backfill terminé : {total} messages historisés, "
                  f"total {store.count_messages()}")

    @app_commands.command(name="backfill",
                          description="Ré-historise les salons (300 messages chacun)")
    @app_commands.checks.has_permissions(administrator=True)
    async def backfill(self, inter: discord.Interaction) -> None:
        await inter.response.send_message(
            f"backfill lancé ({BACKFILL_PER_CHANNEL}/salon) — la capture en direct continue",
            ephemeral=True)
        asyncio.create_task(self._backfill_all(BACKFILL_PER_CHANNEL))

    @app_commands.command(name="capture_stats",
                          description="L'état de la capture Discord")
    async def capture_stats(self, inter: discord.Interaction) -> None:
        con = store.connect()
        try:
            n = con.execute("SELECT COUNT(*) FROM d_messages").fetchone()[0]
            media = con.execute("SELECT COUNT(*) FROM d_media").fetchone()[0]
            par_salon = con.execute(
                "SELECT channel_name, COUNT(*) c FROM d_messages "
                "GROUP BY channel_name ORDER BY c DESC LIMIT 10").fetchall()
            with_media = con.execute(
                "SELECT COUNT(*) FROM d_messages WHERE attachment_count > 0").fetchone()[0]
        finally:
            con.close()
        salon_txt = "\n".join(f"• #{r['channel_name']} : {r['c']}" for r in par_salon)
        await inter.response.send_message(
            f"**Capture Discord** : {n:,} messages ({with_media:,} avec médias, "
            f"{media:,} attaches) — top salons :\n{salon_txt}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Capture(bot))
