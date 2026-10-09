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
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "backend" / "services" / "onchain" / "aster" / \
    "aster_public_funding_history_cache.json"
REPORTS = ROOT / "reports"

BPS_PER_8H_TO_ANNUAL_PCT = 3 * 365 / 100  # 3 reglements/jour, 100 bps = 1 %
SEUIL_EXTREME_ANN = 50.0  # % annualises


def _per_day_for(interval_h) -> float:
    """Règlements/jour réels d'après l'intervalle MESURÉ par le refresher
    (FIX F12, médiane des gaps) — le champ du cache est étiqueté « per_8h »
    mais porte du per-intervalle : annualiser à 3/8 h figés mentait de ×2
    (4 h) à ×8 (1 h). Fallback 8 h = cadence standard si non mesuré."""
    try:
        return 24.0 / float(interval_h) if interval_h else 3.0
    except (TypeError, ValueError):
        return 3.0

# FIX F-041 : la fraîcheur du cache funding est un CONTRAT, pas une
# information. Le cache est un SNAPSHOT live (F-030) : chaque symbole porte
# son propre `cached_at`, et 48 des 73 symboles de la prod ont > 25 h
# (9 > 30 j, max 127 j) alors que le mtime du fichier n'a que 15,5 h.
# Un funding vieux de 4 mois annualisé à 3×365 donne un chiffre qui a
# l'air d'un taux et qui n'en est pas un.
FUNDING_MAX_AGE_S = 25 * 3600


def load_fresh_ranked(max_age_s: float = FUNDING_MAX_AGE_S) -> tuple[list[dict], int]:
    """Les symboles du cache dont le `cached_at` est dans la fenêtre.

    Retourne (rows, n_rejetes). Un symbole sans `cached_at` est REJETÉ :
    l'absence d'horodatage n'est pas une fraîcheur, c'est une donnée qu'on
    ne peut pas dater — et le code qui suit annualise ce qu'on lui donne.
    """
    try:
        with CACHE.open(encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return [], 0
    now = time.time()
    rows: list[dict] = []
    rejected = 0
    for sym, entry in cache.get("symbols", {}).items():
        data = entry.get("data") or {}
        latest = _ann_pct(data.get("latest_funding_bps_per_8h"),
                          data.get("funding_interval_hours"))
        avg = _ann_pct(data.get("avg_funding_bps_per_8h"),
                       data.get("funding_interval_hours"))
        if latest is None or avg is None:
            continue
        age = now - float(entry.get("cached_at") or 0)
        if age > max_age_s:
            rejected += 1
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
    return rows, rejected


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


def _ann_pct(bps_per_8h: float | None, interval_h=None) -> float | None:
    if bps_per_8h is None:
        return None
    return bps_per_8h * (_per_day_for(interval_h) * 365 / 100)


def load_ranked() -> list[dict]:
    """Compatibilité : délègue à load_fresh_ranked (F-041)."""
    rows, _ = load_fresh_ranked()
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
    rows, rejected = load_fresh_ranked()
    if rejected:
        print(f"[scanner] {rejected} symbole(s) rejete(s) — cached_at > 25 h "
              f"(funding trop vieux pour etre annualise)", file=sys.stderr)
    if not rows:
        print("[scanner] cache funding vide ou tout perime — lancer "
              "refresh_aster_cache d'abord", file=sys.stderr)
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
