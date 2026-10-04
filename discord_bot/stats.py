"""Les statistiques du serveur en lecture seule — LA source partagée.

Un seul endroit pour les requêtes (classement, profil, serveur) : le dashboard
et le panneau Discord (cogs/panel.py) rendent les MÊMES chiffres. Les fonctions
prennent un chemin de DB (défaut : la warehouse) — testables sur une DB
temporaire, la prod sur data/warehouse/discord.db en mode ro.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DDB = ROOT / "data" / "warehouse" / "discord.db"
KDB = ROOT / "data" / "warehouse" / "klines.db"
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "ASTERUSDT")


def _kcon(path: Path | None = None) -> sqlite3.Connection:
    p = path or KDB
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def market_snapshot(path: Path | None = None) -> dict | None:
    """La photo du marché 24 h (les klines 1h) — None si la DB est absente/vide.

    Fraîcheur : un symbole dont la dernière bougie date de plus de 2 h sort
    (on n'affiche jamais un prix périmé comme s'il était vivant).
    """
    p = path or KDB
    if not p.exists():
        return None
    con = _kcon(path)
    try:
        row = con.execute("SELECT MAX(open_time) FROM klines WHERE interval='1h'").fetchone()
        if not row or not row[0]:
            return None
        cutoff = row[0]
        rows = con.execute(
            """SELECT symbol, open_time, close FROM klines WHERE interval='1h'
               AND open_time > ? ORDER BY symbol, open_time""",
            (cutoff - 24 * 3600000,)).fetchall()
    finally:
        con.close()
    fresh = cutoff - 2 * 3600000
    series: dict[str, list[tuple[int, float]]] = {}
    for r in rows:
        series.setdefault(r["symbol"], []).append((r["open_time"], r["close"]))
    chg: dict[str, tuple[float, float]] = {}  # symbole → (prix, %24h)
    for sym, pts in series.items():
        if pts[-1][0] < fresh or pts[0][1] <= 0:
            continue
        chg[sym] = (pts[-1][1], (pts[-1][1] / pts[0][1] - 1) * 100)
    if not chg:
        return None
    majors = {s: chg[s] for s in MAJORS if s in chg}
    others = sorted(((s, p2, c) for s, (p2, c) in chg.items() if s not in MAJORS),
                    key=lambda x: x[2])
    return {"majors": majors, "ts": cutoff,
            "up": others[-5:][::-1], "down": others[:5], "n_symbols": len(chg)}


def _price(price: float) -> str:
    return f"${price:,.2f}" if price >= 1 else f"${price:.6f}"


def _pct(pct: float) -> str:
    return f"{'+' if pct >= 0 else ''}{pct:.1f} %"


def market_lines(snap: dict) -> tuple[str, str]:
    """(la ligne des majeures, le bloc des movers) — l'affichage partagé."""
    majors_line = " · ".join(f"**{s.removesuffix('USDT')}** {_price(p)} "
                             f"({_pct(c)})" for s, (p, c) in snap["majors"].items())
    up = " · ".join(f"**{s.removesuffix('USDT')}** {_pct(c)}" for s, _, c in snap["up"]) or "—"
    down = " · ".join(f"**{s.removesuffix('USDT')}** {_pct(c)}" for s, _, c in snap["down"]) or "—"
    return majors_line, f"📈 {up}\n📉 {down}"


def market_context(snap: dict) -> str:
    """Le bloc compact pour le cerveau — les prix RÉELS qu'il peut citer."""
    majors_line, movers = market_lines(snap)
    return f"Prix actuels (24 h) : {majors_line}\nTop variations : {movers}"


def _con(path: Path | None = None) -> sqlite3.Connection:
    p = path or DDB
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _tables_ready(con: sqlite3.Connection) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='d_calls'").fetchone())


def classement(path: Path | None = None, limit: int = 10, min_calls: int = 3) -> list[dict]:
    """Le classement des calls scorés — la même règle que /leaderboard du bot."""
    con = _con(path)
    try:
        if not _tables_ready(con):
            return []
        rows = con.execute("""SELECT author_id, author_name, COUNT(*) n,
                              AVG(CASE WHEN ret_pct>0 THEN 1.0 ELSE 0 END) wr,
                              SUM(ret_pct) tot
                              FROM d_calls WHERE scored=1
                              GROUP BY author_id HAVING n>=?
                              ORDER BY tot DESC LIMIT ?""",
                            (min_calls, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def user_stats(user_id: str, path: Path | None = None) -> dict:
    """Le dossier d'un membre : messages capturés, calls (12 derniers), l'agrégat."""
    con = _con(path)
    try:
        out = {"n_messages": 0, "calls": [], "n_scored": 0, "wr": None, "tot_ret": None}
        out["n_messages"] = con.execute(
            "SELECT COUNT(*) FROM d_messages WHERE author_id=?",
            (str(user_id),)).fetchone()[0]
        if _tables_ready(con):
            out["calls"] = [dict(r) for r in con.execute(
                """SELECT symbol, direction, entry, posted_at, scored, ret_pct, verdict
                   FROM d_calls WHERE author_id=? ORDER BY posted_at DESC LIMIT 12""",
                (str(user_id),)).fetchall()]
            agg = con.execute(
                """SELECT COUNT(*) n, AVG(CASE WHEN ret_pct>0 THEN 1.0 ELSE 0 END) wr,
                   SUM(ret_pct) tot FROM d_calls
                   WHERE author_id=? AND scored=1""", (str(user_id),)).fetchone()
            out["n_scored"] = agg["n"] or 0
            out["wr"] = agg["wr"]
            out["tot_ret"] = agg["tot"]
        return out
    finally:
        con.close()


def server_stats(path: Path | None = None) -> dict:
    """La photo du serveur : membres, capture 24h/7j, top salons, derniers arrivés."""
    con = _con(path)
    try:
        out = {
            "n_members": con.execute("SELECT COUNT(*) FROM d_members WHERE bot=0").fetchone()[0],
            "n_bots": con.execute("SELECT COUNT(*) FROM d_members WHERE bot=1").fetchone()[0],
            "n_roles": con.execute("SELECT COUNT(*) FROM d_roles").fetchone()[0],
            "m24": con.execute("SELECT COUNT(*) FROM d_messages WHERE fetched_at > ?",
                               (time.time() - 86400,)).fetchone()[0],
            "m7": con.execute("SELECT COUNT(*) FROM d_messages WHERE fetched_at > ?",
                              (time.time() - 7 * 86400,)).fetchone()[0],
            "top_channels": [dict(r) for r in con.execute(
                """SELECT channel_name, COUNT(*) n FROM d_messages
                   WHERE fetched_at > ? AND channel_name IS NOT NULL
                   GROUP BY channel_name ORDER BY n DESC LIMIT 5""",
                (time.time() - 7 * 86400,)).fetchall()],
            "newcomers": [dict(r) for r in con.execute(
                """SELECT user_name, joined_at FROM d_members
                   WHERE bot=0 AND joined_at IS NOT NULL
                   ORDER BY joined_at DESC LIMIT 5""").fetchall()],
            "n_gate_pending": 0,
        }
        rows = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='d_registry'").fetchone()[0]
        if rows:
            out["n_gate_pending"] = con.execute(
                "SELECT COUNT(*) FROM d_registry WHERE kind='gate_pending'").fetchone()[0]
        return out
    finally:
        con.close()
