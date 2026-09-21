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


def _target_row(**overrides):
    row = {
        "id": 1,
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
        "future_target_queue": "cex_market_evidence_review_queue",
        "source_url": "https://example.com/evidence",
        "source_tier": "tier_1",
        "evidence_type": "official_market_page",
        "evidence_preview_digest": "digest",
        "post_apply_insert_dedupe_key": "post-insert",
        "post_apply_execution_dedupe_key": "post-execution",
        "post_apply_execution_apply_dedupe_key": "post-execution-apply",
        "final_apply_dedupe_key": "final-apply",
        "final_target_execution_dedupe_key": "final-target-execution",
        "handoff_dedupe_key": "handoff",
        "target_dedupe_key": "target",
        "status": "accepted_for_future_final_handoff_target",
        "created_at": "2026-05-15T00:00:00Z",
        "source_policy": "test",
    }
    row.update(overrides)
    payload = {
        "target_dedupe_key": row["target_dedupe_key"],
        "target_queue": row["target_queue"],
        "final_handoff_id": row["final_handoff_id"],
        "source_url": row["source_url"],
        "evidence_preview_digest": row["evidence_preview_digest"],
    }
    row["target_contract_json"] = json.dumps({"payload_preview": payload})
    if "target_contract_json" in overrides:
        row["target_contract_json"] = overrides["target_contract_json"]
    return row


def _current_contract(row):
    payload = {
        "target_dedupe_key": row["target_dedupe_key"],
        "target_queue": row["target_queue"],
        "final_handoff_id": row["final_handoff_id"],
        "source_url": row["source_url"],
        "evidence_preview_digest": row["evidence_preview_digest"],
    }
    contract = {
        "contract_status": "ready_but_disabled",
        "target_dedupe_key": row["target_dedupe_key"],
        "target_contract": {"payload_preview": payload},
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
    }
    for field in (
        "token_symbol",
        "source_url",
        "source_tier",
        "evidence_type",
        "evidence_preview_digest",
        "post_apply_insert_dedupe_key",
        "post_apply_execution_dedupe_key",
        "post_apply_execution_apply_dedupe_key",
        "final_apply_dedupe_key",
        "final_target_execution_dedupe_key",
        "handoff_dedupe_key",
    ):
        contract[field] = row[field]
    return contract


def _with_db(row):
    tmp = tempfile.TemporaryDirectory()
    db_path = str(Path(tmp.name) / "contract.sqlite")
    conn = sqlite3.connect(db_path)
    columns = ", ".join(f"{key} TEXT" for key in row if key != "id")
    conn.execute(f"CREATE TABLE token_market_final_handoff_target_queue (id INTEGER PRIMARY KEY, {columns})")
    keys = list(row)
    placeholders = ", ".join("?" for _ in keys)
    conn.execute(
        f"INSERT INTO token_market_final_handoff_target_queue ({', '.join(keys)}) VALUES ({placeholders})",
        [row[key] for key in keys],
    )
    conn.commit()
    conn.close()
    return tmp, db_path


class TokenMarketCexReviewHandoffContractTests(unittest.TestCase):
    def test_accepted_cex_contract_is_ready_and_read_only(self) -> None:
        row = _target_row()
        tmp, db_path = _with_db(row)
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_contract",
                return_value=_current_contract(row),
            ),
        ):
            contract = onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract(1, True)

        self.assertEqual(contract["contract_status"], "ready_but_disabled")
        self.assertEqual(contract["cex_review_target_queue"], "cex_market_evidence_review_queue")
        self.assertEqual(contract["final_handoff_target_status"], "accepted_for_future_final_handoff_target")
        self.assertTrue(contract["dedupe_status"]["dedupe_bound"])
        self.assertTrue(contract["dedupe_status"]["source_digest_bound"])
        self.assertTrue(contract["dedupe_status"]["target_contract_json_valid"])
        self.assertTrue(contract["dedupe_status"]["target_contract_json_bound"])
        self.assertTrue(contract["cex_review_handoff_dedupe_key"])
        self.assertFalse(contract["would_create_cex_review_row"])
        self.assertFalse(contract["would_create_cex_label"])
        self.assertFalse(contract["would_create_dex_router_evidence"])
        self.assertFalse(contract["would_create_mapping"])
        self.assertFalse(contract["would_execute_target"])
        self.assertFalse(contract["would_execute_trade"])
        self.assertFalse(contract["would_create_client_opt_in"])
        self.assertFalse(contract["would_write"])
        self.assertEqual(contract["writes_performed"], 0)

    def test_non_accepted_dex_json_dedupe_and_missing_row_block(self) -> None:
        row = _target_row(status="pending_admin_review")
        tmp, db_path = _with_db(row)
        self.addCleanup(tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(db_path)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_contract",
                return_value=_current_contract(row),
            ),
        ):
            pending = onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract(1, True)
            missing = onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract(999, True)

        dex_row = _target_row(market_type="dex", target_queue="dex_router_official_evidence_queue")
        dex_tmp, dex_db = _with_db(dex_row)
        self.addCleanup(dex_tmp.cleanup)
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(dex_db)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_contract",
                return_value=_current_contract(dex_row),
            ),
        ):
            dex = onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract(1, True)

        drift_row = _target_row(target_contract_json="{bad json")
        drift_tmp, drift_db = _with_db(drift_row)
        self.addCleanup(drift_tmp.cleanup)
        drift_contract = _current_contract(drift_row)
        drift_contract["target_dedupe_key"] = "different"
        with (
            patch("services.onchain_engine._get_db", side_effect=lambda: sqlite3.connect(drift_db)),
            patch(
                "services.onchain_engine.get_token_market_final_handoff_target_contract",
                return_value=drift_contract,
            ),
        ):
            drift = onchain_engine.get_token_market_final_handoff_target_cex_review_handoff_contract(1, True)

        self.assertIn("final_handoff_target_not_accepted_for_cex_review_handoff", pending["blockers"])
        self.assertIn("final_handoff_target_missing", missing["blockers"])
        self.assertIn("not_cex_review_handoff_route", dex["blockers"])
        self.assertIn("invalid_target_contract_json", drift["blockers"])
        self.assertIn("target_dedupe_key_mismatch", drift["blockers"])
        self.assertEqual(pending["contract_status"], "blocked")
        self.assertEqual(missing["contract_status"], "blocked")
        self.assertEqual(dex["contract_status"], "blocked")
        self.assertEqual(drift["contract_status"], "blocked")


if __name__ == "__main__":
    unittest.main()
