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

from services import label_ledger, onchain_engine  # noqa: E402


class LabelLedgerPromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db_path = label_ledger.DB_PATH
        self.original_onchain_db_path = onchain_engine.DB_PATH
        self.original_normalized_dir = label_ledger.NORMALIZED_DIR
        self.original_manual_labels_path = label_ledger.MANUAL_LABELS_PATH
        label_ledger.DB_PATH = Path(self.tmp.name) / "label_ledger.db"
        onchain_engine.DB_PATH = Path(self.tmp.name) / "onchain.db"
        label_ledger.NORMALIZED_DIR = Path(self.tmp.name) / "normalized"
        label_ledger.MANUAL_LABELS_PATH = Path(self.tmp.name) / "manual" / "verified_entity_labels.json"
        label_ledger.NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
        label_ledger.MANUAL_LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
        label_ledger._init_db()
        onchain_engine._init_db()

    def tearDown(self) -> None:
        label_ledger.DB_PATH = self.original_db_path
        onchain_engine.DB_PATH = self.original_onchain_db_path
        label_ledger.NORMALIZED_DIR = self.original_normalized_dir
        label_ledger.MANUAL_LABELS_PATH = self.original_manual_labels_path
        self.tmp.cleanup()

    def _insert_candidate(self, *, source_url: str, seen_count: int = 20, source: str = "manual_verified") -> int:
        conn = sqlite3.connect(str(label_ledger.DB_PATH))
        try:
            now = label_ledger._utc_now()
            cursor = conn.execute(
                """
                INSERT INTO label_candidates (
                    chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                    confidence, source, source_key, source_url, evidence_json,
                    first_seen_at, last_seen_at, seen_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ethereum",
                    "0x1111111111111111111111111111111111111111",
                    "Binance Hot Wallet",
                    "Binance",
                    "hot wallet",
                    "medium",
                    source,
                    f"test:{source_url}",
                    source_url,
                    json.dumps(["holder_snapshot", "scrapling_entity"]),
                    now,
                    now,
                    seen_count,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def _insert_trusted_label(
        self,
        *,
        entity: str = "Binance",
        address: str = "0x2222222222222222222222222222222222222222",
        sources_json: str = '[{"source":"manual_verified"}]',
    ) -> None:
        conn = sqlite3.connect(str(label_ledger.DB_PATH))
        try:
            now = label_ledger._utc_now()
            conn.execute(
                """
                INSERT INTO labels (
                    chain, address, label, entity, wallet_type, confidence,
                    flags_json, tags_json, sources_json, first_seen_source_at,
                    last_seen_source_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ethereum",
                    address,
                    f"{entity}: Hot Wallet",
                    entity,
                    "hot wallet",
                    "high",
                    '["exchange","hot wallet"]',
                    "[]",
                    sources_json,
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def test_dry_run_strict_ready_does_not_write_trusted_label(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance"
        )

        before = label_ledger.get_label_ledger_summary()["labels"]
        result = label_ledger.promote_label_candidates([candidate_id], dry_run=True)
        after = label_ledger.get_label_ledger_summary()["labels"]

        self.assertEqual(before, 0)
        self.assertEqual(after, before)
        self.assertEqual(result["rows"][0]["status"], "would_promote")
        self.assertTrue(result["rows"][0]["promotion"]["strict_ready"])

    def test_real_promotion_uses_strict_gate_not_legacy_score(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/token/binance"
        )

        result = label_ledger.promote_label_candidates([candidate_id], min_score=70, dry_run=True)

        self.assertEqual(label_ledger.get_label_ledger_summary()["labels"], 0)
        self.assertEqual(result["rows"][0]["status"], "blocked")
        self.assertIn("strict_requires_entity_source_url", result["rows"][0]["promotion"]["blockers"])

    def test_scrapling_only_candidate_is_not_strict_ready(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )

        result = label_ledger.promote_label_candidates([candidate_id], dry_run=True)

        self.assertEqual(label_ledger.get_label_ledger_summary()["labels"], 0)
        self.assertEqual(result["rows"][0]["status"], "blocked")
        blockers = result["rows"][0]["promotion"]["blockers"]
        self.assertIn("strict_requires_verified_or_external_source", blockers)
        self.assertIn("strict_blocks_scrapling_only_evidence", blockers)

    def test_candidate_corroboration_is_read_only_and_reports_external_evidence(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )
        original_http_json = label_ledger._http_json

        def fake_http_json(_url, timeout=12):
            return {
                "hash": "0x1111111111111111111111111111111111111111",
                "name": "Binance Hot Wallet",
                "is_contract": False,
                "metadata": {"tags": [{"name": "Exchange"}, {"name": "Binance"}]},
            }

        try:
            label_ledger._http_json = fake_http_json
            result = label_ledger.corroborate_label_candidates(entity="Binance", limit=1, persist=False)
        finally:
            label_ledger._http_json = original_http_json

        self.assertEqual(label_ledger.get_label_ledger_summary()["labels"], 0)
        self.assertEqual(result["rows"][0]["id"], candidate_id)
        # 20 blockscout + 45 confirmation entité + 25 bonus strict_ready (scoring 2026-05-09)
        self.assertEqual(result["rows"][0]["corroboration"]["score"], 90)
        self.assertEqual(result["rows"][0]["corroboration"]["status"], "needs_more_evidence")
        self.assertIn("blockscout_address", result["rows"][0]["corroboration"]["evidence"][0]["source"])

    def test_candidate_corroboration_adds_etherscan_activity_when_key_exists(self) -> None:
        self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )
        original_http_json = label_ledger._http_json
        original_api_key = label_ledger._etherscan_api_key

        def fake_api_key():
            return "test-key"

        def fake_http_json(url, timeout=12):
            if "action=balance" in url:
                return {"status": "1", "result": "123"}
            if "action=txlist" in url:
                return {
                    "status": "1",
                    "result": [
                        {
                            "hash": "0xabc",
                            "from": "0x1111111111111111111111111111111111111111",
                            "to": "0x2222222222222222222222222222222222222222",
                            "timeStamp": "1770000000",
                        }
                    ],
                }
            return {
                "hash": "0x1111111111111111111111111111111111111111",
                "name": "Binance Hot Wallet",
                "is_contract": False,
                "metadata": {"tags": [{"name": "Binance"}]},
            }

        try:
            label_ledger._etherscan_api_key = fake_api_key
            label_ledger._http_json = fake_http_json
            result = label_ledger.corroborate_label_candidates(entity="Binance", limit=1, persist=False)
        finally:
            label_ledger._http_json = original_http_json
            label_ledger._etherscan_api_key = original_api_key

        sources = [item["source"] for item in result["rows"][0]["corroboration"]["evidence"]]
        self.assertIn("blockscout_address", sources)
        self.assertIn("etherscan_balance", sources)
        self.assertIn("etherscan_recent_tx", sources)
        # 65 + 10 balance + 15 tx + 25 bonus strict_ready, plafonné à 100
        self.assertEqual(result["rows"][0]["corroboration"]["score"], 100)

    def test_candidate_corroboration_persists_evidence_bundle_without_trusted_write(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )
        original_http_json = label_ledger._http_json

        def fake_http_json(_url, timeout=12):
            return {
                "hash": "0x1111111111111111111111111111111111111111",
                "name": "Binance Hot Wallet",
                "is_contract": False,
                "metadata": {"tags": [{"name": "Binance"}]},
            }

        try:
            label_ledger._http_json = fake_http_json
            result = label_ledger.corroborate_label_candidates(entity="Binance", limit=1, persist=True)
        finally:
            label_ledger._http_json = original_http_json

        evidence = label_ledger.get_label_candidate_evidence(candidate_id=candidate_id)

        self.assertEqual(label_ledger.get_label_ledger_summary()["labels"], 0)
        self.assertEqual(result["evidence_bundles_written"], 1)
        self.assertEqual(evidence["total_evidence_bundles"], 1)
        self.assertEqual(evidence["rows"][0]["candidate_id"], candidate_id)
        self.assertEqual(evidence["rows"][0]["source"], "corroboration_bundle")

    def test_candidate_corroboration_persist_false_writes_no_bundle(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )
        original_http_json = label_ledger._http_json

        def fake_http_json(_url, timeout=12):
            return {
                "hash": "0x1111111111111111111111111111111111111111",
                "name": "Binance Hot Wallet",
                "is_contract": False,
                "metadata": {"tags": [{"name": "Binance"}]},
            }

        try:
            label_ledger._http_json = fake_http_json
            result = label_ledger.corroborate_label_candidates(entity="Binance", limit=1, persist=False)
        finally:
            label_ledger._http_json = original_http_json

        evidence = label_ledger.get_label_candidate_evidence(candidate_id=candidate_id)

        self.assertEqual(result["evidence_bundles_written"], 0)
        self.assertEqual(evidence["rows"], [])

    def test_candidate_corroboration_job_uses_queue_and_logs_data_job(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )
        original_http_json = label_ledger._http_json

        def fake_http_json(_url, timeout=12):
            return {
                "hash": "0x1111111111111111111111111111111111111111",
                "name": "Binance Hot Wallet",
                "is_contract": False,
                "metadata": {"tags": [{"name": "Binance"}]},
            }

        try:
            label_ledger._http_json = fake_http_json
            result = onchain_engine.corroborate_label_candidates_job(entity="Binance", limit=1, timeout=2)
        finally:
            label_ledger._http_json = original_http_json

        jobs = onchain_engine.get_data_jobs(limit=1, job_type="label_candidate_corroboration")
        evidence = label_ledger.get_label_candidate_evidence(candidate_id=candidate_id)

        self.assertEqual(label_ledger.get_label_ledger_summary()["labels"], 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["candidate_ids"], [candidate_id])
        self.assertEqual(result["result"]["candidates_selected"], 1)
        self.assertEqual(result["result"]["evidence_bundles_written"], 1)
        self.assertFalse(result["result"]["trusted_labels_changed"])
        self.assertEqual(evidence["total_evidence_bundles"], 1)
        self.assertEqual(jobs["rows"][0]["job_type"], "label_candidate_corroboration")
        self.assertEqual(jobs["rows"][0]["status"], "ok")
        self.assertEqual(jobs["rows"][0]["result"]["candidate_ids"], [candidate_id])
        self.assertIn("no candidates are promoted", jobs["rows"][0]["result"]["source_policy"])

    def test_candidate_evidence_scores_rank_persisted_bundles_without_trusted_write(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )
        conn = sqlite3.connect(str(label_ledger.DB_PATH))
        try:
            now = label_ledger._utc_now()
            conn.execute(
                """
                INSERT INTO label_candidate_evidence (
                    candidate_id, chain, address, source, source_key, status, score,
                    evidence_json, blockers_json, observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    "ethereum",
                    "0x1111111111111111111111111111111111111111",
                    "corroboration_bundle",
                    "test-key",
                    "needs_more_evidence",
                    90,
                    json.dumps([
                        {"source": "blockscout_address"},
                        {"source": "etherscan_recent_tx"},
                    ]),
                    json.dumps(["strict_blocks_scrapling_only_evidence"]),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        result = label_ledger.get_label_candidate_evidence_scores(entity="Binance", limit=5)
        row = result["rows"][0]

        self.assertEqual(label_ledger.get_label_ledger_summary()["labels"], 0)
        self.assertEqual(row["id"], candidate_id)
        self.assertEqual(row["evidence_bundles"], 1)
        self.assertEqual(row["max_bundle_score"], 90)
        # Source publique (blockscout) présente → le blocker scrapling-only n'est plus
        # sévère : score 90 + 5 bonus sources (>= 80, >= 2 sources) → strict_review_candidate
        self.assertEqual(row["decision"], "strict_review_candidate")
        self.assertNotIn("strict_blocks_scrapling_only_evidence", row["severe_blockers"])

    def test_corroboration_queue_prioritizes_unchecked_priority_candidates_read_only(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )

        result = label_ledger.get_label_corroboration_queue(entity="Binance", limit=5)
        evidence = label_ledger.get_label_candidate_evidence(candidate_id=candidate_id)

        self.assertEqual(evidence["rows"], [])
        self.assertEqual(result["rows"][0]["id"], candidate_id)
        self.assertEqual(result["rows"][0]["recommended_action"], "corroborate_first_pass")
        self.assertGreater(result["rows"][0]["priority_score"], 0)
        self.assertIn("no evidence is fetched", result["source_policy"])

    def test_corroboration_queue_filters_signers_by_default(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            source="scrapling_wallet",
            seen_count=20,
        )
        conn = sqlite3.connect(str(label_ledger.DB_PATH))
        try:
            conn.execute(
                "UPDATE label_candidates SET proposed_label = ?, proposed_wallet_type = ? WHERE id = ?",
                ("Signer: 0x1111111111111111111111111111111111111111", "signer", candidate_id),
            )
            conn.commit()
        finally:
            conn.close()

        result = label_ledger.get_label_corroboration_queue(entity="Binance", limit=5)

        self.assertEqual(result["rows"], [])
        self.assertEqual(result["manual_review_filtered"], 1)

        with_review = label_ledger.get_label_corroboration_queue(
            entity="Binance",
            limit=5,
            include_manual_review=True,
        )

        self.assertEqual(with_review["rows"][0]["id"], candidate_id)
        self.assertTrue(with_review["rows"][0]["requires_manual_review"])
        self.assertEqual(with_review["rows"][0]["priority_score"], 0)
        self.assertIn("signer_candidate_requires_manual_review", with_review["rows"][0]["promotion_blockers"])

    def test_corroboration_queue_filters_protocol_manual_review_by_default(self) -> None:
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/vault-dao",
            source="scrapling_wallet",
            seen_count=20,
        )
        conn = sqlite3.connect(str(label_ledger.DB_PATH))
        try:
            conn.execute(
                "UPDATE label_candidates SET proposed_entity = ?, proposed_label = ?, proposed_wallet_type = ? WHERE id = ?",
                ("VaultDAO", "VaultDAO: Vault Proxy", "protocol", candidate_id),
            )
            conn.commit()
        finally:
            conn.close()

        result = label_ledger.get_label_corroboration_queue(entity="VaultDAO", limit=5)
        with_review = label_ledger.get_label_corroboration_queue(
            entity="VaultDAO",
            limit=5,
            include_manual_review=True,
        )

        self.assertEqual(result["rows"], [])
        self.assertEqual(result["manual_review_filtered"], 1)
        self.assertEqual(with_review["rows"][0]["id"], candidate_id)
        self.assertTrue(with_review["rows"][0]["requires_manual_review"])
        self.assertIn("strict_protocol_requires_manual_review", with_review["rows"][0]["promotion_blockers"])

    def test_label_acquisition_plan_is_read_only_and_surfaces_strict_ready(self) -> None:
        self._insert_trusted_label()
        candidate_id = self._insert_candidate(
            source_url="https://intel.arkm.com/explorer/entity/binance",
            seen_count=10,
        )

        before = label_ledger.get_label_ledger_summary()["labels"]
        plan = label_ledger.get_label_acquisition_plan(limit=20, min_trusted_per_entity=5)
        after = label_ledger.get_label_ledger_summary()["labels"]
        rows = {row["entity"]: row for row in plan["rows"]}

        self.assertEqual(before, after)
        self.assertIn("Binance", rows)
        self.assertEqual(rows["Binance"]["trusted_labels"], 1)
        self.assertEqual(rows["Binance"]["strict_ready_candidates"], 1)
        self.assertEqual(rows["Binance"]["recommended_action"], "dry_run_promote_strict_ready")
        self.assertIn(candidate_id, rows["Binance"]["top_candidate_ids"])
        self.assertIn("no trusted labels are changed", plan["source_policy"])

    def test_label_acquisition_plan_does_not_count_legacy_labels_as_strict(self) -> None:
        self._insert_trusted_label(sources_json='[{"source":"scrapling_wallet"}]')

        plan = label_ledger.get_label_acquisition_plan(limit=20, min_trusted_per_entity=5)
        rows = {row["entity"]: row for row in plan["rows"]}

        self.assertEqual(rows["Binance"]["trusted_labels"], 0)
        self.assertEqual(rows["Binance"]["total_label_rows"], 1)
        self.assertEqual(rows["Binance"]["legacy_or_unverified_labels"], 1)
        self.assertEqual(rows["Binance"]["recommended_action"], "acquire_new_source_snapshots")

    def test_candidate_source_staging_never_writes_trusted_labels(self) -> None:
        snapshot_path = label_ledger.NORMALIZED_DIR / "entity_binance.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "source": "scrapling_arkham",
                    "final_url": "https://intel.arkm.com/explorer/entity/binance",
                    "generated_at": 1770000000,
                    "entity": {"name": "Binance"},
                    "wallets": [
                        {
                            "address": "0x3333333333333333333333333333333333333333",
                            "chain": "ethereum",
                            "label": "Binance: Hot Wallet",
                            "entity": "Binance",
                            "wallet_type": "hot wallet",
                            "confidence": "high",
                            "flags": ["exchange", "hot wallet"],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = label_ledger.stage_label_candidates_from_normalized_sources(target_stems=["entity_binance"])
        summary = label_ledger.get_label_ledger_summary()

        self.assertEqual(result["rows_observed"], 1)
        self.assertEqual(result["candidates_inserted"], 1)
        self.assertEqual(summary["labels"], 0)
        self.assertEqual(summary["label_candidates"], 1)
        self.assertIn("trusted labels are never changed", result["source_policy"])

    def test_build_label_ledger_keeps_scrapling_rows_candidate_only(self) -> None:
        snapshot_path = label_ledger.NORMALIZED_DIR / "entity_binance.json"
        snapshot_path.write_text(
            json.dumps(
                {
                    "source": "scrapling_arkham",
                    "final_url": "https://intel.arkm.com/explorer/entity/binance",
                    "generated_at": 1770000000,
                    "entity": {"name": "Binance"},
                    "wallets": [
                        {
                            "address": "0x3333333333333333333333333333333333333333",
                            "chain": "ethereum",
                            "label": "Binance: Hot Wallet",
                            "entity": "Binance",
                            "wallet_type": "hot wallet",
                            "confidence": "high",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = label_ledger.build_label_ledger()
        summary = label_ledger.get_label_ledger_summary()

        self.assertEqual(result["rows_observed"], 1)
        self.assertEqual(result["candidates_inserted"], 1)
        self.assertEqual(result["rows_inserted"], 0)
        self.assertEqual(summary["labels"], 0)
        self.assertEqual(summary["label_candidates"], 1)

    def test_label_ledger_summary_marks_legacy_scrapling_trusted_sources(self) -> None:
        conn = sqlite3.connect(str(label_ledger.DB_PATH))
        try:
            now = label_ledger._utc_now()
            conn.execute(
                """
                INSERT INTO labels (
                    chain, address, label, entity, wallet_type, confidence,
                    flags_json, tags_json, sources_json, first_seen_source_at,
                    last_seen_source_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "ethereum",
                    "0x5555555555555555555555555555555555555555",
                    "Binance: Hot Wallet",
                    "Binance",
                    "hot wallet",
                    "high",
                    "[]",
                    "[]",
                    json.dumps([{"source": "scrapling_wallet"}]),
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        audit = label_ledger.get_label_ledger_summary()["trusted_source_audit"]

        self.assertEqual(audit["trust_buckets"]["legacy_scrapling"], 1)
        self.assertIn("candidates only", audit["warning"])

    def test_priority_source_acquisition_uses_scrapling_but_only_stages_candidates(self) -> None:
        class FakeSnapshotService:
            def get_entity_snapshot(self, target, **_kwargs):
                snapshot_path = label_ledger.NORMALIZED_DIR / f"entity_{target}.json"
                snapshot = {
                    "source": "scrapling_arkham",
                    "url": f"https://intel.arkm.com/explorer/entity/{target}",
                    "final_url": f"https://intel.arkm.com/explorer/entity/{target}",
                    "generated_at": 1770000000,
                    "entity": {"name": "Binance"},
                    "wallets": [
                        {
                            "address": "0x4444444444444444444444444444444444444444",
                            "chain": "ethereum",
                            "label": "Binance: Hot Wallet",
                            "entity": "Binance",
                            "wallet_type": "hot wallet",
                            "confidence": "high",
                        }
                    ],
                    "transfers": [],
                    "counterparties": [],
                    "artifact_path": str(snapshot_path),
                }
                snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
                return snapshot

        result = label_ledger.acquire_priority_label_source_snapshots(
            limit=1,
            min_trusted_per_entity=5,
            snapshot_service=FakeSnapshotService(),
        )
        summary = label_ledger.get_label_ledger_summary()

        self.assertEqual(result["acquired"][0]["entity"], "Binance")
        self.assertEqual(result["candidate_staging"]["candidates_inserted"], 1)
        self.assertEqual(summary["labels"], 0)
        self.assertEqual(summary["label_candidates"], 1)
        self.assertIn("stages label candidates only", result["source_policy"])


if __name__ == "__main__":
    unittest.main()
