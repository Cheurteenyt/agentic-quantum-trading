#!/usr/bin/env python3
"""Scanner de funding Aster — ou va l'argent des frais de financement.

Le cache funding Aster (62 symboles, rafraichi chaque nuit par
refresh_aster_cache) contient une mine jamais transformee en decisions :
le taux de funding de chaque perp, son historique sur 100 points, son
dernier reglement.

Ce scanner calcule par symbole :
  - le funding annualise (bps/8h x 3 reglements/jour x 365 / 100)
  - la moyenne vs le dernier reglement (ca chauffe / ca refroidit)
  - qui encaisse : funding positif = les longs paient les shorts,
    negatif = l'inverse

Sortie : rapport horodate dans reports/ + console. Le scanner RANGEOUE,
il ne conseille pas : un perp seul reste un risque directionnel. Le carry
veritablement hedgge demande une seconde jambe (spot long ailleurs, perp
inverse sur une autre venue — le service multi_exchange existe).

    python scripts/funding_scanner.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "backend" / "services" / "onchain" / "aster" / \
    "aster_public_funding_history_cache.json"
REPORTS = ROOT / "reports"

BPS_PER_8H_TO_ANNUAL_PCT = 3 * 365 / 100  # 3 reglements/jour, 100 bps = 1 %
SEUIL_EXTREME_ANN = 50.0  # % annualises

# Perps d'actions / matieres premieres : horaires New York, erreur
# -2016 NO_TRADING_WINDOW hors session (working-map Aster legacy).
SESSION_GATED_PREFIXES = (
    "INTC", "MSFT", "NVDA", "MSTR", "GOOGL", "AAPL", "AMZN", "TSLA",
    "META", "NFLX", "AMD", "ORCL", "CRCL", "CLU", "BZ", "XAU", "XAG",
)


def _session_note(symbol: str) -> str:
    if symbol.startswith(SESSION_GATED_PREFIXES):
        return " ⚠️ session NY (hors session : NO_TRADING_WINDOW)"
    return ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ann_pct(bps_per_8h: float | None) -> float | None:
    return bps_per_8h * BPS_PER_8H_TO_ANNUAL_PCT if bps_per_8h is not None else None


def load_ranked() -> list[dict]:
    with CACHE.open(encoding="utf-8") as fh:
        cache = json.load(fh)
    rows: list[dict] = []
    for sym, entry in cache.get("symbols", {}).items():
        data = entry.get("data") or {}
        latest = _ann_pct(data.get("latest_funding_bps_per_8h"))
        avg = _ann_pct(data.get("avg_funding_bps_per_8h"))
        if latest is None or avg is None:
            continue
        rows.append({
            "symbol": sym,
            "latest_ann": latest,
            "avg_ann": avg,
            "heat": latest - avg,
            "who_collects": "shorts" if latest > 0 else "longs",
            "session_note": _session_note(sym),
        })
    rows.sort(key=lambda r: abs(r["latest_ann"]), reverse=True)
    return rows


def _fmt(v: float) -> str:
    return f"{v:+.1f} %"


def write_report(rows: list[dict]) -> Path:
    now = _utc_now()
    extremes = [r for r in rows if abs(r["latest_ann"]) >= SEUIL_EXTREME_ANN]
    lines = [
        "# Scanner de funding Aster",
        "",
        f"Genere : {now} UTC — source : cache Aster nocturne ({len(rows)} symboles)",
        "",
        "## Regle de lecture",
        "",
        "Funding positif = les LONGS paient les SHORTS (les shorts encaissent).",
        "Negatif = l'inverse. Un perp seul reste un risque directionnel : le",
        "carry hedgge exige une seconde jambe. |Annualise| > "
        f"{SEUIL_EXTREME_ANN:.0f} % = regime extreme, a la fois opportun et",
        "signal de surchauffe.",
        "",
        f"## Top 10 (|annualise| le plus eleve) — {len(extremes)} extreme(s) > "
        f"{SEUIL_EXTREME_ANN:.0f} %",
        "",
        "| symbole | dernier (ann.) | moyenne 100p (ann.) | chauffe | qui encaisse |",
        "|---|---|---|---|---|",
    ]
    for r in rows[:10]:
        heat = "chauffe" if r["heat"] > 0 else "refroidit"
        lines.append(
            f"| {r['symbol']} | {_fmt(r['latest_ann'])} | {_fmt(r['avg_ann'])} "
            f"| {heat} | {r['who_collects']} |{r['session_note']}"
        )
    if extremes:
        lines += ["", "### Regime extreme", ""]
        for r in extremes[:10]:
            lines.append(
                f"- **{r['symbol']}** : {_fmt(r['latest_ann'])} annualise "
                f"→ les {r['who_collects']} encaissent"
            )
    lines += [
        "",
        "Le scanner range, il ne conseille pas. Toute jambe engagee reste un",
        " choix de gestion du risque, pas une recommandation.",
    ]
    out = REPORTS / f"funding-scanner-{now.replace(':', '').replace('-', '')}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    fixed = REPORTS / "funding-scanner.md"
    fixed.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    rows = load_ranked()
    if not rows:
        print("[scanner] cache funding vide — lancer refresh_aster_cache d'abord",
              file=sys.stderr)
        return 1
    out = write_report(rows)
    print(f"[scanner] {len(rows)} symboles classes — rapport : {out}")
    print("[scanner] top 3 :")
    for r in rows[:3]:
        print(f"  {r['symbol']:16} {_fmt(r['latest_ann'])} annualise "
              f"→ les {r['who_collects']} encaissent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
