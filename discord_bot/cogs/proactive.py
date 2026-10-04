"""Le cog PROACTIF — le bot observe la warehouse et PARLE QUAND ÇA COMPTE.

Zéro commande : une boucle de veille toutes les 15 min sur les événements de la
warehouse (les nouveaux listings, les liquidations notables, les anomalies de volume,
les extrêmes de premium), un contexte intelligent posté automatiquement sur chaque call
des membres, et le brief matinal 09:00 UTC.

L'anti-bruit (la culture du labo) : chaque type d'event a un cooldown de 2 h et un
plafond de 5/jour — le bot devient plus sélectif, jamais plus bruyant.
"""
from __future__ import annotations

import asyncio
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

from .. import config

KDB = config.KDB
COOLDOWN_H = 2
DAILY_CAP = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Proactive(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cooldowns: dict[str, datetime] = {}
        self._daily: dict[str, int] = defaultdict(int)
        self._last_seen: dict[str, str] = {}
        self.watch_loop.start()
        self.brief_loop.start()

    def cog_unload(self) -> None:
        self.watch_loop.cancel()
        self.brief_loop.cancel()

    # ——— l'anti-bruit ———

    def _budget(self, kind: str) -> bool:
        key = f"{kind}:{_now().strftime('%Y-%m-%d')}"
        if self._daily[key] >= DAILY_CAP:
            return False
        last = self._cooldowns.get(kind)
        if last and (_now() - last) < timedelta(hours=COOLDOWN_H):
            return False
        self._cooldowns[kind] = _now()
        self._daily[key] += 1
        return True

    def _channel(self) -> discord.TextChannel | None:
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild:
            return None
        return store_log(guild) or discord.utils.get(guild.text_channels, name="logs")

    # ——— les événements de la warehouse ———

    def _new_listings(self) -> list[tuple[str, float]]:
        con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT symbol, MIN(open_time) FROM klines WHERE interval='1h' "
                "GROUP BY symbol HAVING MIN(open_time) > ?",
                (int((_now() - timedelta(hours=48)).timestamp() * 1000),)).fetchall()
            return [(r[0], r[1]) for r in rows]
        finally:
            con.close()

    def _big_liqs(self) -> list[tuple]:
        con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
        try:
            since = int((_now() - timedelta(minutes=20)).timestamp() * 1000)
            return con.execute(
                "SELECT symbol, side, notional, price, event_time FROM liq_events "
                "WHERE captured_at > ? AND notional > 20000 ORDER BY notional DESC LIMIT 3",
                (since / 1000,)).fetchall()
        finally:
            con.close()

    def _volume_anomaly(self) -> list[tuple[str, float, float]] | None:
        """Les volume z-score > 4 sur les majeures — l'anomalie d'activité."""
        con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
        try:
            out = []
            for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ASTERUSDT"):
                rows = con.execute(
                    "SELECT volume FROM klines WHERE symbol=? AND interval='1h' "
                    "ORDER BY open_time DESC LIMIT 169", (sym,)).fetchall()
                if len(rows) < 169:
                    continue
                vols = [r[0] for r in rows]
                mean = sum(vols[1:]) / len(vols[1:])
                sd = (sum((v - mean) ** 2 for v in vols[1:]) / len(vols[1:])) ** 0.5
                if sd > 0:
                    z = (vols[0] - mean) / sd
                    if abs(z) > 4:
                        out.append((sym, z, vols[0]))
            return out or None
        finally:
            con.close()

    def _premium_extreme(self) -> list[tuple[str, float]] | None:
        """Les |z| du premium 15m > 4 sur les majeures."""
        con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
        try:
            out = []
            for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ASTERUSDT"):
                rows = con.execute(
                    "SELECT premium_close FROM premium_15m WHERE symbol=? "
                    "ORDER BY open_time DESC LIMIT 96", (sym,)).fetchall()
                if len(rows) < 96:
                    continue
                vals = [r[0] for r in rows]
                mean = sum(vals) / len(vals)
                sd = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
                if sd > 0:
                    z = (vals[0] - mean) / sd
                    if abs(z) > 4:
                        out.append((sym, z))
            return out or None
        finally:
            con.close()

    # ——— la boucle de veille ———

    @tasks.loop(minutes=15)
    async def watch_loop(self) -> None:
        await self.bot.wait_until_ready()
        ch = self._channel()
        if ch is None:
            return
        posts = []
        for sym, first_ms in self._new_listings():
            key = f"listing:{sym}"
            if self._last_seen.get(key) != "vu":
                self._last_seen[key] = "vu"
                posts.append(f"🆕 **{sym}** vient d'apparaître sur Aster (première bougie < 48 h)")
        for sym, side, notional, price, t in self._big_liqs():
            key = f"liq:{sym}:{t}"
            if self._last_seen.get(key) != "vu":
                self._last_seen[key] = "vu"
                posts.append(f"💥 **LIQ {sym}** {side} — {notional:,.0f} $ @ {price:g}")
        if self._budget("volume") and (vols := self._volume_anomaly()):
            for sym, z, v in vols:
                posts.append(f"📊 **{sym}** : volume ×{abs(z):.1f}σ sur la dernière heure "
                             f"({v:,.0f}) — l'activité sort de sa fourchette")
        if self._budget("premium") and (prem := self._premium_extreme()):
            for sym, z in prem:
                posts.append(f"⚖ **{sym}** : premium à {z:+.1f}σ — le déséquilibre "
                             f"mark/index est extrême (le MM devra rebalancer)")
        for text in posts[:DAILY_CAP]:
            await ch.send(text[:1500])
        if len(self._last_seen) > 2000:
            self._last_seen.clear()  # la garde anti-croissance (les clés horodatées repartiront)

    # ——— le brief matinal ———

    @tasks.loop(hours=1)
    async def brief_loop(self) -> None:
        await self.bot.wait_until_ready()
        if _now().hour != 7:   # 09:00 CEST = 07:00 UTC
            return
        ch = self._channel()
        if ch is None:
            return
        con = sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)
        try:
            paper = con.execute("SELECT COUNT(*) FROM aster_survivors_paper").fetchone()[0]
            calls = con.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        finally:
            con.close()
        e = discord.Embed(title="☀ Le brief 09:00", color=0x5865F2,
                          timestamp=_now())
        e.add_field(name="paper survivants", value=f"{paper} entrées au ledger")
        e.add_field(name="paper_trades (machine)", value=f"{calls:,}")
        e.add_field(name="veille", value="les événements de la nuit sont dans #trading-agent")
        await ch.send(embed=e)

    @brief_loop.before_loop
    async def _wait(self) -> None:
        await self.bot.wait_until_ready()


def store_log(guild: discord.Guild) -> discord.TextChannel | None:
    return discord.utils.get(guild.text_channels, name="trading-agent")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Proactive(bot))
