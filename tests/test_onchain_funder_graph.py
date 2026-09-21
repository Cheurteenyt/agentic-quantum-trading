from __future__ import annotations

import json
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import onchain_engine  # noqa: E402
from services.onchain_engine import (  # noqa: E402
    get_cex_label_acquisition_plan,
    get_cex_label_promotion_admin_queue,
    get_cex_label_promotion_backup,
    get_cex_label_promotion_backups,
    get_cex_label_promotion_blocker_audit,
    get_cex_label_promotion_dashboard,
    get_cex_label_promotion_execution_envelope,
    get_cex_label_promotion_final_check,
    get_cex_label_promotion_review,
    get_cex_label_promotion_simulation_report,
    get_cex_label_promotion_stage,
    get_cex_label_promotion_write_preview,
    get_cex_label_independent_evidence_dry_run,
    get_cex_label_independent_evidence_persist_contract,
    get_cex_label_independent_evidence_persist_preview,
    get_cex_label_independent_evidence_review_queue,
    get_cex_label_confidence_upgrade_preview,
    get_cex_label_confidence_upgrade_stage,
    get_cex_label_confidence_upgrade_backup_preview,
    get_cex_label_confidence_upgrade_backup,
    get_cex_label_confidence_upgrade_backups,
    get_cex_label_confidence_upgrade_final_check,
    get_cex_label_confidence_upgrade_execution_envelope,
    get_cex_label_confidence_upgrade_simulation_report,
    get_cex_label_confidence_upgrade_policy_gate,
    get_cex_label_confidence_upgrade_apply,
    get_cex_label_confidence_upgrade_prewrite_audit,
    get_cex_label_confidence_upgrade_controlled_write_review,
    get_cex_label_confidence_upgrade_sql_plan,
    get_cex_label_confidence_upgrade_rollback_smoke,
    get_cex_label_independent_source_queue,
    get_cex_label_source_quality_plan,
    get_cex_independent_evidence_queue_schema_plan,
    create_cex_independent_evidence_queue,
    insert_cex_label_independent_evidence,
    get_funder_graph_readiness,
    get_wallet_cex_deposit_surface,
)


def _fetchone_value(db_path: Path, sql: str):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


class OnchainFunderGraphReadinessTests(unittest.TestCase):
    def test_funder_graph_uses_only_local_transaction_edges(self) -> None:
        wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        funder = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        linked = "0xcccccccccccccccccccccccccccccccccccccccc"
        token_funder = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        token = "0xffffffffffffffffffffffffffffffffffffffff"
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            with patch("services.onchain_engine.DB_PATH", db_path):
                onchain_engine._init_db()
                conn = onchain_engine._get_db()
                try:
                    conn.execute(
                        "INSERT INTO transactions (tx_hash, chain, block_number, from_addr, to_addr, value, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("0xfund1", "bsc", 100, funder, wallet, 0.14, 1778457600),
                    )
                    conn.execute(
                        "INSERT INTO transactions (tx_hash, chain, block_number, from_addr, to_addr, value, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        ("0xfund2", "bsc", 101, funder, linked, 0.03, 1778457660),
                    )
                    conn.execute(
                        (
                            "INSERT INTO token_transfers "
                            "(tx_hash, log_index, chain, block_number, timestamp, token, from_addr, to_addr, value_raw, source) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        ("0xtokenfund", 0, "bsc", 102, 1778457720, token, token_funder, wallet, "1000", "erc20_transfer_log"),
                    )
                    conn.commit()
                finally:
                    conn.close()

                result = get_funder_graph_readiness(wallet, "bsc")

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "local_onchain_db")
        self.assertEqual(result["funders"][0]["address"], funder)
        self.assertEqual(result["funders"][0]["funding_type"], "native_transfer")
        self.assertTrue(any(row["address"] == token_funder and row["funding_type"] == "token_transfer" for row in result["funders"]))
        self.assertEqual(result["gas_distributors"][0]["address"], funder)
        self.assertEqual(result["linked_wallet_count"], 2)
        self.assertEqual(result["cluster_hints"][0]["type"], "shared_native_funder")
        self.assertEqual(result["missing_proofs"], [])

    def test_funder_graph_missing_history_is_explicit(self) -> None:
        wallet = "0xdddddddddddddddddddddddddddddddddddddddd"
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            with patch("services.onchain_engine.DB_PATH", db_path):
                onchain_engine._init_db()
                result = get_funder_graph_readiness(wallet, "bsc")

        self.assertFalse(result["ok"])
        self.assertEqual(result["funders"], [])
        self.assertIn("wallet_funding_history", result["missing_proofs"])
        self.assertIn("gas_distributor_surface", result["missing_proofs"])

    def test_wallet_cex_deposit_surface_requires_source_backed_cex_label(self) -> None:
        wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        cex = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        dex = "0xcccccccccccccccccccccccccccccccccccccccc"
        token = "0xffffffffffffffffffffffffffffffffffffffff"
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            with patch("services.onchain_engine.DB_PATH", db_path):
                onchain_engine._init_db()
                conn = onchain_engine._get_db()
                try:
                    conn.execute(
                        (
                            "INSERT INTO wallet_chain_state "
                            "(chain, address, label, entity, confidence, observed_at, label_sources_json, source_attribution_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        ("bsc", cex, "Binance: Hot Wallet", "Binance", "high", 1778457600, '[{\"source\":\"label_ledger\"}]', "{\"label_seed_source\":\"test\"}"),
                    )
                    conn.execute(
                        (
                            "INSERT INTO wallet_chain_state "
                            "(chain, address, label, entity, confidence, observed_at, label_sources_json, source_attribution_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        ("bsc", dex, "PancakeSwap: Router", "PancakeSwap", "high", 1778457600, '[{\"source\":\"label_ledger\"}]', "{\"label_seed_source\":\"test\"}"),
                    )
                    conn.execute(
                        (
                            "INSERT INTO token_transfers "
                            "(tx_hash, log_index, chain, block_number, timestamp, token, from_addr, to_addr, value_raw, source) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        ("0xcexdeposit", 0, "bsc", 100, 1778457700, token, wallet, cex, "1000", "erc20_transfer_log"),
                    )
                    conn.execute(
                        (
                            "INSERT INTO token_transfers "
                            "(tx_hash, log_index, chain, block_number, timestamp, token, from_addr, to_addr, value_raw, source) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        ("0xdexswap", 0, "bsc", 101, 1778457800, token, wallet, dex, "2000", "erc20_transfer_log"),
                    )
                    conn.commit()
                finally:
                    conn.close()

                result = get_wallet_cex_deposit_surface(wallet, "bsc")

        self.assertTrue(result["ok"])
        self.assertTrue(result["confirmed"])
        self.assertFalse(result["hint_only"])
        self.assertEqual(result["token_transfer_count"], 1)
        self.assertEqual(len(result["deposits"]), 1)
        self.assertEqual(result["deposits"][0]["entity"], "binance")
        self.assertEqual(result["deposits"][0]["proof_status"], "token_transfer_to_source_backed_cex_wallet")

    def test_wallet_cex_deposit_surface_keeps_unbacked_label_as_hint(self) -> None:
        wallet = "0xdddddddddddddddddddddddddddddddddddddddd"
        cex = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        token = "0xffffffffffffffffffffffffffffffffffffffff"
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            with patch("services.onchain_engine.DB_PATH", db_path):
                onchain_engine._init_db()
                conn = onchain_engine._get_db()
                try:
                    conn.execute(
                        (
                            "INSERT INTO wallet_chain_state "
                            "(chain, address, label, entity, confidence, observed_at, label_sources_json, source_attribution_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        ("eth", cex, "Coinbase Deposit", "Coinbase", "low", 1778457600, "[]", "{}"),
                    )
                    conn.execute(
                        (
                            "INSERT INTO token_transfers "
                            "(tx_hash, log_index, chain, block_number, timestamp, token, from_addr, to_addr, value_raw, source) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        ("0xhintdeposit", 0, "eth", 100, 1778457700, token, wallet, cex, "1000", "erc20_transfer_log"),
                    )
                    conn.commit()
                finally:
                    conn.close()

                result = get_wallet_cex_deposit_surface(wallet, "eth")

        self.assertTrue(result["ok"])
        self.assertFalse(result["confirmed"])
        self.assertTrue(result["hint_only"])
        self.assertEqual(result["hint_count"], 1)
        self.assertIn("source_backed_cex_destination_label", result["missing_proofs"])

    def test_cex_label_acquisition_plan_is_read_only_for_gate_mexc_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        1,
                        "bsc",
                        "0x1111111111111111111111111111111111111111",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "high",
                        "candidate",
                        "scrapling_wallet",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                result = get_cex_label_acquisition_plan("gate,mexc", limit=10)

        self.assertTrue(result["ok"])
        self.assertFalse(any(plan["promotion_allowed"] for plan in result["plans"]))
        mexc = next(plan for plan in result["plans"] if plan["entity"] == "mexc")
        self.assertEqual(mexc["open_evm_label_candidates"], 1)
        self.assertFalse(mexc["can_confirm_today"])
        self.assertIn("source_backed_wallet_chain_state_label", mexc["missing_proofs"])
        self.assertEqual(mexc["candidate_examples"][0]["address"], "0x1111111111111111111111111111111111111111")

    def test_cex_label_promotion_review_dry_run_flags_ready_and_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                rows = [
                    (
                        1,
                        "bsc",
                        "0x1111111111111111111111111111111111111111",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "high",
                        "candidate",
                        "scrapling_wallet",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                    (
                        2,
                        "ethereum",
                        "0x2222222222222222222222222222222222222222",
                        "Signer of Gnosis Safe: 0x2222222222222222222222222222222222222222",
                        "Gate",
                        "signer",
                        "medium",
                        "candidate",
                        "scrapling_profile_tag",
                        "https://intel.arkm.com/explorer/entity/gate-io",
                        '[{"file":"entity_gate-io.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                ]
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    rows,
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                result = get_cex_label_promotion_review("gate,mexc", limit=10)

        self.assertTrue(result["ok"])
        ready = [row for row in result["rows"] if row["promotion_ready"]]
        blocked = [row for row in result["rows"] if not row["promotion_ready"]]
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["entity"], "mexc")
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["entity"], "gate")
        self.assertIn("high_confidence_required", blocked[0]["blockers"])
        self.assertIn("signer_candidate_requires_manual_review", blocked[0]["blockers"])

    def test_cex_label_promotion_write_preview_never_writes_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "bsc",
                            "0x1111111111111111111111111111111111111111",
                            "MEXC: Hot Wallet",
                            "MEXC",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "ethereum",
                            "0x2222222222222222222222222222222222222222",
                            "Signer of Gnosis Safe: 0x2222222222222222222222222222222222222222",
                            "Gate",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                result = get_cex_label_promotion_write_preview([1, 2, 404], dry_run=True)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                refused = get_cex_label_promotion_write_preview([1], dry_run=False, confirm="PROMOTE_STRICT_CEX_LABELS")

        self.assertTrue(result["ok"])
        self.assertEqual(result["write_preview_count"], 1)
        self.assertEqual(result["write_preview"][0]["entity"], "mexc")
        self.assertEqual(result["writes_performed"], 0)
        self.assertEqual(row_count, 0)
        blockers = {item["candidate_id"]: item["blockers"] for item in result["blocked"]}
        self.assertIn("signer_candidate_requires_manual_review", blockers[2])
        self.assertIn("candidate_id_unknown", blockers[404])
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["refused_reason"], "real_write_disabled_until_admin_flow_is_validated")
        self.assertEqual(refused["writes_performed"], 0)

    def test_cex_label_promotion_admin_queue_groups_candidates_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "bsc",
                            "0x1111111111111111111111111111111111111111",
                            "MEXC: Hot Wallet",
                            "MEXC",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "ethereum",
                            "0x2222222222222222222222222222222222222222",
                            "Signer of Gnosis Safe: 0x2222222222222222222222222222222222222222",
                            "Gate",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                result = get_cex_label_promotion_admin_queue("gate,mexc", limit=10)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["ready_for_preview"], 1)
        self.assertEqual(result["summary"]["blocked_manual_review"], 1)
        ready = result["groups"]["ready_for_preview"][0]
        blocked = result["groups"]["blocked_manual_review"][0]
        self.assertTrue(ready["write_preview_available"])
        self.assertEqual(ready["next_admin_action"], "Open write-preview with this candidate_id; no DB write will happen by default.")
        self.assertFalse(blocked["write_preview_available"])
        self.assertIn("signer_candidate_requires_manual_review", blocked["blockers"])
        self.assertTrue(blocked["blocker_explanations"])
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_stage_is_single_candidate_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "base",
                            "0x1111111111111111111111111111111111111111",
                            "Gate: Hot Wallet",
                            "Gate",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "ethereum",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Signer",
                            "MEXC",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                multi = get_cex_label_promotion_stage("1,2", dry_run=True)
                blocked = get_cex_label_promotion_stage(2, dry_run=True)
                ready = get_cex_label_promotion_stage(1, dry_run=True)
                confirmed = get_cex_label_promotion_stage(1, dry_run=False, confirm="STAGE_STRICT_CEX_LABEL")
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertFalse(multi["ok"])
        self.assertIn("single_candidate_required", multi["blockers"])
        self.assertFalse(blocked["ok"])
        self.assertFalse(blocked["promotion_ready"])
        self.assertIn("high_confidence_required", blocked["blockers"])
        self.assertTrue(ready["ok"])
        self.assertTrue(ready["promotion_ready"])
        self.assertTrue(ready["backup_required"])
        self.assertTrue(ready["rollback_required"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["would_insert_or_update"], "insert")
        self.assertIsNone(ready["existing_wallet_chain_state_row"])
        self.assertEqual(ready["rollback_plan"]["rollback_action"], "delete_inserted_row")
        self.assertEqual(ready["writes_performed"], 0)
        self.assertFalse(confirmed["ok"])
        self.assertEqual(confirmed["refused_reason"], "real_write_disabled_until_backup_rollback_is_implemented")
        self.assertEqual(confirmed["writes_performed"], 0)
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_stage_previews_update_rollback_for_existing_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        1,
                        "base",
                        "0x1111111111111111111111111111111111111111",
                        "Gate: Hot Wallet",
                        "Gate",
                        "cex",
                        "high",
                        "candidate",
                        "scrapling_wallet",
                        "https://intel.arkm.com/explorer/entity/gate-io",
                        '[{"file":"entity_gate-io.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        (
                            "INSERT INTO wallet_chain_state "
                            "(chain, address, label, entity, confidence, observed_at, label_sources_json, source_attribution_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        (
                            "base",
                            "0x1111111111111111111111111111111111111111",
                            "Old Label",
                            "Unknown",
                            "low",
                            1778457600,
                            "[]",
                            "{}",
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

                result = get_cex_label_promotion_stage(1, dry_run=True)
                conn = sqlite3.connect(db_path)
                try:
                    row = conn.execute(
                        "SELECT label, entity FROM wallet_chain_state WHERE chain = ? AND address = ?",
                        ("base", "0x1111111111111111111111111111111111111111"),
                    ).fetchone()
                finally:
                    conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["would_insert_or_update"], "update")
        self.assertEqual(result["existing_wallet_chain_state_row"]["label"], "Old Label")
        self.assertEqual(result["rollback_plan"]["rollback_action"], "restore_existing_row")
        self.assertEqual(row[0], "Old Label")
        self.assertEqual(row[1], "Unknown")

    def test_cex_label_promotion_backup_artifact_dry_run_and_confirmed_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "base",
                            "0x1111111111111111111111111111111111111111",
                            "Gate: Hot Wallet",
                            "Gate",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "ethereum",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Signer",
                            "MEXC",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                dry_run = get_cex_label_promotion_backup(1, dry_run=True)
                missing_confirm = get_cex_label_promotion_backup(1, dry_run=False)
                blocked = get_cex_label_promotion_backup(
                    2,
                    dry_run=False,
                    confirm="CREATE_STRICT_CEX_LABEL_BACKUP",
                )
                created = get_cex_label_promotion_backup(
                    1,
                    dry_run=False,
                    confirm="CREATE_STRICT_CEX_LABEL_BACKUP",
                )
                backup_path = Path(created["backup_path"])
                backup_exists = backup_path.exists()
                payload = json.loads(backup_path.read_text(encoding="utf-8"))
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(dry_run["ok"])
        self.assertFalse(dry_run["backup_created"])
        self.assertFalse(backup_dir.exists())
        self.assertFalse(missing_confirm["ok"])
        self.assertEqual(missing_confirm["refused_reason"], "confirm_CREATE_STRICT_CEX_LABEL_BACKUP_required")
        self.assertFalse(blocked["ok"])
        self.assertIn("high_confidence_required", blocked["blockers"])
        self.assertTrue(created["ok"])
        self.assertTrue(created["backup_created"])
        self.assertTrue(backup_exists)
        self.assertEqual(
            set(payload),
            {
                "candidate_id",
                "write_preview",
                "existing_wallet_chain_state_row",
                "rollback_plan",
                "created_at",
                "source_policy",
            },
        )
        self.assertEqual(payload["candidate_id"], 1)
        self.assertIsNone(payload["existing_wallet_chain_state_row"])
        self.assertEqual(payload["rollback_plan"]["rollback_action"], "delete_inserted_row")
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_backup_artifact_captures_existing_row_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        1,
                        "base",
                        "0x1111111111111111111111111111111111111111",
                        "Gate: Hot Wallet",
                        "Gate",
                        "cex",
                        "high",
                        "candidate",
                        "scrapling_wallet",
                        "https://intel.arkm.com/explorer/entity/gate-io",
                        '[{"file":"entity_gate-io.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        (
                            "INSERT INTO wallet_chain_state "
                            "(chain, address, label, entity, confidence, observed_at, label_sources_json, source_attribution_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                        ),
                        (
                            "base",
                            "0x1111111111111111111111111111111111111111",
                            "Old Label",
                            "Unknown",
                            "low",
                            1778457600,
                            "[]",
                            "{}",
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

                created = get_cex_label_promotion_backup(
                    1,
                    dry_run=False,
                    confirm="CREATE_STRICT_CEX_LABEL_BACKUP",
                )
                payload = json.loads(Path(created["backup_path"]).read_text(encoding="utf-8"))
                conn = sqlite3.connect(db_path)
                try:
                    row = conn.execute(
                        "SELECT label, entity FROM wallet_chain_state WHERE chain = ? AND address = ?",
                        ("base", "0x1111111111111111111111111111111111111111"),
                    ).fetchone()
                finally:
                    conn.close()

        self.assertTrue(created["ok"])
        self.assertEqual(payload["existing_wallet_chain_state_row"]["label"], "Old Label")
        self.assertEqual(payload["rollback_plan"]["rollback_action"], "restore_existing_row")
        self.assertEqual(row[0], "Old Label")
        self.assertEqual(row[1], "Unknown")

    def test_cex_label_promotion_backups_report_missing_and_valid_artifacts_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            backup_dir = Path(tmpdir) / "backups"
            valid_payload = {
                "candidate_id": 1,
                "write_preview": {"chain": "base", "address": "0x1111111111111111111111111111111111111111"},
                "existing_wallet_chain_state_row": None,
                "rollback_plan": {"rollback_action": "delete_inserted_row"},
                "created_at": "2026-05-13T00:00:00Z",
                "source_policy": "test backup",
            }
            backup_dir.mkdir(parents=True)
            (backup_dir / "cex_label_promotion_candidate_1_20260513T000000Z.json").write_text(
                json.dumps(valid_payload),
                encoding="utf-8",
            )

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                missing = get_cex_label_promotion_backups(2, limit=20)
                result = get_cex_label_promotion_backups(1, limit=20)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(missing["ok"])
        self.assertFalse(missing["valid_backup_available"])
        self.assertIn("valid_backup_artifact", missing["missing_proofs"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["backup_count"], 1)
        self.assertTrue(result["valid_backup_available"])
        self.assertTrue(result["future_promotion_gate"]["backup_artifact_ready"])
        self.assertFalse(result["future_promotion_gate"]["real_write_enabled"])
        self.assertEqual(result["latest_backup"]["candidate_id"], 1)
        self.assertEqual(result["missing_proofs"], [])
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_backups_flags_invalid_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            backup_dir = Path(tmpdir) / "backups"
            backup_dir.mkdir(parents=True)
            (backup_dir / "cex_label_promotion_candidate_1_20260513T000000Z.json").write_text(
                json.dumps({
                    "candidate_id": 1,
                    "write_preview": {"chain": "base"},
                    "created_at": "2026-05-13T00:00:00Z",
                    "source_policy": "test backup",
                }),
                encoding="utf-8",
            )
            (backup_dir / "cex_label_promotion_candidate_1_20260513T000001Z.json").write_text(
                "{not-json",
                encoding="utf-8",
            )

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                result = get_cex_label_promotion_backups(1, limit=20)

        self.assertTrue(result["ok"])
        self.assertEqual(result["backup_count"], 2)
        self.assertFalse(result["valid_backup_available"])
        self.assertIn("valid_backup_artifact", result["missing_proofs"])
        all_missing = {proof for backup in result["backups"] for proof in backup["missing_proofs"]}
        self.assertIn("rollback_plan", all_missing)
        self.assertIn("existing_wallet_chain_state_row", all_missing)
        self.assertIn("backup_json_valid", all_missing)

    def test_cex_label_promotion_final_check_requires_ready_candidate_and_backup_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "base",
                            "0x1111111111111111111111111111111111111111",
                            "Gate: Hot Wallet",
                            "Gate",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "ethereum",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Signer",
                            "MEXC",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                non_ready = get_cex_label_promotion_final_check(2)
                without_backup = get_cex_label_promotion_final_check(1)
                backup = get_cex_label_promotion_backup(
                    1,
                    dry_run=False,
                    confirm="CREATE_STRICT_CEX_LABEL_BACKUP",
                )
                with_backup = get_cex_label_promotion_final_check(1)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertFalse(non_ready["promotion_ready"])
        self.assertIn("high_confidence_required", non_ready["blockers"])
        self.assertFalse(non_ready["all_gates_ready"])
        self.assertTrue(without_backup["promotion_ready"])
        self.assertTrue(without_backup["write_preview_ready"])
        self.assertFalse(without_backup["backup_artifact_ready"])
        self.assertIn("valid_backup_artifact", without_backup["missing_proofs"])
        self.assertTrue(backup["backup_created"])
        self.assertTrue(with_backup["all_gates_ready"])
        self.assertTrue(with_backup["backup_artifact_ready"])
        self.assertTrue(with_backup["rollback_plan_ready"])
        self.assertTrue(with_backup["existing_row_captured"])
        self.assertFalse(with_backup["real_write_enabled"])
        self.assertFalse(with_backup["label_promotion_enabled"])
        self.assertEqual(with_backup["writes_performed"], 0)
        self.assertEqual(with_backup["missing_proofs"], [])
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_execution_envelope_is_dry_run_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        1,
                        "base",
                        "0x1111111111111111111111111111111111111111",
                        "Gate: Hot Wallet",
                        "Gate",
                        "cex",
                        "high",
                        "candidate",
                        "scrapling_wallet",
                        "https://intel.arkm.com/explorer/entity/gate-io",
                        '[{"file":"entity_gate-io.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                without_backup = get_cex_label_promotion_execution_envelope(1, dry_run=True)
                backup = get_cex_label_promotion_backup(
                    1,
                    dry_run=False,
                    confirm="CREATE_STRICT_CEX_LABEL_BACKUP",
                )
                with_backup = get_cex_label_promotion_execution_envelope(1, dry_run=True)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertFalse(without_backup["all_gates_ready"])
        self.assertFalse(without_backup["would_write"])
        self.assertIsNone(without_backup["write_preview"])
        self.assertIn("valid_backup_artifact", without_backup["missing_proofs"])
        self.assertTrue(backup["backup_created"])
        self.assertTrue(with_backup["all_gates_ready"])
        self.assertTrue(with_backup["would_write"])
        self.assertIsNotNone(with_backup["write_preview"])
        self.assertIsNotNone(with_backup["backup_artifact"])
        self.assertIsNotNone(with_backup["rollback_plan"])
        self.assertFalse(with_backup["execution_allowed"])
        self.assertFalse(with_backup["real_write_enabled"])
        self.assertFalse(with_backup["label_promotion_enabled"])
        self.assertEqual(with_backup["writes_performed"], 0)
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_simulation_report_is_admin_readable_and_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        1,
                        "base",
                        "0x1111111111111111111111111111111111111111",
                        "Gate: Hot Wallet",
                        "Gate",
                        "cex",
                        "high",
                        "candidate",
                        "scrapling_wallet",
                        "https://intel.arkm.com/explorer/entity/gate-io",
                        '[{"file":"entity_gate-io.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                blocked = get_cex_label_promotion_simulation_report(1)
                backup = get_cex_label_promotion_backup(
                    1,
                    dry_run=False,
                    confirm="CREATE_STRICT_CEX_LABEL_BACKUP",
                )
                ready = get_cex_label_promotion_simulation_report(1)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertEqual(blocked["status"], "blocked")
        self.assertFalse(blocked["would_write"])
        self.assertIn("valid_backup_artifact", blocked["blocking_reasons"])
        self.assertTrue(backup["backup_created"])
        self.assertEqual(ready["status"], "ready_but_disabled")
        self.assertTrue(ready["would_write"])
        self.assertEqual(ready["write_preview_summary"]["entity"], "gate")
        self.assertTrue(ready["backup_summary"]["valid"])
        self.assertEqual(ready["rollback_summary"]["rollback_action"], "delete_inserted_row")
        self.assertFalse(ready["execution_allowed"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertFalse(ready["label_promotion_enabled"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertNotIn("path", ready["backup_summary"])
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_dashboard_aggregates_gates_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "base",
                            "0x1111111111111111111111111111111111111111",
                            "Gate: Hot Wallet",
                            "Gate",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "ethereum",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Signer",
                            "MEXC",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_LABEL_PROMOTION_BACKUP_DIR", backup_dir),
            ):
                onchain_engine._init_db()
                before = get_cex_label_promotion_dashboard("gate,mexc", limit=10)
                backup = get_cex_label_promotion_backup(
                    1,
                    dry_run=False,
                    confirm="CREATE_STRICT_CEX_LABEL_BACKUP",
                )
                after = get_cex_label_promotion_dashboard("gate,mexc", limit=10)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        before_rows = {row["candidate_id"]: row for row in before["rows"]}
        after_rows = {row["candidate_id"]: row for row in after["rows"]}

        self.assertTrue(before["ok"])
        self.assertIn("blocked_missing_backup", before["groups"])
        self.assertEqual(before["summary"]["rows"], 2)
        self.assertLessEqual(before["summary"]["limit"], 50)
        self.assertTrue(before_rows[1]["promotion_ready"])
        self.assertEqual(before_rows[1]["admin_group"], "blocked_missing_backup")
        self.assertFalse(before_rows[1]["backup_artifact_ready"])
        self.assertFalse(before_rows[1]["final_check_all_gates_ready"])
        self.assertEqual(before_rows[1]["simulation_status"], "blocked")
        self.assertFalse(before_rows[1]["would_write"])
        self.assertFalse(before_rows[1]["execution_allowed"])
        self.assertFalse(before_rows[1]["real_write_enabled"])
        self.assertIn("valid_backup_artifact", before_rows[1]["missing_proofs"])
        self.assertEqual(before_rows[2]["admin_group"], "blocked_manual_review")
        self.assertIn("signer_candidate_requires_manual_review", before_rows[2]["blockers"])

        self.assertTrue(backup["backup_created"])
        self.assertEqual(after_rows[1]["admin_group"], "ready_but_disabled")
        self.assertTrue(after_rows[1]["backup_artifact_ready"])
        self.assertTrue(after_rows[1]["final_check_all_gates_ready"])
        self.assertEqual(after_rows[1]["simulation_status"], "ready_but_disabled")
        self.assertTrue(after_rows[1]["would_write"])
        self.assertFalse(after_rows[1]["execution_allowed"])
        self.assertFalse(after_rows[1]["real_write_enabled"])
        self.assertEqual(after_rows[1]["writes_performed"], 0)
        self.assertEqual(row_count, 0)

    def test_cex_label_promotion_blocker_audit_keeps_manual_and_low_confidence_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "ethereum",
                            "0x1111111111111111111111111111111111111111",
                            "Signer of Gnosis Safe: 0x1111111111111111111111111111111111111111",
                            "Gate",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "bsc",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Hot Wallet",
                            "MEXC",
                            "cex",
                            "medium",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                result = get_cex_label_promotion_blocker_audit("gate,mexc", limit=10)
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["blocked_manual_review"], 1)
        self.assertEqual(result["summary"]["blocked_low_confidence"], 1)
        manual = result["groups"]["blocked_manual_review"][0]
        low_conf = result["groups"]["blocked_low_confidence"][0]
        self.assertIn("signer_candidate_requires_manual_review", manual["blockers"])
        self.assertIn("high_confidence_required", low_conf["blockers"])
        self.assertTrue(manual["blocker_explanations"])
        self.assertEqual(manual["evidence_summary"]["evidence_count"], 1)
        self.assertFalse(manual["can_be_fixed_automatically"])
        self.assertFalse(low_conf["can_be_fixed_automatically"])
        self.assertFalse(result["summary"]["can_be_fixed_automatically"])
        self.assertEqual(result["summary"]["writes_performed"], 0)
        self.assertEqual(row_count, 0)

    def test_cex_label_source_quality_plan_is_read_only_for_low_confidence_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            1,
                            "base",
                            "0x1111111111111111111111111111111111111111",
                            "Gate: Hot Wallet",
                            "Gate",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_wallet",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            2,
                            "bsc",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Hot Wallet",
                            "MEXC",
                            "cex",
                            "medium",
                            "candidate",
                            "scrapling_transfer_side",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                before_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")
                result = get_cex_label_source_quality_plan("gate,mexc", limit=10)
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["rows"], 1)
        row = result["rows"][0]
        self.assertEqual(row["candidate_id"], 2)
        self.assertEqual(row["current_confidence"], "medium")
        self.assertEqual(row["target_confidence"], "high")
        self.assertFalse(row["upgrade_possible"])
        self.assertIn("second_independent_source_or_manual_admin_review", row["required_evidence"])
        self.assertIn("high_confidence_required", row["blocked_by"])
        self.assertEqual(before_conf, "medium")
        self.assertEqual(after_conf, "medium")
        self.assertEqual(row_count, 0)

    def test_cex_label_independent_source_queue_is_read_only_work_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                before_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")
                result = get_cex_label_independent_source_queue("gate,mexc", limit=10)
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(result["summary"]["rows"], 1)
        self.assertFalse(result["summary"]["automation_allowed"])
        row = result["rows"][0]
        self.assertEqual(row["candidate_id"], 2)
        self.assertFalse(row["automation_allowed"])
        self.assertIn("block_explorer_verified_label", row["accepted_evidence_types"])
        self.assertIn("single_scrapling_transfer_side_only", row["rejected_evidence_types"])
        self.assertTrue(any("0x2222222222222222222222222222222222222222" in query for query in row["search_queries"]))
        self.assertEqual(before_conf, "medium")
        self.assertEqual(after_conf, "medium")
        self.assertEqual(row_count, 0)

    def test_cex_label_independent_evidence_dry_run_validates_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            2,
                            "bsc",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Hot Wallet",
                            "MEXC",
                            "cex",
                            "medium",
                            "candidate",
                            "scrapling_transfer_side",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            3,
                            "ethereum",
                            "0x3333333333333333333333333333333333333333",
                            "Signer of Gnosis Safe: 0x3333333333333333333333333333333333333333",
                            "Gate",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_profile_tag",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate-io.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                accepted = get_cex_label_independent_evidence_dry_run(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    True,
                )
                rejected_type = get_cex_label_independent_evidence_dry_run(
                    2,
                    "single_scrapling_transfer_side_only",
                    "https://example.com/source",
                    None,
                    True,
                )
                manual = get_cex_label_independent_evidence_dry_run(
                    3,
                    "block_explorer_verified_label",
                    "https://etherscan.io/address/0x3333333333333333333333333333333333333333",
                    None,
                    True,
                )
                before_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(accepted["ok"])
        self.assertTrue(accepted["evidence_accepted"])
        self.assertTrue(accepted["would_improve_source_quality"])
        self.assertFalse(accepted["would_change_confidence"])
        self.assertFalse(accepted["would_write"])
        self.assertEqual(accepted["writes_performed"], 0)
        self.assertFalse(rejected_type["ok"])
        self.assertIn("accepted_evidence_type_required", rejected_type["validation"]["errors"])
        self.assertIn("rejected_evidence_type", rejected_type["validation"]["errors"])
        self.assertFalse(manual["ok"])
        self.assertIn("manual_review_candidate_not_source_quality_intake", manual["validation"]["errors"])
        self.assertEqual(before_conf, "medium")
        self.assertEqual(row_count, 0)

    def test_cex_label_independent_evidence_persist_preview_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with patch("services.onchain_engine.DB_PATH", db_path), patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path):
                onchain_engine._init_db()
                rejected = get_cex_label_independent_evidence_persist_preview(
                    2,
                    "single_scrapling_transfer_side_only",
                    "https://example.com/source",
                    None,
                    True,
                )
                accepted = get_cex_label_independent_evidence_persist_preview(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    True,
                )
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")
                conn = sqlite3.connect(db_path)
                try:
                    row_count = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                    table_exists = conn.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cex_independent_evidence_queue'"
                    ).fetchone()[0]
                finally:
                    conn.close()

        self.assertFalse(rejected["would_persist"])
        self.assertTrue(accepted["ok"])
        self.assertTrue(accepted["would_persist"])
        self.assertEqual(accepted["target_table"], "cex_independent_evidence_queue")
        self.assertIn("candidate_id", accepted["target_fields"])
        self.assertIn("dedupe_key", accepted["target_fields"])
        self.assertIn("cex_independent_evidence:2:block_explorer_verified_label:", accepted["dedupe_key"])
        self.assertFalse(accepted["would_change_confidence"])
        self.assertFalse(accepted["would_promote_label"])
        self.assertFalse(accepted["would_write"])
        self.assertEqual(accepted["writes_performed"], 0)
        self.assertEqual(after_conf, "medium")
        self.assertEqual(row_count, 0)
        self.assertEqual(table_exists, 0)

    def test_cex_independent_evidence_queue_schema_plan_is_dry_run_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            with patch("services.onchain_engine.DB_PATH", db_path):
                result = get_cex_independent_evidence_queue_schema_plan(dry_run=True)
                refused = get_cex_independent_evidence_queue_schema_plan(dry_run=False)
                conn = sqlite3.connect(db_path)
                try:
                    table_exists = conn.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cex_independent_evidence_queue'"
                    ).fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["table_exists"])
        self.assertTrue(result["migration_required"])
        self.assertEqual(result["target_table"], "cex_independent_evidence_queue")
        self.assertTrue(result["schema_preview"])
        self.assertTrue(result["indexes_preview"])
        self.assertFalse(result["would_create_table"])
        self.assertFalse(result["would_write"])
        self.assertEqual(result["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "dry_run_required")
        self.assertEqual(table_exists, 0)
        self.assertEqual(wallet_rows, 0)

    def test_create_cex_independent_evidence_queue_requires_confirm_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
            ):
                dry_run = create_cex_independent_evidence_queue(dry_run=True)
                refused = create_cex_independent_evidence_queue(dry_run=False)
                created = create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                second = create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                conn = sqlite3.connect(db_path)
                try:
                    table_exists = conn.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='cex_independent_evidence_queue'"
                    ).fetchone()[0]
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                    index_count = conn.execute(
                        """
                        SELECT COUNT(*) FROM sqlite_master
                        WHERE type='index'
                          AND name IN (
                              'idx_cex_independent_evidence_candidate',
                              'idx_cex_independent_evidence_entity_chain',
                              'idx_cex_independent_evidence_status',
                              'ux_cex_independent_evidence_dedupe'
                          )
                        """
                    ).fetchone()[0]
                finally:
                    conn.close()
                ledger_count = _fetchone_value(ledger_path, "SELECT COUNT(*) FROM label_candidates")

        self.assertTrue(dry_run["ok"])
        self.assertTrue(dry_run["would_create_table"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "confirm_CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE_required")
        self.assertTrue(created["ok"])
        self.assertTrue(created["table_created"])
        self.assertEqual(len(created["indexes_created"]), 4)
        self.assertEqual(created["writes_performed"], 5)
        self.assertTrue(second["ok"])
        self.assertFalse(second["table_created"])
        self.assertEqual(second["indexes_created"], [])
        self.assertEqual(second["writes_performed"], 0)
        self.assertEqual(table_exists, 1)
        self.assertEqual(index_count, 4)
        self.assertEqual(evidence_rows, 0)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(ledger_count, 1)

    def test_cex_label_independent_evidence_persist_contract_checks_table_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
            ):
                missing_table = get_cex_label_independent_evidence_persist_contract(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    True,
                )
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                ready = get_cex_label_independent_evidence_persist_contract(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    True,
                )
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        """
                        INSERT INTO cex_independent_evidence_queue
                        (candidate_id, entity, chain, address, label, evidence_type, source_url, notes,
                         dedupe_key, status, created_at, source_policy)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            2,
                            "mexc",
                            "bsc",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Hot Wallet",
                            "block_explorer_verified_label",
                            "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                            "Verified explorer label",
                            ready["dedupe_key"],
                            "pending_admin_review",
                            "2026-05-13T00:00:00Z",
                            "fixture duplicate row",
                        ),
                    )
                    conn.commit()
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                duplicate = get_cex_label_independent_evidence_persist_contract(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    True,
                )
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertTrue(missing_table["ok"])
        self.assertFalse(missing_table["table_ready"])
        self.assertEqual(missing_table["dedupe_status"], "table_missing")
        self.assertFalse(missing_table["would_insert"])
        self.assertTrue(ready["table_ready"])
        self.assertEqual(ready["dedupe_status"], "new")
        self.assertTrue(ready["would_insert"])
        self.assertFalse(ready["would_write"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertEqual(duplicate["dedupe_status"], "duplicate")
        self.assertFalse(duplicate["would_insert"])
        self.assertFalse(duplicate["would_change_confidence"])
        self.assertFalse(duplicate["would_promote_label"])
        self.assertEqual(after_conf, "medium")
        self.assertEqual(wallet_rows, 0)

    def test_insert_cex_label_independent_evidence_is_confirmed_and_deduped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
            ):
                table_missing = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                dry_run = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    True,
                )
                refused = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    None,
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                duplicate = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                    staged = conn.execute(
                        "SELECT candidate_id, evidence_type, status FROM cex_independent_evidence_queue"
                    ).fetchone()
                finally:
                    conn.close()
                ledger_conn = sqlite3.connect(ledger_path)
                try:
                    after_conf = ledger_conn.execute(
                        "SELECT confidence FROM label_candidates WHERE id = 2"
                    ).fetchone()[0]
                    ledger_count = ledger_conn.execute("SELECT COUNT(*) FROM label_candidates").fetchone()[0]
                finally:
                    ledger_conn.close()

        self.assertFalse(table_missing["ok"])
        self.assertIn("table_missing", table_missing["error"])
        self.assertTrue(dry_run["ok"])
        self.assertTrue(dry_run["would_insert"])
        self.assertFalse(dry_run["inserted"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "confirm_INSERT_CEX_INDEPENDENT_EVIDENCE_required")
        self.assertTrue(inserted["ok"])
        self.assertTrue(inserted["inserted"])
        self.assertIsNotNone(inserted["row_id"])
        self.assertEqual(inserted["writes_performed"], 1)
        self.assertFalse(inserted["would_change_confidence"])
        self.assertFalse(inserted["would_promote_label"])
        self.assertFalse(duplicate["ok"])
        self.assertEqual(duplicate["dedupe_status"], "duplicate")
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(staged, (2, "block_explorer_verified_label", "pending_admin_review"))
        self.assertEqual(after_conf, "medium")
        self.assertEqual(ledger_count, 1)

    def test_cex_label_independent_evidence_review_queue_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                rows = [
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                    (
                        3,
                        "bsc",
                        "0x3333333333333333333333333333333333333333",
                        "Gate Signer",
                        "Gate",
                        "signer",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/gate-io",
                        '[{"file":"entity_gate.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                ]
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    rows,
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        """
                        INSERT INTO cex_independent_evidence_queue
                        (candidate_id, entity, chain, address, label, evidence_type, source_url, notes,
                         dedupe_key, status, created_at, source_policy)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            3,
                            "gate",
                            "bsc",
                            "0x3333333333333333333333333333333333333333",
                            "Gate Signer",
                            "block_explorer_verified_label",
                            "https://bscscan.com/address/0x3333333333333333333333333333333333333333",
                            "Signer candidate fixture",
                            "signer-candidate-dedupe",
                            "pending_admin_review",
                            "2026-05-13T00:00:00Z",
                            "fixture signer review row",
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO cex_independent_evidence_queue
                        (candidate_id, entity, chain, address, label, evidence_type, source_url, notes,
                         dedupe_key, status, created_at, source_policy)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            9999,
                            "gate",
                            "bsc",
                            "0x9999999999999999999999999999999999999999",
                            "Gate Missing",
                            "block_explorer_verified_label",
                            "https://bscscan.com/address/0x9999999999999999999999999999999999999999",
                            "Missing candidate",
                            "missing-candidate-dedupe",
                            "pending_admin_review",
                            "2026-05-13T00:00:00Z",
                            "fixture missing candidate",
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

                pending = get_cex_label_independent_evidence_review_queue("pending_admin_review", 50)
                done = get_cex_label_independent_evidence_review_queue("reviewed", 50)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertTrue(pending["ok"])
        self.assertEqual(pending["summary"]["rows"], 3)
        by_candidate = {row["candidate_id"]: row for row in pending["rows"]}
        self.assertEqual(by_candidate[2]["review_readiness"], "ready_for_admin_source_review")
        self.assertEqual(by_candidate[2]["candidate_current_confidence"], "medium")
        self.assertFalse(by_candidate[2]["would_change_confidence"])
        self.assertFalse(by_candidate[2]["would_promote_label"])
        self.assertEqual(by_candidate[3]["review_readiness"], "manual_risk_review_required")
        self.assertIn("signer_candidate_requires_manual_review", by_candidate[3]["review_blockers"])
        self.assertEqual(by_candidate[9999]["review_readiness"], "blocked")
        self.assertIn("candidate_missing", by_candidate[9999]["review_blockers"])
        self.assertEqual(done["summary"]["rows"], 0)
        self.assertEqual(evidence_rows, 3)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_preview_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.executemany(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    [
                        (
                            2,
                            "bsc",
                            "0x2222222222222222222222222222222222222222",
                            "MEXC: Hot Wallet",
                            "MEXC",
                            "cex",
                            "medium",
                            "candidate",
                            "scrapling_transfer_side",
                            "https://intel.arkm.com/explorer/entity/mexc",
                            '[{"file":"entity_mexc.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            3,
                            "bsc",
                            "0x3333333333333333333333333333333333333333",
                            "Gate Signer",
                            "Gate",
                            "signer",
                            "medium",
                            "candidate",
                            "scrapling_transfer_side",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                        (
                            4,
                            "bsc",
                            "0x4444444444444444444444444444444444444444",
                            "Gate Hot Wallet",
                            "Gate",
                            "cex",
                            "high",
                            "candidate",
                            "scrapling_transfer_side",
                            "https://intel.arkm.com/explorer/entity/gate-io",
                            '[{"file":"entity_gate.json"}]',
                            42,
                            "2026-05-12T00:00:00Z",
                        ),
                    ],
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                clean = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                conn = sqlite3.connect(db_path)
                try:
                    conn.executemany(
                        """
                        INSERT INTO cex_independent_evidence_queue
                        (candidate_id, entity, chain, address, label, evidence_type, source_url, notes,
                         dedupe_key, status, created_at, source_policy)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                2,
                                "mexc",
                                "bsc",
                                "0x2222222222222222222222222222222222222222",
                                "MEXC: Hot Wallet",
                                "block_explorer_verified_label",
                                "https://bscscan.com/address/0x2222222222222222222222222222222222222222?reviewed=1",
                                "Reviewed fixture",
                                "reviewed-clean-dedupe",
                                "reviewed",
                                "2026-05-13T00:00:00Z",
                                "fixture reviewed evidence",
                            ),
                            (
                                3,
                                "gate",
                                "bsc",
                                "0x3333333333333333333333333333333333333333",
                                "Gate Signer",
                                "block_explorer_verified_label",
                                "https://bscscan.com/address/0x3333333333333333333333333333333333333333",
                                "Signer fixture",
                                "signer-upgrade-dedupe",
                                "pending_admin_review",
                                "2026-05-13T00:00:00Z",
                                "fixture signer evidence",
                            ),
                            (
                                4,
                                "gate",
                                "bsc",
                                "0x4444444444444444444444444444444444444444",
                                "Gate Hot Wallet",
                                "block_explorer_verified_label",
                                "https://bscscan.com/address/0x4444444444444444444444444444444444444444",
                                "High confidence fixture",
                                "high-upgrade-dedupe",
                                "pending_admin_review",
                                "2026-05-13T00:00:00Z",
                                "fixture high evidence",
                            ),
                        ],
                    )
                    conn.commit()
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                    signer_id = conn.execute(
                        "SELECT id FROM cex_independent_evidence_queue WHERE candidate_id = 3"
                    ).fetchone()[0]
                    high_id = conn.execute(
                        "SELECT id FROM cex_independent_evidence_queue WHERE candidate_id = 4"
                    ).fetchone()[0]
                    reviewed_id = conn.execute(
                        "SELECT id FROM cex_independent_evidence_queue WHERE status = 'reviewed'"
                    ).fetchone()[0]
                finally:
                    conn.close()

                ready = get_cex_label_confidence_upgrade_preview(clean["row_id"], "high", True)
                bad_target = get_cex_label_confidence_upgrade_preview(clean["row_id"], "medium", True)
                missing = get_cex_label_confidence_upgrade_preview(9999, "high", True)
                reviewed = get_cex_label_confidence_upgrade_preview(reviewed_id, "high", True)
                signer = get_cex_label_confidence_upgrade_preview(signer_id, "high", True)
                already_high = get_cex_label_confidence_upgrade_preview(high_id, "high", True)
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertTrue(ready["upgrade_preview_available"])
        self.assertFalse(ready["would_change_confidence"])
        self.assertFalse(ready["would_promote_label"])
        self.assertFalse(ready["would_write"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertIn("target_confidence_high_required", bad_target["blockers"])
        self.assertIn("evidence_missing", missing["blockers"])
        self.assertIn("evidence_not_pending", reviewed["blockers"])
        self.assertIn("manual_risk_review_required", signer["blockers"])
        self.assertIn("candidate_already_high_confidence", already_high["blockers"])
        self.assertEqual(evidence_rows, 4)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_stage_is_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                dry_run = get_cex_label_confidence_upgrade_stage(inserted["row_id"], "high", True)
                confirmed_stage = get_cex_label_confidence_upgrade_stage(
                    inserted["row_id"],
                    "high",
                    False,
                    "STAGE_CEX_CONFIDENCE_UPGRADE",
                )
                refused = get_cex_label_confidence_upgrade_stage(inserted["row_id"], "high", False, None)
                blocked = get_cex_label_confidence_upgrade_stage(inserted["row_id"], "medium", True)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertTrue(dry_run["stage_ready"])
        self.assertTrue(dry_run["would_update_label_candidates"])
        self.assertEqual(dry_run["label_candidates_update_preview"]["table"], "label_candidates")
        self.assertEqual(dry_run["label_candidates_update_preview"]["set"]["confidence"], "high")
        self.assertFalse(dry_run["real_write_enabled"])
        self.assertFalse(dry_run["would_change_confidence"])
        self.assertFalse(dry_run["would_promote_label"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertTrue(confirmed_stage["stage_report_created"])
        self.assertFalse(confirmed_stage["real_write_enabled"])
        self.assertEqual(confirmed_stage["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "confirm_STAGE_CEX_CONFIDENCE_UPGRADE_required")
        self.assertFalse(blocked["stage_ready"])
        self.assertIn("target_confidence_high_required", blocked["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_backup_preview_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                ready = get_cex_label_confidence_upgrade_backup_preview(inserted["row_id"], "high", True)
                stage_blocked = get_cex_label_confidence_upgrade_backup_preview(inserted["row_id"], "medium", True)
                with patch(
                    "services.onchain_engine.get_cex_label_confidence_upgrade_stage",
                    return_value={
                        "ok": True,
                        "evidence_id": inserted["row_id"],
                        "candidate_id": 2,
                        "current_confidence": "low",
                        "target_confidence": "high",
                        "stage_ready": True,
                        "blockers": [],
                    },
                ):
                    drift = get_cex_label_confidence_upgrade_backup_preview(inserted["row_id"], "high", True)
                with patch(
                    "services.onchain_engine.get_cex_label_confidence_upgrade_stage",
                    return_value={
                        "ok": True,
                        "evidence_id": inserted["row_id"],
                        "candidate_id": 9999,
                        "current_confidence": "medium",
                        "target_confidence": "high",
                        "stage_ready": True,
                        "blockers": [],
                    },
                ):
                    missing = get_cex_label_confidence_upgrade_backup_preview(inserted["row_id"], "high", True)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertTrue(ready["backup_preview_available"])
        self.assertEqual(ready["existing_label_candidate_row"]["confidence"], "medium")
        self.assertTrue(ready["backup_required"])
        self.assertTrue(ready["rollback_required"])
        self.assertEqual(ready["update_preview"]["set"], {"confidence": "high"})
        self.assertEqual(ready["update_preview"]["only_fields"], ["confidence"])
        self.assertEqual(ready["rollback_preview"]["set"], {"confidence": "medium"})
        self.assertFalse(ready["real_write_enabled"])
        self.assertFalse(ready["would_write"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertFalse(stage_blocked["backup_preview_available"])
        self.assertIn("stage_not_ready", stage_blocked["blockers"])
        self.assertIn("confidence_changed_since_stage", drift["blockers"])
        self.assertIn("candidate_row_missing", missing["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_backup_artifact_is_confirmed_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                dry_run = get_cex_label_confidence_upgrade_backup(inserted["row_id"], "high", True)
                dry_files = list(backup_dir.glob("*.json")) if backup_dir.exists() else []
                blocked = get_cex_label_confidence_upgrade_backup(inserted["row_id"], "medium", True)
                refused = get_cex_label_confidence_upgrade_backup(inserted["row_id"], "high", False, None)
                created = get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                backup_files = list(backup_dir.glob("*.json"))
                payload = json.loads(Path(created["backup_path"]).read_text(encoding="utf-8"))
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertTrue(dry_run["would_create_backup"])
        self.assertFalse(dry_run["backup_created"])
        self.assertEqual(dry_run["writes_performed"], 0)
        self.assertEqual(dry_files, [])
        self.assertFalse(blocked["would_create_backup"])
        self.assertIn("stage_not_ready", blocked["blockers"])
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["error"], "confirm_CREATE_CEX_CONFIDENCE_BACKUP_required")
        self.assertTrue(created["backup_created"])
        self.assertEqual(created["writes_performed"], 0)
        self.assertEqual(len(backup_files), 1)
        self.assertEqual(payload["evidence_id"], inserted["row_id"])
        self.assertEqual(payload["candidate_id"], 2)
        self.assertEqual(payload["existing_label_candidate_row"]["confidence"], "medium")
        self.assertEqual(payload["update_preview"]["set"], {"confidence": "high"})
        self.assertEqual(payload["rollback_preview"]["set"], {"confidence": "medium"})
        serialized = json.dumps(payload).lower()
        self.assertNotIn("core_admin_token", serialized)
        self.assertNotIn(".env", serialized)
        self.assertNotIn("cookie", serialized)
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_backups_verify_artifacts_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            outside_dir = Path(tmpdir) / "outside"
            outside_dir.mkdir()
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                none = get_cex_label_confidence_upgrade_backups(inserted["row_id"], 2, 20)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                invalid_path = backup_dir / "cex_confidence_upgrade_evidence_999_candidate_2_invalid.json"
                backup_dir.mkdir(parents=True, exist_ok=True)
                invalid_path.write_text(json.dumps({"candidate_id": 2}), encoding="utf-8")
                outside_path = outside_dir / f"cex_confidence_upgrade_evidence_{inserted['row_id']}_candidate_2_outside.json"
                outside_path.write_text("{}", encoding="utf-8")
                valid = get_cex_label_confidence_upgrade_backups(inserted["row_id"], 2, 20)
                invalid = get_cex_label_confidence_upgrade_backups(999, 2, 20)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertFalse(none["valid_backup_available"])
        self.assertIn("valid_backup_artifact", none["missing_proofs"])
        self.assertTrue(valid["valid_backup_available"])
        self.assertTrue(valid["future_confidence_update_gate"]["backup_artifact_ready"])
        self.assertEqual(valid["backup_count"], 1)
        self.assertNotIn(str(outside_path), json.dumps(valid))
        self.assertFalse(invalid["valid_backup_available"])
        self.assertIn("rollback_preview", invalid["backups"][0]["missing_proofs"])
        self.assertIn("rollback_confidence_matches_existing", invalid["backups"][0]["missing_proofs"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_final_check_gates_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                no_backup = get_cex_label_confidence_upgrade_final_check(inserted["row_id"], "high")
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_final_check(inserted["row_id"], "high")
                bad_target = get_cex_label_confidence_upgrade_final_check(inserted["row_id"], "medium")
                with patch(
                    "services.onchain_engine.get_cex_label_confidence_upgrade_stage",
                    return_value={
                        "ok": True,
                        "evidence_id": inserted["row_id"],
                        "candidate_id": 2,
                        "current_confidence": "low",
                        "target_confidence": "high",
                        "stage_ready": True,
                        "would_update_label_candidates": True,
                        "blockers": [],
                    },
                ):
                    drift = get_cex_label_confidence_upgrade_final_check(inserted["row_id"], "high")
                invalid_path = next(backup_dir.glob("*.json"))
                payload = json.loads(invalid_path.read_text(encoding="utf-8"))
                payload.pop("rollback_preview")
                invalid_path.write_text(json.dumps(payload), encoding="utf-8")
                invalid_rollback = get_cex_label_confidence_upgrade_final_check(inserted["row_id"], "high")
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertFalse(no_backup["all_gates_ready"])
        self.assertFalse(no_backup["backup_artifact_ready"])
        self.assertIn("backup_artifact_missing_or_invalid", no_backup["blockers"])
        self.assertTrue(ready["all_gates_ready"])
        self.assertTrue(ready["preview_ready"])
        self.assertTrue(ready["stage_ready"])
        self.assertTrue(ready["backup_artifact_ready"])
        self.assertTrue(ready["rollback_plan_ready"])
        self.assertTrue(ready["confidence_drift_check"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertFalse(bad_target["all_gates_ready"])
        self.assertIn("target_confidence_high_required", bad_target["blockers"])
        self.assertFalse(drift["confidence_drift_check"])
        self.assertIn("confidence_drift_check_failed", drift["blockers"])
        self.assertFalse(invalid_rollback["rollback_plan_ready"])
        self.assertIn("rollback_plan_missing_or_invalid", invalid_rollback["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_execution_envelope_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                blocked = get_cex_label_confidence_upgrade_execution_envelope(inserted["row_id"], "high", True)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_execution_envelope(inserted["row_id"], "high", True)
                refused = get_cex_label_confidence_upgrade_execution_envelope(inserted["row_id"], "high", False)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertFalse(blocked["all_gates_ready"])
        self.assertFalse(blocked["would_update"])
        self.assertFalse(blocked["execution_allowed"])
        self.assertTrue(ready["all_gates_ready"])
        self.assertTrue(ready["would_update"])
        self.assertFalse(ready["execution_allowed"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["label_candidates_update"]["set"], {"confidence": "high"})
        self.assertEqual(ready["rollback_plan"]["set"], {"confidence": "medium"})
        self.assertTrue(ready["backup_artifact"])
        self.assertFalse(ready["would_change_confidence"])
        self.assertFalse(ready["would_promote_label"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertIn("dry_run_required", refused["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_simulation_report_is_readable_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                blocked = get_cex_label_confidence_upgrade_simulation_report(inserted["row_id"], "high", True)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_simulation_report(inserted["row_id"], "high", True)
                refused = get_cex_label_confidence_upgrade_simulation_report(inserted["row_id"], "high", False)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertEqual(blocked["status"], "blocked")
        self.assertFalse(blocked["would_update"])
        self.assertEqual(ready["status"], "ready_but_disabled")
        self.assertEqual(ready["current_confidence"], "medium")
        self.assertEqual(ready["target_confidence"], "high")
        self.assertTrue(ready["would_update"])
        self.assertTrue(ready["backup_summary"]["available"])
        self.assertTrue(ready["rollback_summary"]["available"])
        self.assertIn("medium -> high", ready["summary"]["would_change"])
        self.assertIn("real_write_disabled_by_policy", ready["blocking_reasons"])
        self.assertFalse(ready["execution_allowed"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertFalse(ready["would_change_confidence"])
        self.assertFalse(ready["would_promote_label"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertEqual(refused["status"], "blocked")
        self.assertIn("dry_run_required", refused["blocking_reasons"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_policy_gate_is_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                blocked = get_cex_label_confidence_upgrade_policy_gate(inserted["row_id"], "high", True)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_policy_gate(inserted["row_id"], "high", True)
                refused = get_cex_label_confidence_upgrade_policy_gate(inserted["row_id"], "high", False)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertEqual(blocked["policy_status"], "blocked")
        self.assertFalse(blocked["mutation_policy_allowed"])
        self.assertIsNone(blocked["required_future_confirm"])
        self.assertEqual(ready["policy_status"], "eligible_but_disabled")
        self.assertTrue(ready["all_gates_ready"])
        self.assertEqual(ready["simulation_status"], "ready_but_disabled")
        self.assertTrue(ready["backup_ready"])
        self.assertTrue(ready["rollback_ready"])
        self.assertTrue(ready["confidence_drift_ok"])
        self.assertFalse(ready["mutation_policy_allowed"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["required_future_confirm"], "APPLY_CEX_CONFIDENCE_UPGRADE")
        self.assertIn("real_write_disabled_by_policy", ready["blockers"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["policy_status"], "blocked")
        self.assertIn("dry_run_required", refused["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_apply_contract_is_dry_run_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                blocked = get_cex_label_confidence_upgrade_apply(inserted["row_id"], "high", True, None)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_apply(inserted["row_id"], "high", True, None)
                ready_confirmed = get_cex_label_confidence_upgrade_apply(
                    inserted["row_id"],
                    "high",
                    True,
                    "APPLY_CEX_CONFIDENCE_UPGRADE",
                )
                refused = get_cex_label_confidence_upgrade_apply(
                    inserted["row_id"],
                    "high",
                    False,
                    "APPLY_CEX_CONFIDENCE_UPGRADE",
                )
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertEqual(blocked["apply_status"], "blocked")
        self.assertFalse(blocked["would_update"])
        self.assertEqual(ready["apply_status"], "ready_for_future_confirm")
        self.assertEqual(ready["policy_status"], "eligible_but_disabled")
        self.assertTrue(ready["would_update"])
        self.assertEqual(ready["update_preview"]["set"], {"confidence": "high"})
        self.assertEqual(ready["required_confirm"], "APPLY_CEX_CONFIDENCE_UPGRADE")
        self.assertIsNone(ready["confirm_received"])
        self.assertEqual(ready_confirmed["apply_status"], "ready_for_future_confirm")
        self.assertEqual(ready_confirmed["confirm_received"], "APPLY_CEX_CONFIDENCE_UPGRADE")
        self.assertFalse(ready_confirmed["mutation_allowed_now"])
        self.assertFalse(ready_confirmed["real_write_enabled"])
        self.assertEqual(ready_confirmed["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["apply_status"], "blocked")
        self.assertIn("dry_run_required", refused["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_prewrite_audit_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                before_backup = get_cex_label_confidence_upgrade_prewrite_audit(inserted["row_id"], "high", True)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_prewrite_audit(inserted["row_id"], "high", True)
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        "UPDATE cex_independent_evidence_queue SET status = 'reviewed' WHERE id = ?",
                        (inserted["row_id"],),
                    )
                    conn.commit()
                    non_pending = get_cex_label_confidence_upgrade_prewrite_audit(inserted["row_id"], "high", True)
                    conn.execute(
                        "UPDATE cex_independent_evidence_queue SET status = 'pending_admin_review' WHERE id = ?",
                        (inserted["row_id"],),
                    )
                    conn.commit()
                finally:
                    conn.close()
                ledger = sqlite3.connect(ledger_path)
                try:
                    ledger.execute("UPDATE label_candidates SET confidence = 'low' WHERE id = 2")
                    ledger.commit()
                    drift = get_cex_label_confidence_upgrade_prewrite_audit(inserted["row_id"], "high", True)
                    ledger.execute("UPDATE label_candidates SET confidence = 'medium' WHERE id = 2")
                    ledger.commit()
                    ledger.execute("DELETE FROM label_candidates WHERE id = 2")
                    ledger.commit()
                    missing_candidate = get_cex_label_confidence_upgrade_prewrite_audit(inserted["row_id"], "high", True)
                finally:
                    ledger.close()
                refused = get_cex_label_confidence_upgrade_prewrite_audit(inserted["row_id"], "high", False)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()

        self.assertEqual(before_backup["audit_status"], "blocked")
        self.assertFalse(before_backup["prewrite_ready"])
        self.assertEqual(ready["audit_status"], "ready_but_disabled")
        self.assertTrue(ready["prewrite_ready"])
        self.assertEqual(ready["candidate_current_confidence"], "medium")
        self.assertEqual(ready["candidate_current_status"], "candidate")
        self.assertEqual(ready["evidence_status"], "pending_admin_review")
        self.assertEqual(ready["apply_status"], "ready_for_future_confirm")
        self.assertTrue(ready["all_gates_ready"])
        self.assertTrue(ready["backup_ready"])
        self.assertTrue(ready["rollback_ready"])
        self.assertTrue(ready["confidence_drift_ok"])
        self.assertTrue(ready["would_update"])
        self.assertEqual(ready["update_preview"]["set"], {"confidence": "high"})
        self.assertEqual(ready["rollback_preview"]["set"], {"confidence": "medium"})
        self.assertFalse(ready["mutation_allowed_now"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertEqual(non_pending["audit_status"], "blocked")
        self.assertIn("evidence_not_pending", non_pending["blockers"])
        self.assertEqual(drift["audit_status"], "blocked")
        self.assertIn("confidence_changed_since_backup", drift["blockers"])
        self.assertEqual(missing_candidate["audit_status"], "blocked")
        self.assertIn("candidate_row_missing", missing_candidate["blockers"])
        self.assertFalse(refused["ok"])
        self.assertIn("dry_run_required", refused["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)

    def test_cex_label_confidence_upgrade_controlled_write_review_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                blocked = get_cex_label_confidence_upgrade_controlled_write_review(
                    inserted["row_id"],
                    "high",
                    True,
                )
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_controlled_write_review(inserted["row_id"], "high", True)
                refused = get_cex_label_confidence_upgrade_controlled_write_review(inserted["row_id"], "high", False)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertEqual(blocked["review_status"], "blocked")
        self.assertFalse(blocked["prewrite_ready"])
        self.assertEqual(ready["review_status"], "ready_for_human_decision")
        self.assertTrue(ready["prewrite_ready"])
        self.assertTrue(ready["would_update"])
        self.assertEqual(ready["planned_update"]["set"], {"confidence": "high"})
        self.assertEqual(ready["rollback_plan"]["set"], {"confidence": "medium"})
        self.assertIn("APPLY_CEX_CONFIDENCE_UPGRADE", ready["required_confirmations"])
        self.assertIn("CONFIRM_LABEL_CANDIDATE_CONFIDENCE_WRITE", ready["required_confirmations"])
        self.assertIn("admin_token_valid", ready["required_preconditions"])
        self.assertIn("prewrite_audit_ready", ready["required_preconditions"])
        self.assertIn("candidate_confidence_unchanged", ready["required_preconditions"])
        self.assertIn("evidence_pending_admin_review", ready["required_preconditions"])
        self.assertIn("backup_artifact_valid", ready["required_preconditions"])
        self.assertIn("rollback_plan_valid", ready["required_preconditions"])
        self.assertIn("source_evidence_could_still_be_wrong", ready["remaining_risks"])
        self.assertIn("confidence_upgrade_is_not_label_promotion", ready["remaining_risks"])
        self.assertIn("alpha_lab_cex_confirmations_remain_separate", ready["remaining_risks"])
        self.assertIn("no_client_signal_generated", ready["remaining_risks"])
        self.assertTrue(ready["rollback_available"])
        self.assertFalse(ready["write_enabled_now"])
        self.assertFalse(ready["mutation_allowed_now"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertIn("dry_run_required", refused["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_sql_plan_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                blocked = get_cex_label_confidence_upgrade_sql_plan(inserted["row_id"], "high", True)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_sql_plan(inserted["row_id"], "high", True)
                refused = get_cex_label_confidence_upgrade_sql_plan(inserted["row_id"], "high", False)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertEqual(blocked["plan_status"], "blocked")
        self.assertEqual(blocked["transaction_steps"], [])
        self.assertEqual(ready["plan_status"], "ready_but_disabled")
        self.assertEqual(ready["target_table"], "label_candidates")
        self.assertIn("begin_transaction", ready["transaction_steps"])
        self.assertIn("verify_candidate_row_exists", ready["transaction_steps"])
        self.assertIn("verify_current_confidence_equals_rollback_confidence", ready["transaction_steps"])
        self.assertIn("verify_evidence_row_still_pending_admin_review", ready["transaction_steps"])
        self.assertIn("update_only_label_candidates_confidence", ready["transaction_steps"])
        self.assertIn("verify_exactly_one_row_affected", ready["transaction_steps"])
        self.assertIn("commit_transaction", ready["transaction_steps"])
        self.assertIn({"field": "id", "operator": "=", "value": 2}, ready["where_guards"])
        self.assertIn({"field": "confidence", "operator": "=", "value": "medium"}, ready["where_guards"])
        self.assertIn({"field": "status", "operator": "=", "value": "candidate"}, ready["where_guards"])
        self.assertIn("begin_transaction", ready["rollback_steps"])
        self.assertIn("update_only_label_candidates_confidence_back_to_rollback_value", ready["rollback_steps"])
        self.assertIn("verify_exactly_one_row_affected", ready["rollback_steps"])
        self.assertIn("commit_transaction", ready["rollback_steps"])
        self.assertEqual(ready["expected_rows_affected"], 1)
        self.assertEqual(ready["planned_confidence"], "high")
        self.assertEqual(ready["rollback_confidence"], "medium")
        self.assertFalse(ready["write_enabled_now"])
        self.assertFalse(ready["mutation_allowed_now"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertFalse(refused["ok"])
        self.assertIn("dry_run_required", refused["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")

    def test_cex_label_confidence_upgrade_rollback_smoke_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            ledger_path = Path(tmpdir) / "label_ledger.db"
            backup_dir = Path(tmpdir) / "confidence_backups"
            ledger = sqlite3.connect(ledger_path)
            try:
                ledger.execute(
                    """
                    CREATE TABLE label_candidates (
                        id INTEGER PRIMARY KEY,
                        chain TEXT,
                        address TEXT,
                        proposed_label TEXT,
                        proposed_entity TEXT,
                        proposed_wallet_type TEXT,
                        confidence TEXT,
                        status TEXT,
                        source TEXT,
                        source_url TEXT,
                        evidence_json TEXT,
                        seen_count INTEGER,
                        last_seen_at TEXT
                    )
                    """
                )
                ledger.execute(
                    (
                        "INSERT INTO label_candidates "
                        "(id, chain, address, proposed_label, proposed_entity, proposed_wallet_type, confidence, status, source, source_url, evidence_json, seen_count, last_seen_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        2,
                        "bsc",
                        "0x2222222222222222222222222222222222222222",
                        "MEXC: Hot Wallet",
                        "MEXC",
                        "cex",
                        "medium",
                        "candidate",
                        "scrapling_transfer_side",
                        "https://intel.arkm.com/explorer/entity/mexc",
                        '[{"file":"entity_mexc.json"}]',
                        42,
                        "2026-05-12T00:00:00Z",
                    ),
                )
                ledger.commit()
            finally:
                ledger.close()

            with (
                patch("services.onchain_engine.DB_PATH", db_path),
                patch("services.onchain_engine.LABEL_LEDGER_PATH", ledger_path),
                patch("services.onchain_engine.CEX_CONFIDENCE_UPGRADE_BACKUP_DIR", backup_dir),
            ):
                create_cex_independent_evidence_queue(
                    dry_run=False,
                    confirm="CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                )
                inserted = insert_cex_label_independent_evidence(
                    2,
                    "block_explorer_verified_label",
                    "https://bscscan.com/address/0x2222222222222222222222222222222222222222",
                    "Verified explorer label",
                    False,
                    "INSERT_CEX_INDEPENDENT_EVIDENCE",
                )
                blocked = get_cex_label_confidence_upgrade_rollback_smoke(inserted["row_id"], "high", True)
                get_cex_label_confidence_upgrade_backup(
                    inserted["row_id"],
                    "high",
                    False,
                    "CREATE_CEX_CONFIDENCE_BACKUP",
                )
                ready = get_cex_label_confidence_upgrade_rollback_smoke(inserted["row_id"], "high", True)
                ledger = sqlite3.connect(ledger_path)
                try:
                    ledger.execute("UPDATE label_candidates SET confidence = 'low' WHERE id = 2")
                    ledger.commit()
                    drift = get_cex_label_confidence_upgrade_rollback_smoke(inserted["row_id"], "high", True)
                    ledger.execute("UPDATE label_candidates SET confidence = 'medium' WHERE id = 2")
                    ledger.commit()
                finally:
                    ledger.close()
                refused = get_cex_label_confidence_upgrade_rollback_smoke(inserted["row_id"], "high", False)
                conn = sqlite3.connect(db_path)
                try:
                    evidence_rows = conn.execute("SELECT COUNT(*) FROM cex_independent_evidence_queue").fetchone()[0]
                    wallet_rows = conn.execute("SELECT COUNT(*) FROM wallet_chain_state").fetchone()[0]
                finally:
                    conn.close()
                after_conf = _fetchone_value(ledger_path, "SELECT confidence FROM label_candidates WHERE id = 2")

        self.assertEqual(blocked["rollback_status"], "blocked")
        self.assertFalse(blocked["rollback_available"])
        self.assertEqual(ready["rollback_status"], "ready_but_disabled")
        self.assertEqual(ready["current_confidence"], "medium")
        self.assertEqual(ready["planned_confidence"], "high")
        self.assertEqual(ready["rollback_confidence"], "medium")
        self.assertTrue(ready["rollback_available"])
        self.assertIn({"field": "id", "operator": "=", "value": 2}, ready["rollback_where_guards"])
        self.assertIn({"field": "confidence", "operator": "=", "value": "high"}, ready["rollback_where_guards"])
        self.assertIn({"field": "status", "operator": "=", "value": "candidate"}, ready["rollback_where_guards"])
        self.assertIn("begin_transaction", ready["rollback_steps"])
        self.assertIn("verify_candidate_row_exists", ready["rollback_steps"])
        self.assertIn("verify_current_confidence_equals_planned_confidence", ready["rollback_steps"])
        self.assertIn("update_only_label_candidates_confidence_back_to_rollback_value", ready["rollback_steps"])
        self.assertIn("verify_exactly_one_row_affected", ready["rollback_steps"])
        self.assertIn("commit_transaction", ready["rollback_steps"])
        self.assertEqual(ready["expected_rows_affected"], 1)
        self.assertFalse(ready["rollback_enabled_now"])
        self.assertFalse(ready["mutation_allowed_now"])
        self.assertFalse(ready["real_write_enabled"])
        self.assertEqual(ready["writes_performed"], 0)
        self.assertEqual(drift["rollback_status"], "blocked")
        self.assertIn("confidence_changed_since_backup", drift["blockers"])
        self.assertFalse(refused["ok"])
        self.assertIn("dry_run_required", refused["blockers"])
        self.assertEqual(evidence_rows, 1)
        self.assertEqual(wallet_rows, 0)
        self.assertEqual(after_conf, "medium")


if __name__ == "__main__":
    unittest.main()
