"""Tests du Research OS — PR 1 de la séquence V3 (brief §203).

Couvre les tests d'acceptation §185 applicables à cette couche :
B (scope violation), D (discovery → confirmation autorisé), E (doublon),
F (réplication sur nouveau snapshot), H (preflight fail = 0 slot),
et les invariants structurels du DataScope.

    python tests/test_research_os.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.research_os import (  # noqa: E402
    DUPLICATE, NEW, REPLICATION, DataScope, DataView, ExecState, Mode,
    ScopeViolation, consumes_slot, dedup_verdict)

H1, P1 = "hh-1", "ph-1"


def _scope():
    return DataScope(snapshot_id="S1",
                     train_start_ms=0, train_end_ms=1_000,
                     validation_start_ms=2_000, validation_end_ms=3_000,
                     holdout_start_ms=4_000, holdout_end_ms=5_000)


class TestDataScope(unittest.TestCase):
    def test_la_vue_discovery_ne_porte_pas_la_validation(self):
        v = _scope().discovery_view()
        self.assertEqual(v.mode, Mode.DISCOVERY.value)
        self.assertFalse(hasattr(v, "validation_start_ms"))
        self.assertFalse(hasattr(v, "validation_end_ms"))
        self.assertFalse(hasattr(v, "holdout_start_ms"))

    def test_assert_within_leve_scope_violation_hors_vue(self):
        v = _scope().discovery_view()
        v.assert_within(500)                       # dans le TRAIN : OK
        with self.assertRaises(ScopeViolation):
            v.assert_within(2_500)                 # la validation : INTERDIT
        with self.assertRaises(ScopeViolation):
            v.assert_range(500, 2_500)             # une requête qui déborde

    def test_la_vue_confirmation_voit_les_deux_fenetres(self):
        tr, va = _scope().confirmation_view()
        self.assertEqual(tr.mode, Mode.CONFIRMATION.value)
        tr.assert_within(1_000)
        va.assert_within(2_500)

    def test_la_vue_paper_couvre_tout_et_ne_se_retune_pas(self):
        v = _scope().paper_view()
        self.assertEqual(v.mode, Mode.PAPER.value)
        v.assert_within(4_500)

    def test_fenetres_non_croisantes_refusees(self):
        with self.assertRaises(ValueError):
            DataScope("S", 1_000, 500, 2_000, 3_000)


class TestConsumptionPolicy(unittest.TestCase):
    """§47 : un crash AVANT la lecture de la validation ne coûte rien."""

    def test_preflight_failed_ne_consomme_pas(self):
        self.assertFalse(consumes_slot(ExecState.PREFLIGHT_FAILED))
        self.assertFalse(consumes_slot(ExecState.EXECUTION_FAILED_PRE_READ))

    def test_post_read_et_sealed_consomment(self):
        self.assertTrue(consumes_slot(ExecState.EXECUTION_FAILED_POST_READ))
        self.assertTrue(consumes_slot(ExecState.SEALED))
        self.assertTrue(consumes_slot(ExecState.VERDICT))


class TestDedupV3(unittest.TestCase):
    """§4-6 : DUPLICATE ≠ REPLICATION ≠ transition discovery→confirmation."""

    def _prior(self, mode="confirmation", snapshot="S1", hh=H1, ph=P1):
        return [{"mode": mode, "hh": hh, "ph": ph, "snapshot": snapshot}]

    def test_meme_spec_meme_snapshot_meme_mode_duplicale(self):
        self.assertEqual(dedup_verdict("confirmation", H1, P1, "S1",
                                       self._prior()), DUPLICATE)

    def test_discovery_puis_confirmation_est_autorise(self):
        """LE point du système : la découverte ne bloque pas sa confirmation."""
        self.assertEqual(dedup_verdict("confirmation", H1, P1, "S1",
                                       self._prior(mode="discovery")), NEW)
        self.assertEqual(dedup_verdict("discovery", H1, P1, "S1",
                                       self._prior(mode="confirmation")), NEW)

    def test_meme_hypothese_nouveau_snapshot_replication(self):
        self.assertEqual(dedup_verdict("confirmation", H1, P1, "S2",
                                       self._prior(snapshot="S1")), REPLICATION)

    def test_nouvelle_hypothese_new(self):
        self.assertEqual(dedup_verdict("confirmation", "hh-2", P1, "S1",
                                       self._prior()), NEW)

    def test_meme_spec_mode_discovery_deja_loggue_duplicale(self):
        self.assertEqual(dedup_verdict("discovery", H1, P1, "S1",
                                       self._prior(mode="discovery")), DUPLICATE)


if __name__ == "__main__":
    unittest.main()
