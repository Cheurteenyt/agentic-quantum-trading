"""Le cog TRADING — le compagnon de trading de la communauté : les prix, les charts,
les calls des membres scorés contre la warehouse, le leaderboard.

Les sources : klines.db (586 symboles × 5 ans, 1h) — la même vérité que le labo.
Les calls postés dans les salons de trading sont parsés (direction, ticker, entrée),
scorés à chaque /leaderboard contre les prix 1h réels, et classés par membre.
"""
from __future__ import annotations

import io
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from .. import config

KDB = config.KDB
DDB = config.ROOT / "data" / "warehouse" / "discord.db"

DIRECTION_RE = re.compile(
    r"\b(long|short|bullish|bearish|achat|vente|achete|vend|bought|aping|aped|"
    r"shorting|shorted|sold|selling)\b", re.I)
CALL_RE = re.compile(r"\$?([A-Za-z]{2,10})(?:USDT)?\b")
TRADING_CHANNELS = {"💪-vos-trades", "💎-discussions-trading"}


def _kdb() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{KDB}?mode=ro", uri=True)


def _ddb() -> sqlite3.Connection:
    con = sqlite3.connect(DDB, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS d_calls (
        call_id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT UNIQUE, author_id TEXT, author_name TEXT,
        symbol TEXT, direction TEXT, entry REAL, posted_at TEXT,
        channel_name TEXT, scored INTEGER DEFAULT 0,
        ret_pct REAL, verdict TEXT)""")
    return con


def _last_price(sym: str) -> tuple[float | None, str | None]:
    con = _kdb()
    try:
        row = con.execute("SELECT close, open_time FROM klines WHERE symbol=? "
                          "AND interval='1h' ORDER BY open_time DESC LIMIT 1",
                          (sym,)).fetchone()
        if row:
            ts = datetime.fromtimestamp(row[1] / 1000, timezone.utc)
            return float(row[0]), ts.strftime("%d/%m %H:%M UTC")
        return None, None
    finally:
        con.close()


class Trading(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ——— le parse des calls dans les salons de trading ———

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if getattr(message.channel, "name", "") not in TRADING_CHANNELS:
            return
        content = message.content or ""
        dm = DIRECTION_RE.search(content)
        if not dm:
            return
        direction = dm.group(1).lower()
        d = -1.0 if direction in ("short", "bearish", "vente", "vend", "shorting",
                                  "shorted", "sold", "selling") else 1.0
        # le ticker : le $CASHTAG prioritaire, sinon le mot après la direction
        tick = re.search(r"\$([A-Za-z]{2,10})", content)
        if tick:
            sym = tick.group(1).upper()
        else:
            tail = content[dm.end():]
            tm = CALL_RE.search(tail)
            sym = tm.group(1).upper() if tm else None
        if not sym or len(sym) < 2:
            return
        con = _ddb()
        try:
            con.execute("INSERT OR IGNORE INTO d_calls (message_id, author_id, "
                        "author_name, symbol, direction, posted_at, channel_name) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (str(message.id), str(message.author.id), str(message.author),
                         sym, "long" if d > 0 else "short",
                         message.created_at.isoformat(),
                         getattr(message.channel, "name", "?")))
            con.commit()
        finally:
            con.close()

    @app_commands.command(name="prix", description="Le dernier prix collecté d'un symbole")
    async def prix(self, inter: discord.Interaction, symbole: str) -> None:
        sym = symbole.upper().removesuffix("USDT") + "USDT"
        px, age = _last_price(sym)
        if px is None:
            await inter.response.send_message(f"❌ {sym} : pas de prix en warehouse "
                                              f"(symbole inconnu ou non collecté)", ephemeral=True)
            return
        con = _kdb()
        try:
            row = con.execute("SELECT close FROM klines WHERE symbol=? AND interval='1h' "
                              "ORDER BY open_time DESC LIMIT 25", (sym,)).fetchall()
        finally:
            con.close()
        if len(row) >= 25:
            ch24 = (row[0][0] / row[24][0] - 1) * 100
            await inter.response.send_message(
                f"💠 **{sym}** : `{px:,.6g}` ({age}) — 24 h : {ch24:+.2f} %")
        else:
            await inter.response.send_message(f"💠 **{sym}** : `{px:,.6g}` ({age})")

    @app_commands.command(name="chart", description="Le graphique 7 jours d'un symbole")
    async def chart(self, inter: discord.Interaction, symbole: str) -> None:
        await inter.response.defer()
        sym = symbole.upper().removesuffix("USDT") + "USDT"
        con = _kdb()
        try:
            rows = con.execute("SELECT open_time, close FROM klines WHERE symbol=? "
                               "AND interval='1h' ORDER BY open_time DESC LIMIT 168",
                               (sym,)).fetchall()
        finally:
            con.close()
        if len(rows) < 24:
            await inter.followup.send(f"❌ {sym} : pas assez de données", ephemeral=True)
            return
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        rows = rows[::-1]
        ts = [datetime.fromtimestamp(r[0] / 1000, timezone.utc) for r in rows]
        px = [r[1] for r in rows]
        fig, ax = plt.subplots(figsize=(9, 4), dpi=110)
        ax.plot(ts, px, lw=1.4, color="#5865F2")
        ax.set_title(f"{sym} — 7 jours (1h, warehouse)")
        ax.grid(alpha=0.3)
        ax.tick_params(axis="x", rotation=20, labelsize=7)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        await inter.followup.send(file=discord.File(buf, f"{sym}_7j.png"))

    @app_commands.command(name="leaderboard",
                          description="Le classement des calls des membres (scorés contre les prix réels)")
    async def leaderboard(self, inter: discord.Interaction) -> None:
        await inter.response.defer()
        con = _ddb()
        try:
            rows = con.execute("SELECT call_id, symbol, direction, posted_at "
                               "FROM d_calls WHERE scored=0").fetchall()
        finally:
            con.close()
        kcon = _kdb()
        scored = 0
        try:
            for r in rows:
                sym = r["symbol"] + "USDT"
                posted = datetime.fromisoformat(r["posted_at"])
                entry_row = kcon.execute(
                    "SELECT close, open_time FROM klines WHERE symbol=? AND interval='1h' "
                    "AND open_time >= ? ORDER BY open_time LIMIT 1",
                    (sym, int(posted.timestamp() * 1000))).fetchone()
                if not entry_row:
                    continue
                exit_row = kcon.execute(
                    "SELECT close FROM klines WHERE symbol=? AND interval='1h' "
                    "AND open_time >= ? ORDER BY open_time LIMIT 1",
                    (sym, int(posted.timestamp() * 1000) + 24 * 3600 * 1000)).fetchone()
                if not exit_row:
                    continue
                d = 1.0 if r["direction"] == "long" else -1.0
                ret = d * (exit_row[0] / entry_row[0] - 1) * 100
                verdict = "win" if ret > 0 else "loss"
                con.execute("UPDATE d_calls SET scored=1, ret_pct=?, verdict=? "
                            "WHERE call_id=?", (round(ret, 3), verdict, r["call_id"]))
                scored += 1
            con.commit()
        finally:
            kcon.close()
        # le classement : WR et la somme des rets, min 3 calls scorés
        con = _ddb()
        try:
            board = con.execute(
                "SELECT author_name, COUNT(*) n, AVG(ret_pct) avg_ret, "
                "SUM(CASE WHEN verdict='win' THEN 1 ELSE 0 END)*100.0/COUNT(*) wr "
                "FROM d_calls WHERE scored=1 GROUP BY author_id "
                "HAVING n >= 3 ORDER BY avg_ret DESC LIMIT 10").fetchall()
        finally:
            con.close()
        txt = "\n".join(f"• **{r['author_name']}** — {r['n']} calls, WR {r['wr']:.0f} %, "
                        f"moy {r['avg_ret']:+.2f} %" for r in board) or "aucun call scoré"
        await inter.followup.send(
            f"🏆 **Leaderboard des calls** ({scored} nouveau(x) scoré(s) sur 24 h réels) :\n{txt}")

    @app_commands.command(name="mes-calls",
                          description="Tes calls parsés et leur performance")
    async def mes_calls(self, inter: discord.Interaction) -> None:
        con = _ddb()
        try:
            rows = con.execute("SELECT symbol, direction, posted_at, scored, ret_pct, "
                               "verdict FROM d_calls WHERE author_id=? "
                               "ORDER BY posted_at DESC LIMIT 15",
                               (str(inter.user.id),)).fetchall()
        finally:
            con.close()
        if not rows:
            await inter.response.send_message(
                "aucun call parsé — poste dans #💪-vos-trades avec le format : "
                "« long $SYMBOL »", ephemeral=True)
            return
        txt = "\n".join(
            f"• {r['symbol']} {r['direction'].upper()} ({r['posted_at'][:10]}) — "
            + (f"{r['verdict']} {r['ret_pct']:+.2f} %" if r["scored"] else "en cours")
            for r in rows)
        await inter.response.send_message(f"**📊 Tes 15 derniers calls :**\n{txt}",
                                          ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Trading(bot))
