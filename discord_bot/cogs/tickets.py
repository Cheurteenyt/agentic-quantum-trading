"""Les TICKETS — le support asynchrone (le module n°2 de l'analyse d'écart).

/ticket → un salon privé sous la catégorie Tickets (l'utilisateur + le staff
seulement), un bouton « Fermer » ; la fermeture archive le compte des messages
(les messages eux-mêmes sont déjà capturés par capture.py dans d_messages) et
trace open/close dans d_mod_actions. Zéro schéma nouveau : le registre porte
l'anti-doublon (`ticket_open`), le compteur (`ticket_counter`) et la catégorie
(`channel_tickets`).
"""
from __future__ import annotations

import re

import discord
from discord.ext import commands

from discord_bot import store

NAME_MAX = 80


# ——— les helpers purs (testés) ———


def slugify(name: str) -> str:
    """Le nom de salon : minuscules, les non-alnum → tirets, borné à NAME_MAX."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug or "membre")[:NAME_MAX].rstrip("-")


def next_counter(value: str | None) -> int:
    """Le compteur de tickets : '7' → 8, vide/pourri → 1."""
    try:
        return int(value) + 1
    except (ValueError, TypeError):
        return 1


# ——— le cog ———


class CloseTicket(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger,
                       emoji="🔒", custom_id="ce_ticket_close")
    async def close(self, interaction: discord.Interaction,
                    button: discord.ui.Button) -> None:
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel) or not ch.name.startswith("ticket-"):
            await interaction.response.send_message("ce bouton vit dans un ticket",
                                                    ephemeral=True)
            return
        if not await Tickets.can_manage(interaction):
            await interaction.response.send_message(
                "réservé au staff ou au propriétaire du ticket", ephemeral=True)
            return
        await interaction.response.defer()
        n = sum(1 async for _ in ch.history(limit=None, oldest_first=True))
        mod = Tickets._mod_db
        mod("ticket_close", str(ch.guild.id), str(interaction.user.id),
            Tickets._owner_of(ch) or "?", f"{ch.name} · {n} message(s) archivé(s)")
        await ch.send("🔒 Fermeture dans 5 secondes — tout est archivé.")
        await interaction.delete_original_response()
        guild, uid = ch.guild, Tickets._owner_of(ch)
        await ch.delete(reason="ticket fermé")
        if uid:
            store.reg_del(guild.id, "ticket_open", str(uid))


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    def _mod_db(action: str, guild_id: str, moderator_id: str, target_id: str,
                detail: str) -> None:
        store.mod_db(action, guild_id, moderator_id, target_id, "ticket", detail)

    @staticmethod
    def _owner_of(channel: discord.TextChannel) -> str | None:
        """L'id du propriétaire : l'unique membre non-staff avec le view allow."""
        for target, ow in channel.overwrites.items():
            if isinstance(target, discord.Member) and ow.view_channel is True:
                if not target.bot and not target.guild_permissions.administrator:
                    return str(target.id)
        return None

    @staticmethod
    async def can_manage(interaction: discord.Interaction) -> bool:
        u = interaction.user
        if not isinstance(u, discord.Member):
            return False
        if u.guild_permissions.administrator:
            return True
        wanted = {int(r["target"]) for kind in ("admin", "mod")
                  for r in store.reg_get(interaction.guild_id, f"role_{kind}")}
        return bool(wanted & {r.id for r in u.roles}) or Tickets._owner_of(
            interaction.channel) == str(u.id)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # les vues persistent après un restart (le custom_id rebranche)
        self.bot.add_view(CloseTicket())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.GuildChannel) -> None:
        # un salon de ticket supprimé à la main → l'anti-doublon est libéré
        if isinstance(channel, discord.TextChannel) and channel.name.startswith("ticket-"):
            owner = self._owner_of(channel)
            if owner:
                store.reg_del(channel.guild.id, "ticket_open", owner)

    @commands.command(name="ticket")
    @commands.guild_only()
    async def ticket_prefix(self, ctx: commands.Context, *, raison: str = "sans raison") -> None:
        await self._open(ctx.author, raison, ctx.message)

    @discord.app_commands.command(name="ticket",
                                  description="Ouvre un ticket privé avec le staff")
    @discord.app_commands.describe(raison="Le sujet du ticket")
    async def ticket(self, inter: discord.Interaction, raison: str) -> None:
        await inter.response.defer(ephemeral=True)
        await self._open(inter.user, raison, None, inter)

    async def _open(self, user, raison: str, prefix_msg=None, inter=None) -> None:
        guild = user.guild
        if store.reg_get(guild.id, "ticket_open") and \
                any(r["target"] == str(user.id) for r in store.reg_get(guild.id, "ticket_open")):
            msg = "tu as déjà un ticket ouvert — je le référence ci-dessus"
            if inter:
                await inter.followup.send(msg, ephemeral=True)
            elif prefix_msg:
                await prefix_msg.reply(msg)
            return
        rows = store.reg_get(guild.id, "ticket_counter")
        n = next_counter(rows[0]["value"] if rows else None)
        store.reg_set(guild.id, "ticket_counter", str(n), str(n))

        cat = None
        cid = store.reg_channel(guild.id, "tickets")
        cat = guild.get_channel(cid) if cid else None
        if cat is None:
            cat = discord.utils.get(guild.categories, name="Tickets") \
                or await guild.create_category("Tickets", reason="le support")
            store.reg_set(guild.id, "channel_tickets", str(cat.id), cat.name)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                              read_message_history=True),
        }
        for kind in ("admin", "mod"):
            for r in store.reg_get(guild.id, f"role_{kind}"):
                role = guild.get_role(int(r["target"]))
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, read_message_history=True)
        try:
            ch = await guild.create_text_channel(
                f"ticket-{n:03d}-{slugify(user.name)}", category=cat,
                overwrites=overwrites, reason=f"ticket : {raison[:80]}")
        except discord.Forbidden:
            msg = "je ne peux pas créer le salon de ticket (permissions manquantes)"
            if inter:
                await inter.followup.send(msg, ephemeral=True)
            elif prefix_msg:
                await prefix_msg.reply(msg)
            return
        store.reg_set(guild.id, "ticket_open", str(user.id), str(ch.id))
        self._mod_db("ticket_open", str(guild.id), str(self.bot.user.id),
                     str(user.id), f"{ch.mention} · {raison[:80]}")
        e = discord.Embed(
            title=f"Ticket #{n:03d} — {user.display_name}",
            description=f"**Sujet :** {raison}\n\nLe staff est notifié. Décris ta "
                        f"demande ici — tout est archivé, y compris ce qui est supprimé.",
            color=discord.Color.Blurple())
        e.set_footer(text="🔒 Fermer = le bouton — le staff et toi pouvez le faire")
        await ch.send(content=user.mention, embed=e, view=CloseTicket())
        msg = f"ton ticket est ouvert : {ch.mention}"
        if inter:
            await inter.followup.send(msg, ephemeral=True)
        elif prefix_msg:
            await prefix_msg.reply(msg)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
