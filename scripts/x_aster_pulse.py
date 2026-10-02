#!/usr/bin/env python
"""Pression X par perp Aster — le pont explicite X → décisions Aster.

Pour chaque perp suivi : mentions X sur 24h vs les 24h précédentes
(vélocité), calls long/short du registre, engagement total, funding
annualisé du cache Aster. Sortie : table `x_pressure` + rapport classé.

Un perp dont X s'embrase (vélocité ≥ 2, ≥ 3 posts) avec un consensus
directionnel est un candidat onde — le wave_detector croise déjà la
vélocité X, ce rapport ajoute la VUE D'ENSEMBLE par perp, chaque nuit.

Usage :
  .venv/bin/python scripts/x_aster_pulse.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

XDB = ROOT / "data" / "warehouse" / "x_posts.db"
REPORTS = ROOT / "reports"

MAJEURS = ["BTC", "ETH", "SOL", "ASTER", "XRP", "BNB", "DOGE"]


def _universe() -> list[str]:
    try:
        from scripts.memecoin_pulse import MEMECOINS
        mem = {t[:-4] if t.endswith("USDT") else t for t in MEMECOINS}
    except Exception:  # noqa: BLE001
        mem = set()
    return sorted(set(mem) | set(MAJEURS))


def _mentions(con: sqlite3.Connection, ticker: str, day_prefix: str) -> tuple[int, float]:
    """(nb posts, engagement cumulé) pour $TICKER sur un préfixe de date."""
    row = con.execute(
        "SELECT COUNT(*), COALESCE(SUM("
        " COALESCE(CAST(json_extract(metrics,'$.views') AS INTEGER),0)"
        "+ COALESCE(CAST(json_extract(metrics,'$.likes') AS INTEGER),0)),0) "
        "FROM x_posts WHERE fetched_at LIKE ? AND ("
        " text LIKE ? OR text LIKE ?)",
        (day_prefix + "%", f"%${ticker}%", f"%${ticker}USDT%")).fetchone()
    return row[0], row[1] or 0.0


def _calls(con: sqlite3.Connection, ticker: str, day_prefix: str) -> tuple[int, int]:
    """(longs, shorts) appelés aujourd'hui sur le ticker."""
    longs = shorts = 0
    for (direction,) in con.execute(
        "SELECT c.direction FROM x_calls c JOIN x_posts p ON p.post_id = c.post_id "
        "WHERE p.fetched_at LIKE ? AND (c.symbol = ? OR c.symbol = ?)",
        (day_prefix + "%", ticker, ticker + "USDT")):
        if direction == "long":
            longs += 1
        elif direction == "short":
            shorts += 1
    return longs, shorts


def main() -> int:
    from scripts.memecoin_pulse import funding_row

    uni = _universe()
    today = (datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    con = sqlite3.connect(XDB, timeout=60)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows: list[dict] = []
    for ticker in uni:
        n_now, engage = _mentions(con, ticker, today)
        n_prev, _ = _mentions(con, ticker, yesterday)
        if n_now == 0 and n_prev == 0:
            continue
        longs, shorts = _calls(con, ticker, today)
        rate, annual = funding_row(ticker + "USDT")
        # auteurs uniques : la largeur réelle du signal (anti-spam)
        authors = con.execute(
            "SELECT COUNT(DISTINCT author_handle) FROM x_posts "
            "WHERE fetched_at LIKE ? AND (text LIKE ? OR text LIKE ?)",
            (today + "%", f"%${ticker}%", f"%${ticker}USDT%")).fetchone()[0]
        rows.append({
            "ticker": ticker, "posts": n_now, "posts_prev": n_prev,
            "velocity": round(n_now / max(n_prev, 1), 2),
            "longs": longs, "shorts": shorts, "engagement": engage,
            "funding_pct": annual, "authors": authors,
        })
    con.executescript("""
    CREATE TABLE IF NOT EXISTS x_pressure (
        ticker TEXT PRIMARY KEY, posts INTEGER, posts_prev INTEGER,
        velocity REAL, longs INTEGER, shorts INTEGER, engagement REAL,
        funding_pct REAL, captured_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS x_signal_history (
        day TEXT NOT NULL, ticker TEXT NOT NULL,
        mentions INTEGER, unique_authors INTEGER, velocity REAL,
        calls_long INTEGER, calls_short INTEGER, consensus REAL,
        engagement REAL, captured_at REAL NOT NULL,
        PRIMARY KEY (day, ticker));
    """)
    now = datetime.now(timezone.utc).timestamp()
    for r in rows:
        con.execute("INSERT OR REPLACE INTO x_pressure VALUES (?,?,?,?,?,?,?,?,?)",
                    (r["ticker"], r["posts"], r["posts_prev"], r["velocity"],
                     r["longs"], r["shorts"], r["engagement"], r["funding_pct"], now))
        # historique quotidien des signaux X — la matière première du futur
        # backtest des indicateurs X (il faut ~3 semaines de points pour
        # que la règle N≥10 signifie quelque chose)
        calls_total = r["longs"] + r["shorts"]
        consensus = ((r["longs"] - r["shorts"]) / calls_total
                     if calls_total else 0.0)
        con.execute(
            "INSERT OR REPLACE INTO x_signal_history VALUES (?,?,?,?,?,?,?,?,?,?)",
            (today, r["ticker"], r["posts"], r["authors"], r["velocity"],
             r["longs"], r["shorts"], round(consensus, 3),
             r["engagement"], now))
    con.commit()
    con.close()

    rows.sort(key=lambda r: (-r["velocity"], -r["posts"]))
    hot = [r for r in rows if r["velocity"] >= 2 and r["posts"] >= 3]
    lines = [
        f"# Pression X × Aster — {today}",
        f"{len(rows)} perps suivis côté X, {len(hot)} en embrasement (vélocité ≥ 2, ≥ 3 posts).",
        "",
        "## Embrasements", "",
    ]
    if not hot:
        lines.append("- aucun : X est calme sur l'univers suivi")
    for r in hot:
        cons = (f"{r['longs']} long / {r['shorts']} short"
                if r["longs"] + r["shorts"] else "aucun call")
        fund = f"{r['funding_pct']:+.0f} % ann." if r["funding_pct"] is not None else "?"
        lines.append(f"- **${r['ticker']}** : {r['posts']} posts (×{r['velocity']} vs hier), "
                     f"engagement {r['engagement']:,.0f} — {cons} — funding {fund}")
    lines += ["", "## Consensus directionnel (≥ 2 calls aujourd'hui)", "",
              "| Perp | Posts | Vélocité | Calls | Funding |", "|---|---|---|---|---|"]
    for r in rows:
        if r["longs"] + r["shorts"] >= 2:
            fund = f"{r['funding_pct']:+.0f} %" if r["funding_pct"] is not None else "?"
            lines.append(f"| ${r['ticker']} | {r['posts']} | ×{r['velocity']} "
                         f"| {r['longs']} L / {r['shorts']} S | {fund} |")
    out = REPORTS / f"x-aster-pulse-{today}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[pulse] {len(rows)} perps, {len(hot)} embrasements -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
