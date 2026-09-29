#!/usr/bin/env python
"""Whale Radar automatisé — diff des positions des constants fomo, chaque nuit.

Se connecte au navigateur daemon (CDP :9222), mine les positions de tous les
constants (PnL>0 sur 24h/7j/30j), les insère dans data/fomo/fomo.db, puis
produit le radar : confluence + les NOUVELLES positions vs le snapshot
précédent (les achats frais des baleines = le signal).

Usage :
  .venv/bin/python scripts/whale_radar.py                 # mine tout + rapport
  .venv/bin/python scripts/whale_radar.py --top 12        # limiter aux N premiers
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.fomo_harvest import mine_positions  # noqa: E402

DB = ROOT / "data" / "fomo" / "fomo.db"
REPORTS = ROOT / "reports"

ASTEROIDS = {"CATE", "MEME", "BOME", "WIF", "PNUT", "MOODENG", "NEIRO", "TURBO",
             "PENGU", "NOT", "DOGS", "TRUMP", "FARTCOIN", "1000PEPE", "BONK",
             "FLOKI", "DRAM", "PIEVERSE", "SOL", "DOGE", "BTC", "ETH"}


def _aster_universe() -> set[str]:
    """Univers perp Aster LIVE (jamais en dur — leçon PONS, listé sans bruit)."""
    try:
        import urllib.request
        req = urllib.request.Request("https://fapi.asterdex.com/fapi/v1/exchangeInfo",
                                     headers={"User-Agent": "trading-agent/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.load(resp)
        return {s["symbol"][:-4] for s in d.get("symbols", [])
                if s.get("quoteAsset") == "USDT" and s.get("status") == "TRADING"}
    except Exception:  # noqa: BLE001 — repli sur la liste en dur
        return ASTEROIDS


def constants(con: sqlite3.Connection, top: int | None = None) -> list[str]:
    """Constants (PnL>0 sur 24h/7j/30j) + tier list frogmanhaha S/A/B
    (les meilleurs joueurs all-time sont minés même en drawdown courant)."""
    q = ("SELECT handle FROM fomo_traders "
         "WHERE pnl_24h > 0 AND pnl_7d > 0 AND pnl_30d > 0 ORDER BY pnl_30d DESC")
    if top is not None:
        q += f" LIMIT {int(top)}"
    out = [r[0] for r in con.execute(q).fetchall()]
    try:
        tier = [r[0] for r in con.execute(
            "SELECT DISTINCT handle FROM fomo_tier_list "
            "WHERE tier IN ('S','A','B') AND handle IS NOT NULL "
            "AND confidence IN ('high','medium')")]
    except sqlite3.OperationalError:
        tier = []
    out += [h for h in tier if h not in out]
    return out


def _skill(con: sqlite3.Connection) -> dict[str, dict]:
    """Compétence réalisée par baleine (fomo_closed) — un achat d'un joueur
    à 24/24 fermés et +$626K net ne pèse pas comme un joueur moyen."""
    out: dict[str, dict] = {}
    try:
        for handle, n, wins, net in con.execute(
            "SELECT handle, COUNT(*), SUM(dir = '▲'), "
            "SUM(CASE WHEN pnl LIKE '-%' THEN -1 ELSE 1 END * "
            "CAST(REPLACE(REPLACE(pnl, '+', ''), ',', '') AS REAL)) "
            "FROM fomo_closed GROUP BY handle"
        ):
            out[handle] = {"closed": n, "wins": wins or 0, "net": net or 0.0}
    except sqlite3.OperationalError:
        pass
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Whale Radar nocturne (via CDP)")
    ap.add_argument("--top", type=int, default=35)
    args = ap.parse_args()

    con = sqlite3.connect(DB, timeout=30)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS fomo_positions (
        handle     TEXT    NOT NULL, ticker TEXT NOT NULL, qty TEXT,
        value_usd  REAL, dir TEXT, captured_at REAL NOT NULL,
        PRIMARY KEY (handle, ticker, captured_at));
    CREATE TABLE IF NOT EXISTS fomo_social (
        handle TEXT NOT NULL, followers TEXT, following TEXT, mutuals TEXT,
        x_ref TEXT, bio TEXT, captured_at REAL NOT NULL,
        PRIMARY KEY (handle, captured_at));
    """)
    handles = constants(con, top=args.top)
    print(f"[radar] démarrage: {len(handles)} constants à miner via CDP :9222", flush=True)
    if not handles:
        print("[radar] aucun constant en base — miner le leaderboard d'abord", file=sys.stderr)
        return 1
    now = time.time()
    previous: dict[str, set[str]] = {}
    for (handle, ticker) in con.execute(
        "SELECT handle, ticker FROM fomo_positions WHERE captured_at < ?", (now,)
    ):
        previous.setdefault(handle, set()).add(ticker)

    inserted = 0
    fresh: dict[str, list] = defaultdict(list)
    mined_now: dict[str, dict] = {}
    skill = _skill(con)
    for i, handle in enumerate(handles, 1):
        try:
            res = mine_positions(handle)
        except Exception as exc:  # noqa: BLE001 — un profil en échec ne bloque pas le radar
            print(f"[radar] {i}/{len(handles)} {handle}: ERREUR {str(exc)[:60]}", file=sys.stderr)
            continue
        pos = res["mined"]
        mined_now[handle] = pos
        soc = res.get("social") or {}
        if soc.get("followers"):
            con.execute("INSERT OR IGNORE INTO fomo_social VALUES (?,?,?,?,?,?,?)",
                        (handle, soc.get("followers"), soc.get("following"),
                         soc.get("mutuals"), soc.get("x_ref"), soc.get("bio"), now))
        prev = previous.get(handle, set())
        for ticker, p in pos.items():
            con.execute("INSERT OR IGNORE INTO fomo_positions VALUES (?,?,?,?,?,?)",
                        (handle, ticker, p.get("qty"), p.get("value_usd"), p.get("dir"), now))
            inserted += 1
            if ticker not in prev and p.get("value_usd", 0) >= 5000:
                fresh[handle].append((ticker, p))
        print(f"[radar] {i}/{len(handles)} {handle}: {len(pos)} positions "
              f"({len([t for t in pos if t not in prev])} nouvelles)", flush=True)
    con.commit()

    # 2e passage pour les profils restés à 0 (course Privy après un restart)
    empty = [h for h, p in mined_now.items() if not p]
    for handle in empty:
        try:
            res = mine_positions(handle)
            if res["mined"]:
                mined_now[handle] = res["mined"]
                prev = previous.get(handle, set())
                for ticker, p in res["mined"].items():
                    con.execute("INSERT OR IGNORE INTO fomo_positions VALUES (?,?,?,?,?,?)",
                                (handle, ticker, p.get("qty"), p.get("value_usd"),
                                 p.get("dir"), now))
                    inserted += 1
                    if ticker not in prev and p.get("value_usd", 0) >= 5000:
                        fresh[handle].append((ticker, p))
                print(f"[radar] 2e passe {handle}: {len(res['mined'])} positions récupérées",
                      flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[radar] 2e passe {handle}: ERREUR {str(exc)[:60]}", file=sys.stderr)
    con.commit()

    # confluence à l'instant t
    by_ticker: dict[str, dict] = defaultdict(lambda: {"traders": [], "total": 0.0, "dirs": []})
    for handle, pos in mined_now.items():
        for ticker, p in pos.items():
            r = by_ticker[ticker]
            if handle not in r["traders"]:
                r["traders"].append(handle)
            r["total"] += p.get("value_usd", 0)
            r["dirs"].append(p.get("dir", "?"))
    conv = [(t, v) for t, v in by_ticker.items()
            if len(v["traders"]) >= 3 and v["total"] >= 5000
            and v["total"] / len(v["traders"]) >= 2000]
    conv.sort(key=lambda kv: (-len(kv[1]["traders"]), -kv[1]["total"]))

    nowdt = datetime.now(tz=timezone.utc)
    lines = [
        f"# Whale Radar — {nowdt:%d/%m/%Y %H:%M} UTC",
        f"{len(handles)} constants minés via CDP, {inserted} lignes de positions.",
        "NOUVEAUX ACHATS (>= $5k, absents du snapshot précédent) :",
        "",
    ]
    any_fresh = False
    for handle, items in fresh.items():
        sk = skill.get(handle)
        tag = (f" [compétence: {sk['wins']}/{sk['closed']} fermés, "
               f"+${sk['net']:,.0f} réalisé]" if sk and sk["closed"] else "")
        for ticker, p in items:
            any_fresh = True
            lines.append(f"- **@{handle} achète {ticker}** ({p.get('qty')}, "
                         f"${p.get('value_usd'):,.0f}, {p.get('dir')}){tag}")
    if not any_fresh:
        lines.append("- aucun nouvel achat >= $5k depuis le snapshot précédent")
    lines += ["", "## Confluence (>= 3 baleines, >= $5k, >= $2k/tenant)", "",
              "| Token | Baleines | Valeur | Sentiment | Sur Aster ? |", "|---|---|---|---|---|"]
    for ticker, v in conv:
        up = sum(1 for d0 in v["dirs"] if d0 == "▲")
        aster = "OUI (perp)" if ticker in _aster_universe() else "fomo"
        lines.append(f"| **{ticker}** | {len(v['traders'])}/35 | ${v['total']:,.0f} | "
                     f"{'▲' if up * 2 > len(v['dirs']) else '▼'} | {aster} |")
    out = REPORTS / f"whale-radar-{nowdt:%Y%m%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[radar] {out}")
    con.close()
    return 0


def _main_guard() -> int:
    """L'échec doit être VISIBLE : traceback dans reports/whale_radar_err.log
    + stderr, exit non-zéro (le ExecStart=- du nocturne ignore le code mais
    la trace reste)."""
    try:
        return main()
    except BaseException:
        err = REPORTS / "whale_radar_err.log"
        try:
            with err.open("a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now(tz=timezone.utc):%Y-%m-%d %H:%M:%S} UTC "
                        f"— whale_radar crash ===\n")
                traceback.print_exc(file=f)
        except OSError:
            pass
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(_main_guard())
