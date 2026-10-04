"""Le cog CARTE DU SERVEUR — l'intelligence des salons et des rôles.

Le user déclare UNE FOIS : les salons fonctionnels (log, bienvenue, commandes), les rôles
(admin, mod), et les règles par salon (no_links, media_only, commands_only). TOUT le bot
lira ce registre — la modération, l'auto-mod, les logs — au lieu de deviner par les noms.

Les listeners on_guild_channel_* et on_guild_role_* tracent les changements de structure
dans #logs : la carte vit avec le serveur. /map montre tout.
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from .. import store

KINDS_CHANNEL = {"log": "le salon des logs de modération",
                 "bienvenue": "le salon des arrivées",
                 "commandes": "le salon réservé aux commandes"}
KINDS_ROLE = {"admin": "les rôles administrateurs",
              "mod": "les rôles modérateurs"}
RULES = {"no_links": "les liens y sont supprimés",
         "media_only": "seuls les messages avec image/vidéo y passent",
         "commands_only": "seuls les slash commands y sont tolérés (le texte est purgé)"}


def is_mod(inter: discord.Interaction) -> bool:
    """Modérateur = la permission native OU un rôle enregistré 'mod'."""
    if not isinstance(inter.user, discord.Member):
        return False
    if inter.user.guild_permissions.manage_messages:
        return True
    return store.reg_has_role([r.id for r in inter.user.roles],
                              inter.guild_id or 0, "mod")


def is_admin(inter: discord.Interaction) -> bool:
    if not isinstance(inter.user, discord.Member):
        return False
    if inter.user.guild_permissions.administrator:
        return True
    return store.reg_has_role([r.id for r in inter.user.roles],
                              inter.guild_id or 0, "admin")


class ServerMap(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ——— les déclarations ———

    @app_commands.command(name="setchannel")
    @app_commands.describe(kind="la fonction du salon", channel="le salon")
    @app_commands.choices(kind=[app_commands.Choice(name=f"{k} — {v}", value=k)
                                for k, v in KINDS_CHANNEL.items()])
    async def setchannel(self, inter: discord.Interaction, kind: app_commands.Choice[str],
                         channel: discord.TextChannel) -> None:
        if not is_admin(inter):
            await inter.response.send_message("réservé aux admins (ou rôles admin enregistrés)",
                                              ephemeral=True)
            return
        store.reg_set(inter.guild_id, f"channel_{kind.value}", str(channel.id),
                      channel.name)
        await inter.response.send_message(
            f"📌 #{channel.name} = salon **{kind.value}** ({KINDS_CHANNEL[kind.value]})",
            ephemeral=True)

    @app_commands.command(name="setrole")
    @app_commands.describe(kind="admin ou mod", role="le rôle à enregistrer")
    @app_commands.choices(kind=[app_commands.Choice(name=f"{k} — {v}", value=k)
                                for k, v in KINDS_ROLE.items()])
    async def setrole(self, inter: discord.Interaction, kind: app_commands.Choice[str],
                      role: discord.Role) -> None:
        if not is_admin(inter):
            await inter.response.send_message("réservé aux admins", ephemeral=True)
            return
        store.reg_set(inter.guild_id, f"role_{kind.value}", str(role.id), role.name)
        await inter.response.send_message(
            f"🎭 le rôle **{role.name}** est enregistré comme {kind.value} "
            f"({KINDS_ROLE[kind.value]})", ephemeral=True)

    @app_commands.command(name="setrule")
    @app_commands.describe(rule="la règle", channel="le salon cible",
                           state="on ou off")
    @app_commands.choices(rule=[app_commands.Choice(name=f"{k} — {v}", value=k)
                                for k, v in RULES.items()])
    async def setrule(self, inter: discord.Interaction, rule: app_commands.Choice[str],
                      channel: discord.TextChannel, state: str) -> None:
        if not is_admin(inter):
            await inter.response.send_message("réservé aux admins", ephemeral=True)
            return
        if state not in ("on", "off"):
            await inter.response.send_message("state = on ou off", ephemeral=True)
            return
        if state == "on":
            store.reg_set(inter.guild_id, f"rule_{rule.value}", str(channel.id),
                          channel.name)
        else:
            store.reg_del(inter.guild_id, f"rule_{rule.value}", str(channel.id))
        await inter.response.send_message(
            f"⚖ #{channel.name} : {rule.value} = **{state.upper()}** "
            f"({RULES[rule.value]})", ephemeral=True)

    # ——— la carte ———

    @app_commands.command(name="map", description="La carte vivante du serveur (salons, rôles, règles)")
    async def map_cmd(self, inter: discord.Interaction) -> None:
        guild = inter.guild
        lines = [f"**🗺 La carte de « {guild.name} »**"]
        for cat, channels in _by_category(guild):
            lines.append(f"\n**📁 {cat}**")
            for ch in channels:
                tags = []
                for kind in KINDS_CHANNEL:
                    if store.reg_channel(guild.id, kind) == ch.id:
                        tags.append(kind)
                rules = [rule for rule in RULES if store.reg_rule(guild.id, ch.id, rule)]
                if rules:
                    tags += rules
                suffix = f" — 🏷 {' · '.join(tags)}" if tags else ""
                lines.append(f"  • #{ch.name} ({ch.id}){suffix}")
        roles = {f"role_{k}": k for k in KINDS_ROLE}
        for reg, kind in roles.items():
            entries = store.reg_get(guild.id, reg)
            if entries:
                names = ", ".join(f"<@&{r['target']}>" for r in entries)
                lines.append(f"\n🎭 rôles {kind} : {names}")
        await inter.response.send_message("\n".join(lines)[:1900], ephemeral=True)

    # ——— la carte vit avec le serveur ———

    async def _structure_changed(self, guild: discord.Guild, what: str) -> None:
        ch = discord.utils.get(guild.text_channels, name="logs") \
            or discord.utils.get(guild.text_channels,
                                 id=store.reg_channel(guild.id, "log") or 0)
        if ch:
            try:
                await ch.send(f"🗺 **structure du serveur modifiée** : {what}")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._structure_changed(channel.guild, f"salon créé : **{channel.name}**")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._structure_changed(channel.guild, f"salon supprimé : **{channel.name}**")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel,
                                      after: discord.abc.GuildChannel) -> None:
        if before.name != after.name:
            await self._structure_changed(after.guild,
                                           f"salon renommé : {before.name} → **{after.name}**")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._structure_changed(role.guild, f"rôle créé : **{role.name}**")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._structure_changed(role.guild, f"rôle supprimé : **{role.name}**")

    @app_commands.command(name="acces",
                          description="La matrice des accès d'un salon (rôles, overwrites, mes droits)")
    async def acces(self, inter: discord.Interaction, channel: discord.TextChannel) -> None:
        if not is_admin(inter):
            await inter.response.send_message("réservé aux admins", ephemeral=True)
            return
        me = inter.guild.me
        mine = channel.permissions_for(me)
        mes_droits = [n for n, ok in (("voir", mine.view_channel),
                                      ("écrire", mine.send_messages),
                                      ("historique", mine.read_message_history),
                                      ("gérer le salon", mine.manage_channels),
                                      ("purger", mine.manage_messages))
                      if ok]
        lines = [f"**🔐 Les accès de #{channel.name}**",
                 f"• mes droits : {', '.join(mes_droits) or 'AUCUN'}"]
        for target, ow in sorted(channel.overwrites.items(), key=lambda kv: str(kv[0])):
            if target.is_default():
                name = "@everyone"
            else:
                name = f"@{target.name}"
            allow = [perm for perm, val in ow if val is True]
            deny = [perm for perm, val in ow if val is False]
            if allow or deny:
                lines.append(f"• {name} : ✅ {', '.join(allow) or '—'} | "
                             f"❌ {', '.join(deny) or '—'}")
        await inter.response.send_message("\n".join(lines)[:1900], ephemeral=True)


def _by_category(guild: discord.Guild) -> list[tuple[str, list[discord.TextChannel]]]:
    out: dict[str, list[discord.TextChannel]] = {}
    for ch in sorted(guild.text_channels, key=lambda c: (c.category_id or 0, c.position)):
        out.setdefault(ch.category.name if ch.category else "sans catégorie", []).append(ch)
    return list(out.items())


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerMap(bot))
