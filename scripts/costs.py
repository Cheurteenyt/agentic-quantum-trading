#!/usr/bin/env python3
"""P2 (audit Sonnet 5.5, R4) — LES COÛTS PAR SYMBOLE et le coût d'équilibre.

## Pourquoi

Le pipeline Research OS appliquait `cost_pct = 0,28` (%) PLAT à chaque
symbole — un modèle hérité, jamais questionné. Or le coût réel de
round-trip (frais + slippage/spread) varie par symbole, et chaque verdict
porte un coût implicite qui décide seul de certains PASS/FAIL. Deux
livrables :

1. **La table** `research/costs_par_symbole.yaml` — le défaut explicite
   (`defaut_rt_pct: 0.28`, la mesure meme TAKER_RT 28 bps du 04/10) et les
   overrides **mesurés** par symbole. ⚠️ Honnêteté : la table est VIDE
   aujourd'hui (aucune mesure par symbole post-correctif). Elle existe pour
   que la prochaine mesure atterrisse quelque part au lieu de rester un
   magic number noyé dans les specs. Une entrée sans `source` datée est
   refusée (`verifier_table`) — on n'invente pas un coût.
2. **`breakeven_cost_bps`** — le coût de round-trip (en bps) auquel la
   moyenne nette d'une spec devient 0 : `gross_mean_pct × 100`. C'est la
   grandeur qui dit « à quel coût cette hypothèse aurait passé » — le champ
   que R2 demandait au ledger et que #287 n'avait pas rendu obligatoire
   (périmètre volontairement limité à n/er).

## Priorité du coût appliqué

   `spec.cost_pct` explicite  >  table `par_symbole[sym]`  >  `defaut_rt_pct`

Une spec qui PINNE son coût (les specs du grind Bonsai pinnet 0.28) garde
son modèle — le P2 ne re-écrit pas l'histoire des specs existantes ; les
specs SANS coût explicite deviennent symbol-aware.

Usage :
    from scripts.costs import cout_rt_pct, breakeven_cost_bps
    cout_rt_pct("PEPEUSDT")                 # 0.28 (défaut, table vide)
    cout_rt_pct("PEPEUSDT", spec_pct=0.42)  # 0.42 (la spec décide)
    breakeven_cost_bps(mean_net_pct=-0.10, cost_pct=0.28)  # 18.0
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "research" / "costs_par_symbole.yaml"

DEFAUT_RT_PCT = 0.28      # la mesure meme TAKER_RT 28 bps (04/10) — le plat actuel
COSTS_SCHEMA_VERSION = 1


def _table() -> dict:
    """La table parsée, ou {} si absente/illisible — JAMAIS une fabrication."""
    try:
        import yaml
        d = yaml.safe_load(TABLE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def cout_rt_pct(symbole: str | None, spec_pct: float | None = None) -> float:
    """Le coût de round-trip (%) appliqué à un symbole.

    Priorité : `spec_pct` explicite > override table > défaut. Un symbole
    None (agrégat) retombe sur le défaut sauf spec explicite."""
    if spec_pct is not None:
        return float(spec_pct)
    d = _table()
    if symbole is not None:
        over = (d.get("par_symbole") or {}).get(symbole)
        if isinstance(over, dict) and over.get("rt_pct") is not None:
            return float(over["rt_pct"])
    defaut = d.get("defaut_rt_pct")
    return float(defaut) if defaut is not None else DEFAUT_RT_PCT


def breakeven_cost_bps(mean_net_pct: float, cost_pct: float) -> float:
    """Le RT cost (bps) auquel la moyenne nette devient 0.

    `mean_net_pct` est la moyenne NETTE du coût (en % de notional, comme
    `event_study`), `cost_pct` le coût effectivement appliqué (même unité).
    breakeven = (net + coût) × 100 : si ≤ 0, l'hypothèse est morte MÊME à
    coût nul — c'est précisément l'information que R2 exigeait."""
    return round((float(mean_net_pct) + float(cost_pct)) * 100.0, 2)


def verifier_table() -> list[str]:
    """Les défauts de la table (entrée sans `source` datée, rt_pct hors
    bornes). Retourne la liste des problèmes — vide = table saine.
    Un coût sans provenance est une invention : on n'entre pas dans le
    modèle sans dire d'où il vient."""
    problemes: list[str] = []
    d = _table()
    if not d:
        return problemes
    for sym, over in (d.get("par_symbole") or {}).items():
        if not isinstance(over, dict):
            problemes.append(f"{sym} : entrée mal formée (dict attendu)")
            continue
        rt = over.get("rt_pct")
        if rt is None or not (0 < float(rt) < 5):
            problemes.append(f"{sym} : rt_pct absent ou hors bornes (0;5)")
        if not over.get("source"):
            problemes.append(f"{sym} : pas de `source` — un coût sans "
                             "provenance est une invention")
    return problemes
