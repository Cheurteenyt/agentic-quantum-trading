"""Le bot Discord du projet — les rapports et les commandes de consultation.

Lancement : .venv/bin/python -m discord.bot
Le bot voit TOUS les salons du serveur (intents guilds + messages + message_content —
cette dernière est PRIVILÉGIÉE : à activer dans le portail développeur → Bot →
Privileged Gateway Intents → Message Content Intent, sinon le bot ne lit aucun texte).

La structure est en cogs (discord/cogs/) — une nouvelle famille de commandes
= un nouveau fichier cog, rien d'autre à toucher.
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil

import discord
from discord.ext import commands

from . import config

COGS_PACKAGE = "discord_bot.cogs"


def _intents() -> discord.Intents:
    intents = discord.Intents.default()          # guilds + salons visibles
    intents.messages = True                       # les messages des salons
    intents.message_content = True                # PRIVILÉGIÉ — le contenu du texte
    intents.members = True                        # PRIVILÉGIÉ — les membres (alertes par role)
    return intents


class HermesBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=_intents(),
                         help_command=None)

    async def setup_hook(self) -> None:
        # les cogs du package cogs
        import discord_bot.cogs as cogs
        for mod in pkgutil.iter_modules(cogs.__path__):
            module = importlib.import_module(f"{COGS_PACKAGE}.{mod.name}")
            if hasattr(module, "setup"):
                await module.setup(self)
        # sync des slash commands SUR LA GUILDE (instantané, pas l'heure de sync globale)
        if config.DISCORD_GUILD_ID:
            guild = discord.Object(id=int(config.DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

    async def on_ready(self) -> None:
        user = self.user
        print(f"[discord] connecté : {user} (id {user.id if user else '?'})")
        # le ménage one-shot : le #stats en doublon (la leçon anti-duplication 05/10)
        for guild in self.guilds:
            stats = discord.utils.get(guild.text_channels, name="stats")
            me = guild.me
            if stats and me.guild_permissions.manage_channels:
                try:
                    await stats.delete(reason="le doublon #stats — le rapport va dans #logs")
                    print(f"[discord] #stats supprimé (doublon de #logs)")
                except discord.Forbidden:
                    pass
        guild = discord.utils.get(self.guilds, id=int(config.DISCORD_GUILD_ID)) \
            if config.DISCORD_GUILD_ID else None
        if guild:
            salons = list(guild.channels)
            print(f"[discord] serveur « {guild.name} » — {len(salons)} salons visibles : "
                  + ", ".join(f"#{c.name}" for c in sorted(salons, key=lambda c: c.position)
                              if isinstance(c, discord.TextChannel)))
        else:
            print("[discord] ⚠ la guilde DISCORD_GUILD_ID n'est pas visible — "
                  "invite le bot sur ce serveur (voir discord/README.md)")


def main() -> int:
    errs = config.validate()
    if errs:
        for e in errs:
            print(f"[discord] ERREUR : {e}")
        return 1
    bot = HermesBot()
    try:
        bot.run(config.DISCORD_BOT_TOKEN)
    except discord.LoginFailure:
        print("[discord] ERREUR : token refusé par Discord — vérifie DISCORD_BOT_TOKEN dans .env")
        return 1
    except discord.PrivilegedIntentsRequired:
        print("[discord] ERREUR : les intents privilégiés ne sont pas activés — "
              "portail développeur → Bot → Message Content Intent + Server Members Intent")
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
