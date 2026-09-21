from __future__ import annotations

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


def _review_row(**overrides):
    row = {
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
        "market_type": "cex",
        "target_queue": "cex_market_evidence_review_queue",
        "handoff_target_queue": "cex_market_evidence_review_queue",
        "execution_target_queue": "cex_market_evidence_review_queue",
        "final_target_queue": "cex_market_evidence_review_queue",
        "final_apply_target": "cex_market_evidence_review_queue",
        "execution_target": "cex_market_evidence_review_queue",
        "apply_target": "cex_market_evidence_review_queue",
        "insert_target": "cex_market_evidence_review_queue",
        "post_apply_target": "cex_market_evidence_review_queue",
        "business_target": "cex_market_evidence_review_queue",
        "promotion_target": "cex_market_evidence_flow",
        "downstream_target": "cex_market_evidence_review_queue",
        "source_tier": "tier_1",
        "review_readiness": "ready_for_final_handoff_target_decision_preview",
        "review_blockers": [],
        "status": "pending_admin_review",
        "dedupe_bound": True,
        "source_digest_bound": True,
        "contract_ready_now": True,
        "target_contract_json_valid": True,
        "target_contract_json_bound": True,
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
        "route_consistent": True,
    }
    row.update(overrides)
    return row


def _decision_preview(decision: str = "accept_for_future_final_handoff_target", **overrides):
    future_status = {
        "accept_for_future_final_handoff_target": "accepted_for_future_final_handoff_target",
        "request_better_source": "needs_better_source",
        "reject": "rejected",
    }[decision]
    preview = {
        "ok": True,
        "preview_status": "ready_but_disabled",
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
        "proposed_decision": decision,
        "decision_allowed": True,
        "decision_preview": {"future_status": future_status},
        "blockers": [],
    }
    preview.update(overrides)
    return preview


class TokenMarketFinalHandoffTargetDecisionPreviewTests(unittest.TestCase):
    def _patch_review(self, row):
        return patch(
            "services.onchain_engine.get_token_market_final_handoff_target_queue_review",
            return_value={"ok": True, "queue_status": "ready", "rows": [row], "blockers": []},
        )

    def test_accept_ready_row_is_read_only_and_allowed(self) -> None:
        with self._patch_review(_review_row()):
            preview = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=1,
                proposed_decision="accept_for_future_final_handoff_target",
                dry_run=True,
            )

        self.assertEqual(preview["preview_status"], "ready_but_disabled")
        self.assertTrue(preview["decision_allowed"])
        self.assertEqual(preview["decision_preview"]["future_status"], "accepted_for_future_final_handoff_target")
        self.assertEqual(
            preview["decision_preview"]["next_step"],
            "final_handoff_target_status_only_apply_not_label_router_mapping_trade",
        )
        self.assertFalse(preview["would_update_final_handoff_target_status"])
        self.assertFalse(preview["would_create_cex_label"])
        self.assertFalse(preview["would_create_dex_router_evidence"])
        self.assertFalse(preview["would_create_mapping"])
        self.assertFalse(preview["would_execute_target"])
        self.assertFalse(preview["would_execute_trade"])
        self.assertFalse(preview["would_create_client_opt_in"])
        self.assertFalse(preview["would_write"])
        self.assertEqual(preview["writes_performed"], 0)

    def test_accept_blocks_on_drift_but_request_and_reject_remain_available(self) -> None:
        drifted = _review_row(
            dedupe_bound=False,
            review_readiness="blocked",
            review_blockers=["target_dedupe_key_mismatch"],
        )
        with self._patch_review(drifted):
            accept = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=1,
                proposed_decision="accept_for_future_final_handoff_target",
                dry_run=True,
            )
            request = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=1,
                proposed_decision="request_better_source",
                dry_run=True,
            )
            reject = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=1,
                proposed_decision="reject",
                dry_run=True,
            )

        self.assertEqual(accept["preview_status"], "blocked")
        self.assertFalse(accept["decision_allowed"])
        self.assertIn("final_handoff_target_not_ready_for_acceptance", accept["blockers"])
        self.assertIn("final_handoff_target_dedupe_not_bound", accept["blockers"])
        self.assertTrue(request["decision_allowed"])
        self.assertEqual(request["decision_preview"]["future_status"], "needs_better_source")
        self.assertTrue(reject["decision_allowed"])
        self.assertEqual(reject["decision_preview"]["future_status"], "rejected")

    def test_missing_invalid_real_write_and_hybrid_accept_are_blocked(self) -> None:
        with patch(
            "services.onchain_engine.get_token_market_final_handoff_target_queue_review",
            return_value={"ok": True, "queue_status": "ready", "rows": [], "blockers": []},
        ):
            missing = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=999,
                proposed_decision="accept_for_future_final_handoff_target",
                dry_run=True,
            )
        with self._patch_review(_review_row()):
            invalid = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=1,
                proposed_decision="approve",
                dry_run=True,
            )
            real_write = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=1,
                proposed_decision="accept_for_future_final_handoff_target",
                dry_run=False,
            )
        with self._patch_review(
            _review_row(
                market_type="hybrid_or_unclear",
                review_readiness="blocked",
                review_blockers=["manual_classification_required"],
            )
        ):
            hybrid = onchain_engine.get_token_market_final_handoff_target_decision_preview(
                final_handoff_target_id=1,
                proposed_decision="accept_for_future_final_handoff_target",
                dry_run=True,
            )

        self.assertIn("final_handoff_target_missing", missing["blockers"])
        self.assertIn("invalid_proposed_decision", invalid["blockers"])
        self.assertIn("dry_run_required", real_write["blockers"])
        self.assertIn("manual_classification_required_before_accept", hybrid["blockers"])
        self.assertFalse(missing["decision_allowed"])
        self.assertFalse(invalid["decision_allowed"])
        self.assertFalse(real_write["decision_allowed"])
        self.assertFalse(hybrid["decision_allowed"])

    def test_apply_dry_run_is_status_only_preview_without_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "apply.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE token_market_final_handoff_target_queue (id INTEGER PRIMARY KEY, status TEXT)")
            conn.execute(
                "INSERT INTO token_market_final_handoff_target_queue (id, status) VALUES (1, 'pending_admin_review')"
            )
            conn.commit()
            conn.close()

            with (
                patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
                patch(
                    "services.onchain_engine.get_token_market_final_handoff_target_decision_preview",
                    return_value=_decision_preview(),
                ),
            ):
                result = onchain_engine.apply_token_market_final_handoff_target_decision(
                    final_handoff_target_id=1,
                    proposed_decision="accept_for_future_final_handoff_target",
                    dry_run=True,
                    confirm=None,
                )

            conn = sqlite3.connect(db_path)
            status = conn.execute("SELECT status FROM token_market_final_handoff_target_queue WHERE id = 1").fetchone()[0]
            conn.close()

        self.assertEqual(result["apply_status"], "ready_but_disabled")
        self.assertTrue(result["would_update_final_handoff_target_status"])
        self.assertFalse(result["updated"])
        self.assertEqual(result["writes_performed"], 0)
        self.assertEqual(status, "pending_admin_review")
        self.assertFalse(result["would_create_cex_label"])
        self.assertFalse(result["would_create_dex_router_evidence"])
        self.assertFalse(result["would_create_mapping"])
        self.assertFalse(result["would_execute_target"])
        self.assertFalse(result["would_execute_trade"])
        self.assertFalse(result["would_create_client_opt_in"])

    def test_apply_confirmed_accept_updates_exactly_status_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "apply.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE token_market_final_handoff_target_queue (id INTEGER PRIMARY KEY, status TEXT)")
            conn.execute(
                "INSERT INTO token_market_final_handoff_target_queue (id, status) VALUES (1, 'pending_admin_review')"
            )
            conn.commit()
            conn.close()

            with (
                patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
                patch(
                    "services.onchain_engine.get_token_market_final_handoff_target_decision_preview",
                    return_value=_decision_preview(),
                ),
            ):
                result = onchain_engine.apply_token_market_final_handoff_target_decision(
                    final_handoff_target_id=1,
                    proposed_decision="accept_for_future_final_handoff_target",
                    dry_run=False,
                    confirm="APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION",
                )
                second = onchain_engine.apply_token_market_final_handoff_target_decision(
                    final_handoff_target_id=1,
                    proposed_decision="accept_for_future_final_handoff_target",
                    dry_run=False,
                    confirm="APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION",
                )

            conn = sqlite3.connect(db_path)
            status = conn.execute("SELECT status FROM token_market_final_handoff_target_queue WHERE id = 1").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM token_market_final_handoff_target_queue").fetchone()[0]
            conn.close()

        self.assertEqual(result["apply_status"], "updated")
        self.assertTrue(result["updated"])
        self.assertEqual(result["previous_status"], "pending_admin_review")
        self.assertEqual(result["new_status"], "accepted_for_future_final_handoff_target")
        self.assertEqual(result["writes_performed"], 1)
        self.assertEqual(status, "accepted_for_future_final_handoff_target")
        self.assertEqual(count, 1)
        self.assertEqual(second["apply_status"], "blocked")
        self.assertIn("final_handoff_target_status_not_pending_admin_review", second["blockers"])

    def test_apply_missing_confirm_invalid_decision_and_blocked_preview_do_not_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "apply.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE token_market_final_handoff_target_queue (id INTEGER PRIMARY KEY, status TEXT)")
            conn.execute(
                "INSERT INTO token_market_final_handoff_target_queue (id, status) VALUES (1, 'pending_admin_review')"
            )
            conn.commit()
            conn.close()

            with (
                patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
                patch(
                    "services.onchain_engine.get_token_market_final_handoff_target_decision_preview",
                    return_value=_decision_preview(),
                ),
            ):
                missing_confirm = onchain_engine.apply_token_market_final_handoff_target_decision(
                    final_handoff_target_id=1,
                    proposed_decision="accept_for_future_final_handoff_target",
                    dry_run=False,
                    confirm=None,
                )
            with (
                patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
                patch(
                    "services.onchain_engine.get_token_market_final_handoff_target_decision_preview",
                    return_value=_decision_preview("accept_for_future_final_handoff_target", decision_allowed=False),
                ),
            ):
                blocked_preview = onchain_engine.apply_token_market_final_handoff_target_decision(
                    final_handoff_target_id=1,
                    proposed_decision="accept_for_future_final_handoff_target",
                    dry_run=False,
                    confirm="APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION",
                )
            with (
                patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
                patch(
                    "services.onchain_engine.get_token_market_final_handoff_target_decision_preview",
                    return_value=_decision_preview("accept_for_future_final_handoff_target"),
                ),
            ):
                invalid = onchain_engine.apply_token_market_final_handoff_target_decision(
                    final_handoff_target_id=1,
                    proposed_decision="approve",
                    dry_run=False,
                    confirm="APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION",
                )

            conn = sqlite3.connect(db_path)
            status = conn.execute("SELECT status FROM token_market_final_handoff_target_queue WHERE id = 1").fetchone()[0]
            conn.close()

        self.assertIn("confirm_APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION_required", missing_confirm["blockers"])
        self.assertIn("final_handoff_target_decision_preview_not_allowed", blocked_preview["blockers"])
        self.assertIn("invalid_proposed_decision", invalid["blockers"])
        self.assertEqual(status, "pending_admin_review")


if __name__ == "__main__":
    unittest.main()
