#!/usr/bin/env python
"""Rapport de CONVERGENCE par perp Aster — les trois lentilles en une table.

Pour chaque perp suivi, croise :
  - la pression X        (x_pressure : vélocité de mentions, calls L/S)
  - la vélocité d'OI     (klines.db:oi_history, 2 derniers snapshots maison)
  - le funding annualisé (cache Aster)
Un perp dont les TROIS lentilles penchent du même côté = confluence complète —
le signal le plus rare et le plus structuré que notre pile produise.

Usage :
  .venv/bin/python scripts/aster_convergence.py
"""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

XDB = ROOT / "data" / "warehouse" / "x_posts.db"
KDB = ROOT / "data" / "warehouse" / "klines.db"
REPORTS = ROOT / "reports"


def _x_pressure(max_age_s: float = 26 * 3600) -> dict[str, dict]:
    """Pression X par ticker, filtrée par fraîcheur.

    x_aster_pulse réécrit x_pressure en INSERT OR REPLACE par ticker : si le
    pulse ne tourne plus (crash, service off), une ligne fossile votait
    indéfiniment dans la confluence. 26 h = 1 cycle nightly + marge."""
    try:
        con = sqlite3.connect(XDB, timeout=60)
        rows = con.execute(
            "SELECT ticker, posts, velocity, longs, shorts, captured_at "
            "FROM x_pressure"
        ).fetchall()
        con.close()
        now = time.time()
        return {t: {"posts": p, "vx": v, "longs": lo, "shorts": sh}
                for t, p, v, lo, sh, cap in rows
                if cap and now - float(cap) <= max_age_s}
    except sqlite3.OperationalError:
        return {}


def _oi_velocity(max_stale_h: float = 6.0) -> dict[str, float]:
    """ΔOI % entre les deux derniers snapshots par symbole — le plus récent
    doit être FRAIS : le composite crowding impose OI_MAX_STALE_H = 6 h, ici
    un oi-collector arrêté 3 jours produisait un ΔOI fossile affiché comme
    actuel et votant dans la confluence."""
    out: dict[str, float] = {}
    try:
        con = sqlite3.connect(KDB, timeout=60)
        now_ms = time.time() * 1000
        for (sym,) in con.execute("SELECT DISTINCT symbol FROM oi_history"):
            pts = con.execute(
                "SELECT open_interest, captured_at_ms FROM oi_history "
                "WHERE symbol = ? ORDER BY captured_at_ms DESC LIMIT 2",
                (sym,)).fetchall()
            if len(pts) == 2 and pts[1][0] and pts[0][1] \
                    and now_ms - float(pts[0][1]) <= max_stale_h * 3600_000:
                out[sym[:-4]] = (pts[0][0] - pts[1][0]) / pts[1][0] * 100
        con.close()
    except sqlite3.OperationalError:
        pass
    return out


def main() -> int:
    from scripts.memecoin_pulse import funding_row

    xp = _x_pressure()
    oi = _oi_velocity()
    tickers = sorted(set(xp) | {s for s in oi})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# Convergence Aster — X × OI × funding",
        f"{today} — {len(tickers)} perps croisés.",
        "",
        "| Perp | X (posts ×v) | Calls L/S | ΔOI | Funding ann. | Lecture |",
        "|---|---|---|---|---|---|",
    ]
    confl = []
    for t in tickers:
        x = xp.get(t, {})
        d_oi = oi.get(t)
        _, annual = funding_row(t + "USDT")
        fund_s = f"{annual:+.0f} %" if annual is not None else "—"
        posts = x.get("posts", 0)
        vx = x.get("vx")
        vx_s = f"{posts} ×{vx:.1f}" if posts else "—"
        calls = f"{x.get('longs', 0)}L/{x.get('shorts', 0)}S" if posts else "—"
        doi_s = f"{d_oi:+.1f} %" if d_oi is not None else "—"

        # lecture : combien de lentilles penchent, et de quel côté
        bias = 0
        if posts >= 3 and x.get("longs", 0) > x.get("shorts", 0):
            bias += 1
        elif posts >= 3 and x.get("shorts", 0) > x.get("longs", 0):
            bias -= 1
        if d_oi is not None:
            if d_oi > 0.5:
                bias += 1
            elif d_oi < -0.5:
                bias -= 1
        fund_bias = 0
        if annual is not None:
            # funding très négatif = shorts payent cher (crowded short)
            if annual <= -30:
                fund_bias = -1
            elif annual >= 50:
                fund_bias = +1
        lecture = {
            3: "**CONFLUENCE 3/3**", 2: "convergence 2/3",
            -3: "**CONFLUENCE 3/3 (short)**", -2: "convergence 2/3 (short)",
        }.get(bias + fund_bias * 0, "")  # fund lu séparément ci-dessous
        if bias >= 2 and fund_bias != 0:
            lecture += " · funding " + ("élevé (crowded long)" if fund_bias > 0
                                        else "négatif (crowded short)")
        row = f"| ${t} | {vx_s} | {calls} | {doi_s} | {fund_s} | {lecture or '—'} |"
        lines.append(row)
        if abs(bias) >= 2:
            confl.append((t, bias))

    if confl:
        lines += ["", "## Confluences détectées", ""]
        for t, b in confl:
            side = "LONG" if b > 0 else "SHORT"
            lines.append(f"- **${t}** : {side} — X et OI penchent ensemble")
    else:
        lines += ["", "Aucune convergence ≥ 2 lentilles ce cycle — normal, "
                  "c'est rare par construction."]

    out = REPORTS / f"aster-convergence-{datetime.now(timezone.utc):%Y-%m-%d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[convergence] {len(tickers)} perps, {len(confl)} confluences -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
