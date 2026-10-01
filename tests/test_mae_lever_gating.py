"""Tests de l'asservissement du levier cascade majors au MAE (T8, 01/10/2026).

Règle pré-enregistrée (reports/aster_machine_deep_regimes.md) : levier
≤ 100/(MAE_pire_régime + 0,5) → 4x sur le cycle ; 10x SEULEMENT si le
moniteur MAE 6 majors (the_machine.py) donne lev_safe >= 10 dans
data/warehouse/mae_state.json. DÉFAUT SÛR = 4x : état absent, illisible
ou périmé (> 8 j). Les 3 consommateurs (the_machine écrivain,
paper_forward, qubo_forward_tracker) doivent appliquer la MÊME règle —
sinon le tracker et le forward divergent.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import paper_forward as pf  # noqa: E402
from scripts import qubo_forward_tracker as qft  # noqa: E402
from scripts import the_machine as tm  # noqa: E402


def _state(tmp: str, lev_safe: float, age_days: float = 0.0) -> Path:
    """Un mae_state.json synthétique au format exact de write_mae_state."""
    st = {"mae_gated": round(100 / lev_safe - 0.5, 4) if lev_safe else 0.0,
          "lev_safe": lev_safe,
          "updated_at": (datetime.now(timezone.utc)
                         - timedelta(days=age_days)).isoformat()}
    p = Path(tmp) / "mae_state.json"
    p.write_text(json.dumps(st), encoding="utf-8")
    return p


class MaeLeverGatingTest(unittest.TestCase):
    """La règle T8 sur les DEUX consommateurs (papier + tracker)."""

    def test_etat_absent_defaut_sur_4x(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "inexistant.json"
            self.assertEqual(pf._cascade_majors_lever(p), 4.0)
            self.assertEqual(qft._cascade_majors_lever(p), 4.0)

    def test_lev_safe_8_3_donne_4x(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _state(tmp, 8.3)
            self.assertEqual(pf._cascade_majors_lever(p), 4.0)
            self.assertEqual(qft._cascade_majors_lever(p), 4.0)

    def test_lev_safe_10_2_donne_10x(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _state(tmp, 10.2)
            self.assertEqual(pf._cascade_majors_lever(p), 10.0)
            self.assertEqual(qft._cascade_majors_lever(p), 10.0)

    def test_etat_perime_8j_defaut_sur_4x(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _state(tmp, 10.2, age_days=9.0)
            self.assertEqual(pf._cascade_majors_lever(p), 4.0)
            self.assertEqual(qft._cascade_majors_lever(p), 4.0)

    def test_etat_corrompu_defaut_sur_4x(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "mae_state.json"
            p.write_text("{pas du json", encoding="utf-8")
            self.assertEqual(pf._cascade_majors_lever(p), 4.0)
            self.assertEqual(qft._cascade_majors_lever(p), 4.0)

    def test_regles_identiques_paper_et_tracker(self):
        """Les deux consommateurs = la MÊME règle sur tous les cas T8."""
        for lev_safe, attendu in ((8.3, 4.0), (9.9, 4.0), (10.2, 10.0),
                                  (12.7, 10.0)):
            with tempfile.TemporaryDirectory() as tmp:
                p = _state(tmp, lev_safe)
                self.assertEqual(pf._cascade_majors_lever(p), attendu)
                self.assertEqual(qft._cascade_majors_lever(p), attendu)


class MaeStateWriteTest(unittest.TestCase):
    """L'écrivain the_machine.write_mae_state + le round-trip."""

    def test_write_format_et_roundtrip_10x(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "mae_state.json"
            tm.write_mae_state(7.84, 12.7135, path=p)
            st = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(sorted(st), ["lev_safe", "mae_gated", "updated_at"])
            self.assertEqual(st["mae_gated"], 7.84)
            self.assertEqual(st["lev_safe"], 12.7135)
            datetime.fromisoformat(st["updated_at"])   # UTC ISO parsable
            # l'état fraîchement écrit pilote bien le 10x chez les 2 lecteurs
            self.assertEqual(pf._cascade_majors_lever(p), 10.0)
            self.assertEqual(qft._cascade_majors_lever(p), 10.0)

    def test_write_echec_tolerant(self):
        with tempfile.TemporaryDirectory() as tmp:
            # un directory au lieu d'un fichier : l'écriture échoue, ne lève PAS
            tm.write_mae_state(7.84, 12.7, path=Path(tmp) / "d")


class MaeConsumersCoherenceTest(unittest.TestCase):
    """Les 3 consommateurs alignés (même règle, mêmes bases, flux inchangés)."""

    def test_tracker_flows_suivent_le_moniteur(self):
        base, lev = qft.FLOWS["machine_cascade_majors"]
        self.assertEqual(base, 0.24)   # poids/base INCHANGÉS
        self.assertEqual(lev, qft._cascade_majors_lever())
        for f in ("machine_cascade_meme", "machine_survivor_long",
                  "machine_vol_spike_6h"):
            self.assertEqual(qft.FLOWS[f], (0.10, 1.0))   # flux non majors 1x

    def test_etat_prod_absent_implique_defaut_sur_4x(self):
        """Tant que la machine n'a pas tiré, mae_state.json peut être absent :
        le défaut SÛR 4x s'applique partout (état de la prod du 01/10)."""
        p = pf.ROOT / "data" / "warehouse" / "mae_state.json"
        self.assertEqual(pf._cascade_majors_lever(p), 4.0)
        self.assertEqual(qft._cascade_majors_lever(p), 4.0)
        self.assertEqual(qft.FLOWS["machine_cascade_majors"][1], 4.0)


if __name__ == "__main__":
    unittest.main()
