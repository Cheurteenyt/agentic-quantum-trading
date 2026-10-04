"""Le cog MODÉRATION SÉMANTIQUE — le triage en 3 niveaux d'autonomie (design 05/10).

Le triage : regex d'abord (les cas évidents, déjà gérés par protection.py), le LLM sur
les cas LIMITES (compte neuf + lien, lien sans contexte, message long d'un compte jeune).
Les niveaux :
  AUTO   — score > 90 OU (scam ET compte < 24 h) : purge + timeout, sans attendre
  QUEUE  — score 70-90 : le message est masqué et mis en revue dans #revue-secu avec les
           boutons [BAN] [PURGER] [IGNORER] — 15 min pour cliquer, sinon retour rapport
  RAPPORT — le reste : agrégé dans le rapport quotidien
LE FILTRE ANTI-FATIGUE : max 5 alertes critiques/jour dans #revue-secu — au-delà, tout
passe au rapport (le bot devient plus sélectif, pas plus bruyant).
"""
from __future__ import annotations

import asyncio
import datetime as dt

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .. import bonsai_judge, store

CRIT_MAX_PER_DAY = 5
LINK_MIN_AGE_J = 7
REVIEW_WINDOW_S = 900
_scored_today = {"date": None, "count": 0}


def _today() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")


def _critical_budget() -> bool:
    if _scored_today["date"] != _today():
        _scored_today["date"] = _today()
        _scored_today["count"] = 0
    _scored_today["count"] += 1
    return _scored_today["count"] <= CRIT_MAX_PER_DAY


async def _resolve_channel(guild: discord.Guild, name: str) -> discord.TextChannel | None:
    """LA RÈGLE ANTI-DUPLICATION (leçon #stats 05/10) : le bot INTÈGRE la structure
    existante, il ne crée jamais de salon parallèle. Ordre : le registre (/setchannel),
    puis le salon existant par nom, puis #logs, sinon None (le rapport est abstenu)."""
    reg_id = store.reg_channel(guild.id, name)
    if reg_id:
        ch = guild.get_channel(reg_id)
        if isinstance(ch, discord.TextChannel):
            return ch
    ch = discord.utils.get(guild.text_channels, name=name)
    if isinstance(ch, discord.TextChannel):
        return ch
    return discord.utils.get(guild.text_channels, name="logs")


class ReviewView(discord.ui.View):
    """La file de revue : [BAN] [PURGER] [IGNORER] — 15 min pour décider."""

    def __init__(self, target: discord.Member, message: discord.Message, verdict: dict):
        super().__init__(timeout=REVIEW_WINDOW_S)
        self.target, self.message, self.verdict = target, message, verdict

    async def _close(self, inter: discord.Interaction, note: str, color: int) -> None:
        for child in self.children:
            child.disabled = True
        await inter.message.edit(content=f"✅ revu par {inter.user} — {note}",
                                 embed=inter.message.embeds[0], view=self)
        self.stop()

    @discord.ui.button(label="BAN", style=discord.ButtonStyle.danger)
    async def do_ban(self, inter: discord.Interaction, _b: discord.ui.Button) -> None:
        await inter.response.defer()
        try:
            await self.target.ban(reason=f"revue sémantique : {self.verdict}")
            await self._close(inter, "BAN appliqué", 0xED4245)
        except discord.Forbidden:
            await self._close(inter, "BAN refusé (hiérarchie)", 0x95A5A6)

    @discord.ui.button(label="PURGER LE MESSAGE", style=discord.ButtonStyle.secondary)
    async def do_purge(self, inter: discord.Interaction, _b: discord.ui.Button) -> None:
        await inter.response.defer()
        try:
            await self.message.delete()
            await self._close(inter, "message purgé", 0xFEE75C)
        except discord.NotFound:
            await self._close(inter, "déjà supprimé", 0x95A5A6)

    @discord.ui.button(label="IGNORER", style=discord.ButtonStyle.success)
    async def do_ignore(self, inter: discord.Interaction, _b: discord.ui.Button) -> None:
        await inter.response.defer()
        await self._close(inter, "ignoré (faux positif — le seuil du juge remontera)", 0x57F287)

    async def on_timeout(self) -> None:
        try:
            for child in self.children:
                child.disabled = True
            if self.message:
                await self.message.edit(content="⏱ non revu en 15 min — archivé au rapport",
                                        view=self)
        except Exception:
            pass


class Semantic(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._daily = dt.datetime.now(dt.UTC)
        self.report_loop.start()

    def cog_unload(self) -> None:
        self.report_loop.cancel()

    # ——— le triage ———

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not isinstance(message.author, discord.Member) \
                or message.author.guild_permissions.administrator:
            return
        content = message.content or ""
        if len(content) < 8:
            return
        age = (dt.datetime.now(dt.UTC) - message.author.created_at).total_seconds() / 86400
        has_link = "http" in content.lower()
        # le LLM ne juge que les cas limites (le volume reste raisonnable pour un 27B local)
        if not (age < LINK_MIN_AGE_J and (has_link or len(content) > 120)):
            return
        verdict = await asyncio.to_thread(
            bonsai_judge.classify, content, age, getattr(message.channel, "name", "?"))
        if verdict is None:
            return
        score = verdict.get("toxicity", 0)
        conf = verdict.get("confidence", 0.0)
        scam = verdict.get("scam_type")
        if score > 90 and age < 1.0 and conf > 0.9:
            # AUTO : purge + mute (le ban reste en queue — la règle d'or)
            await message.delete()
            await message.author.timeout(dt.datetime.now(dt.UTC) + dt.timedelta(hours=24),
                                         reason=f"juge sémantique score {score}")
            _log_to(message.guild, f"🤖 AUTO score {score} — {message.author.mention} "
                                    f"purge + mute 24 h ({scam or 'toxicité'})")
        elif (score >= 70 or (scam and conf >= 0.8)) and message.guild:
            if _critical_budget():
                await self._queue_review(message, verdict)
            else:
                _log_to(message.guild, f"🤖 score {score} (file de revue saturée — "
                                        f"{_scored_today['count']} alertes aujourd'hui)")
        # le reste = rapport quotidien (les lignes sont comptées par le rapporteur)

    async def _queue_review(self, message: discord.Message, verdict: dict) -> None:
        ch = await _resolve_channel(message.guild, "revue-secu")
        if ch is None:
            return
        e = discord.Embed(title=f"🤖 REVUE — score {verdict.get('toxicity')} "
                                f"conf {verdict.get('confidence')}", color=0xFEE75C,
                          timestamp=dt.datetime.now(dt.UTC))
        e.add_field(name="auteur", value=f"{message.author.mention} "
                                         f"(compte {age_of(message.author):.1f} j)")
        e.add_field(name="scam_type", value=str(verdict.get("scam_type")))
        e.add_field(name="salon", value=f"#{getattr(message.channel, 'name', '?')}")
        e.description = (message.content or "")[:1000]
        await ch.send(embed=e,
                       view=ReviewView(message.author, message, verdict),
                       content="🤖 cas ambigu — la règle d'or : le LLM propose, l'humain clique")

    # ——— le rapport quotidien ———

    @tasks.loop(hours=24)
    async def report_loop(self) -> None:
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            con = store.connect()
            try:
                msgs = con.execute("SELECT COUNT(*) FROM d_messages WHERE "
                                   "fetched_at > ?", (dt.datetime.now(dt.UTC).timestamp()
                                                      - 86400,)).fetchone()[0]
                media = con.execute("SELECT COUNT(*) FROM d_media WHERE captured_at > ?",
                                    (dt.datetime.now(dt.UTC).timestamp() - 86400,)).fetchone()[0]
                actions = con.execute("SELECT COUNT(*) FROM d_mod_actions WHERE ts > ?",
                                      (dt.datetime.now(dt.UTC).timestamp() - 86400,)).fetchone()[0]
                cases = con.execute("SELECT COUNT(*) FROM d_cases WHERE ts > ?",
                                    (dt.datetime.now(dt.UTC).timestamp() - 86400,)).fetchone()[0]
            finally:
                con.close()
            ch = await _resolve_channel(guild, "stats")
            if ch is None:
                print("[semantic] pas de salon de destination — rapport 24 h abstenu")
                return
            e = discord.Embed(title="📊 Le rapport 24 h du bot", color=0x5865F2)
            e.add_field(name="messages capturés", value=f"{msgs:,}")
            e.add_field(name="médias", value=f"{media:,}")
            e.add_field(name="actions mod", value=f"{actions}")
            e.add_field(name="cases ouvertes", value=f"{cases}")
            e.add_field(name="alertes critiques aujourd'hui",
                        value=f"{_scored_today['count']}/{CRIT_MAX_PER_DAY}")
            try:
                await ch.send(embed=e)
            except discord.Forbidden:
                pass

    @app_commands.command(name="judge",
                          description="Tester le juge sémantique sur un texte")
    async def judge(self, inter: discord.Interaction, texte: str) -> None:
        await inter.response.defer(ephemeral=True)
        verdict = await asyncio.to_thread(bonsai_judge.classify, texte, 999, inter.channel.name)
        if verdict is None:
            await inter.followup.send("juge indisponible (le serveur Bonsai ne répond pas)")
            return
        await inter.followup.send(f"🤖 verdict : `{verdict}`", ephemeral=True)


def age_of(member: discord.Member) -> float:
    return (dt.datetime.now(dt.UTC) - member.created_at).total_seconds() / 86400


def _log_to(guild: discord.Guild | None, text: str) -> None:
    ch = discord.utils.get(guild.text_channels, name="logs") if guild else None
    if ch:
        asyncio.ensure_future(ch.send(text))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Semantic(bot))
