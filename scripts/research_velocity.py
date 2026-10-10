#!/usr/bin/env python3
"""E5 — la PRODUCTIVITÉ de la recherche, mesurée et affichée.

La revue d'architecture (2026-10-10) a constaté le fait dur : 657 commits,
**0 candidat confirmé**, et AUCUN indicateur ne dit si une semaine a été
bonne. Ni le nombre d'hypothèses TUÉES proprement, ni de lots de découverte
exécutés. On ne peut pas piloter ce qu'on ne mesure pas.

Ce script calcule, depuis la SOURCE DE VÉRITÉ (`research/ledger/trials.jsonl`,
le même que les oracles — pas une 2ème base qui divergerait), une métrique
de vélocité hebdo et l'affiche. Objectif : une ligne « cette semaine a-t-elle
produit ? » dans STATE.md.

## Les 3 métriques (définition de « fini » hebdo, revue §6)

1. **Lots exécutés** — nombre d'entrées ledger vivantes de la semaine (une
   entrée = un essai journalisé). Une semaine sans entrée = semaine morte.
2. **Hypothèses tranchées** — verdicts rendus (vivants, non-superseded), par
   nature. Un FAIL est un RÉSULTAT (une fausse piste fermée), pas un échec.
3. **Candidats** — verdicts positifs vivants (PASS/DISCOVERY_PASS). C'est le
   seul vrai « produit ». Aujourd'hui : 0, et c'est honnête de le voir.

La doctrine du dépôt : un chiffre sans commande de reproduction est présumé
halluciné. Ce script imprime SA commande en tête.

Usage :
    python scripts/research_velocity.py           # affiche les métriques
    python scripts/research_velocity.py --state   # bloc à coller dans STATE.md
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research" / "ledger" / "trials.jsonl"

# Verdicts qui COMPTENT comme preuve positive (cf. lab_ledger.confirmation).
POSITIFS = ("PASS", "DISCOVERY_PASS")
# Verdicts qui sont des RÉSULTATS (une hypothèse tranchée), positifs ou non.
TRANCHE = ("PASS", "DISCOVERY_PASS", "FAIL", "DISCOVERY_FAIL",
           "SOUS_PUISSANT", "NUL")


def _semaine(iso_date: str) -> str | None:
    """Semaine ISO (AAAA-Www) d'une date ledger 'YYYY-MM-DD'. None si illisible."""
    try:
        d = datetime.fromisoformat(iso_date).replace(tzinfo=timezone.utc)
        y, w, _ = d.isocalendar()
        return f"{y}-W{w:02d}"
    except (ValueError, TypeError):
        return None


def charger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in
            LEDGER.read_text("utf-8").splitlines() if l.strip()]


def metriques(entrees: list[dict]) -> dict:
    """Calcule les métriques depuis les entrées VIVANTES (non-superseded) —
    une entrée superseded est hors preuve (PR#253), la compter comme de la
    productivité serait se créditer d'un travail invalidé."""
    vifs = [e for e in entrees if not e.get("superseded")]
    # une dérogation n_degression reste une entrée vivante (elle compte comme
    # un essai fait, juste sans n lisible) — on la garde dans le décompte.
    par_semaine: dict[str, list[dict]] = {}
    for e in vifs:
        s = _semaine(e.get("date") or e.get("ts", "")[:10] or "")
        if s:
            par_semaine.setdefault(s, []).append(e)

    semaine_courante = None
    if par_semaine:
        semaine_courante = max(par_semaine)

    def resume(lst: list[dict]) -> dict:
        verd = Counter(e.get("verdict", "?") for e in lst)
        return {
            "lots": len(lst),
            "tranchees": sum(verd.get(v, 0) for v in TRANCHE),
            "candidats": sum(verd.get(v, 0) for v in POSITIFS),
            "verdicts": dict(verd),
        }

    # semaine_courante est None seulement si par_semaine est vide (aucune
    # entrée vivante avec date lisible) ; .get(None, []) retomberait sur le
    # défaut mais on le rend explicite pour ne pas dépendre de ce refus.
    courante_lst = par_semaine.get(semaine_courante, []) if semaine_courante else []
    return {
        "semaine_courante": semaine_courante,
        "cette_semaine": resume(courante_lst),
        "toutes_semaines": {s: resume(lst)
                            for s, lst in sorted(par_semaine.items())},
        "total_vivant": len(vifs),
        "total_ledger": len(entrees),
    }


def bloc_state(m: dict) -> str:
    """Le bloc à afficher dans STATE.md (hors marqueurs générés)."""
    cs = m["cette_semaine"]
    s = m["semaine_courante"] or "—"
    lignes = [
        "## Productivité (généré : `python scripts/research_velocity.py`)",
        f"- Semaine courante **{s}** : **{cs['lots']}** lot(s) exécuté(s), "
        f"**{cs['tranchees']}** hypothèse(s) tranchée(s), "
        f"**{cs['candidats']}** candidat(s).",
    ]
    if m["toutes_semaines"]:
        lignes.append("- Historique vivant (par semaine) :")
        for sem, r in m["toutes_semaines"].items():
            lignes.append(
                f"  - {sem} : {r['lots']} lots · {r['tranchees']} tranchées · "
                f"{r['candidats']} candidats · {r['verdicts']}")
    lignes.append(
        "- Définition de « fini » hebdo : ≥ 1 lot exécuté ET journalisé, "
        "≥ 1 hypothèse tranchée. Un FAIL est un résultat (fausse piste fermée).")
    return "\n".join(lignes)


def main() -> int:
    entrees = charger()
    if not entrees:
        print("VELOCITÉ: ledger absent ou vide — aucune productivité mesurable.")
        return 0
    m = metriques(entrees)
    if "--state" in sys.argv:
        print(bloc_state(m))
        return 0
    cs = m["cette_semaine"]
    print(f"VELOCITÉ RECHERCHE — semaine {m['semaine_courante']}")
    print(f"  cette semaine : {cs['lots']} lots · {cs['tranchees']} tranchées · "
          f"{cs['candidats']} candidats")
    print(f"  total ledger  : {m['total_ledger']} entrées, "
          f"{m['total_vivant']} vivantes (non-superseded)")
    print("  historique vivant par semaine :")
    for sem, r in m["toutes_semaines"].items():
        print(f"    {sem} : {r['lots']} lots · {r['tranchees']} tranchées · "
              f"{r['candidats']} candidats")
    # le signal de la revue : une semaine sans lot = semaine morte
    if cs["lots"] == 0:
        print("\n  ⚠️  0 lot cette semaine — la machine n'a pas produit de "
              "résultat cette semaine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
