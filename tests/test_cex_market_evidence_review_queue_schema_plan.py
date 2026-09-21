from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import onchain_engine  # noqa: E402


def _contract(**overrides):
    contract = {
        "ok": True,
        "contract_status": "ready_but_disabled",
        "final_handoff_target_id": 1,
        "final_handoff_id": 1,
        "final_target_execution_id": 1,
        "final_apply_id": 1,
        "post_apply_execution_apply_id": 1,
        "post_apply_execution_id": 1,
        "post_apply_insert_id": 1,
        "post_apply_id": 1,
        "business_apply_id": 1,
        "business_execution_id": 1,
        "business_insert_id": 1,
        "business_handoff_id": 1,
        "downstream_id": 1,
        "promotion_id": 1,
        "evidence_id": 1,
        "candidate_id": 1,
        "token_symbol": "TEST",
        "market_type": "cex",
        "target_queue": "cex_market_evidence_review_queue",
        "source_url": "https://example.com/evidence",
        "source_tier": "tier_1",
        "evidence_type": "official_market_page",
        "evidence_preview_digest": "digest",
        "target_dedupe_key": "target-dedupe",
        "cex_review_target_queue": "cex_market_evidence_review_queue",
        "cex_review_handoff_dedupe_key": "cex-review-dedupe",
        "cex_review_handoff_contract": {
            "handoff_kind": "cex_market_evidence_review_handoff_not_direct_label_write",
            "target_queue": "cex_market_evidence_review_queue",
            "payload_preview": {
                "final_handoff_target_id": 1,
                "cex_review_handoff_dedupe_key": "cex-review-dedupe",
            },
        },
        "dedupe_status": {
            "dedupe_bound": True,
            "source_digest_bound": True,
            "target_contract_json_valid": True,
            "target_contract_json_bound": True,
        },
        "parent_status": {
            "final_handoff_exists": True,
            "final_target_execution_exists": True,
            "final_apply_exists": True,
            "post_apply_execution_apply_exists": True,
            "post_apply_execution_exists": True,
            "post_apply_insert_exists": True,
            "post_apply_exists": True,
            "business_apply_exists": True,
            "business_execution_exists": True,
            "business_insert_exists": True,
            "business_handoff_exists": True,
            "downstream_exists": True,
            "promotion_exists": True,
            "evidence_exists": True,
            "candidate_exists": True,
        },
        "blockers": [],
        "would_create_cex_review_row": False,
        "would_create_cex_label": False,
        "would_write": False,
        "writes_performed": 0,
        "source_policy": "test contract",
    }
    contract.update(overrides)
    return contract


def _with_db(create_target_table: bool = False):
    tmp = tempfile.TemporaryDirectory()
    db_path = str(Path(tmp.name) / "schema-plan.sqlite")
    conn = sqlite3.connect(db_path)
    if create_target_table:
        conn.execute(
            """
            CREATE TABLE cex_market_evidence_review_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cex_review_handoff_dedupe_key TEXT NOT NULL UNIQUE
            )
            """
        )
    conn.commit()
    conn.close()
    return tmp, db_path


def _label_candidate_handoff_contract(**overrides):
    contract = {
        "ok": True,
        "contract_status": "ready_but_disabled",
        "cex_review_id": 1,
        "final_handoff_target_id": 1,
        "token_symbol": "TEST",
        "market_type": "cex",
        "cex_review_status": "accepted_for_future_cex_review",
        "handoff_target": "cex_label_candidate_review_queue",
        "label_candidate_handoff_dedupe_key": "label-candidate-dedupe",
        "dedupe_status": {
            "dedupe_bound": True,
            "source_digest_bound": True,
            "cex_review_handoff_contract_json_valid": True,
            "cex_review_handoff_contract_json_bound": True,
        },
        "parent_status": {"cex_review_parent_chain_exists": True},
        "blockers": [],
        "would_create_label_candidate": False,
        "would_create_cex_label": False,
        "would_write": False,
        "writes_performed": 0,
        "source_policy": "test label candidate handoff contract",
    }
    contract.update(overrides)
    return contract


def _label_creation_contract(**overrides):
    contract = {
        "ok": True,
        "contract_status": "ready_but_disabled",
        "cex_label_candidate_review_id": 1,
        "cex_review_id": 1,
        "final_handoff_target_id": 1,
        "final_handoff_id": 1,
        "final_target_execution_id": 1,
        "final_apply_id": 1,
        "post_apply_execution_apply_id": 1,
        "post_apply_execution_id": 1,
        "post_apply_insert_id": 1,
        "post_apply_id": 1,
        "business_apply_id": 1,
        "business_execution_id": 1,
        "business_insert_id": 1,
        "business_handoff_id": 1,
        "downstream_id": 1,
        "promotion_id": 1,
        "evidence_id": 1,
        "candidate_id": 1,
        "token_symbol": "TEST",
        "market_type": "cex",
        "cex_label_candidate_status": "accepted_for_future_cex_label_candidate",
        "source_url": "https://example.com/evidence",
        "source_tier": "tier_1",
        "evidence_type": "official_market_page",
        "evidence_preview_digest": "digest",
        "cex_review_handoff_dedupe_key": "cex-review-dedupe",
        "label_candidate_handoff_dedupe_key": "label-candidate-dedupe",
        "label_target": "cex_label_registry_future_review",
        "label_dedupe_key": "label-dedupe",
        "label_proposal": {
            "label_kind": "cex_market_presence_candidate",
            "label_target": "cex_label_registry_future_review",
            "token_symbol": "TEST",
            "market_type": "cex",
            "source_url": "https://example.com/evidence",
            "source_tier": "tier_1",
            "evidence_type": "official_market_page",
            "evidence_preview_digest": "digest",
            "label_dedupe_key": "label-dedupe",
            "direct_label_write": False,
        },
        "label_creation_contract": {
            "contract_kind": "cex_label_creation_contract_not_direct_write",
            "label_target": "cex_label_registry_future_review",
            "payload_preview": {
                "label_kind": "cex_market_presence_candidate",
                "label_target": "cex_label_registry_future_review",
                "token_symbol": "TEST",
                "market_type": "cex",
                "source_url": "https://example.com/evidence",
                "source_tier": "tier_1",
                "evidence_type": "official_market_page",
                "evidence_preview_digest": "digest",
                "label_dedupe_key": "label-dedupe",
                "direct_label_write": False,
            },
            "direct_cex_label_write": False,
        },
        "dedupe_status": {
            "dedupe_bound": True,
            "source_digest_bound": True,
            "label_candidate_handoff_contract_json_valid": True,
            "label_candidate_handoff_contract_json_bound": True,
            "cex_review_handoff_dedupe_key": "cex-review-dedupe",
            "label_candidate_handoff_dedupe_key": "label-candidate-dedupe",
            "label_dedupe_key": "label-dedupe",
        },
        "parent_status": {"cex_label_candidate_parent_chain_exists": True},
        "blockers": [],
        "would_create_cex_label": False,
        "would_write": False,
        "writes_performed": 0,
        "source_policy": "test label creation contract",
    }
    contract.update(overrides)
    return contract


class CexMarketEvidenceReviewQueueSchemaPlanTests(unittest.TestCase):
    def test_ready_contract_returns_read_only_schema_plan(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            plan = onchain_engine.get_cex_market_evidence_review_queue_schema_plan(1, True)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists_after = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_market_evidence_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(plan["plan_status"], "ready")
        self.assertEqual(plan["target_table"], "cex_market_evidence_review_queue")
        self.assertFalse(plan["table_exists"])
        self.assertTrue(plan["migration_required"])
        self.assertIn("cex_review_handoff_dedupe_key TEXT NOT NULL UNIQUE", plan["schema_preview"])
        self.assertTrue(plan["indexes_preview"])
        self.assertEqual(plan["constraints_preview"]["market_type"], ["cex"])
        self.assertEqual(plan["dedupe_constraints"]["cex_review_handoff_dedupe_key"], "cex-review-dedupe")
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_cex_review_row"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_create_dex_router_evidence"])
        self.assertFalse(plan["would_create_mapping"])
        self.assertFalse(plan["would_write"])
        self.assertFalse(plan["would_execute_trade"])
        self.assertFalse(plan["would_create_client_opt_in"])
        self.assertEqual(plan["writes_performed"], 0)
        self.assertFalse(table_exists_after)

    def test_dry_run_false_and_blocked_contract_block_plan(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(contract_status="blocked", blockers=["not_cex_review_handoff_route"]),
            ),
        ):
            blocked = onchain_engine.get_cex_market_evidence_review_queue_schema_plan(1, True)
            real_write = onchain_engine.get_cex_market_evidence_review_queue_schema_plan(1, False)
            missing_id = onchain_engine.get_cex_market_evidence_review_queue_schema_plan(None, True)

        self.assertEqual(blocked["plan_status"], "blocked")
        self.assertIn("cex_review_handoff_contract_not_ready", blocked["blockers"])
        self.assertFalse(blocked["migration_required"])
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_review_handoff_contract_not_ready", real_write["blockers"])
        self.assertIn("final_handoff_target_id_required", missing_id["blockers"])
        self.assertEqual(real_write["writes_performed"], 0)
        self.assertFalse(real_write["would_create_table"])

    def test_existing_table_is_visible_and_not_migration_required(self) -> None:
        tmp, db_path = _with_db(create_target_table=True)
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            plan = onchain_engine.get_cex_market_evidence_review_queue_schema_plan(1, True)

        self.assertEqual(plan["plan_status"], "ready")
        self.assertTrue(plan["table_exists"])
        self.assertFalse(plan["migration_required"])
        self.assertFalse(plan["would_create_table"])

    def test_create_dry_run_does_not_create_table(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            create = onchain_engine.create_cex_market_evidence_review_queue(1, True, None)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_market_evidence_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(create["create_status"], "ready_but_disabled")
        self.assertTrue(create["would_create_table"])
        self.assertFalse(create["table_created"])
        self.assertEqual(create["rows_inserted"], 0)
        self.assertEqual(create["writes_performed"], 0)
        self.assertFalse(table_exists)

    def test_create_without_confirm_is_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            create = onchain_engine.create_cex_market_evidence_review_queue(1, False, None)

        self.assertEqual(create["create_status"], "blocked")
        self.assertIn("confirm_CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE_required", create["blockers"])
        self.assertFalse(create["table_created"])
        self.assertEqual(create["rows_inserted"], 0)
        self.assertEqual(create["writes_performed"], 0)

    def test_confirmed_create_is_ddl_only_and_idempotent(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            first = onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            second = onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_market_evidence_review_queue").fetchone()[0])
                columns = {
                    row[1]
                    for row in check_conn.execute("PRAGMA table_info(cex_market_evidence_review_queue)").fetchall()
                }
                indexes = {
                    row[0]
                    for row in check_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'cex_market_evidence_review_queue'"
                    ).fetchall()
                }
            finally:
                check_conn.close()

        self.assertEqual(first["create_status"], "created")
        self.assertTrue(first["table_created"])
        self.assertGreaterEqual(first["writes_performed"], 1)
        self.assertEqual(first["rows_inserted"], 0)
        self.assertFalse(first["would_create_cex_review_row"])
        self.assertFalse(first["would_create_cex_label"])
        self.assertFalse(first["would_create_dex_router_evidence"])
        self.assertFalse(first["would_create_mapping"])
        self.assertFalse(first["would_execute_trade"])
        self.assertFalse(first["would_create_client_opt_in"])
        self.assertEqual(second["create_status"], "already_exists")
        self.assertFalse(second["table_created"])
        self.assertEqual(second["rows_inserted"], 0)
        self.assertEqual(row_count, 0)
        self.assertIn("cex_review_handoff_dedupe_key", columns)
        self.assertIn("idx_cex_market_evidence_review_queue_dedupe", indexes)

    def test_insert_dry_run_requires_table_and_would_insert(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            missing_table = onchain_engine.insert_cex_market_evidence_review(1, "cex-review-dedupe", True, None)
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            ready = onchain_engine.insert_cex_market_evidence_review(1, "cex-review-dedupe", True, None)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_market_evidence_review_queue").fetchone()[0]
                )
            finally:
                check_conn.close()

        self.assertEqual(missing_table["insert_status"], "blocked")
        self.assertIn("cex_market_evidence_review_queue_missing", missing_table["blockers"])
        self.assertEqual(ready["insert_status"], "ready_but_disabled")
        self.assertTrue(ready["would_insert"])
        self.assertTrue(ready["would_create_cex_review_row"])
        self.assertFalse(ready["would_create_cex_label"])
        self.assertFalse(ready["would_create_dex_router_evidence"])
        self.assertFalse(ready["would_create_mapping"])
        self.assertFalse(ready["would_execute_trade"])
        self.assertFalse(ready["would_create_client_opt_in"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertEqual(row_count, 0)

    def test_insert_confirmed_requires_expected_dedupe_and_blocks_duplicate(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            missing_expected = onchain_engine.insert_cex_market_evidence_review(
                1,
                None,
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            mismatch = onchain_engine.insert_cex_market_evidence_review(
                1,
                "wrong",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            inserted = onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            duplicate = onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_market_evidence_review_queue").fetchone()[0])
                row = check_conn.execute(
                    "SELECT status, cex_review_handoff_dedupe_key FROM cex_market_evidence_review_queue LIMIT 1"
                ).fetchone()
            finally:
                check_conn.close()

        self.assertIn("expected_cex_review_handoff_dedupe_key_required", missing_expected["blockers"])
        self.assertIn("expected_cex_review_handoff_dedupe_key_mismatch", mismatch["blockers"])
        self.assertEqual(inserted["insert_status"], "inserted")
        self.assertTrue(inserted["inserted"])
        self.assertEqual(inserted["writes_performed"], 1)
        self.assertFalse(inserted["would_create_cex_label"])
        self.assertFalse(inserted["would_create_dex_router_evidence"])
        self.assertFalse(inserted["would_create_mapping"])
        self.assertFalse(inserted["would_execute_trade"])
        self.assertFalse(inserted["would_create_client_opt_in"])
        self.assertEqual(duplicate["insert_status"], "blocked")
        self.assertIn("duplicate_cex_review_handoff_dedupe_key", duplicate["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(row[0], "pending_admin_review")
        self.assertEqual(row[1], "cex-review-dedupe")

    def test_review_queue_returns_ready_inserted_cex_review_row(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            review = onchain_engine.get_cex_market_evidence_review_queue_review(
                status="pending_admin_review",
                token_symbol="TEST",
                market_type="cex",
                limit=50,
                dry_run=True,
            )
            real_write = onchain_engine.get_cex_market_evidence_review_queue_review(dry_run=False)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_market_evidence_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(review["queue_status"], "ready")
        self.assertEqual(review["summary"]["total_cex_reviews"], 1)
        self.assertEqual(review["summary"]["ready_for_cex_review_decision_preview"], 1)
        row = review["rows"][0]
        self.assertEqual(row["cex_review_id"], 1)
        self.assertEqual(row["review_readiness"], "ready_for_cex_review_decision_preview")
        self.assertTrue(row["dedupe_bound"])
        self.assertTrue(row["source_digest_bound"])
        self.assertTrue(row["contract_ready_now"])
        self.assertTrue(row["cex_review_handoff_contract_json_valid"])
        self.assertTrue(row["cex_review_handoff_contract_json_bound"])
        self.assertTrue(row["route_consistent"])
        self.assertFalse(row["would_create_cex_label"])
        self.assertFalse(review["would_create_cex_label"])
        self.assertFalse(review["would_create_dex_router_evidence"])
        self.assertFalse(review["would_create_mapping"])
        self.assertFalse(review["would_execute_trade"])
        self.assertFalse(review["would_create_client_opt_in"])
        self.assertFalse(review["would_write"])
        self.assertEqual(review["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertEqual(row_count, 1)

    def test_review_queue_blocks_dedupe_source_json_parent_and_route_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        contract = _contract(
            cex_review_handoff_dedupe_key="current-dedupe",
            source_url="https://example.com/current",
            parent_status={"final_handoff_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_market_evidence_review_queue
                    SET market_type = 'dex',
                        cex_review_handoff_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=contract,
            ),
        ):
            review = onchain_engine.get_cex_market_evidence_review_queue_review(status="all", dry_run=True)

        row = review["rows"][0]
        self.assertEqual(row["review_readiness"], "blocked")
        self.assertIn("cex_review_handoff_dedupe_key_mismatch", row["review_blockers"])
        self.assertIn("source_or_digest_mismatch", row["review_blockers"])
        self.assertIn("invalid_cex_review_handoff_contract_json", row["review_blockers"])
        self.assertIn("parent_chain_not_bound", row["review_blockers"])
        self.assertIn("cex_review_route_mismatch", row["review_blockers"])

    def test_decision_preview_accept_request_and_reject_are_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            accept = onchain_engine.get_cex_market_evidence_review_decision_preview(
                1,
                "accept_for_future_cex_review",
                True,
            )
            request = onchain_engine.get_cex_market_evidence_review_decision_preview(
                1,
                "request_better_source",
                True,
            )
            reject = onchain_engine.get_cex_market_evidence_review_decision_preview(1, "reject", True)
            invalid = onchain_engine.get_cex_market_evidence_review_decision_preview(1, "bad", True)
            real_write = onchain_engine.get_cex_market_evidence_review_decision_preview(
                1,
                "accept_for_future_cex_review",
                False,
            )
            missing = onchain_engine.get_cex_market_evidence_review_decision_preview(
                999,
                "accept_for_future_cex_review",
                True,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_market_evidence_review_queue").fetchone()[0])
                status = check_conn.execute("SELECT status FROM cex_market_evidence_review_queue WHERE id = 1").fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(accept["preview_status"], "ready_but_disabled")
        self.assertTrue(accept["decision_allowed"])
        self.assertEqual(accept["decision_preview"]["future_status"], "accepted_for_future_cex_review")
        self.assertFalse(accept["would_update_cex_review_status"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_create_dex_router_evidence"])
        self.assertFalse(accept["would_create_mapping"])
        self.assertFalse(accept["would_execute_trade"])
        self.assertFalse(accept["would_create_client_opt_in"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")
        self.assertTrue(reject["decision_allowed"])
        self.assertEqual(reject["decision_preview"]["future_status"], "rejected")
        self.assertIn("invalid_proposed_decision", invalid["blockers"])
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_review_missing", missing["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "pending_admin_review")

    def test_decision_preview_accept_blocks_on_review_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "UPDATE cex_market_evidence_review_queue SET market_type = 'dex', source_url = 'https://drift.example' WHERE id = 1"
                )
                conn.commit()
            finally:
                conn.close()

        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            accept = onchain_engine.get_cex_market_evidence_review_decision_preview(
                1,
                "accept_for_future_cex_review",
                True,
            )
            request = onchain_engine.get_cex_market_evidence_review_decision_preview(
                1,
                "request_better_source",
                True,
            )

        self.assertEqual(accept["preview_status"], "blocked")
        self.assertFalse(accept["decision_allowed"])
        self.assertIn("cex_review_not_ready_for_acceptance", accept["blockers"])
        self.assertIn("cex_review_source_digest_not_bound", accept["blockers"])
        self.assertIn("cex_review_route_inconsistent", accept["blockers"])
        self.assertTrue(request["decision_allowed"])

    def test_decision_apply_dry_run_confirm_and_second_apply(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            dry_run = onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                True,
                None,
            )
            no_confirm = onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                None,
            )
            request = onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "request_better_source",
                True,
                None,
            )
            confirmed = onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            second = onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_market_evidence_review_queue").fetchone()[0])
                status = check_conn.execute("SELECT status FROM cex_market_evidence_review_queue WHERE id = 1").fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(dry_run["apply_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_update_cex_review_status"])
        self.assertFalse(dry_run["updated"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("confirm_APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION_required", no_confirm["blockers"])
        self.assertIn("only_accept_for_future_cex_review_can_be_applied", request["blockers"])
        self.assertEqual(confirmed["apply_status"], "updated")
        self.assertTrue(confirmed["updated"])
        self.assertEqual(confirmed["previous_status"], "pending_admin_review")
        self.assertEqual(confirmed["new_status"], "accepted_for_future_cex_review")
        self.assertEqual(confirmed["writes_performed"], 1)
        self.assertFalse(confirmed["would_create_cex_label"])
        self.assertFalse(confirmed["would_create_dex_router_evidence"])
        self.assertFalse(confirmed["would_create_mapping"])
        self.assertFalse(confirmed["would_execute_trade"])
        self.assertFalse(confirmed["would_create_client_opt_in"])
        self.assertEqual(second["apply_status"], "blocked")
        self.assertIn("cex_review_status_not_pending_admin_review", second["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "accepted_for_future_cex_review")

    def test_label_candidate_handoff_contract_ready_and_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            contract = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(1, True)
            real_write = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(1, False)
            missing = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(999, True)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_market_evidence_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(contract["contract_status"], "ready_but_disabled")
        self.assertEqual(contract["cex_review_id"], 1)
        self.assertEqual(contract["cex_review_status"], "accepted_for_future_cex_review")
        self.assertEqual(contract["handoff_target"], "cex_label_candidate_review_queue")
        self.assertTrue(contract["label_candidate_handoff_dedupe_key"])
        self.assertTrue(contract["dedupe_status"]["dedupe_bound"])
        self.assertTrue(contract["dedupe_status"]["source_digest_bound"])
        self.assertTrue(contract["dedupe_status"]["cex_review_handoff_contract_json_valid"])
        self.assertTrue(contract["dedupe_status"]["cex_review_handoff_contract_json_bound"])
        self.assertFalse(contract["would_create_label_candidate"])
        self.assertFalse(contract["would_create_cex_label"])
        self.assertFalse(contract["would_create_dex_router_evidence"])
        self.assertFalse(contract["would_create_mapping"])
        self.assertFalse(contract["would_execute_trade"])
        self.assertFalse(contract["would_create_client_opt_in"])
        self.assertFalse(contract["would_write"])
        self.assertEqual(contract["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_review_missing", missing["blockers"])
        self.assertEqual(row_count, 1)

    def test_label_candidate_handoff_contract_blocks_non_accepted_and_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        drift_contract = _contract(
            cex_review_handoff_dedupe_key="current-dedupe",
            source_url="https://example.com/current",
            parent_status={"final_handoff_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            non_accepted = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(1, True)
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_market_evidence_review_queue
                    SET status = 'accepted_for_future_cex_review',
                        market_type = 'dex',
                        cex_review_handoff_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=drift_contract,
            ),
        ):
            drift = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(1, True)

        self.assertEqual(non_accepted["contract_status"], "blocked")
        self.assertIn("cex_review_not_accepted_for_label_candidate_handoff", non_accepted["blockers"])
        self.assertEqual(drift["contract_status"], "blocked")
        self.assertIn("cex_review_handoff_dedupe_key_mismatch", drift["blockers"])
        self.assertIn("source_or_digest_mismatch", drift["blockers"])
        self.assertIn("invalid_cex_review_handoff_contract_json", drift["blockers"])
        self.assertIn("parent_chain_not_bound", drift["blockers"])
        self.assertIn("cex_review_route_mismatch", drift["blockers"])

    def test_label_candidate_queue_schema_plan_ready_and_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=_label_candidate_handoff_contract(),
            ),
        ):
            plan = onchain_engine.get_cex_label_candidate_review_queue_schema_plan(1, True)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists_after = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_label_candidate_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(plan["plan_status"], "ready")
        self.assertEqual(plan["cex_review_id"], 1)
        self.assertEqual(plan["target_table"], "cex_label_candidate_review_queue")
        self.assertFalse(plan["table_exists"])
        self.assertTrue(plan["migration_required"])
        self.assertIn("label_candidate_handoff_dedupe_key TEXT NOT NULL UNIQUE", plan["schema_preview"])
        self.assertTrue(plan["indexes_preview"])
        self.assertEqual(plan["constraints_preview"]["market_type"], ["cex"])
        self.assertEqual(plan["constraints_preview"]["handoff_target"], ["cex_label_candidate_review_queue"])
        self.assertEqual(plan["dedupe_constraints"]["label_candidate_handoff_dedupe_key"], "label-candidate-dedupe")
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_label_candidate"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_create_dex_router_evidence"])
        self.assertFalse(plan["would_create_mapping"])
        self.assertFalse(plan["would_write"])
        self.assertFalse(plan["would_execute_trade"])
        self.assertFalse(plan["would_create_client_opt_in"])
        self.assertEqual(plan["writes_performed"], 0)
        self.assertFalse(table_exists_after)

    def test_label_candidate_queue_schema_plan_blocks_real_write_and_blocked_contract(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=_label_candidate_handoff_contract(
                    contract_status="blocked",
                    blockers=["cex_review_not_accepted_for_label_candidate_handoff"],
                ),
            ),
        ):
            blocked = onchain_engine.get_cex_label_candidate_review_queue_schema_plan(1, True)
            real_write = onchain_engine.get_cex_label_candidate_review_queue_schema_plan(1, False)
            missing_id = onchain_engine.get_cex_label_candidate_review_queue_schema_plan(None, True)

        self.assertEqual(blocked["plan_status"], "blocked")
        self.assertIn("label_candidate_handoff_contract_not_ready", blocked["blockers"])
        self.assertFalse(blocked["migration_required"])
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("label_candidate_handoff_contract_not_ready", real_write["blockers"])
        self.assertIn("cex_review_id_required", missing_id["blockers"])
        self.assertFalse(real_write["would_create_table"])
        self.assertEqual(real_write["writes_performed"], 0)

    def test_label_candidate_queue_schema_plan_sees_existing_table(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE cex_label_candidate_review_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label_candidate_handoff_dedupe_key TEXT NOT NULL UNIQUE
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=_label_candidate_handoff_contract(),
            ),
        ):
            plan = onchain_engine.get_cex_label_candidate_review_queue_schema_plan(1, True)

        self.assertEqual(plan["plan_status"], "ready")
        self.assertTrue(plan["table_exists"])
        self.assertFalse(plan["migration_required"])
        self.assertFalse(plan["would_create_table"])

    def test_label_candidate_queue_create_dry_run_does_not_create_table(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=_label_candidate_handoff_contract(),
            ),
        ):
            create = onchain_engine.create_cex_label_candidate_review_queue(1, True, None)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_label_candidate_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(create["create_status"], "ready_but_disabled")
        self.assertTrue(create["would_create_table"])
        self.assertFalse(create["table_created"])
        self.assertEqual(create["rows_inserted"], 0)
        self.assertEqual(create["writes_performed"], 0)
        self.assertFalse(create["would_create_label_candidate"])
        self.assertFalse(create["would_create_cex_label"])
        self.assertFalse(table_exists)

    def test_label_candidate_queue_create_without_confirm_is_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=_label_candidate_handoff_contract(),
            ),
        ):
            create = onchain_engine.create_cex_label_candidate_review_queue(1, False, None)

        self.assertEqual(create["create_status"], "blocked")
        self.assertIn("confirm_CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE_required", create["blockers"])
        self.assertFalse(create["table_created"])
        self.assertEqual(create["rows_inserted"], 0)
        self.assertEqual(create["writes_performed"], 0)

    def test_label_candidate_queue_confirmed_create_is_ddl_only_and_idempotent(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=_label_candidate_handoff_contract(),
            ),
        ):
            first = onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            second = onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_candidate_review_queue").fetchone()[0])
                columns = {
                    row[1]
                    for row in check_conn.execute("PRAGMA table_info(cex_label_candidate_review_queue)").fetchall()
                }
                indexes = {
                    row[0]
                    for row in check_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'cex_label_candidate_review_queue'"
                    ).fetchall()
                }
            finally:
                check_conn.close()

        self.assertEqual(first["create_status"], "created")
        self.assertTrue(first["table_created"])
        self.assertGreaterEqual(first["writes_performed"], 1)
        self.assertEqual(first["rows_inserted"], 0)
        self.assertFalse(first["would_create_label_candidate"])
        self.assertFalse(first["would_create_cex_label"])
        self.assertFalse(first["would_create_dex_router_evidence"])
        self.assertFalse(first["would_create_mapping"])
        self.assertFalse(first["would_execute_trade"])
        self.assertFalse(first["would_create_client_opt_in"])
        self.assertEqual(second["create_status"], "already_exists")
        self.assertFalse(second["table_created"])
        self.assertEqual(second["rows_inserted"], 0)
        self.assertEqual(row_count, 0)
        self.assertIn("label_candidate_handoff_dedupe_key", columns)
        self.assertIn("idx_cex_label_candidate_review_queue_dedupe", indexes)

    def test_label_candidate_insert_dry_run_requires_table_and_would_insert(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            missing_table = onchain_engine.insert_cex_label_candidate_review(
                1,
                "label-candidate-dedupe",
                True,
                None,
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            ready = onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                True,
                None,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_label_candidate_review_queue").fetchone()[0]
                )
            finally:
                check_conn.close()

        self.assertEqual(missing_table["insert_status"], "blocked")
        self.assertIn("cex_label_candidate_review_queue_missing", missing_table["blockers"])
        self.assertEqual(ready["insert_status"], "ready_but_disabled")
        self.assertTrue(ready["would_insert"])
        self.assertFalse(ready["would_create_label_candidate"])
        self.assertFalse(ready["would_create_cex_label"])
        self.assertFalse(ready["would_create_dex_router_evidence"])
        self.assertFalse(ready["would_create_mapping"])
        self.assertFalse(ready["would_execute_trade"])
        self.assertFalse(ready["would_create_client_opt_in"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertEqual(row_count, 0)

    def test_label_candidate_insert_confirmed_requires_expected_dedupe_and_blocks_duplicate(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            missing_expected = onchain_engine.insert_cex_label_candidate_review(
                1,
                None,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            mismatch = onchain_engine.insert_cex_label_candidate_review(
                1,
                "wrong",
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            inserted = onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            duplicate = onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_candidate_review_queue").fetchone()[0])
                row = check_conn.execute(
                    """
                    SELECT status, label_candidate_handoff_dedupe_key, market_type, handoff_target
                    FROM cex_label_candidate_review_queue
                    LIMIT 1
                    """
                ).fetchone()
            finally:
                check_conn.close()

        self.assertIn("expected_label_candidate_handoff_dedupe_key_required", missing_expected["blockers"])
        self.assertIn("expected_label_candidate_handoff_dedupe_key_mismatch", mismatch["blockers"])
        self.assertEqual(inserted["insert_status"], "inserted")
        self.assertTrue(inserted["inserted"])
        self.assertEqual(inserted["writes_performed"], 1)
        self.assertFalse(inserted["would_create_label_candidate"])
        self.assertFalse(inserted["would_create_cex_label"])
        self.assertFalse(inserted["would_create_dex_router_evidence"])
        self.assertFalse(inserted["would_create_mapping"])
        self.assertFalse(inserted["would_execute_trade"])
        self.assertFalse(inserted["would_create_client_opt_in"])
        self.assertEqual(duplicate["insert_status"], "blocked")
        self.assertIn("duplicate_label_candidate_handoff_dedupe_key", duplicate["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(row[0], "pending_admin_review")
        self.assertEqual(row[1], expected)
        self.assertEqual(row[2], "cex")
        self.assertEqual(row[3], "cex_label_candidate_review_queue")

    def test_label_candidate_review_queue_returns_ready_inserted_row(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            review = onchain_engine.get_cex_label_candidate_review_queue_review(
                status="pending_admin_review",
                token_symbol="TEST",
                market_type="cex",
                limit=50,
                dry_run=True,
            )
            real_write = onchain_engine.get_cex_label_candidate_review_queue_review(dry_run=False)

        self.assertEqual(review["queue_status"], "ready")
        self.assertEqual(review["summary"]["total_cex_label_candidates"], 1)
        self.assertEqual(review["summary"]["ready_for_cex_label_candidate_decision_preview"], 1)
        self.assertEqual(review["summary"]["blocked"], 0)
        row = review["rows"][0]
        self.assertEqual(row["cex_label_candidate_review_id"], 1)
        self.assertEqual(row["cex_review_id"], 1)
        self.assertEqual(row["review_readiness"], "ready_for_cex_label_candidate_decision_preview")
        self.assertTrue(row["dedupe_bound"])
        self.assertTrue(row["source_digest_bound"])
        self.assertTrue(row["contract_ready_now"])
        self.assertTrue(row["label_candidate_handoff_contract_json_valid"])
        self.assertTrue(row["label_candidate_handoff_contract_json_bound"])
        self.assertTrue(row["route_consistent"])
        self.assertFalse(row["would_create_cex_label"])
        self.assertFalse(row["would_create_dex_router_evidence"])
        self.assertFalse(row["would_create_mapping"])
        self.assertFalse(row["would_execute_trade"])
        self.assertFalse(row["would_create_client_opt_in"])
        self.assertFalse(row["would_write"])
        self.assertFalse(review["would_create_cex_label"])
        self.assertFalse(review["would_write"])
        self.assertEqual(review["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])

    def test_label_candidate_review_queue_blocks_dedupe_source_json_parent_and_route_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_label_candidate_review_queue
                    SET label_candidate_handoff_dedupe_key = 'stale',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        label_candidate_handoff_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        drift_contract = _label_candidate_handoff_contract(
            label_candidate_handoff_dedupe_key="current",
            parent_status={"final_handoff_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=drift_contract,
            ),
        ):
            review = onchain_engine.get_cex_label_candidate_review_queue_review(status="all", dry_run=True)

        self.assertEqual(review["summary"]["blocked"], 1)
        row = review["rows"][0]
        self.assertEqual(row["review_readiness"], "blocked")
        self.assertIn("label_candidate_handoff_dedupe_key_mismatch", row["review_blockers"])
        self.assertIn("source_or_digest_mismatch", row["review_blockers"])
        self.assertIn("invalid_label_candidate_handoff_contract_json", row["review_blockers"])
        self.assertIn("parent_chain_not_bound", row["review_blockers"])
        self.assertIn("cex_label_candidate_route_mismatch", row["review_blockers"])

    def test_label_candidate_decision_preview_accept_request_and_reject_are_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            accept = onchain_engine.get_cex_label_candidate_review_decision_preview(
                1,
                "accept_for_future_cex_label_candidate",
                True,
            )
            request = onchain_engine.get_cex_label_candidate_review_decision_preview(
                1,
                "request_better_source",
                True,
            )
            reject = onchain_engine.get_cex_label_candidate_review_decision_preview(
                1,
                "reject",
                True,
            )
            real_write = onchain_engine.get_cex_label_candidate_review_decision_preview(
                1,
                "accept_for_future_cex_label_candidate",
                False,
            )
            invalid = onchain_engine.get_cex_label_candidate_review_decision_preview(1, "approve", True)
            missing = onchain_engine.get_cex_label_candidate_review_decision_preview(999, "reject", True)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_candidate_review_queue").fetchone()[0])
                status = check_conn.execute("SELECT status FROM cex_label_candidate_review_queue WHERE id = 1").fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(accept["preview_status"], "ready_but_disabled")
        self.assertTrue(accept["decision_allowed"])
        self.assertEqual(accept["decision_preview"]["future_status"], "accepted_for_future_cex_label_candidate")
        self.assertEqual(accept["decision_preview"]["next_step"], "cex_label_candidate_status_only_apply_not_label_write")
        self.assertFalse(accept["would_update_cex_label_candidate_status"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_create_dex_router_evidence"])
        self.assertFalse(accept["would_create_mapping"])
        self.assertFalse(accept["would_execute_trade"])
        self.assertFalse(accept["would_create_client_opt_in"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")
        self.assertTrue(reject["decision_allowed"])
        self.assertEqual(reject["decision_preview"]["future_status"], "rejected")
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("invalid_proposed_decision", invalid["blockers"])
        self.assertIn("cex_label_candidate_review_missing", missing["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "pending_admin_review")

    def test_label_candidate_decision_preview_blocks_accept_on_drift_but_request_allowed(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_label_candidate_review_queue
                    SET label_candidate_handoff_dedupe_key = 'stale',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        label_candidate_handoff_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        drift_contract = _label_candidate_handoff_contract(
            label_candidate_handoff_dedupe_key="current",
            parent_status={"final_handoff_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=drift_contract,
            ),
        ):
            accept = onchain_engine.get_cex_label_candidate_review_decision_preview(
                1,
                "accept_for_future_cex_label_candidate",
                True,
            )
            request = onchain_engine.get_cex_label_candidate_review_decision_preview(
                1,
                "request_better_source",
                True,
            )

        self.assertEqual(accept["preview_status"], "blocked")
        self.assertFalse(accept["decision_allowed"])
        self.assertIn("cex_label_candidate_not_ready_for_acceptance", accept["blockers"])
        self.assertIn("cex_label_candidate_dedupe_not_bound", accept["blockers"])
        self.assertIn("cex_label_candidate_source_digest_not_bound", accept["blockers"])
        self.assertIn("invalid_label_candidate_handoff_contract_json", accept["blockers"])
        self.assertIn("parent_chain_not_bound", accept["blockers"])
        self.assertIn("cex_label_candidate_route_inconsistent", accept["blockers"])
        self.assertIn("non_cex_label_candidate_cannot_accept", accept["blockers"])
        self.assertTrue(request["decision_allowed"])

    def test_label_candidate_decision_apply_dry_run_confirm_and_second_apply(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            dry_run = onchain_engine.apply_cex_label_candidate_review_decision(
                1,
                "accept_for_future_cex_label_candidate",
                True,
                None,
            )
            no_confirm = onchain_engine.apply_cex_label_candidate_review_decision(
                1,
                "accept_for_future_cex_label_candidate",
                False,
                None,
            )
            request = onchain_engine.apply_cex_label_candidate_review_decision(
                1,
                "request_better_source",
                True,
                None,
            )
            confirmed = onchain_engine.apply_cex_label_candidate_review_decision(
                1,
                "accept_for_future_cex_label_candidate",
                False,
                "APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION",
            )
            second = onchain_engine.apply_cex_label_candidate_review_decision(
                1,
                "accept_for_future_cex_label_candidate",
                False,
                "APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_candidate_review_queue").fetchone()[0])
                status = check_conn.execute(
                    "SELECT status FROM cex_label_candidate_review_queue WHERE id = 1"
                ).fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(dry_run["apply_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_update_cex_label_candidate_status"])
        self.assertFalse(dry_run["updated"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("confirm_APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION_required", no_confirm["blockers"])
        self.assertIn("only_accept_for_future_cex_label_candidate_can_be_applied", request["blockers"])
        self.assertEqual(confirmed["apply_status"], "updated")
        self.assertTrue(confirmed["updated"])
        self.assertEqual(confirmed["previous_status"], "pending_admin_review")
        self.assertEqual(confirmed["new_status"], "accepted_for_future_cex_label_candidate")
        self.assertEqual(confirmed["writes_performed"], 1)
        self.assertFalse(confirmed["would_create_cex_label"])
        self.assertFalse(confirmed["would_create_dex_router_evidence"])
        self.assertFalse(confirmed["would_create_mapping"])
        self.assertFalse(confirmed["would_execute_trade"])
        self.assertFalse(confirmed["would_create_client_opt_in"])
        self.assertEqual(second["apply_status"], "blocked")
        self.assertIn("cex_label_candidate_status_not_pending_admin_review", second["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "accepted_for_future_cex_label_candidate")

    def test_label_creation_contract_ready_and_read_only_after_candidate_accept(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            onchain_engine.apply_cex_label_candidate_review_decision(
                1,
                "accept_for_future_cex_label_candidate",
                False,
                "APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION",
            )
            contract = onchain_engine.get_cex_label_creation_contract(1, True)
            real_write = onchain_engine.get_cex_label_creation_contract(1, False)
            missing = onchain_engine.get_cex_label_creation_contract(999, True)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_candidate_review_queue").fetchone()[0])
                status = check_conn.execute(
                    "SELECT status FROM cex_label_candidate_review_queue WHERE id = 1"
                ).fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(contract["contract_status"], "ready_but_disabled")
        self.assertEqual(contract["cex_label_candidate_review_id"], 1)
        self.assertEqual(contract["cex_label_candidate_status"], "accepted_for_future_cex_label_candidate")
        self.assertEqual(contract["label_proposal"]["label_kind"], "cex_market_presence_candidate")
        self.assertEqual(contract["label_proposal"]["token_symbol"], "TEST")
        self.assertEqual(contract["label_proposal"]["market_type"], "cex")
        self.assertTrue(contract["label_dedupe_key"])
        self.assertTrue(contract["dedupe_status"]["dedupe_bound"])
        self.assertTrue(contract["dedupe_status"]["source_digest_bound"])
        self.assertTrue(contract["dedupe_status"]["label_candidate_handoff_contract_json_valid"])
        self.assertTrue(contract["dedupe_status"]["label_candidate_handoff_contract_json_bound"])
        self.assertTrue(contract["routing_safety"]["cex_label_creation_not_enabled"])
        self.assertFalse(contract["would_create_cex_label"])
        self.assertFalse(contract["would_create_dex_router_evidence"])
        self.assertFalse(contract["would_create_mapping"])
        self.assertFalse(contract["would_execute_trade"])
        self.assertFalse(contract["would_create_client_opt_in"])
        self.assertFalse(contract["would_write"])
        self.assertEqual(contract["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_label_candidate_review_missing", missing["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "accepted_for_future_cex_label_candidate")

    def test_label_creation_contract_blocks_non_accepted_and_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract",
                return_value=_contract(),
            ),
        ):
            onchain_engine.create_cex_market_evidence_review_queue(
                1,
                False,
                "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_market_evidence_review(
                1,
                "cex-review-dedupe",
                False,
                "INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            )
            onchain_engine.apply_cex_market_evidence_review_decision(
                1,
                "accept_for_future_cex_review",
                False,
                "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_label_candidate_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
            )
            expected = onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract(
                1,
                True,
            )["label_candidate_handoff_dedupe_key"]
            onchain_engine.insert_cex_label_candidate_review(
                1,
                expected,
                False,
                "INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            )
            non_accepted = onchain_engine.get_cex_label_creation_contract(1, True)
            onchain_engine.apply_cex_label_candidate_review_decision(
                1,
                "accept_for_future_cex_label_candidate",
                False,
                "APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_label_candidate_review_queue
                    SET label_candidate_handoff_dedupe_key = 'stale',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        label_candidate_handoff_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        drift_contract = _label_candidate_handoff_contract(
            label_candidate_handoff_dedupe_key="current",
            parent_status={"final_handoff_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_market_evidence_review_label_candidate_handoff_contract",
                return_value=drift_contract,
            ),
        ):
            drift = onchain_engine.get_cex_label_creation_contract(1, True)

        self.assertEqual(non_accepted["contract_status"], "blocked")
        self.assertIn("cex_label_candidate_not_accepted_for_label_creation_contract", non_accepted["blockers"])
        self.assertEqual(drift["contract_status"], "blocked")
        self.assertIn("label_candidate_handoff_dedupe_key_mismatch", drift["blockers"])
        self.assertIn("source_or_digest_mismatch", drift["blockers"])
        self.assertIn("invalid_label_candidate_handoff_contract_json", drift["blockers"])
        self.assertIn("parent_chain_not_bound", drift["blockers"])
        self.assertIn("cex_label_creation_route_mismatch", drift["blockers"])
        self.assertFalse(drift["would_create_cex_label"])
        self.assertFalse(drift["would_write"])
        self.assertEqual(drift["writes_performed"], 0)

    def test_label_creation_queue_schema_plan_ready_and_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        contract = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_label_candidate_review_id": 1,
            "token_symbol": "TEST",
            "market_type": "cex",
            "label_target": "cex_label_registry_future_review",
            "label_proposal": {
                "label_kind": "cex_market_presence_candidate",
                "token_symbol": "TEST",
            },
            "label_dedupe_key": "label-dedupe",
            "blockers": [],
            "would_create_cex_label": False,
            "would_write": False,
            "writes_performed": 0,
        }
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=contract),
        ):
            plan = onchain_engine.get_cex_label_creation_queue_schema_plan(1, True)
            real_write = onchain_engine.get_cex_label_creation_queue_schema_plan(1, False)
            missing_id = onchain_engine.get_cex_label_creation_queue_schema_plan(None, True)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_label_creation_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(plan["plan_status"], "ready")
        self.assertEqual(plan["target_table"], "cex_label_creation_review_queue")
        self.assertFalse(plan["table_exists"])
        self.assertTrue(plan["migration_required"])
        self.assertIn("label_dedupe_key TEXT NOT NULL UNIQUE", plan["schema_preview"])
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_cex_label_creation_review_queue_dedupe", plan["indexes_preview"][0])
        self.assertEqual(plan["constraints_preview"]["market_type"], ["cex"])
        self.assertFalse(plan["constraints_preview"]["direct_cex_label_write_allowed"])
        self.assertFalse(plan["constraints_preview"]["label_table_mutation_allowed"])
        self.assertEqual(plan["dedupe_constraints"]["label_dedupe_key"], "label-dedupe")
        self.assertEqual(plan["label_dedupe_key"], "label-dedupe")
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_label_creation_row"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_write"])
        self.assertEqual(plan["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_label_candidate_review_id_required", missing_id["blockers"])
        self.assertFalse(table_exists)

    def test_label_creation_queue_schema_plan_blocks_when_contract_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        blocked_contract = {
            "ok": True,
            "contract_status": "blocked",
            "cex_label_candidate_review_id": 1,
            "label_dedupe_key": None,
            "blockers": ["cex_label_candidate_not_accepted_for_label_creation_contract"],
            "would_create_cex_label": False,
            "would_write": False,
            "writes_performed": 0,
        }
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=blocked_contract),
        ):
            plan = onchain_engine.get_cex_label_creation_queue_schema_plan(1, True)

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertIn("cex_label_creation_contract_not_ready", plan["blockers"])
        self.assertFalse(plan["migration_required"])
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_write"])
        self.assertEqual(plan["writes_performed"], 0)

    def test_label_creation_review_queue_create_dry_run_does_not_create_table(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        contract = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_label_candidate_review_id": 1,
            "label_dedupe_key": "label-dedupe",
            "blockers": [],
            "would_create_cex_label": False,
            "would_write": False,
            "writes_performed": 0,
        }
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=contract),
        ):
            create = onchain_engine.create_cex_label_creation_review_queue(1, True, None)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_label_creation_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(create["create_status"], "ready_but_disabled")
        self.assertTrue(create["would_create_table"])
        self.assertFalse(create["table_created"])
        self.assertEqual(create["rows_inserted"], 0)
        self.assertEqual(create["writes_performed"], 0)
        self.assertFalse(create["would_create_label_creation_row"])
        self.assertFalse(create["would_create_cex_label"])
        self.assertFalse(table_exists)

    def test_label_creation_review_queue_create_without_confirm_is_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        contract = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_label_candidate_review_id": 1,
            "label_dedupe_key": "label-dedupe",
            "blockers": [],
        }
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=contract),
        ):
            create = onchain_engine.create_cex_label_creation_review_queue(1, False, None)

        self.assertEqual(create["create_status"], "blocked")
        self.assertIn("confirm_CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE_required", create["blockers"])
        self.assertFalse(create["table_created"])
        self.assertEqual(create["rows_inserted"], 0)
        self.assertEqual(create["writes_performed"], 0)

    def test_label_creation_review_queue_confirmed_create_is_ddl_only_and_idempotent(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        contract = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_label_candidate_review_id": 1,
            "label_dedupe_key": "label-dedupe",
            "blockers": [],
        }
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=contract),
        ):
            first = onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            second = onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
                columns = {
                    row[1]
                    for row in check_conn.execute("PRAGMA table_info(cex_label_creation_review_queue)").fetchall()
                }
                indexes = {
                    row[0]
                    for row in check_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'cex_label_creation_review_queue'"
                    ).fetchall()
                }
            finally:
                check_conn.close()

        self.assertEqual(first["create_status"], "created")
        self.assertTrue(first["table_created"])
        self.assertGreaterEqual(first["writes_performed"], 1)
        self.assertEqual(first["rows_inserted"], 0)
        self.assertFalse(first["would_create_label_creation_row"])
        self.assertFalse(first["would_create_cex_label"])
        self.assertFalse(first["would_create_dex_router_evidence"])
        self.assertFalse(first["would_create_mapping"])
        self.assertFalse(first["would_execute_trade"])
        self.assertFalse(first["would_create_client_opt_in"])
        self.assertEqual(second["create_status"], "already_exists")
        self.assertFalse(second["table_created"])
        self.assertEqual(second["rows_inserted"], 0)
        self.assertEqual(row_count, 0)
        self.assertIn("label_dedupe_key", columns)
        self.assertIn("label_creation_contract_json", columns)
        self.assertIn("idx_cex_label_creation_review_queue_dedupe", indexes)

    def test_label_creation_review_insert_dry_run_requires_table_and_would_insert(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            missing_table = onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                True,
                None,
            )
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            ready = onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                True,
                None,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(missing_table["insert_status"], "blocked")
        self.assertIn("cex_label_creation_review_queue_missing", missing_table["blockers"])
        self.assertEqual(ready["insert_status"], "ready_but_disabled")
        self.assertTrue(ready["would_insert"])
        self.assertFalse(ready["would_create_label_creation_row"])
        self.assertFalse(ready["would_create_cex_label"])
        self.assertFalse(ready["would_create_dex_router_evidence"])
        self.assertFalse(ready["would_create_mapping"])
        self.assertFalse(ready["would_execute_trade"])
        self.assertFalse(ready["would_create_client_opt_in"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertEqual(row_count, 0)

    def test_label_creation_review_insert_confirmed_requires_expected_dedupe_and_blocks_duplicate(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            missing_expected = onchain_engine.insert_cex_label_creation_review(
                1,
                None,
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            mismatch = onchain_engine.insert_cex_label_creation_review(
                1,
                "wrong",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            inserted = onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            duplicate = onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
                row = check_conn.execute(
                    """
                    SELECT status, label_dedupe_key, market_type, label_target, label_kind
                    FROM cex_label_creation_review_queue
                    LIMIT 1
                    """
                ).fetchone()
            finally:
                check_conn.close()

        self.assertIn("expected_label_dedupe_key_required", missing_expected["blockers"])
        self.assertIn("expected_label_dedupe_key_mismatch", mismatch["blockers"])
        self.assertEqual(inserted["insert_status"], "inserted")
        self.assertTrue(inserted["inserted"])
        self.assertEqual(inserted["writes_performed"], 1)
        self.assertFalse(inserted["would_create_label_creation_row"])
        self.assertFalse(inserted["would_create_cex_label"])
        self.assertFalse(inserted["would_create_dex_router_evidence"])
        self.assertFalse(inserted["would_create_mapping"])
        self.assertFalse(inserted["would_execute_trade"])
        self.assertFalse(inserted["would_create_client_opt_in"])
        self.assertEqual(duplicate["insert_status"], "blocked")
        self.assertIn("duplicate_label_dedupe_key", duplicate["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(row[0], "pending_admin_review")
        self.assertEqual(row[1], "label-dedupe")
        self.assertEqual(row[2], "cex")
        self.assertEqual(row[3], "cex_label_registry_future_review")
        self.assertEqual(row[4], "cex_market_presence_candidate")

    def test_label_creation_review_queue_returns_ready_inserted_row(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            review = onchain_engine.get_cex_label_creation_review_queue_review(
                status="pending_admin_review",
                token_symbol="TEST",
                market_type="cex",
                limit=50,
                dry_run=True,
            )
            real_write = onchain_engine.get_cex_label_creation_review_queue_review(dry_run=False)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(review["queue_status"], "ready")
        self.assertEqual(review["summary"]["total_cex_label_creation_reviews"], 1)
        self.assertEqual(review["summary"]["ready_for_cex_label_creation_decision_preview"], 1)
        self.assertEqual(review["summary"]["blocked"], 0)
        row = review["rows"][0]
        self.assertEqual(row["cex_label_creation_review_id"], 1)
        self.assertEqual(row["cex_label_candidate_review_id"], 1)
        self.assertEqual(row["review_readiness"], "ready_for_cex_label_creation_decision_preview")
        self.assertTrue(row["dedupe_bound"])
        self.assertTrue(row["source_digest_bound"])
        self.assertTrue(row["contract_ready_now"])
        self.assertTrue(row["label_creation_contract_json_valid"])
        self.assertTrue(row["label_creation_contract_json_bound"])
        self.assertTrue(row["route_consistent"])
        self.assertFalse(row["would_create_cex_label"])
        self.assertFalse(row["would_create_dex_router_evidence"])
        self.assertFalse(row["would_create_mapping"])
        self.assertFalse(row["would_execute_trade"])
        self.assertFalse(row["would_create_client_opt_in"])
        self.assertFalse(row["would_write"])
        self.assertFalse(review["would_create_cex_label"])
        self.assertFalse(review["would_write"])
        self.assertEqual(review["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertEqual(row_count, 1)

    def test_label_creation_review_queue_blocks_dedupe_source_json_parent_and_route_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_label_creation_review_queue
                    SET label_dedupe_key = 'stale',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        label_creation_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        drift_contract = _label_creation_contract(
            label_dedupe_key="current",
            parent_status={"cex_label_candidate_parent_chain_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=drift_contract),
        ):
            review = onchain_engine.get_cex_label_creation_review_queue_review(status="all", dry_run=True)

        self.assertEqual(review["summary"]["blocked"], 1)
        row = review["rows"][0]
        self.assertEqual(row["review_readiness"], "blocked")
        self.assertIn("label_dedupe_key_mismatch", row["review_blockers"])
        self.assertIn("source_or_digest_mismatch", row["review_blockers"])
        self.assertIn("invalid_label_creation_contract_json", row["review_blockers"])
        self.assertIn("parent_chain_not_bound", row["review_blockers"])
        self.assertIn("cex_label_creation_route_mismatch", row["review_blockers"])
        self.assertFalse(row["would_create_cex_label"])
        self.assertFalse(row["would_write"])

    def test_label_creation_decision_preview_allows_ready_accept_and_stays_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            accept = onchain_engine.get_cex_label_creation_review_decision_preview(
                1,
                "accept_for_future_cex_label_creation",
                True,
            )
            request = onchain_engine.get_cex_label_creation_review_decision_preview(
                1,
                "request_better_source",
                True,
            )
            reject = onchain_engine.get_cex_label_creation_review_decision_preview(1, "reject", True)
            invalid = onchain_engine.get_cex_label_creation_review_decision_preview(1, "approve", True)
            missing = onchain_engine.get_cex_label_creation_review_decision_preview(
                999,
                "accept_for_future_cex_label_creation",
                True,
            )
            real_write = onchain_engine.get_cex_label_creation_review_decision_preview(
                1,
                "accept_for_future_cex_label_creation",
                False,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
                status = check_conn.execute("SELECT status FROM cex_label_creation_review_queue WHERE id = 1").fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(accept["preview_status"], "ready_but_disabled")
        self.assertTrue(accept["decision_allowed"])
        self.assertEqual(accept["decision_preview"]["future_status"], "accepted_for_future_cex_label_creation")
        self.assertEqual(accept["required_future_confirm"], "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION")
        self.assertFalse(accept["would_update_cex_label_creation_status"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_create_dex_router_evidence"])
        self.assertFalse(accept["would_create_mapping"])
        self.assertFalse(accept["would_execute_trade"])
        self.assertFalse(accept["would_create_client_opt_in"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")
        self.assertTrue(reject["decision_allowed"])
        self.assertEqual(reject["decision_preview"]["future_status"], "rejected")
        self.assertFalse(invalid["decision_allowed"])
        self.assertIn("invalid_proposed_decision", invalid["blockers"])
        self.assertFalse(missing["decision_allowed"])
        self.assertIn("cex_label_creation_review_missing", missing["blockers"])
        self.assertFalse(real_write["decision_allowed"])
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "pending_admin_review")

    def test_label_creation_decision_preview_blocks_accept_on_drift_but_allows_request(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_label_creation_review_queue
                    SET label_dedupe_key = 'stale',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        label_creation_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        drift_contract = _label_creation_contract(
            label_dedupe_key="current",
            parent_status={"cex_label_candidate_parent_chain_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=drift_contract),
        ):
            accept = onchain_engine.get_cex_label_creation_review_decision_preview(
                1,
                "accept_for_future_cex_label_creation",
                True,
            )
            request = onchain_engine.get_cex_label_creation_review_decision_preview(
                1,
                "request_better_source",
                True,
            )

        self.assertEqual(accept["preview_status"], "blocked")
        self.assertFalse(accept["decision_allowed"])
        self.assertIn("cex_label_creation_not_ready_for_acceptance", accept["blockers"])
        self.assertIn("cex_label_creation_dedupe_not_bound", accept["blockers"])
        self.assertIn("cex_label_creation_source_digest_not_bound", accept["blockers"])
        self.assertIn("invalid_label_creation_contract_json", accept["blockers"])
        self.assertIn("parent_chain_not_bound", accept["blockers"])
        self.assertIn("cex_label_creation_route_inconsistent", accept["blockers"])
        self.assertIn("non_cex_label_creation_cannot_accept", accept["blockers"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)
        self.assertEqual(request["preview_status"], "ready_but_disabled")
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")

    def test_label_creation_decision_apply_updates_only_status_after_confirm(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            dry_run = onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                True,
                None,
            )
            no_confirm = onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                None,
            )
            request = onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "request_better_source",
                True,
                None,
            )
            confirmed = onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            second = onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
                status = check_conn.execute(
                    "SELECT status FROM cex_label_creation_review_queue WHERE id = 1"
                ).fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(dry_run["apply_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_update_cex_label_creation_status"])
        self.assertFalse(dry_run["updated"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("confirm_APPLY_CEX_LABEL_CREATION_REVIEW_DECISION_required", no_confirm["blockers"])
        self.assertIn("only_accept_for_future_cex_label_creation_can_be_applied", request["blockers"])
        self.assertEqual(confirmed["apply_status"], "updated")
        self.assertTrue(confirmed["updated"])
        self.assertEqual(confirmed["previous_status"], "pending_admin_review")
        self.assertEqual(confirmed["new_status"], "accepted_for_future_cex_label_creation")
        self.assertEqual(confirmed["writes_performed"], 1)
        self.assertFalse(confirmed["would_create_cex_label"])
        self.assertFalse(confirmed["would_create_dex_router_evidence"])
        self.assertFalse(confirmed["would_create_mapping"])
        self.assertFalse(confirmed["would_execute_trade"])
        self.assertFalse(confirmed["would_create_client_opt_in"])
        self.assertEqual(second["apply_status"], "blocked")
        self.assertIn("cex_label_creation_status_not_pending_admin_review", second["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "accepted_for_future_cex_label_creation")

    def test_final_label_write_contract_ready_after_label_creation_accept(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            blocked_before_accept = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            real_write = onchain_engine.get_cex_final_label_write_contract(1, False)
            missing = onchain_engine.get_cex_final_label_write_contract(999, True)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
                status = check_conn.execute(
                    "SELECT status FROM cex_label_creation_review_queue WHERE id = 1"
                ).fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(blocked_before_accept["contract_status"], "blocked")
        self.assertIn(
            "cex_label_creation_not_accepted_for_final_label_write_contract",
            blocked_before_accept["blockers"],
        )
        self.assertEqual(contract["contract_status"], "ready_but_disabled")
        self.assertEqual(contract["cex_label_creation_review_id"], 1)
        self.assertEqual(contract["cex_label_creation_status"], "accepted_for_future_cex_label_creation")
        self.assertEqual(contract["final_label_target_table"], "cex_token_market_labels_future")
        self.assertEqual(contract["label_write_proposal"]["token_symbol"], "TEST")
        self.assertEqual(contract["label_write_proposal"]["label_kind"], "cex_market_presence_candidate")
        self.assertTrue(contract["final_label_dedupe_key"])
        self.assertTrue(contract["dedupe_status"]["dedupe_bound"])
        self.assertTrue(contract["dedupe_status"]["source_digest_bound"])
        self.assertTrue(contract["dedupe_status"]["label_creation_contract_json_valid"])
        self.assertTrue(contract["dedupe_status"]["label_creation_contract_json_bound"])
        self.assertTrue(all(contract["parent_status"].values()))
        self.assertTrue(contract["routing_safety"]["cex_only"])
        self.assertFalse(contract["would_create_cex_label"])
        self.assertFalse(contract["would_mutate_label_table"])
        self.assertFalse(contract["would_create_dex_router_evidence"])
        self.assertFalse(contract["would_create_mapping"])
        self.assertFalse(contract["would_execute_trade"])
        self.assertFalse(contract["would_create_client_opt_in"])
        self.assertFalse(contract["would_write"])
        self.assertEqual(contract["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_label_creation_review_missing", missing["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "accepted_for_future_cex_label_creation")

    def test_final_label_write_contract_blocks_dedupe_source_json_parent_and_route_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_label_creation_review_queue
                    SET label_dedupe_key = 'stale',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        label_creation_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        drift_contract = _label_creation_contract(
            label_dedupe_key="current",
            parent_status={"cex_label_candidate_parent_chain_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=drift_contract),
        ):
            contract = onchain_engine.get_cex_final_label_write_contract(1, True)

        self.assertEqual(contract["contract_status"], "blocked")
        self.assertIn("label_dedupe_key_mismatch", contract["blockers"])
        self.assertIn("source_or_digest_mismatch", contract["blockers"])
        self.assertIn("invalid_label_creation_contract_json", contract["blockers"])
        self.assertIn("parent_chain_not_bound", contract["blockers"])
        self.assertIn("cex_final_label_write_route_mismatch", contract["blockers"])
        self.assertFalse(contract["would_create_cex_label"])
        self.assertFalse(contract["would_write"])
        self.assertEqual(contract["writes_performed"], 0)

    def test_final_label_write_queue_schema_plan_ready_and_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            plan = onchain_engine.get_cex_final_label_write_queue_schema_plan(1, True)
            real_write = onchain_engine.get_cex_final_label_write_queue_schema_plan(1, False)
            missing_id = onchain_engine.get_cex_final_label_write_queue_schema_plan(None, True)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_final_label_write_review_queue'"
                    ).fetchone()
                )
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(plan["plan_status"], "ready")
        self.assertEqual(plan["target_table"], "cex_final_label_write_review_queue")
        self.assertFalse(plan["table_exists"])
        self.assertTrue(plan["migration_required"])
        self.assertIn("final_label_dedupe_key TEXT NOT NULL UNIQUE", plan["schema_preview"])
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS idx_cex_final_label_write_review_queue_dedupe", plan["indexes_preview"][0])
        self.assertEqual(plan["constraints_preview"]["market_type"], ["cex"])
        self.assertEqual(plan["constraints_preview"]["final_label_target_table"], ["cex_token_market_labels_future"])
        self.assertTrue(plan["final_label_dedupe_key"])
        self.assertEqual(plan["dedupe_constraints"]["final_label_dedupe_key"], plan["final_label_dedupe_key"])
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_final_label_write_row"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_mutate_label_table"])
        self.assertFalse(plan["would_write"])
        self.assertFalse(plan["would_execute_trade"])
        self.assertFalse(plan["would_create_client_opt_in"])
        self.assertEqual(plan["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_label_creation_review_id_required", missing_id["blockers"])
        self.assertFalse(table_exists)
        self.assertEqual(row_count, 1)

    def test_final_label_write_queue_schema_plan_blocks_when_contract_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        blocked_contract = {
            "ok": True,
            "contract_status": "blocked",
            "label_dedupe_key": "label-dedupe",
            "final_label_dedupe_key": None,
            "blockers": ["cex_label_creation_not_accepted_for_final_label_write_contract"],
        }
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_final_label_write_contract", return_value=blocked_contract),
        ):
            plan = onchain_engine.get_cex_final_label_write_queue_schema_plan(1, True)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_final_label_write_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertIn("cex_final_label_write_contract_not_ready", plan["blockers"])
        self.assertFalse(plan["migration_required"])
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_write"])
        self.assertEqual(plan["writes_performed"], 0)
        self.assertFalse(table_exists)

    def test_final_label_write_queue_create_dry_run_requires_confirm_and_creates_idempotently(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            dry_run = onchain_engine.create_cex_final_label_write_review_queue(1, True, None)
            no_confirm = onchain_engine.create_cex_final_label_write_review_queue(1, False, None)
            first = onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            second = onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0])
                columns = {
                    row[1]
                    for row in check_conn.execute("PRAGMA table_info(cex_final_label_write_review_queue)").fetchall()
                }
                indexes = {
                    row[0]
                    for row in check_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'cex_final_label_write_review_queue'"
                    ).fetchall()
                    if not str(row[0]).startswith("sqlite_autoindex_")
                }
                source_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(dry_run["create_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_create_table"])
        self.assertFalse(dry_run["table_created"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("confirm_CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE_required", no_confirm["blockers"])
        self.assertEqual(first["create_status"], "created")
        self.assertTrue(first["table_created"])
        self.assertGreater(first["writes_performed"], 0)
        self.assertEqual(second["create_status"], "already_exists")
        self.assertFalse(second["table_created"])
        self.assertEqual(second["rows_inserted"], 0)
        self.assertFalse(first["would_create_cex_label"])
        self.assertFalse(first["would_mutate_label_table"])
        self.assertFalse(first["would_create_dex_router_evidence"])
        self.assertFalse(first["would_create_mapping"])
        self.assertFalse(first["would_execute_trade"])
        self.assertFalse(first["would_create_client_opt_in"])
        self.assertEqual(row_count, 0)
        self.assertEqual(source_count, 1)
        self.assertIn("final_label_dedupe_key", columns)
        self.assertIn("final_label_write_contract_json", columns)
        self.assertIn("idx_cex_final_label_write_review_queue_dedupe", indexes)

    def test_final_label_write_review_insert_dry_run_then_confirm_and_duplicate_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            final_label_dedupe_key = contract["final_label_dedupe_key"]
            dry_run = onchain_engine.insert_cex_final_label_write_review(
                1,
                final_label_dedupe_key,
                True,
                None,
            )
            missing_expected = onchain_engine.insert_cex_final_label_write_review(
                1,
                None,
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            mismatch = onchain_engine.insert_cex_final_label_write_review(
                1,
                "wrong",
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            inserted = onchain_engine.insert_cex_final_label_write_review(
                1,
                final_label_dedupe_key,
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            duplicate = onchain_engine.insert_cex_final_label_write_review(
                1,
                final_label_dedupe_key,
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                row = check_conn.execute(
                    """
                    SELECT status, final_label_dedupe_key, market_type, final_label_target_table,
                           label_target, label_kind
                    FROM cex_final_label_write_review_queue
                    LIMIT 1
                    """
                ).fetchone()
                source_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(dry_run["insert_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_insert"])
        self.assertFalse(dry_run["inserted"])
        self.assertFalse(dry_run["would_create_final_label_write_row"])
        self.assertFalse(dry_run["would_create_cex_label"])
        self.assertFalse(dry_run["would_mutate_label_table"])
        self.assertFalse(dry_run["would_create_dex_router_evidence"])
        self.assertFalse(dry_run["would_create_mapping"])
        self.assertFalse(dry_run["would_execute_trade"])
        self.assertFalse(dry_run["would_create_client_opt_in"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("expected_final_label_dedupe_key_required", missing_expected["blockers"])
        self.assertIn("expected_final_label_dedupe_key_mismatch", mismatch["blockers"])
        self.assertEqual(inserted["insert_status"], "inserted")
        self.assertTrue(inserted["inserted"])
        self.assertEqual(inserted["writes_performed"], 1)
        self.assertFalse(inserted["would_create_cex_label"])
        self.assertFalse(inserted["would_mutate_label_table"])
        self.assertFalse(inserted["would_create_dex_router_evidence"])
        self.assertFalse(inserted["would_create_mapping"])
        self.assertFalse(inserted["would_execute_trade"])
        self.assertFalse(inserted["would_create_client_opt_in"])
        self.assertEqual(duplicate["insert_status"], "blocked")
        self.assertIn("duplicate_final_label_dedupe_key", duplicate["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(source_count, 1)
        self.assertEqual(row[0], "pending_admin_review")
        self.assertEqual(row[1], final_label_dedupe_key)
        self.assertEqual(row[2], "cex")
        self.assertEqual(row[3], "cex_token_market_labels_future")
        self.assertEqual(row[4], "cex_label_registry_future_review")
        self.assertEqual(row[5], "cex_market_presence_candidate")

    def test_final_label_write_review_queue_returns_ready_inserted_row(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            review = onchain_engine.get_cex_final_label_write_review_queue_review(
                status="pending_admin_review",
                token_symbol="TEST",
                market_type="cex",
                limit=50,
                dry_run=True,
            )
            real_write = onchain_engine.get_cex_final_label_write_review_queue_review(
                status="pending_admin_review",
                dry_run=False,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                source_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(review["queue_status"], "ready")
        self.assertEqual(review["summary"]["total_cex_final_label_write_reviews"], 1)
        self.assertEqual(review["summary"]["ready_for_cex_final_label_write_decision_preview"], 1)
        self.assertEqual(review["summary"]["blocked"], 0)
        row = review["rows"][0]
        self.assertEqual(row["cex_final_label_write_review_id"], 1)
        self.assertEqual(row["status"], "pending_admin_review")
        self.assertEqual(row["review_readiness"], "ready_for_cex_final_label_write_decision_preview")
        self.assertTrue(row["dedupe_bound"])
        self.assertTrue(row["label_dedupe_bound"])
        self.assertTrue(row["source_digest_bound"])
        self.assertTrue(row["contract_ready_now"])
        self.assertTrue(row["final_label_write_contract_json_valid"])
        self.assertTrue(row["final_label_write_contract_json_bound"])
        self.assertTrue(all(row["parent_status"].values()))
        self.assertTrue(row["route_consistent"])
        self.assertFalse(row["would_create_cex_label"])
        self.assertFalse(row["would_mutate_label_table"])
        self.assertFalse(row["would_create_dex_router_evidence"])
        self.assertFalse(row["would_create_mapping"])
        self.assertFalse(row["would_execute_trade"])
        self.assertFalse(row["would_create_client_opt_in"])
        self.assertFalse(row["would_write"])
        self.assertFalse(review["would_create_cex_label"])
        self.assertFalse(review["would_mutate_label_table"])
        self.assertFalse(review["would_write"])
        self.assertEqual(review["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(source_count, 1)

    def test_final_label_write_decision_preview_allows_ready_accept_and_stays_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            accept = onchain_engine.get_cex_final_label_write_decision_preview(
                1,
                "accept_for_future_cex_final_label_write",
                True,
            )
            request = onchain_engine.get_cex_final_label_write_decision_preview(
                1,
                "request_better_source",
                True,
            )
            reject = onchain_engine.get_cex_final_label_write_decision_preview(1, "reject", True)
            invalid = onchain_engine.get_cex_final_label_write_decision_preview(1, "approve", True)
            missing = onchain_engine.get_cex_final_label_write_decision_preview(
                999,
                "accept_for_future_cex_final_label_write",
                True,
            )
            real_write = onchain_engine.get_cex_final_label_write_decision_preview(
                1,
                "accept_for_future_cex_final_label_write",
                False,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                status = check_conn.execute(
                    "SELECT status FROM cex_final_label_write_review_queue WHERE id = 1"
                ).fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(accept["preview_status"], "ready_but_disabled")
        self.assertTrue(accept["decision_allowed"])
        self.assertEqual(accept["decision_preview"]["future_status"], "accepted_for_future_cex_final_label_write")
        self.assertEqual(accept["required_future_confirm"], "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION")
        self.assertFalse(accept["would_update_cex_final_label_write_status"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_mutate_label_table"])
        self.assertFalse(accept["would_create_dex_router_evidence"])
        self.assertFalse(accept["would_create_mapping"])
        self.assertFalse(accept["would_execute_trade"])
        self.assertFalse(accept["would_create_client_opt_in"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")
        self.assertTrue(reject["decision_allowed"])
        self.assertEqual(reject["decision_preview"]["future_status"], "rejected")
        self.assertFalse(invalid["decision_allowed"])
        self.assertIn("invalid_proposed_decision", invalid["blockers"])
        self.assertFalse(missing["decision_allowed"])
        self.assertIn("cex_final_label_write_review_missing", missing["blockers"])
        self.assertFalse(real_write["decision_allowed"])
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(status, "pending_admin_review")

    def test_final_label_write_decision_preview_blocks_accept_on_drift_but_allows_request(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    UPDATE cex_final_label_write_review_queue
                    SET final_label_dedupe_key = 'stale',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        final_label_write_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                conn.commit()
            finally:
                conn.close()

        drift_contract = _label_creation_contract(
            label_dedupe_key="current",
            parent_status={"cex_label_candidate_parent_chain_exists": False},
        )
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=drift_contract),
        ):
            accept = onchain_engine.get_cex_final_label_write_decision_preview(
                1,
                "accept_for_future_cex_final_label_write",
                True,
            )
            request = onchain_engine.get_cex_final_label_write_decision_preview(
                1,
                "request_better_source",
                True,
            )

        self.assertEqual(accept["preview_status"], "blocked")
        self.assertFalse(accept["decision_allowed"])
        self.assertIn("cex_final_label_write_not_ready_for_acceptance", accept["blockers"])
        self.assertIn("cex_final_label_write_dedupe_not_bound", accept["blockers"])
        self.assertIn("cex_final_label_write_source_digest_not_bound", accept["blockers"])
        self.assertIn("invalid_final_label_write_contract_json", accept["blockers"])
        self.assertIn("parent_chain_not_bound", accept["blockers"])
        self.assertIn("cex_final_label_write_route_inconsistent", accept["blockers"])
        self.assertIn("non_cex_final_label_write_cannot_accept", accept["blockers"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_mutate_label_table"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)
        self.assertEqual(request["preview_status"], "ready_but_disabled")
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")

    def test_final_label_write_decision_apply_updates_only_status_after_confirm(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            dry_run = onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                True,
                None,
            )
            no_confirm = onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                None,
            )
            request = onchain_engine.apply_cex_final_label_write_decision(
                1,
                "request_better_source",
                True,
                None,
            )
            confirmed = onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            second = onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                status = check_conn.execute(
                    "SELECT status FROM cex_final_label_write_review_queue WHERE id = 1"
                ).fetchone()[0]
                source_count = int(check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0])
            finally:
                check_conn.close()

        self.assertEqual(dry_run["apply_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_update_cex_final_label_write_status"])
        self.assertFalse(dry_run["updated"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("confirm_APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION_required", no_confirm["blockers"])
        self.assertIn("only_accept_for_future_cex_final_label_write_can_be_applied", request["blockers"])
        self.assertEqual(confirmed["apply_status"], "updated")
        self.assertTrue(confirmed["updated"])
        self.assertEqual(confirmed["previous_status"], "pending_admin_review")
        self.assertEqual(confirmed["new_status"], "accepted_for_future_cex_final_label_write")
        self.assertEqual(confirmed["writes_performed"], 1)
        self.assertFalse(confirmed["would_create_cex_label"])
        self.assertFalse(confirmed["would_mutate_label_table"])
        self.assertFalse(confirmed["would_create_dex_router_evidence"])
        self.assertFalse(confirmed["would_create_mapping"])
        self.assertFalse(confirmed["would_execute_trade"])
        self.assertFalse(confirmed["would_create_client_opt_in"])
        self.assertEqual(second["apply_status"], "blocked")
        self.assertIn("cex_final_label_write_status_not_pending_admin_review", second["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(source_count, 1)
        self.assertEqual(status, "accepted_for_future_cex_final_label_write")

    def test_final_label_write_execution_contract_ready_after_status_accept_and_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            real_write = onchain_engine.get_cex_final_label_write_execution_contract(1, False)
            missing = onchain_engine.get_cex_final_label_write_execution_contract(999, True)
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                status = check_conn.execute(
                    "SELECT status FROM cex_final_label_write_review_queue WHERE id = 1"
                ).fetchone()[0]
                source_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_label_creation_review_queue").fetchone()[0]
                )
            finally:
                check_conn.close()

        self.assertEqual(contract["contract_status"], "ready_but_disabled")
        self.assertEqual(contract["cex_final_label_write_review_id"], 1)
        self.assertEqual(contract["cex_final_label_write_status"], "accepted_for_future_cex_final_label_write")
        self.assertEqual(contract["label_write_proposal"]["target_table"], "cex_token_market_labels_future")
        self.assertTrue(contract["final_label_execution_dedupe_key"])
        self.assertTrue(contract["dedupe_status"]["final_label_dedupe_bound"])
        self.assertTrue(contract["dedupe_status"]["label_dedupe_bound"])
        self.assertTrue(contract["dedupe_status"]["source_digest_bound"])
        self.assertTrue(contract["dedupe_status"]["final_label_write_contract_json_valid"])
        self.assertTrue(contract["dedupe_status"]["final_label_write_contract_json_bound"])
        self.assertTrue(all(contract["parent_status"].values()))
        self.assertFalse(contract["would_create_cex_label"])
        self.assertFalse(contract["would_mutate_label_table"])
        self.assertFalse(contract["would_create_dex_router_evidence"])
        self.assertFalse(contract["would_create_mapping"])
        self.assertFalse(contract["would_execute_trade"])
        self.assertFalse(contract["would_create_client_opt_in"])
        self.assertFalse(contract["would_write"])
        self.assertEqual(contract["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_final_label_write_review_missing", missing["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(source_count, 1)
        self.assertEqual(status, "accepted_for_future_cex_final_label_write")

    def test_final_label_write_execution_contract_blocks_on_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract") as creation_contract,
        ):
            creation_contract.return_value = _label_creation_contract()
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                check_conn.execute(
                    """
                    UPDATE cex_final_label_write_review_queue
                    SET status = 'pending_admin_review',
                        final_label_dedupe_key = 'stale-final-label-dedupe',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        final_label_write_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                check_conn.commit()
            finally:
                check_conn.close()

            creation_contract.return_value = _label_creation_contract(
                parent_status={"cex_label_candidate_parent_chain_exists": False}
            )
            contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)

        self.assertEqual(contract["contract_status"], "blocked")
        self.assertIn("cex_final_label_write_not_accepted_for_execution_contract", contract["blockers"])
        self.assertIn("final_label_dedupe_key_mismatch", contract["blockers"])
        self.assertIn("source_or_digest_mismatch", contract["blockers"])
        self.assertIn("parent_chain_not_bound", contract["blockers"])
        self.assertIn("invalid_final_label_write_contract_json", contract["blockers"])
        self.assertIn("cex_final_label_write_execution_route_mismatch", contract["blockers"])
        self.assertFalse(contract["would_create_cex_label"])
        self.assertFalse(contract["would_mutate_label_table"])
        self.assertFalse(contract["would_write"])
        self.assertEqual(contract["writes_performed"], 0)

    def test_final_label_execution_queue_schema_plan_ready_and_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            plan = onchain_engine.get_cex_final_label_execution_queue_schema_plan(1, True)
            real_write = onchain_engine.get_cex_final_label_execution_queue_schema_plan(1, False)
            missing_id = onchain_engine.get_cex_final_label_execution_queue_schema_plan(None, True)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists_after = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_final_label_execution_review_queue'"
                    ).fetchone()
                )
                source_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
            finally:
                check_conn.close()

        self.assertEqual(plan["plan_status"], "ready")
        self.assertEqual(plan["target_table"], "cex_final_label_execution_review_queue")
        self.assertFalse(plan["table_exists"])
        self.assertTrue(plan["migration_required"])
        self.assertIn("final_label_execution_dedupe_key TEXT NOT NULL UNIQUE", plan["schema_preview"])
        self.assertTrue(plan["indexes_preview"])
        self.assertEqual(plan["constraints_preview"]["market_type"], ["cex"])
        self.assertEqual(plan["constraints_preview"]["final_label_target_table"], ["cex_token_market_labels_future"])
        self.assertTrue(plan["final_label_execution_dedupe_key"])
        self.assertEqual(
            plan["dedupe_constraints"]["final_label_execution_dedupe_key"],
            plan["final_label_execution_dedupe_key"],
        )
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_final_label_execution_row"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_mutate_label_table"])
        self.assertFalse(plan["would_create_dex_router_evidence"])
        self.assertFalse(plan["would_create_mapping"])
        self.assertFalse(plan["would_write"])
        self.assertFalse(plan["would_execute_trade"])
        self.assertFalse(plan["would_create_client_opt_in"])
        self.assertEqual(plan["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_final_label_write_review_id_required", missing_id["blockers"])
        self.assertFalse(table_exists_after)
        self.assertEqual(source_count, 1)

    def test_final_label_execution_queue_schema_plan_blocks_when_contract_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        blocked_contract = {
            "ok": True,
            "contract_status": "blocked",
            "blockers": ["cex_final_label_write_not_accepted_for_execution_contract"],
            "final_label_execution_dedupe_key": None,
        }
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_cex_final_label_write_execution_contract",
                return_value=blocked_contract,
            ),
        ):
            plan = onchain_engine.get_cex_final_label_execution_queue_schema_plan(1, True)
            check_conn = sqlite3.connect(db_path)
            try:
                table_exists_after = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_final_label_execution_review_queue'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(plan["plan_status"], "blocked")
        self.assertIn("cex_final_label_write_execution_contract_not_ready", plan["blockers"])
        self.assertFalse(plan["migration_required"])
        self.assertFalse(plan["would_create_table"])
        self.assertFalse(plan["would_create_cex_label"])
        self.assertFalse(plan["would_write"])
        self.assertEqual(plan["writes_performed"], 0)
        self.assertFalse(table_exists_after)

    def test_final_label_execution_queue_create_dry_run_requires_confirm_and_creates_idempotently(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            dry_run = onchain_engine.create_cex_final_label_execution_review_queue(1, True, None)
            no_confirm = onchain_engine.create_cex_final_label_execution_review_queue(1, False, None)
            first = onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            second = onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_execution_review_queue").fetchone()[0]
                )
                source_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                columns = {
                    row[1]
                    for row in check_conn.execute(
                        "PRAGMA table_info(cex_final_label_execution_review_queue)"
                    ).fetchall()
                }
                indexes = {
                    row[0]
                    for row in check_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'cex_final_label_execution_review_queue'"
                    ).fetchall()
                }
            finally:
                check_conn.close()

        self.assertEqual(dry_run["create_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_create_table"])
        self.assertFalse(dry_run["table_created"])
        self.assertEqual(dry_run["rows_inserted"], 0)
        self.assertIn("confirm_CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE_required", no_confirm["blockers"])
        self.assertEqual(first["create_status"], "created")
        self.assertTrue(first["table_created"])
        self.assertEqual(first["rows_inserted"], 0)
        self.assertFalse(first["would_create_cex_label"])
        self.assertFalse(first["would_mutate_label_table"])
        self.assertFalse(first["would_create_dex_router_evidence"])
        self.assertFalse(first["would_create_mapping"])
        self.assertFalse(first["would_execute_trade"])
        self.assertFalse(first["would_create_client_opt_in"])
        self.assertEqual(second["create_status"], "already_exists")
        self.assertFalse(second["table_created"])
        self.assertEqual(second["rows_inserted"], 0)
        self.assertEqual(row_count, 0)
        self.assertEqual(source_count, 1)
        self.assertIn("final_label_execution_dedupe_key", columns)
        self.assertIn("execution_contract_json", columns)
        self.assertIn("idx_cex_final_label_execution_review_queue_dedupe", indexes)

    def test_final_label_execution_review_insert_dry_run_then_confirm_and_duplicate_blocked(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            dry_run = onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                True,
                None,
            )
            missing_expected = onchain_engine.insert_cex_final_label_execution_review(
                1,
                None,
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            mismatch = onchain_engine.insert_cex_final_label_execution_review(
                1,
                "wrong-dedupe",
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            inserted = onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            duplicate = onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_execution_review_queue").fetchone()[0]
                )
                source_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                row = check_conn.execute(
                    """
                    SELECT status, final_label_execution_dedupe_key, execution_contract_json
                    FROM cex_final_label_execution_review_queue
                    WHERE id = 1
                    """
                ).fetchone()
            finally:
                check_conn.close()

        self.assertEqual(dry_run["insert_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_insert"])
        self.assertFalse(dry_run["inserted"])
        self.assertFalse(dry_run["would_create_cex_label"])
        self.assertFalse(dry_run["would_mutate_label_table"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("expected_final_label_execution_dedupe_key_required", missing_expected["blockers"])
        self.assertIn("expected_final_label_execution_dedupe_key_mismatch", mismatch["blockers"])
        self.assertEqual(inserted["insert_status"], "inserted")
        self.assertTrue(inserted["inserted"])
        self.assertEqual(inserted["cex_final_label_execution_review_id"], 1)
        self.assertFalse(inserted["would_create_cex_label"])
        self.assertFalse(inserted["would_mutate_label_table"])
        self.assertFalse(inserted["would_create_dex_router_evidence"])
        self.assertFalse(inserted["would_create_mapping"])
        self.assertFalse(inserted["would_execute_trade"])
        self.assertFalse(inserted["would_create_client_opt_in"])
        self.assertEqual(inserted["writes_performed"], 1)
        self.assertIn("duplicate_final_label_execution_dedupe_key", duplicate["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(source_count, 1)
        self.assertEqual(row[0], "pending_admin_review")
        self.assertEqual(row[1], execution_contract["final_label_execution_dedupe_key"])
        self.assertEqual(json.loads(row[2])["contract_kind"], "cex_final_label_write_execution_contract_not_enabled")

    def test_final_label_execution_review_queue_returns_ready_inserted_row(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            review = onchain_engine.get_cex_final_label_execution_review_queue_review(
                "pending_admin_review",
                None,
                None,
                50,
                True,
            )
            real_write = onchain_engine.get_cex_final_label_execution_review_queue_review(
                "pending_admin_review",
                None,
                None,
                50,
                False,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_execution_review_queue").fetchone()[0]
                )
                source_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
            finally:
                check_conn.close()

        self.assertEqual(review["queue_status"], "ready")
        self.assertEqual(review["summary"]["total_cex_final_label_execution_reviews"], 1)
        self.assertEqual(review["summary"]["ready_for_cex_final_label_execution_decision_preview"], 1)
        self.assertEqual(review["summary"]["blocked"], 0)
        row = review["rows"][0]
        self.assertEqual(row["cex_final_label_execution_review_id"], 1)
        self.assertEqual(row["status"], "pending_admin_review")
        self.assertEqual(row["review_readiness"], "ready_for_cex_final_label_execution_decision_preview")
        self.assertTrue(row["dedupe_bound"])
        self.assertTrue(row["final_label_dedupe_bound"])
        self.assertTrue(row["label_dedupe_bound"])
        self.assertTrue(row["source_digest_bound"])
        self.assertTrue(row["contract_ready_now"])
        self.assertTrue(row["execution_contract_json_valid"])
        self.assertTrue(row["execution_contract_json_bound"])
        self.assertTrue(all(row["parent_status"].values()))
        self.assertTrue(row["route_consistent"])
        self.assertFalse(row["would_create_cex_label"])
        self.assertFalse(row["would_mutate_label_table"])
        self.assertFalse(row["would_write"])
        self.assertFalse(review["would_create_cex_label"])
        self.assertFalse(review["would_mutate_label_table"])
        self.assertFalse(review["would_write"])
        self.assertEqual(review["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(source_count, 1)

    def test_final_label_execution_review_queue_blocks_on_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract") as creation_contract,
        ):
            creation_contract.return_value = _label_creation_contract()
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                check_conn.execute(
                    """
                    UPDATE cex_final_label_execution_review_queue
                    SET final_label_execution_dedupe_key = 'stale-execution-dedupe',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        execution_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                check_conn.commit()
            finally:
                check_conn.close()
            creation_contract.return_value = _label_creation_contract(
                parent_status={"cex_label_candidate_parent_chain_exists": False}
            )
            review = onchain_engine.get_cex_final_label_execution_review_queue_review("all", None, None, 50, True)

        self.assertEqual(review["queue_status"], "ready")
        row = review["rows"][0]
        self.assertEqual(row["review_readiness"], "blocked")
        self.assertIn("final_label_execution_dedupe_key_mismatch", row["review_blockers"])
        self.assertIn("source_or_digest_mismatch", row["review_blockers"])
        self.assertIn("parent_chain_not_bound", row["review_blockers"])
        self.assertIn("invalid_execution_contract_json", row["review_blockers"])
        self.assertIn("cex_final_label_execution_route_mismatch", row["review_blockers"])
        self.assertFalse(row["would_create_cex_label"])
        self.assertFalse(row["would_mutate_label_table"])
        self.assertFalse(review["would_write"])
        self.assertEqual(review["writes_performed"], 0)

    def test_final_label_execution_decision_preview_accept_request_and_reject_are_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            accept = onchain_engine.get_cex_final_label_execution_decision_preview(
                1,
                "accept_for_future_cex_final_label_execution",
                True,
            )
            request = onchain_engine.get_cex_final_label_execution_decision_preview(
                1,
                "request_better_source",
                True,
            )
            reject = onchain_engine.get_cex_final_label_execution_decision_preview(
                1,
                "reject",
                True,
            )
            real_write = onchain_engine.get_cex_final_label_execution_decision_preview(
                1,
                "accept_for_future_cex_final_label_execution",
                False,
            )
            invalid = onchain_engine.get_cex_final_label_execution_decision_preview(1, "ship_it", True)
            missing = onchain_engine.get_cex_final_label_execution_decision_preview(
                999,
                "accept_for_future_cex_final_label_execution",
                True,
            )
            check_conn = sqlite3.connect(db_path)
            try:
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_execution_review_queue").fetchone()[0]
                )
                row_status = check_conn.execute(
                    "SELECT status FROM cex_final_label_execution_review_queue WHERE id = 1"
                ).fetchone()[0]
            finally:
                check_conn.close()

        self.assertEqual(accept["preview_status"], "ready_but_disabled")
        self.assertTrue(accept["decision_allowed"])
        self.assertEqual(
            accept["decision_preview"]["future_status"],
            "accepted_for_future_cex_final_label_execution",
        )
        self.assertEqual(accept["required_future_confirm"], "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION")
        self.assertFalse(accept["would_update_cex_final_label_execution_status"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_mutate_label_table"])
        self.assertFalse(accept["would_create_dex_router_evidence"])
        self.assertFalse(accept["would_create_mapping"])
        self.assertFalse(accept["would_execute_trade"])
        self.assertFalse(accept["would_create_client_opt_in"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")
        self.assertTrue(reject["decision_allowed"])
        self.assertEqual(reject["decision_preview"]["future_status"], "rejected")
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("invalid_proposed_decision", invalid["blockers"])
        self.assertIn("cex_final_label_execution_review_missing", missing["blockers"])
        self.assertEqual(row_count, 1)
        self.assertEqual(row_status, "pending_admin_review")

    def test_final_label_execution_decision_preview_blocks_accept_on_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract") as creation_contract,
        ):
            creation_contract.return_value = _label_creation_contract()
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                check_conn.execute(
                    """
                    UPDATE cex_final_label_execution_review_queue
                    SET final_label_execution_dedupe_key = 'stale-execution-dedupe',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        execution_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                check_conn.commit()
            finally:
                check_conn.close()
            creation_contract.return_value = _label_creation_contract(
                parent_status={"cex_label_candidate_parent_chain_exists": False}
            )
            accept = onchain_engine.get_cex_final_label_execution_decision_preview(
                1,
                "accept_for_future_cex_final_label_execution",
                True,
            )
            request = onchain_engine.get_cex_final_label_execution_decision_preview(
                1,
                "request_better_source",
                True,
            )
            reject = onchain_engine.get_cex_final_label_execution_decision_preview(
                1,
                "reject",
                True,
            )

        self.assertEqual(accept["preview_status"], "blocked")
        self.assertFalse(accept["decision_allowed"])
        self.assertIn("cex_final_label_execution_not_ready_for_acceptance", accept["blockers"])
        self.assertIn("cex_final_label_execution_dedupe_not_bound", accept["blockers"])
        self.assertIn("cex_final_label_execution_source_digest_not_bound", accept["blockers"])
        self.assertIn("invalid_cex_final_label_execution_contract_json", accept["blockers"])
        self.assertIn("cex_final_label_execution_contract_json_not_bound", accept["blockers"])
        self.assertIn("parent_chain_not_bound", accept["blockers"])
        self.assertIn("cex_final_label_execution_route_inconsistent", accept["blockers"])
        self.assertIn("non_cex_final_label_execution_cannot_accept", accept["blockers"])
        self.assertTrue(request["decision_allowed"])
        self.assertTrue(reject["decision_allowed"])
        self.assertFalse(accept["would_create_cex_label"])
        self.assertFalse(accept["would_mutate_label_table"])
        self.assertFalse(accept["would_write"])
        self.assertEqual(accept["writes_performed"], 0)

    def test_final_label_execution_decision_apply_is_status_only_and_terminal(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            dry_run = onchain_engine.apply_cex_final_label_execution_decision(
                1,
                "accept_for_future_cex_final_label_execution",
                True,
                None,
            )
            no_confirm = onchain_engine.apply_cex_final_label_execution_decision(
                1,
                "accept_for_future_cex_final_label_execution",
                False,
                None,
            )
            invalid = onchain_engine.apply_cex_final_label_execution_decision(
                1,
                "reject",
                False,
                "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION",
            )
            applied = onchain_engine.apply_cex_final_label_execution_decision(
                1,
                "accept_for_future_cex_final_label_execution",
                False,
                "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION",
            )
            second = onchain_engine.apply_cex_final_label_execution_decision(
                1,
                "accept_for_future_cex_final_label_execution",
                False,
                "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                status = check_conn.execute(
                    "SELECT status FROM cex_final_label_execution_review_queue WHERE id = 1"
                ).fetchone()[0]
                execution_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_execution_review_queue").fetchone()[0]
                )
                final_write_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_write_review_queue").fetchone()[0]
                )
                final_label_table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_token_market_labels_future'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(dry_run["apply_status"], "ready_but_disabled")
        self.assertTrue(dry_run["would_update_cex_final_label_execution_status"])
        self.assertFalse(dry_run["updated"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertIn("confirm_APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION_required", no_confirm["blockers"])
        self.assertIn("only_accept_for_future_cex_final_label_execution_can_be_applied", invalid["blockers"])
        self.assertEqual(applied["apply_status"], "updated")
        self.assertTrue(applied["updated"])
        self.assertEqual(applied["previous_status"], "pending_admin_review")
        self.assertEqual(applied["new_status"], "accepted_for_future_cex_final_label_execution")
        self.assertFalse(applied["would_create_cex_label"])
        self.assertFalse(applied["would_mutate_label_table"])
        self.assertFalse(applied["would_create_dex_router_evidence"])
        self.assertFalse(applied["would_create_mapping"])
        self.assertFalse(applied["would_execute_trade"])
        self.assertFalse(applied["would_create_client_opt_in"])
        self.assertEqual(applied["writes_performed"], 1)
        self.assertEqual(second["apply_status"], "blocked")
        self.assertIn("cex_final_label_execution_status_not_pending_admin_review", second["blockers"])
        self.assertEqual(status, "accepted_for_future_cex_final_label_execution")
        self.assertEqual(execution_count, 1)
        self.assertEqual(final_write_count, 1)
        self.assertFalse(final_label_table_exists)

    def test_final_label_write_safety_checkpoint_ready_after_execution_accept_and_read_only(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract", return_value=_label_creation_contract()),
        ):
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            onchain_engine.apply_cex_final_label_execution_decision(
                1,
                "accept_for_future_cex_final_label_execution",
                False,
                "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION",
            )
            checkpoint = onchain_engine.get_cex_final_label_write_safety_checkpoint(1, True)
            real_write = onchain_engine.get_cex_final_label_write_safety_checkpoint(1, False)
            missing = onchain_engine.get_cex_final_label_write_safety_checkpoint(999, True)
            check_conn = sqlite3.connect(db_path)
            try:
                status = check_conn.execute(
                    "SELECT status FROM cex_final_label_execution_review_queue WHERE id = 1"
                ).fetchone()[0]
                row_count = int(
                    check_conn.execute("SELECT COUNT(*) FROM cex_final_label_execution_review_queue").fetchone()[0]
                )
                final_label_table_exists = bool(
                    check_conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'cex_token_market_labels_future'"
                    ).fetchone()
                )
            finally:
                check_conn.close()

        self.assertEqual(checkpoint["checkpoint_status"], "ready_but_disabled")
        self.assertEqual(checkpoint["cex_final_label_execution_review_id"], 1)
        self.assertEqual(checkpoint["cex_final_label_execution_status"], "accepted_for_future_cex_final_label_execution")
        self.assertEqual(checkpoint["final_label_target_table"], "cex_token_market_labels_future")
        self.assertEqual(checkpoint["label_target"], "cex_label_registry_future_review")
        self.assertEqual(checkpoint["label_kind"], "cex_market_presence_candidate")
        self.assertEqual(checkpoint["label_write_proposal"]["target_table"], "cex_token_market_labels_future")
        self.assertTrue(checkpoint["dedupe_status"]["final_label_execution_dedupe_bound"])
        self.assertTrue(checkpoint["dedupe_status"]["final_label_dedupe_bound"])
        self.assertTrue(checkpoint["dedupe_status"]["label_dedupe_bound"])
        self.assertTrue(checkpoint["dedupe_status"]["source_digest_bound"])
        self.assertTrue(checkpoint["dedupe_status"]["execution_contract_json_valid"])
        self.assertTrue(checkpoint["dedupe_status"]["execution_contract_json_bound"])
        self.assertTrue(all(checkpoint["parent_status"].values()))
        self.assertTrue(checkpoint["routing_safety"]["cex_only"])
        self.assertFalse(checkpoint["routing_safety"]["direct_cex_label_write_now"])
        self.assertFalse(checkpoint["routing_safety"]["direct_label_table_mutation_now"])
        self.assertFalse(checkpoint["final_label_table_status"]["table_exists"])
        self.assertFalse(checkpoint["would_create_cex_label"])
        self.assertFalse(checkpoint["would_mutate_label_table"])
        self.assertFalse(checkpoint["would_create_dex_router_evidence"])
        self.assertFalse(checkpoint["would_create_mapping"])
        self.assertFalse(checkpoint["would_execute_trade"])
        self.assertFalse(checkpoint["would_create_client_opt_in"])
        self.assertFalse(checkpoint["would_write"])
        self.assertEqual(checkpoint["writes_performed"], 0)
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("cex_final_label_execution_review_missing", missing["blockers"])
        self.assertEqual(status, "accepted_for_future_cex_final_label_execution")
        self.assertEqual(row_count, 1)
        self.assertFalse(final_label_table_exists)

    def test_final_label_write_safety_checkpoint_blocks_on_drift(self) -> None:
        tmp, db_path = _with_db()
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch("services.onchain_engine.get_cex_label_creation_contract") as creation_contract,
        ):
            creation_contract.return_value = _label_creation_contract()
            onchain_engine.create_cex_label_creation_review_queue(
                1,
                False,
                "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
            )
            onchain_engine.insert_cex_label_creation_review(
                1,
                "label-dedupe",
                False,
                "INSERT_CEX_LABEL_CREATION_REVIEW",
            )
            onchain_engine.apply_cex_label_creation_review_decision(
                1,
                "accept_for_future_cex_label_creation",
                False,
                "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_write_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
            )
            write_contract = onchain_engine.get_cex_final_label_write_contract(1, True)
            onchain_engine.insert_cex_final_label_write_review(
                1,
                write_contract["final_label_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            )
            onchain_engine.apply_cex_final_label_write_decision(
                1,
                "accept_for_future_cex_final_label_write",
                False,
                "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
            )
            onchain_engine.create_cex_final_label_execution_review_queue(
                1,
                False,
                "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
            )
            execution_contract = onchain_engine.get_cex_final_label_write_execution_contract(1, True)
            onchain_engine.insert_cex_final_label_execution_review(
                1,
                execution_contract["final_label_execution_dedupe_key"],
                False,
                "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            )
            onchain_engine.apply_cex_final_label_execution_decision(
                1,
                "accept_for_future_cex_final_label_execution",
                False,
                "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION",
            )
            check_conn = sqlite3.connect(db_path)
            try:
                check_conn.execute(
                    """
                    UPDATE cex_final_label_execution_review_queue
                    SET final_label_execution_dedupe_key = 'stale-execution-dedupe',
                        source_url = 'https://example.com/stale',
                        market_type = 'dex',
                        execution_contract_json = '{bad json'
                    WHERE id = 1
                    """
                )
                check_conn.commit()
            finally:
                check_conn.close()
            creation_contract.return_value = _label_creation_contract(
                parent_status={"cex_label_candidate_parent_chain_exists": False}
            )
            checkpoint = onchain_engine.get_cex_final_label_write_safety_checkpoint(1, True)

        self.assertEqual(checkpoint["checkpoint_status"], "blocked")
        self.assertIn("final_label_execution_dedupe_key_mismatch", checkpoint["blockers"])
        self.assertIn("source_or_digest_mismatch", checkpoint["blockers"])
        self.assertIn("parent_chain_not_bound", checkpoint["blockers"])
        self.assertIn("invalid_execution_contract_json", checkpoint["blockers"])
        self.assertIn("cex_final_label_write_route_mismatch", checkpoint["blockers"])
        self.assertFalse(checkpoint["would_create_cex_label"])
        self.assertFalse(checkpoint["would_mutate_label_table"])
        self.assertFalse(checkpoint["would_write"])
        self.assertEqual(checkpoint["writes_performed"], 0)


if __name__ == "__main__":
    unittest.main()
