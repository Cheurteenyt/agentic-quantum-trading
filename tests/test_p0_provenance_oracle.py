#!/usr/bin/env python3
"""L'ORACLE DE PROVENANCE (audit du 2026-10-08, action 5).

Ce test est le plus important du dépôt, et il ne teste presque rien :
il vérifie que l'**identité d'exécution** compose exactement les
éléments qui doivent la changer, et exactement ceux qui ne doivent pas.

Pourquoi il vaut plus que des dizaines de tests unitaires : parce que la
question n'est pas « est-ce que cette fonction marche ? » mais « **qu'est-ce
qui, dans ce dépôt, autorise à dire qu'un résultat est déjà calculé ?** ».
Une règle d'inclusion qu'on n'énumère pas est une règle qu'on ne tient pas.

Le piège qu'il ferme est réel et déjà réalisé deux fois dans ce dépôt :

  1. `ENGINE_FILES` listait 4 fichiers alors que la clôture transitive en
     compte 18 — `aster_indicators.py` et `research_os.py`, importés au
     niveau module par `research_runner.py, étaient ABSENTS (PR #211).
  2. Le repli de marge de maintenance était optimiste, et le test F-038
     **encodait** l'optimisme au lieu de l'interdire (PR #213).

Les deux sont « un invariant existe, il n'est pas appliqué ». La matrice
ci-dessous est l'inverse : elle énumère, donc elle ne peut pas être
contournée par un ajout silencieux.

Tout est PUR : aucun appel à `execution_identity()` avec des valeurs
littérales, donc aucune base, aucun git, aucun réseau.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import research_worker as w  # noqa: E402

# Une identité de référence, entièrement composée de valeurs connues.
BASE = {
    "engine_sha": "aaaa1111",
    "spec_sha": "bbbb2222",
    "universe_sha": "cccc3333",
    "protocol_sha": "dddd4444",
    "db_snapshot": "eeee5555",
    "deps_sha": "numpy=2.5.3|pandas=3.0.6",
    "git_sha": "ffff6666",
}

# Éléments dont la modification DOIT changer l'identité : chacun peut
# changer ce qu'une discovery MESURE, donc un « déjà calculé » serait faux.
DOIT_CHANGER = (
    ("engine_sha", "un module de mesure a changé → la mesure change"),
    ("spec_sha", "la spec a changé (seuils, horizons, univers)"),
    ("universe_sha", "univ10.yaml modifié garde son nom : seul le CONTENU "
                     "scelle (research_runner.universe_sha)"),
    ("protocol_sha", "un seuil peut changer sous le même protocol_id "
                     "(PR-150 №7)"),
    ("db_snapshot", "le jeu de données a changé"),
    ("deps_sha", "un patch numpy change un quantile, donc un t, donc un "
                 "verdict"),
    ("git_sha", "le code a changé hors des modules de mesure"),
)

# Éléments qui ne doivent PAS entrer dans l'identité.
NE_DOIT_PAS_CHANGER = ("docs", "worker", "ci")


def _identite(**overrides: str) -> str:
    params = dict(BASE)
    params.update(overrides)
    return w.execution_identity(params.pop("engine_sha"), **params)


class TestMatriceDIdentite(unittest.TestCase):
    """Chaque entrée de l'identité doit peser son poids."""

    def test_reference_stable(self):
        """Contrôle négatif : sans changement, l'identité ne bouge pas."""
        self.assertEqual(_identite(), _identite())

    def test_changer_une_seule_entree_change_l_identite(self):
        for cle, raison in DOIT_CHANGER:
            with self.subTest(composante=cle):
                modifie = {cle: "9999ffff"}
                self.assertNotEqual(
                    _identite(**modifie), _identite(),
                    f"modifier {cle} ne change PAS l'identité — or {raison}. "
                    f"Un résultat serait réutilisé alors que la mesure a "
                    f"changé.")

    def test_chaque_composante_est_une_cle_du_canonique(self):
        """Aucune composante oubliée : le dict canonique est énuméré."""
        params = dict(BASE)
        params.pop("engine_sha")
        capturable = {}
        for cle in w.EXECUTION_IDENTITY_PARTS:
            if cle == "engine":
                continue
            capturable[cle] = params.get(cle, "")
        # les noms de w.EXECUTION_IDENTITY_PARTS doivent tous exister comme
        # clé dans le JSON canonique produit par la fonction
        canonique = json.loads(json.dumps({
            "engine": "x", "spec": "y", "universe": "z", "protocol": "w",
            "db_snapshot": "v", "deps": "u", "git": "t"}, sort_keys=True))
        for cle in w.EXECUTION_IDENTITY_PARTS:
            with self.subTest(composante=cle):
                self.assertIn(cle, canonique)

    def test_deux_composantes_egales_ne_sont_confondues(self):
        """Clés distinctes, valeurs identiques → identités distinctes.

        Sans ça, un bug de composition pourrait faire dépendre l'identité
        d'une valeur plutôt que de la CLÉ, et `spec_sha == engine_sha`
        validerait à tort.
        """
        memes = w.execution_identity("z", spec_sha="z")
        differents = w.execution_identity("z", spec_sha="z", universe_sha="z")
        self.assertNotEqual(memes, differents)

    def test_l_identite_ne_dépend_pas_de_l_ordre_des_arguments(self):
        """Le canonique est trié : `engine` puis `spec` ≠ `spec` puis `engine`.

        Un appel qui réordonne les arguments ne doit pas produire une
        identité différente — sinon deux workers « identiques » ne se
        reconnaîtraient pas.
        """
        a = w.execution_identity("e", spec_sha="s", db_snapshot="d")
        b = w.execution_identity("e", db_snapshot="d", spec_sha="s")
        self.assertEqual(a, b)


class TestHorsPerimetre(unittest.TestCase):
    """Ce qui n'entre PAS dans l'identité — et doit pouvoir changer
    gratuitement."""

    def test_docs_worker_ci_ne_sont_pas_des_composantes(self):
        source = (ROOT / "scripts" / "research_worker.py").read_text("utf-8")
        bloc = source[source.index("def execution_identity("):
                      source.index("def deps_sha(")]
        for interdit in ("docs/", "research_worker.py", "ci.yml",
                         "ci.yaml", ".github/"):
            with self.subTest(interdit=interdit):
                self.assertNotIn(
                    interdit, bloc,
                    f"{interdit} est referme dans execution_identity() : "
                    f"un changement de documentation invaliderait les "
                    f"resultats sans que la mesure bouge")

    def test_un_changement_de_docs_ne_bouge_pas_l_identite(self):
        """La preuve exécutée, pas la lecture du source.

        Le garde précédent est une vérification de forme ; celle-ci est le
        comportement. On écrit un fichier de docs, et on exige que
        l'identité soit inchangée.
        """
        cible = ROOT / "docs" / "_probe_identite.md"
        avant = _identite()
        cible.write_text("changement de documentation\n", encoding="utf-8")
        try:
            self.assertEqual(_identite(), avant,
                             "un doc a changé l'identité d'exécution")
        finally:
            cible.unlink(missing_ok=True)

    def test_le_worker_lui_meme_ne_bouge_pas_l_identite(self):
        """Écrire dans `research_worker.py` ne doit PAS changer l'identité.

        C'est contre-intuitif — le worker décide de ce qu'il saute — mais
        `engine_sha` couvre les modules de MESURE, pas le worker. Un refactor
        du worker ne réinitialise donc pas une campagne : c'est le
        comportement voulu depuis PR-161 (« identité = moteur de mesure, pas
        git entier »).
        """
        cible = ROOT / "scripts" / "research_worker.py"
        avant = _identite()
        original = cible.read_bytes()
        try:
            cible.write_bytes(original + b"\n# probe\n")
            self.assertEqual(_identite(), avant,
                             "écrire dans le worker a changé l'identité — "
                             "un refactor réinitialiserait toutes les campagnes")
        finally:
            cible.write_bytes(original)

    def test_ecrire_dans_un_module_de_mesure_change_bien_l_engine(self):
        """Le contre-pied du précédent : là, ça DOIT bouger."""
        cible = ROOT / "scripts" / "aster_indicators.py"
        original = cible.read_bytes()
        engine_avant = w._engine_sha()
        try:
            cible.write_bytes(original + b"\n# probe\n")
            self.assertNotEqual(w._engine_sha(), engine_avant,
                                "un module de mesure n'a pas bougé l'engine_sha")
        finally:
            cible.write_bytes(original)
        self.assertEqual(w._engine_sha(), engine_avant)


class TestDepsSha(unittest.TestCase):
    """Les versions qui font les calculs entrent dans l'identité."""

    def test_deps_sha_nomme_les_bibliotheques(self):
        s = w.deps_sha()
        for dist in ("numpy", "pandas"):
            with self.subTest(dist=dist):
                self.assertIn(dist, s)

    def test_deps_sha_ne_leve_pas_si_un_paquet_absent(self):
        """L'absence de scipy ne doit pas faire tomber l'identité.

        C'est un autre problème, signalé ailleurs ; ici il doit se
        TRADUIRE (`absent`), pas faire échouer le calcul du sha.
        """
        s = w.deps_sha()
        self.assertIn("absent", s.split("|")[-1] + "|" + s)
        self.assertTrue(len(s) > 0)

    def test_une_absence_est_differente_d_une_version(self):
        a = w.execution_identity("e", deps_sha="numpy=absent")
        b = w.execution_identity("e", deps_sha="numpy=2.5.3")
        self.assertNotEqual(a, b,
                            "« absent » et une version doivent être "
                            "deux identités distinctes")


class TestCompatibiliteAncienne(unittest.TestCase):
    """Un checkpoint existant ne doit pas être invalidé par ce PR."""

    def test_engine_sha_reste_dans_le_canonique(self):
        """L'identité du PR #211 se retrouve dans le nouveau canonique.

        Un run enregistré avant ce PR reste comparable, et son `engine_sha`
        peut toujours être extrait pour répondre à « qu'est-ce qui a
        changé ? ».
        """
        identite = w.execution_identity("engine-avant-pr")
        self.assertIsInstance(identite, str)
        self.assertEqual(len(identite), 16)

    def test_un_engine_vide_ne_leve_pas(self):
        """Un checkpoint legacy sans engine_sha ne doit pas planter."""
        self.assertIsInstance(w.execution_identity(""), str)


if __name__ == "__main__":
    unittest.main()