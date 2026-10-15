#!/usr/bin/env python3
"""Tests du contrôle de configuration du miroir.

## Le principe

Un contrôleur qui dit toujours « OK » est PIRE que pas de contrôleur : il
transforme une question ouverte (« est-ce que j'ai bien configuré ? ») en
une fausse réponse ferme. Chaque test de ce fichier pousse donc une
configuration CASSEE et exige que le contrôleur la refuse.

## L'ancrage

Deux paires (clé publique, empreinte) sont connues et documentées dans le
runbook d'Ariad. Elles servent d'ancrage a l'algorithme d'empreinte : si
`empreinte_blob` derivait, ces deux tests le diraient immediatement — au
lieu de laisser le contrôleur valider des empreintes fausses en silence.

L'une des deux est la clé d'un AUTRE projet (le miroir Ariad). C'est aussi
le test de non-reutilisation : la deploy key est « project-scoped », et la
partager entre deux projets elargit sa portee sans decision.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))

import check_mirror_setup as C  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "mirror-main-to-gitlab.yml"

# ── Les deux paires d'ancrage (publiques, documentees par le runbook) ──
CLE_HOTE_B64 = "AAAAC3NzaC1lZDI1NTE5AAAAIAfuCHKVTjquxvt6CM6tdG4SLp1Btn/nOeHHE5UOzRdf"
FP_HOTE = "SHA256:eUXGGm1YGsMAS7vkcx6JOJdOGHPem5gQp4taiCfCLB8"

CLE_CLIENT_B64 = "AAAAC3NzaC1lZDI1NTE5AAAAIJKTdD3se4yH0BUPpZ1lnIwIpTZzD5UlD8gcjSP6/R9O"
FP_CLIENT = "SHA256:p45GIFj/WYp6QAab9FgwbC0cgGv4EHPj94I8PKQBO5M"

# Notre propre deploy key (github-actions-aqt-mirror), dediee a ce depot.
# Le commentaire « Required environment » du workflow la cite : sans cette
# ancre, une rotation laisserait le workflow annoncer une empreinte perimee
# sans que rien ne le signale.
FP_CLIENT_AQT = "SHA256:RE5SfICdM/KFkU6bm0PRNhaDounULNbd04zIwXPhjlA"

KNOWN_HOSTS_OK = (
    "# gitlab.com host keys\n"
    f"gitlab.com ssh-ed25519 {CLE_HOTE_B64}\n"
    f"[gitlab.com]:22 ssh-ed25519 {CLE_HOTE_B64}\n"
)


class TestEmpreinte(unittest.TestCase):
    """L'algorithme d'empreinte, ancre a deux valeurs connues.

    Sans cet ancrage, une erreur d'implementation (mauvais decodage,
    padding non retire, mauvais algorithme) rendrait le contrôleur
    incapable de detecter une vraie cle fausse — ou capable de refuser
    une vraie cle. Les deux sont graves, le second fait perdre des
    heures.
    """

    def test_empreinte_de_la_cle_hote(self):
        self.assertEqual(C.empreinte_blob(CLE_HOTE_B64), FP_HOTE)

    def test_empreinte_de_la_cle_client(self):
        self.assertEqual(C.empreinte_blob(CLE_CLIENT_B64), FP_CLIENT)

    def test_pas_de_padding_dans_l_empreinte(self):
        """OpenSSH omet le `=` final ; l'inclure casserait la comparaison."""
        self.assertFalse(C.empreinte_blob(CLE_HOTE_B64).endswith("="))


class TestKnownHosts(unittest.TestCase):
    """L'analyse du known_hosts — un faux negatif ici bloquerait un vrai cle."""

    def test_extrait_la_cle_simple(self):
        self.assertEqual(C.cles_du_known_hosts(KNOWN_HOSTS_OK),
                         [CLE_HOTE_B64, CLE_HOTE_B64])

    def test_ignore_les_commentaires(self):
        texte = f"# gitlab.com ssh-ed25519 {CLE_HOTE_B64}\n"
        self.assertEqual(C.cles_du_known_hosts(texte), [],
                         "une cle en commentaire n'epingle RIEN")

    def test_ignore_une_cle_d_un_autre_hote(self):
        texte = f"github.com ssh-ed25519 {CLE_HOTE_B64}\n"
        self.assertEqual(C.cles_du_known_hosts(texte), [])

    def test_ignore_rsa(self):
        """Le runtime force ed25519 : epingler du rsa ne protegerait rien."""
        texte = f"gitlab.com ssh-rsa {CLE_HOTE_B64}\n"
        self.assertEqual(C.cles_du_known_hosts(texte), [])

    def test_accepte_le_prefixe_de_marqueur(self):
        texte = f"@cert-authority gitlab.com ssh-ed25519 {CLE_HOTE_B64}\n"
        self.assertEqual(C.cles_du_known_hosts(texte), [CLE_HOTE_B64])

    def test_accepte_plusieurs_hotes_sur_une_ligne(self):
        texte = f"gitlab.com,gitlab.org ssh-ed25519 {CLE_HOTE_B64}\n"
        self.assertEqual(C.cles_du_known_hosts(texte), [CLE_HOTE_B64])


class TestControleEmpreinteHote(unittest.TestCase):

    def test_empreinte_correcte_acceptee(self):
        c = C.controle_empreinte_hote(KNOWN_HOSTS_OK, FP_HOTE)
        self.assertTrue(c.ok, c.detail)

    def test_empreinte_dune_autre_cle_refusee(self):
        """Le cas MITM : la variable annonce une cle, l'epinglee en est une autre."""
        c = C.controle_empreinte_hote(KNOWN_HOSTS_OK, FP_CLIENT)
        self.assertFalse(c.ok)
        self.assertIn("recalculee", c.detail)

    def test_empreinte_inversee_avec_la_cle_client(self):
        """Meme faute dans l'autre sens : les deux doivent se recouper."""
        texte = f"gitlab.com ssh-ed25519 {CLE_CLIENT_B64}\n"
        c = C.controle_empreinte_hote(texte, FP_HOTE)
        self.assertFalse(c.ok)

    def test_known_hosts_vide(self):
        self.assertFalse(C.controle_empreinte_hote("", FP_HOTE).ok)
        self.assertFalse(C.controle_empreinte_hote(None, FP_HOTE).ok)

    def test_known_hosts_sans_ed25519(self):
        texte = "gitlab.com ssh-rsa AAAAB3NzaC1yc2EAAAA=\n"
        c = C.controle_empreinte_hote(texte, FP_HOTE)
        self.assertFalse(c.ok)
        self.assertIn("ed25519", c.detail)

    def test_empreinte_variable_absente(self):
        c = C.controle_empreinte_hote(KNOWN_HOSTS_OK, None)
        self.assertFalse(c.ok)

    def test_cle_tronquee_est_signalee(self):
        texte = "gitlab.com ssh-ed25519 AAAA\n"
        c = C.controle_empreinte_hote(texte, FP_HOTE)
        self.assertFalse(c.ok, "une cle illisible ne doit pas passer")


class TestControleClient(unittest.TestCase):

    def test_reutilisation_de_la_cle_ariad_refusee(self):
        """Le point le plus important : une deploy key est project-scoped.

        Reutiliser la cle d'Ariad donnerait a un run de CE depot un droit
        d'ecriture sur le projet d'Ariad. Rien ne le signalerait : la cle
        est valide, bien formee, et l'empreinte correspond.
        """
        c = C.controle_empreinte_client(FP_CLIENT)
        self.assertFalse(c.ok)
        self.assertIn("Ariad", c.detail)

    def test_empreinte_valide_acceptee(self):
        autre = "SHA256:" + "A" * 43
        c = C.controle_empreinte_client(autre)
        self.assertTrue(c.ok, c.detail)

    def test_empreinte_mal_formee_refusee(self):
        for mauvais in ("p45GIFj/WYp6QAab9FgwbC0cgGv4EHPj94I8PKQBO5M",
                        "SHA256:court", "SHA256:" + "A" * 44, ""):
            with self.subTest(valeur=mauvais):
                self.assertFalse(C.controle_empreinte_client(mauvais).ok)

    def test_absence_refusee(self):
        self.assertFalse(C.controle_empreinte_client(None).ok)


class TestControleUrl(unittest.TestCase):

    def test_egalite_exacte_acceptee(self):
        u = "git@gitlab.com:cheurteen1/agentic-quantum-trading.git"
        self.assertTrue(C.controle_url(u, u).ok)

    def test_autre_projet_refuse(self):
        """Le scenario d'Ariad : meme hote, autre projet."""
        w = "git@gitlab.com:cheurteen1/agentic-quantum-trading.git"
        c = C.controle_url(w, "git@gitlab.com:cheurteen1/codebase-memory-V2.git")
        self.assertFalse(c.ok)
        self.assertIn("stricte", c.detail)

    def test_https_au_lieu_de_ssh_refuse(self):
        w = "git@gitlab.com:cheurteen1/agentic-quantum-trading.git"
        c = C.controle_url(
            w, "https://gitlab.com/cheurteen1/agentic-quantum-trading.git")
        self.assertFalse(c.ok)

    def test_espace_final_tolere(self):
        """Une valeur collee depuis une interface attrape souvent un espace."""
        u = "git@gitlab.com:cheurteen1/agentic-quantum-trading.git"
        self.assertTrue(C.controle_url(u, u + "\n").ok)

    def test_url_absente_refusee(self):
        u = "git@gitlab.com:x/y.git"
        self.assertFalse(C.controle_url(u, None).ok)
        self.assertFalse(C.controle_url(u, "").ok)


class TestControlePin(unittest.TestCase):

    def test_pin_damorcage_refuse(self):
        """40 zeros est bien forme mais ne resout vers aucun commit."""
        c = C.controle_pin("0" * 40)
        self.assertFalse(c.ok)
        self.assertIn("amorcage", c.detail)

    def test_pin_valide_accepte(self):
        self.assertTrue(C.controle_pin("a" * 40).ok)

    def test_pin_mal_forme_refuse(self):
        for mauvais in ("abc", "A" * 40, "z" * 40, "0" * 39, "0" * 41):
            with self.subTest(valeur=mauvais):
                self.assertFalse(C.controle_pin(mauvais).ok)

    def test_pin_absent_refuse(self):
        self.assertFalse(C.controle_pin(None).ok)


class TestControleVariables(unittest.TestCase):

    ATTENDUES = ("GITLAB_REPOSITORY_SSH_URL", "GITLAB_KNOWN_HOSTS",
                 "GITLAB_MIRROR_KEY_FINGERPRINT",
                 "GITLAB_ED25519_HOST_FINGERPRINT")

    def test_toutes_presentes_et_pleines(self):
        variables = [{"name": n, "value": "x"} for n in self.ATTENDUES]
        constats = C.controle_variables(variables)
        self.assertEqual(len(constats), 1)
        self.assertTrue(constats[0].ok)

    def test_variable_absente_signalee(self):
        variables = [{"name": n, "value": "x"} for n in self.ATTENDUES[:-1]]
        constats = C.controle_variables(variables)
        self.assertIn("GITLAB_ED25519_HOST_FINGERPRINT",
                      " ".join(c.nom for c in constats))
        self.assertTrue(all(not c.ok for c in constats))

    def test_variable_vide_signalee(self):
        """Une variable presente mais vide: le workflow echoue en la lisant.

        C'est une erreur d'amorcage classique : on cree la variable en
        pensant la remplir plus tard.
        """
        variables = [{"name": n, "value": ""} for n in self.ATTENDUES]
        constats = C.controle_variables(variables)
        self.assertTrue(all(not c.ok for c in constats))
        self.assertTrue(all("VIDE" in c.detail for c in constats))

    def test_espace_seul_traite_comme_vide(self):
        variables = [{"name": n, "value": " \n"} for n in self.ATTENDUES]
        self.assertTrue(all(not c.ok for c in C.controle_variables(variables)))


class TestControleSecret(unittest.TestCase):

    def test_secret_present_accepte(self):
        c = C.controle_secret([{"name": "GITLAB_MIRROR_SSH_PRIVATE_KEY"}])
        self.assertTrue(c.ok)

    def test_secret_absent_refuse(self):
        self.assertFalse(C.controle_secret([]).ok)
        self.assertFalse(C.controle_secret(
            [{"name": "AUTRE_CHOSE"}]).ok)


class TestControleGitlabCi(unittest.TestCase):

    def test_when_never_accepte(self):
        texte = "workflow:\n  rules:\n    - when: never\n"
        self.assertTrue(C.controle_gitlab_ci(texte).ok)

    def test_fichier_absent_refuse(self):
        c = C.controle_gitlab_ci(None)
        self.assertFalse(c.ok)

    def test_fichier_sans_desactivation_refuse(self):
        c = C.controle_gitlab_ci("test:\n  script: echo bonjour\n")
        self.assertFalse(c.ok)
        self.assertIn("when: never", c.detail)


class TestPermissionsEstManuel(unittest.TestCase):
    """L'autorisation deploy key sur main n'est PAS verifiable ici.

    Le point de ce test : le contrôleur ne doit jamais rapporter « OK »
    pour quelque chose qu'il n'a pas regardé. Un contrôle qui se declare
    vert sans avoir verifie donne une confiance qu'il n'a pas gagnee —
    exactement le fail-open que ce depot combat ailleurs.
    """

    def test_rapporte_manuel_et_jamais_ok(self):
        c = C.controle_permissions()
        self.assertIsNone(c.ok, "doit etre rapportee MANUEL, pas OK")
        self.assertEqual(c.symbole, "MANUEL")
        self.assertIn("main", c.detail)


class TestAnalyseRemote(unittest.TestCase):
    """`depot()` ne doit JAMAIS deviner le depot qu'il interroge.

    Le controle interroge l'API GitHub. S'il se rabattait sur un nom en
    dur quand `origin` est illisible, il interrogerait un depot qui n'est
    pas celui de l'operateur — et rendrait un verdict sur une
    configuration qui n'est pas celle qu'on croit examiner. Un repli
    silencieux est ici un fail-open : il rend « OK » sur le mauvais objet.
    """

    def test_url_https(self):
        self.assertEqual(
            C.analyse_remote(
                "https://github.com/Cheurteenyt/agentic-quantum-trading.git"),
            "Cheurteenyt/agentic-quantum-trading")

    def test_url_ssh(self):
        self.assertEqual(
            C.analyse_remote(
                "git@github.com:Cheurteenyt/agentic-quantum-trading.git"),
            "Cheurteenyt/agentic-quantum-trading")

    def test_sans_suffixe_git(self):
        self.assertEqual(C.analyse_remote("https://github.com/o/r"), "o/r")

    def test_url_non_github_rend_None(self):
        for mauvais in ("git@gitlab.com:cheurteen1/x.git",
                        "https://gitlab.com/o/r.git",
                        "n'importe quoi", ""):
            with self.subTest(url=mauvais):
                self.assertIsNone(C.analyse_remote(mauvais))

    def test_aucun_repli_en_dur_dans_le_controleur(self):
        source = (ROOT / "scripts" / "ci" /
                  "check_mirror_setup.py").read_text(encoding="utf-8")
        self.assertNotIn(
            'return "Cheurteenyt', source,
            "depot() a un repli en dur : le contrôle interrogerait un "
            "dépôt choisi d'avance au lieu de celui de l'opérateur")


class TestAccordAvecLeWorkflow(unittest.TestCase):
    """Le contrôleur lit ses constantes DANS le workflow.

    Ce test verrouille le fait : si quelqu'un recopiait les valeurs dans
    le contrôleur, elles deriveraient du workflow en silence, et le
    contrôle validerait une configuration pendant que le workflow en
    attendrait une autre.
    """

    @classmethod
    def setUpClass(cls):
        cls.wf = WORKFLOW.read_text(encoding="utf-8")

    def test_url_lue_dans_le_workflow(self):
        c = C.lire_constantes(self.wf)
        self.assertEqual(c["url"],
                         "git@gitlab.com:cheurteen1/agentic-quantum-trading.git",
                         "l'URL du workflow doit viser le projet GitLab cible")

    def test_le_workflow_ne_vise_aucun_projet_ariad(self):
        """Les restes d'Ariad sont des pieges, et pas seulement son nom.

        Le port avait adapte l'URL du projet mais PAS l'empreinte de la
        cle, une ligne plus bas : le workflow annoncait la deploy key
        d'Ariad. Un operateur suivant la checklist aurait pose la
        mauvaise — et le controle du nom ne voyait rien.

        Les verifications portent sur des LIGNES, jamais sur le fichier
        entier : comparer 750 lignes de YAML recrache tout le fichier a
        l'echec et noie la raison.
        """
        lignes = self.wf.splitlines()

        for motif, explication in (
            ("codebase-memory-V2", "le projet GitLab d'Ariad"),
            ("Cheurteenyt/Ariad", "le depot GitHub d'Ariad"),
            ("github-actions-passive-mirror",
             "le titre de la deploy key d'Ariad"),
            ("p45GIFj",
             "l'empreinte de la cle d'Ariad : une deploy key est "
             "« project-scoped », la reutiliser donnerait a ce depot "
             "un droit d'ECRITURE sur son projet"),
        ):
            for numero, ligne in enumerate(lignes, 1):
                with self.subTest(motif=motif, ligne=numero):
                    self.assertNotIn(motif, ligne,
                                     f"ligne {numero} : {explication}")

        self.assertTrue(
            any(FP_CLIENT_AQT in ligne for ligne in lignes),
            "le workflow ne cite nulle part notre empreinte "
            f"({FP_CLIENT_AQT}). Si la cle a tourne, mettre a jour son "
            "commentaire « Required environment », puis l'ancre "
            "FP_CLIENT_AQT de ce fichier")

    def test_pin_lu_dans_le_workflow(self):
        """Le pin du workflow REEL doit etre pose, et non l'amorcage.

        Ce test a exige l'inverse tant que le pin valait zero : le
        contrôleur devait le DIRE au lieu de l'avaler. Depuis que le PR
        du pin est passe, il exige l'inverse — sinon un retour a
        l'amorcage passerait inapercu, et le miroir serait mort a
        l'etape 1 sans que rien ne le signale avant le run.
        """
        c = C.lire_constantes(self.wf)
        constat = C.controle_pin(c["pin"])
        self.assertTrue(
            constat.ok,
            "le pin du workflow est encore l'amorcage : poser le sha du "
            "commit de fusion qui a introduit scripts/ci/ sur main")

    def test_le_workflow_ne_force_jamais_le_push(self):
        """L'invariant 5, verifie aussi sur le workflow (qui pourrait
        passer des arguments au script)."""
        for ligne in self.wf.splitlines():
            nu = ligne.strip()
            if nu.startswith("#") or "git push" not in nu:
                continue
            with self.subTest(ligne=nu[:80]):
                self.assertNotIn("--force", nu)
                self.assertNotIn("--mirror", nu)

    def test_le_declencheur_ne_contient_pas_workflow_dispatch(self):
        """L'ecart assume depuis Ariad, verrouille sur TROIS niveaux.

        Si quelqu'un remettait le chemin `workflow_dispatch` sans le job
        de preflight correspondant, chaque CI lancee a la main produirait
        un miroir rouge. Les trois verrous ci-dessous doivent sauter
        ensemble pour que le chemin revienne — pas l'un par inadvertance.
        """
        import yaml
        d = yaml.safe_load(self.wf)
        declencheur = d.get("on") if "on" in d else d.get(True)
        self.assertIn("workflow_run", declencheur)
        self.assertNotIn(
            "workflow_dispatch", declencheur,
            "le declencheur ne doit pas accepter workflow_dispatch")

        # Verrou 2 : la condition du job exige un push.
        condition = d["jobs"]["mirror"]["if"]
        self.assertIn("github.event.workflow_run.event == 'push'", condition)
        self.assertNotIn("workflow_dispatch", condition)

        # Verrou 3 : la validation de l'etape 1 refuse tout ce qui n'est
        # pas `push`, meme si les deux premiers verrous sautaient.
        self.assertIn('if event not in {"push"}', self.wf,
                      "l'etape 1 doit refuser tout evenement autre que push")


class TestExecutionReelle(unittest.TestCase):
    """Le programme complet, en mode hors-ligne, sur le VRAI depot.

    La regle verifiee n'est pas « le depot est mal configure » — elle
    change de valeur le jour du PR qui posera le pin. La regle qui tient
    dans les deux cas est : **le verdict du contrôleur doit s'accorder
    avec ce que contient le workflow.** Un contrôleur qui se plaint d'un
    pin d'amorcage alors que le pin est reel est aussi faux qu'un
    contrôleur silencieux devant un pin d'amorcage.
    """

    @staticmethod
    def _lance():
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ci" /
                                 "check_mirror_setup.py"), "--hors-ligne"],
            cwd=ROOT, capture_output=True, text=True, timeout=60)

    def test_le_verdict_s_accorde_avec_le_pin_reel(self):
        constantes = C.lire_constantes(WORKFLOW.read_text(encoding="utf-8"))
        amorcage = constantes["pin"] == "0" * 40
        r = self._lance()
        if amorcage:
            self.assertEqual(
                r.returncode, 1,
                f"pin d'amorcage : le contrôle doit sortir en 1\n"
                f"{r.stdout[-1200:]}")
            self.assertIn("amorcage", r.stdout)
        else:
            self.assertNotIn(
                "amorcage", r.stdout,
                "le pin est reel : le contrôle ne doit plus se plaindre "
                "de l'amorcage")
        self.assertIn("MANUEL", r.stdout,
                      "le point non verifiable doit etre rapporte MANUEL, "
                      "jamais omis")

    def test_hors_ligne_ne_pretend_pas_avoir_verifie_github(self):
        r = self._lance()
        self.assertIn("NON verifies", r.stdout,
                      "le mode hors-ligne doit DIRE ce qu'il n'a pas "
                      "verifie, pas le passer sous silence")


if __name__ == "__main__":
    unittest.main()
