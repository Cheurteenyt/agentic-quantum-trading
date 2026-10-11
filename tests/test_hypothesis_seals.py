from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def const(script: str, name: str) -> str:
    m = re.search(rf'^{name}\s*=\s*"([0-9a-f]{{64}})"', (ROOT / script).read_text(encoding="utf-8"), re.M)
    assert m, f"{name} introuvable dans {script}"
    return m.group(1)


class SealTests(unittest.TestCase):
    """Un pré-enregistrement scellé ne change plus : on AMENDE PAR AJOUT (fichier séparé, scellé à part)."""

    def test_crowding_composite_seals(self):
        s = "scripts/crowding_composite.py"
        self.assertEqual(sha(ROOT / "docs/lab/hypotheses/crowding-composite.md"), const(s, "EXPECTED_SEAL"),
                         "l'hypothèse scellée a été modifiée : le script refuserait de tourner (exit 2)")
        self.assertEqual(sha(ROOT / "docs/lab/hypotheses/crowding-composite.amendments.md"), const(s, "EXPECTED_AMEND_SEAL"))


# --- Le gel d'une spec est un ÉTAT, pas une intention (audit Sonnet 5.5, R1) ---------------
#
# Défaut trouvé : `research/hypotheses/holdout-x.md` portait
#   « Hash du gel : <à committer avant le run> »
# là où `w42-reconstruction.md` porte un vrai sha (`12465ab`). Autrement dit : une spec qui
# AFFIRME avoir un gel sans en avoir un — un placeholder qui se lit comme une consigne, pas
# comme un manque. C'est la classe d'audit de ce dépôt : « je n'ai pas gelé » ne doit pas
# pouvoir se lire « tout va bien ».
#
# ⚠️ Le verrou vise la FORME DÉCLARÉE, pas l'absence de gel :
#   - une spec qui DÉCLARE un gel (`Hash … :`) doit porter un vrai sha ;
#   - une spec sans ligne de gel est un STUB honnête (ex. `liq-echo.md` : forward-only,
#     jugée à n≥30 mi-nov, aucun moteur à geler) → tolérée ;
#   - `crowding-composite` est gelée par sha256 dans le script (F3 + SealTests) → hors champ.
# Flaguer les 6 stubs aurait été le même piège que `grep "import pyflakes"` (compter un
# commentaire comme un garde, journal du 11/10) : sur-compter, ce n'est pas verrouiller.

HYP_DIRS = ("research/hypotheses", "docs/lab/hypotheses")
TEMPLATE = "research/hypotheses/_TEMPLATE.md"

SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")          # sha de commit (court ou long)
PLACEHOLDER_RE = re.compile(r"<[^>\n]*>")           # <commit>, <sha>, <à committer…>
DECLARE_RE = re.compile(r"^\s*Hash\b", re.M)        # la spec AFFIRME un gel
# Spec gelée par un autre mécanisme (sha256 dans le script, vérifié par SealTests/F3).
HORS_CHAMP = {"crowding-composite.md", "crowding-composite.amendments.md"}


def _spec_files() -> list[Path]:
    out: list[Path] = []
    for d in HYP_DIRS:
        p = ROOT / d
        if p.is_dir():
            out += [f for f in sorted(p.glob("*.md"))
                    if f.name not in ("README.md", "_TEMPLATE.md") and f.name not in HORS_CHAMP]
    return out


class LeGelDEstPasUneIntention(unittest.TestCase):
    """Une spec qui déclare un gel doit porter un sha réel — jamais un `<…>`."""

    def test_le_template_exige_un_sha_dans_la_ligne_de_gel(self):
        """Ancrage : si le template cesse d'exiger un sha, ce verrou n'a plus de sens."""
        txt = (ROOT / TEMPLATE).read_text(encoding="utf-8")
        ligne = [l for l in txt.splitlines() if re.match(r"\s*Hash\b", l)]
        self.assertTrue(ligne, "le template ne porte plus de ligne « Hash … »")
        self.assertRegex(ligne[0], r"sha", "le template n'exige plus un sha (l'invariant a changé)")

    def test_toute_spec_qui_declare_un_gel_porte_un_sha(self):
        """Le défaut d'origine : `<à committer avant le run>` se lit comme une consigne."""
        fautives = []
        for f in _spec_files():
            txt = f.read_text(encoding="utf-8")
            if not DECLARE_RE.search(txt):
                continue  # stub sans gel déclaré : forward-only ou exploratoire, toléré
            gel = [l for l in txt.splitlines() if re.match(r"\s*Hash\b", l)]
            l = gel[0]
            if PLACEHOLDER_RE.search(l) and not SHA_RE.search(l):
                fautives.append(f"{f.relative_to(ROOT)} : {l.strip()!r}")
        self.assertEqual(fautives, [],
                         "une spec qui déclare un gel doit porter un sha de commit réel "
                         "(ou supprimer la ligne si elle n'est pas encore gelable)")

    def test_au_moins_une_spec_est_gelée_pour_de_vrai(self):
        """Mémoire de l'invariant : le mécanisme n'est pas théorique, il a un précédent."""
        geles = []
        for f in _spec_files():
            txt = f.read_text(encoding="utf-8")
            for l in txt.splitlines():
                if re.match(r"\s*Hash\b", l) and SHA_RE.search(l) and not PLACEHOLDER_RE.search(l):
                    geles.append(f.name)
        self.assertTrue(geles, "aucune spec n'est gelée par un sha réel — l'invariant est vide")

    # --- mutations : prouvent que le verrou rougit sur le défaut réel ---------------------

    def test_mutation_un_placeholder_est_bien_detecte(self):
        l = "Hash du gel : <à committer avant le run> · Jugé sous : protocol_v2"
        self.assertTrue(PLACEHOLDER_RE.search(l) and not SHA_RE.search(l))

    def test_mutation_un_sha_est_accepte(self):
        l = "Hash du gel : 12465ab — protocol-v1"
        self.assertFalse(PLACEHOLDER_RE.search(l) and not SHA_RE.search(l))

    def test_mutation_un_stub_sans_ligne_est_tolere(self):
        self.assertFalse(DECLARE_RE.search("# INV-C — l'Écho de Liquidation\nFORWARD-ONLY.\n"))


if __name__ == "__main__":
    unittest.main()
