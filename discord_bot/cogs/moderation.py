"""Le cog MODÉRATION — opérationnel pour absolument tout, chaque action tracée.

Les commandes mod : kick, ban/unban, timeout/untimeout, clear (purge), warn/warns,
slowmode, lock/unlock, addrole/removerole, modlog (l'historique des actions).
L'auto-mod : anti-spam (6 msgs/10 s → timeout 5 min), anti-mention-spam (4+ mentions
→ purge + timeout), anti-invite (discord.gg → suppression + trace).
La log : chaque action part dans le salon #logs (ou DISCORD_MOD_LOG_CHANNEL du .env)
ET dans d_mod_actions (l'audit permanent).
"""
from __future__ import annotations

import asyncio
import collections
import datetime as dt
import re

import discord
from discord import app_commands
from discord.ext import commands

from .. import config, store

INVITE_RE = re.compile(r"(discord\.gg/|discord\.com/invite/)", re.I)
SPAM_WINDOW_S, SPAM_MAX_MSGS = 10, 6
MENTION_MAX = 4


def _mod_log_guild(guild: discord.Guild) -> discord.TextChannel | None:
    """Le salon de log : DISCORD_MOD_LOG_CHANNEL du .env, sinon un salon nommé logs."""
    if config.DISCORD_MOD_LOG_CHANNEL:
        ch = guild.get_channel(int(config.DISCORD_MOD_LOG_CHANNEL))
        return ch if isinstance(ch, discord.TextChannel) else None
    return discord.utils.get(guild.text_channels, name="logs")


async def _log(guild: discord.Guild | None, embed: discord.Embed) -> None:
    if guild:
        ch = _mod_log_guild(guild)
        if ch:
            try:
                await ch.send(embed=embed)
            except discord.Forbidden:
                pass
    store.mod_db(embed.title or "action", str(guild.id) if guild else "",
                 embed.fields[0].value if embed.fields else "",
                 embed.fields[1].value if len(embed.fields) > 1 else "",
                 embed.fields[2].value if len(embed.fields) > 2 else "")


def _embed(action: str, mod: discord.Member, target: str, reason: str,
           detail: str = "") -> discord.Embed:
    e = discord.Embed(title=action, color=0xED4245, timestamp=dt.datetime.now(dt.UTC))
    e.add_field(name="modérateur", value=str(mod))
    e.add_field(name="cible", value=str(target))
    e.add_field(name="raison", value=reason or "—")
    if detail:
        e.description = detail
    return e


def _check_mod(inter: discord.Interaction, target: discord.Member | None = None) -> str | None:
    """Le garde-fou : le modérateur a le droit, et il ne modère pas au-dessus de lui."""
    if not isinstance(inter.user, discord.Member) or \
            not inter.user.guild_permissions.manage_messages:
        return "il faut la permission Gérer les messages pour modérer"
    if target is not None and not inter.user.guild_permissions.administrator:
        if target.guild_permissions.administrator or \
                target.top_role >= inter.user.top_role:
            return "tu ne peux pas modérer un membre au-dessus de ton rôle"
    return None


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._msg_times: dict[int, collections.deque] = collections.defaultdict(collections.deque)

    # ——— les commandes mod ———

    @app_commands.command(name="kick", description="Exclure un membre")
    @app_commands.describe(member="le membre", reason="la raison")
    async def kick(self, inter: discord.Interaction, member: discord.Member,
                   reason: str = "—") -> None:
        if err := _check_mod(inter, member):
            await inter.response.send_message(err, ephemeral=True)
            return
        await _log(inter.guild, _embed("KICK", inter.user, str(member), reason))
        await member.kick(reason=reason)
        await inter.response.send_message(f"👢 {member.mention} exclu — {reason}")

    @app_commands.command(name="ban", description="Bannir un membre (purge optionnelle des messages)")
    @app_commands.describe(member="le membre", purge_days="jours de messages à purger (0-7)", reason="la raison")
    async def ban(self, inter: discord.Interaction, member: discord.Member,
                  purge_days: app_commands.Range[int, 0, 7] = 0, reason: str = "—") -> None:
        if err := _check_mod(inter, member):
            await inter.response.send_message(err, ephemeral=True)
            return
        await _log(inter.guild, _embed("BAN", inter.user, str(member), reason,
                                       f"purge {purge_days} j"))
        await member.ban(delete_message_days=purge_days, reason=reason)
        await inter.response.send_message(f"🔨 {member.mention} banni — {reason}")

    @app_commands.command(name="unban", description="Débannir par id")
    async def unban(self, inter: discord.Interaction, user_id: str, reason: str = "—") -> None:
        if err := _check_mod(inter):
            await inter.response.send_message(err, ephemeral=True)
            return
        user = await self.bot.fetch_user(int(user_id))
        await inter.guild.unban(user, reason=reason)
        await _log(inter.guild, _embed("UNBAN", inter.user, str(user), reason))
        await inter.response.send_message(f"✅ {user} débanni")

    @app_commands.command(name="timeout", description="Muter un membre (minutes)")
    async def timeout(self, inter: discord.Interaction, member: discord.Member,
                      minutes: app_commands.Range[int, 1, 40320], reason: str = "—") -> None:
        if err := _check_mod(inter, member):
            await inter.response.send_message(err, ephemeral=True)
            return
        until = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await _log(inter.guild, _embed("TIMEOUT", inter.user, str(member), reason,
                                       f"{minutes} min"))
        await inter.response.send_message(f"🔇 {member.mention} muté {minutes} min — {reason}")

    @app_commands.command(name="untimeout", description="Retirer le mute")
    async def untimeout(self, inter: discord.Interaction, member: discord.Member) -> None:
        if err := _check_mod(inter, member):
            await inter.response.send_message(err, ephemeral=True)
            return
        await member.timeout(None)
        await _log(inter.guild, _embed("UNTIMEOUT", inter.user, str(member), ""))
        await inter.response.send_message(f"🔊 {member.mention} démuté")

    @app_commands.command(name="clear", description="Purger les N derniers messages du salon")
    async def clear(self, inter: discord.Interaction,
                    count: app_commands.Range[int, 1, 200],
                    member: discord.Member | None = None) -> None:
        if err := _check_mod(inter):
            await inter.response.send_message(err, ephemeral=True)
            return
        def only(m: discord.Message) -> bool:
            return member is None or m.author == member
        deleted = await inter.channel.purge(limit=count, check=only, bulk=True)
        await _log(inter.guild, _embed("CLEAR", inter.user, str(member or inter.channel),
                                       f"{len(deleted)} messages purgés"))
        await inter.response.send_message(f"🧹 {len(deleted)} messages purgés", ephemeral=True)

    @app_commands.command(name="warn", description="Avertir un membre (les warns s'accumulent)")
    async def warn(self, inter: discord.Interaction, member: discord.Member,
                   reason: str = "—") -> None:
        if err := _check_mod(inter, member):
            await inter.response.send_message(err, ephemeral=True)
            return
        store.mod_db("warn", str(inter.guild.id), str(inter.user.id),
                     str(member.id), reason)
        n = len(store.warns_of(str(inter.guild.id), str(member.id)))
        escalation = ""
        # L'ÉCHELLE : 2 = mute 1 h · 3 = mute 24 h · 4 = kick · 5 = ban (l'auto-punition)
        if n == 2:
            await member.timeout(dt.datetime.now(dt.UTC) + dt.timedelta(hours=1), reason="échelle 2 warns")
            escalation = " → mute 1 h (échelle)"
        elif n == 3:
            await member.timeout(dt.datetime.now(dt.UTC) + dt.timedelta(hours=24), reason="échelle 3 warns")
            escalation = " → mute 24 h (échelle)"
        elif n == 4:
            await member.kick(reason="échelle 4 warns")
            escalation = " → KICK (échelle)"
        elif n >= 5:
            await member.ban(reason="échelle 5 warns")
            escalation = " → BAN (échelle)"
        await _log(inter.guild, _embed("WARN", inter.user, str(member), reason,
                                       f"total {n} warn(s){escalation}"))
        await inter.response.send_message(f"⚠️ {member.mention} averti ({n} warn(s)) — {reason}{escalation}")

    @app_commands.command(name="warns", description="Les warns d'un membre")
    async def warns(self, inter: discord.Interaction, member: discord.Member) -> None:
        if err := _check_mod(inter):
            await inter.response.send_message(err, ephemeral=True)
            return
        rows = store.warns_of(str(inter.guild.id), str(member.id))
        txt = "\n".join(f"• {r[0] and dt.datetime.fromtimestamp(r[0], dt.UTC).date()} — {r[1]}"
                        for r in rows) or "aucun warn"
        await inter.response.send_message(f"⚠️ {member.mention} : {txt}", ephemeral=True)

    @app_commands.command(name="slowmode", description="Le mode lent du salon (secondes, 0 = off)")
    async def slowmode(self, inter: discord.Interaction,
                       channel: discord.TextChannel,
                       seconds: app_commands.Range[int, 0, 21600] = 5) -> None:
        if err := _check_mod(inter):
            await inter.response.send_message(err, ephemeral=True)
            return
        await channel.edit(slowmode_delay=seconds)
        await _log(inter.guild, _embed("SLOWMODE", inter.user, f"#{channel.name}",
                                       f"{seconds} s"))
        await inter.response.send_message(f"🐢 #{channel.name} : slowmode {seconds} s")

    @app_commands.command(name="lock", description="Verrouiller un salon (anti-raid)")
    async def lock(self, inter: discord.Interaction, channel: discord.TextChannel) -> None:
        if err := _check_mod(inter):
            await inter.response.send_message(err, ephemeral=True)
            return
        await channel.set_permissions(inter.guild.default_role, send_messages=False)
        await _log(inter.guild, _embed("LOCK", inter.user, f"#{channel.name}", ""))
        await inter.response.send_message(f"🔒 #{channel.name} verrouillé")

    @app_commands.command(name="unlock", description="Déverrouiller un salon")
    async def unlock(self, inter: discord.Interaction, channel: discord.TextChannel) -> None:
        if err := _check_mod(inter):
            await inter.response.send_message(err, ephemeral=True)
            return
        await channel.set_permissions(inter.guild.default_role, send_messages=None)
        await _log(inter.guild, _embed("UNLOCK", inter.user, f"#{channel.name}", ""))
        await inter.response.send_message(f"🔓 #{channel.name} déverrouillé")

    @app_commands.command(name="role", description="Ajouter/retirer un rôle (add/remove)")
    async def role(self, inter: discord.Interaction, action: str, member: discord.Member,
                   role: discord.Role) -> None:
        if err := _check_mod(inter, member):
            await inter.response.send_message(err, ephemeral=True)
            return
        if action == "add":
            await member.add_roles(role, reason=f"par {inter.user}")
        elif action == "remove":
            await member.remove_roles(role, reason=f"par {inter.user}")
        else:
            await inter.response.send_message("action = add ou remove", ephemeral=True)
            return
        await _log(inter.guild, _embed(f"ROLE {action.upper()}", inter.user,
                                       str(member), f"{role.name}"))
        await inter.response.send_message(f"🎭 {role.name} → {action} sur {member.mention}")

    @app_commands.command(name="modlog", description="Les dernières actions de modération")
    async def modlog(self, inter: discord.Interaction) -> None:
        if err := _check_mod(inter):
            await inter.response.send_message(err, ephemeral=True)
            return
        con = store.connect()
        try:
            rows = con.execute("SELECT ts, action, moderator_id, target_id, reason "
                               "FROM d_mod_actions ORDER BY ts DESC LIMIT 15").fetchall()
        finally:
            con.close()
        txt = "\n".join(f"• {dt.datetime.fromtimestamp(r['ts'], dt.UTC):%d/%m %H:%M} "
                        f"[{r['action']}] {r['moderator_id']} → {r['target_id']} : {r['reason']}"
                        for r in rows) or "aucune action"
        await inter.response.send_message(f"**Mod log (15 dernières)** :\n{txt}", ephemeral=True)

    # ——— l'auto-mod ———

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not isinstance(message.author, discord.Member) \
                or message.author.guild_permissions.administrator:
            return
        now = dt.datetime.now(dt.UTC).timestamp()
        dq = self._msg_times[message.author.id]
        dq.append(now)
        while dq and dq[0] < now - SPAM_WINDOW_S:
            dq.popleft()
        # anti-invite : les liens discord.gg se suppriment (hors admins/mods)
        if INVITE_RE.search(message.content or ""):
            await message.delete()
            await _log(message.guild, _embed("AUTO-INVITE", self.bot.user or "auto-mod",
                                             str(message.author), "lien d'invitation supprimé"))
            return
        # anti-mention-spam : 4+ mentions = purge + mute 5 min
        if len(message.mentions) >= MENTION_MAX:
            await message.delete()
            await message.author.timeout(dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
                                         reason="mention-spam (auto-mod)")
            await _log(message.guild, _embed("AUTO-MENTION-SPAM", self.bot.user or "auto-mod",
                                             str(message.author), "purge + mute 5 min"))
            return
        # anti-spam : 6+ messages en 10 s = mute 5 min
        if len(dq) > SPAM_MAX_MSGS:
            await message.author.timeout(dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
                                         reason="spam (auto-mod)")
            await _log(message.guild, _embed("AUTO-SPAM", self.bot.user or "auto-mod",
                                             str(message.author),
                                             f"{SPAM_MAX_MSGS} msgs en {SPAM_WINDOW_S} s → mute 5 min"))
            self._msg_times[message.author.id].clear()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        arrival = discord.utils.get(member.guild.text_channels, name="🔔-salon-arrivée") \
            or discord.utils.get(member.guild.text_channels, name="général")
        if arrival:
            await arrival.send(f"👋 Bienvenue {member.mention} sur **{member.guild.name}** — "
                               f"lis #⚖️-règles et présente-toi. Membre n°{member.guild.member_count}.")
        await _log(member.guild, _embed("JOIN", self.bot.user or "auto-mod",
                                        str(member), f"membre n°{member.guild.member_count}"))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await _log(member.guild, _embed("LEAVE", self.bot.user or "auto-mod",
                                        str(member), ""))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
