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

import json
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


LEDGER = ROOT / "research" / "evidence" / "facts.jsonl"


def _couvert(path: str, patterns: list[str]) -> bool:
    """Le chemin est-il couvert par un motif `dir/**`, ou listé exactement ?

    Volontairement MINIMAL : on n'imite pas picomatch (dont la sémantique de
    `**`/`*` est subtile et versionnée). On vérifie la seule propriété qui
    compte — ce chemin déclenche-t-il `core` ou `ci` ? Les deux formes
    utilisées dans le workflow sont `dir/**` (préfixe) et le fichier exact.

    Ce matcher est plus STRICT que picomatch : un motif à joker comme
    `requirements*.txt` ne matchera pas `requirements.txt` ici. C'est voulu —
    l'erreur va dans le sens sûr (exiger une entrée explicite), jamais dans
    le sens « couvert à tort ».
    """
    for p in patterns:
        if p.endswith("/**"):
            prefix = p[:-3]
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif p == path:
            return True
    return False


def _chemins_du_ledger() -> list[tuple[str, str]]:
    """(id, chemin) de chaque fait du ledger qui déclare une preuve."""
    if not LEDGER.exists():
        raise AssertionError(f"ledger introuvable : {LEDGER}")
    out: list[tuple[str, str]] = []
    for ligne in LEDGER.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne:
            continue
        fait = json.loads(ligne)
        p = fait.get("path")
        if p:
            out.append((fait.get("id", "?"), p))
    if not out:
        raise AssertionError("ledger vide — le test ne mesurerait rien")
    return out


class TestLesPreuvesDuLedgerDeclenchentLeGate(unittest.TestCase):
    """Tout fichier de preuve du ledger doit déclencher `t1-core`.

    `claim_verify.py` (step BLOQUANT de t1-core) relit chaque fait de
    `research/evidence/facts.jsonl` contre son fichier de preuve. Ce fichier
    peut vivre N'IMPORTE OÙ — deux d'entre eux étaient hors de `core` :
    `docs/21-vagues-registre.md` (F-033/F-034/F-035) et
    `reports/al-gradient-reproof-2026-10-07.md` (F-037).

    Mesuré : retirer `Décision requise` du rapport F-037 fait passer
    `claim_verify` à `41/42 SUPPORTED — LE LEDGER EST CONTREDIT`. Comme le
    fichier est un `.md`, une telle PR était classée `docs`-only, `t1-core`
    sortait `skipped`, et la contradiction partait sur `main` sans être vue.

    Ce test DÉRIVE les chemins du ledger : ajouter un fait qui pointe un
    nouveau fichier force à élargir le filtre — sinon il rougit ici.
    """

    def setUp(self):
        self.f = _filtres()

    def test_le_ledger_est_lisible(self):
        faits = _chemins_du_ledger()
        self.assertGreater(len(faits), 10,
                           "ledger suspicieusement court — parse cassé ?")

    def test_chaque_preuve_declenche_un_palier(self):
        declencheurs = self.f["core"] + self.f["ci"]
        manquants = []
        for fid, path in _chemins_du_ledger():
            if not _couvert(path, declencheurs):
                manquants.append(f"{fid} -> {path}")
        self.assertEqual(
            manquants, [],
            "ces preuves du ledger ne déclenchent AUCUN palier : modifier le "
            "fichier casserait claim_verify sans que la CI s'en aperçoive.\n"
            "  " + "\n  ".join(manquants) +
            "\n→ ajoute-les au filtre `core` de .github/workflows/ci.yml")

    def test_les_deux_cas_mesures_sont_couverts(self):
        """Épingle nommément les deux chemins du défaut du 10/10."""
        declencheurs = self.f["core"] + self.f["ci"]
        for p in ("docs/21-vagues-registre.md",
                  "reports/al-gradient-reproof-2026-10-07.md"):
            self.assertTrue(_couvert(p, declencheurs),
                            f"{p} doit déclencher t1-core (preuve du ledger)")

    def test_le_matcher_lui_meme_est_testable(self):
        """Garde-fou : si `_couvert` se trompait, tout ce qui précède
        passerait pour de mauvaises raisons."""
        self.assertTrue(_couvert("scripts/a.py", ["scripts/**"]))
        self.assertTrue(_couvert("scripts/deep/b.py", ["scripts/**"]))
        self.assertFalse(_couvert("scriptsX/a.py", ["scripts/**"]))
        self.assertTrue(_couvert("docs/x.md", ["docs/x.md"]))
        self.assertFalse(_couvert("docs/y.md", ["docs/x.md"]))
        self.assertFalse(_couvert("reports/x.md", ["scripts/**"]))


class TestLesEntreesDesOraclesDeclenchentLeGate(unittest.TestCase):
    """Tout fichier LU par un oracle doit déclencher `t1-core`.

    `audit_check.py` (step BLOQUANT) ne fait pas que lire le code : il LIT des
    fichiers de configuration et de documentation, et rougit s'ils changent.
    Mesuré :
      - retirer `lab_ledger.py` de `.zcode/agents/quant-researcher.md`
        -> contrôle A4 ROUGE ;
      - retirer une famille du `docs/lab/mortuary.md` -> contrôle C1 ROUGE.
    Aucun de ces fichiers n'était dans `core` : une PR qui les modifie sortait
    `skipped`, et la CI ne voyait rien.

    Ce test DÉRIVE les entrées : il extrait les littéraux de chemin des scripts
    d'oracle, ne garde que ceux qui EXISTENT réellement (ce qui écarte les
    artefacts de regex comme `data/...`), et exige que chacun soit couvert.
    Ajouter un `ROOT / "nouveau/fichier"` dans un oracle fait donc rougir ici
    tant que le filtre n'est pas élargi.
    """

    ORACLES = (
        "claim_verify.py", "audit_check.py", "deep_audit.py",
        "research_integrity.py", "ledger_provenance.py",
        "ledger_puissance.py", "audit_path_root.py",
    )
    # Littéraux de chemin : un dossier de 1er niveau connu, puis la suite.
    MOTIF = re.compile(
        r"""["']((?:docs|research|scripts|tests|backend|frontend|discord_bot"""
        r"""|agent|reports|\.zcode|\.github|configs|deploy|data|rag|archives"""
        r"""|integrations)/[^"'\n]*?)["']""")

    def setUp(self):
        self.f = _filtres()

    def _litteraux_reels(self) -> dict[str, set[str]]:
        """{chemin: {oracles}} — seulement les chemins qui EXISTENT.

        Le filtre d'existence est ce qui rend la dérivation exploitable : il
        élimine les faux positifs (motifs de regex, chaînes d'affichage) sans
        exiger une liste blanche à maintenir.
        """
        import subprocess
        tracked = set(subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True,
            text=True, check=True).stdout.split("\n"))
        out: dict[str, set[str]] = {}
        for oracle in self.ORACLES:
            p = ROOT / "scripts" / oracle
            if not p.exists():
                continue
            for m in self.MOTIF.finditer(p.read_text(encoding="utf-8",
                                                    errors="replace")):
                lit = m.group(1)
                prefixe = lit.rstrip("/") + "/"
                existe = (ROOT / lit).exists() or any(
                    t.startswith(prefixe) for t in tracked)
                if existe:
                    out.setdefault(lit, set()).add(oracle)
        return out

    def test_la_derivation_trouve_quelque_chose(self):
        """Si l'extraction casse, les tests suivants passeraient à vide."""
        lits = self._litteraux_reels()
        self.assertGreater(len(lits), 8,
                           "extraction suspicieusement pauvre — motif cassé ?")

    def test_chaque_entree_d_oracle_declenche_un_palier(self):
        declencheurs = self.f["core"] + self.f["ci"]
        manquants = [f"{p} <- {','.join(sorted(o))}"
                     for p, o in sorted(self._litteraux_reels().items())
                     if not _couvert(p, declencheurs)]
        self.assertEqual(
            manquants, [],
            "ces fichiers sont LUS par un oracle mais ne déclenchent AUCUN "
            "palier : les modifier casserait le gate en silence.\n  " +
            "\n  ".join(manquants) +
            "\n→ ajoute-les au filtre `core` de .github/workflows/ci.yml")

    def test_les_cas_mesures_du_10_10_sont_couverts(self):
        declencheurs = self.f["core"] + self.f["ci"]
        for p in (".zcode/agents/quant-researcher.md",
                  "docs/lab/mortuary.md",
                  "configs/systemd-user/trading-agent-nightly.service"):
            self.assertTrue(_couvert(p, declencheurs),
                            f"{p} est lu par audit_check -> doit être en core")


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
