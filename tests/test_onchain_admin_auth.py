from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routers.onchain import router as onchain_router  # noqa: E402
from services.core_equity_guards import dry_run_raw_data_collection_payload  # noqa: E402


class OnchainAdminAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_token = os.environ.get("CORE_ADMIN_TOKEN")
        app = FastAPI()
        app.include_router(onchain_router, prefix="/api/onchain")
        self.client = TestClient(app)

    def tearDown(self) -> None:
        if self.original_token is None:
            os.environ.pop("CORE_ADMIN_TOKEN", None)
        else:
            os.environ["CORE_ADMIN_TOKEN"] = self.original_token

    def test_core_equity_raw_data_guard_keeps_runtime_surfaces_disabled(self) -> None:
        payload = dry_run_raw_data_collection_payload(
            status_key="ingest_status",
            status="ready_but_disabled",
            action_type="single_block",
            confirm_required="INGEST_ONCHAIN_SINGLE_BLOCK",
            params={"chain": "bsc", "block_number": 123},
            would_call_rpc=True,
            would_collect_raw_data=True,
            would_update_wallet_aggregates=True,
            source_policy="test",
        )

        self.assertFalse(payload["would_create_cex_label"])
        self.assertFalse(payload["would_create_dex_router_evidence"])
        self.assertFalse(payload["would_create_mapping"])
        self.assertFalse(payload["would_execute_trade"])
        self.assertFalse(payload["would_create_client_signal"])
        self.assertFalse(payload["would_create_client_opt_in"])
        self.assertFalse(payload["would_write"])
        self.assertEqual(payload["writes_performed"], 0)

    def test_onchain_mutation_routes_keep_data_admin_dependency(self) -> None:
        violations: list[str] = []

        for route in onchain_router.routes:
            methods = set(getattr(route, "methods", set()) or set())
            if not methods & {"POST", "PUT", "PATCH", "DELETE"}:
                continue
            dependant = getattr(route, "dependant", None)
            dependencies = getattr(dependant, "dependencies", []) if dependant else []
            dependency_names = {
                getattr(getattr(dependency, "call", None), "__name__", "")
                for dependency in dependencies
            }
            if "_require_data_admin" not in dependency_names:
                path = getattr(route, "path", "<unknown>")
                violations.append(f"{','.join(sorted(methods))} {path}")

        self.assertEqual(violations, [], "Every onchain mutation route must require Core Equity data admin.")

    def test_admin_endpoints_reject_when_token_not_configured(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/enrich-chain-gaps")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_behavioral_evidence_bridge_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-behavioral-evidence-bridge?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_behavioral_evidence_bridge_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "bridge_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_behavioral_evidence_bridge",
            return_value=expected,
        ) as bridge:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-behavioral-evidence-bridge"
                "?chain=bsc&token=0xtoken&limit=7&wallet_limit=5&dry_run=true"
                "&breakout_threshold_pct=500&baseline_swaps=12&confirmation_swaps=3"
                "&pre_event_swaps=20&fresh_wallet_hours=72&cluster_window_minutes=60",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        bridge.assert_called_once_with(
            "bsc",
            "0xtoken",
            7,
            5,
            True,
            500.0,
            12,
            3,
            20,
            72,
            60,
        )

    def test_top_expansion_behavioral_anomaly_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-anomaly-scoring-preview?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_top_expansion_behavioral_anomaly_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-anomaly-scoring-preview"
                "?chain=bsc&pool_address=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&limit=2&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            2,
            True,
        )

    def test_top_expansion_behavioral_shadow_outcome_backtest_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-shadow-outcome-backtest-plan"
                "?chain=bsc&pool_address=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&limit=2&dry_run=true"
                "&score_threshold=75&entry_slippage_bps=400&exit_slippage_bps=400&mev_penalty_bps=200",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(
            "bsc",
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            2,
            True,
            75,
            400,
            400,
            200,
        )

    def test_behavioral_score_pump_backtest_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_behavioral_score_pump_backtest_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-behavioral-score-pump-backtest-preview"
                "?chain=bsc&pool_address=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&limit=20&dry_run=true"
                "&min_swaps=10&min_behavioral_score=60&entry_score_threshold=70"
                "&entry_slippage_bps=400&exit_slippage_bps=400&mev_penalty_bps=200",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            20,
            True,
            10,
            60,
            70,
            400,
            400,
            200,
        )

    def test_honeypot_correlation_scan_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "correlation_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_honeypot_correlation_scan_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-honeypot-correlation-scan-preview"
                "?chain=bsc&limit=20&dry_run=true&min_behavioral_score=60&min_swaps=10"
                "&use_honeypot=true&use_goplus=false&timeout_seconds=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            20,
            True,
            60,
            10,
            True,
            False,
            5,
        )

    def test_top_expansion_behavioral_tradability_filter_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_top_expansion_behavioral_tradability_filter_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-tradability-filter-preview"
                "?chain=bsc&pool_address=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&limit=2&dry_run=true"
                "&score_threshold=75",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            2,
            True,
            75,
        )

    def test_top_expansion_behavioral_t0_shift_experiment_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_top_expansion_behavioral_t0_shift_experiment_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-t0-shift-experiment-preview"
                "?chain=bsc&pool_address=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&limit=2&dry_run=true"
                "&strong_score_threshold=75&thresholds=40,50,60,70,82"
                "&entry_slippage_bps=400&exit_slippage_bps=400&mev_penalty_bps=200",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            2,
            True,
            75,
            "40,50,60,70,82",
            400,
            400,
            200,
        )

    def test_top_expansion_directional_intent_classifier_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_top_expansion_directional_intent_classifier_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-top-expansion-directional-intent-classifier-preview"
                "?chain=bsc&pool_address=0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa&limit=2&dry_run=true"
                "&min_behavioral_score=50",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            2,
            True,
            50,
        )

    def test_stealth_accumulation_anomaly_scan_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "scan_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_stealth_accumulation_anomaly_scan_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-stealth-accumulation-anomaly-scan-preview"
                "?chain=bsc&limit=2&dry_run=true&max_pools=10&max_circularity_pct=30"
                "&min_hold_freeze_proxy_pct=70&min_buy_flows=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            2,
            True,
            10,
            30.0,
            70.0,
            3,
        )

    def test_stealth_funnel_diagnostic_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "diagnostic_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_stealth_funnel_diagnostic_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-stealth-funnel-diagnostic-preview"
                "?chain=bsc&limit=2&dry_run=true&max_pools=10&low_circularity_pct=30"
                "&high_hold_freeze_proxy_pct=50&min_buy_flows=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            2,
            True,
            10,
            30.0,
            50.0,
            3,
        )

    def test_quiet_pool_scanner_plan_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_quiet_pool_scanner_plan_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-quiet-pool-scanner-plan-preview"
                "?chain=bsc&limit=2&dry_run=true&max_pools=10&max_swap_rows=50"
                "&min_transfer_rows=1&min_pool_age_days=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            2,
            True,
            10,
            50,
            1,
            7,
        )

    def test_cex_listing_probability_bridge_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "bridge_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_cex_listing_probability_bridge_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-cex-listing-probability-bridge-preview"
                "?chain=bsc&limit=2&dry_run=true&min_behavioral_score=50&cex_deposit_limit=25",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            2,
            True,
            50,
            25,
            None,
        )

    def test_cex_listing_negative_cohort_discovery_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "discovery_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_cex_listing_negative_cohort_discovery_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-cex-listing-negative-cohort-discovery-preview"
                "?chain=bsc&limit=2&dry_run=true&min_behavioral_score=20&min_age_days=90",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            2,
            True,
            20,
            90,
        )

    def test_external_scam_negative_intake_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "intake_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }
        token = "0x" + "1" * 40

        with patch(
            "routers.onchain.get_manipulation_detection_external_scam_negative_intake_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-external-scam-negative-intake-preview"
                f"?chain=bsc&token_addresses={token}&limit=2&dry_run=true"
                "&use_honeypot=true&use_goplus=false&timeout_seconds=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            token,
            2,
            True,
            True,
            False,
            5,
        )

    def test_documented_scam_negative_scope_expansion_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "scope_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_documented_scam_negative_candidate_scope_expansion_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-documented-scam-negative-candidate-scope-expansion-preview"
                "?chain=bsc&limit=3&dry_run=true&max_scan_rows=100"
                "&use_honeypot=true&use_goplus=false&timeout_seconds=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            3,
            True,
            100,
            True,
            False,
            5,
        )

    def test_cex_listing_ground_truth_seed_coherence_checkpoint_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "coherence_status": "ready_for_seed_insert_dry_run",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_cex_listing_ground_truth_seed_coherence_checkpoint",
            return_value=expected,
        ) as checkpoint:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-cex-listing-ground-truth-seed-coherence-checkpoint"
                "?chain=bsc&dry_run=true&negative_limit=3&max_scan_rows=100"
                "&use_honeypot=true&use_goplus=false&timeout_seconds=5"
                "&allow_exploratory_majority_context=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        checkpoint.assert_called_once_with(
            "bsc",
            True,
            3,
            100,
            True,
            False,
            5,
            True,
        )

    def test_local_native_ground_truth_discovery_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "discovery_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_local_native_ground_truth_discovery_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-local-native-ground-truth-discovery-preview"
                "?chain=bsc&limit=10&dry_run=true&min_swaps=0&min_transfers=1",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            10,
            True,
            0,
            1,
        )

    def test_native_positive_candidate_replacement_discovery_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "discovery_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_native_positive_candidate_replacement_discovery_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-native-positive-candidate-replacement-discovery-preview"
                "?chain=bsc&limit=8&dry_run=true&min_swaps=0&min_transfers=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            8,
            True,
            0,
            3,
        )

    def test_cex_listing_exploratory_shadow_backtest_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "backtest_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_cex_listing_exploratory_shadow_backtest_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-cex-listing-exploratory-shadow-backtest-preview"
                "?chain=bsc&dry_run=true&score_threshold=50&negative_limit=3"
                "&max_scan_rows=100&use_honeypot=true&use_goplus=false&timeout_seconds=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            True,
            50,
            3,
            100,
            True,
            False,
            5,
        )

    def test_cex_listing_feature_wiring_diagnostic_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "diagnostic_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_cex_listing_feature_wiring_diagnostic_preview",
            return_value=expected,
        ) as diagnostic:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-cex-listing-feature-wiring-diagnostic-preview"
                "?chain=bsc&dry_run=true&cex_deposit_limit=25",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        diagnostic.assert_called_once_with(
            "bsc",
            True,
            25,
        )

    def test_feature_backfill_orchestrator_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "orchestrator_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_feature_backfill_orchestrator_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-feature-backfill-orchestrator-preview"
                "?chain=bsc&token_addresses=0x1111111111111111111111111111111111111111"
                "&dry_run=true&run_existing_previews=false&cex_deposit_limit=25"
                "&min_raw_swaps_for_feature_backfill=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0x1111111111111111111111111111111111111111",
            True,
            False,
            25,
            5,
        )

    def test_b_feature_backfill_replay_diagnostic_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "diagnostic_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_b_feature_backfill_replay_diagnostic_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-b-feature-backfill-replay-diagnostic-preview"
                "?chain=bsc&dry_run=true&sample_limit=10",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
            "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
            True,
            10,
        )

    def test_b_cex_destination_wallet_reference_repair_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_b_cex_destination_wallet_reference_repair_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-b-cex-destination-wallet-reference-repair-preview"
                "?chain=bsc&dry_run=true&limit=10",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
            True,
            10,
        )

    def test_b_destination_holder_distribution_flow_check_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "flow_check_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_b_destination_holder_distribution_flow_check_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-b-destination-holder-distribution-flow-check-preview"
                "?chain=bsc&dry_run=true&limit=10",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
            "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
            True,
            10,
        )

    def test_lab_b_targeted_raw_context_backfill_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_lab_b_targeted_raw_context_backfill_plan",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-lab-b-targeted-raw-context-backfill-plan"
                "?chain=bsc&token_addresses=0x1111111111111111111111111111111111111111"
                "&dry_run=true&block_padding=25000&max_window_blocks=100000",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0x1111111111111111111111111111111111111111",
            True,
            25000,
            100000,
        )

    def test_b_seed_bounded_raw_context_lookup_dry_run_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "lookup_status": "ready_but_external_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_b_seed_bounded_raw_context_lookup_dry_run",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-b-seed-bounded-raw-context-lookup-dry-run"
                "?chain=bsc&dry_run=true&allow_external=false&max_sqd_calls=3&max_sqd_block_span=1000"
                "&max_logs_total=25&max_logs_per_filter=10&timeout=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
            "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
            True,
            False,
            None,
            50000,
            250000,
            3,
            1000,
            25,
            10,
            5,
        )

    def test_b_seed_raw_context_evidence_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "ready_for_insert",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.insert_manipulation_detection_b_seed_raw_context_evidence",
            return_value=expected,
        ) as insert:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-b-seed-raw-context-evidence/insert"
                "?chain=bsc&dry_run=true&allow_external=true"
                "&confirm=PREVIEW_B_SEED_RAW_CONTEXT_EVIDENCE_INSERT&max_sqd_calls=3"
                "&max_sqd_block_span=1000&max_logs_total=25&max_logs_per_filter=10&timeout=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "bsc",
            "0x6bdcce4a559076e37755a78ce0c06214e59e4444",
            "0x203d66ecb7263efe424fcba0898761fc9fc9a8c0",
            True,
            True,
            "PREVIEW_B_SEED_RAW_CONTEXT_EVIDENCE_INSERT",
            None,
            50000,
            250000,
            3,
            1000,
            25,
            10,
            5,
        )

    def test_local_native_ground_truth_labeling_lookup_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "lookup_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_local_native_ground_truth_labeling_lookup_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-local-native-ground-truth-labeling-lookup-preview"
                "?chain=bsc&limit=10&dry_run=true&min_swaps=0&min_transfers=1"
                "&use_coingecko=true&use_honeypot=true&use_goplus=true&timeout_seconds=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            10,
            True,
            0,
            1,
            True,
            True,
            True,
            5,
        )

    def test_cex_listing_ground_truth_dataset_plan_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_cex_listing_ground_truth_dataset_plan_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-cex-listing-ground-truth-dataset-plan-preview"
                "?chain=bsc&limit=2&dry_run=true&lookback_days=365",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "bsc",
            2,
            True,
            365,
        )

    def test_cex_listing_ground_truth_dataset_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "row_count": 0,
            "would_write": False,
        }

        with patch(
            "routers.onchain.create_manipulation_detection_cex_listing_ground_truth_dataset",
            return_value=expected,
        ) as create:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-cex-listing-ground-truth-dataset/create"
                "?chain=bsc&dry_run=false&confirm=CREATE_CEX_LISTING_GROUND_TRUTH_DATASET",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(
            "bsc",
            False,
            "CREATE_CEX_LISTING_GROUND_TRUTH_DATASET",
        )

    def test_cex_listing_ground_truth_dataset_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }
        payload = {
            "rows": [
                {
                    "chain": "bsc",
                    "token_address": "0x" + "1" * 40,
                    "token_symbol": "TEST",
                    "cex_name": "Gate",
                    "market_pair": "TEST/USDT",
                    "announcement_url": "https://example.com/listing",
                    "announcement_at": "2026-01-01T00:00:00Z",
                    "listing_tier": "tier_2_listing",
                    "source_tier": "tier_2",
                    "source_digest": "a" * 64,
                }
            ],
            "expected_dedupe_keys": [],
        }

        with patch(
            "routers.onchain.insert_manipulation_detection_cex_listing_ground_truth_rows",
            return_value=expected,
        ) as insert:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-cex-listing-ground-truth-dataset/insert"
                "?chain=bsc&dry_run=true",
                json=payload,
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            payload["rows"],
            "bsc",
            True,
            None,
            [],
        )

    def test_admin_endpoints_reject_wrong_token(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/enrich-chain-gaps",
            headers={"x-core-admin-token": "wrong-token"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Core Equity admin token required")

    def test_read_only_gap_report_does_not_require_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/entity-chain-gaps?limit=1")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_read_only_token_transfer_coverage_does_not_require_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        with patch("routers.onchain.get_token_transfer_coverage") as mocked:
            mocked.return_value = {
                "ok": True,
                "chain": "eth",
                "summary": {"token_transfer_rows": 0},
                "source_policy": "read-only token transfer coverage",
            }
            response = self.client.get("/api/onchain/rpc/token-transfer-coverage?chain=eth")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["chain"], "eth")
        self.assertIn("read-only", response.json()["source_policy"])
        mocked.assert_called_once_with("eth")

    def test_read_only_token_transfer_cex_deposits_does_not_require_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        with patch("routers.onchain.get_token_transfer_cex_deposit_scan") as mocked:
            mocked.return_value = {
                "ok": True,
                "chain": "bsc",
                "summary": {"deposits": 0},
                "source_policy": "read-only CEX token deposit scan",
            }
            response = self.client.get("/api/onchain/rpc/token-transfer-cex-deposits?chain=bsc&limit=3")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["chain"], "bsc")
        self.assertIn("read-only", response.json()["source_policy"])
        mocked.assert_called_once_with("bsc", 3)

    def test_cex_deposit_holder_snapshot_queue_does_not_require_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        with patch("routers.onchain.get_cex_deposit_holder_snapshot_refresh_queue") as mocked:
            mocked.return_value = {
                "ok": True,
                "chain": "bsc",
                "summary": {"queued_tokens": 1},
                "queue": [{"chain": "bsc", "token": "0xabc"}],
                "source_policy": "read-only refresh queue",
            }
            response = self.client.get("/api/onchain/rpc/cex-deposit-holder-snapshot-refresh-queue?chain=bsc&limit=2")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertIn("read-only", response.json()["source_policy"])
        mocked.assert_called_once_with("bsc", 2)

    def test_cex_deposit_holder_snapshot_refresh_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-deposit-holder-snapshots/refresh?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_deposit_holder_snapshot_refresh_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-deposit-holder-snapshots/refresh?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_REFRESH_CEX_DEPOSIT_HOLDER_SNAPSHOTS_required")

    def test_cex_deposit_holder_snapshot_refresh_passes_dry_run_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "summary": {"queued_tokens": 1, "would_refresh_tokens": 1},
            "execution_envelope": {
                "client_execution_enabled": False,
                "copy_trade_enabled": False,
                "writes": "none_dry_run",
            },
        }

        with patch("routers.onchain.refresh_cex_deposit_holder_snapshots", return_value=expected) as refresh:
            response = self.client.post(
                "/api/onchain/rpc/cex-deposit-holder-snapshots/refresh?chain=bsc&limit=2&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        self.assertFalse(response.json()["execution_envelope"]["client_execution_enabled"])
        refresh.assert_called_once_with("bsc", 2, True)

    def test_cex_deposit_holder_snapshot_refresh_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-deposit-holder-snapshots/refresh?limit=11&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_10")

    def test_dex_router_source_map_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/dex-router-source-map?limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_source_map_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"unknown_routers": 1},
            "rows": [],
            "source_policy": "read-only",
        }

        with patch("routers.onchain.get_dex_router_source_map", return_value=expected) as source_map:
            response = self.client.get(
                "/api/onchain/rpc/dex-router-source-map?chain=eth&limit=5&include_public_evidence=false",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        source_map.assert_called_once_with("eth", 5, False)

    def test_dex_router_source_map_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/dex-router-source-map?limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_source_backed_shadow_backtest_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-plan?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_shadow_backtest_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "summary": {"shadow_backtest_executable_now": False},
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_shadow_backtest_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True)

    def test_source_backed_shadow_backtest_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-preview?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_shadow_backtest_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "summary": {"shadow_backtest_preview_ready": True},
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_shadow_backtest_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-preview"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True)

    def test_source_backed_shadow_replay_controls_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-shadow-replay-controls-preview?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_shadow_replay_controls_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "summary": {"local_control_candidates": 3},
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_shadow_replay_controls_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-shadow-replay-controls-preview"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&min_swaps=4",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4)

    def test_source_backed_control_outcome_collection_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-collection-plan?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_control_outcome_collection_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "planned_control_count": 3,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_control_outcome_collection_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-collection-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&min_swaps=4&max_controls=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4, 3)

    def test_source_backed_control_outcome_lookup_dry_run_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-lookup-dry-run?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_control_outcome_lookup_dry_run_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "lookup_status": "ready_but_disabled",
            "summary": {"ready_control_windows": 3},
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.run_manipulation_detection_source_backed_control_outcome_lookup_dry_run",
            return_value=expected,
        ) as lookup:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-lookup-dry-run"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&min_swaps=4&max_controls=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        lookup.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4, 3)

    def test_source_backed_control_outcome_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-schema-plan?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_control_outcome_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "manipulation_control_outcome_windows",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_control_outcome_schema_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-schema-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&min_swaps=4&max_controls=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4, 3)

    def test_source_backed_control_outcome_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/create?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_control_outcome_create_requires_confirm_for_real_mode(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/create"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_MANIPULATION_CONTROL_OUTCOME_WINDOWS_required")

    def test_source_backed_control_outcome_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "manipulation_control_outcome_windows",
            "rows_inserted": 0,
            "would_write": False,
            "writes_performed": 6,
        }

        with patch(
            "routers.onchain.create_manipulation_detection_source_backed_control_outcome_table",
            return_value=expected,
        ) as create:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/create"
                "?chain=bsc&dry_run=false&confirm=CREATE_MANIPULATION_CONTROL_OUTCOME_WINDOWS",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with("bsc", False, "CREATE_MANIPULATION_CONTROL_OUTCOME_WINDOWS")

    def test_source_backed_control_outcome_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/insert?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_control_outcome_insert_requires_confirm_for_real_mode(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/insert"
            "?dry_run=false&expected_control_outcome_lookup_digest=digest",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS_required")

    def test_source_backed_control_outcome_insert_requires_expected_digest_for_real_mode(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/insert"
            "?dry_run=false&confirm=INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "expected_control_outcome_lookup_digest_required")

    def test_source_backed_control_outcome_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "ready_for_insert",
            "would_insert_control_outcome_rows": 6,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.insert_manipulation_detection_source_backed_control_outcome_windows",
            return_value=expected,
        ) as insert:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/insert"
                "?chain=bsc&limit=7&dry_run=true&confirm=INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS"
                "&expected_control_outcome_lookup_digest=digest&min_swaps=4&max_controls=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "bsc",
            7,
            True,
            "INSERT_MANIPULATION_CONTROL_OUTCOME_WINDOWS",
            "digest",
            4,
            3,
        )

    def test_source_backed_control_outcome_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/review?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_control_outcome_review_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/review?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_source_backed_control_outcome_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready_but_disabled",
            "review_readiness": "ready_for_multi_candidate_replay_preview",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_control_outcome_review_queue",
            return_value=expected,
        ) as review:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-control-outcome-windows/review"
                "?chain=bsc&status=pending_control_outcome_review&limit=7&dry_run=true&min_swaps=4&max_controls=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("bsc", "pending_control_outcome_review", 7, True, 4, 3)

    def test_source_backed_multi_candidate_shadow_replay_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_multi_candidate_shadow_replay_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_source_backed_multi_candidate_shadow_replay_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "replay_status": "ready_but_disabled",
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_multi_candidate_shadow_replay_preview",
            return_value=expected,
        ) as replay:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-multi-candidate-shadow-replay-preview"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&min_swaps=4&max_controls=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        replay.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4, 3)

    def test_source_backed_replay_policy_thresholds_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-replay-policy-thresholds"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_replay_policy_thresholds_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-replay-policy-thresholds"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_source_backed_replay_policy_thresholds_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "policy_status": "ready_but_disabled",
            "machine_policy_decision": {"next_decision": "reject_research_signal_candidate"},
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_replay_policy_thresholds",
            return_value=expected,
        ) as policy:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-replay-policy-thresholds"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&min_swaps=4&max_controls=3&min_control_cases=3"
                "&min_source_favorable_move_pct=15&min_source_net_move_pct=5&max_source_adverse_move_pct=-20",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        policy.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4, 3, 3, 15.0, 5.0, -20.0)

    def test_source_backed_case_control_expansion_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-case-control-expansion-plan"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_case_control_expansion_plan_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-case-control-expansion-plan"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_source_backed_case_control_expansion_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "summary": {"expansion_candidates": 2},
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_case_control_expansion_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-case-control-expansion-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&min_swaps=4&max_candidates=8",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4, 8)

    def test_source_backed_top_expansion_raw_context_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_top_expansion_raw_context_plan_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_source_backed_top_expansion_raw_context_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "summary": {"candidate_plans": 3},
            "would_call_provider": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_top_expansion_raw_context_collection_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-collection-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&min_swaps=4&max_candidates=3&max_window_blocks=5000",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 4, 3, 5000)

    def test_source_backed_top_expansion_raw_context_lookup_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_top_expansion_raw_context_lookup_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_source_backed_top_expansion_raw_context_lookup_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "lookup_status": "ready_but_external_disabled",
            "would_call_external": True,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.run_manipulation_detection_source_backed_top_expansion_raw_context_lookup_dry_run",
            return_value=expected,
        ) as lookup:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-lookup-dry-run"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&allow_external=false&min_swaps=4&max_candidates=3&max_window_blocks=5000"
                "&max_sqd_calls=48&max_logs_total=2000&max_logs_per_filter=50"
                "&max_sqd_block_span=1000&timeout=8",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        lookup.assert_called_once_with(
            "bsc",
            "0xpool",
            "0xtoken",
            7,
            True,
            False,
            None,
            4,
            3,
            5000,
            48,
            2000,
            50,
            1000,
            8,
        )

    def test_source_backed_top_expansion_raw_context_evidence_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence-schema-plan"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_top_expansion_raw_context_evidence_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "target_tables": ["dex_raw_swap_events", "dex_raw_sync_events", "erc20_transfer_events"],
            "would_create_table": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_top_expansion_raw_context_evidence_schema_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence-schema-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&min_swaps=4&max_candidates=3&max_window_blocks=5000&max_sqd_calls=9"
                "&max_logs_total=450&max_logs_per_filter=50&max_sqd_block_span=1000",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(
            "bsc",
            "0xpool",
            "0xtoken",
            7,
            True,
            4,
            3,
            5000,
            9,
            450,
            50,
            1000,
        )

    def test_source_backed_top_expansion_raw_context_evidence_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence/insert"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_top_expansion_raw_context_evidence_insert_requires_confirm_for_real(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence/insert"
            "?dry_run=false&allow_external=true&expected_raw_context_lookup_digest=digest",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_required")

    def test_source_backed_top_expansion_raw_context_evidence_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "ready_for_insert",
            "would_insert_raw_context": True,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.insert_manipulation_detection_source_backed_top_expansion_raw_context_evidence",
            return_value=expected,
        ) as insert:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-source-backed-top-expansion-raw-context-evidence/insert"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&allow_external=true&confirm=PREVIEW_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_INSERT"
                "&expected_raw_context_lookup_digest=digest&min_swaps=4&max_candidates=3"
                "&max_window_blocks=5000&max_sqd_calls=9&max_logs_total=450"
                "&max_logs_per_filter=50&max_sqd_block_span=1000&timeout=8",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "bsc",
            "0xpool",
            "0xtoken",
            7,
            True,
            True,
            "PREVIEW_TOP_EXPANSION_RAW_CONTEXT_EVIDENCE_INSERT",
            "digest",
            4,
            3,
            5000,
            9,
            450,
            50,
            1000,
            8,
        )

    def test_source_backed_shadow_backtest_outcome_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-outcome-dataset-schema-plan"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_shadow_backtest_outcome_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "manipulation_shadow_backtest_outcome_windows",
            "would_create_table": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_shadow_backtest_outcome_dataset_schema_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-shadow-backtest-outcome-dataset-schema-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True)

    def test_source_backed_outcome_window_collection_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-window-data-collection"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_outcome_window_collection_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "collection_status": "partial_with_local_outcomes",
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_outcome_window_data_collection_dry_run",
            return_value=expected,
        ) as collect:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-window-data-collection"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&allow_external=false",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        collect.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, False, None)

    def test_outcome_quality_repair_sync_liquidity_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-quality-repair-sync-liquidity-context"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_outcome_quality_repair_sync_liquidity_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "repair_status": "needs_sync_liquidity_collection",
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_outcome_quality_repair_sync_liquidity_context_dry_run",
            return_value=expected,
        ) as repair:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-quality-repair-sync-liquidity-context"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&allow_rpc=false",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        repair.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, False, None)

    def test_outcome_sync_liquidity_collection_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-collection-plan"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_outcome_sync_liquidity_collection_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "planned_filter_count": 9,
            "would_call_rpc": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_outcome_sync_liquidity_collection_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-collection-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&max_window_blocks=500",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 500)

    def test_sync_mint_burn_topic_binding_checkpoint_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-mint-burn-topic-binding-checkpoint"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_sync_mint_burn_topic_binding_checkpoint_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "checkpoint_status": "ready",
            "would_call_rpc": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_outcome_sync_mint_burn_topic_binding_checkpoint",
            return_value=expected,
        ) as checkpoint:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-mint-burn-topic-binding-checkpoint"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        checkpoint.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True)

    def test_outcome_sync_liquidity_lookup_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_outcome_sync_liquidity_lookup_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "lookup_status": "ready_but_external_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.run_manipulation_detection_source_backed_outcome_sync_liquidity_lookup_dry_run",
            return_value=expected,
        ) as lookup:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-lookup-dry-run"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&allow_external=true&confirm=RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP"
                "&max_sqd_calls=3&max_logs_total=99&timeout=6&max_window_blocks=500",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        lookup.assert_called_once_with(
            "bsc",
            "0xpool",
            "0xtoken",
            7,
            True,
            True,
            "RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP",
            3,
            99,
            6,
            500,
        )

    def test_outcome_sync_liquidity_evidence_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence-schema-plan"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_outcome_sync_liquidity_evidence_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "target_tables": ["dex_raw_sync_events", "dex_raw_liquidity_events"],
            "would_create_table": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_schema_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence-schema-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true&max_window_blocks=500",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True, 500)

    def test_outcome_sync_liquidity_evidence_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/insert"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_outcome_sync_liquidity_evidence_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "ready_for_insert",
            "would_insert_sync_events": 1,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.insert_manipulation_detection_source_backed_outcome_sync_liquidity_evidence",
            return_value=expected,
        ) as insert:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/insert"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&allow_external=true&lookup_confirm=RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP"
                "&confirm=INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE&expected_lookup_digest=digest"
                "&max_sqd_calls=3&max_logs_total=99&timeout=6&max_window_blocks=500",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "bsc",
            "0xpool",
            "0xtoken",
            7,
            True,
            True,
            "RUN_UFLOKI_OUTCOME_SYNC_LIQUIDITY_LOOKUP",
            "INSERT_UFLOKI_SYNC_LIQUIDITY_EVIDENCE",
            "digest",
            3,
            99,
            6,
            500,
        )

    def test_outcome_sync_liquidity_evidence_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/review"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_outcome_sync_liquidity_evidence_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready_but_disabled",
            "review_readiness": "ready_for_outcome_quality_repair_preview",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_outcome_sync_liquidity_evidence_review_queue",
            return_value=expected,
        ) as review:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-sync-liquidity-evidence/review"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&status=raw_observed&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("bsc", "0xpool", "0xtoken", "raw_observed", 7, True)

    def test_outcome_quality_repair_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-outcome-quality-repair-preview"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_outcome_quality_repair_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "repair_preview_status": "ready_but_disabled",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_outcome_quality_repair_preview",
            return_value=expected,
        ) as preview:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-outcome-quality-repair-preview"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True)

    def test_repaired_outcome_dataset_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset-schema-plan"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_repaired_outcome_dataset_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "manipulation_repaired_outcome_windows",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_repaired_outcome_dataset_schema_plan",
            return_value=expected,
        ) as plan:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset-schema-plan"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("bsc", "0xpool", "0xtoken", 7, True)

    def test_repaired_outcome_dataset_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/create"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_repaired_outcome_dataset_create_requires_confirm_for_real_mode(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/create"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS_required")

    def test_repaired_outcome_dataset_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "manipulation_repaired_outcome_windows",
            "rows_inserted": 0,
            "would_write": False,
            "writes_performed": 7,
        }

        with patch(
            "routers.onchain.create_manipulation_detection_source_backed_repaired_outcome_dataset_table",
            return_value=expected,
        ) as create:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/create"
                "?chain=bsc&dry_run=false&confirm=CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with("bsc", False, "CREATE_MANIPULATION_REPAIRED_OUTCOME_WINDOWS")

    def test_repaired_outcome_dataset_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/insert"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_repaired_outcome_dataset_insert_requires_confirm_for_real_mode(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/insert"
            "?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_MANIPULATION_REPAIRED_OUTCOME_WINDOWS_required")

    def test_repaired_outcome_dataset_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "ready_for_insert",
            "would_insert_repaired_outcome_rows": 4,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.insert_manipulation_detection_source_backed_repaired_outcome_dataset",
            return_value=expected,
        ) as insert:
            response = self.client.post(
                "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/insert"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&limit=7&dry_run=true"
                "&confirm=INSERT_MANIPULATION_REPAIRED_OUTCOME_WINDOWS&expected_repair_preview_digest=digest",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "bsc",
            "0xpool",
            "0xtoken",
            7,
            True,
            "INSERT_MANIPULATION_REPAIRED_OUTCOME_WINDOWS",
            "digest",
        )

    def test_repaired_outcome_dataset_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/review"
            "?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_repaired_outcome_dataset_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready_but_disabled",
            "review_readiness": "ready_for_shadow_backtest_preview",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_manipulation_detection_source_backed_repaired_outcome_dataset_review_queue",
            return_value=expected,
        ) as review:
            response = self.client.get(
                "/api/onchain/rpc/manipulation-detection-source-backed-repaired-outcome-dataset/review"
                "?chain=bsc&pool_address=0xpool&token_address=0xtoken&status=pending_shadow_backtest_review&limit=7&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("bsc", "0xpool", "0xtoken", "pending_shadow_backtest_review", 7, True)

    def test_legacy_ingest_single_block_is_dry_run_first(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        with patch("routers.onchain.ingest_block") as ingest:
            response = self.client.post(
                "/api/onchain/ingest/bsc/123?dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ingest_status"], "ready_but_disabled")
        self.assertFalse(response.json()["would_write"])
        self.assertEqual(response.json()["writes_performed"], 0)
        ingest.assert_not_called()

        with patch("routers.onchain.ingest_block") as ingest:
            response = self.client.post(
                "/api/onchain/ingest/bsc/123?dry_run=false",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INGEST_ONCHAIN_SINGLE_BLOCK_required")
        ingest.assert_not_called()

    def test_legacy_ingest_single_block_confirm_calls_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {"ok": True, "tx_count": 0, "swaps_found": 0}

        with patch("routers.onchain.ingest_block", return_value=expected) as ingest:
            response = self.client.post(
                "/api/onchain/ingest/bsc/123?dry_run=false&confirm=INGEST_ONCHAIN_SINGLE_BLOCK",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        ingest.assert_called_once_with("bsc", 123)

    def test_legacy_ingest_batch_routes_are_dry_run_first(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        cases = [
            ("/api/onchain/ingest/recent/bsc?count=1&dry_run=true", "routers.onchain.ingest_recent_blocks"),
            (
                "/api/onchain/ingest/exact-swap-window/bsc?count=1&dry_run=true",
                "routers.onchain.ingest_exact_swap_window_job",
            ),
            (
                "/api/onchain/ingest/exact-swap-progressive?max_chains=1&count_per_chain=1&dry_run=true",
                "routers.onchain.run_exact_swap_ingestion_plan_once",
            ),
        ]

        for url, target in cases:
            with self.subTest(url=url), patch(target) as service:
                response = self.client.post(url, headers={"x-core-admin-token": "correct-token"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["ingest_status"], "ready_but_disabled")
            self.assertFalse(response.json()["would_write"])
            service.assert_not_called()

    def test_dex_router_official_source_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/dex-router-official-source-queue?limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_official_source_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"queue_rows": 1, "automation_allowed": False},
            "rows": [],
            "source_policy": "read-only",
        }

        with patch("routers.onchain.get_dex_router_official_source_queue", return_value=expected) as queue:
            response = self.client.get(
                "/api/onchain/rpc/dex-router-official-source-queue?chain=eth&limit=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        queue.assert_called_once_with("eth", 5)

    def test_dex_router_official_source_queue_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/dex-router-official-source-queue?limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_dex_router_official_evidence_dry_run_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-official-evidence-dry-run"
            "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
            "&evidence_type=official_protocol_docs&source_url=https://docs.example.org&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_official_evidence_dry_run_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-official-evidence-dry-run"
            "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
            "&evidence_type=official_protocol_docs&source_url=https://docs.example.org&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_official_evidence_dry_run_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "evidence_accepted": True,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_official_evidence_dry_run", return_value=expected) as dry_run:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-official-evidence-dry-run"
                "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
                "&evidence_type=official_protocol_docs&source_url=https://docs.example.org"
                "&notes=checked&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        dry_run.assert_called_once_with(
            "eth",
            "0x1111111111111111111111111111111111111111",
            "official_protocol_docs",
            "https://docs.example.org",
            "checked",
            True,
        )

    def test_dex_router_official_evidence_persist_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-official-evidence-persist-preview"
            "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
            "&evidence_type=official_protocol_docs&source_url=https://docs.example.org&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_official_evidence_persist_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-official-evidence-persist-preview"
            "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
            "&evidence_type=official_protocol_docs&source_url=https://docs.example.org&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_official_evidence_persist_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "would_persist": True,
            "target_table": "dex_router_official_evidence_queue",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_official_evidence_persist_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-official-evidence-persist-preview"
                "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
                "&evidence_type=official_protocol_docs&source_url=https://docs.example.org"
                "&notes=checked&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(
            "eth",
            "0x1111111111111111111111111111111111111111",
            "official_protocol_docs",
            "https://docs.example.org",
            "checked",
            True,
        )

    def test_dex_router_official_evidence_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/dex-router-official-evidence-queue-schema-plan?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_official_evidence_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/dex-router-official-evidence-queue-schema-plan?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_official_evidence_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "target_table": "dex_router_official_evidence_queue",
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_official_evidence_queue_schema_plan", return_value=expected) as plan:
            response = self.client.get(
                "/api/onchain/rpc/dex-router-official-evidence-queue-schema-plan?dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(True)

    def test_create_dex_router_official_evidence_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/dex-router-official-evidence-queue/create?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_create_dex_router_official_evidence_queue_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-official-evidence-queue/create?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_DEX_ROUTER_OFFICIAL_EVIDENCE_QUEUE_required")

    def test_create_dex_router_official_evidence_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "would_create_table": True,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.create_dex_router_official_evidence_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-official-evidence-queue/create?dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(True, None)

    def test_insert_dex_router_official_evidence_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-official-evidence/insert"
            "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
            "&evidence_type=official_protocol_docs&source_url=https://docs.example.org&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_insert_dex_router_official_evidence_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-official-evidence/insert"
            "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
            "&evidence_type=official_protocol_docs&source_url=https://docs.example.org&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_DEX_ROUTER_OFFICIAL_EVIDENCE_required")

    def test_insert_dex_router_official_evidence_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "inserted": False,
            "would_insert": True,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.insert_dex_router_official_evidence", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-official-evidence/insert"
                "?chain=eth&router_address=0x1111111111111111111111111111111111111111"
                "&evidence_type=official_protocol_docs&source_url=https://docs.example.org"
                "&notes=checked&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "eth",
            "0x1111111111111111111111111111111111111111",
            "official_protocol_docs",
            "https://docs.example.org",
            "checked",
            True,
            None,
        )

    def test_dex_router_official_evidence_review_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/dex-router-official-evidence-review-queue")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_official_evidence_review_queue_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/dex-router-official-evidence-review-queue?limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_dex_router_official_evidence_review_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"rows": 1},
            "rows": [],
            "source_policy": "read-only",
        }

        with patch("routers.onchain.get_dex_router_official_evidence_review_queue", return_value=expected) as review:
            response = self.client.get(
                "/api/onchain/rpc/dex-router-official-evidence-review-queue?status=pending_admin_review&limit=5",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", 5)

    def test_dex_router_venue_mapping_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-preview?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-preview?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_available": True,
            "would_create_venue_mapping": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-preview?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_final_check_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-final-check?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_final_check_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-final-check?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_final_check_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "all_gates_ready": True,
            "would_create_venue_mapping": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_final_check", return_value=expected) as final_check:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-final-check?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        final_check.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_execution_envelope_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-execution-envelope?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_execution_envelope_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-execution-envelope?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_execution_envelope_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "all_gates_ready": True,
            "would_write": True,
            "execution_allowed": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_execution_envelope", return_value=expected) as envelope:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-execution-envelope?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        envelope.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_simulation_report_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-simulation-report?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_simulation_report_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-simulation-report?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_simulation_report_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "status": "ready_but_disabled",
            "execution_allowed": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_simulation_report", return_value=expected) as report:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-simulation-report?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        report.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_policy_gate_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-policy-gate?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_policy_gate_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-policy-gate?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_policy_gate_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "policy_status": "eligible_but_disabled",
            "mapping_policy_allowed": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_policy_gate", return_value=expected) as gate:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-policy-gate?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        gate.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-apply?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_apply_rejects_real_write_even_with_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-apply"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "ready_for_future_confirm",
            "would_apply": True,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_apply", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-apply"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(1, "ExampleSwap", True, "APPLY_DEX_ROUTER_VENUE_MAPPING")

    def test_dex_router_venue_mapping_prewrite_audit_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-prewrite-audit?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_prewrite_audit_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-prewrite-audit"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_prewrite_audit_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "audit_status": "ready_but_disabled",
            "prewrite_ready": True,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_prewrite_audit", return_value=expected) as audit:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-prewrite-audit"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        audit.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_controlled_write_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-controlled-write-review"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_controlled_write_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-controlled-write-review"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_controlled_write_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "review_status": "ready_for_human_decision",
            "prewrite_ready": True,
            "write_enabled_now": False,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_controlled_write_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-controlled-write-review"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_sql_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-sql-plan?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_sql_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-sql-plan"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_sql_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "target_table": "dex_venue_mappings",
            "write_enabled_now": False,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_sql_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-sql-plan"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_final_safety_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-final-safety-review"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_final_safety_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-final-safety-review"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_final_safety_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "safety_status": "ready_for_write_design_only",
            "plan_ready": True,
            "write_enabled_now": False,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_final_safety_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-final-safety-review"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_apply_confirmed_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/apply-confirmed"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_apply_confirmed_rejects_real_write_even_with_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/apply-confirmed"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false"
            "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_apply_confirmed_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "ready_for_future_confirm",
            "would_write": True,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_apply_confirmed_design", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/apply-confirmed"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
                "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "ExampleSwap",
            True,
            "APPLY_DEX_ROUTER_VENUE_MAPPING CONFIRM_DEX_VENUE_MAPPING_WRITE",
        )

    def test_dex_router_venue_mapping_real_write_go_nogo_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-real-write-go-nogo"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_real_write_go_nogo_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping-real-write-go-nogo"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_real_write_go_nogo_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "decision": "go_for_write_design",
            "pipeline_ready": True,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_real_write_go_nogo", return_value=expected) as go_nogo:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping-real-write-go-nogo"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        go_nogo.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_write_skeleton_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/write-skeleton"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_write_skeleton_rejects_real_write_even_with_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/write-skeleton"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false"
            "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_write_skeleton_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "skeleton_status": "ready_but_disabled",
            "real_write_enabled": False,
            "mapping_allowed_now": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_write_skeleton", return_value=expected) as skeleton:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/write-skeleton"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
                "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        skeleton.assert_called_once_with(
            1,
            "ExampleSwap",
            True,
            "APPLY_DEX_ROUTER_VENUE_MAPPING CONFIRM_DEX_VENUE_MAPPING_WRITE CONFIRM_TRANSACTIONAL_RECHECKS",
        )

    def test_dex_router_venue_mapping_transactional_write_design_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/transactional-write-design"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_transactional_write_design_rejects_real_write_even_with_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/transactional-write-design"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false"
            "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS%20CONFIRM_ROLLBACK_ARTIFACT_BOUND",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_transactional_write_design_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "design_status": "ready_for_future_transactional_write",
            "write_enabled_now": False,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_transactional_write_design", return_value=expected) as design:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/transactional-write-design"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
                "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS%20CONFIRM_ROLLBACK_ARTIFACT_BOUND",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        design.assert_called_once_with(
            1,
            "ExampleSwap",
            True,
            "APPLY_DEX_ROUTER_VENUE_MAPPING CONFIRM_DEX_VENUE_MAPPING_WRITE CONFIRM_TRANSACTIONAL_RECHECKS CONFIRM_ROLLBACK_ARTIFACT_BOUND",
        )

    def test_dex_router_venue_mapping_transactional_write_report_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/transactional-write-report"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_transactional_write_report_rejects_real_write_even_with_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/transactional-write-report"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false"
            "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS%20CONFIRM_ROLLBACK_ARTIFACT_BOUND",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_transactional_write_report_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "status": "ready_but_disabled",
            "would_write_later": True,
            "write_enabled_now": False,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_transactional_write_report", return_value=expected) as report:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/transactional-write-report"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
                "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS%20CONFIRM_ROLLBACK_ARTIFACT_BOUND",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        report.assert_called_once_with(
            1,
            "ExampleSwap",
            True,
            "APPLY_DEX_ROUTER_VENUE_MAPPING CONFIRM_DEX_VENUE_MAPPING_WRITE CONFIRM_TRANSACTIONAL_RECHECKS CONFIRM_ROLLBACK_ARTIFACT_BOUND",
        )

    def test_dex_router_venue_mapping_confirmed_write_blueprint_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/confirmed-write-blueprint"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_confirmed_write_blueprint_rejects_real_write_even_with_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/confirmed-write-blueprint"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false"
            "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS%20CONFIRM_ROLLBACK_ARTIFACT_BOUND%20CONFIRM_REAL_DEX_MAPPING_WRITE",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_confirmed_write_blueprint_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "blueprint_status": "ready_but_disabled",
            "would_enable_write": False,
            "write_enabled_now": False,
            "mapping_allowed_now": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_confirmed_write_blueprint", return_value=expected) as blueprint:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/confirmed-write-blueprint"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
                "&confirm=APPLY_DEX_ROUTER_VENUE_MAPPING%20CONFIRM_DEX_VENUE_MAPPING_WRITE%20CONFIRM_TRANSACTIONAL_RECHECKS%20CONFIRM_ROLLBACK_ARTIFACT_BOUND%20CONFIRM_REAL_DEX_MAPPING_WRITE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        blueprint.assert_called_once_with(
            1,
            "ExampleSwap",
            True,
            "APPLY_DEX_ROUTER_VENUE_MAPPING CONFIRM_DEX_VENUE_MAPPING_WRITE CONFIRM_TRANSACTIONAL_RECHECKS CONFIRM_ROLLBACK_ARTIFACT_BOUND CONFIRM_REAL_DEX_MAPPING_WRITE",
        )

    def test_dex_router_venue_mapping_multi_router_validation_scan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/multi-router-validation-scan?limit=20&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_multi_router_validation_scan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/multi-router-validation-scan?limit=20&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_multi_router_validation_scan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "scan_status": "ready",
            "summary": {"ready_for_pipeline_replay": 1},
            "rows": [],
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_multi_router_validation_scan", return_value=expected) as scan:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/multi-router-validation-scan?limit=20&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        scan.assert_called_once_with(20, True)

    def test_dex_router_venue_mapping_additional_router_evidence_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/additional-router-evidence-plan?needed=2&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_additional_router_evidence_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/additional-router-evidence-plan?needed=2&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_additional_router_evidence_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "summary": {"proposed_rows": 2},
            "rows": [],
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_additional_router_evidence_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/additional-router-evidence-plan?needed=2&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(2, True)

    def test_dex_router_venue_mapping_additional_router_evidence_plan_rejects_large_needed(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/additional-router-evidence-plan?needed=6&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "needed_max_5")

    def test_lab_venue_coverage_source_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/lab-venue-coverage-source-plan?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_lab_venue_coverage_source_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/lab-venue-coverage-source-plan?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_lab_venue_coverage_source_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "summary": {"user_observed_venues": 26},
            "cex_rows": [],
            "dex_rows": [],
            "hybrid_or_unclear_rows": [],
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_lab_venue_coverage_source_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/lab-venue-coverage-source-plan?dry_run=true&include_user_observed=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(True, True)

    def test_token_venue_coverage_source_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/token-venue-coverage-source-plan?token_symbol=LAB&dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_venue_coverage_source_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-venue-coverage-source-plan?token_symbol=LAB&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_venue_coverage_source_plan_requires_token_symbol(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-venue-coverage-source-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "token_symbol_required")

    def test_token_venue_coverage_source_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "token_symbol": "LAB",
            "plan_status": "ready",
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_venue_coverage_source_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/token-venue-coverage-source-plan"
                "?token_symbol=LAB&chain=bsc&dry_run=true&include_user_observed=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("LAB", "bsc", True, True)

    def test_token_market_discovery_input_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/token-market-discovery-input-contract?token_symbol=LAB&dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_input_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-input-contract?token_symbol=LAB&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_input_contract_requires_token_symbol(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-input-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "token_symbol_required")

    def test_token_market_discovery_input_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "token_symbol": "LAB",
            "contract_status": "ready",
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_input_contract", return_value=expected) as contract:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-input-contract?token_symbol=LAB&chain=bsc&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with("LAB", "bsc", True)

    def test_token_market_discovery_candidate_schema_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/token-market-discovery-candidate-schema?token_symbol=LAB&dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_candidate_schema_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidate-schema?token_symbol=LAB&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_candidate_schema_requires_token_symbol(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidate-schema?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "token_symbol_required")

    def test_token_market_discovery_candidate_schema_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "token_symbol": "LAB",
            "schema_status": "ready",
            "would_create_table": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_candidate_schema", return_value=expected) as schema:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-candidate-schema?token_symbol=LAB&chain=bsc&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        schema.assert_called_once_with("LAB", "bsc", True)

    def test_token_market_discovery_candidates_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates-schema-plan?token_symbol=LAB&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_candidates_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates-schema-plan?token_symbol=LAB&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_candidates_schema_plan_requires_token_symbol(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "token_symbol_required")

    def test_token_market_discovery_candidates_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "token_symbol": "LAB",
            "plan_status": "ready",
            "would_create_table": False,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_candidates_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-candidates-schema-plan?token_symbol=LAB&chain=bsc&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("LAB", "bsc", True)

    def test_create_token_market_discovery_candidates_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/create?token_symbol=LAB&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_create_token_market_discovery_candidates_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/create?token_symbol=LAB&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_TOKEN_MARKET_DISCOVERY_CANDIDATES_TABLE_required")

    def test_create_token_market_discovery_candidates_requires_token_symbol(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "token_symbol_required")

    def test_create_token_market_discovery_candidates_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "token_symbol": "LAB",
            "table_created": True,
            "candidate_rows": 0,
            "would_write": False,
            "writes_performed": 9,
        }

        with patch("routers.onchain.create_token_market_discovery_candidates", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-candidates/create"
                "?token_symbol=LAB&chain=bsc&dry_run=false&confirm=CREATE_TOKEN_MARKET_DISCOVERY_CANDIDATES_TABLE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with("LAB", "bsc", False, "CREATE_TOKEN_MARKET_DISCOVERY_CANDIDATES_TABLE")

    def test_insert_token_market_discovery_candidate_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/insert?token_symbol=LAB&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_insert_token_market_discovery_candidate_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/insert?token_symbol=LAB&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_TOKEN_MARKET_DISCOVERY_CANDIDATE_required")

    def test_insert_token_market_discovery_candidate_requires_token_symbol(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "token_symbol_required")

    def test_insert_token_market_discovery_candidate_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_status": "ready_for_insert",
            "would_insert": True,
            "inserted": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.insert_token_market_discovery_candidate", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-candidates/insert"
                "?token_symbol=LAB&chain=bsc&market_type=cex&venue_name=Gate&pair=LAB/USDT"
                "&source_url=https://gate.example/markets/lab-usdt&source_tier=tier_1&evidence_type=official_exchange_market_page"
                "&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "LAB",
            "bsc",
            "cex",
            "Gate",
            "LAB/USDT",
            None,
            None,
            None,
            None,
            None,
            "https://gate.example/markets/lab-usdt",
            "tier_1",
            "official_exchange_market_page",
            None,
            None,
            None,
            True,
            None,
        )

    def test_token_market_discovery_candidate_review_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/token-market-discovery-candidates/review-queue?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_candidate_review_queue_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/review-queue?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_candidate_review_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_candidates": 1},
            "rows": [],
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_candidate_review_queue", return_value=expected) as queue:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-candidates/review-queue"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        queue.assert_called_once_with("pending_admin_review", "LAB", "cex", 25, True)

    def test_token_market_discovery_candidate_evidence_intake_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/evidence-intake-preview?candidate_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_candidate_evidence_intake_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/evidence-intake-preview?candidate_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_candidate_evidence_intake_preview_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-candidates/evidence-intake-preview?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_token_market_discovery_candidate_evidence_intake_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "candidate_id": 1,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_candidate_evidence_intake_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-candidates/evidence-intake-preview?candidate_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, True)

    def test_token_market_discovery_evidence_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence-queue-schema-plan?candidate_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_evidence_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence-queue-schema-plan?candidate_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_evidence_queue_schema_plan_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_token_market_discovery_evidence_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "candidate_id": 1,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_evidence_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence-queue-schema-plan?candidate_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_create_token_market_discovery_evidence_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence-queue/create?candidate_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_create_token_market_discovery_evidence_queue_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence-queue/create?candidate_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_TOKEN_MARKET_DISCOVERY_EVIDENCE_QUEUE_required")

    def test_create_token_market_discovery_evidence_queue_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_create_token_market_discovery_evidence_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "table_created": True,
            "evidence_rows": 0,
            "writes_performed": 7,
        }

        with patch("routers.onchain.create_token_market_discovery_evidence_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence-queue/create"
                "?candidate_id=1&dry_run=false&confirm=CREATE_TOKEN_MARKET_DISCOVERY_EVIDENCE_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_TOKEN_MARKET_DISCOVERY_EVIDENCE_QUEUE")

    def test_insert_token_market_discovery_evidence_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/token-market-discovery-evidence/insert?candidate_id=1&dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_insert_token_market_discovery_evidence_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/insert?candidate_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_TOKEN_MARKET_DISCOVERY_EVIDENCE_required")

    def test_insert_token_market_discovery_evidence_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_insert_token_market_discovery_evidence_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "ready_for_insert",
            "candidate_id": 1,
            "would_insert": True,
            "writes_performed": 0,
        }

        with patch("routers.onchain.insert_token_market_discovery_evidence", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence/insert"
                "?candidate_id=1&expected_evidence_preview_digest=abc&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(1, "abc", True, None)

    def test_token_market_discovery_evidence_review_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/token-market-discovery-evidence/review-queue?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_evidence_review_queue_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/review-queue?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_evidence_review_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_evidence_rows": 1},
            "rows": [],
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_evidence_review_queue", return_value=expected) as queue:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence/review-queue"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        queue.assert_called_once_with("pending_admin_review", "LAB", "cex", 25, True)

    def test_token_market_discovery_evidence_human_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision-preview"
            "?evidence_id=1&proposed_decision=accept_for_future_controlled_promotion&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_evidence_human_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision-preview"
            "?evidence_id=1&proposed_decision=accept_for_future_controlled_promotion&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_evidence_human_decision_preview_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision-preview"
            "?proposed_decision=accept_for_future_controlled_promotion&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_token_market_discovery_evidence_human_decision_preview_rejects_invalid_decision(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision-preview"
            "?evidence_id=1&proposed_decision=approve_everything&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid_proposed_decision")

    def test_token_market_discovery_evidence_human_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "evidence_id": 1,
            "decision_allowed": True,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_evidence_human_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence/human-decision-preview"
                "?evidence_id=1&proposed_decision=accept_for_future_controlled_promotion&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_controlled_promotion", True)

    def test_apply_token_market_discovery_evidence_human_decision_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision/apply"
            "?evidence_id=1&proposed_decision=accept_for_future_controlled_promotion&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_apply_token_market_discovery_evidence_human_decision_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision/apply"
            "?evidence_id=1&proposed_decision=accept_for_future_controlled_promotion&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_APPLY_TOKEN_MARKET_DISCOVERY_EVIDENCE_HUMAN_DECISION_required")

    def test_apply_token_market_discovery_evidence_human_decision_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision/apply"
            "?proposed_decision=accept_for_future_controlled_promotion&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_apply_token_market_discovery_evidence_human_decision_rejects_invalid_decision(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/human-decision/apply"
            "?evidence_id=1&proposed_decision=approve&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid_proposed_decision")

    def test_apply_token_market_discovery_evidence_human_decision_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "evidence_id": 1,
            "writes_performed": 1,
        }

        with patch("routers.onchain.apply_token_market_discovery_evidence_human_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence/human-decision/apply"
                "?evidence_id=1&proposed_decision=accept_for_future_controlled_promotion"
                "&dry_run=false&confirm=APPLY_TOKEN_MARKET_DISCOVERY_EVIDENCE_HUMAN_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_controlled_promotion",
            False,
            "APPLY_TOKEN_MARKET_DISCOVERY_EVIDENCE_HUMAN_DECISION",
        )

    def test_token_market_discovery_evidence_controlled_promotion_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-preview"
            "?evidence_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_evidence_controlled_promotion_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-preview"
            "?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_evidence_controlled_promotion_preview_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-preview?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_token_market_discovery_evidence_controlled_promotion_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "evidence_id": 1,
            "promotion_target": "cex_market_evidence_flow",
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_evidence_controlled_promotion_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-preview"
                "?evidence_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, True)

    def test_token_market_discovery_evidence_controlled_promotion_insert_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-insert-contract"
            "?evidence_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_discovery_evidence_controlled_promotion_insert_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-insert-contract"
            "?evidence_id=1&dry_run=false&confirm=INSERT_TOKEN_MARKET_DISCOVERY_CONTROLLED_PROMOTION",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_discovery_evidence_controlled_promotion_insert_contract_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-insert-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_token_market_discovery_evidence_controlled_promotion_insert_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "evidence_id": 1,
            "future_target_queue": "cex_market_discovery_promotion_queue",
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_discovery_evidence_controlled_promotion_insert_contract", return_value=expected) as contract:
            response = self.client.post(
                "/api/onchain/rpc/token-market-discovery-evidence/controlled-promotion-insert-contract"
                "?evidence_id=1&dry_run=true&confirm=IGNORED_IN_DRY_RUN",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True, "IGNORED_IN_DRY_RUN")

    def test_token_market_controlled_promotion_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue-schema-plan"
            "?evidence_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_controlled_promotion_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue-schema-plan"
            "?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_controlled_promotion_queue_schema_plan_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_token_market_controlled_promotion_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "evidence_id": 1,
            "target_table": "token_market_controlled_promotion_queue",
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_controlled_promotion_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/token-market-controlled-promotion-queue-schema-plan"
                "?evidence_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_create_token_market_controlled_promotion_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/create"
            "?evidence_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_create_token_market_controlled_promotion_queue_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/create"
            "?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_TOKEN_MARKET_CONTROLLED_PROMOTION_QUEUE_required")

    def test_create_token_market_controlled_promotion_queue_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_create_token_market_controlled_promotion_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "token_market_controlled_promotion_queue",
            "rows_inserted": 0,
        }

        with patch("routers.onchain.create_token_market_controlled_promotion_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/token-market-controlled-promotion-queue/create"
                "?evidence_id=1&dry_run=false&confirm=CREATE_TOKEN_MARKET_CONTROLLED_PROMOTION_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_TOKEN_MARKET_CONTROLLED_PROMOTION_QUEUE")

    def test_insert_token_market_controlled_promotion_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/insert"
            "?evidence_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_insert_token_market_controlled_promotion_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/insert"
            "?evidence_id=1&expected_promotion_dedupe_key=abc&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_TOKEN_MARKET_CONTROLLED_PROMOTION_required")

    def test_insert_token_market_controlled_promotion_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_insert_token_market_controlled_promotion_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "inserted",
            "evidence_id": 1,
            "promotion_id": 1,
        }

        with patch("routers.onchain.insert_token_market_controlled_promotion", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/token-market-controlled-promotion-queue/insert"
                "?evidence_id=1&expected_promotion_dedupe_key=abc&dry_run=false"
                "&confirm=INSERT_TOKEN_MARKET_CONTROLLED_PROMOTION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(1, "abc", False, "INSERT_TOKEN_MARKET_CONTROLLED_PROMOTION")

    def test_token_market_controlled_promotion_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/token-market-controlled-promotion-queue/review?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_controlled_promotion_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/review?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_controlled_promotion_queue_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_promotions": 1},
            "rows": [],
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_controlled_promotion_queue_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/token-market-controlled-promotion-queue/review"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "LAB", "cex", 25, True)

    def test_token_market_controlled_promotion_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision-preview"
            "?promotion_id=1&proposed_decision=accept_for_future_downstream_insert&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_controlled_promotion_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision-preview"
            "?promotion_id=1&proposed_decision=accept_for_future_downstream_insert&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_controlled_promotion_decision_preview_requires_promotion_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision-preview"
            "?proposed_decision=accept_for_future_downstream_insert&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "promotion_id_required")

    def test_token_market_controlled_promotion_decision_preview_rejects_invalid_decision(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision-preview"
            "?promotion_id=1&proposed_decision=approve&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid_proposed_decision")

    def test_token_market_controlled_promotion_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "promotion_id": 1,
            "decision_allowed": True,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_token_market_controlled_promotion_decision_preview",
            return_value=expected,
        ) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-controlled-promotion-queue/decision-preview"
                "?promotion_id=1&proposed_decision=accept_for_future_downstream_insert&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_downstream_insert", True)

    def test_apply_token_market_controlled_promotion_decision_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision/apply"
            "?promotion_id=1&proposed_decision=accept_for_future_downstream_insert&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_apply_token_market_controlled_promotion_decision_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision/apply"
            "?promotion_id=1&proposed_decision=accept_for_future_downstream_insert&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "confirm_APPLY_TOKEN_MARKET_CONTROLLED_PROMOTION_DECISION_required",
        )

    def test_apply_token_market_controlled_promotion_decision_requires_promotion_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision/apply"
            "?proposed_decision=accept_for_future_downstream_insert&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "promotion_id_required")

    def test_apply_token_market_controlled_promotion_decision_rejects_invalid_decision(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/decision/apply"
            "?promotion_id=1&proposed_decision=approve&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid_proposed_decision")

    def test_apply_token_market_controlled_promotion_decision_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "promotion_id": 1,
            "updated": True,
            "writes_performed": 1,
        }

        with patch(
            "routers.onchain.apply_token_market_controlled_promotion_decision",
            return_value=expected,
        ) as apply:
            response = self.client.post(
                "/api/onchain/rpc/token-market-controlled-promotion-queue/decision/apply"
                "?promotion_id=1&proposed_decision=accept_for_future_downstream_insert&dry_run=false"
                "&confirm=APPLY_TOKEN_MARKET_CONTROLLED_PROMOTION_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_downstream_insert",
            False,
            "APPLY_TOKEN_MARKET_CONTROLLED_PROMOTION_DECISION",
        )

    def test_token_market_controlled_promotion_downstream_insert_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/downstream-insert-contract"
            "?promotion_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_controlled_promotion_downstream_insert_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/downstream-insert-contract"
            "?promotion_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_controlled_promotion_downstream_insert_contract_requires_promotion_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-controlled-promotion-queue/downstream-insert-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "promotion_id_required")

    def test_token_market_controlled_promotion_downstream_insert_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "promotion_id": 1,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.get_token_market_controlled_promotion_downstream_insert_contract",
            return_value=expected,
        ) as contract:
            response = self.client.post(
                "/api/onchain/rpc/token-market-controlled-promotion-queue/downstream-insert-contract"
                "?promotion_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_token_market_downstream_promotion_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue-schema-plan?promotion_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_promotion_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue-schema-plan?promotion_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_promotion_queue_schema_plan_requires_promotion_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "promotion_id_required")

    def test_token_market_downstream_promotion_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "token_market_downstream_promotion_queue",
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_token_market_downstream_promotion_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-promotion-queue-schema-plan"
                "?promotion_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_token_market_downstream_promotion_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/create?promotion_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_promotion_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/create?promotion_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_TOKEN_MARKET_DOWNSTREAM_PROMOTION_QUEUE_required")

    def test_token_market_downstream_promotion_queue_create_requires_promotion_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "promotion_id_required")

    def test_token_market_downstream_promotion_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "token_market_downstream_promotion_queue",
            "rows_inserted": 0,
        }

        with patch("routers.onchain.create_token_market_downstream_promotion_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-promotion-queue/create"
                "?promotion_id=1&dry_run=false&confirm=CREATE_TOKEN_MARKET_DOWNSTREAM_PROMOTION_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_TOKEN_MARKET_DOWNSTREAM_PROMOTION_QUEUE")

    def test_token_market_downstream_promotion_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/insert?promotion_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_promotion_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/insert?promotion_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_TOKEN_MARKET_DOWNSTREAM_PROMOTION_required")

    def test_token_market_downstream_promotion_queue_insert_requires_promotion_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "promotion_id_required")

    def test_token_market_downstream_promotion_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "inserted",
            "promotion_id": 1,
            "downstream_id": 1,
        }

        with patch("routers.onchain.insert_token_market_downstream_promotion", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-promotion-queue/insert"
                "?promotion_id=1&expected_downstream_dedupe_key=abc&dry_run=false"
                "&confirm=INSERT_TOKEN_MARKET_DOWNSTREAM_PROMOTION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(1, "abc", False, "INSERT_TOKEN_MARKET_DOWNSTREAM_PROMOTION")

    def test_token_market_downstream_promotion_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/review?status=pending_admin_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_promotion_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/review?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_promotion_queue_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_downstream_rows": 1},
            "rows": [],
        }

        with patch("routers.onchain.get_token_market_downstream_promotion_queue_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-promotion-queue/review"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=20&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "LAB", "cex", 20, True)

    def test_token_market_downstream_promotion_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/decision-preview"
            "?downstream_id=1&proposed_decision=accept_for_future_downstream_business_insert&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_promotion_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/decision-preview"
            "?downstream_id=1&proposed_decision=accept_for_future_downstream_business_insert&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_promotion_decision_preview_requires_downstream_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/decision-preview"
            "?proposed_decision=accept_for_future_downstream_business_insert&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "downstream_id_required")

    def test_token_market_downstream_promotion_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "downstream_id": 1,
            "decision_allowed": True,
        }

        with patch("routers.onchain.get_token_market_downstream_promotion_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-promotion-queue/decision-preview"
                "?downstream_id=1&proposed_decision=accept_for_future_downstream_business_insert&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_downstream_business_insert", True)

    def test_token_market_downstream_promotion_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/decision/apply"
            "?downstream_id=1&proposed_decision=accept_for_future_downstream_business_insert&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_promotion_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/decision/apply"
            "?downstream_id=1&proposed_decision=accept_for_future_downstream_business_insert&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_APPLY_TOKEN_MARKET_DOWNSTREAM_PROMOTION_DECISION_required")

    def test_token_market_downstream_promotion_decision_apply_requires_downstream_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/decision/apply"
            "?proposed_decision=accept_for_future_downstream_business_insert&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "downstream_id_required")

    def test_token_market_downstream_promotion_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "downstream_id": 1,
            "updated": True,
        }

        with patch("routers.onchain.apply_token_market_downstream_promotion_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-promotion-queue/decision/apply"
                "?downstream_id=1&proposed_decision=accept_for_future_downstream_business_insert&dry_run=false"
                "&confirm=APPLY_TOKEN_MARKET_DOWNSTREAM_PROMOTION_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_downstream_business_insert",
            False,
            "APPLY_TOKEN_MARKET_DOWNSTREAM_PROMOTION_DECISION",
        )

    def test_token_market_downstream_business_insert_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/business-insert-contract"
            "?downstream_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_insert_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/business-insert-contract"
            "?downstream_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_business_insert_contract_requires_downstream_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-promotion-queue/business-insert-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "downstream_id_required")

    def test_token_market_downstream_business_insert_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "downstream_id": 1,
        }

        with patch("routers.onchain.get_token_market_downstream_business_insert_contract", return_value=expected) as contract:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-promotion-queue/business-insert-contract"
                "?downstream_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_token_market_downstream_business_handoff_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue-schema-plan"
            "?downstream_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_handoff_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue-schema-plan"
            "?downstream_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_business_handoff_queue_schema_plan_requires_downstream_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "downstream_id_required")

    def test_token_market_downstream_business_handoff_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "token_market_downstream_business_handoff_queue",
        }

        with patch("routers.onchain.get_token_market_downstream_business_handoff_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-business-handoff-queue-schema-plan"
                "?downstream_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_token_market_downstream_business_handoff_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/create"
            "?downstream_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_handoff_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/create"
            "?downstream_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "confirm_CREATE_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_QUEUE_required",
        )

    def test_token_market_downstream_business_handoff_queue_create_requires_downstream_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "downstream_id_required")

    def test_token_market_downstream_business_handoff_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "token_market_downstream_business_handoff_queue",
        }

        with patch("routers.onchain.create_token_market_downstream_business_handoff_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-business-handoff-queue/create"
                "?downstream_id=1&dry_run=false&confirm=CREATE_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_QUEUE")

    def test_token_market_downstream_business_handoff_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/insert"
            "?downstream_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_handoff_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/insert"
            "?downstream_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_required")

    def test_token_market_downstream_business_handoff_queue_insert_requires_downstream_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "downstream_id_required")

    def test_token_market_downstream_business_handoff_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "inserted",
            "business_handoff_id": 1,
        }

        with patch("routers.onchain.insert_token_market_downstream_business_handoff", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-business-handoff-queue/insert"
                "?downstream_id=1&expected_business_dedupe_key=abc&dry_run=false"
                "&confirm=INSERT_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(1, "abc", False, "INSERT_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF")

    def test_token_market_downstream_business_handoff_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/review"
            "?status=pending_admin_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_handoff_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/review?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_business_handoff_queue_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_business_handoffs": 1},
        }

        with patch("routers.onchain.get_token_market_downstream_business_handoff_queue_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-business-handoff-queue/review"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=20&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "LAB", "cex", 20, True)

    def test_token_market_downstream_business_handoff_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision-preview"
            "?business_handoff_id=1&proposed_decision=accept_for_future_business_insert&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_handoff_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision-preview"
            "?business_handoff_id=1&proposed_decision=accept_for_future_business_insert&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_business_handoff_decision_preview_requires_handoff_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision-preview"
            "?proposed_decision=accept_for_future_business_insert&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_handoff_id_required")

    def test_token_market_downstream_business_handoff_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "business_handoff_id": 1,
        }

        with patch(
            "routers.onchain.get_token_market_downstream_business_handoff_decision_preview",
            return_value=expected,
        ) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision-preview"
                "?business_handoff_id=1&proposed_decision=accept_for_future_business_insert&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_business_insert", True)

    def test_token_market_downstream_business_handoff_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision/apply"
            "?business_handoff_id=1&proposed_decision=accept_for_future_business_insert&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_handoff_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision/apply"
            "?business_handoff_id=1&proposed_decision=accept_for_future_business_insert&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "confirm_APPLY_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_DECISION_required",
        )

    def test_token_market_downstream_business_handoff_decision_apply_requires_handoff_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision/apply"
            "?proposed_decision=accept_for_future_business_insert&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_handoff_id_required")

    def test_token_market_downstream_business_handoff_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "business_handoff_id": 1,
            "updated": True,
        }

        with patch(
            "routers.onchain.apply_token_market_downstream_business_handoff_decision",
            return_value=expected,
        ) as apply:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-business-handoff-queue/decision/apply"
                "?business_handoff_id=1&proposed_decision=accept_for_future_business_insert&dry_run=false"
                "&confirm=APPLY_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_business_insert",
            False,
            "APPLY_TOKEN_MARKET_DOWNSTREAM_BUSINESS_HANDOFF_DECISION",
        )

    def test_token_market_downstream_business_handoff_business_insert_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/business-insert-contract"
            "?business_handoff_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_downstream_business_handoff_business_insert_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/business-insert-contract"
            "?business_handoff_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_downstream_business_handoff_business_insert_contract_requires_handoff_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-downstream-business-handoff-queue/business-insert-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_handoff_id_required")

    def test_token_market_downstream_business_handoff_business_insert_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "business_handoff_id": 1,
        }

        with patch(
            "routers.onchain.get_token_market_downstream_business_handoff_business_insert_contract",
            return_value=expected,
        ) as contract:
            response = self.client.post(
                "/api/onchain/rpc/token-market-downstream-business-handoff-queue/business-insert-contract"
                "?business_handoff_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_token_market_business_insert_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue-schema-plan"
            "?business_handoff_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_business_insert_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue-schema-plan"
            "?business_handoff_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_business_insert_queue_schema_plan_requires_handoff_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_handoff_id_required")

    def test_token_market_business_insert_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "token_market_business_insert_queue",
        }

        with patch("routers.onchain.get_token_market_business_insert_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/token-market-business-insert-queue-schema-plan"
                "?business_handoff_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_token_market_business_insert_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/create"
            "?business_handoff_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_business_insert_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/create"
            "?business_handoff_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "confirm_CREATE_TOKEN_MARKET_BUSINESS_INSERT_QUEUE_required",
        )

    def test_token_market_business_insert_queue_create_requires_handoff_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_handoff_id_required")

    def test_token_market_business_insert_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "token_market_business_insert_queue",
        }

        with patch("routers.onchain.create_token_market_business_insert_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/token-market-business-insert-queue/create"
                "?business_handoff_id=1&dry_run=false&confirm=CREATE_TOKEN_MARKET_BUSINESS_INSERT_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_TOKEN_MARKET_BUSINESS_INSERT_QUEUE")

    def test_token_market_business_insert_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/insert"
            "?business_handoff_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_business_insert_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/insert"
            "?business_handoff_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_TOKEN_MARKET_BUSINESS_INSERT_required")

    def test_token_market_business_insert_queue_insert_requires_handoff_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_handoff_id_required")

    def test_token_market_business_insert_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "inserted",
            "business_insert_id": 1,
        }

        with patch("routers.onchain.insert_token_market_business_insert", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/token-market-business-insert-queue/insert"
                "?business_handoff_id=1&expected_business_insert_dedupe_key=abc&dry_run=false"
                "&confirm=INSERT_TOKEN_MARKET_BUSINESS_INSERT",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(1, "abc", False, "INSERT_TOKEN_MARKET_BUSINESS_INSERT")

    def test_token_market_business_insert_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/review"
            "?status=pending_admin_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_business_insert_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/review?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_business_insert_queue_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_business_inserts": 1},
        }

        with patch("routers.onchain.get_token_market_business_insert_queue_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/token-market-business-insert-queue/review"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=20&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "LAB", "cex", 20, True)

    def test_token_market_business_insert_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/decision-preview"
            "?business_insert_id=1&proposed_decision=accept_for_future_business_execution&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_business_insert_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/decision-preview"
            "?business_insert_id=1&proposed_decision=accept_for_future_business_execution&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_business_insert_decision_preview_requires_insert_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/decision-preview"
            "?proposed_decision=accept_for_future_business_execution&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_insert_id_required")

    def test_token_market_business_insert_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "business_insert_id": 1,
        }

        with patch("routers.onchain.get_token_market_business_insert_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-business-insert-queue/decision-preview"
                "?business_insert_id=1&proposed_decision=accept_for_future_business_execution&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_business_execution", True)

    def test_token_market_business_insert_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/decision/apply"
            "?business_insert_id=1&proposed_decision=accept_for_future_business_execution&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_business_insert_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/decision/apply"
            "?business_insert_id=1&proposed_decision=accept_for_future_business_execution&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "confirm_APPLY_TOKEN_MARKET_BUSINESS_INSERT_DECISION_required",
        )

    def test_token_market_business_insert_decision_apply_requires_insert_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-business-insert-queue/decision/apply"
            "?proposed_decision=accept_for_future_business_execution&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "business_insert_id_required")

    def test_token_market_business_insert_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "business_insert_id": 1,
            "updated": True,
        }

        with patch("routers.onchain.apply_token_market_business_insert_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/token-market-business-insert-queue/decision/apply"
                "?business_insert_id=1&proposed_decision=accept_for_future_business_execution&dry_run=false"
                "&confirm=APPLY_TOKEN_MARKET_BUSINESS_INSERT_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_business_execution",
            False,
            "APPLY_TOKEN_MARKET_BUSINESS_INSERT_DECISION",
        )

    def test_dex_router_venue_mapping_rollback_artifact_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-preview"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_rollback_artifact_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-preview"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_rollback_artifact_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "would_create_artifact": False,
            "artifact_write_enabled": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_rollback_artifact_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-preview"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "ExampleSwap", True)

    def test_dex_router_venue_mapping_rollback_artifact_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-schema-plan?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_rollback_artifact_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-schema-plan?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_dex_router_venue_mapping_rollback_artifact_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "target_table": "dex_venue_mapping_rollback_artifacts",
            "would_create_table": False,
            "would_create_file": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_rollback_artifact_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-schema-plan?dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(True)

    def test_create_dex_router_venue_mapping_rollback_artifact_storage_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-storage/create?dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_create_dex_router_venue_mapping_rollback_artifact_storage_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-storage/create?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT_STORAGE_required")

    def test_create_dex_router_venue_mapping_rollback_artifact_storage_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "would_create_table": True,
            "would_create_file": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch(
            "routers.onchain.create_dex_router_venue_mapping_rollback_artifact_storage",
            return_value=expected,
        ) as create:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact-storage/create?dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(True, None)

    def test_create_dex_router_venue_mapping_rollback_artifact_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact/create"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_create_dex_router_venue_mapping_rollback_artifact_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact/create"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT_required")

    def test_create_dex_router_venue_mapping_rollback_artifact_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "would_create_artifact": True,
            "would_create_file": False,
            "would_create_venue_mapping": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.create_dex_router_venue_mapping_rollback_artifact", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact/create"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, "ExampleSwap", True, None)

    def test_refresh_dex_router_venue_mapping_rollback_artifact_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact/refresh"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_refresh_dex_router_venue_mapping_rollback_artifact_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact/refresh"
            "?evidence_id=1&venue_name=ExampleSwap&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_REFRESH_DEX_VENUE_MAPPING_ROLLBACK_ARTIFACT_required")

    def test_refresh_dex_router_venue_mapping_rollback_artifact_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "refresh_status": "ready_but_disabled",
            "would_create_new_artifact": True,
            "would_create_file": False,
            "would_create_venue_mapping": False,
            "would_write": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.refresh_dex_router_venue_mapping_rollback_artifact", return_value=expected) as refresh:
            response = self.client.post(
                "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifact/refresh"
                "?evidence_id=1&venue_name=ExampleSwap&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        refresh.assert_called_once_with(1, "ExampleSwap", True, None)

    def test_dex_router_venue_mapping_rollback_artifacts_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifacts"
            "?evidence_id=1&venue_name=ExampleSwap&limit=20"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_dex_router_venue_mapping_rollback_artifacts_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifacts?venue_name=ExampleSwap",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 422)

    def test_dex_router_venue_mapping_rollback_artifacts_requires_venue_name(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifacts?evidence_id=1",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 422)

    def test_dex_router_venue_mapping_rollback_artifacts_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "valid_artifact_available": True,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_dex_router_venue_mapping_rollback_artifacts", return_value=expected) as artifacts:
            response = self.client.get(
                "/api/onchain/rpc/dex-router-venue-mapping/rollback-artifacts"
                "?evidence_id=1&venue_name=ExampleSwap&limit=99",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        artifacts.assert_called_once_with(1, "ExampleSwap", 99)

    def test_cex_label_promotion_write_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-promotion-write-preview?candidate_ids=1&dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_write_preview_passes_dry_run_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "write_enabled": False,
            "writes_performed": 0,
            "write_preview": [],
            "blocked": [],
        }

        with patch("routers.onchain.get_cex_label_promotion_write_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-promotion-write-preview?candidate_ids=1,2&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with([1, 2], True, None)

    def test_cex_label_promotion_write_preview_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-promotion-write-preview?candidate_ids=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_PROMOTE_STRICT_CEX_LABELS_required")

    def test_cex_label_promotion_admin_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-promotion-admin-queue?entities=gate,mexc&limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_admin_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"ready_for_preview": 1},
            "groups": {"ready_for_preview": []},
            "source_policy": "admin queue read-only",
        }

        with patch("routers.onchain.get_cex_label_promotion_admin_queue", return_value=expected) as queue:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-promotion-admin-queue?entities=gate,mexc&limit=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        queue.assert_called_once_with("gate,mexc", 7)

    def test_cex_label_promotion_stage_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-promotion-stage?candidate_id=1&dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_stage_rejects_multiple_candidates(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-promotion-stage?candidate_id=1,2&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "single_candidate_required")

    def test_cex_label_promotion_stage_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-promotion-stage?candidate_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_STAGE_STRICT_CEX_LABEL_required")

    def test_cex_label_promotion_stage_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "promotion_ready": True,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_cex_label_promotion_stage", return_value=expected) as stage:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-promotion-stage?candidate_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        stage.assert_called_once_with("1", True, None)

    def test_cex_label_promotion_backup_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-promotion-backup?candidate_id=1&dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_backup_rejects_multiple_candidates(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-promotion-backup?candidate_id=1,2&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "single_candidate_required")

    def test_cex_label_promotion_backup_create_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-promotion-backup?candidate_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_STRICT_CEX_LABEL_BACKUP_required")

    def test_cex_label_promotion_backup_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "backup_created": False,
            "writes_performed": 0,
        }

        with patch("routers.onchain.get_cex_label_promotion_backup", return_value=expected) as backup:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-promotion-backup?candidate_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        backup.assert_called_once_with("1", True, None)

    def test_cex_label_promotion_backups_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-promotion-backups?candidate_id=1&limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_backups_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-promotion-backups?candidate_id=&limit=5",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_cex_label_promotion_backups_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "backup_count": 0,
            "valid_backup_available": False,
        }

        with patch("routers.onchain.get_cex_label_promotion_backups", return_value=expected) as backups:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-promotion-backups?candidate_id=1&limit=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        backups.assert_called_once_with("1", 7)

    def test_cex_label_promotion_final_check_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-promotion-final-check?candidate_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_final_check_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-promotion-final-check?candidate_id=",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_cex_label_promotion_final_check_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "all_gates_ready": False,
            "real_write_enabled": False,
        }

        with patch("routers.onchain.get_cex_label_promotion_final_check", return_value=expected) as final_check:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-promotion-final-check?candidate_id=1",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        final_check.assert_called_once_with("1")

    def test_cex_label_promotion_execution_envelope_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-promotion-execution-envelope?candidate_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_execution_envelope_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-promotion-execution-envelope?candidate_id=",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_cex_label_promotion_execution_envelope_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-promotion-execution-envelope?candidate_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_promotion_execution_envelope_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "would_write": False,
            "execution_allowed": False,
        }

        with patch("routers.onchain.get_cex_label_promotion_execution_envelope", return_value=expected) as envelope:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-promotion-execution-envelope?candidate_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        envelope.assert_called_once_with("1", True)

    def test_cex_label_promotion_simulation_report_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-promotion-simulation-report?candidate_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_simulation_report_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-promotion-simulation-report?candidate_id=",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_cex_label_promotion_simulation_report_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "status": "blocked",
            "execution_allowed": False,
        }

        with patch("routers.onchain.get_cex_label_promotion_simulation_report", return_value=expected) as report:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-promotion-simulation-report?candidate_id=1",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        report.assert_called_once_with("1")

    def test_cex_label_promotion_dashboard_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-promotion-dashboard?entities=gate,mexc&limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_dashboard_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-promotion-dashboard?entities=gate,mexc&limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_cex_label_promotion_dashboard_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"rows": 0, "real_write_enabled": False},
            "groups": {"ready_but_disabled": []},
            "rows": [],
            "source_policy": "dashboard read-only",
        }

        with patch("routers.onchain.get_cex_label_promotion_dashboard", return_value=expected) as dashboard:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-promotion-dashboard?entities=gate,mexc&limit=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        dashboard.assert_called_once_with("gate,mexc", 7)

    def test_cex_label_promotion_blocker_audit_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-promotion-blocker-audit?entities=gate,mexc&limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_promotion_blocker_audit_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-promotion-blocker-audit?entities=gate,mexc&limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_cex_label_promotion_blocker_audit_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"rows": 0, "can_be_fixed_automatically": False},
            "groups": {"blocked_manual_review": []},
            "rows": [],
            "source_policy": "blocker audit read-only",
        }

        with patch("routers.onchain.get_cex_label_promotion_blocker_audit", return_value=expected) as audit:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-promotion-blocker-audit?entities=gate,mexc&limit=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        audit.assert_called_once_with("gate,mexc", 7)

    def test_cex_label_source_quality_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-source-quality-plan?entities=gate,mexc&limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_source_quality_plan_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-source-quality-plan?entities=gate,mexc&limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_cex_label_source_quality_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"rows": 0, "upgrade_possible": False},
            "rows": [],
            "source_policy": "source quality plan read-only",
        }

        with patch("routers.onchain.get_cex_label_source_quality_plan", return_value=expected) as plan:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-source-quality-plan?entities=gate,mexc&limit=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("gate,mexc", 7)

    def test_cex_label_independent_source_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-independent-source-queue?entities=gate,mexc&limit=5")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_independent_source_queue_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-independent-source-queue?entities=gate,mexc&limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_cex_label_independent_source_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"rows": 0, "automation_allowed": False},
            "rows": [],
            "source_policy": "independent source queue read-only",
        }

        with patch("routers.onchain.get_cex_label_independent_source_queue", return_value=expected) as queue:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-independent-source-queue?entities=gate,mexc&limit=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        queue.assert_called_once_with("gate,mexc", 7)

    def test_cex_label_independent_evidence_dry_run_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence-dry-run"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_independent_evidence_dry_run_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence-dry-run"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_independent_evidence_dry_run_requires_source_url(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence-dry-run"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "source_url_required")

    def test_cex_label_independent_evidence_dry_run_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "evidence_accepted": True,
            "would_change_confidence": False,
            "would_write": False,
        }

        with patch("routers.onchain.get_cex_label_independent_evidence_dry_run", return_value=expected) as intake:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-independent-evidence-dry-run"
                "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&notes=test",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        intake.assert_called_once_with("1", "block_explorer_verified_label", "https://example.com", "test", True)

    def test_cex_label_independent_evidence_persist_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence-persist-preview"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_independent_evidence_persist_preview_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence-persist-preview"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_independent_evidence_persist_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "would_persist": True,
            "would_write": False,
        }

        with patch("routers.onchain.get_cex_label_independent_evidence_persist_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-independent-evidence-persist-preview"
                "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&notes=test",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with("1", "block_explorer_verified_label", "https://example.com", "test", True)

    def test_cex_label_independent_evidence_persist_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence-persist-contract"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_independent_evidence_persist_contract_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence-persist-contract"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_independent_evidence_persist_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "candidate_id": 1,
            "table_ready": True,
            "would_insert": True,
            "would_write": False,
        }

        with patch("routers.onchain.get_cex_label_independent_evidence_persist_contract", return_value=expected) as contract:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-independent-evidence-persist-contract"
                "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&notes=test",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with("1", "block_explorer_verified_label", "https://example.com", "test", True)

    def test_cex_label_independent_evidence_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence/insert"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_independent_evidence_insert_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-independent-evidence/insert"
            "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_CEX_INDEPENDENT_EVIDENCE_required")

    def test_cex_label_independent_evidence_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "inserted": False,
            "would_insert": True,
            "writes_performed": 0,
        }

        with patch("routers.onchain.insert_cex_label_independent_evidence", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-independent-evidence/insert"
                "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com&notes=test",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with("1", "block_explorer_verified_label", "https://example.com", "test", True, None)

    def test_cex_label_independent_evidence_insert_passes_confirm_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "inserted": True,
            "writes_performed": 1,
        }

        with patch("routers.onchain.insert_cex_label_independent_evidence", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-independent-evidence/insert"
                "?candidate_id=1&evidence_type=block_explorer_verified_label&source_url=https://example.com"
                "&dry_run=false&confirm=INSERT_CEX_INDEPENDENT_EVIDENCE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            "1",
            "block_explorer_verified_label",
            "https://example.com",
            None,
            False,
            "INSERT_CEX_INDEPENDENT_EVIDENCE",
        )

    def test_cex_label_independent_evidence_review_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-independent-evidence-review-queue")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_independent_evidence_review_queue_limit_max_50(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-independent-evidence-review-queue?limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_cex_label_independent_evidence_review_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "summary": {"rows": 1},
            "rows": [],
        }

        with patch("routers.onchain.get_cex_label_independent_evidence_review_queue", return_value=expected) as queue:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-independent-evidence-review-queue?status=pending_admin_review&limit=10",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        queue.assert_called_once_with("pending_admin_review", 10)

    def test_cex_label_confidence_upgrade_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-preview?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_preview_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-preview?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_preview_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-preview?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "evidence_id": 1,
            "upgrade_preview_available": True,
            "would_write": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-preview"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_stage_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-stage?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_stage_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-stage?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_STAGE_CEX_CONFIDENCE_UPGRADE_required")

    def test_cex_label_confidence_upgrade_stage_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-stage?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_stage_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "evidence_id": 1,
            "stage_ready": True,
            "real_write_enabled": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_stage", return_value=expected) as stage:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-stage"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        stage.assert_called_once_with("1", "high", True, None)

    def test_cex_label_confidence_upgrade_stage_passes_confirm_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "stage_ready": True,
            "real_write_enabled": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_stage", return_value=expected) as stage:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-stage"
                "?evidence_id=1&target_confidence=high&dry_run=false&confirm=STAGE_CEX_CONFIDENCE_UPGRADE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        stage.assert_called_once_with("1", "high", False, "STAGE_CEX_CONFIDENCE_UPGRADE")

    def test_cex_label_confidence_upgrade_backup_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-backup-preview?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_backup_preview_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-backup-preview?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_backup_preview_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-backup-preview?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_backup_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "evidence_id": 1,
            "backup_preview_available": True,
            "would_write": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_backup_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-backup-preview"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_backup_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-backup?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_backup_real_file_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-backup?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_CEX_CONFIDENCE_BACKUP_required")

    def test_cex_label_confidence_upgrade_backup_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-backup?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_backup_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "would_create_backup": True,
            "backup_created": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_backup", return_value=expected) as backup:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-backup"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        backup.assert_called_once_with("1", "high", True, None)

    def test_cex_label_confidence_upgrade_backup_passes_confirm_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "backup_created": True,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_backup", return_value=expected) as backup:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-backup"
                "?evidence_id=1&target_confidence=high&dry_run=false&confirm=CREATE_CEX_CONFIDENCE_BACKUP",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        backup.assert_called_once_with("1", "high", False, "CREATE_CEX_CONFIDENCE_BACKUP")

    def test_cex_label_confidence_upgrade_backups_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-confidence-upgrade-backups?evidence_id=1&candidate_id=2")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_backups_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-confidence-upgrade-backups?evidence_id=abc&candidate_id=2",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_backups_requires_candidate_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-confidence-upgrade-backups?evidence_id=1&candidate_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "candidate_id_required")

    def test_cex_label_confidence_upgrade_backups_limit_max_50(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-confidence-upgrade-backups?evidence_id=1&candidate_id=2&limit=51",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_50")

    def test_cex_label_confidence_upgrade_backups_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "evidence_id": 1,
            "candidate_id": 2,
            "valid_backup_available": True,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_backups", return_value=expected) as backups:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-confidence-upgrade-backups?evidence_id=1&candidate_id=2&limit=7",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        backups.assert_called_once_with("1", "2", 7)

    def test_cex_label_confidence_upgrade_final_check_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-label-confidence-upgrade-final-check?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_final_check_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-confidence-upgrade-final-check?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_final_check_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "evidence_id": 1,
            "all_gates_ready": True,
            "real_write_enabled": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_final_check", return_value=expected) as final_check:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-confidence-upgrade-final-check?evidence_id=1&target_confidence=high",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        final_check.assert_called_once_with("1", "high")

    def test_cex_label_confidence_upgrade_execution_envelope_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-execution-envelope?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_execution_envelope_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-execution-envelope?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_execution_envelope_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-execution-envelope?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_execution_envelope_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "evidence_id": 1,
            "would_update": True,
            "execution_allowed": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_execution_envelope", return_value=expected) as envelope:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-execution-envelope"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        envelope.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_simulation_report_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-simulation-report?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_simulation_report_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-simulation-report?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_simulation_report_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-simulation-report?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_simulation_report_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "status": "ready_but_disabled",
            "evidence_id": 1,
            "execution_allowed": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_simulation_report", return_value=expected) as report:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-simulation-report"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        report.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_policy_gate_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-policy-gate?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_policy_gate_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-policy-gate?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_policy_gate_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-policy-gate?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_policy_gate_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "policy_status": "eligible_but_disabled",
            "evidence_id": 1,
            "mutation_policy_allowed": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_policy_gate", return_value=expected) as gate:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-policy-gate"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        gate.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-apply?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_apply_requires_dry_run_even_with_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-apply"
            "?evidence_id=1&dry_run=false&confirm=APPLY_CEX_CONFIDENCE_UPGRADE",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_apply_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-apply?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "ready_for_future_confirm",
            "evidence_id": 1,
            "mutation_allowed_now": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_apply", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-apply"
                "?evidence_id=1&target_confidence=high&dry_run=true&confirm=APPLY_CEX_CONFIDENCE_UPGRADE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with("1", "high", True, "APPLY_CEX_CONFIDENCE_UPGRADE")

    def test_cex_label_confidence_upgrade_prewrite_audit_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-prewrite-audit?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_prewrite_audit_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-prewrite-audit?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_prewrite_audit_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-prewrite-audit?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_prewrite_audit_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "audit_status": "ready_but_disabled",
            "evidence_id": 1,
            "mutation_allowed_now": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_prewrite_audit", return_value=expected) as audit:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-prewrite-audit"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        audit.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_controlled_write_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-controlled-write-review?evidence_id=1"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_controlled_write_review_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-controlled-write-review?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_controlled_write_review_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-controlled-write-review?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_controlled_write_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "review_status": "ready_for_human_decision",
            "evidence_id": 1,
            "write_enabled_now": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_controlled_write_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-controlled-write-review"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_sql_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-sql-plan?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_sql_plan_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-sql-plan?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_sql_plan_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-sql-plan?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_sql_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready_but_disabled",
            "evidence_id": 1,
            "write_enabled_now": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_sql_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-sql-plan"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with("1", "high", True)

    def test_cex_label_confidence_upgrade_rollback_smoke_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-label-confidence-upgrade-rollback-smoke?evidence_id=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_confidence_upgrade_rollback_smoke_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-rollback-smoke?evidence_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_confidence_upgrade_rollback_smoke_requires_evidence_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-confidence-upgrade-rollback-smoke?evidence_id=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "evidence_id_required")

    def test_cex_label_confidence_upgrade_rollback_smoke_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "rollback_status": "ready_but_disabled",
            "evidence_id": 1,
            "rollback_enabled_now": False,
        }

        with patch("routers.onchain.get_cex_label_confidence_upgrade_rollback_smoke", return_value=expected) as smoke:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-confidence-upgrade-rollback-smoke"
                "?evidence_id=1&target_confidence=high&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        smoke.assert_called_once_with("1", "high", True)

    def test_cex_independent_evidence_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/cex-independent-evidence-queue-schema-plan?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_independent_evidence_queue_schema_plan_requires_dry_run(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-independent-evidence-queue-schema-plan?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_independent_evidence_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "target_table": "cex_independent_evidence_queue",
            "would_create_table": False,
            "would_write": False,
        }

        with patch("routers.onchain.get_cex_independent_evidence_queue_schema_plan", return_value=expected) as plan:
            response = self.client.get(
                "/api/onchain/rpc/cex-independent-evidence-queue-schema-plan?dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(True)

    def test_create_cex_independent_evidence_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/cex-independent-evidence-queue/create?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_create_cex_independent_evidence_queue_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-independent-evidence-queue/create?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE_required")

    def test_create_cex_independent_evidence_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "would_create_table": True,
            "writes_performed": 0,
        }

        with patch("routers.onchain.create_cex_independent_evidence_queue", return_value=expected) as create_queue:
            response = self.client.post(
                "/api/onchain/rpc/cex-independent-evidence-queue/create?dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create_queue.assert_called_once_with(True, None)

    def test_create_cex_independent_evidence_queue_passes_confirm_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "table_created": True,
            "writes_performed": 5,
        }

        with patch("routers.onchain.create_cex_independent_evidence_queue", return_value=expected) as create_queue:
            response = self.client.post(
                "/api/onchain/rpc/cex-independent-evidence-queue/create"
                "?dry_run=false&confirm=CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create_queue.assert_called_once_with(False, "CREATE_CEX_INDEPENDENT_EVIDENCE_QUEUE")

    def test_read_only_corroborate_get_does_not_require_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/labels/candidates/corroborate?limit=1&timeout=2")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertFalse(response.json()["persist"])

    def test_readiness_gap_auto_fill_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/auto-fill-gaps?dry_run=true")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_readiness_gap_auto_fill_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/auto-fill-gaps?dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_RUN_READYNESS_GAP_FILL_required")

    def test_readiness_gap_auto_fill_passes_bounded_dry_run_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {"ok": True, "dry_run": True, "actions": []}

        with patch("routers.onchain.run_readiness_gap_auto_fill", return_value=expected) as auto_fill:
            response = self.client.post(
                "/api/onchain/rpc/auto-fill-gaps"
                "?entity=Binance&chain=bsc&dry_run=true&max_cycles=2&max_pairs=1",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        auto_fill.assert_called_once_with("Binance", "bsc", True, None, 2, 1)

    def test_readiness_gap_auto_fill_rejects_unbounded_runs(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/auto-fill-gaps?max_cycles=6",
            headers={"x-core-admin-token": "correct-token"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "max_cycles_max_5")

        response = self.client.post(
            "/api/onchain/rpc/auto-fill-gaps?max_pairs=6",
            headers={"x-core-admin-token": "correct-token"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "max_pairs_max_5")

    def test_persistent_corroborate_post_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/labels/candidates/corroborate?limit=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_persistent_corroborate_post_accepts_admin_token(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/labels/candidates/corroborate?limit=1&timeout=2",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertTrue(response.json()["persist"])

    def test_corroborate_job_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/labels/candidates/corroborate-job?limit=1&timeout=2")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_corroborate_job_rejects_unbounded_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/labels/candidates/corroborate-job?limit=26&timeout=2",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "limit_max_25")

    def test_candidate_duplicate_consolidation_uses_audited_job(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {"ok": True, "job_id": 123, "result": {"dry_run": True}}

        with patch("routers.onchain.consolidate_label_candidate_duplicates_job", return_value=expected) as job:
            response = self.client.post(
                "/api/onchain/labels/candidates/consolidate-duplicates?limit=5&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        job.assert_called_once_with(5, True)

    def test_candidate_real_promotion_requires_explicit_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/labels/candidates/promote?candidate_ids=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_PROMOTE_TRUSTED_LABELS_required")

    def test_candidate_real_promotion_passes_confirm_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {"ok": True, "dry_run": False, "promoted": 1, "rows": []}

        with patch("routers.onchain.promote_label_candidates", return_value=expected) as promote:
            response = self.client.post(
                "/api/onchain/labels/candidates/promote"
                "?candidate_ids=1,2&dry_run=false&confirm=PROMOTE_TRUSTED_LABELS",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        promote.assert_called_once_with([1, 2], 90, False, "PROMOTE_TRUSTED_LABELS")

    def test_candidate_real_promotion_has_tighter_id_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        ids = ",".join(str(i) for i in range(1, 12))

        response = self.client.post(
            f"/api/onchain/labels/candidates/promote"
            f"?candidate_ids={ids}&dry_run=false&confirm=PROMOTE_TRUSTED_LABELS",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "real_promote_candidate_ids_max_10")

    def test_guided_venue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/source-backed-venue-mapping/confirm-guided-review"
            "?candidate_id=eth:0x0000000000000000000000000000000000000000"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_mapping_admin_review_queue_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get("/api/onchain/rpc/source-backed-venue-mapping/admin-review-queue?limit=1")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_source_backed_mapping_admin_review_queue_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {"ok": True, "summary": {"queue_items": 0}}

        with patch("routers.onchain.get_source_backed_venue_mapping_admin_review_queue", return_value=expected) as queue:
            response = self.client.get(
                "/api/onchain/rpc/source-backed-venue-mapping/admin-review-queue"
                "?chain=eth&limit=3&timeout=2&include_counterparty_source_search=false",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        queue.assert_called_once_with("eth", 3, 2, False)

    def test_guided_venue_review_real_write_requires_confirm(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/source-backed-venue-mapping/confirm-guided-review"
            "?candidate_id=eth:0x0000000000000000000000000000000000000000&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_UPSERT_SOURCE_BACKED_VENUE_MAPPING_required")

    def test_guided_venue_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {"ok": True, "dry_run": True}

        with patch("routers.onchain.confirm_guided_venue_review", return_value=expected) as confirm:
            response = self.client.post(
                "/api/onchain/rpc/source-backed-venue-mapping/confirm-guided-review"
                "?candidate_id=eth:0x0000000000000000000000000000000000000000&dry_run=true&limit=3&timeout=2",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        confirm.assert_called_once_with(
            "eth:0x0000000000000000000000000000000000000000",
            True,
            None,
            3,
            2,
        )

    def test_guided_venue_reviews_batch_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post("/api/onchain/rpc/source-backed-venue-mapping/confirm-guided-reviews")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_guided_venue_reviews_batch_real_write_requires_confirm_and_tight_limit(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/source-backed-venue-mapping/confirm-guided-reviews?dry_run=false&limit=6",
            headers={"x-core-admin-token": "correct-token"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "real_write_limit_max_5")

        response = self.client.post(
            "/api/onchain/rpc/source-backed-venue-mapping/confirm-guided-reviews?dry_run=false&limit=5",
            headers={"x-core-admin-token": "correct-token"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_UPSERT_SOURCE_BACKED_VENUE_MAPPING_required")

    def test_guided_venue_reviews_batch_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {"ok": True, "dry_run": True, "actions": []}

        with patch("routers.onchain.confirm_guided_venue_reviews_batch", return_value=expected) as batch:
            response = self.client.post(
                "/api/onchain/rpc/source-backed-venue-mapping/confirm-guided-reviews"
                "?candidate_ids=eth:0x1111111111111111111111111111111111111111,eth:0x2222222222222222222222222222222222222222"
                "&dry_run=true&limit=2&timeout=3",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        batch.assert_called_once_with(
            [
                "eth:0x1111111111111111111111111111111111111111",
                "eth:0x2222222222222222222222222222222222222222",
            ],
            True,
            None,
            2,
            3,
        )

    def test_token_market_final_handoff_target_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/decision-preview"
            "?final_handoff_target_id=1&proposed_decision=accept_for_future_final_handoff_target&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_final_handoff_target_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/decision-preview"
            "?final_handoff_target_id=1&proposed_decision=accept_for_future_final_handoff_target&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_final_handoff_target_decision_preview_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/decision-preview"
            "?proposed_decision=accept_for_future_final_handoff_target&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "final_handoff_target_id_required")

    def test_token_market_final_handoff_target_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "final_handoff_target_id": 1,
            "decision_allowed": True,
        }

        with patch("routers.onchain.get_token_market_final_handoff_target_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/token-market-final-handoff-target-queue/decision-preview"
                "?final_handoff_target_id=1&proposed_decision=accept_for_future_final_handoff_target&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_final_handoff_target", True)

    def test_token_market_final_handoff_target_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/decision/apply"
            "?final_handoff_target_id=1&proposed_decision=accept_for_future_final_handoff_target&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_final_handoff_target_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/decision/apply"
            "?final_handoff_target_id=1&proposed_decision=accept_for_future_final_handoff_target&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "confirm_APPLY_TOKEN_MARKET_FINAL_HANDOFF_TARGET_DECISION_required",
        )

    def test_token_market_final_handoff_target_decision_apply_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/decision/apply"
            "?proposed_decision=accept_for_future_final_handoff_target&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "final_handoff_target_id_required")

    def test_token_market_final_handoff_target_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": True,
            "apply_status": "ready_but_disabled",
            "final_handoff_target_id": 1,
        }

        with patch("routers.onchain.apply_token_market_final_handoff_target_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/token-market-final-handoff-target-queue/decision/apply"
                "?final_handoff_target_id=1&proposed_decision=accept_for_future_final_handoff_target&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(1, "accept_for_future_final_handoff_target", True, None)

    def test_token_market_final_handoff_target_cex_review_handoff_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract"
            "?final_handoff_target_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_token_market_final_handoff_target_cex_review_handoff_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract"
            "?final_handoff_target_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_token_market_final_handoff_target_cex_review_handoff_contract_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "final_handoff_target_id_required")

    def test_token_market_final_handoff_target_cex_review_handoff_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "final_handoff_target_id": 1,
        }

        with patch(
            "routers.onchain.get_token_market_final_handoff_target_cex_review_handoff_contract",
            return_value=expected,
        ) as contract:
            response = self.client.post(
                "/api/onchain/rpc/token-market-final-handoff-target-queue/cex-review-handoff-contract"
                "?final_handoff_target_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_cex_market_evidence_review_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue-schema-plan"
            "?final_handoff_target_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_market_evidence_review_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue-schema-plan"
            "?final_handoff_target_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_market_evidence_review_queue_schema_plan_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "final_handoff_target_id_required")

    def test_cex_market_evidence_review_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "final_handoff_target_id": 1,
            "target_table": "cex_market_evidence_review_queue",
        }

        with patch("routers.onchain.get_cex_market_evidence_review_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/cex-market-evidence-review-queue-schema-plan"
                "?final_handoff_target_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_cex_market_evidence_review_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/create"
            "?final_handoff_target_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_market_evidence_review_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/create"
            "?final_handoff_target_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE_required")

    def test_cex_market_evidence_review_queue_create_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "final_handoff_target_id_required")

    def test_cex_market_evidence_review_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "create_status": "created",
            "target_table": "cex_market_evidence_review_queue",
        }

        with patch("routers.onchain.create_cex_market_evidence_review_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/cex-market-evidence-review-queue/create"
                "?final_handoff_target_id=1&dry_run=false&confirm=CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_CEX_MARKET_EVIDENCE_REVIEW_QUEUE")

    def test_cex_market_evidence_review_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/insert"
            "?final_handoff_target_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_market_evidence_review_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/insert"
            "?final_handoff_target_id=1&expected_cex_review_handoff_dedupe_key=abc&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_CEX_MARKET_EVIDENCE_REVIEW_required")

    def test_cex_market_evidence_review_queue_insert_requires_expected_dedupe_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/insert"
            "?final_handoff_target_id=1&dry_run=false&confirm=INSERT_CEX_MARKET_EVIDENCE_REVIEW",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "expected_cex_review_handoff_dedupe_key_required")

    def test_cex_market_evidence_review_queue_insert_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "final_handoff_target_id_required")

    def test_cex_market_evidence_review_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "insert_status": "inserted",
            "cex_review_id": 1,
        }

        with patch("routers.onchain.insert_cex_market_evidence_review", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/cex-market-evidence-review-queue/insert"
                "?final_handoff_target_id=1&expected_cex_review_handoff_dedupe_key=abc"
                "&dry_run=false&confirm=INSERT_CEX_MARKET_EVIDENCE_REVIEW",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(1, "abc", False, "INSERT_CEX_MARKET_EVIDENCE_REVIEW")

    def test_cex_market_evidence_review_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/review?status=pending_admin_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_market_evidence_review_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/review?status=pending_admin_review&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_market_evidence_review_queue_review_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_cex_reviews": 1},
            "rows": [],
        }

        with patch("routers.onchain.get_cex_market_evidence_review_queue_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/cex-market-evidence-review-queue/review"
                "?status=pending_admin_review&token_symbol=TEST&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "TEST", "cex", 25, True)

    def test_cex_market_evidence_review_queue_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/decision-preview"
            "?cex_review_id=1&proposed_decision=accept_for_future_cex_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_market_evidence_review_queue_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/decision-preview"
            "?cex_review_id=1&proposed_decision=accept_for_future_cex_review&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_market_evidence_review_queue_decision_preview_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/decision-preview"
            "?proposed_decision=accept_for_future_cex_review&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_review_id_required")

    def test_cex_market_evidence_review_queue_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "cex_review_id": 1,
            "decision_allowed": True,
        }

        with patch("routers.onchain.get_cex_market_evidence_review_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-market-evidence-review-queue/decision-preview"
                "?cex_review_id=1&proposed_decision=accept_for_future_cex_review&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_cex_review", True)

    def test_cex_market_evidence_review_queue_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/decision/apply"
            "?cex_review_id=1&proposed_decision=accept_for_future_cex_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_market_evidence_review_queue_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/decision/apply"
            "?cex_review_id=1&proposed_decision=accept_for_future_cex_review&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION_required")

    def test_cex_market_evidence_review_queue_decision_apply_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/decision/apply"
            "?proposed_decision=accept_for_future_cex_review&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_review_id_required")

    def test_cex_market_evidence_review_queue_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "apply_status": "updated",
            "cex_review_id": 1,
        }

        with patch("routers.onchain.apply_cex_market_evidence_review_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/cex-market-evidence-review-queue/decision/apply"
                "?cex_review_id=1&proposed_decision=accept_for_future_cex_review"
                "&dry_run=false&confirm=APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(1, "accept_for_future_cex_review", False, "APPLY_CEX_MARKET_EVIDENCE_REVIEW_DECISION")

    def test_cex_market_evidence_review_label_candidate_handoff_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract"
            "?cex_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_market_evidence_review_label_candidate_handoff_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract"
            "?cex_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_market_evidence_review_label_candidate_handoff_contract_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_review_id_required")

    def test_cex_market_evidence_review_label_candidate_handoff_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_review_id": 1,
        }

        with patch(
            "routers.onchain.get_cex_market_evidence_review_label_candidate_handoff_contract",
            return_value=expected,
        ) as contract:
            response = self.client.post(
                "/api/onchain/rpc/cex-market-evidence-review-queue/label-candidate-handoff-contract"
                "?cex_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_cex_label_candidate_review_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue-schema-plan"
            "?cex_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_candidate_review_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue-schema-plan"
            "?cex_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_candidate_review_queue_schema_plan_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_review_id_required")

    def test_cex_label_candidate_review_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "cex_review_id": 1,
        }

        with patch(
            "routers.onchain.get_cex_label_candidate_review_queue_schema_plan",
            return_value=expected,
        ) as plan:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-candidate-review-queue-schema-plan"
                "?cex_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_cex_label_candidate_review_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/create"
            "?cex_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_candidate_review_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/create"
            "?cex_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE_required")

    def test_cex_label_candidate_review_queue_create_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_review_id_required")

    def test_cex_label_candidate_review_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "create_status": "created",
            "target_table": "cex_label_candidate_review_queue",
        }

        with patch("routers.onchain.create_cex_label_candidate_review_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-candidate-review-queue/create"
                "?cex_review_id=1&dry_run=false&confirm=CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_CEX_LABEL_CANDIDATE_REVIEW_QUEUE")

    def test_cex_label_candidate_review_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/insert"
            "?cex_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_candidate_review_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/insert"
            "?cex_review_id=1&expected_label_candidate_handoff_dedupe_key=dedupe&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_CEX_LABEL_CANDIDATE_REVIEW_required")

    def test_cex_label_candidate_review_queue_insert_requires_expected_dedupe_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/insert"
            "?cex_review_id=1&dry_run=false&confirm=INSERT_CEX_LABEL_CANDIDATE_REVIEW",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "expected_label_candidate_handoff_dedupe_key_required")

    def test_cex_label_candidate_review_queue_insert_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_review_id_required")

    def test_cex_label_candidate_review_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "insert_status": "inserted",
            "cex_label_candidate_review_id": 1,
        }

        with patch("routers.onchain.insert_cex_label_candidate_review", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-candidate-review-queue/insert"
                "?cex_review_id=1&expected_label_candidate_handoff_dedupe_key=dedupe"
                "&dry_run=false&confirm=INSERT_CEX_LABEL_CANDIDATE_REVIEW",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(1, "dedupe", False, "INSERT_CEX_LABEL_CANDIDATE_REVIEW")

    def test_cex_label_candidate_review_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-label-candidate-review-queue/review?status=pending_admin_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_candidate_review_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-candidate-review-queue/review?status=pending_admin_review&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_candidate_review_queue_review_passes_filters_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "rows": [],
        }

        with patch("routers.onchain.get_cex_label_candidate_review_queue_review", return_value=expected) as review:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-candidate-review-queue/review"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "LAB", "cex", 25, True)

    def test_cex_label_candidate_review_queue_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/decision-preview"
            "?cex_label_candidate_review_id=1&proposed_decision=accept_for_future_cex_label_candidate"
            "&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_candidate_review_queue_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/decision-preview"
            "?cex_label_candidate_review_id=1&proposed_decision=accept_for_future_cex_label_candidate"
            "&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_candidate_review_queue_decision_preview_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/decision-preview"
            "?proposed_decision=accept_for_future_cex_label_candidate&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_candidate_review_id_required")

    def test_cex_label_candidate_review_queue_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "cex_label_candidate_review_id": 1,
        }

        with patch("routers.onchain.get_cex_label_candidate_review_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-candidate-review-queue/decision-preview"
                "?cex_label_candidate_review_id=1&proposed_decision=accept_for_future_cex_label_candidate"
                "&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_cex_label_candidate", True)

    def test_cex_label_candidate_review_queue_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/decision/apply"
            "?cex_label_candidate_review_id=1&proposed_decision=accept_for_future_cex_label_candidate"
            "&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_candidate_review_queue_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/decision/apply"
            "?cex_label_candidate_review_id=1&proposed_decision=accept_for_future_cex_label_candidate"
            "&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION_required")

    def test_cex_label_candidate_review_queue_decision_apply_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-candidate-review-queue/decision/apply"
            "?proposed_decision=accept_for_future_cex_label_candidate&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_candidate_review_id_required")

    def test_cex_label_candidate_review_queue_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "apply_status": "updated",
            "cex_label_candidate_review_id": 1,
        }

        with patch("routers.onchain.apply_cex_label_candidate_review_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-candidate-review-queue/decision/apply"
                "?cex_label_candidate_review_id=1&proposed_decision=accept_for_future_cex_label_candidate"
                "&dry_run=false&confirm=APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_cex_label_candidate",
            False,
            "APPLY_CEX_LABEL_CANDIDATE_REVIEW_DECISION",
        )

    def test_cex_label_creation_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-label-candidate-review-queue/label-creation-contract"
            "?cex_label_candidate_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_creation_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-candidate-review-queue/label-creation-contract"
            "?cex_label_candidate_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_creation_contract_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-candidate-review-queue/label-creation-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_candidate_review_id_required")

    def test_cex_label_creation_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_label_candidate_review_id": 1,
        }

        with patch("routers.onchain.get_cex_label_creation_contract", return_value=expected) as contract:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-candidate-review-queue/label-creation-contract"
                "?cex_label_candidate_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_cex_label_creation_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-queue-schema-plan"
            "?cex_label_candidate_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_creation_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-queue-schema-plan"
            "?cex_label_candidate_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_creation_queue_schema_plan_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_candidate_review_id_required")

    def test_cex_label_creation_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "cex_label_creation_review_queue",
        }

        with patch("routers.onchain.get_cex_label_creation_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-creation-queue-schema-plan"
                "?cex_label_candidate_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_cex_label_creation_review_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/create"
            "?cex_label_candidate_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_creation_review_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/create"
            "?cex_label_candidate_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE_required")

    def test_cex_label_creation_review_queue_create_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_candidate_review_id_required")

    def test_cex_label_creation_review_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "create_status": "created",
            "target_table": "cex_label_creation_review_queue",
        }

        with patch("routers.onchain.create_cex_label_creation_review_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-creation-review-queue/create"
                "?cex_label_candidate_review_id=1&dry_run=false&confirm=CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_CEX_LABEL_CREATION_REVIEW_QUEUE")

    def test_cex_label_creation_review_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/insert"
            "?cex_label_candidate_review_id=1&expected_label_dedupe_key=dedupe&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_creation_review_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/insert"
            "?cex_label_candidate_review_id=1&expected_label_dedupe_key=dedupe&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_CEX_LABEL_CREATION_REVIEW_required")

    def test_cex_label_creation_review_queue_insert_requires_expected_dedupe_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/insert"
            "?cex_label_candidate_review_id=1&dry_run=false&confirm=INSERT_CEX_LABEL_CREATION_REVIEW",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "expected_label_dedupe_key_required")

    def test_cex_label_creation_review_queue_insert_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/insert"
            "?expected_label_dedupe_key=dedupe&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_candidate_review_id_required")

    def test_cex_label_creation_review_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "insert_status": "inserted",
            "cex_label_creation_review_id": 1,
        }

        with patch("routers.onchain.insert_cex_label_creation_review", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-creation-review-queue/insert"
                "?cex_label_candidate_review_id=1&expected_label_dedupe_key=dedupe"
                "&dry_run=false&confirm=INSERT_CEX_LABEL_CREATION_REVIEW",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            1,
            "dedupe",
            False,
            "INSERT_CEX_LABEL_CREATION_REVIEW",
        )

    def test_cex_label_creation_review_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-review-queue/review"
            "?status=pending_admin_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_creation_review_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-review-queue/review"
            "?status=pending_admin_review&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_creation_review_queue_review_passes_filters_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_cex_label_creation_reviews": 1},
        }

        with patch("routers.onchain.get_cex_label_creation_review_queue_review", return_value=expected) as review:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-creation-review-queue/review"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "LAB", "cex", 25, True)

    def test_cex_label_creation_review_queue_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/decision-preview"
            "?cex_label_creation_review_id=1&proposed_decision=accept_for_future_cex_label_creation"
            "&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_creation_review_queue_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/decision-preview"
            "?cex_label_creation_review_id=1&proposed_decision=accept_for_future_cex_label_creation"
            "&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_label_creation_review_queue_decision_preview_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/decision-preview"
            "?proposed_decision=accept_for_future_cex_label_creation&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_creation_review_id_required")

    def test_cex_label_creation_review_queue_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "cex_label_creation_review_id": 1,
        }

        with patch("routers.onchain.get_cex_label_creation_review_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-creation-review-queue/decision-preview"
                "?cex_label_creation_review_id=1&proposed_decision=accept_for_future_cex_label_creation"
                "&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_cex_label_creation", True)

    def test_cex_label_creation_review_queue_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/decision/apply"
            "?cex_label_creation_review_id=1&proposed_decision=accept_for_future_cex_label_creation"
            "&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_label_creation_review_queue_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/decision/apply"
            "?cex_label_creation_review_id=1&proposed_decision=accept_for_future_cex_label_creation"
            "&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_APPLY_CEX_LABEL_CREATION_REVIEW_DECISION_required")

    def test_cex_label_creation_review_queue_decision_apply_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-label-creation-review-queue/decision/apply"
            "?proposed_decision=accept_for_future_cex_label_creation&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_creation_review_id_required")

    def test_cex_label_creation_review_queue_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "cex_label_creation_review_id": 1,
        }

        with patch("routers.onchain.apply_cex_label_creation_review_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/cex-label-creation-review-queue/decision/apply"
                "?cex_label_creation_review_id=1&proposed_decision=accept_for_future_cex_label_creation"
                "&dry_run=false&confirm=APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_cex_label_creation",
            False,
            "APPLY_CEX_LABEL_CREATION_REVIEW_DECISION",
        )

    def test_cex_final_label_write_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-review-queue/final-label-write-contract"
            "?cex_label_creation_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-review-queue/final-label-write-contract"
            "?cex_label_creation_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_write_contract_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-label-creation-review-queue/final-label-write-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_creation_review_id_required")

    def test_cex_final_label_write_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_label_creation_review_id": 1,
        }

        with patch("routers.onchain.get_cex_final_label_write_contract", return_value=expected) as contract:
            response = self.client.get(
                "/api/onchain/rpc/cex-label-creation-review-queue/final-label-write-contract"
                "?cex_label_creation_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_cex_final_label_write_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue-schema-plan"
            "?cex_label_creation_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue-schema-plan"
            "?cex_label_creation_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_write_queue_schema_plan_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_creation_review_id_required")

    def test_cex_final_label_write_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "cex_final_label_write_review_queue",
        }

        with patch("routers.onchain.get_cex_final_label_write_queue_schema_plan", return_value=expected) as plan:
            response = self.client.get(
                "/api/onchain/rpc/cex-final-label-write-queue-schema-plan"
                "?cex_label_creation_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_cex_final_label_write_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/create"
            "?cex_label_creation_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/create"
            "?cex_label_creation_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE_required")

    def test_cex_final_label_write_queue_create_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_creation_review_id_required")

    def test_cex_final_label_write_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "cex_final_label_write_review_queue",
        }

        with patch("routers.onchain.create_cex_final_label_write_review_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-write-queue/create"
                "?cex_label_creation_review_id=1&dry_run=false&confirm=CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_CEX_FINAL_LABEL_WRITE_REVIEW_QUEUE")

    def test_cex_final_label_write_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/insert"
            "?cex_label_creation_review_id=1&expected_final_label_dedupe_key=dedupe&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/insert"
            "?cex_label_creation_review_id=1&expected_final_label_dedupe_key=dedupe&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_CEX_FINAL_LABEL_WRITE_REVIEW_required")

    def test_cex_final_label_write_queue_insert_requires_expected_dedupe_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/insert"
            "?cex_label_creation_review_id=1&dry_run=false&confirm=INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "expected_final_label_dedupe_key_required")

    def test_cex_final_label_write_queue_insert_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/insert"
            "?expected_final_label_dedupe_key=dedupe&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_label_creation_review_id_required")

    def test_cex_final_label_write_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "dry_run": False,
            "insert_status": "inserted",
            "cex_final_label_write_review_id": 1,
        }

        with patch("routers.onchain.insert_cex_final_label_write_review", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-write-queue/insert"
                "?cex_label_creation_review_id=1&expected_final_label_dedupe_key=dedupe"
                "&dry_run=false&confirm=INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            1,
            "dedupe",
            False,
            "INSERT_CEX_FINAL_LABEL_WRITE_REVIEW",
        )

    def test_cex_final_label_write_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue/review"
            "?status=pending_admin_review&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue/review"
            "?status=pending_admin_review&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_write_queue_review_passes_filters_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_cex_final_label_write_reviews": 1},
        }

        with patch("routers.onchain.get_cex_final_label_write_review_queue_review", return_value=expected) as review:
            response = self.client.get(
                "/api/onchain/rpc/cex-final-label-write-queue/review"
                "?status=pending_admin_review&token_symbol=LAB&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "LAB", "cex", 25, True)

    def test_cex_final_label_write_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/decision-preview"
            "?cex_final_label_write_review_id=1&proposed_decision=accept_for_future_cex_final_label_write&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/decision-preview"
            "?cex_final_label_write_review_id=1&proposed_decision=accept_for_future_cex_final_label_write&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_write_decision_preview_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/decision-preview"
            "?proposed_decision=accept_for_future_cex_final_label_write&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_write_review_id_required")

    def test_cex_final_label_write_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "decision_allowed": True,
        }

        with patch("routers.onchain.get_cex_final_label_write_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-write-queue/decision-preview"
                "?cex_final_label_write_review_id=1&proposed_decision=accept_for_future_cex_final_label_write"
                "&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_cex_final_label_write", True)

    def test_cex_final_label_write_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/decision/apply"
            "?cex_final_label_write_review_id=1&proposed_decision=accept_for_future_cex_final_label_write&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/decision/apply"
            "?cex_final_label_write_review_id=1&proposed_decision=accept_for_future_cex_final_label_write&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION_required")

    def test_cex_final_label_write_decision_apply_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-write-queue/decision/apply"
            "?proposed_decision=accept_for_future_cex_final_label_write&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_write_review_id_required")

    def test_cex_final_label_write_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "updated": True,
        }

        with patch("routers.onchain.apply_cex_final_label_write_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-write-queue/decision/apply"
                "?cex_final_label_write_review_id=1&proposed_decision=accept_for_future_cex_final_label_write"
                "&dry_run=false&confirm=APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_cex_final_label_write",
            False,
            "APPLY_CEX_FINAL_LABEL_WRITE_REVIEW_DECISION",
        )

    def test_cex_final_label_write_execution_contract_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue/execution-contract"
            "?cex_final_label_write_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_execution_contract_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue/execution-contract"
            "?cex_final_label_write_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_write_execution_contract_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-write-queue/execution-contract?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_write_review_id_required")

    def test_cex_final_label_write_execution_contract_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "contract_status": "ready_but_disabled",
            "cex_final_label_write_review_id": 1,
        }

        with patch("routers.onchain.get_cex_final_label_write_execution_contract", return_value=expected) as contract:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-write-queue/execution-contract"
                "?cex_final_label_write_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        contract.assert_called_once_with(1, True)

    def test_cex_final_label_execution_queue_schema_plan_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue-schema-plan"
            "?cex_final_label_write_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_execution_queue_schema_plan_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue-schema-plan"
            "?cex_final_label_write_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_execution_queue_schema_plan_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue-schema-plan?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_write_review_id_required")

    def test_cex_final_label_execution_queue_schema_plan_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "plan_status": "ready",
            "target_table": "cex_final_label_execution_review_queue",
        }

        with patch("routers.onchain.get_cex_final_label_execution_queue_schema_plan", return_value=expected) as plan:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-execution-queue-schema-plan"
                "?cex_final_label_write_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        plan.assert_called_once_with(1, True)

    def test_cex_final_label_execution_queue_create_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/create"
            "?cex_final_label_write_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_execution_queue_create_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/create"
            "?cex_final_label_write_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE_required")

    def test_cex_final_label_execution_queue_create_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/create?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_write_review_id_required")

    def test_cex_final_label_execution_queue_create_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "create_status": "created",
            "target_table": "cex_final_label_execution_review_queue",
        }

        with patch("routers.onchain.create_cex_final_label_execution_review_queue", return_value=expected) as create:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-execution-queue/create"
                "?cex_final_label_write_review_id=1&dry_run=false"
                "&confirm=CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        create.assert_called_once_with(1, False, "CREATE_CEX_FINAL_LABEL_EXECUTION_REVIEW_QUEUE")

    def test_cex_final_label_execution_queue_insert_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/insert"
            "?cex_final_label_write_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_execution_queue_insert_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/insert"
            "?cex_final_label_write_review_id=1&dry_run=false&expected_final_label_execution_dedupe_key=abc",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW_required")

    def test_cex_final_label_execution_queue_insert_requires_expected_dedupe_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/insert"
            "?cex_final_label_write_review_id=1&dry_run=false&confirm=INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "expected_final_label_execution_dedupe_key_required")

    def test_cex_final_label_execution_queue_insert_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/insert?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_write_review_id_required")

    def test_cex_final_label_execution_queue_insert_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "insert_status": "inserted",
            "cex_final_label_execution_review_id": 1,
        }

        with patch("routers.onchain.insert_cex_final_label_execution_review", return_value=expected) as insert:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-execution-queue/insert"
                "?cex_final_label_write_review_id=1&dry_run=false"
                "&expected_final_label_execution_dedupe_key=dedupe"
                "&confirm=INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        insert.assert_called_once_with(
            1,
            "dedupe",
            False,
            "INSERT_CEX_FINAL_LABEL_EXECUTION_REVIEW",
        )

    def test_cex_final_label_execution_queue_review_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue/review"
            "?status=pending_admin_review&limit=50&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_execution_queue_review_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue/review"
            "?status=pending_admin_review&limit=50&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_execution_queue_review_passes_filters_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "queue_status": "ready",
            "summary": {"total_cex_final_label_execution_reviews": 1},
            "rows": [],
        }

        with patch("routers.onchain.get_cex_final_label_execution_review_queue_review", return_value=expected) as review:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-execution-queue/review"
                "?status=pending_admin_review&token_symbol=TEST&market_type=cex&limit=25&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        review.assert_called_once_with("pending_admin_review", "TEST", "cex", 25, True)

    def test_cex_final_label_execution_decision_preview_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/decision-preview"
            "?cex_final_label_execution_review_id=1"
            "&proposed_decision=accept_for_future_cex_final_label_execution&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_execution_decision_preview_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/decision-preview"
            "?cex_final_label_execution_review_id=1"
            "&proposed_decision=accept_for_future_cex_final_label_execution&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_execution_decision_preview_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/decision-preview"
            "?proposed_decision=accept_for_future_cex_final_label_execution&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_execution_review_id_required")

    def test_cex_final_label_execution_decision_preview_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "preview_status": "ready_but_disabled",
            "decision_allowed": True,
        }

        with patch("routers.onchain.get_cex_final_label_execution_decision_preview", return_value=expected) as preview:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-execution-queue/decision-preview"
                "?cex_final_label_execution_review_id=1"
                "&proposed_decision=accept_for_future_cex_final_label_execution&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        preview.assert_called_once_with(1, "accept_for_future_cex_final_label_execution", True)

    def test_cex_final_label_execution_decision_apply_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/decision/apply"
            "?cex_final_label_execution_review_id=1"
            "&proposed_decision=accept_for_future_cex_final_label_execution&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_execution_decision_apply_requires_confirm_for_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/decision/apply"
            "?cex_final_label_execution_review_id=1"
            "&proposed_decision=accept_for_future_cex_final_label_execution&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "confirm_APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION_required")

    def test_cex_final_label_execution_decision_apply_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.post(
            "/api/onchain/rpc/cex-final-label-execution-queue/decision/apply"
            "?proposed_decision=accept_for_future_cex_final_label_execution&dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_execution_review_id_required")

    def test_cex_final_label_execution_decision_apply_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "apply_status": "updated",
            "updated": True,
        }

        with patch("routers.onchain.apply_cex_final_label_execution_decision", return_value=expected) as apply:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-execution-queue/decision/apply"
                "?cex_final_label_execution_review_id=1"
                "&proposed_decision=accept_for_future_cex_final_label_execution"
                "&dry_run=false&confirm=APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        apply.assert_called_once_with(
            1,
            "accept_for_future_cex_final_label_execution",
            False,
            "APPLY_CEX_FINAL_LABEL_EXECUTION_REVIEW_DECISION",
        )

    def test_cex_final_label_write_safety_checkpoint_requires_admin_token(self) -> None:
        os.environ.pop("CORE_ADMIN_TOKEN", None)

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint"
            "?cex_final_label_execution_review_id=1&dry_run=true"
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "CORE_ADMIN_TOKEN is not configured")

    def test_cex_final_label_write_safety_checkpoint_rejects_real_write(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint"
            "?cex_final_label_execution_review_id=1&dry_run=false",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "dry_run_required")

    def test_cex_final_label_write_safety_checkpoint_requires_id(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"

        response = self.client.get(
            "/api/onchain/rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint?dry_run=true",
            headers={"x-core-admin-token": "correct-token"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "cex_final_label_execution_review_id_required")

    def test_cex_final_label_write_safety_checkpoint_passes_to_service(self) -> None:
        os.environ["CORE_ADMIN_TOKEN"] = "correct-token"
        expected = {
            "ok": True,
            "checkpoint_status": "ready_but_disabled",
            "cex_final_label_execution_review_id": 1,
        }

        with patch("routers.onchain.get_cex_final_label_write_safety_checkpoint", return_value=expected) as checkpoint:
            response = self.client.post(
                "/api/onchain/rpc/cex-final-label-execution-queue/final-label-write-safety-checkpoint"
                "?cex_final_label_execution_review_id=1&dry_run=true",
                headers={"x-core-admin-token": "correct-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected)
        checkpoint.assert_called_once_with(1, True)


if __name__ == "__main__":
    unittest.main()
