"""Le PORTIER — la quarantaine fonctionnelle des nouveaux membres (Bonsai RBAC).

security.py pose l'étiquette « Probatant » ; ce cog lui donne des DENTS :
silence total (deny send_messages sur tous les salons, ré-appliqué à chaque
join = auto-réparant pour les salons nouveaux) SAUF le salon d'arrivée
(kind `arrivee` du /setchannel, sinon bienvenue*). La sortie :
  1. le premier message en arrivée scoré clean par le juge sémantique → libre,
  2. sinon la boucle horaire ouvre à GATE_HOURS.
Les pendings vivent dans le registre (kind `gate_pending`, target=user_id,
value=joined_at ISO) — zéro schéma nouveau.
"""
from __future__ import annotations

import asyncio
import datetime as dt

import discord
from discord.ext import commands, tasks

from discord_bot import store
from discord_bot.bonsai_judge import classify

GATE_HOURS = 48
TOX_MAX = 70  # le seuil de libération par le juge (en dessous = clean)


# ——— les helpers purs (testés) ———


def release_at(joined_iso: str | None) -> float:
    """L'époque de libération = l'arrivée + GATE_HOURS ; ISO malformé → 0 (libre)."""
    if not joined_iso:
        return 0.0
    try:
        joined = dt.datetime.fromisoformat(joined_iso)
    except (ValueError, TypeError):
        return 0.0
    return joined.timestamp() + GATE_HOURS * 3600


def pending_of(rows: list) -> list[tuple[int, float]]:
    """Les rows du registre → [(user_id, release_epoch)] — les rows pourris sautent."""
    out = []
    for r in rows:
        try:
            out.append((int(r["target"]), release_at(r["value"])))
        except (ValueError, TypeError):
            continue
    return out


def is_due(release_epoch: float, now: float) -> bool:
    # fail-open : un timestamp corrompu (0) libère à la prochaine boucle —
    # on ne piège JAMAIS un membre en quarantaine
    return release_epoch <= now


# ——— le cog ———


class Gatekeeper(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.gate_loop.start()

    def cog_unload(self) -> None:
        self.gate_loop.cancel()

    # la géométrie du gate

    async def _probatant_role(self, guild: discord.Guild) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name="Probatant")
        if role is None:
            try:
                role = await guild.create_role(name="Probatant",
                                               reason="le portier 48 h")
            except discord.Forbidden:
                return None
        return role

    def _gate_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cid = store.reg_channel(guild.id, "arrivee")
        ch = guild.get_channel(cid) if cid else None
        if ch:
            return ch
        ch = discord.utils.get(guild.text_channels, name="arrivée") \
            or discord.utils.get(guild.text_channels, name="arrivee")
        if ch:
            return ch
        cid = store.reg_channel(guild.id, "bienvenue")
        return guild.get_channel(cid) if cid else None

    async def _apply_silence(self, guild: discord.Guild, role: discord.Role) -> None:
        """deny send_messages partout SAUF le salon d'arrivée (allow)."""
        gate = self._gate_channel(guild)
        for ch in guild.text_channels:
            allow = ch == gate
            try:
                await ch.set_permissions(
                    role,
                    overwrite=discord.PermissionOverwrite(send_messages=allow),
                    reason="le portier : silence sauf arrivée")
            except discord.Forbidden:
                continue

    # le flow

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        role = await self._probatant_role(member.guild)
        if role is None:
            return
        await self._apply_silence(member.guild, role)
        store.reg_set(member.guild.id, "gate_pending", str(member.id),
                      dt.datetime.now(dt.UTC).isoformat())

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        store.reg_del(member.guild.id, "gate_pending", str(member.id))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        role = discord.utils.get(message.author.roles, name="Probatant")
        if role is None:
            return
        if self._gate_channel(message.guild) != message.channel:
            return  # il ne peut de toute façon parler que là
        age_days = 0.0
        if message.author.created_at:
            age_days = (dt.datetime.now(dt.UTC) - message.author.created_at).total_seconds() / 86400
        verdict = await asyncio.to_thread(
            classify, message.content or "", age_days, message.channel.name)
        if verdict is None:
            return  # le juge est down — la boucle 48 h tranchera
        if verdict.get("scam_type") or verdict.get("toxicity", 0) >= TOX_MAX:
            await self._log(message.guild, "🚪 PORTIER — PREMIER MESSAGE SUSPECT",
                            f"{message.author.mention} reste en quarantaine "
                            f"(toxicité {verdict.get('toxicity')}, "
                            f"scam {verdict.get('scam_type')})", discord.Color.Red())
            return
        await self.release(message.author, "premier message clean")

    async def release(self, member: discord.Member, why: str) -> None:
        role = discord.utils.get(member.roles, name="Probatant")
        if role:
            try:
                await member.remove_roles(role, reason=f"portier : {why}")
            except discord.Forbidden:
                return
        store.reg_del(member.guild.id, "gate_pending", str(member.id))
        await self._log(member.guild, "🚪 PORTIER — LIBÉRÉ",
                        f"{member.mention} sort de quarantaine ({why})",
                        discord.Color.Green())

    async def _log(self, guild: discord.Guild, title: str, desc: str, color) -> None:
        cid = store.reg_channel(guild.id, "log")
        ch = guild.get_channel(cid) if cid else None
        ch = ch or discord.utils.get(guild.text_channels, name="logs")
        if ch:
            await ch.send(embed=discord.Embed(title=title, description=desc, color=color))

    # la boucle horaire : les 48 h dépassées sortent, les partis sont nettoyés

    @tasks.loop(hours=1)
    async def gate_loop(self) -> None:
        now = dt.datetime.now(dt.UTC).timestamp()
        for guild in self.bot.guilds:
            rows = store.reg_get(guild.id, "gate_pending")
            for uid, rel in pending_of(rows):
                member = guild.get_member(uid)
                if member is None:
                    store.reg_del(guild.id, "gate_pending", str(uid))
                    continue
                if is_due(rel, now):
                    await self.release(member, "48 h écoulées sans incident")

    @gate_loop.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

    # le refresh manuel (un salon nouveau né avant le prochain join)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.GuildChannel) -> None:
        role = discord.utils.get(channel.guild.roles, name="Probatant")
        if role and isinstance(channel, discord.TextChannel):
            gate = self._gate_channel(channel.guild)
            allow = channel == gate
            try:
                await channel.set_permissions(
                    role, overwrite=discord.PermissionOverwrite(send_messages=allow),
                    reason="le portier : les salons nouveaux naissent silencieux")
            except discord.Forbidden:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Gatekeeper(bot))
