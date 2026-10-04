"""Le CERVEAU — la couche conversationnelle du bot (le « réellement intelligent »).

Deux portes d'entrée, ZÉRO commande :
  1. mentionne le bot dans n'importe quel salon → il répond (Bonsai 27B local,
     nourri avec les prix RÉELS de la warehouse — il ne peut pas inventer un
     prix absent du contexte).
  2. le bouton 🧠 du panneau → un modal de question, la réponse en éphémère.

Garde-fous : cooldown 20 s par salon (anti-spam), la question tronquée à 600
caractères, la réponse à 1900, le refus poli si le cerveau est indisponible.
"""
from __future__ import annotations

import asyncio
import collections

import discord
from discord.ext import commands

from discord_bot import stats
from discord_bot.bonsai_judge import ask

COOLDOWN_S = 20
CHANNEL_HIST_MAX = 500


def _market_context() -> str:
    snap = stats.market_snapshot()
    return stats.market_context(snap) if snap else "(marché indisponible)"


class BrainModal(discord.ui.Modal, title="🧠 Demande à Core Equity"):
    question = discord.ui.TextInput(
        label="Ta question (marché, prix, le serveur…)",
        style=discord.TextStyle.paragraph, max_length=500,
        placeholder="Ex : comment s'est passée la dernière heure sur BTC ?")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        answer = await asyncio.to_thread(ask, str(self.question.value),
                                         _market_context())
        if answer is None:
            await interaction.followup.send(
                "🧠 mon cerveau local se réveille (il tourne sur ta machine) — "
                "réessaie dans une minute.", ephemeral=True)
            return
        await interaction.followup.send(
            f"**{interaction.user.display_name}** → {answer}", ephemeral=True)


class Brain(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last: dict[int, float] = collections.defaultdict(float)

    def _cooled(self, channel_id: int, now: float) -> bool:
        if now - self._last[channel_id] < COOLDOWN_S:
            return False
        self._last[channel_id] = now
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild or not self.bot.user:
            return
        if self.bot.user not in message.mentions:
            return
        content = (message.content or "").replace(f"<@{self.bot.user.id}>", "").strip()
        if len(content) < 4:
            await message.reply("🧠 pose-moi ta question après la mention — "
                                "ex : <@%d> c'est quoi le top du jour ?" % self.bot.user.id)
            return
        import time as _t
        if not self._cooled(message.channel.id, _t.time()):
            await message.reply("🧠 laisse-moi finir — je réponds à une question "
                                "toutes les 20 secondes par salon.")
            return
        question = content[:600]
        async with message.channel.typing():
            answer = await asyncio.to_thread(ask, question, _market_context())
        if answer is None:
            await message.reply("🧠 mon cerveau local est indisponible — "
                                "il se relance, réessaie dans une minute.")
            return
        await message.reply(f"🧠 {answer}", mention_author=False)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Brain(bot))
