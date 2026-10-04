"""Le cog PROTECTION AVANCÉE — la couche au-dessus de la modération de base.

1. LE BOUCLIER ANTI-SCAM (le fléau des serveurs crypto) :
   - les patterns d'arnaque (airdrop/giveaway/seed phrase/dm me/claim...) → purge + sanction
   - le portier par âge de compte : un compte < 3 jours qui poste un lien ou un pattern →
     purge + timeout 24 h + case
   - les liens postés par des comptes < 7 jours → suppression + case
2. L'ÉCHELLE D'ESCALADE : les warns punissent automatiquement
   (2 = mute 1 h · 3 = mute 24 h · 4 = kick · 5 = ban) — chaque palier = une case.
3. LA DÉTECTION DE RAID : ≥ 8 joins en 120 s → mode raid auto (les nouveaux arrivants
   mutés 1 h + l'alerte) ; /raidmode on|off force l'état.
4. L'IMPERSONATION : un arrivant dont le pseudo contient le nom d'un admin/modérateur
   → alerte + case (les faux « Core Equity support » meurent ici).
5. LE LOG TOTAL : les éditions et suppressions de messages sont tracées (le scammer édite
   son message après la modération — le contenu d'avant est conservé).
6. LES CASES : chaque action = un numéro de case ; /case N et /cases @user relisent tout.
"""
from __future__ import annotations

import asyncio
import collections
import datetime as dt
import re

import discord
from discord import app_commands
from discord.ext import commands

from .. import store

SCAM_RE = re.compile(
    r"(airdrop|giveaway|give\s*away|claim\s+(your|now)|double\s+your|free\s+(eth|btc|usdt|sol)"
    r"|dm\s+(me|for)|private\s+(message|key)|seed\s*phrase|mnemonic|recovery\s+(wallet|funds)"
    r"|whitelist\s+spots?|send\s+(eth|usdt)\s+to|guaranteed\s+(profit|x\d+))", re.I)
LINK_RE = re.compile(r"https?://[^\s<>\")\]]+", re.I)
ACCOUNT_MIN_DAYS = 3      # le portier : les comptes plus jeunes que ça
LINK_ACCOUNT_MIN_DAYS = 7 # l'âge minimal pour poster un lien sans vérification
JOIN_WINDOW_S = 120       # la fenêtre de détection de raid
JOIN_RAID_N = 8           # le nombre de joins qui déclenche le mode raid
WARN_LADDER = {2: ("timeout", 60), 3: ("timeout", 1440), 4: ("kick", 0), 5: ("ban", 0)}


def _case(guild: discord.Guild, user: discord.abc.User, ctype: str, reason: str) -> int:
    con = store.connect()
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS d_cases (
            case_id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
            guild_id TEXT, user_id TEXT, user_name TEXT, ctype TEXT, reason TEXT)""")
        cur = con.execute("INSERT INTO d_cases (ts, guild_id, user_id, user_name, ctype, "
                          "reason) VALUES (?,?,?,?,?,?)",
                          (dt.datetime.now(dt.UTC).timestamp(), str(guild.id),
                           str(user.id), str(user), ctype, reason))
        con.commit()
        return cur.lastrowid or 0
    finally:
        con.close()


def _log(guild: discord.Guild | None, title: str, description: str,
         color: discord.Color = 0xFEE75C) -> None:
    ch = discord.utils.get(guild.text_channels, name="logs") if guild else None
    if ch:
        e = discord.Embed(title=f"🛡 {title}", description=description[:2000],
                          color=color, timestamp=dt.datetime.now(dt.UTC))
        try:
            asyncio.ensure_future(ch.send(embed=e))
        except Exception:
            pass


def _account_age_days(user: discord.abc.User) -> float:
    return (dt.datetime.now(dt.UTC) - user.created_at).total_seconds() / 86400


class Protection(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._joins: collections.deque = collections.deque()
        self._raid_mode: set[int] = set()

    # ——— le bouclier on_message ———

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not isinstance(message.author, discord.Member) \
                or message.author.guild_permissions.administrator:
            return
        content = message.content or ""
        scam = SCAM_RE.search(content)
        link = LINK_RE.search(content)
        if not scam and not link:
            return
        age = _account_age_days(message.author)
        if scam and re.search(r"seed\s*phrase|mnemonic|private\s+key", content, re.I):
            # les voleurs de seed phrase = ban immédiat, sans discussion
            case = _case(message.guild, message.author, "SCAM-BAN", content[:200])
            await message.delete()
            await message.author.ban(reason=f"case #{case} : vol de seed phrase")
            _log(message.guild, f"CASE #{case} — BAN IMMÉDIAT",
                 f"{message.author.mention} — vol de seed phrase (le message est conservé en case)",
                 discord.Color.Red())
            return
        if scam or (link and age < LINK_ACCOUNT_MIN_DAYS):
            case = _case(message.guild, message.author,
                         "SCAM-SHIELD" if scam else "LIEN-COMPTE-NEUF", content[:200])
            await message.delete()
            if age < ACCOUNT_MIN_DAYS:
                await message.author.timeout(dt.datetime.now(dt.UTC) + dt.timedelta(hours=24),
                                             reason=f"case #{case}")
            _log(message.guild, f"CASE #{case} — {'SCAM-SHIELD' if scam else 'LIEN + COMPTE NEUF'}",
                 f"{message.author.mention} (compte {age:.1f} j) — purge"
                 + (" + mute 24 h" if age < ACCOUNT_MIN_DAYS else ""),
                 discord.Color.Orange())

    # ——— le portier : joins, raids, impersonations ———

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        now = dt.datetime.now(dt.UTC).timestamp()
        self._joins.append(now)
        while self._joins and self._joins[0] < now - JOIN_WINDOW_S:
            self._joins.popleft()
        raid_auto = len(self._joins) >= JOIN_RAID_N
        if raid_auto and member.guild.id not in self._raid_mode:
            self._raid_mode.add(member.guild.id)
            _log(member.guild, "MODE RAID AUTO",
                 f"{JOIN_RAID_N}+ joins en {JOIN_WINDOW_S} s — les nouveaux arrivants sont mutés 1 h",
                 discord.Color.Red())
        age = _account_age_days(member.user if hasattr(member, "user") else member)
        notes = [f"compte créé il y a {age:.1f} j"]
        if member.guild.id in self._raid_mode:
            try:
                await member.timeout(dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
                                     reason="mode raid actif")
                notes.append("muté 1 h (mode raid)")
            except discord.Forbidden:
                notes.append("mute raid refusé (hiérarchie)")
        # l'impersonation : le pseudo qui contient le nom d'un staff
        staff = [m.display_name for m in member.guild.members
                 if m.guild_permissions.administrator or m.guild_permissions.manage_messages]
        low = member.display_name.lower().replace(" ", "")
        for name in staff:
            clean = name.lower().replace(" ", "")
            if len(clean) >= 5 and clean in low and str(member.id) != str(self.bot.user.id):
                case = _case(member.guild, member, "IMPERSONATION",
                             f"pseudo « {member.display_name} » ≈ staff « {name} »")
                notes.append(f"⚠ impersonation du staff (case #{case})")
                _log(member.guild, f"CASE #{case} — IMPERSONATION",
                     f"{member.mention} ≈ « {name} »", discord.Color.Orange())
                break
        _log(member.guild, "JOIN", f"{member.mention} — " + " · ".join(notes))

    @app_commands.command(name="raidmode",
                          description="Mode raid : les nouveaux arrivants mutés 1 h")
    @app_commands.checks.has_permissions(administrator=True)
    async def raidmode(self, inter: discord.Interaction, state: str) -> None:
        if state not in ("on", "off"):
            await inter.response.send_message("state = on ou off", ephemeral=True)
            return
        (self._raid_mode.add if state == "on" else self._raid_mode.discard)(
            inter.guild_id or 0)
        await inter.response.send_message(f"🚨 mode raid : **{state.upper()}**", ephemeral=True)

    # ——— les cases ———

    @app_commands.command(name="case", description="Relire une case par numéro")
    async def case(self, inter: discord.Interaction, number: int) -> None:
        con = store.connect()
        try:
            con.execute("""CREATE TABLE IF NOT EXISTS d_cases (
                case_id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
                guild_id TEXT, user_id TEXT, user_name TEXT, ctype TEXT, reason TEXT)""")
            r = con.execute("SELECT * FROM d_cases WHERE case_id=?", (number,)).fetchone()
        finally:
            con.close()
        if r is None:
            await inter.response.send_message(f"case #{number} : inexistante", ephemeral=True)
            return
        e = discord.Embed(title=f"CASE #{r['case_id']} — {r['ctype']}",
                          description=r["reason"][:1500], timestamp=dt.datetime.fromtimestamp(r["ts"], dt.UTC))
        e.add_field(name="membre", value=f"{r['user_name']} (`{r['user_id']}`)")
        await inter.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="cases", description="Toutes les cases d'un membre")
    async def cases(self, inter: discord.Interaction, member: discord.Member) -> None:
        con = store.connect()
        try:
            rows = con.execute("SELECT case_id, ts, ctype, reason FROM d_cases "
                               "WHERE user_id=? ORDER BY ts DESC", (str(member.id),)).fetchall()
        finally:
            con.close()
        txt = "\n".join(f"• #{r['case_id']} [{r['ctype']}] {r['reason'][:80]}" for r in rows) \
            or "aucune case"
        await inter.response.send_message(
            f"**{member.mention} — {len(rows)} case(s)** :\n{txt}"[:1900], ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Protection(bot))


    # ——— le log total : les éditions et les suppressions ———

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or (before.content or "") == (after.content or ""):
            return
        _log(before.guild, "ÉDITION",
             f"{before.author.mention} — avant : `{(before.content or 'vide')[:300]}`\n"
             f"après : `{(after.content or 'vide')[:300]}`", discord.Color.Blurple())

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot or not message.content:
            return
        _log(message.guild, "SUPPRESSION",
             f"{message.author.mention} — `{message.content[:400]}`", discord.Color.DarkGrey())
