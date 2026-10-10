#!/usr/bin/env python3
"""Le filtre `core` de la CI doit couvrir tout ce que le gate ANALYSE.

Défaut trouvé le 10/10 : le job `t1-core` lance

    python -m pyflakes scripts backend discord_bot agent tests

et `t1-security` lance

    bandit -r backend discord_bot scripts

mais le filtre de chemins ne déclenchait `core` que sur
`scripts/** backend/** tests/** research/**` + les requirements. `discord_bot/**`
(22 fichiers .py) et `agent/**` (4 .py) en étaient ABSENTS.

Conséquence : une PR qui ne touchait QUE `discord_bot/` ou `agent/` était classée
`core=false`. `t1-core` et `t1-security` sortaient `skipped`, le job `gate`
traite `skipped` comme neutre (c'est voulu, pour ne pas exiger la suite Python
sur une PR docs-only) → **aucun palier ne tournait**, et un `undefined name`
dans ces 26 fichiers partait en production sans être vu, alors que le gate
AURAIT su le voir.

Prouvé par mutation : injecter `return DOES_NOT_EXIST_XYZ` dans
`discord_bot/bot.py` fait bien rougir le pyflakes du gate (mesuré). Le trou
n'était donc pas la détection, mais le DÉCLENCHEMENT.

Ce test verrouille l'équivalence entre :
  - le scope de chemins RÉELLEMENT analysé par les steps du workflow, et
  - les motifs du filtre `core`.

La leçon générale (celle du `t1-security` non déclenché par `.github/**`) :
un filtre de chemins est un contrat sur qui juge quoi. S'il est plus étroit
que ce que le gate regarde, il ne dit pas « je n'ai pas tourné » — le palier
disparaît. Le remède est de DÉRIVER le filtre du scope, pas de le maintenir
à la main, et de tester l'équivalence.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CI = ROOT / ".github" / "workflows" / "ci.yml"


def _filtres() -> dict[str, list[str]]:
    """Les motifs du filtre `core`/`ci`/`frontend`/`docs`, lus dans le YAML.

    On lit le YAML plutôt que de regexer le texte : le bloc `filters: |` est
    un scalaire littéral, et une lecture naïve attraperait les commentaires.
    PyYAML n'est pas une dépendance du projet : on l'importe ici, et si le
    module manque on lit à la main (repli testé plus bas).
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover - repli hors CI
        return _filtres_manuel()
    doc = yaml.safe_load(CI.read_text(encoding="utf-8"))
    for step in doc["jobs"]["changes"]["steps"]:
        if "filters" in (step.get("with") or {}):
            return _parser_bloc(step["with"]["filters"])
    raise AssertionError("pas de bloc `filters:` dans le job `changes`")


def _parser_bloc(bloc: str) -> dict[str, list[str]]:
    """Parse le scalaire littéral `filters: |` en {filtre: [motifs]}.

    Tolérant à l'INDENTATION, et c'est nécessaire : le bloc obtenu via
    `yaml.safe_load` est DÉ-INDENTÉ (un scalaire littéral perd son
    indentation commune), alors que celui lu à la main ne l'est pas (12
    espaces). Sans ce `strip`, le repli sans PyYAML rendait `{}` en silence —
    un parseur qui ne trouve rien et ne le dit pas, exactement le défaut que
    ce fichier de tests combat.

    On `lstrip` donc chaque ligne. Le bloc est PLAT (une clé `nom:`, puis des
    items `- 'motif'`) : il n'y a aucune imbrication à préserver.
    """
    out: dict[str, list[str]] = {}
    courant: str | None = None
    for ligne in bloc.splitlines():
        l = ligne.strip()
        if not l or l.startswith("#"):
            continue
        m = re.match(r"^(\w+):$", l)
        if m:
            courant = m.group(1)
            out[courant] = []
            continue
        m = re.match(r"^-\s*'([^']+)'$", l)
        if m and courant:
            out[courant].append(m.group(1))
    return out


def _filtres_manuel() -> dict[str, list[str]]:  # pragma: no cover - repli
    """Repli sans PyYAML : extrait le scalaire `filters: |` et s'ARRÊTE à la
    fin du bloc.

    Sans cette borne, on avalait tout le reste du workflow et `_parser_bloc`
    ramassait `gate:`, `run:`, `steps:`, `with:` — un filtre pollué de clés
    qui ne sont pas des filtres. La borne est l'indentation : le bloc est
    plus indenté que la clé `filters:`, et se termine dès qu'une ligne non
    vide redescend à ce niveau ou en dessous.
    """
    lignes = CI.read_text(encoding="utf-8").splitlines()
    debut = None
    for i, l in enumerate(lignes):
        if l.strip() == "filters: |":
            debut = i + 1
            break
    if debut is None:
        raise AssertionError("bloc `filters: |` introuvable dans le workflow")
    cle = lignes[debut - 1]
    ind_cle = len(cle) - len(cle.lstrip())
    bloc: list[str] = []
    for l in lignes[debut:]:
        if not l.strip():
            continue
        if (len(l) - len(l.lstrip())) <= ind_cle:
            break
        bloc.append(l)
    return _parser_bloc("\n".join(bloc))


class TestFiltreCoreCouvreLeScope(unittest.TestCase):
    """Le filtre `core` ⊇ le scope des steps qui l'exigent."""

    def setUp(self):
        self.f = _filtres()
        self.src = CI.read_text(encoding="utf-8")

    def test_le_parser_lit_bien_les_quatre_filtres(self):
        """Garde-fou du test lui-même : si le parseur casse, tout le reste
        passerait à vide et ne vérifierait plus rien."""
        for nom in ("core", "frontend", "docs", "ci"):
            self.assertIn(nom, self.f, f"filtre {nom} introuvable")
            self.assertTrue(self.f[nom], f"filtre {nom} vide")

    def test_les_racines_du_scope_pyflakes_sont_dans_core(self):
        """`pyflakes scripts backend discord_bot agent tests` (step BLOQUANT).

        On extrait les racines du VRAI texte du workflow — pas une constante
        recopiée ici, sinon le test vérifierait sa propre copie.
        """
        m = re.search(r"pyflakes\s+([\w\s]+?)\s*\|", self.src)
        self.assertIsNotNone(m, "ligne pyflakes introuvable dans le workflow")
        racines = m.group(1).split()
        self.assertIn("discord_bot", racines,
                      "le workflow ne pyflakes plus discord_bot : le test "
                      "ci-dessous doit être requalifié")
        self.assertIn("agent", racines)
        for r in racines:
            if r in ("tests",):
                continue  # `tests/**` est déjà dans core, vérifié plus bas
            self.assertIn(
                f"{r}/**", self.f["core"],
                f"le gate pyflakes analyse `{r}` mais `core` ne le déclenche "
                f"pas : une PR {r}-only serait `skipped` et le défaut passerait")

    def test_les_racines_du_scope_bandit_sont_dans_core(self):
        """`bandit -r backend discord_bot scripts` (les 2 steps T1-security)."""
        m = re.search(r"bandit\s+-q\s+-ll\s+-r\s+([\w\s]+?)\s+-t", self.src)
        self.assertIsNotNone(m, "commande bandit ciblée introuvable")
        for r in m.group(1).split():
            self.assertIn(
                f"{r}/**", self.f["core"],
                f"bandit analyse `{r}` mais `core` ne le déclenche pas")

    def test_tests_et_backend_et_scripts_et_research_sont_dans_core(self):
        for r in ("scripts", "backend", "tests", "research"):
            self.assertIn(f"{r}/**", self.f["core"], r)

    def test_les_gardes_hors_github_sont_dans_le_filtre_ci(self):
        """`.gitleaks.toml` gouverne le scan de secrets ; `start_all.sh` est
        l'entrée d'exécution. Aucun autre filtre ne les couvre : s'ils
        manquaient ici, une PR qui les modifie ne déclencherait rien."""
        self.assertIn(".gitleaks.toml", self.f["ci"])
        self.assertIn("start_all.sh", self.f["ci"])
        self.assertIn(".github/**", self.f["ci"])


class TestFiltreCoreEstLePlusLarge(unittest.TestCase):
    """Un fichier du scope ne doit pas tomber dans un filtre PLUS FAIBLE.

    Le piège n'est pas seulement l'absence : un fichier classé ONLY `docs`
    pour un step `core` ferait aussi sauter le palier (une PR mixte
    `discord_bot/ + docs/` resterait déclenchée par discord_bot, mais
    l'intention « docs-only ne relance pas Python » ne doit pas avaler du
    code de noyau).
    """

    def setUp(self):
        self.f = _filtres()

    def test_aucune_racine_de_noyau_n_est_absente(self):
        for r in ("scripts", "backend", "tests", "discord_bot", "agent",
                  "research"):
            self.assertIn(f"{r}/**", self.f["core"], r)

    def test_les_requirements_et_pyproject_sont_dans_core(self):
        """Ils changent les dépendances donc le comportement du gate."""
        for m in ("pyproject.toml", "requirements*.txt", "requirements.lock"):
            self.assertIn(m, self.f["core"], m)


class TestRegression1009(unittest.TestCase):
    """Le cas exact du défaut, épinglé nommément.

    Si quelqu'un retire `discord_bot/**` ou `agent/**` de `core` en croyant
    simplifier, ce test dit pourquoi c'est faux — et renvoie à la mesure.
    """

    def setUp(self):
        self.f = _filtres()

    def test_discord_bot_dans_core(self):
        self.assertIn("discord_bot/**", self.f["core"],
                      "discord_bot est pyflakes+bandit par le gate ; sans "
                      "cette entrée, une PR discord_bot-only ne déclenche "
                      "AUCUN palier (défaut mesuré le 10/10)")

    def test_agent_dans_core(self):
        self.assertIn("agent/**", self.f["core"],
                      "agent est pyflakes par le gate ; même trou que "
                      "discord_bot")

    def test_les_dossiers_invoques_existent_vraiment(self):
        """Un motif de filtre pointant un dossier disparu serait un faux
        sentiment de couverture."""
        for r in ("discord_bot", "agent"):
            self.assertTrue((ROOT / r).is_dir(), f"{r}/ n'existe pas")
            self.assertTrue(list((ROOT / r).rglob("*.py")),
                            f"{r}/ n'a aucun .py — requalifier le filtre")


class TestLeRepliSansPyYAMLEstFidele(unittest.TestCase):
    """Les DEUX chemins de lecture doivent rendre le MÊME filtre.

    Le premier jet de ce fichier avait un repli manuel qui rendait `{}` : il
    lisait le bloc brut (indenté de 12 espaces) avec une regex exigeant la
    colonne 0. Un parseur qui ne trouve rien et rend un dict VIDE sans rien
    dire, c'est précisément le fail-open que ce dépôt combat — le test
    ci-dessous l'aurait attrapé.
    """

    def test_parser_indente_et_non_indentee_donnent_le_meme(self):
        indentee = "          filters: |\n            core:\n" \
                   "              - 'scripts/**'\n" \
                   "              - 'discord_bot/**'\n" \
                   "            ci:\n              - '.github/**'\n"
        non_indentee = "filters: |\ncore:\n  - 'scripts/**'\n" \
                       "  - 'discord_bot/**'\nci:\n  - '.github/**'\n"
        a = _parser_bloc(indentee)
        b = _parser_bloc(non_indentee)
        self.assertEqual(a, b)
        self.assertEqual(a["core"], ["scripts/**", "discord_bot/**"])
        self.assertEqual(a["ci"], [".github/**"])

    def test_le_repli_manuel_lit_le_vrai_workflow(self):
        """Le repli (sans PyYAML) doit rendre le MÊME filtre que PyYAML."""
        attendu = _filtres()  # via PyYAML si dispo, sinon le repli
        obtenu = _filtres_manuel()
        self.assertEqual(obtenu, attendu)
        self.assertTrue(obtenu.get("core"),
                        "le repli a rendu un filtre core VIDE — il n'a rien "
                        "mesuré, ce qui est pire qu'une erreur")
        self.assertIn("discord_bot/**", obtenu["core"])

    def test_un_parseur_qui_ne_trouve_rien_le_dit(self):
        """Contrat : le bloc vide rend un dict vide, pas une exception muette.
        Ce qui compte est que le TEST au-dessus exige un `core` non vide —
        un `{}` ne peut pas passer pour un succès."""
        self.assertEqual(_parser_bloc(""), {})
        self.assertEqual(_parser_bloc("aucune cle ici"), {})


if __name__ == "__main__":
    unittest.main()
