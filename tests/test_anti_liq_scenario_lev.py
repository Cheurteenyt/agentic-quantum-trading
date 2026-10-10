"""Issue #201 (C-B2) — le label pnl et le seuil de liquidation doivent
décrire LA MÊME position.

Le levier de scénario apparaissait **4 fois en clair** dans `anti_liq.py`
(frais, funding, pnl, `liq_move_for`) : `ret * 20`, `... * 20`, `... * 20`,
`liq_move_for(sym, 20)`. Si l'un changeait sans les autres, le label de
liquidation et le pnl cesseraient de décrire la même position — silencieusement,
et la mesure de risque n'aurait plus de sens.

Deux verrous :
  1. une constante unique `SCENARIO_LEV` (test source : plus aucun littéral 20
     dans les expressions du label) ;
  2. l'égalité label/seuil à l'exécution.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.anti_liq as anti_liq  # noqa: E402
from scripts.portfolio_sim import liq_move_for  # noqa: E402


class ScenarioLevSingleSourceTests(unittest.TestCase):
    def test_constante_existe_et_vaut_20(self) -> None:
        self.assertEqual(anti_liq.SCENARIO_LEV, 20)

    def test_le_litteral_20_ne_revient_pas_dans_le_label(self) -> None:
        """Le verrou anti-régression : les expressions du label utilisent la
        constante, pas un 20 codé en dur. On lit la SOURCE — un test de valeur
        ne le verrait pas, puisque 20 == SCENARIO_LEV aujourd'hui."""
        src = (ROOT / "scripts" / "anti_liq.py").read_text(encoding="utf-8")
        # les motifs fautifs d'origine, à interdire tant que SCENARIO_LEV vaut 20
        interdits = [
            r"fees_pct\s*=\s*\(FEE_BPS \+ SLIP_BPS\) \* 2 \* 20\b",
            r"fund_pct\s*=\s*fund_h \* HOLD_H \* 20\b",
            r"pnl_pct\s*=\s*ret \* 20\b",
            r"liq_move_for\(sym, 20\)",
        ]
        for pat in interdits:
            self.assertIsNone(
                re.search(pat, src),
                f"littéral 20 revenu dans le label (#201) : /{pat}/")

    def test_le_label_et_le_seuil_partagent_la_constante(self) -> None:
        src = (ROOT / "scripts" / "anti_liq.py").read_text(encoding="utf-8")
        self.assertIn("ret * SCENARIO_LEV", src)
        self.assertIn("liq_move_for(sym, SCENARIO_LEV)", src)


class LabelEtSeuilCoherentsTests(unittest.TestCase):
    def test_pnl_et_liquidation_au_meme_levier(self) -> None:
        """Sur un major (mm = 2,5 %), à 20x : pnl = ret*20, et le seuil de
        liquidation vaut 100/20 − 2,5 = 2,5 %. Donc un mouvement de −2,5 %
        met le pnl à −50 % ET franchit le seuil : les deux racontent la même
        position."""
        lev = anti_liq.SCENARIO_LEV
        seuil = liq_move_for("BTCUSDT", lev)
        self.assertAlmostEqual(seuil, 100 / lev - 2.5, places=9)
        ret = -seuil
        self.assertAlmostEqual(ret * lev, -50.0, places=9)

    def test_le_seuil_ne_depend_pas_du_levier_du_label(self) -> None:
        """Le `100/L` dépend du levier (c'est la distance de liquidation de la
        position), mais la marge de maintien vient du SYMBOLE, pas du levier.
        Deux symboles de mm différents à même levier ont des seuils distincts —
        c'est le cœur de F-038."""
        lev = anti_liq.SCENARIO_LEV
        major = liq_move_for("BTCUSDT", lev)       # mm 2,5 %
        memecoin = liq_move_for("INCONNUUSDT", lev)  # repli prudent (mm plus haut)
        self.assertNotAlmostEqual(major, memecoin, places=6)

    def test_seuil_jamais_negatif(self) -> None:
        """#202 : la garde réelle (raise) protège l'exécution."""
        for lev in (1, 2, 5, 10, 20, 50):
            self.assertGreaterEqual(liq_move_for("BTCUSDT", lev), 0.0)


if __name__ == "__main__":
    unittest.main()
