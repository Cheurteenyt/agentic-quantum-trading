"""Le cog CARTE DU SERVEUR — l'intelligence des salons et des rôles.

Le user déclare UNE FOIS : les salons fonctionnels (log, bienvenue, commandes), les rôles
(admin, mod), et les règles par salon (no_links, media_only, commands_only). TOUT le bot
lira ce registre — la modération, l'auto-mod, les logs — au lieu de deviner par les noms.

Les listeners on_guild_channel_* et on_guild_role_* tracent les changements de structure
dans #logs : la carte vit avec le serveur. /map montre tout.
"""
from __future__ import annotations

import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import store

KINDS_CHANNEL = {"log": "le salon des logs de modération",
                 "bienvenue": "le salon des arrivées",
                 "commandes": "le salon réservé aux commandes",
                 "arrivee": "le salon où les Probatants peuvent parler (le portier)",
                 "tickets": "la catégorie des tickets (le support)"}
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
        self.access_loop.start()

    def cog_unload(self) -> None:
        self.access_loop.cancel()

    # ——— le monitor d'accès AUTONOME (ce que le screenshot montre, en continu) ———

    def _access_snapshot(self, guild: discord.Guild) -> list[dict]:
        """Pour chaque salon : privé ?, sync catégorie ?, QUI a accès (rôles + membres)."""
        out = []
        for ch in guild.channels:
            if not isinstance(ch, (discord.TextChannel, discord.ForumChannel,
                                   discord.VoiceChannel)):
                continue
            base = ch.overwrites_for(guild.default_role)
            private = base.view_channel is False
            access = []
            for target, ow in ch.overwrites.items():
                if ow.view_channel is True:
                    access.append(f"{type(target).__name__}:{target.name}")
            try:
                viewers = [m.mention for m in guild.members
                           if ch.permissions_for(m).view_channel][:20]
            except Exception:
                viewers = []
            out.append({
                "channel_id": str(ch.id), "channel_name": ch.name,
                "private": int(private),
                "synced": int(ch.permissions_synced),
                "access_json": "; ".join(access) or "@everyone",
                "viewers": "; ".join(viewers),
            })
        return out

    async def _upsert_access(self, guild: discord.Guild, snap: dict,
                             log_ch: discord.TextChannel | None) -> None:
        con = store.connect()
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS d_access (
                channel_id TEXT PRIMARY KEY, channel_name TEXT,
                private INTEGER, synced INTEGER, access_json TEXT,
                viewers TEXT, updated_at REAL)""")
            prev = con.execute("SELECT private, synced, access_json, viewers "
                               "FROM d_access WHERE channel_id=?",
                               (snap["channel_id"],)).fetchone()
            digest = f"{snap['private']}|{snap['synced']}|{snap['access_json']}|{snap['viewers']}"
            now_ts = dt.datetime.now(dt.UTC).timestamp()
            if prev is None:
                con.execute("""INSERT INTO d_access
                    (channel_id, channel_name, private, synced, access_json,
                     viewers, updated_at) VALUES (?,?,?,?,?,?,?)""",
                    (snap["channel_id"], snap["channel_name"],
                     snap["private"], snap["synced"],
                     snap["access_json"], snap["viewers"], now_ts))
                con.commit()
                return  # la première cartographie ne crie pas
            old = f"{prev['private']}|{prev['synced']}|{prev['access_json']}|{prev['viewers']}"
            if old == digest:
                return
            con.execute("UPDATE d_access SET channel_name=?, private=?, synced=?, "
                        "access_json=?, viewers=?, updated_at=? WHERE channel_id=?",
                        (snap["channel_name"], snap["private"], snap["synced"],
                         snap["access_json"], snap["viewers"], now_ts,
                         snap["channel_id"]))
            con.commit()
            flags = []
            if prev["private"] != snap["private"]:
                flags.append("privé=" + ("ON" if snap["private"] else "OFF"))
            if prev["synced"] != snap["synced"]:
                flags.append("sync catégorie=" + ("ON" if snap["synced"] else "OFF"))
            if prev["access_json"] != snap["access_json"]:
                flags.append("les overwrites ont bougé")
            if prev["viewers"] != snap["viewers"]:
                flags.append("la liste des voyants a changé")
            if log_ch and flags:
                e = discord.Embed(
                    title=f"🔐 ACCÈS MODIFIÉ — #{snap['channel_name']}",
                    description=" · ".join(flags),
                    color=discord.Color.Orange(),
                    timestamp=dt.datetime.now(dt.UTC))
                e.add_field(name="accès actuels",
                            value=snap["access_json"][:1000] or "@everyone")
                try:
                    await log_ch.send(embed=e)
                except discord.Forbidden:
                    pass
        finally:
            con.close()

    @tasks.loop(minutes=30)
    async def access_loop(self) -> None:
        """La capture + la détection de changement : un accès qui bouge = un event de sécurité."""
        await self.bot.wait_until_ready()
        log_ch = None
        for guild in self.bot.guilds:
            log_ch = discord.utils.get(guild.text_channels, name="logs") \
                or discord.utils.get(guild.text_channels,
                                     id=store.reg_channel(guild.id, "log") or 0)
            for snap in self._access_snapshot(guild):
                try:
                    await self._upsert_access(guild, snap, log_ch)
                except Exception as exc:  # noqa: BLE001 — un salon ne tue pas la cartographie
                    print(f"[carte] accès {snap.get('channel_name')} : {exc}")

    @access_loop.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()

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
