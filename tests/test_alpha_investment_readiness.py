from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routers.alpha_lab import (  # noqa: E402
    _wallet_cex_flow_gate,
    _wallet_investment_readiness,
    _wallet_source_freshness,
    _wallet_token_risk_watchlist,
)


class AlphaInvestmentReadinessTests(unittest.TestCase):
    def test_missing_proofs_keep_client_investment_disabled(self) -> None:
        readiness = _wallet_investment_readiness(
            mode="watch_only",
            readiness_score=25,
            blockers=["Wallet is not a proven copy candidate yet."],
            source_trace={"probe": "alpha_wallets.probe_wallet_candidate"},
            data_quality={"source_freshness": "no_recent_sample", "token_sellability": "needs_token_level_proof"},
            token_risk_watchlist=[{
                "asset": "LAB",
                "risk_flag": "needs_sellability_proof",
                "copy_allowed": None,
                "missing_proofs": ["successful_sell_proof", "liquidity_snapshot"],
            }],
            scorecard={"providers_ok": 0, "estimated_value": None, "roi_pct": None},
        )

        self.assertEqual(readiness["verdict"], "inconclusive")
        self.assertFalse(readiness["client_investment_enabled"])
        self.assertFalse(readiness["execution_enabled"])
        self.assertFalse(readiness["copy_trade_enabled"])
        self.assertFalse(readiness["profit_guarantee_allowed"])
        self.assertFalse(readiness["trade_signal_allowed"])
        self.assertIn("token_sellability_contract", readiness["missing_proofs"])
        self.assertIn("LAB:sell_proof_missing", readiness["missing_proofs"])
        self.assertIn("LAB:liquidity_snapshot_missing", readiness["missing_proofs"])
        self.assertFalse(readiness["required_gates"]["token_sell_proof_ok"])
        self.assertFalse(readiness["required_gates"]["liquidity_snapshot_ok"])

    def test_clean_manual_review_still_does_not_enable_client_execution(self) -> None:
        freshness = {
            "latest_seen": datetime.now(timezone.utc).isoformat(),
            "age_seconds": 0,
            "source": "wallet_surface.activity",
            "provider": "alpha_wallets.get_wallet_surface",
            "chain": "ethereum",
            "tx_hash": "0xabc",
            "freshness_policy": "fresh_24h",
        }
        cex_flow = {"status": "confirmed_token_transfer", "confirmed": True}
        readiness = _wallet_investment_readiness(
            mode="manual_review_ready",
            readiness_score=82,
            blockers=[],
            source_trace={"probe": "alpha_wallets.probe_wallet_candidate", "source_freshness": freshness, "cex_flow_gate": cex_flow},
            data_quality={"source_freshness": "fresh_24h", "source_freshness_detail": freshness, "cex_flow_gate": cex_flow, "token_sellability": "verified"},
            token_risk_watchlist=[{"asset": "USDC", "risk_flag": "major_token", "copy_allowed": True, "source_policy": "trusted stablecoin source trace"}],
            scorecard={"providers_ok": 2, "estimated_value": 103.4, "roi_pct": 3.4},
        )

        self.assertEqual(readiness["status"], "manual_review_only")
        self.assertEqual(readiness["verdict"], "manual_review_only")
        self.assertTrue(readiness["manual_review_allowed"])
        self.assertFalse(readiness["client_investment_enabled"])
        self.assertFalse(readiness["execution_enabled"])
        self.assertFalse(readiness["trade_signal_allowed"])
        self.assertEqual(readiness["missing_proofs"], [])
        self.assertTrue(readiness["required_gates"]["confirmed_cex_flow"])
        self.assertTrue(readiness["required_gates"]["token_sell_proof_ok"])
        self.assertTrue(readiness["required_gates"]["liquidity_snapshot_ok"])

    def test_critical_token_blocker_overrides_high_score(self) -> None:
        readiness = _wallet_investment_readiness(
            mode="manual_review_ready",
            readiness_score=90,
            blockers=[],
            source_trace={"probe": "alpha_wallets.probe_wallet_candidate"},
            data_quality={"source_freshness": "fresh_sample", "token_sellability": "verified"},
            token_risk_watchlist=[{"asset": "SCAM", "risk_flag": "honeypot_confirmed", "block_trade": True}],
            scorecard={"providers_ok": 3, "estimated_value": 150.0, "roi_pct": 50.0},
        )

        self.assertEqual(readiness["status"], "not_ready")
        self.assertEqual(readiness["verdict"], "inconclusive")
        self.assertFalse(readiness["manual_review_allowed"])
        self.assertFalse(readiness["client_investment_enabled"])
        self.assertIn("SCAM:honeypot_confirmed", readiness["critical_blockers"])

    def test_token_watchlist_uses_real_token_risk_result_fields(self) -> None:
        watchlist = _wallet_token_risk_watchlist({
            "risk_summary": {"suspicious_assets": []},
            "asset_focus": [{"asset": "LAB", "chain": "bsc", "events": 4, "amount_usd": 1200}],
            "intel": {
                "pnl": [
                    {
                        "token": "LAB",
                        "chain": "bsc",
                        "token_address": "0x1111111111111111111111111111111111111111",
                        "risk_score": 66,
                        "block_trade": True,
                        "profit_integrity": "not_trustworthy",
                        "flags": [{"code": "honeypot_confirmed", "severity": "critical", "points": 48, "detail": "blocked"}],
                        "missing_proofs": ["successful_sell_proof"],
                        "source_policy": "wallet_pnl_provider:test",
                        "source_trace": {"honeypot_api": "ok"},
                    }
                ]
            },
        })

        self.assertEqual(len(watchlist), 1)
        row = watchlist[0]
        self.assertEqual(row["asset"], "LAB")
        self.assertEqual(row["risk_flag"], "honeypot_confirmed")
        self.assertTrue(row["block_trade"])
        self.assertFalse(row["copy_allowed"])
        self.assertEqual(row["token_address"], "0x1111111111111111111111111111111111111111")
        self.assertIn("successful_sell_proof", row["missing_proofs"])
        self.assertEqual(row["source_trace"]["honeypot_api"], "ok")

        readiness = _wallet_investment_readiness(
            mode="manual_review_ready",
            readiness_score=90,
            blockers=[],
            source_trace={"probe": "alpha_wallets.probe_wallet_candidate"},
            data_quality={"source_freshness": "fresh_sample", "token_sellability": "verified"},
            token_risk_watchlist=watchlist,
            scorecard={"providers_ok": 2, "estimated_value": 180.0, "roi_pct": 80.0},
        )
        self.assertEqual(readiness["status"], "not_ready")
        self.assertEqual(readiness["verdict"], "inconclusive")
        self.assertIn("LAB:honeypot_confirmed", readiness["critical_blockers"])
        self.assertIn("LAB:successful_sell_proof", readiness["missing_proofs"])
        self.assertIn("LAB:sell_proof_missing", readiness["missing_proofs"])
        self.assertFalse(readiness["required_gates"]["token_sell_proof_ok"])

    def test_source_freshness_extracts_latest_timestamped_flow(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        freshness = _wallet_source_freshness({
            "activity": [
                {
                    "timestamp": now,
                    "tx_hash": "0xfresh",
                    "chain": "bsc",
                    "event_type": "transfer",
                    "provider": "blockscout",
                }
            ]
        })

        self.assertEqual(freshness["latest_seen"], now)
        self.assertEqual(freshness["tx_hash"], "0xfresh")
        self.assertEqual(freshness["chain"], "bsc")
        self.assertEqual(freshness["provider"], "blockscout")
        self.assertEqual(freshness["freshness_policy"], "fresh_24h")
        self.assertIsInstance(freshness["age_seconds"], int)

    def test_cex_flow_distinguishes_confirmed_token_transfer_from_hint(self) -> None:
        confirmed = _wallet_cex_flow_gate({
            "activity": [
                {
                    "event_type": "transfer",
                    "direction": "outflow",
                    "chain": "bsc",
                    "asset": "LAB",
                    "tx_hash": "0xdeposit",
                    "counterparty": {"label": "Bitget Deposit", "address": "0xcex"},
                }
            ]
        })

        self.assertTrue(confirmed["confirmed"])
        self.assertEqual(confirmed["status"], "confirmed_token_transfer")
        self.assertEqual(confirmed["token_transfer_count"], 1)
        self.assertEqual(confirmed["targets"][0]["flow_type"], "token_transfer_to_cex")

        hint = _wallet_cex_flow_gate({
            "counterparties": [
                {"label": "Binance Hot Wallet", "latest_tx": "0xhint", "latest_chain": "ethereum", "assets": ["ETH"]}
            ]
        })

        self.assertFalse(hint["confirmed"])
        self.assertTrue(hint["hint_only"])
        self.assertEqual(hint["status"], "heuristic_hint")

    def test_stale_or_unconfirmed_flow_keeps_readiness_inconclusive(self) -> None:
        freshness = {
            "latest_seen": "2024-01-01T00:00:00Z",
            "age_seconds": 999_999_999,
            "source": "wallet_surface.activity",
            "provider": "alpha_wallets.get_wallet_surface",
            "chain": "ethereum",
            "tx_hash": "0xold",
            "freshness_policy": "stale_over_7d",
        }
        readiness = _wallet_investment_readiness(
            mode="manual_review_ready",
            readiness_score=90,
            blockers=[],
            source_trace={"source_freshness": freshness, "cex_flow_gate": {"status": "heuristic_hint", "hint_only": True}},
            data_quality={
                "source_freshness": "stale_over_7d",
                "source_freshness_detail": freshness,
                "cex_flow_gate": {"status": "heuristic_hint", "hint_only": True},
                "token_sellability": "verified",
            },
            token_risk_watchlist=[{"asset": "USDC", "copy_allowed": True, "source_policy": "test"}],
            scorecard={"providers_ok": 2, "estimated_value": 120.0, "roi_pct": 20.0},
        )

        self.assertEqual(readiness["verdict"], "inconclusive")
        self.assertIn("fresh_timestamped_flow_sample", readiness["missing_proofs"])
        self.assertIn("cex_flow_confirmation", readiness["missing_proofs"])
        self.assertFalse(readiness["required_gates"]["freshness"])
        self.assertFalse(readiness["required_gates"]["confirmed_cex_flow"])

    def test_liquidity_snapshot_missing_has_explicit_gate(self) -> None:
        freshness = {
            "latest_seen": datetime.now(timezone.utc).isoformat(),
            "age_seconds": 0,
            "source": "wallet_surface.activity",
            "provider": "alpha_wallets.get_wallet_surface",
            "chain": "bsc",
            "tx_hash": "0xfresh",
            "freshness_policy": "fresh_24h",
        }
        cex_flow = {"status": "confirmed_token_transfer", "confirmed": True}
        readiness = _wallet_investment_readiness(
            mode="manual_review_ready",
            readiness_score=88,
            blockers=[],
            source_trace={"source_freshness": freshness, "cex_flow_gate": cex_flow},
            data_quality={
                "source_freshness": "fresh_24h",
                "source_freshness_detail": freshness,
                "cex_flow_gate": cex_flow,
                "token_sellability": "verified",
            },
            token_risk_watchlist=[
                {
                    "asset": "LAB",
                    "copy_allowed": True,
                    "source_policy": "test",
                    "missing_proofs": ["liquidity_snapshot"],
                }
            ],
            scorecard={"providers_ok": 2, "estimated_value": 110.0, "roi_pct": 10.0},
        )

        self.assertEqual(readiness["verdict"], "inconclusive")
        self.assertIn("LAB:liquidity_snapshot", readiness["missing_proofs"])
        self.assertIn("LAB:liquidity_snapshot_missing", readiness["missing_proofs"])
        self.assertFalse(readiness["required_gates"]["liquidity_snapshot_ok"])
        self.assertTrue(readiness["required_gates"]["token_sell_proof_ok"])


if __name__ == "__main__":
    unittest.main()
