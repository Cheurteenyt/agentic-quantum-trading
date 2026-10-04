"""Le cog SÉCURITÉ — l'anti-nuke et la probation des membres (le module n°1 de Bonsai).

L'ANTI-NUKE : si un compte staff enchaîne ≥ 3 actions destructrices (salons supprimés,
rôles supprimés, bans en masse) en 5 minutes → QUARANTAINE (les rôles de staff retirés)
+ alerte directe au propriétaire. La compromission d'un compte admin meurt ici.
LA PROBATION : tout nouveau membre reçoit le rôle « Probatant » (créé à la volée, aucun
droit) — l'upgrade se fait à la main ou au tap de la règle des 3 jours.
"""
from __future__ import annotations

import collections
import datetime as dt

import discord
from discord.ext import commands

DESTRUCTIVE_WINDOW_S, DESTRUCTIVE_MAX = 300, 3


async def _quarantine_role(guild: discord.Guild) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name="staff_quarantine")
    if role is None:
        try:
            role = await guild.create_role(name="staff_quarantine",
                                           reason="la quarantaine anti-nuke")
        except discord.Forbidden:
            return None
    return role


async def _probation_role(guild: discord.Guild) -> discord.Role | None:
    role = discord.utils.get(guild.roles, name="Probatant")
    if role is None:
        try:
            role = await guild.create_role(name="Probatant",
                                           reason="la probation des nouveaux membres")
        except discord.Forbidden:
            return None
    return role


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._destructive: dict[int, collections.deque] = collections.defaultdict(
            collections.deque)
        self._alerted: set[int] = set()

    def _staff_acting(self, guild: discord.Guild) -> discord.Member | None:
        """L'auteur de la dernière action destructive, via le journal d'audit."""
        async def fetch():
            async for entry in guild.audit_logs(limit=5,
                                                action=discord.AuditLogAction.channel_delete):
                if (dt.datetime.now(dt.UTC) - entry.created_at).total_seconds() < 300:
                    return entry.user
            return None
        return fetch()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.GuildChannel) -> None:
        await self._register_destructive(channel.guild, f"salon #{channel.name} supprimé")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._register_destructive(guild, f"{user} banni")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._register_destructive(role.guild, f"rôle {role.name} supprimé")

    async def _register_destructive(self, guild: discord.Guild, what: str) -> None:
        # l'auteur réel vient du journal d'audit (discord ne le donne pas dans l'event)
        user = None
        try:
            async for entry in guild.audit_logs(limit=3):
                if (dt.datetime.now(dt.UTC) - entry.created_at).total_seconds() < 300 \
                        and entry.user.id != self.bot.user.id:
                    user = entry.user
                    break
        except discord.Forbidden:
            return
        if not isinstance(user, discord.Member) or user.guild_permissions.administrator is False:
            return  # seuls les comptes staff compromis sont une menace anti-nuke
        now = dt.datetime.now(dt.UTC).timestamp()
        dq = self._destructive[user.id]
        dq.append(now)
        while dq and dq[0] < now - DESTRUCTIVE_WINDOW_S:
            dq.popleft()
        if len(dq) < DESTRUCTIVE_MAX or user.id in self._alerted:
            return
        self._alerted.add(user.id)
        role = _quarantine_role(guild)
        kept = [r.name for r in user.roles if r.is_default()]
        try:
            await user.edit(roles=[r for r in [role] if role], reason="anti-nuke : "
                            f"{DESTRUCTIVE_MAX} actions destructrices en "
                            f"{DESTRUCTIVE_WINDOW_S} s")
        except discord.Forbidden:
            pass
        log_ch = discord.utils.get(guild.text_channels, name="logs")
        if log_ch:
            e = discord.Embed(title="🚨 ANTI-NUKE — STAFF EN QUARANTAINE",
                              description=f"{user.mention} — {what}\n"
                                          f"rôles retirés sauf : {', '.join(kept) or '—'}",
                              color=discord.Color.Red())
            await log_ch.send(embed=e)
        try:
            await guild.owner.send(
                f"🚨 ANTI-NUKE : {user.mention} a enchaîné {DESTRUCTIVE_MAX} actions "
                f"destructrices en 5 min — ses rôles sont retirés (quarantaine). "
                f"Si c'est une compromission, réinitialise le token du compte MAINTENANT.")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        role = _probation_role(member.guild)
        if role:
            try:
                await member.add_roles(role, reason="la probation des nouveaux membres")
            except discord.Forbidden:
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
