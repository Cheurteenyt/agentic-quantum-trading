#!/usr/bin/env python3
"""Controle de configuration du miroir GitHub -> GitLab.

## Pourquoi ce fichier existe

La mise en place du miroir demande cinq valeurs dans un environnement
GitHub, une deploy key GitLab, et un sha figé. Ce sont des gestes manuels
qui touchent a des identifiants, et le runbook d'Ariad documente huit
erreurs de configuration qui se sont REELLEMENT produites pendant son
amorcage. La plus vicieuse : une deploy key en ecriture qui n'est pas
autorisee sur `main` protege. Elle est correcte partout ailleurs, et le
miroir echoue au push avec un message qui parle de branches protegees, pas
de configuration.

Le principe de ce contrôle : **rendre deterministe une question qui, sinon,
se repond en lancant un miroir et en lisant un log rouge.** Une
configuration mal faite doit se voir AVANT le premier push, pas pendant.

## Ce qui est verifie automatiquement

  1. L'environnement GitHub existe et est restreint a `main`.
  2. Le secret de cle privee est present.
  3. Les quatre variables sont presentes et non vides.
  4. `GITLAB_REPOSITORY_SSH_URL` est EXACTEMENT celle du workflow.
     Ariad rejette une URL vers un autre projet du meme hote ; ce
     contrôle verifie la meme egalite, mais cote configuration, pour
     que l'ecart se voie ici et non dans un refus du workflow.
  5. `GITLAB_KNOWN_HOSTS` epingle bien une cle ed25519 de gitlab.com,
     et l'empreinte CALCULEE correspond a la variable d'empreinte.
     Comparer deux variables entre elles ne prouverait rien : si les
     deux ont ete remplies de travers, elles se confirment mutuellement.
     Ici on recalcule depuis la cle publique.
  6. La deploy key n'est PAS celle d'Ariad. Une deploy key est
     « project-scoped » : la reutiliser sur un second projet elargit sa
     portee sans que personne ne l'ait decide.
  7. Le pin `TRUSTED_VERIFIER_SHA` est un sha de 40 caracteres, non nul.
  8. `.gitlab-ci.yml` desactive bien toute CI GitLab.

## Ce qui NE peut PAS etre verifie ici

L'autorisation de la deploy key sur `main` protege vit chez GitLab et
demande un token d'API GitLab. Tant qu'il n'est pas fourni, ce point est
rapporte comme « a verifier a la main » — jamais comme « OK ». Un
contrôle qui se declare vert sans avoir regarde est pire que pas de
contrôle : il donne une confiance qu'il n'a pas gagnee.

    python scripts/ci/check_mirror_setup.py            # tout
    python scripts/ci/check_mirror_setup.py --hors-ligne  # sans API
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "mirror-main-to-gitlab.yml"
GITLAB_CI = ROOT / ".gitlab-ci.yml"

ENVIRONNEMENT = "gitlab-passive-mirror"

# L'empreinte de la cle HOTE ed25519 de GitLab.com. Publique : n'importe
# qui la relit en se connectant a gitlab.com:22. Elle est fige ici parce
# que le runbook d'Ariad la documente, et parce qu'une rotation de cle
# hote DOIT se voir dans un diff.
EMPREINTE_HOTE_GITLAB = "SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8"

# La deploy key d'Ariad. Elle est project-scoped : la reutiliser ici
# donnerait a un run de ce depot un droit d'ecriture sur codebase-memory-V2.
EMPREINTES_CLIENT_INTERDITES = {
    "SHA256:p45GIFj/WYp6QAab9FgwbC0cgGv4EHPj94I8PKQBO5M": "deploy key du miroir Ariad",
}

SHA40 = re.compile(r"^[0-9a-f]{40}$")
EMPREINTE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


class Injoignable(RuntimeError):
    """L'API GitHub n'a pas pu etre interroge."""


# ─────────────────────────────────────────────────────────────────────
# Resultats
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Constat:
    nom: str
    # True = verifie conforme, False = verifie NON conforme,
    # None = pas pu verifier ici (jamais un succes par defaut).
    ok: bool | None
    detail: str

    @property
    def symbole(self) -> str:
        return {True: "OK  ", False: "ECHEC", None: "MANUEL"}[self.ok]


# ─────────────────────────────────────────────────────────────────────
# Lecture des constantes — une seule source de verite
# ─────────────────────────────────────────────────────────────────────

def lire_constantes(texte: str) -> dict[str, str | None]:
    """Extrait du workflow les valeurs auxquelles la config doit obeir.

    On les LIT dans le workflow au lieu de les recopier ici. Recopier
    creerait deux sources qui deriveraient en silence : le contrôle
    validerait alors une configuration pendant que le workflow en
    attendrait une autre.
    """
    url = re.search(r'EXPECTED_GITLAB_URL="([^"]+)"', texte)
    pin = re.search(
        r'^\s+TRUSTED_VERIFIER_SHA:\s*"([0-9a-f]{40})"\s*$', texte, re.M)
    return {
        "url": url.group(1) if url else None,
        "pin": pin.group(1) if pin else None,
    }


# ─────────────────────────────────────────────────────────────────────
# Empreintes OpenSSH
# ─────────────────────────────────────────────────────────────────────

def empreinte_blob(cle_b64: str) -> str:
    """L'empreinte OpenSSH d'une cle : SHA256 du blob binaire, base64 sans `=`.

    C'est la definition d'OpenSSH. La recalculer depuis la cle plutot que
    de comparer deux variables entre elles est ce qui rend le contrôle
    utile : deux variables fausses de la meme facon se confirmeraient.
    """
    blob = base64.b64decode(cle_b64, validate=True)
    return "SHA256:" + base64.b64encode(
        hashlib.sha256(blob).digest()).decode().rstrip("=")


def cles_du_known_hosts(texte: str, hote: str = "gitlab.com") -> list[str]:
    """Les cles publiques ed25519 epinglees pour `hote`.

    Accepte `gitlab.com`, `[gitlab.com]:22`, et les prefixes de marqueur.
    Les lignes commentees et les autres algorithmes sont ignores : le
    runtime force ed25519, donc epingler un rsa ne protegerait pas
    l'echange qui a reellement lieu.
    """
    cles = []
    for ligne in texte.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        champs = ligne.split()
        if champs and champs[0].startswith("@"):
            champs = champs[1:]
        if len(champs) < 3:
            continue
        hotes, type_cle = champs[0], champs[1]
        cibles = {hote, f"[{hote}]:22", f"[{hote}]:{22}"}
        if not (set(hotes.split(",")) & cibles):
            continue
        if type_cle != "ssh-ed25519":
            continue
        cles.append(champs[2])
    return cles


# ─────────────────────────────────────────────────────────────────────
# Les contrôles (fonctions pures : testables sans reseau)
# ─────────────────────────────────────────────────────────────────────

def controle_pin(pin: str | None) -> Constat:
    """Le pin doit etre un sha plein, et surtout PAS celui de l'amorcage."""
    if pin is None:
        return Constat("pin de confiance", False,
                       "TRUSTED_VERIFIER_SHA introuvable dans le workflow")
    if pin == "0" * 40:
        return Constat(
            "pin de confiance", False,
            "TRUSTED_VERIFIER_SHA vaut encore l'amorcage (40 zeros). Le "
            "miroir echouera a l'etape 1. Le remplacer par le sha du "
            "commit qui a introduit scripts/ci/ sur main")
    if not SHA40.match(pin):
        return Constat("pin de confiance", False,
                       f"TRUSTED_VERIFIER_SHA n'est pas un sha de 40 "
                       f"caracteres hexadecimaux : {pin!r}")
    return Constat("pin de confiance", True, f"{pin[:12]}… (bien forme)")


def controle_url(url_workflow: str | None,
                 url_variable: str | None) -> Constat:
    """L'URL configuree doit etre EXACTEMENT celle que le workflow accepte."""
    if url_workflow is None:
        return Constat("URL GitLab", False,
                       "EXPECTED_GITLAB_URL introuvable dans le workflow")
    if not url_variable:
        return Constat("URL GitLab", False,
                       "GITLAB_REPOSITORY_SSH_URL est absente ou vide")
    if url_variable.strip() != url_workflow:
        return Constat(
            "URL GitLab", False,
            f"la variable ne correspond pas au workflow.\n"
            f"      workflow : {url_workflow}\n"
            f"      variable : {url_variable.strip()}\n"
            f"      L'egalite est stricte : le workflow refuse tout ce qui "
            f"n'est pas exactement sa constante")
    return Constat("URL GitLab", True, url_workflow)


def controle_empreinte_hote(known_hosts: str | None,
                            empreinte_var: str | None) -> Constat:
    """L'empreinte doit etre RECALCULEE depuis la cle epinglee."""
    if not known_hosts:
        return Constat("cle hote GitLab.com", False,
                       "GITLAB_KNOWN_HOSTS est absente ou vide")
    cles = cles_du_known_hosts(known_hosts)
    if not cles:
        return Constat(
            "cle hote GitLab.com", False,
            "GITLAB_KNOWN_HOSTS ne contient aucune cle ed25519 pour "
            "gitlab.com. Le runtime force ed25519 : une cle rsa epinglee "
            "ne protegerait pas l'echange reel")
    if not empreinte_var:
        return Constat("cle hote GitLab.com", False,
                       "GITLAB_ED25519_HOST_FINGERPRINT est absente ou vide")
    calculees = []
    for cle in cles:
        try:
            calculees.append(empreinte_blob(cle))
        except Exception as exc:  # cle tronquee ou non base64
            return Constat("cle hote GitLab.com", False,
                           f"cle ed25519 illisible : {exc}")
    if empreinte_var.strip() not in calculees:
        return Constat(
            "cle hote GitLab.com", False,
            f"l'empreinte annoncee ne correspond a AUCUNE cle epinglee.\n"
            f"      annoncee  : {empreinte_var.strip()}\n"
            f"      recalculee: {', '.join(calculees)}\n"
            f"      L'annoncee et l'epinglee viennent de deux endroits : "
            f"c'est precisement pour cela qu'on recalcule")
    return Constat("cle hote GitLab.com", True,
                   f"{empreinte_var.strip()} (recalculee depuis la cle)")


def controle_empreinte_client(empreinte_var: str | None) -> Constat:
    """L'empreinte de la deploy key doit etre bien formee et NON reutilisee."""
    if not empreinte_var:
        return Constat("deploy key GitLab", False,
                       "GITLAB_MIRROR_KEY_FINGERPRINT est absente ou vide")
    fp = empreinte_var.strip()
    if fp in EMPREINTES_CLIENT_INTERDITES:
        return Constat(
            "deploy key GitLab", False,
            f"c'est la {EMPREINTES_CLIENT_INTERDITES[fp]}.\n"
            f"      Une deploy key est « project-scoped ». La reutiliser "
            f"donnerait a ce depot un droit d'ECRITURE sur le projet "
            f"d'Ariad. Generer une paire dediee")
    if not EMPREINTE.match(fp):
        return Constat(
            "deploy key GitLab", False,
            f"empreinte mal formee : {fp!r}. Attendu SHA256: suivi de 43 "
            f"caracteres base64. Relever avec `ssh-keygen -lf <cle>.pub`")
    return Constat("deploy key GitLab", True, fp)


def controle_secret(secrets: list[dict]) -> Constat:
    noms = {s.get("name") for s in secrets}
    if "GITLAB_MIRROR_SSH_PRIVATE_KEY" not in noms:
        return Constat(
            "secret de cle privee", False,
            "GITLAB_MIRROR_SSH_PRIVATE_KEY est absent de l'environnement. "
            "Le workflow echoue avant tout push")
    return Constat("secret de cle privee", True,
                   "GITLAB_MIRROR_SSH_PRIVATE_KEY present "
                   "(valeur illisible via l'API — normal)")


def controle_variables(variables: list[dict]) -> list[Constat]:
    attendues = (
        "GITLAB_REPOSITORY_SSH_URL", "GITLAB_KNOWN_HOSTS",
        "GITLAB_MIRROR_KEY_FINGERPRINT", "GITLAB_ED25519_HOST_FINGERPRINT",
    )
    par_nom = {v.get("name"): (v.get("value") or "") for v in variables}
    constats = []
    for nom in attendues:
        if nom not in par_nom:
            constats.append(Constat(f"variable {nom}", False,
                                    "absente de l'environnement"))
        elif not par_nom[nom].strip():
            constats.append(Constat(f"variable {nom}", False, "presente mais VIDE"))
    if not constats:
        constats.append(Constat("variables requises", True,
                                f"{len(attendues)}/{len(attendues)} presentes "
                                f"et non vides"))
    return constats


def controle_gitlab_ci(texte: str | None) -> Constat:
    """La CI GitLab doit rester desactivee.

    C'est la cause de l'incident d'origine d'Ariad : la CI GitLab
    consommait le quota de runners partages au point de bloquer les
    depots voisins. Le fichier doit refuser de tourner.
    """
    if texte is None:
        return Constat("CI GitLab desactivee", False,
                       ".gitlab-ci.yml est absent. Sans lui, GitLab peut "
                       "declencher ses propres pipelines par defaut")
    if "when: never" not in texte:
        return Constat("CI GitLab desactivee", False,
                       ".gitlab-ci.yml ne contient pas de regle "
                       "`when: never` : un pipeline GitLab pourrait partir "
                       "a chaque push miroir")
    return Constat("CI GitLab desactivee", True,
                   "regle `when: never` presente")


def controle_permissions() -> Constat:
    """L'autorisation deploy key sur `main` protege — non verifiable ici."""
    return Constat(
        "deploy key autorisee sur main", None,
        "a verifier dans GitLab : la deploy key doit avoir le droit "
        "d'ECRITURE **et** etre autorisee a pousser sur la branche "
        "protegee `main` (GitLab : « Allowed to push and merge »). "
        "L'oublier produit un refus pre-receive au premier push")


# ─────────────────────────────────────────────────────────────────────
# Acces a l'API GitHub
# ─────────────────────────────────────────────────────────────────────

def _token() -> str | None:
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True,
                           text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _get(chemin: str, token: str) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com{chemin}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "aqt-check-mirror-setup",
        })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise Injoignable(f"HTTP {exc.code} sur {chemin} : {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise Injoignable(f"{chemin} : {exc}") from exc


def depot() -> str:
    try:
        r = subprocess.run(["git", "remote", "get-url", "origin"],
                           cwd=ROOT, capture_output=True, text=True,
                           timeout=20)
        m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", r.stdout.strip())
        if m:
            return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return "Cheurteenyt/agentic-quantum-trading"


# ─────────────────────────────────────────────────────────────────────
# Programme
# ─────────────────────────────────────────────────────────────────────

def rassemble(hors_ligne: bool) -> tuple[list[Constat], str | None]:
    texte = WORKFLOW.read_text(encoding="utf-8")
    constantes = lire_constantes(texte)
    gitlab_ci = GITLAB_CI.read_text(encoding="utf-8") \
        if GITLAB_CI.exists() else None

    constats: list[Constat] = [controle_pin(constantes["pin"])]

    if hors_ligne:
        constats.append(Constat(
            "configuration GitHub", None,
            "--hors-ligne : environnement, secret et variables NON "
            "verifies. Relancer sans ce drapeau"))
    else:
        token = _token()
        if token is None:
            constats.append(Constat(
                "configuration GitHub", None,
                "aucun token GitHub. Poser GH_TOKEN, ou s'authentifier "
                "avec `gh auth login`"))
        else:
            chemin = (f"/repos/{depot()}/environments/{ENVIRONNEMENT}")
            try:
                env = _get(chemin, token)
                protection = env.get("deployment_branch_policy") or {}
                branches = None
                if protection.get("custom_branch_policies"):
                    try:
                        branches = _get(chemin + "/deployment-branch-policies",
                                        token).get("branch_policies") or []
                    except Injoignable:
                        branches = None
                if branches is None and protection.get("protected_branches"):
                    constats.append(Constat(
                        "environnement restreint a main", True,
                        "politique « protected branches » : seule la "
                        "branche protegee peut deployer"))
                elif branches is not None:
                    noms = {b.get("name") for b in branches}
                    constats.append(Constat(
                        "environnement restreint a main", noms == {"main"},
                        f"branches autorisees : {sorted(noms) or 'aucune'}"))
                else:
                    constats.append(Constat(
                        "environnement restreint a main", False,
                        "aucune restriction de branche : n'importe quelle "
                        "branche pourrait lire le secret GitLab"))
                secrets = _get(chemin + "/secrets", token).get("secrets") or []
                variables = _get(chemin + "/variables", token).get(
                    "variables") or []
                constats.append(controle_secret(secrets))
                constats.extend(controle_variables(variables))
                par_nom = {v.get("name"): v.get("value") for v in variables}
                constats.append(controle_url(
                    constantes["url"], par_nom.get("GITLAB_REPOSITORY_SSH_URL")))
                constats.append(controle_empreinte_hote(
                    par_nom.get("GITLAB_KNOWN_HOSTS"),
                    par_nom.get("GITLAB_ED25519_HOST_FINGERPRINT")))
                constats.append(controle_empreinte_client(
                    par_nom.get("GITLAB_MIRROR_KEY_FINGERPRINT")))
            except Injoignable as exc:
                constats.append(Constat(
                    f"environnement {ENVIRONNEMENT}", False,
                    f"{exc}\n      L'environnement doit exister et le token "
                    f"doit pouvoir le lire (portee `repo`)"))
        # Deux verifications qui, elles, ne dependent pas de l'API.
        constats.append(controle_permissions())

    constats.append(controle_gitlab_ci(gitlab_ci))
    return constats, constantes["url"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--hors-ligne", action="store_true",
                   help="ne pas interroger l'API GitHub")
    args = p.parse_args()

    constats, url = rassemble(args.hors_ligne)

    print("CONTROLE DE CONFIGURATION DU MIROIR")
    print("=" * 68)
    print(f"Workflow   : {WORKFLOW.relative_to(ROOT)}")
    print(f"Environne. : {ENVIRONNEMENT}")
    print(f"Destination: {url or '(constante introuvable)'}")
    print()
    for c in constats:
        print(f"[{c.symbole}] {c.nom}")
        for ligne in c.detail.splitlines():
            print(f"         {ligne}")
    print()
    echecs = [c for c in constats if c.ok is False]
    manuels = [c for c in constats if c.ok is None]
    if echecs:
        print(f"{len(echecs)} point(s) BLOQUANT(S). Le miroir ne peut pas "
              f"fonctionner en l'etat.")
        return 1
    if manuels:
        print(f"Configuration automatique conforme. "
              f"{len(manuels)} point(s) a verifier a la main — ils ne sont "
              f"PAS certifies par ce script.")
        return 0
    print("Configuration conforme.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
