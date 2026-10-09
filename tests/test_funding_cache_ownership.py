"""Issue #203 — l'ownership du cache funding n'était pas prouvé : le
backend (aster_perps_model) écrasait `funding_interval_hours` MESURÉ par
le refresher nocturne (médiane des gaps) par une row publique qui ne
produit jamais ce champ → fallback costs.py 8.0h → coût funding ÷8 sur
les symboles 1h (CATEUSDT, MEMEUSDT).

LE TEST DEMANDÉ PAR L'ISSUE : writer A (refresher) → write → read →
writer B (backend) → write → read — l'intervalle doit SURVIVRE au cycle.
Plus : keep-old-on-error (une erreur transitoire ne remplace plus une
bonne entrée) et le mode catastrophe (cache corrompu → jamais d'écriture
— les 73 symboles ne peuvent plus être effacés).

Aucun appel réseau réel.

    python tests/test_funding_cache_ownership.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))   # refresh_aster_cache importe aster_rate

# Writer A : le refresher nocturne (chargé par chemin — pas un package)
_spec = importlib.util.spec_from_file_location(
    "refresh_aster_cache", ROOT / "scripts" / "refresh_aster_cache.py"
)
rac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rac)

# Writer B : le backend (l'écrivain fautif)
from backend.services.onchain.aster import aster_perps_model as apm  # noqa: E402

# Le lecteur officiel : le moteur de coûts des backtests
from backend.services.backtest_v2.costs import load_funding_rate  # noqa: E402

ROWS_1H = [
    {"symbol": "CATEUSDT", "fundingTime": 1780000000000 + i * 3_600_000,
     "fundingRate": "0.0001"}
    for i in range(40)
]
# intervalle mesuré attendu : médiane des gaps = 1.0 h (symbole 1h réel)


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(payload):
    def _open(req, timeout=None):
        return _FakeResp(payload)
    return _open


def backend_row_no_interval(symbol: str) -> dict:
    """Ce que le backend produit : une row ok mais SANS intervalle mesuré
    (exactement `_funding_metrics` l.253-266)."""
    return {
        "symbol": symbol,
        "status": "ok",
        "source": "aster_public_funding_history_fapi_v3",
        "funding_count": 100,
        "avg_funding_rate": 0.0002,
        "latest_funding_rate": 0.0002,
        "min_funding_rate": 0.0001,
        "max_funding_rate": 0.0003,
        "avg_funding_bps_per_8h": 2.0,
        "latest_funding_bps_per_8h": 2.0,
        "first_funding_time": 1780000000000,
        "last_funding_time": 1780003596000000,
    }


def backend_row_error(symbol: str) -> dict:
    return {
        "symbol": symbol, "status": "rate_limited", "funding_count": 0,
        "source": "aster_public_funding_history_unavailable",
    }


class TestOwnershipCycle(unittest.TestCase):
    """Le scénario exact de l'issue #203 : A → read → B → read."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "aster_public_funding_history_cache.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _writer_a_refresh(self):
        res = rac.refresh_funding(
            ["CATEUSDT"], cache_path=self.cache, opener=fake_opener(ROWS_1H))
        self.assertTrue(res["written"])
        self.assertEqual(res["ok"], 1)

    def _read_interval(self) -> float:
        return load_funding_rate("CATEUSDT", self.cache).interval_hours

    def _writer_b_snapshot(self, fetch_row):
        with mock.patch.object(apm, "FUNDING_CACHE_FILE", self.cache), \
             mock.patch.object(apm, "_fetch_funding_history",
                               lambda s, limit, timeout_seconds: fetch_row(s)):
            return apm.get_public_funding_history_snapshot(
                ["CATEUSDT"], cache_ttl_seconds=0)

    def test_le_cycle_complet_preserve_l_interval_mesure(self):
        """LE TEST #203 : A → write → read(1.0) → B → write → read(1.0)."""
        self._writer_a_refresh()
        self.assertEqual(self._read_interval(), 1.0,
                         "le refresher a mesuré 1h — la lecture doit le voir")
        # writer B (backend, TTL épuisé) remplace l'entrée par une row
        # SANS funding_interval_hours
        self._writer_b_snapshot(backend_row_no_interval)
        # AVANT le fix : fallback 8.0 → coût funding ÷8. APRÈS : héritage.
        self.assertEqual(self._read_interval(), 1.0,
                         "l'intervalle MESURÉ par le refresher doit survivre "
                         "au passage du backend (issue #203)")

    def test_erreur_transitoire_ne_remplace_pas_une_bonne_entree(self):
        self._writer_a_refresh()
        good = json.loads(self.cache.read_text())
        self._writer_b_snapshot(backend_row_error)   # 429 / timeout
        after = json.loads(self.cache.read_text())
        self.assertEqual(after["symbols"]["CATEUSDT"]["data"]["status"], "ok",
                         "une erreur transitoire ne doit pas remplacer une "
                         "entrée ok dans le cache")
        self.assertEqual(after["symbols"]["CATEUSDT"]["data"],
                         good["symbols"]["CATEUSDT"]["data"])

    def test_cache_corrompu_n_est_jamais_efface(self):
        """Mode catastrophe : l'ancien code lisait {} sur corruption et la
        write-back suivante réécrivait un cache à N symboles (les 73
        symboles effacés)."""
        payload = {"symbols": {
            f"SYM{i}USDT": {"cached_at": 1.0, "data": {"status": "ok"}}
            for i in range(73)}}
        self.cache.write_text(json.dumps(payload), encoding="utf-8")
        self.cache.write_text("{CORROMPU:::", encoding="utf-8")  # tronqué
        with mock.patch.object(apm, "FUNDING_CACHE_FILE", self.cache), \
             mock.patch.object(apm, "_fetch_funding_history",
                               lambda s, limit, timeout_seconds:
                               backend_row_no_interval(s)):
            res = apm.get_public_funding_history_snapshot(
                ["CATEUSDT"], cache_ttl_seconds=0)
        # le consommateur reçoit quand même sa réponse (mode dégradé)
        self.assertEqual(res["CATEUSDT"]["status"], "ok")
        # le fichier corrompu n'a PAS été remplacé par un cache à 1 symbole
        content = self.cache.read_text()
        self.assertEqual(content, "{CORROMPU:::",
                         "sur cache illisible, le backend ne doit JAMAIS "
                         "écrire (les 73 symboles ne sont pas effaçables)")

    def test_cache_status_transitoire_non_persiste(self):
        self._writer_a_refresh()
        self._writer_b_snapshot(backend_row_no_interval)
        blob = json.loads(self.cache.read_text())
        self.assertNotIn(
            "cache_status", blob["symbols"]["CATEUSDT"]["data"],
            "cache_status est un champ d'appel transitoire, pas une donnée")

    def test_le_backend_ecrit_son_champ_si_aucune_mesure(self):
        # sans entrée précédente : la row backend entre au cache telle
        # quelle (l'héritage ne FABRIQUE pas une mesure qui n'existe pas)
        self._writer_b_snapshot(backend_row_no_interval)
        blob = json.loads(self.cache.read_text())
        data = blob["symbols"]["CATEUSDT"]["data"]
        self.assertEqual(data["status"], "ok")
        self.assertNotIn("funding_interval_hours", data)
        # et le lecteur officiel retombe sur son fallback documenté 8.0
        self.assertEqual(self._read_interval(), 8.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
