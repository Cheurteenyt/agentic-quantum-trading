#!/usr/bin/env python3
"""N5 — le LEDGER ne doit pas pouvoir diverger de ses RUNS (audit
2026-10-08, §4 du plan).

## Le trou que ce module ferme

`research_integrity.py` vérifie les run dirs entre eux, et ne lit le
ledger que pour la correspondance CONFIRMED ↔ run. **Rien** ne vérifie
que le VERDICT du ledger est encore celui du run qu'il décrit.

Résultat mesuré au HEAD de ce fichier : **23 des 23 lignes
`DISCOVERY_PASS` du ledger sont périmées.** PR-143 a re-mesuré chaque
candidat et les a tous retournés en `DISCOVERY_FAIL` ; les run dirs
 disent la vérité, le ledger continue d'annoncer des candidats morts.

Et `EXP-bonsai-h-01` porte un `PASS` au ledger alors que son propre
`summary_confirmation.json` dit `REJECTED`.

Le ledger est donc, à ce jour, la SEULE source du dépôt qui affirme une
chose que le moteur a depuis infirmée. C'est exactement la classe
de défaut que le projet combat : un artefact périmé qui continue de
circuler parce que personne ne le confronte à sa source.

## Pourquoi un oracle et pas un patch

Patcher 23 lignes aujourd'hui corrige le symptôme. Ça ne corrige pas la
raison : demain un run sera re-mesuré, et le ledger divergera de nouveau,
en silence. Ce module rend la divergence **détectable**, et un test
garantit que le ledger de ce dépôt reste propre.

## La preuve de code : le DERNIER attempt

Le run le plus instructive est `EXP-crash-short-6h-004` :

    attempt 17:12  git c2fadaf      DISCOVERY_PASS   CONFIRMED
    attempt 20:56  git ea993a80    DISCOVERY_PASS   CONFIRMED
    attempt 21:59  git b7f5a28      DISCOVERY_FAIL   CONFIRMED   <- PR-143

Le verdict qui fait foi est celui du **DERNIER** attempt. Utiliser « un
attempt est antérieur au fix » compterait les runs correctement
re-mesurés comme périmés — c'est l'erreur inverse, et elle est plus
grave : elle effacerait 56 verdicts valides.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.lab_ledger import load  # noqa: E402

# Le commit qui corrige le look-ahead temporel (PR-143). Un verdict
# mesuré par un commit STRICTEMENT antérieur est entaché ; un verdict
# mesuré PAR ce commit est post-correctif et valide.
PR143 = "b7f5a28a52b270c68f51154fea8f15f79373bbf0"

# Le vocabulaire du ledger et celui des runs ne sont pas les mêmes.
# Traduire explicitement vaut mieux que deviner.
CONFIRMATION = {"PASS": "CONFIRMED", "FAIL": "REJECTED"}
DISCOVERY = {"DISCOVERY_PASS": "DISCOVERY_PASS",
             "DISCOVERY_FAIL": "DISCOVERY_FAIL"}

# Le look-ahead de PR-143 GONFLAIT les mesures : avant le fix, du bruit
#pur battaient le seuil de confirmation. Le commit lui-meme le dit
# ("tous les resultats precedents sont invalides et re-mesures"), et le
# HEAD le confirme : DISCOVERY_PASS -> DISCOVERY_FAIL sur tous les
# candidats.
#
# Le biais est donc a SENS UNIQUE, et c'est ce qui rend la revision
# justifiable : un FAIL mesure par le code bugge reste valable (le bug ne
# pouvait que le renforcer), seul un PASS est douteux. Inverser ce
# raisonnement — disqualifier aussi les FAIL — effacerait 27 verdicts
# corrects pour rien.
BIAS_UNIDIRECTIONNEL = True


def _sha_fn():
    sys.path.insert(0, str(ROOT))
    from scripts.lab_ledger import norm_text, sha
    return sha, norm_text


def _resolve_git(short: str) -> str | None:
    """Résout un sha court en sha complet, ou None si absent du dépôt."""
    if not short or len(short) < 7:
        return None
    try:
        return subprocess.run(
            ["git", "rev-parse", "--verify", short + "^{commit}"],
            capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def code_est_prefix(git_sha: str, fix: str = PR143) -> bool | None:
    """True = le code tournait AVANT le correctif de causalité.

    `None` = indéterminable (commit absent du dépôt, clone superficiel).
    L'indéterminable ne vaut PAS « pré-fix » : on ne disqualifie pas un
    verdict sur une absence d'information.
    """
    full = _resolve_git(git_sha)
    if full is None:
        return None
    fix_full = _resolve_git(fix)
    if fix_full is None:
        return None
    if full == fix_full:
        return False                      # c'est le fix lui-même
    rc = subprocess.run(["git", "merge-base", "--is-ancestor", full, fix_full],
                        capture_output=True).returncode
    if rc == 0:
        return True                       # antérieur au fix
    return False                          # postérieur


def resolve_runs(runs_dir: Path | None = None) -> dict:
    """hypothesis_hash → le verdict du DERNIER attempt de chaque run.

    Deux dispositions coexistent sur disque : `attempts/N/` (la plupart)
    et un run à la racine (EXP-bonsai-h-01). Ne lire qu'un des deux a
    déjà fait manquer un run dans cet audit — donc les deux.
    """
    runs_dir = Path(runs_dir or ROOT / "research" / "runs")
    sha, norm_text = _sha_fn()
    best: dict = {}
    if not runs_dir.exists():
        return best

    dispositions = []
    for m in runs_dir.glob("*/attempts/*/manifest.json"):
        n = int(m.parent.name)
        dispositions.append((n, m.parent))
    for m in runs_dir.glob("*/manifest.json"):
        dispositions.append((0, m.parent))

    for n, d in dispositions:
        sp, mf = d / "spec.json", d / "manifest.json"
        if not (sp.exists() and mf.exists()):
            continue
        try:
            spec = json.loads(sp.read_text("utf-8"))
            man = json.loads(mf.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        hh = sha(norm_text(spec.get("hypothesis", "")))
        cur = best.get(hh)
        if cur is None or n > cur["attempt"]:
            best[hh] = {"attempt": n, "dir": d, "manifest": man,
                        "run_id": spec.get("id") or d.parent.name}
    return best


def _verdicts(run: dict) -> dict:
    """Lit les verdicts `summary_{confirmation,discovery}.json` d'un run.

    G5 (deep-audit) : un `except` muet est un fail-open — si un summary est
    illisible, l'oracle lirait « pas de verdict » et laisserait passer le
    ledger comme honnête. On ne peut pas DEVINER le verdict d'un fichier
    corrompu, mais on peut ne pas le taire : la clé `_unreadable` fait
    remonter le problème à `audit()` qui le signale (kind `UNREADABLE`)
    au lieu de le masquer.
    """
    out: dict = {}
    for kind in ("confirmation", "discovery"):
        f = run["dir"] / f"summary_{kind}.json"
        if f.exists():
            try:
                out[kind] = json.loads(f.read_text("utf-8")).get("verdict")
            except (json.JSONDecodeError, OSError) as ex:
                # La trace est le correctif du fail-open : le run existe,
                # son verdict est INCONNU, et ça doit être vu.
                out.setdefault("_unreadable", []).append(
                    f"{kind}:{f.name}: {type(ex).__name__}")
    return out


def audit(ledger: Path | None = None, runs_dir: Path | None = None,
          fix: str = PR143) -> list[dict]:
    """Retourne la liste des PROBLÈMES. Vide = le ledger est honnête.

    Six familles :

      STALE         le verdict du ledger ≠ le verdict COURANT du run
      PREFIX        le verdict repose sur du code antérieur au fix
      UNATTRIBUTED  un verdict positif qu'aucun run ne corrobore
      SUPERSEDED_ACTIVE  une ligne marquée superseded qui compte encore
      NO_RUN        un PASS sans aucun run derrière (fail-closed)
      UNREADABLE    un summary illisible — verdict INCERTAIN, pas « absent »
                    (le correctif du fail-open G5 : on ne devine pas, on dit)
    """
    ledger = Path(ledger or ROOT / "research" / "ledger" / "trials.jsonl")
    runs = resolve_runs(runs_dir)
    out: list[dict] = []
    if not ledger.exists():
        return out

    # On passe par `lab_ledger.load()` et non par un json.loads() nu : cet
    # oracle doit juger la MÊME normalisation que le reste du dépôt, sinon
    # « est-ce que ce verdict compte ? » aurait deux réponses selon qui
    # demande — et la plus flatteuse gagnerait.
    #
    # N5-merge : PR#253 implémente la marque `superseded` en ACCÈS INLINE
    # (`e.get("superseded")`) et ne normalise NI la ligne physique NI un
    # booléen « compte comme positif ». Cet oracle en a besoin (la ligne
    # physique est ce qu'un humain cite pour contester un verdict), donc
    # on les DÉRIVE ici, sur le modèle inline de #253 — sans réintroduire
    # les champs normalisés que #253 a choisi de ne pas avoir.
    try:
        entrees = load(ledger, None)
    except ValueError as exc:
        return [{"kind": "MALFORMED", "line": 0,
                 "detail": f"ledger illisible : {exc}"}]

    def _counts_positive(e: dict) -> bool:
        """Un verdict marqué `superseded` ne compte PLUS comme positif
        (PR#253 : le N, le statut et le budget l'excluent). C'est la MÊME
        règle que `confirmation_multiplicity()` — on la reflète ici pour
        qu'une marque qui laisserait encore compter un positif soit
        détectée (SUPERSEDED_ACTIVE)."""
        return (e.get("verdict") in ("PASS", "DISCOVERY_PASS")
                and not e.get("superseded"))

    for pos, e in enumerate(entrees, 1):
        verdict = e.get("verdict", "")
        hh = e.get("hypothesis_hash")
        # `load()` numérote les lignes physiques mais n'expose pas le n° sur
        # l'entrée (PR#253 l'a fait disparaître). On le re-dérive ici par
        # position : `entrees` ne contient QUE les lignes non vides, dans
        # l'ordre, donc la position dans la liste est le n° de ligne utile
        # pour un humain qui va contester le verdict (cf. `sed -n 'Ni p'`).
        i = e.get("_line", pos)
        ref = f"L{i} {e.get('date')} {verdict} {e.get('family')}/{e.get('strategy')}"

        sup = e.get("superseded")

        if hh not in runs:
            # Sans run, rien ne corrobore le verdict. Un verdict
            # NEGATIF sans run est un constat de non-reussite : il ne
            # revendique rien, donc il ne peut rien surestimer. Un
            # verdict POSITIF sans run, lui, affirme une reussite que
            # personne ne peut corroborer — c'est ça qu'on signale.
            #
            # Une ligne DÉJÀ marquée n'est plus signalée : c'est le
            # travail de la marque, pas de l'oracle. Le signaler aussi
            # rendrait l'oracle rouge en permanence.
            if verdict in ("PASS", "DISCOVERY_PASS") and not sup:
                out.append({"kind": "UNATTRIBUTED", "line": i, "ref": ref,
                            "detail": "verdict positif sans run : "
                                      "personne ne peut le corroborer"})
            continue

        run = runs[hh]
        v = _verdicts(run)
        attendu = CONFIRMATION.get(verdict) or DISCOVERY.get(verdict)
        reel = v.get("confirmation" if verdict in CONFIRMATION else "discovery")
        rid = run["run_id"]

        # Un summary illisible = un verdict INCONNU. Ne pas le dire
        # laisserait le ledger paraître honnête par défaut (fail-open) :
        # c'est le même défaut que le `except` muet de `_verdicts`,
        # remonté ici au lieu d'être avalé une seconde fois.
        if v.get("_unreadable"):
            out.append({"kind": "UNREADABLE", "line": i, "ref": ref,
                        "detail": f"{rid} : summary illisible — "
                                  + "; ".join(v["_unreadable"])
                                  + " — verdict incertain"})
            continue

        # Une ligne DÉJÀ marquée ne peut plus être « stale » ni
        # « pré-fix » : la marque EST la réponse. La signaler encore
        # produirait un rapport rouge en permanence, donc un rapport
        # qu'on finit par ignorer.
        if not sup:
            if attendu and reel and attendu != reel:
                out.append({
                    "kind": "STALE", "line": i, "ref": ref,
                    "detail": f"ledger={verdict} mais {rid} dit {reel}"})
            pre = code_est_prefix(run["manifest"].get("git_sha", ""), fix)
            if pre is True and verdict in ("PASS", "DISCOVERY_PASS"):
                out.append({
                    "kind": "PREFIX", "line": i, "ref": ref,
                    "detail": f"{rid} mesure par "
                              f"{str(run['manifest'].get('git_sha'))[:7]}, "
                              f"anterieur au correctif de causalite"})

        # En revanche, une marque qui laisse ENCORE compter un verdict
        # positif est un défaut : l'exclusion promise n'est pas appliquée.
        # On interroge `_counts_positive(e)` — la MÊME règle d'exclusion
        # que `confirmation_multiplicity()` de PR#253 — plutôt que le
        # verdict brut. Marquer sans exclure laisserait ce booléen à
        # True et cet oracle le verrait.
        if sup and _counts_positive(e):
            out.append({
                "kind": "SUPERSEDED_ACTIVE", "line": i, "ref": ref,
                "detail": f"superseded={sup} mais le verdict compte encore"})
    return out


def main() -> int:
    pb = audit()
    if not pb:
        print("LEDGER PROVENANCE: PASS — chaque verdict est corrobore par "
              "son run, par du code post-correctif")
        return 0
    par_genre: dict = {}
    for p in pb:
        par_genre.setdefault(p["kind"], []).append(p)
    print(f"LEDGER PROVENANCE: {len(pb)} PROBLEME(S)")
    for genre, items in sorted(par_genre.items()):
        print(f"\n  {genre} : {len(items)}")
        for it in items[:6]:
            print(f"    {it.get('ref', 'L' + str(it['line']))} — {it['detail']}")
        if len(items) > 6:
            print(f"    ... et {len(items) - 6} autres")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())