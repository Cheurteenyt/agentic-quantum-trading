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
4. **Part de recherche** (audit Sonnet 5.5, §R3-5) — % des livraisons des
   7 derniers jours qui exécutent ou pré-enregistrent une hypothèse,
   objectif ≥ 50 %. C'est la métrique qui JUGE le gel de la CI (docs/38) :
   pas « la CI est immobile » mais « la part de recherche remonte ».

La doctrine du dépôt : un chiffre sans commande de reproduction est présumé
halluciné. Ce script imprime SA commande en tête.

Usage :
    python scripts/research_velocity.py           # affiche les métriques
    python scripts/research_velocity.py --state   # bloc à coller dans STATE.md
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "research" / "ledger" / "trials.jsonl"
HYPOTHESES = ROOT / "research" / "hypotheses"

# Verdicts qui COMPTENT comme preuve positive (cf. lab_ledger.confirmation).
POSITIFS = ("PASS", "DISCOVERY_PASS")
# Verdicts qui sont des RÉSULTATS (une hypothèse tranchée), positifs ou non.
TRANCHE = ("PASS", "DISCOVERY_PASS", "FAIL", "DISCOVERY_FAIL",
           "SOUS_PUISSANT", "NUL")
# Verdicts de DÉCOUVERTE — les seuls qui DOIVENT porter un `n` (garde N6 de
# lab_ledger). Une ligne DISCOVERY_* sans n est MUETTE (information nulle).
DISCOVERY_VERDICTS = ("DISCOVERY_PASS", "DISCOVERY_FAIL")


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
        # Une ligne MUETTE = un verdict DISCOVERY_* sans `n` (ni er). Le garde
        # N6 de lab_ledger refuse désormais d'en créer (fail-closed), mais les
        # 16 lignes historiques (écrites avant le garde) sont muettes et
        # polluent la vélocité : « 17 lots » mélange 1 verdict chiffré et 16
        # verdicts nus. On les COMPTE à part pour que la métrique soit honnête
        # (un verdict sans n ni moyenne ne dit ni la distance au seuil ni le
        # coût d'équilibre — de l'information nulle). Un PASS/FAIL classique
        # n'est pas concerné (seuls les DISCOVERY_* doivent porter n).
        muets = [e for e in lst
                 if e.get("verdict") in DISCOVERY_VERDICTS
                 and not e.get("n")]
        return {
            "lots": len(lst),
            "lots_chiffres": len(lst) - len(muets),
            "lots_muets": len(muets),
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


# --- Échéances / hypothèses non tranchées (revue Sonnet 5.5, 2026-10-10, P5) ---
#
# Fait mesuré : sur 12 hypothèses pré-enregistrées (research/hypotheses/*.md),
# 8 sont joignables au ledger par leur champ `stratégie :` et AUCUNE n'a de
# verdict VIVANT (2 FAIL superseded, 6 jamais tranchées). Le retard existait
# mais était invisible — aucun indicateur ne le disait. On le mesure ici, SANS
# inventer de date d'échéance : on rapproche chaque hypothèse pré-enregistrée
# du ledger par sa stratégie déclarée, et on compte celles qui n'ont AUCUN
# verdict vivant. C'est un fait (pas une estimation), la donnée existe déjà.
_STRAT_RE = re.compile(r"strat[ée]gie\s*:\s*`?([A-Za-z0-9_\-\.]+)`?")

APERCU_ECHEANCES = 3
"""Nombre d'échéances nommées inline dans le bloc STATE.md (cf. bloc_state).
Le compte total reste affiché ; seul l'aperçu est borné, pour tenir le budget
de 3 Ko de `research/STATE.md` (audit_check C4)."""

HISTO_SEMAINES = 3
"""Nombre de semaines d'historique affichées inline (les plus récentes).
Même raison : sans plafond, le bloc grossit d'une ligne par semaine et
repousse STATE.md au-delà de sa borne."""


def _declarer_strategie(md_path: Path) -> str | None:
    """L'identifiant de stratégie déclaré dans un .md d'hypothèse, ou None.

    Chaque hypothèse porte une ligne `stratégie : <id>` (cf. _TEMPLATE.md).
    C'est la jointure EXACTE avec le champ `strategy` du ledger — pas un
    matching texte approximatif. None si la ligne manque (hypothèse non
    joignable : signalé comme défaut de format, jamais deviné)."""
    try:
        txt = md_path.read_text("utf-8", errors="ignore")
    except OSError:
        return None
    m = _STRAT_RE.search(txt)
    return m.group(1).strip() if m else None


def hypotheses_en_retard(entrees: list[dict]) -> dict:
    """Rapproche les hypothèses pré-enregistrées du ledger VIVANT.

    Retourne, par hypothèse :
      - strategie      : l'id déclaré (ou None si non joignable)
      - verdicts_vifs  : verdicts vivants trouvés au ledger pour cette stratégie
      - etat           : 'tranchee' (≥1 verdict vivant) | 'jamais' (aucun) |
                         'superseded_only' (des verdicts mais tous superseded) |
                         'non_joignable' (pas de stratégie déclarée)

    Ne fabrique RIEN : si une hypothèse n'a pas de `stratégie :`, elle est
    'non_joignable' — on ne devine pas sa correspondance.
    """
    vifs_par_strat: dict[str, list[str]] = defaultdict(list)
    histo_par_strat: dict[str, list[str]] = defaultdict(list)
    for e in entrees:
        strat = e.get("strategy")
        if not strat:
            continue
        verd = e.get("verdict", "?")
        histo_par_strat[strat].append(verd)
        if not e.get("superseded"):
            vifs_par_strat[strat].append(verd)

    rapport = []
    if HYPOTHESES.is_dir():
        for md in sorted(HYPOTHESES.glob("*.md")):
            if md.stem.startswith("_"):  # gabarit, pas une hypothèse réelle
                continue
            strat = _declarer_strategie(md)
            if not strat:
                rapport.append({"hypothese": md.stem, "strategie": None,
                                "verdicts_vifs": [], "etat": "non_joignable"})
                continue
            vifs = vifs_par_strat.get(strat, [])
            if vifs:
                etat = "tranchee"
            elif histo_par_strat.get(strat):
                etat = "superseded_only"
            else:
                etat = "jamais"
            rapport.append({"hypothese": md.stem, "strategie": strat,
                            "verdicts_vifs": vifs, "etat": etat})

    en_retard = [r for r in rapport
                 if r["etat"] in ("jamais", "superseded_only")]
    return {"rapport": rapport, "en_retard": en_retard,
            "n_en_retard": len(en_retard),
            "n_non_joignable": sum(1 for r in rapport
                                   if r["etat"] == "non_joignable")}


# --- Part de recherche (audit Sonnet 5.5, §R3-5, 2026-10-11) ---
#
# Le rapport demande : « % de PR de la semaine qui exécutent ou
# pré-enregistrent une hypothèse », objectif ≥ 50 %, affiché chaque
# semaine. C'est la métrique qui JUGE le gel de la CI (docs/38, #290) :
# pas « la CI est immobile » mais « la part de recherche remonte ».
#
# Définition mesurable, ÉTROITE, hors ligne (git — pas d'API, pas de token) :
#   - Livraisons : les commits entrés dans main pendant la fenêtre de 7 j.
#     Convention mesurée le 11/10 : 208/208 commits des 7 derniers jours
#     sont des squash-merges `(#NNN)`. On compte TOUTES les livraisons au
#     dénominateur — un push direct (sans PR) ne doit pas gonfler la part
#     en disparaissant du compte.
#   - Recherche : une livraison qui touche au moins un chemin de
#     pré-enregistrement ou d'exécution (listes ci-dessous). ÉTROIT par
#     choix (même leçon que l'oracle `ci(...)` de #290) : un périmètre qui
#     déborde (toute la doc, tout fix) mesurerait le bruit, pas la
#     recherche — et une métrique toujours verte apprend à l'ignorer (F2).
PRE_ENREGISTREMENT = ("research/hypotheses/",)
EXECUTION = ("research/ledger/", "research/runs/", "scripts/studies/")


def _est_registre(chemin: str) -> bool:
    """Les registres machine (`research/registry.yaml`,
    `research/openmarket_registry.yaml`, …) — la vérification du registre
    AVANT de partir fait partie du pré-enregistrement (docs/38 §2)."""
    nom = chemin.rsplit("/", 1)[-1]
    return (chemin.startswith("research/") and "registry" in nom
            and nom.endswith((".yaml", ".yml")))


def est_recherche(chemins: list[str]) -> bool:
    """Une livraison touchant ≥ 1 chemin de recherche est UNE livraison
    de recherche (le reste de son diff n'est pas jugé : on mesure si la
    semaine a porté de la recherche, pas la pureté de chaque PR)."""
    for c in chemins:
        c = c.replace("\\", "/").strip()
        if (c.startswith(PRE_ENREGISTREMENT) or c.startswith(EXECUTION)
                or _est_registre(c)):
            return True
    return False


def part_recherche(livraisons: list[tuple[str, list[str]]]) -> dict:
    """Le % R3-5. ⚠️ Dénominateur vide → pct=None (« — » à l'affichage) :
    ni 0 % ni 100 % — un dénominateur vide qui lirait bon ou mauvais est
    le fail-open classique (on ne sait pas, on le DIT)."""
    total = len(livraisons)
    n = sum(1 for _, fichiers in livraisons if est_recherche(fichiers))
    pct = round(100 * n / total) if total else None
    return {"total": total, "recherche": n, "pct": pct, "objectif": 50}


def _parse_livraisons(texte: str) -> list[tuple[str, list[str]]]:
    """Le format exact de `git log --name-only
    --pretty=format:%x00LIV%x00%s` : une ligne `\0LIV\0<sujet>` ouvre un
    commit, les lignes non vides suivantes sont ses fichiers."""
    livraisons: list[tuple[str, list[str]]] = []
    sujet: str | None = None
    fichiers: list[str] = []
    for ligne in texte.splitlines():
        if ligne.startswith("\x00LIV\x00"):
            if sujet is not None:
                livraisons.append((sujet, fichiers))
            sujet = ligne[len("\x00LIV\x00"):]
            fichiers = []
        elif ligne.strip() and sujet is not None:
            fichiers.append(ligne.strip())
    if sujet is not None:
        livraisons.append((sujet, fichiers))
    return livraisons


def lire_livraisons(fenetre_jours: int = 7) -> list[tuple[str, list[str]]] | None:
    """Les livraisons de la fenêtre, lues depuis git. None si git est
    indisponible — on ne fabrique PAS un score à partir d'un échec de
    mesure (leçon oracle-grep : une sortie vide n'est pas un zéro)."""
    try:
        out = subprocess.run(
            ["git", "log", f"--since={fenetre_jours} days", "--name-only",
             # %x00 est interprété PAR GIT (on passe le texte littéral, pas
             # un octet NUL — exec refuse un argv contenant \x00) ; la sortie
             # contient elle un vrai NUL, que _parse_livraisons lit.
             "--pretty=format:%x00LIV%x00%s"],
            capture_output=True, text=True, cwd=ROOT, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return _parse_livraisons(out.stdout)


def bloc_state(m: dict) -> str:
    """Le bloc à afficher dans STATE.md (hors marqueurs générés).

    COMPACT par contrat (audit 10/10) : `research/STATE.md` a un budget de
    3 Ko (audit_check C4) et c'est le fichier à lire EN PREMIER. La liste
    nominative des échéances vit dans la sortie CLI de ce script ; on n'en
    garde ici qu'un aperçu borné. Sans ce plafond, chaque vague de retard
    repousse le fichier au-delà de sa borne (9 échéances inline = +450 o,
    c'est ce qui a fait passer STATE.md à 3701 o le 10/10).
    """
    cs = m["cette_semaine"]
    s = m["semaine_courante"] or "—"
    lignes = [
        "## Productivité (généré : `python scripts/research_velocity.py`)",
        f"- Semaine **{s}** : **{cs['lots']}** lots · "
        f"**{cs['tranchees']}** tranchées · **{cs['candidats']}** candidats.",
    ]
    # distinction chiffré/muet (garde N6 lab_ledger) : un DISCOVERY_* sans n
    # est une ligne muette (information nulle) — on le dit explicitement.
    if cs.get("lots_muets"):
        lignes.append(
            f"- **Dont {cs['lots_muets']} lot(s) MUET(S)** "
            f"(DISCOVERY_* sans `n` — écrits avant le garde N6 de lab_ledger, "
            f"information nulle : ni distance au seuil ni coût d'équilibre) "
            f"et {cs['lots_chiffres']} chiffré(s). Relancer avec chiffres ou "
            f"marquer `sans_chiffres` ne change pas le verdict.")
    if m["toutes_semaines"]:
        items = list(m["toutes_semaines"].items())
        vues = items[-HISTO_SEMAINES:]
        hist = " | ".join(
            f"{sem} : {r['lots']}·{r['tranchees']}·{r['candidats']} {r['verdicts']}"
            for sem, r in vues)
        reste = len(items) - len(vues)
        suite = f" (+{reste} sem.)" if reste > 0 else ""
        lignes.append(f"- Historique : {hist}{suite}")
    lignes.append(
        "- « Fini » hebdo = ≥ 1 lot journalisé ET ≥ 1 hypothèse tranchée.")
    # échéances : hypothèses pré-enregistrées sans verdict vivant (P5)
    ret = m.get("retard", {})
    if ret:
        # APERÇU BORNÉ : le compte est le signal, la liste est le détail.
        apercu = ", ".join(
            f"`{r['hypothese']}`" for r in ret["en_retard"][:APERCU_ECHEANCES])
        reste = ret["n_en_retard"] - len(ret["en_retard"][:APERCU_ECHEANCES])
        suite = f" (+{reste})" if reste > 0 else ""
        lignes.append(
            f"- **Échéances dépassées : {ret['n_en_retard']}** sans verdict "
            f"vivant (+{ret['n_non_joignable']} non joignables) : "
            f"{apercu}{suite} — détail : `python scripts/research_velocity.py`.")
    # part de recherche (R3-5) : la métrique qui juge le gel de la CI
    part = m.get("part_recherche")
    if part is not None:
        if part["pct"] is None:
            lignes.append(
                "- Part recherche (7 j) : aucune livraison — rien à juger.")
        else:
            lignes.append(
                f"- Part recherche (7 j) : **{part['recherche']}/"
                f"{part['total']}** ({part['pct']} %) — objectif ≥ 50 %.")
    return "\n".join(lignes)


def main() -> int:
    entrees = charger()
    if not entrees:
        print("VELOCITÉ: ledger absent ou vide — aucune productivité mesurable.")
        return 0
    m = metriques(entrees)
    m["retard"] = hypotheses_en_retard(entrees)
    liv = lire_livraisons()
    m["part_recherche"] = part_recherche(liv) if liv is not None else None
    if "--state" in sys.argv:
        print(bloc_state(m))
        return 0
    cs = m["cette_semaine"]
    print(f"VELOCITÉ RECHERCHE — semaine {m['semaine_courante']}")
    print(f"  cette semaine : {cs['lots']} lots · {cs['tranchees']} tranchées · "
          f"{cs['candidats']} candidats")
    # la distinction chiffré/muet (garde N6) : un DISCOVERY_* sans n est muet
    if cs.get("lots_muets"):
        print(f"    dont {cs['lots_muets']} MUET(S) (DISCOVERY_* sans n — "
              f"information nulle, écrits avant le garde N6) et "
              f"{cs['lots_chiffres']} chiffré(s)")
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
    # P5 : les hypothèses pré-enregistrées sans verdict vivant (le retard
    # invisible que la revue a demandé de mesurer)
    ret = m["retard"]
    print(f"\n  ÉCHÉANCES : {ret['n_en_retard']} hypothèse(s) "
          f"pré-enregistrée(s) sans verdict vivant "
          f"(+ {ret['n_non_joignable']} non joignable(s)).")
    for r in ret["rapport"]:
        marque = {"tranchee": "  OK ", "jamais": "  ⏳ ",
                  "superseded_only": "  ⏳ ",
                  "non_joignable": "  ❓ "}.get(r["etat"], "    ")
        detail = (f"{r['verdicts_vifs']}" if r['verdicts_vifs']
                  else r["etat"])
        print(f"    {marque} {r['hypothese']:35} -> {detail}")
    if ret["n_en_retard"] > 0:
        print("    (⏳ = en retard : pré-enregistrée, jamais tranchée ou "
              "verdict superseded · ❓ = sans `stratégie :`, non joignable)")
    # R3-5 : la part de recherche — la métrique qui juge le gel de la CI
    part = m["part_recherche"]
    print("")
    if part is None:
        print("  PART DE RECHERCHE : non mesurable (git indisponible) — "
              "aucun score affiché.")
    elif part["pct"] is None:
        print("  PART DE RECHERCHE (7 j) : aucune livraison — rien à juger.")
    else:
        print(f"  PART DE RECHERCHE (7 j) : {part['recherche']}/"
              f"{part['total']} livraisons = {part['pct']} % "
              f"(objectif ≥ {part['objectif']} %)")
        if part["pct"] < part["objectif"]:
            print("    ⚠️ sous l'objectif — la semaine a porté la porte "
                  "(CI/fix/docs) plus que la recherche. Le gel de la CI "
                  "existe pour ça (docs/38).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
