"""Le PANNEAU — l'interface Discord-native (pas de site, pas de commandes).

Un message vivant posté par le bot (salon `commandes` par défaut) : l'embed se
met à jour tout seul (boucle 10 min) et les BOUTONS répondent en éphémère :
🏆 Classement · 📊 Mes calls · 👤 Mon profil. Les chiffres viennent de
stats.py — la même source que tout le reste. Le message est réinstallé tout
seul si quelqu'un le supprime.
"""
from __future__ import annotations

import asyncio

import discord
from discord.ext import commands, tasks

from discord_bot import stats, store
from discord_bot.cogs.brain import BrainModal

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


# ——— les embeds (le rendu partagé) ———


def classement_embed(rows: list[dict]) -> discord.Embed:
    e = discord.Embed(title="🏆 Classement des calls",
                      description="Min. 3 calls scorés · Σ des rendements 24 h réels",
                      color=discord.Color.blurple())
    if not rows:
        e.description += "\n\n*Pas encore 3 calls scorés par membre — poste tes calls dans les salons de trading.*"
        return e
    lignes = []
    for i, r in enumerate(rows, 1):
        med = MEDALS.get(i, f"**{i}.**")
        lignes.append(f"{med} **{r['author_name']}** — {r['n']} calls, "
                      f"WR {r['wr'] * 100:.0f} %, Σ {r['tot']:+.1f} %")
    e.add_field(name="Les meilleurs", value="\n".join(lignes), inline=False)
    return e


def mes_calls_embed(user: discord.Member | discord.User, st: dict) -> discord.Embed:
    e = discord.Embed(title=f"📊 Tes calls — {user.display_name}",
                      color=discord.Color.blurple())
    wr = f"{st['wr'] * 100:.0f} %" if st["wr"] is not None else "—"
    tot = f"{st['tot_ret']:+.1f} %" if st["tot_ret"] is not None else "—"
    e.description = f"{st['n_scored']} call(s) scoré(s) · WR **{wr}** · Σ **{tot}**"
    if st["calls"]:
        lignes = []
        for c in st["calls"][:8]:
            ret = f"{c['ret_pct']:+.1f} %" if c["scored"] else "*en cours*"
            arrow = "📈" if c["direction"] == "long" else "📉"
            lignes.append(f"{arrow} **{c['symbol']}** — {ret} — {(c['posted_at'] or '?')[:10]}")
        e.add_field(name="Les 8 derniers", value="\n".join(lignes), inline=False)
    else:
        e.description += "\n*Aucun call — poste-le dans les salons de trading ($TICKER + long/short).*"
    return e


def profil_embed(member: discord.Member, st: dict) -> discord.Embed:
    e = discord.Embed(title=f"👤 {member.display_name}",
                      color=member.top_role.color if member.top_role.color
                      else discord.Color.blurple())
    roles = [r.name for r in member.roles if not r.is_default()][:8]
    arrivée = member.joined_at.strftime("%d/%m/%Y") if member.joined_at else "?"
    e.description = (f"Arrivé le **{arrivée}** · **{st['n_messages']}** message(s) capturé(s)\n"
                     f"Rôles : {', '.join(roles) or '—'}")
    if st["n_scored"]:
        e.add_field(name="Calls scorés", value=f"{st['n_scored']} · WR "
                    f"{st['wr'] * 100:.0f} % · Σ {st['tot_ret']:+.1f} %")
    e.set_thumbnail(url=member.display_avatar.url)
    return e


def main_embed(guild: discord.Guild) -> discord.Embed:
    """L'embed vivant du panneau — la photo du serveur."""
    s = stats.server_stats()
    e = discord.Embed(title=f"🧭 Le panneau Core Equity",
                      color=discord.Color.blurple())
    e.description = ("**Les boutons ci-dessous = ton interface.** "
                     "Rien à taper, tout se clique.")
    snap = stats.market_snapshot()
    if snap:
        majors_line, _ = stats.market_lines(snap)
        e.add_field(name="📈 Le marché (24 h, prix réels)", value=majors_line,
                    inline=False)
    e.add_field(name="👥 Le serveur", value=f"{s['n_members']} membres · "
                f"{s['n_roles']} rôles", inline=True)
    e.add_field(name="📨 La capture", value=f"{s['m24']} msg / 24 h · "
                f"{s['m7']} / 7 j", inline=True)
    e.add_field(name="🚪 Le portier", value=f"{s['n_gate_pending']} en quarantaine",
                inline=True)
    top = stats.classement(limit=3)
    if top:
        e.add_field(name="🏆 Le podium",
                    value="\n".join(f"{MEDALS.get(i, f'{i}.')} **{r['author_name']}** — "
                                    f"{r['tot']:+.1f} %" for i, r in enumerate(top, 1)),
                    inline=False)
    if s["top_channels"]:
        e.add_field(name="💬 Les salons qui vivent (7 j)",
                    value=" · ".join(f"#{c['channel_name']} ({c['n']})"
                                     for c in s["top_channels"][:4]),
                    inline=False)
    e.set_footer(text="Actualisé toutes les 10 min · les données = la warehouse du bot")
    return e


def marche_embed(snap: dict) -> discord.Embed:
    majors_line, movers = stats.market_lines(snap)
    e = discord.Embed(title="📈 Le marché (24 h, klines 1h)",
                      description=majors_line, color=discord.Color.green())
    up, down = movers.split("\n")
    e.add_field(name="Les fortes hausses", value=up, inline=False)
    e.add_field(name="Les fortes baisses", value=down, inline=False)
    e.set_footer(text=f"{snap['n_symbols']} symboles suivis · la warehouse locale")
    return e


# ——— la vue persistante (les boutons) ———


class PanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Classement", style=discord.ButtonStyle.primary,
                       emoji="🏆", custom_id="ce_panel_classement")
    async def classement(self, interaction: discord.Interaction,
                         button: discord.ui.Button) -> None:
        rows = stats.classement(limit=10)
        await interaction.response.send_message(embed=classement_embed(rows),
                                                ephemeral=True)

    @discord.ui.button(label="Mes calls", style=discord.ButtonStyle.secondary,
                       emoji="📊", custom_id="ce_panel_mescalls")
    async def mes_calls(self, interaction: discord.Interaction,
                        button: discord.ui.Button) -> None:
        st = stats.user_stats(str(interaction.user.id))
        await interaction.response.send_message(
            embed=mes_calls_embed(interaction.user, st), ephemeral=True)

    @discord.ui.button(label="Mon profil", style=discord.ButtonStyle.secondary,
                       emoji="👤", custom_id="ce_panel_profil")
    async def profil(self, interaction: discord.Interaction,
                     button: discord.ui.Button) -> None:
        st = stats.user_stats(str(interaction.user.id))
        await interaction.response.send_message(
            embed=profil_embed(interaction.user, st), ephemeral=True)

    @discord.ui.button(label="Marché", style=discord.ButtonStyle.success,
                       emoji="📈", custom_id="ce_panel_marche")
    async def marche(self, interaction: discord.Interaction,
                     button: discord.ui.Button) -> None:
        snap = stats.market_snapshot()
        if snap is None:
            await interaction.response.send_message(
                "📈 la warehouse dort (pas de klines récentes) — réessaie plus tard.",
                ephemeral=True)
            return
        await interaction.response.send_message(embed=marche_embed(snap), ephemeral=True)

    @discord.ui.button(label="Demander", style=discord.ButtonStyle.primary,
                       emoji="🧠", custom_id="ce_panel_demander")
    async def demander(self, interaction: discord.Interaction,
                       button: discord.ui.Button) -> None:
        await interaction.response.send_modal(BrainModal())


# ——— le cog ———


class Panel(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._install_lock = asyncio.Lock()  # on_ready et le 1er tick du loop
        self.refresh.start()                 # courent ensemble au boot

    def cog_unload(self) -> None:
        self.refresh.cancel()

    @staticmethod
    def _panel_channel(guild: discord.Guild) -> discord.abc.Messageable | None:
        for kind in ("commandes",):
            cid = store.reg_channel(guild.id, kind)
            ch = guild.get_channel(cid) if cid else None
            if ch:
                return ch
        for name in ("commandes", "logs"):
            ch = discord.utils.get(guild.text_channels, name=name)
            if ch:
                return ch
        return guild.system_channel

    @staticmethod
    def _registered(guild: discord.Guild) -> tuple[int, int] | None:
        rows = store.reg_get(guild.id, "channel_panel")
        if rows:
            try:
                return int(rows[0]["target"]), int(rows[0]["value"])
            except (ValueError, TypeError):
                return None
        return None

    async def install(self, guild: discord.Guild, force: bool = False) -> None:
        async with self._install_lock:
            if not force and self._registered(guild) is not None:
                return  # déjà installé — la course au boot ne duplique pas
            ch = self._panel_channel(guild)
            if ch is None or not hasattr(ch, "send"):
                return
            e = main_embed(guild)
            try:
                msg = await ch.send(embed=e, view=PanelView())
            except discord.Forbidden:
                return
            store.reg_set(guild.id, "channel_panel", str(ch.id), str(msg.id))

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        self.bot.add_view(PanelView())  # les boutons survivent aux restarts
        for guild in self.bot.guilds:
            if self._registered(guild) is None:
                await self.install(guild)

    @tasks.loop(minutes=10)
    async def refresh(self) -> None:
        for guild in self.bot.guilds:
            reg = self._registered(guild)
            if reg is None:
                await self.install(guild)
                continue
            ch_id, msg_id = reg
            ch = guild.get_channel(ch_id)
            if ch is None or not hasattr(ch, "get_partial_message"):
                continue
            try:
                await ch.get_partial_message(msg_id).edit(embed=main_embed(guild),
                                            view=PanelView())
            except discord.NotFound:
                await self.install(guild, force=True)  # supprimé → réinstallé
            except discord.Forbidden:
                continue

    @refresh.before_loop
    async def _wait_ready(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Panel(bot))
