#!/usr/bin/env python3
"""Le CONTRAT du miroir — ce qui doit rester vrai, et ce qui ne doit JAMAIS revenir.

## Pourquoi ce fichier existe

Les tests voisins (`test_ci_mirror_runtime.py`, `test_ci_signature_gate.py`)
prouvent ce que le systeme FAIT. Ils ne peuvent pas prouver ce qu'il ne doit
jamais REFAIRE : un fichier de l'ancienne architecture recree, une permission
elargie, un workflow qui reprend le pouvoir de pousser, un hote SSH qui n'est
plus verifie — tout ça laisse le chemin heureux intact, donc tous les tests de
comportement verts.

C'est la moitie de la couverture du systeme d'origine (Ariad) qui n'avait pas
ete portee : ses 97 cas de `r166-github-canonical-passive-mirror.test.ts` sont
des assertions sur le TEXTE des artefacts. Ce fichier reprend l'idee, limitee a
ce qui est vrai ICI, et y ajoute la garde de l'outillage qui les protege (les
linters de la CI, sans lesquels un des deux scripts shell — 48 ko detenant le
seul secret d'ECRITURE du depot — ne serait analysé par rien).

## La regle d'ecriture

Un test qui affirme une ABSENCE est plus fragile qu'un test qui affirme une
presence : il faut le vouloir. Mais c'est exactement le but — la doctrine
« on ne retablit jamais le bidirectionnel » (R166, incident de quota des
runners partages GitLab) ne doit pas dependre de la memoire du redacteur.

On n'affirme jamais sur le fichier ENTIER : un `assertNotIn` sur un YAML de
753 lignes dit « quelque part », jamais « ici ». Chaque assertion collecte les
LIGNES fautives et les cite — un echec doit nommer la ligne, pas le fichier.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "mirror-main-to-gitlab.yml"
CI_WORKFLOW = WORKFLOWS / "ci.yml"
GITLAB_CI = ROOT / ".gitlab-ci.yml"
SCRIPTS_CI = ROOT / "scripts" / "ci"
SCRIPT_MIROIR = SCRIPTS_CI / "mirror-main-to-gitlab.sh"

# Le nom de l'environnement GitHub qui porte le secret. Il est aussi verifie
# par `check_mirror_setup.py` (politique de branche) ; ici on verifie que le
# JOB le consulte — sans lui, le secret n'est meme pas lisible.
ENVIRONNEMENT = "gitlab-passive-mirror"


def _lignes(chemin: Path) -> list[str]:
    return chemin.read_text(encoding="utf-8").splitlines()


def _fautives(chemin: Path, motif: str, *, ignorer_commentaires: bool = False) -> list[str]:
    """Les lignes qui matchent `motif`, citees avec leur numero."""
    trouvees = []
    for i, ligne in enumerate(_lignes(chemin), start=1):
        if ignorer_commentaires and ligne.strip().startswith("#"):
            continue
        if re.search(motif, ligne):
            trouvees.append(f"{chemin.name}:{i}: {ligne.strip()[:110]}")
    return trouvees


def _charger(chemin: Path):
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


class TestMoindrePrivilege(unittest.TestCase):
    """Le job de miroir detient une cle d'ECRITURE sur GitLab.

    Un composant qui peut ecrire dans un depot distant doit demander le
    MINIMUM de permissions GitHub — lire l'evenement, lire les commits — et
    ne jamais laisser trainer le token d'un autre. C'est l'exigence
    « least privilege » d'Ariad (r166), verifiee ici sur la structure du YAML.
    """

    def test_le_workflow_ne_demande_que_la_lecture(self):
        d = _charger(WORKFLOW)
        self.assertEqual(
            {"actions": "read", "contents": "read"}, d.get("permissions"),
            "les permissions du workflow doivent rester exactement "
            "actions:read + contents:read (moindre privilege)")

    def test_aucune_permission_d_ecriture_nulle_part(self):
        fautives = _fautives(WORKFLOW, r":\s*write\s*$")
        self.assertEqual([], fautives, "une permission d'ecriture a ete introduite")

    def test_les_deux_checkouts_ne_persistent_pas_les_credentials(self):
        """`persist-credentials: false` sur CHAQUE checkout.

        Sans lui, `actions/checkout` ecrit un token GitHub dans
        `.git/config` du depot — et le script de miroir tourne ensuite DANS
        cet arbre, avec le secret GitLab en memoire. Le checkout du
        verificateur epingle n'en a pas besoin non plus : il lit un commit
        par son sha.
        """
        lignes = _lignes(WORKFLOW)
        checkouts = [i for i, ligne in enumerate(lignes)
                     if "uses: actions/checkout@" in ligne]
        self.assertEqual(
            2, len(checkouts),
            "le workflow doit avoir exactement deux checkouts "
            "(le verificateur epingle + la cible)")
        for i in checkouts:
            fenetre = "\n".join(lignes[i:i + 8])
            self.assertIn(
                "persist-credentials: false", fenetre,
                f"le checkout de la ligne {i + 1} laisserait un token GitHub "
                f"dans l'arbre ou tourne le script de miroir")

    def test_le_job_travaille_dans_l_environnement_du_secret(self):
        d = _charger(WORKFLOW)
        self.assertEqual(
            ENVIRONNEMENT, d["jobs"]["mirror"].get("environment"),
            "le secret ne doit etre lisible que dans son environnement "
            "(c'est aussi lui qui porte la restriction de branche)")

    def test_l_hote_gitlab_est_verifie_strictement(self):
        """`StrictHostKeyChecking=yes`, jamais `no` ni `accept-new`.

        Troisieme barriere avec le `known_hosts` epingle et les deux
        empreintes recomparsees : pour un push automatique, accepter une cle
        d'hote inconnue n'est pas un raccourci, c'est une redirection.
        """
        self.assertIn(
            "StrictHostKeyChecking=yes",
            SCRIPT_MIROIR.read_text(encoding="utf-8"),
            "la verification de l'hote doit rester ACTIVE dans le script")
        fautives = _fautives(SCRIPT_MIROIR,
                             r"StrictHostKeyChecking=(no|accept-new)")
        self.assertEqual([], fautives,
                         "la verification de l'hote ne doit jamais etre desactivee")


class TestOrdreEtNettoyage(unittest.TestCase):
    """Le verdict juge l'etat REEL, et le nettoyage ne peut pas etre saute.

    L'ordre n'est pas cosmetique : le verdict exige
    `steps.cleanup.outcome == success`. Un nettoyage qui ne tourne pas doit
    rendre le verdict ROUGE, jamais absent — une cle privee qui survit au job
    est un incident, pas un detail.
    """

    @staticmethod
    def _etapes() -> list:
        return _charger(WORKFLOW)["jobs"]["mirror"]["steps"]

    def test_le_nettoyage_tourne_toujours(self):
        nettoyage = [s for s in self._etapes()
                     if isinstance(s, dict) and s.get("id") == "cleanup"]
        self.assertEqual(1, len(nettoyage), "l'etape `cleanup` a disparu")
        self.assertEqual(
            "always()", nettoyage[0].get("if"),
            "le nettoyage doit tourner meme si une etape precedente a echoue")

    def test_le_verdict_est_le_dernier_et_tourne_toujours(self):
        dernieres = self._etapes()[-1]
        self.assertEqual(
            "final_verdict", dernieres.get("id"),
            "le verdict doit rester la DERNIERE etape : c'est lui qui calcule "
            "l'etat effectif et sort en 1 sur FAILED")
        self.assertEqual("always()", dernieres.get("if"))

    def test_le_verdict_exige_la_reussite_du_nettoyage(self):
        verdict = self._etapes()[-1]
        self.assertEqual("${{ steps.cleanup.outcome }}",
                         verdict.get("env", {}).get("CLEANUP_OUTCOME"),
                         "le verdict doit recevoir l'etat du nettoyage")
        self.assertIn(
            '"${CLEANUP_OUTCOME:-}" = "success"', verdict["run"],
            "le verdict doit REFUSER un nettoyage qui n'est pas vert")

    def test_le_workflow_ne_pousse_jamais_lui_meme(self):
        """La seule ecriture distante passe par le script EPINGLE.

        Un `git push` inline dans le workflow contournerait la machine a
        etats auditee — et ne serait couvert par aucun de ses tests.
        """
        fautives = _fautives(WORKFLOW, r"\bgit\s+push\b", ignorer_commentaires=True)
        self.assertEqual(
            [], fautives,
            "le workflow ne doit pas porter de `git push` : le seul composant "
            "qui pousse est scripts/ci/mirror-main-to-gitlab.sh, epingle")


class TestGitLabRestePassif(unittest.TestCase):
    """Aucun pipeline GitLab ne doit jamais naitre.

    La double garde du R166 : `.gitlab-ci.yml` desactive tout (cote GitLab),
    ET chaque push porte `-o ci.no_pipeline` (cote GitHub). L'incident
    d'origine est un quota de runners partages epuise — la garde cote GitLab
    peut tomber avec une configuration d'equipe, pas la notre.
    """

    def test_gitlab_ci_ne_declenche_aucun_pipeline(self):
        # On lit la valeur au lieu d'un `when:\s*(?!never)` : le retour
        # arriere d'un `\s*` annule le lookahead (il peut matcher zero
        # espace, « never » n'est alors plus en tete) et le test passe en
        # annoncant avoir regarde.
        fautives = []
        for i, ligne in enumerate(_lignes(GITLAB_CI), start=1):
            m = re.search(r"when:\s*(\S+)\s*$", ligne)
            if m and m.group(1) != "never":
                fautives.append(f".gitlab-ci.yml:{i}: {ligne.strip()[:110]}")
        self.assertEqual([], fautives,
                         "tout `when:` de .gitlab-ci.yml doit valoir `never`")
        texte = GITLAB_CI.read_text(encoding="utf-8")
        self.assertGreaterEqual(
            texte.count("when: never"), 2,
            "la double garde doit rester : `workflow.rules` ET le job sentinelle")

    def test_chaque_push_gitlab_porte_ci_no_pipeline(self):
        fautives = []
        for i, ligne in enumerate(_lignes(SCRIPT_MIROIR), start=1):
            nu = ligne.strip()
            if nu.startswith("#") or "refs/heads/main" not in nu or "push" not in nu:
                continue
            if "ci.no_pipeline" not in nu:
                fautives.append(f"{SCRIPT_MIROIR.name}:{i}: {nu[:110]}")
        self.assertEqual([], fautives,
                         "un push GitLab sans `-o ci.no_pipeline` creerait un "
                         "pipeline a chaque miroir (quota des runners)")


class TestArchitectureAbandonneeNeRevientPas(unittest.TestCase):
    """Ce que le R166 a SUPPRIME ne doit pas revenir par inadvertance.

    Ariad teste l'absence des memes artefacts : l'architecture
    bidirectionnelle (GitLab -> GitHub) a ete abandonnee apres l'incident de
    quota, et `sync-graph-ui-to-gitlab` a suivi. La reintroduire par morceaux
    serait invisible — chaque morceau pris seul « marche ».
    """

    ANCIENS_JOBS = ("mirror-to-github", "quota-check", "mr-preflight")
    ANCIENS_FICHIERS = ("gitlab-mr-ci.yml", "sync-graph-ui-to-gitlab.yml")

    def test_gitlab_ci_ne_declare_aucun_job_de_l_ancienne_architecture(self):
        motif = r"^(%s)\s*:" % "|".join(self.ANCIENS_JOBS)
        fautives = [f".gitlab-ci.yml:{i}: {ligne.strip()}"
                    for i, ligne in enumerate(_lignes(GITLAB_CI), start=1)
                    if re.match(motif, ligne)]
        self.assertEqual([], fautives)

    def test_les_workflows_de_l_ancienne_architecture_sont_absents(self):
        for nom in self.ANCIENS_FICHIERS:
            self.assertFalse((WORKFLOWS / nom).exists(),
                             f"{nom} appartient a l'architecture abandonnee (R166)")

    def test_aucune_trace_des_composants_abandonnes(self):
        """Les noms du monde d'avant, nulle part dans ce qui PILOTE.

        Un commentaire qui explique pourquoi ils sont partis est legitime ;
        une ligne activee ne l'est pas.
        """
        fichiers = sorted(list(WORKFLOWS.glob("*.yml")) +
                          [p for p in SCRIPTS_CI.iterdir()
                           if p.suffix in (".sh", ".py")])
        fautives = []
        for f in fichiers:
            for i, ligne in enumerate(_lignes(f), start=1):
                if ligne.strip().startswith("#"):
                    continue
                if any(mot in ligne for mot in self.ANCIENS_JOBS + self.ANCIENS_FICHIERS):
                    fautives.append(f"{f.name}:{i}: {ligne.strip()[:110]}")
        self.assertEqual([], fautives)


class TestLeDeclencheurEstUnePorteEtroite(unittest.TestCase):
    """Le declencheur EST la porte d'entree du systeme (r166)."""

    @staticmethod
    def _declencheur():
        d = _charger(WORKFLOW)
        return d.get("on") if "on" in d else d.get(True)

    def test_le_declencheur_ne_peut_venir_que_de_la_CI_sur_main(self):
        wr = self._declencheur()["workflow_run"]
        self.assertEqual(["CI"], wr["workflows"])
        self.assertEqual(["completed"], wr["types"])
        self.assertEqual(["main"], wr["branches"],
                         "une branche de travail poussee sur GitLab ferait "
                         "du miroir un second canon")

    def test_le_miroir_exige_un_push_reussi_sur_ce_depot(self):
        """Quatre conditions, chacune pour un scenario precis.

        Sans `conclusion`, un run de CI ROUGE declencherait quand meme le
        miroir ; sans `event`, un dispatch manuel produirait un miroir rouge
        (la DIVERGENCE ASSUMEE du #308) ; sans `head_branch`, une branche
        poussee sur GitLab ferait doublon ; sans `head_repository`, un fork
        de la CI ferait courir NOTRE secret.
        """
        condition = _charger(WORKFLOW)["jobs"]["mirror"]["if"]
        for attendu in (
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.event == 'push'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.head_repository.full_name == github.repository",
        ):
            with self.subTest(condition=attendu):
                self.assertIn(attendu, condition)


class TestLaCIOutilleLeMiroir(unittest.TestCase):
    """Les linters qui gardent les artefacts ci-dessus.

    Un linter qui disparait en silence est exactement le fail-open que ce
    depot combat ailleurs (« un palier obligatoire ne peut plus disparaitre »,
    #289). Les deux sondes (`sc_probe.sh`, `al_probe.yml`) repondent a la meme
    question que la sonde pyflakes du palier : l'outil MESURE-t-il, ou
    sort-il 0 sans rien regarder ?
    """

    @staticmethod
    def _run(fragment: str) -> str:
        d = _charger(CI_WORKFLOW)
        for job in d["jobs"].values():
            for etape in job.get("steps") or []:
                if fragment.lower() in str(etape.get("name", "")).lower():
                    return etape.get("run", "") or ""
        return ""

    def test_shellcheck_garde_les_scripts_du_miroir(self):
        run = self._run("ShellCheck")
        self.assertIn("scripts/ci", run)
        self.assertIn("--severity=warning", run)
        self.assertIn(
            "shellcheck-v0.10.0/shellcheck", run,
            "la version doit rester epinglee : une mise a jour silencieuse "
            "changerait le verdict du lint")

    def test_shellcheck_sonde_l_outil(self):
        run = self._run("ShellCheck")
        self.assertIn("sc_probe.sh", run)
        self.assertIn(
            'if "$SC" --severity=warning /tmp/sc_probe.sh; then', run,
            "sans sonde, un binaire casse qui sort 0 rendrait le gate vert")

    def test_shellcheck_ne_peut_pas_mesurer_vide(self):
        run = self._run("ShellCheck")
        self.assertIn("${#scripts[@]}", run)
        self.assertIn("exit 1", run,
                      "un `scripts/ci/` vide doit faire ROUGE, pas passer")

    def test_actionlint_garde_les_workflows(self):
        run = self._run("actionlint")
        self.assertIn("v1.7.7", run)
        self.assertIn("al_probe.yml", run)
        self.assertIn(
            "./actionlint\n", run + "\n",
            "le lint doit aussi tourner sur les workflows reels, pas "
            "seulement sur la sonde")

    def test_les_linters_tournent_sur_chaque_PR_sans_filtre(self):
        """Le contrat d'un oracle bon marche : il ne depend d'AUCUN chemin.

        Un lint filtre disparaitrait des PR qui ne touchent « que » un YAML —
        exactement les PR qui modifient le workflow.
        """
        d = _charger(CI_WORKFLOW)
        for nom_job, job in d["jobs"].items():
            etapes = job.get("steps") or []
            if any("shellcheck" in str(e.get("name", "")).lower()
                   or "actionlint" in str(e.get("name", "")).lower()
                   for e in etapes):
                self.assertNotIn(
                    "needs.changes.outputs", str(job.get("if", "")),
                    f"le job `{nom_job}` porte un lint du miroir ET un "
                    f"filtre de chemins")
                return
        self.fail("aucun job de la CI ne porte les linters du miroir")


if __name__ == "__main__":
    unittest.main()
