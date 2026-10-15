#!/usr/bin/env python3
"""Le MIROIR GitHub -> GitLab, teste sur de VRAIS depots nus.

## Pourquoi ce fichier existe

`scripts/ci/mirror-main-to-gitlab.sh` detient un secret GitLab en écriture
et decide, seul, de pousser ou non sur un dépôt distant. C'est le seul
composant du dépôt qui a ce pouvoir. Il est porte depuis le systeme Ariad
ou il tourne en production depuis juillet 2026 — mais un composant porte
n'est pas un composant verifie dans SON depot.

Les tests structurels (grep sur le source) sont ici, mais ils ne sont PAS
la partie importante. Un script peut contenir la chaine `DIVERGENCE` et ne
jamais la produire. Ce qui compte, c'est que la machine a etats, confrontee
a un vrai depot nu, fasse ce qu'elle annonce :

  - depot distant VIDE            -> pousse
  - deja au bon sha               -> no-op, MAIS re-verifie quand meme
  - en retard (fast-forward)      -> pousse
  - EN AVANCE mais valide         -> no-op (ne rollback JAMAIS)
  - divergence (commits GitLab
    absents de GitHub)            -> ECHOUE, sans pousser
  - hook pre-receive qui refuse   -> classe le refus, n'invente pas
  - course apres le push          -> detectee par la post-verification

Le cas « en avance -> no-op » est le plus important de la liste. C'est
l'invariant 9 du modele : *un vieux run ne doit jamais rollback GitLab*.
Un miroir qui, par maladresse, « remet les pendules a l'heure » detruirait
le travail d'un run plus recent — et le ferait silencieusement.

## Le piege que ce fichier evite

Le script porte un garde-fou : les hooks de test ne s'activent JAMAIS
quand `GITHUB_ACTIONS=true`. Sans ce garde-fou, une variable
d'environnement injectee en production suffirait a faire executer une
commande arbitraire au moment precis ou la cle SSH est materialisee.
`TestGardeDeProduction` verifie ce garde-fou separement, parce qu'un
garde-fou qu'on ne teste pas n'existe pas.

## Portage

Porte depuis `v2/tests/ci/r168-mirror-runtime.test.ts` (934 lignes,
vitest) du depot Ariad. Les scenarios ont ete conserves ; le harnais est
reecrit en `unittest` + `subprocess` pour ce depot.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "mirror-main-to-gitlab.sh"

# Le script refuse de tourner sans bash ; git est evidemment requis.
MANQUANT = [n for n in ("bash", "git") if shutil.which(n) is None]


class TestOutilsRequis(unittest.TestCase):
    """En CI, un outil manquant doit ECHOUER, pas faire sauter des tests.

    Les classes ci-dessous portent un `skipIf` pour ne pas casser le
    poste d'un developpeur qui n'a pas git. Mais un test saute ne compte
    PAS dans le total : le ratchet verrait 3120 au lieu de 3140 et
    accuserait « des tests ont disparu » — en designant le mauvais
    coupable, sans jamais nommer l'outil. Mieux vaut le nommer ici.
    """

    def test_les_outils_sont_presents_en_ci(self):
        # Pas de `skipTest` ici, expres : un test saute ne compte pas
        # dans le total, donc le compte local et celui de la CI
        # divergeraient — et le ratchet signalerait un ecart fantome.
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return  # hors CI : le skipIf des classes fait foi
        self.assertEqual(MANQUANT, [],
                         f"outils absents en CI : {MANQUANT} — les tests "
                         f"du miroir ne peuvent pas s'executer")

# Variables d'environnement que le harnais ne doit JAMAIS heriter : elles
# viennent de la machine de developpement ou de la CI, et contamineraient
# les scenarios (le plus grave etant GITHUB_ACTIONS, qui desactive les
# hooks de test et ferait passer des tests de course pour des succes).
A_PURGER = (
    "TARGET_SHA", "GITLAB_URL", "GITHUB_REMOTE", "SKIP_SSH_CONFIG",
    "SKIP_FP_CHECKS", "OUTPUT_FILE", "CBM_MIRROR_TEST_MODE",
    "GITHUB_ACTIONS", "MIRROR_TEST_AFTER_INITIAL_READ",
    "MIRROR_TEST_AFTER_PUSH", "MIRROR_TEST_BEFORE_FINAL_READ",
    "EXPECTED_KEY_FP", "EXPECTED_HOST_FP", "SSH_KEY_FILE",
    "KNOWN_HOSTS_FILE",
)

CLES_SORTIE = (
    "final_result", "observed_sha", "github_main_sha", "error_category",
    "error_phase", "client_fp_verified", "host_fp_verified",
    "push_attempted", "push_completed", "post_verify_result",
)


def _run(cmd, cwd=None, env=None, timeout=60):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=timeout)


def _git(*args, cwd=None):
    r = _run(["git", *args], cwd=cwd)
    if r.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} a echoue ({r.returncode})\n"
            f"stdout: {r.stdout}\nstderr: {r.stderr}")
    return r.stdout.strip()


class Resultat:
    """Ce que le script a fait, et ce qu'il a RACONTE avoir fait."""

    def __init__(self, code, stdout, stderr, sorties, brut):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.sorties = sorties
        self.brut = brut

    def diagnostic(self) -> str:
        return (f"exit={self.code}\n"
                f"--- stdout ---\n{self.stdout}\n"
                f"--- stderr ---\n{self.stderr}\n"
                f"--- outputs ---\n{json.dumps(self.sorties, indent=2)}")


class DepotNu:
    """Un GitHub nu, un GitLab nu, un depot de travail — comme en vrai.

    `GITLAB_URL` et `GITHUB_REMOTE` sont des URL `file://`. Le script
    accepte ce mode explicitement (c'est ce qui le rend testable sans
    reseau ni cle SSH), et c'est AUSSI la condition qui autorise les
    hooks de test — voir `TestGardeDeProduction`.
    """

    _compteur = 0

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mirror-runtime-"))
        self.github = self.tmp / "github.git"
        self.gitlab = self.tmp / "gitlab.git"
        self.work = self.tmp / "work"
        self.output = self.tmp / "outputs.txt"

        _git("init", "--bare", "-b", "main", str(self.github))
        _git("init", "--bare", "-b", "main", str(self.gitlab))
        # GitLab accepte les options de push (le script envoie
        # `-o ci.no_pipeline` : la CI GitLab ne doit jamais se declencher
        # sur un commit miroir).
        _git("-C", str(self.gitlab), "config",
             "receive.advertisePushOptions", "true")

        _git("init", "-b", "main", str(self.work))
        _git("-C", str(self.work), "config", "user.email", "test@test.test")
        _git("-C", str(self.work), "config", "user.name", "Test")
        _git("-C", str(self.work), "remote", "add", "origin",
             str(self.github))
        _git("-C", str(self.work), "remote", "add", "gitlab",
             str(self.gitlab))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ── construction d'historique ────────────────────────────────────
    def commit(self, message: str) -> str:
        """Un commit dont le contenu differe TOUJOURS du precedent."""
        DepotNu._compteur += 1
        (self.work / "file.txt").write_text(
            f"{message}\n{DepotNu._compteur}\n{time.time_ns()}\n",
            encoding="utf-8")
        _git("-C", str(self.work), "add", "-A")
        _git("-C", str(self.work), "commit", "-m", message)
        return _git("-C", str(self.work), "rev-parse", "HEAD")

    def pousse_github(self):
        _git("-C", str(self.work), "push", "origin", "main")

    def fixe_gitlab(self, sha: str):
        """Place GitLab sur `sha` — simule un miroir precedent."""
        _git("-C", str(self.work), "push", "gitlab",
             f"{sha}:refs/heads/main", "--force")

    def sha_gitlab(self) -> str:
        r = _run(["git", "ls-remote", str(self.gitlab), "refs/heads/main"])
        return r.stdout.split()[0] if r.stdout.strip() else ""

    def divergence_gitlab(self) -> str:
        """Un commit qui existe SUR GITLAB SEULEMENT — l'incident."""
        d = self.tmp / "diverge"
        _git("clone", "-b", "main", str(self.gitlab), str(d))
        _git("-C", str(d), "config", "user.email", "d@test")
        _git("-C", str(d), "config", "user.name", "Diverge")
        (d / "diverge.txt").write_text("divergence\n", encoding="utf-8")
        _git("-C", str(d), "add", "-A")
        _git("-C", str(d), "commit", "-m", "divergent commit")
        _git("-C", str(d), "push", "origin", "main")
        return _git("-C", str(d), "rev-parse", "HEAD")

    def hook_pre_receive(self, message: str):
        h = self.gitlab / "hooks" / "pre-receive"
        h.write_text(f'#!/bin/bash\necho "{message}" >&2\nexit 1\n',
                     encoding="utf-8")
        h.chmod(0o755)

    # ── execution ────────────────────────────────────────────────────
    def _env_propre(self) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in A_PURGER}
        return env

    def miroir(self, cible: str, *, mode_test=False, hooks=None) -> Resultat:
        """Execute le script comme le ferait le workflow."""
        _git("-C", str(self.work), "checkout", cible)
        env = self._env_propre()
        env.update({
            "TARGET_SHA": cible,
            "GITLAB_URL": f"file://{self.gitlab}",
            "GITHUB_REMOTE": f"file://{self.github}",
            "SKIP_SSH_CONFIG": "yes",
            "SKIP_FP_CHECKS": "yes",
            "OUTPUT_FILE": str(self.output),
        })
        if mode_test:
            env["CBM_MIRROR_TEST_MODE"] = "1"
            env.update(hooks or {})
        r = _run(["bash", str(SCRIPT)], cwd=str(self.work), env=env,
                 timeout=120)
        brut = self.output.read_text(encoding="utf-8") if \
            self.output.exists() else ""
        sorties = {}
        for ligne in brut.splitlines():
            if "=" in ligne:
                k, _, v = ligne.partition("=")
                sorties[k] = v
        return Resultat(r.returncode, r.stdout, r.stderr, sorties, brut)


@unittest.skipIf(MANQUANT, f"outils absents : {', '.join(MANQUANT)}")
class BaseMiroir(unittest.TestCase):
    """Deux commits sur GitHub (s1, s2), GitLab vide au depart.
    `s3` n'est PAS cree ici : seuls les scenarios qui ont besoin d'un
    commit PLUS RECENT que la cible le demandent, via `ajoute_s3()`. Le
    creer pour tout le monde ferait que `github_main_sha` vaudrait s3
    partout — et un test qui compare a s2 echouerait pour une raison qui
    n'a rien a voir avec ce qu'il verifie.
    """

    def setUp(self):
        self.d = DepotNu()
        self.addCleanup(self.d.__exit__)
        self.s1 = self.d.commit("R1")
        self.d.pousse_github()
        self.s2 = self.d.commit("R2")
        self.d.pousse_github()
        self.assertEqual(self.d.sha_gitlab(), "")

    def ajoute_s3(self) -> str:
        """Un commit de plus sur GitHub — GitLab ne le voit pas encore."""
        self.s3 = self.d.commit("R3")
        self.d.pousse_github()
        return self.s3

    def verifie(self, cond, r: Resultat, msg=""):
        if not cond:
            self.fail(f"{msg}\n{r.diagnostic()}")


class TestEtatsDuMiroir(BaseMiroir):
    """La machine a etats, confrontee a de vrais depots."""

    def test_depot_distant_vide_pousse(self):
        self.assertEqual(self.d.sha_gitlab(), "")
        r = self.d.miroir(self.s2)
        self.verifie(r.code == 0, r, "le miroir devait reussir")
        self.verifie(r.sorties.get("final_result") == "mirrored", r)
        self.verifie(r.sorties.get("observed_sha") == self.s2, r)
        self.verifie(r.sorties.get("push_attempted") == "true", r)
        self.verifie(r.sorties.get("push_completed") == "true", r)
        self.verifie(r.sorties.get("post_verify_result") == "success", r)
        self.verifie(r.sorties.get("error_category") == "none", r)
        self.assertEqual(self.d.sha_gitlab(), self.s2,
                         "GitLab doit etre exactement a la cible")

    def test_deja_miroir_est_un_no_op_qui_reverifie(self):
        """MIRROR-R168-01 : le no-op ne dispense PAS de re-verifier.

        Un no-op qui ne relit pas le distant ne peut pas detecter qu'un
        autre run a bouge GitLab entre-temps.
        """
        self.d.fixe_gitlab(self.s2)
        r = self.d.miroir(self.s2)
        self.verifie(r.code == 0, r)
        self.verifie(r.sorties.get("final_result") == "already-mirrored", r)
        self.verifie(r.sorties.get("observed_sha") == self.s2, r)
        self.verifie(r.sorties.get("push_attempted") == "false", r)
        self.verifie(r.sorties.get("push_completed") == "false", r)
        self.verifie(r.sorties.get("post_verify_result") == "success", r,
                     "la post-verification doit tourner meme sur un no-op")

    def test_en_retard_fait_un_fast_forward(self):
        self.d.fixe_gitlab(self.s1)
        r = self.d.miroir(self.s2)
        self.verifie(r.code == 0, r)
        self.verifie(r.sorties.get("final_result") == "mirrored", r)
        self.verifie(r.sorties.get("observed_sha") == self.s2, r)
        self.verifie(r.sorties.get("push_attempted") == "true", r)
        self.verifie(r.sorties.get("push_completed") == "true", r)
        self.assertEqual(self.d.sha_gitlab(), self.s2)

    def test_en_avance_mais_valide_ne_rollback_pas(self):
        """L'INVARIANT LE PLUS IMPORTANT : jamais de retour en arriere.

        Un run ancien (cible s2) ne doit pas ramener GitLab de s3 a s2.
        Le workflow peut rejouer un run en retard ; s'il ecrasait, il
        detruirait le miroir d'un run plus recent — et GitLab divergerait
        de GitHub sans que personne ne l'ait decide.
        """
        s3 = self.ajoute_s3()
        self.d.fixe_gitlab(s3)
        r = self.d.miroir(self.s2)
        self.verifie(r.code == 0, r,
                     "un GitLab en avance est un SUCCES, pas un echec")
        self.verifie(
            r.sorties.get("final_result") == "newer-valid-mirror-present", r)
        self.verifie(r.sorties.get("observed_sha") == s3, r)
        self.verifie(r.sorties.get("push_attempted") == "false", r,
                     "aucun push ne doit etre TENTE")
        self.assertEqual(self.d.sha_gitlab(), s3,
                         "GitLab doit rester en avance : pas de rollback")

    def test_divergence_echoue_sans_pousser(self):
        """Un commit GitLab absent de GitHub = incident, pas reparation."""
        self.d.fixe_gitlab(self.s1)
        diverge = self.d.divergence_gitlab()
        r = self.d.miroir(self.s2)
        self.verifie(r.code == 1, r, "la divergence doit faire echouer")
        self.verifie(r.sorties.get("final_result") == "failed", r)
        self.verifie(r.sorties.get("error_category") == "DIVERGENCE", r)
        self.verifie(r.sorties.get("error_phase") == "divergence-check", r)
        self.verifie(r.sorties.get("push_attempted") == "false", r,
                     "on ne pousse JAMAIS sur un depot divergent")
        self.assertEqual(self.d.sha_gitlab(), diverge,
                         "GitLab doit rester intact : rien n'a ete ecrase")

    def test_refus_pre_receive_est_classe(self):
        """Le refus doit etre NOMME, pas confondu avec une panne reseau."""
        self.d.hook_pre_receive(
            "not allowed to push code to protected branches on this project")
        r = self.d.miroir(self.s2)
        self.verifie(r.code == 1, r)
        self.verifie(r.sorties.get("final_result") == "failed", r)
        self.verifie(
            r.sorties.get("error_category") == "PROTECTED_BRANCH_REJECTED", r,
            "un refus de branche protegee doit etre classe comme tel — "
            "c'est LUI qui indique qu'il faut autoriser la cle deploy")
        self.verifie(r.sorties.get("error_phase") == "push", r)
        self.verifie(r.sorties.get("push_attempted") == "true", r)
        self.verifie(r.sorties.get("push_completed") == "false", r)

    def test_github_main_est_relu_a_la_fin(self):
        """MIRROR-R168.1-01 : la valeur rapportee doit etre une LECTURE."""
        self.d.fixe_gitlab(self.s1)
        r = self.d.miroir(self.s2)
        self.verifie(r.code == 0, r)
        self.verifie(r.sorties.get("github_main_sha") == self.s2, r,
                     "github_main_sha doit etre relu, pas recopie de "
                     "l'entree")


class TestCourses(BaseMiroir):
    """Le script doit resister a ce qui bouge PENDANT qu'il tourne.

    Ces scenarios utilisent les hooks de test du script, qui injectent une
    commande a un instant precis. Sans eux, on ne peut pas provoquer une
    course de facon deterministe — et un test de course non deterministe
    ne prouve rien.
    """

    def test_course_apres_push_est_detectee(self):
        """SIG-R169-Phase-B-CONC-R3-01 : le cas AFTER_PUSH_RACE.

        Scenario : ce run pousse s2, puis un run PLUS RECENT pousse s3
        avant la post-verification. Le resultat attendu n'est pas
        « echec » mais « newer-valid-mirror-present » — le travail du run
        recent est preserve, et les deux runs sont coherents.

        Le marqueur n'est PAS decoratif : sans lui, on ne saurait pas si
        le hook s'est execute ou si le scenario a simplement ete saute.
        """
        self.d.fixe_gitlab(self.s1)
        s3 = self.ajoute_s3()
        marqueur = self.d.tmp / "hook-a-tourne"
        hook = (f'git -C "{self.d.work}" push gitlab '
                f'{s3}:refs/heads/main --force && '
                f'touch "{marqueur}"')
        r = self.d.miroir(self.s2, mode_test=True,
                          hooks={"MIRROR_TEST_AFTER_PUSH": hook})
        # Pas de `|| true` : un hook qui echoue doit faire echouer le test.
        self.verifie(marqueur.exists(), r,
                     "le hook n'a pas tourne : le scenario n'a rien teste")
        self.verifie(
            r.sorties.get("final_result") == "newer-valid-mirror-present", r)
        self.verifie(r.sorties.get("push_attempted") == "true", r)
        self.verifie(r.sorties.get("push_completed") == "true", r)
        self.verifie(r.sorties.get("observed_sha") == s3, r)
        self.verifie(r.sorties.get("post_verify_result") == "success", r)
        self.verifie(r.sorties.get("github_main_sha") == s3, r)
        self.assertEqual(self.d.sha_gitlab(), s3,
                         "le travail du run recent doit avoir survecu")

    def test_sans_mode_test_aucun_hook_ne_tourne(self):
        """La production ne doit pas pouvoir executer une commande."""
        self.d.fixe_gitlab(self.s1)
        marqueur = self.d.tmp / "hook-a-tourne"
        r = self.d.miroir(self.s2, mode_test=False,
                          hooks={"MIRROR_TEST_AFTER_PUSH": f'touch "{marqueur}"'})
        self.verifie(r.code == 0, r)
        self.verifie(r.sorties.get("final_result") == "mirrored", r)
        self.assertFalse(marqueur.exists(),
                         "un hook a tourne alors que CBM_MIRROR_TEST_MODE "
                         "etait absent")


class TestSortiesEmisesUneFois(unittest.TestCase):
    """OBS-R168.1-01 : l'ancien defaut etait « dernier ecrivain gagne ».

    Si un `final_result` est ecrit deux fois, le lecteur du workflow lit
    la DERNIERE valeur sans le savoir. Un rapport qui se contredit
    silencieusement est pire qu'un rapport absent.
    """

    def test_chaque_cle_apparait_exactement_une_fois(self):
        with DepotNu() as d:
            s1 = d.commit("R1")
            d.pousse_github()
            d.fixe_gitlab(s1)
            s2 = d.commit("R2")
            d.pousse_github()
            r = d.miroir(s2)
            self.assertEqual(r.code, 0, r.diagnostic())
            for cle in CLES_SORTIE:
                with self.subTest(cle=cle):
                    n = len(re.findall(rf"^{re.escape(cle)}=", r.brut,
                                       flags=re.M))
                    self.assertEqual(
                        n, 1, f"la cle {cle!r} apparait {n} fois "
                              f"(attendu 1)\n{r.brut}")


@unittest.skipIf(MANQUANT, f"outils absents : {', '.join(MANQUANT)}")
class TestGardeDeProduction(unittest.TestCase):
    """Le garde-fou des hooks, teste pour lui-meme.

    Le script n'autorise un hook que si `CBM_MIRROR_TEST_MODE=1` ET que
    l'URL distante est en `file://` ET que `GITHUB_ACTIONS != true`. Les
    trois conditions comptent : en production, quelqu'un qui obtiendrait
    le controle de l'environnement du job pourrait sinon faire executer
    une commande arbitraire a l'instant ou la cle SSH est en memoire.
    """

    def test_github_actions_desactive_les_hooks(self):
        with DepotNu() as d:
            s1 = d.commit("R1")
            d.pousse_github()
            d.fixe_gitlab(s1)
            s2 = d.commit("R2")
            d.pousse_github()
            marqueur = d.tmp / "hook-a-tourne"
            # On force GITHUB_ACTIONS=true EN PLUS du mode test : le
            # script doit refuser d'executer le hook.
            env_force = {"GITHUB_ACTIONS": "true"}
            _git("-C", str(d.work), "checkout", s2)
            env = d._env_propre()
            env.update({
                "TARGET_SHA": s2,
                "GITLAB_URL": f"file://{d.gitlab}",
                "GITHUB_REMOTE": f"file://{d.github}",
                "SKIP_SSH_CONFIG": "yes",
                "SKIP_FP_CHECKS": "yes",
                "OUTPUT_FILE": str(d.output),
                "CBM_MIRROR_TEST_MODE": "1",
                "MIRROR_TEST_AFTER_PUSH": f'touch "{marqueur}"',
                **env_force,
            })
            res = _run(["bash", str(SCRIPT)], cwd=str(d.work), env=env,
                       timeout=120)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertFalse(
                marqueur.exists(),
                "GITHUB_ACTIONS=true n'a PAS desactive le hook : un "
                "environnement de CI compromis peut executer du code "
                "arbitraire pendant que la cle GitLab est materialisee")


@unittest.skipIf(MANQUANT, f"outils absents : {', '.join(MANQUANT)}")
class TestStructureDuScript(unittest.TestCase):
    """Controles de source.

    Ils ne prouvent PAS le comportement (c'est le role des tests ci-dessus)
    mais ils protegent contre une edition qui viderait une garantie sans
    toucher aux scenarios.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_le_script_existe_et_est_executable(self):
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(os.access(SCRIPT, os.X_OK),
                        "le workflow l'appelle via `bash`, mais un script "
                        "non executable est un piege pour l'operateur")

    def test_le_classificateur_connait_toutes_les_categories(self):
        categories = [
            "HOST_KEY_MISMATCH", "SSH_PUBLICKEY_REJECTED",
            "PROTECTED_BRANCH_REJECTED", "NON_FAST_FORWARD",
            "REMOTE_DNS_FAILURE", "REMOTE_TIMEOUT",
            "REMOTE_CONNECTION_REFUSED", "REMOTE_UNREACHABLE",
            "REPOSITORY_NOT_FOUND", "PRE_RECEIVE_REJECTED",
            "UNKNOWN_GIT_ERROR",
        ]
        for c in categories:
            with self.subTest(categorie=c):
                self.assertIn(c, self.source,
                              "le workflow lit error_category : une "
                              "categorie absente serait rapportee "
                              "UNKNOWN_GIT_ERROR et l'operateur perdrait "
                              "le diagnostic")

    def test_la_post_verification_tourne_toujours(self):
        self.assertIn("Post-push verification", self.source)
        self.assertIn("always runs", self.source)

    def test_liaison_de_la_cle_hote_par_ssh_keygen_F(self):
        self.assertIn("ssh-keygen -F gitlab.com", self.source)

    def test_empreinte_par_ssh_keygen_lf(self):
        self.assertIn("ssh-keygen -lf", self.source)
        self.assertNotIn("tr '+/' '-_'", self.source,
                         "une empreinte encodee en base64 URL-safe n'est "
                         "pas une empreinte OpenSSH : la comparaison avec "
                         "la valeur attendue ne voudrait rien dire")

    def test_les_timeouts_ssh_sont_configures(self):
        for attendu in ("BatchMode=yes", "ConnectTimeout=15",
                        "ConnectionAttempts=2", "ServerAliveInterval=15",
                        "ServerAliveCountMax=2"):
            with self.subTest(option=attendu):
                self.assertIn(attendu, self.source)

    def test_les_cles_protegees_par_phrase_secrete_sont_detectees(self):
        self.assertIn("ssh-keygen -y -P '' -f", self.source)

    def test_les_lectures_github_ne_sont_pas_avalees(self):
        self.assertIn("run_github_git", self.source)
        self.assertNotRegex(self.source, r"git\s+ls-remote[^\n]*\|\|\s*true",
                            "un `|| true` sur une lecture GitHub "
                            "transformerait une panne en « rien a faire »")
        self.assertIn("GITHUB_REMOTE_UNREACHABLE", self.source)
        self.assertIn("GITHUB_DNS_FAILURE", self.source)
        self.assertIn("GITHUB_AUTH_FAILURE", self.source)
        self.assertIn("GITHUB_REF_MISSING", self.source)

    def test_les_erreurs_locales_sont_classees(self):
        self.assertIn("LOCAL_OBJECT_MISSING", self.source)
        self.assertIn("LOCAL_REF_MISSING", self.source)
        self.assertIn("run_local_git", self.source)

    def test_les_sorties_passent_par_un_trap(self):
        self.assertIn("trap emit_final_outputs EXIT", self.source)

    def test_la_post_verification_exige_une_lecture_non_vide(self):
        self.assertIn("GITHUB_MAIN_SHA", self.source)
        self.assertIn("Post-verification: GitHub main SHA is empty",
                      self.source)

    def test_aucun_force_push_dans_le_script(self):
        """L'invariant 5 : le miroir ne force-pousse JAMAIS.

        `--force` peut apparaitre dans un COMMENTAIRE (pour dire qu'il est
        interdit) ; ce qui est verifie ici, c'est qu'aucune commande
        `git push` ne le porte.
        """
        for ligne in self.source.splitlines():
            nu = ligne.strip()
            if nu.startswith("#"):
                continue
            if "git push" in nu or ("push" in nu and "origin" in nu):
                with self.subTest(ligne=nu[:90]):
                    self.assertNotIn("--force", nu,
                                     "`--force` interdit dans une commande")
                    self.assertNotIn("--mirror", nu)
                    self.assertNotIn("--force-with-lease", nu)


if __name__ == "__main__":
    unittest.main()
