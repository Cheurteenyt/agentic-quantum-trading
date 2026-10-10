#!/usr/bin/env python3
"""N6 — le LEDGER doit porter la TAILLE D'ÉCHANTILLON de chaque verdict
vivant (audit 2026-10-10, suite de l'oracle de provenance).

## Le trou que ce module ferme

`lab_ledger.py` juge le seuil de preuve (Bonferroni, N de multiplicité) et
`STATE.md` affiche « PASS 21 · FAIL 29 ... ». Or la règle fondatrice du
dépôt est **N ≥ 10** pour qu'un verdict compte (cf. README « Pre-registered
rules »). Mesure au HEAD : **0 des 16 entrées vivantes portent un `n`** —
ni au top-level, ni dans `params`. Le N de multiplicité compte des LIGNES,
pas des observations.

Un verdict « SOUS_PUISSANT » existe dans le vocabulaire, donc le dépôt
SAIT que la puissance compte — mais rien ne la porte là où le verdict est
énoncé. Un agent qui lit le ledger croit voir des mesures ; il voit des
affirmations.

## Pourquoi lire le run, pas recopier le n

Le `n` vit dans `summary_{confirmation,discovery}.json` du run pointé par
`ref` (mesuré : EXP-crash-short-6h-004 porte n=8678 dans son summary, rien
dans le ledger). Le recopier à la main dans le ledger créerait une SECONDE
source de vérité qui divergera au prochain run — exactement le défaut que
l'oracle de provenance combat. On lit donc le run, et on exige que le
run existe et porte son n.

Le verdict retenu est celui du DERNIER attempt (même règle que
`ledger_provenance.resolve_runs`) : un run re-mesuré porte son n à jour.

## Le fail-closed

Une entrée vivante dont le n est INTROUVABLE (run absent, summary absent,
ou n non numérique) est un défaut — pas un « 0 » silencieux. Un verdict
énoncé sans taille d'échantillon ne peut pas être cru, et le ledger est
précisément l'endroit où on ne doit pas avoir à faire confiance.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_ledger import load  # noqa: E402

# Le seuil de puissance du dépôt (README, « Pre-registered rules »). Un
# verdict vivant dont le n est SOUS ce seuil est signalé : il ne doit pas
# pouvoir être cité comme preuve sans que ça se voie.
MIN_N = 10


def _run_dir(ref: str | None, runs_dir: Path) -> Path | None:
    """Le `ref` du ledger est un chemin (absolu ou relatif) vers un fichier
    du run. On en dérive le RÉPERTOIRE DU RUN, pas le parent du fichier :
    les réf normaux sont `.../runs/EXP-xxx/report.md` (parent = EXP-xxx),
    mais les runs manuels pointent `reports/x.md` ou `scripts/.../y.py`
    (parent = reports/, scripts/). On remonte donc les parents jusqu'à
    trouver un dossier présent dans `runs_dir`, sinon None."""
    if not ref:
        return None
    p = Path(ref)
    # candidats : le parent, puis les parents proches (un run peut être
    # .../runs/EXP-x/report.md -> EXP-x, ou .../EXP-x/attempts/001/... )
    for anc in [p.parent, *p.parent.parents]:
        if not anc.name:
            break
        cand = runs_dir / anc.name
        if cand.exists():
            return cand
    return None


def _dernier_attempt(run_dir: Path) -> Path | None:
    """Le summary du DERNIER attempt (numéro le plus grand), ou le summary
    à la racine du run si le run n'a pas de sous-attempts. Même règle de
    résolution que l'oracle de provenance : le dernier fait foi."""
    atts = sorted(
        (p for p in (run_dir / "attempts").glob("*") if p.is_dir()),
        key=lambda p: p.name)
    cible = atts[-1] if atts else run_dir
    for kind in ("confirmation", "discovery"):
        f = cible / f"summary_{kind}.json"
        if f.exists():
            return f
    # pas de summary dans le dernier attempt : on tolère le run racine
    for kind in ("confirmation", "discovery"):
        f = run_dir / f"summary_{kind}.json"
        if f.exists():
            return f
    return None


def _lire_n(summary: Path) -> tuple[int | None, str]:
    """Retourne (n, détail). n=None = introuvable/invalide."""
    try:
        d = json.loads(summary.read_text("utf-8"))
    except (json.JSONDecodeError, OSError) as ex:
        return None, f"summary illisible ({type(ex).__name__})"
    for cle in ("n", "n_trades", "count", "n_obs"):
        if cle in d:
            v = d[cle]
            if isinstance(v, bool):        # bool est un int en python : exclure
                continue
            if isinstance(v, int):
                return v, f"{cle}={v}"
            if isinstance(v, (float, str)):
                try:
                    return int(float(v)), f"{cle}={v}"
                except (TypeError, ValueError):
                    continue
    return None, "aucune clé n/n_trades/count dans le summary"


def audit(ledger: Path | None = None,
          runs_dir: Path | None = None) -> list[dict]:
    """Retourne les PROBLÈMES. Vide = chaque verdict vivant porte son n.

    Deux familles :
      NO_RUN      le run pointé par ref n'existe pas (n introuvable)
      NO_N        le run existe mais son summary ne porte pas de n numérique
      SOUS_PUISSANT  n trouvé mais < MIN_N (le verdict ne peut pas être
                     tenu comme preuve au seuil du dépôt)
    """
    ledger = Path(ledger or ROOT / "research" / "ledger" / "trials.jsonl")
    runs_dir = Path(runs_dir or ROOT / "research" / "runs")
    out: list[dict] = []
    if not ledger.exists():
        return out

    try:
        entrees = load(ledger, None)
    except ValueError as exc:
        return [{"kind": "MALFORMED", "line": 0,
                 "detail": f"ledger illisible : {exc}"}]

    for pos, e in enumerate(entrees, 1):
        # On ne juge que les entrées VIVANTES : une ligne `superseded` est
        # déjà hors preuve (PR#253), la juger ici rendrait l'oracle rouge
        # en permanence sur du travail clos.
        if e.get("superseded"):
            continue
        verdict = e.get("verdict", "")
        i = e.get("_line", pos)
        ref_str = f"L{i} {e.get('date')} {verdict} {e.get('family')}/{e.get('strategy')}"

        # DÉROGATION EXPLICITE (pattern `# deep-audit:ignore`) : un champ
        # `n_degression` dispense du contrôle MAIS reste visible — le défaut
        # est documenté dans le ledger, pas masqué. Mesuré : L97
        # (gate-direction-wallet) a un n irrécupérable sans relancer le
        # script ; son verdict est un DISCOVERY_FAIL (échec), donc il
        # n'affirme aucune réussite non corroborée.
        if e.get("n_degression"):
            continue

        # Un PREREG n'a pas encore de mesure : ce n'est pas un défaut de
        # puissance, c'est une intention. On le laisse.
        if verdict == "PREREG":
            continue

        run_dir = _run_dir(e.get("ref"), runs_dir)
        if run_dir is None:
            out.append({"kind": "NO_RUN", "line": i, "ref": ref_str,
                        "detail": "run introuvable depuis ref — "
                                  "le n ne peut pas être lu"})
            continue

        summary = _dernier_attempt(run_dir)
        if summary is None:
            out.append({"kind": "NO_N", "line": i, "ref": ref_str,
                        "detail": f"{run_dir.name} : aucun summary "
                                  "confirmation/discovery"})
            continue

        n, detail = _lire_n(summary)
        if n is None:
            out.append({"kind": "NO_N", "line": i, "ref": ref_str,
                        "detail": f"{run_dir.name} : {detail}"})
        elif n < MIN_N:
            out.append({"kind": "SOUS_PUISSANT", "line": i, "ref": ref_str,
                        "detail": f"{run_dir.name} : {detail} < {MIN_N} "
                                  "(verdict non tenable comme preuve)"})
    return out


def main() -> int:
    pb = audit()
    if not pb:
        print("LEDGER PUISSANCE: PASS — chaque verdict vivant porte un "
              f"n >= {MIN_N} lisible dans son run")
        return 0
    par: dict = {}
    for p in pb:
        par.setdefault(p["kind"], []).append(p)
    print(f"LEDGER PUISSANCE: {len(pb)} PROBLEME(S)")
    for genre, items in sorted(par.items()):
        print(f"\n  {genre} : {len(items)}")
        for it in items[:8]:
            print(f"    {it.get('ref', 'L'+str(it['line']))} — {it['detail']}")
        if len(items) > 8:
            print(f"    ... et {len(items) - 8} autres")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
