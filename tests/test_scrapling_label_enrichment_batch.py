from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.onchain.aster import scrapling_label_enrichment_batch as batch  # noqa: E402


class ScraplingLabelEnrichmentBatchTests(unittest.TestCase):
    def test_preview_reads_local_snapshot_and_returns_digest_without_writes(self) -> None:
        target = "0x1111111111111111111111111111111111111111"
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp)
            payload = {
                "kind": "entity",
                "entity": {"name": "Binance", "type": "cex", "top_address": target},
                "profile": {"name": "Binance", "type": "cex"},
            }
            raw = json.dumps(payload, sort_keys=True).encode("utf-8")
            (snapshot_dir / "entity_binance.json").write_bytes(raw)

            with patch.object(
                batch,
                "_collect_behavioral_candidate_addresses",
                return_value=(
                    {target},
                    [{"pool_address": "0x2222222222222222222222222222222222222222", "behavioral_anomaly_score": 82}],
                    [],
                ),
            ):
                preview = batch.get_scrapling_label_enrichment_preview(snapshot_dir=snapshot_dir)

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["matches_found"], 1)
        self.assertFalse(preview["would_scrape"])
        self.assertFalse(preview["would_call_external"])
        self.assertFalse(preview["would_persist_evidence"])
        self.assertFalse(preview["would_apply_label_source"])
        self.assertFalse(preview["would_write"])
        row = preview["enrichment_rows"][0]
        self.assertEqual(row["address"], target)
        self.assertEqual(row["label_status"], "found_in_local_snapshot")
        self.assertEqual(row["entity"], "Binance")
        self.assertEqual(row["snapshot_sha256"], hashlib.sha256(raw).hexdigest())

    def test_preview_returns_not_found_without_scraping_or_fallback(self) -> None:
        target = "0x3333333333333333333333333333333333333333"
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp)
            (snapshot_dir / "entity_binance.json").write_text(
                json.dumps({"entity": {"name": "Binance", "top_address": "0x4444444444444444444444444444444444444444"}}),
                encoding="utf-8",
            )
            with patch.object(
                batch,
                "_collect_behavioral_candidate_addresses",
                return_value=({target}, [{"behavioral_anomaly_score": 90}], []),
            ):
                preview = batch.get_scrapling_label_enrichment_preview(snapshot_dir=snapshot_dir)
                blocked = batch.get_scrapling_label_enrichment_preview(dry_run=False, snapshot_dir=snapshot_dir)

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["matches_found"], 0)
        self.assertEqual(preview["enrichment_rows"][0]["label_status"], "not_found_in_local_snapshots")
        self.assertFalse(preview["would_scrape"])
        self.assertFalse(preview["would_call_external"])
        self.assertFalse(preview["would_write"])
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["blockers"], ["dry_run_required"])
        self.assertEqual(blocked["writes_performed"], 0)


if __name__ == "__main__":
    unittest.main()
