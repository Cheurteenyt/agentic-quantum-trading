from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import arkham_source_registry  # noqa: E402


class ArkhamSourceRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "arkham"
        self.scrapling = self.root / "scrapling"
        self.normalized = self.scrapling / "normalized"
        self.manual = self.root / "manual" / "verified_entity_labels.json"
        self.cache = self.root / "cache.json"
        self.ledger = self.root / "label_ledger.db"

        self.original_scrapling_dir = arkham_source_registry.SCRAPLING_DIR
        self.original_normalized_dir = arkham_source_registry.SCRAPLING_NORMALIZED_DIR
        self.original_manual_path = arkham_source_registry.MANUAL_LABELS_PATH
        self.original_cache_path = arkham_source_registry.CACHE_PATH
        self.original_ledger_path = arkham_source_registry.LABEL_LEDGER_DB_PATH

        arkham_source_registry.SCRAPLING_DIR = self.scrapling
        arkham_source_registry.SCRAPLING_NORMALIZED_DIR = self.normalized
        arkham_source_registry.MANUAL_LABELS_PATH = self.manual
        arkham_source_registry.CACHE_PATH = self.cache
        arkham_source_registry.LABEL_LEDGER_DB_PATH = self.ledger

        self.normalized.mkdir(parents=True, exist_ok=True)
        self.manual.parent.mkdir(parents=True, exist_ok=True)
        (self.normalized / "entity_binance.json").write_text("{}", encoding="utf-8")
        (self.scrapling / "entity_binance_raw.json").write_text("{}", encoding="utf-8")
        self.cache.write_text(
            json.dumps(
                {
                    "entities": {"binance": {}},
                    "addresses": {"0x1111111111111111111111111111111111111111": {}},
                    "holders_cache": {"holders:ethereum:0xabc": []},
                    "metadata": {"last_scrape": "2026-05-16T00:00:00Z"},
                }
            ),
            encoding="utf-8",
        )
        self.manual.write_text(
            json.dumps(
                {
                    "generated_at": "2026-05-16T00:00:00Z",
                    "policy": "test",
                    "labels": [
                        {
                            "chain": "ethereum",
                            "address": "0x1111111111111111111111111111111111111111",
                            "entity": "Binance",
                            "label": "Binance Hot Wallet",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self._init_ledger()

    def tearDown(self) -> None:
        arkham_source_registry.SCRAPLING_DIR = self.original_scrapling_dir
        arkham_source_registry.SCRAPLING_NORMALIZED_DIR = self.original_normalized_dir
        arkham_source_registry.MANUAL_LABELS_PATH = self.original_manual_path
        arkham_source_registry.CACHE_PATH = self.original_cache_path
        arkham_source_registry.LABEL_LEDGER_DB_PATH = self.original_ledger_path
        self.tmp.cleanup()

    def _init_ledger(self) -> None:
        conn = sqlite3.connect(str(self.ledger))
        try:
            conn.execute("CREATE TABLE labels (sources_json TEXT, entity TEXT)")
            conn.execute("CREATE TABLE label_candidates (source TEXT)")
            conn.execute("CREATE TABLE label_candidate_evidence (source TEXT)")
            conn.execute(
                "INSERT INTO labels (sources_json, entity) VALUES (?, ?)",
                (json.dumps([{"source": "manual_verified"}]), "Binance"),
            )
            conn.execute(
                "INSERT INTO labels (sources_json, entity) VALUES (?, ?)",
                (json.dumps([{"source": "scrapling_wallet"}]), "Binance"),
            )
            conn.execute("INSERT INTO label_candidates (source) VALUES (?)", ("scrapling_wallet",))
            conn.execute("INSERT INTO label_candidate_evidence (source) VALUES (?)", ("corroboration_bundle",))
            conn.commit()
        finally:
            conn.close()

    def test_inventory_is_read_only_and_classifies_source_layers(self) -> None:
        result = arkham_source_registry.get_arkham_source_backed_inventory(limit=5, dry_run=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["inventory_status"], "ready_for_source_backed_planning")
        self.assertEqual(result["summary"]["strict_source_labels"], 1)
        self.assertEqual(result["summary"]["legacy_or_unverified_labels"], 1)
        self.assertEqual(result["summary"]["label_candidates"], 1)
        self.assertEqual(result["summary"]["label_candidate_evidence"], 1)
        self.assertEqual(result["summary"]["manual_verified_labels"], 1)
        self.assertEqual(result["summary"]["normalized_snapshots"], 1)
        self.assertEqual(result["summary"]["raw_scrapling_snapshots"], 1)
        self.assertFalse(result["would_write"])
        self.assertFalse(result["would_create_cex_label"])
        self.assertFalse(result["would_execute_trade"])

        layers = {layer["layer"]: layer for layer in result["source_layers"]}
        self.assertTrue(layers["label_ledger"]["usable_for_core_equity"])
        self.assertFalse(layers["scrapling_normalized_snapshots"]["usable_for_core_equity"])
        self.assertFalse(layers["arkham_scraper"]["usable_for_core_equity"])
        self.assertFalse(layers["arkham_tracker"]["usable_for_core_equity"])

    def test_inventory_rejects_real_mode(self) -> None:
        result = arkham_source_registry.get_arkham_source_backed_inventory(dry_run=False)

        self.assertFalse(result["ok"])
        self.assertEqual(result["inventory_status"], "blocked")
        self.assertIn("dry_run_required", result["blockers"])
        self.assertFalse(result["would_write"])
        self.assertEqual(result["writes_performed"], 0)


if __name__ == "__main__":
    unittest.main()
