"""Le cog MEMBRES & RÔLES — la mémoire du serveur.

La sync complète au démarrage (guild.chunk), puis le suivi en direct : join, leave,
changement de rôles, de pseudo. Chaque membre et chaque rôle vivent dans discord.db
(d_members, d_roles) — le bot CONNAÎT son serveur, il ne le redécouvre pas.

Les commandes : /whois (le dossier complet d'un membre), /roles (la hiérarchie avec
les effectifs), /recherche (trouver un membre par fragment de nom).
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import config, store


def _roles_json(member: discord.Member) -> list[str]:
    return [f"{r.name}({r.id})" for r in member.roles if r != member.guild.default_role]


class Members(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sync_loop.start()

    def cog_unload(self) -> None:
        self.sync_loop.cancel()

    @tasks.loop(hours=6)
    async def sync_loop(self) -> None:
        """La resync complète toutes les 6 h — la mémoire ne dérive jamais."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            await self._sync_guild(guild)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            await self._sync_guild(guild)

    async def _sync_guild(self, guild: discord.Guild) -> None:
        print(f"[membres] sync {guild.name} : {guild.member_count} membres, {len(guild.roles)} rôles", flush=True)
        # FIX 05/10 : guild.chunk() pend indéfiniment quand le cache est déjà complet
        # (quirk discord.py 2.7.1 — l'event CHUNK n'arrive jamais). Le cache avec
        # l'intent members EST la liste complète : on ne bloque plus dessus.
        try:
            await asyncio.wait_for(guild.chunk(), timeout=10)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — le cache suffit
            pass
        for member in guild.members:
            store.member_upsert(str(member.id), str(member),
                                member.display_name, member.bot,
                                member.joined_at.isoformat() if member.joined_at else None,
                                member.created_at.isoformat(),
                                _roles_json(member))
        for role in sorted(guild.roles, key=lambda r: -r.position):
            store.role_upsert(str(role.id), role.name, role.position,
                              f"#{role.color.value:06x}" if role.color.value else "#000000",
                              str(role.permissions.value), len(role.members))
        print(f"[membres] sync {guild.name} : {guild.member_count} membres, "
              f"{len(guild.roles)} rôles")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        store.member_upsert(str(member.id), str(member), member.display_name,
                            member.bot,
                            member.joined_at.isoformat() if member.joined_at else None,
                            member.created_at.isoformat(), _roles_json(member))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        con = store.connect()
        try:
            con.execute("DELETE FROM d_members WHERE user_id=?", (str(member.id),))
            con.commit()
        finally:
            con.close()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if (before.roles != after.roles or before.display_name != after.display_name
                or before.nick != after.nick):
            store.member_upsert(str(after.id), str(after), after.display_name,
                                after.bot,
                                after.joined_at.isoformat() if after.joined_at else None,
                                after.created_at.isoformat(), _roles_json(after))

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        store.role_upsert(str(after.id), after.name, after.position,
                          f"#{after.color.value:06x}" if after.color.value else "#000000",
                          str(after.permissions.value), len(after.members))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        store.role_upsert(str(role.id), role.name, role.position,
                          f"#{role.color.value:06x}" if role.color.value else "#000000",
                          str(role.permissions.value), len(role.members))

    # ——— les commandes de connaissance ———

    @app_commands.command(name="whois",
                          description="Le dossier complet d'un membre")
    async def whois(self, inter: discord.Interaction, member: discord.Member) -> None:
        con = store.connect()
        try:
            row = con.execute("SELECT * FROM d_members WHERE user_id=?",
                              (str(member.id),)).fetchone()
            cases = con.execute("SELECT COUNT(*) FROM d_cases WHERE user_id=?",
                                (str(member.id),)).fetchone()[0]
            msgs = con.execute("SELECT COUNT(*) FROM d_messages WHERE author_id=?",
                               (str(member.id),)).fetchone()[0]
            warns = con.execute("SELECT COUNT(*) FROM d_mod_actions WHERE action='warn' "
                                "AND target_id=?", (str(member.id),)).fetchone()[0]
        finally:
            con.close()
        age = (dt.datetime.now(dt.UTC) - member.created_at).total_seconds() / 86400
        e = discord.Embed(title=f"📋 {member.display_name}", color=member.color)
        e.add_field(name="membre", value=f"{member} (`{member.id}`)")
        e.add_field(name="compte créé il y a", value=f"{age:.0f} j")
        e.add_field(name="a rejoint",
                    value=member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "?")
        roles = [r.name for r in member.roles if r != member.guild.default_role]
        e.add_field(name="rôles", value=", ".join(roles[::-1]) or "—", inline=False)
        e.add_field(name="messages capturés", value=f"{msgs:,}")
        e.add_field(name="cases / warns", value=f"{cases} / {warns}")
        if row:
            seen = row["last_seen"]
            e.set_footer(text=f"dernière sync : {seen[:16] if seen else '?'} UTC")
        await inter.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="roles", description="La hiérarchie des rôles avec les effectifs")
    async def roles(self, inter: discord.Interaction) -> None:
        con = store.connect()
        try:
            rows = con.execute("SELECT name, member_count, color FROM d_roles "
                               "ORDER BY position DESC LIMIT 25").fetchall()
        finally:
            con.close()
        lines = [f"• **{r['name']}** — {r['member_count']} membre(s)" for r in rows]
        await inter.response.send_message("**🎭 Les rôles du serveur :**\n" + "\n".join(lines),
                                          ephemeral=True)

    @app_commands.command(name="recherche", description="Trouver un membre par fragment de nom")
    async def recherche(self, inter: discord.Interaction, nom: str) -> None:
        con = store.connect()
        try:
            rows = con.execute("SELECT user_id, display_name, user_name FROM d_members "
                               "WHERE display_name LIKE ? OR user_name LIKE ? LIMIT 15",
                               (f"%{nom}%", f"%{nom}%")).fetchall()
        finally:
            con.close()
        txt = "\n".join(f"• {r['display_name']} ({r['user_name']}) — `{r['user_id']}`"
                        for r in rows) or "aucun membre trouvé"
        await inter.response.send_message(f"**🔍 « {nom} » :**\n{txt}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Members(bot))
