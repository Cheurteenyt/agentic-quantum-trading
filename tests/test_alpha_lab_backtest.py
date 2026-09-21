from __future__ import annotations

import sys
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routers.alpha_lab import _wallet_coordination_surface, _wallet_copy_backtest_from_surface  # noqa: E402


class AlphaLabBacktestTests(unittest.TestCase):
    def test_coordination_surface_correlates_cex_and_funder_graph_without_trade_signal(self) -> None:
        result = _wallet_coordination_surface(
            wallet="0xec9ab39bffbb7f164b555b8474baa41b67739550",
            chains=["bsc"],
            cex_flow={
                "confirmed": True,
                "hint_only": False,
                "targets": [{"entity": "bitget", "source": "wallet_surface.activity"}],
            },
            funder_graph={
                "ok": True,
                "cluster_hints": [{"type": "shared_native_funder", "source": "onchain.db.transactions"}],
                "gas_distributors": [{"address": "0xfunder", "source": "onchain.db.transactions"}],
            },
            activity=[{"event_type": "transfer", "chain": "bsc"}],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "alpha_lab_existing_evidence")
        self.assertTrue(result["cex_flow_present"])
        self.assertFalse(result["cex_flow_hint_only"])
        self.assertTrue(result["funder_graph_present"])
        self.assertEqual(result["shared_funder_count"], 1)
        self.assertEqual(result["gas_distributor_count"], 1)
        self.assertIn("not identity proof or trade signals", result["source_policy"])
        hint_types = {row["type"] for row in result["coordination_hints"]}
        self.assertIn("shared_funder_with_cex_flow", hint_types)
        self.assertIn("fresh_wallet_with_cex_flow", hint_types)
        self.assertIn("gas_distributor_cluster_hint", hint_types)

    def test_copy_backtest_is_read_only_and_blocks_weak_provider_evidence(self) -> None:
        result = _wallet_copy_backtest_from_surface(
            "0xec9ab39bffbb7f164b555b8474baa41b67739550",
            {
                "activity": [
                    {
                        "event_type": "swap",
                        "direction": "out",
                        "chain": "ethereum",
                        "asset": "RAVE",
                        "amount_usd": 250.0,
                        "timestamp": "2026-04-18T00:00:00Z",
                        "tx_hash": "0xabc",
                    },
                    {
                        "event_type": "swap",
                        "direction": "out",
                        "chain": "ethereum",
                        "asset": "SCAM",
                        "amount_usd": 500.0,
                        "timestamp": "2026-04-18T00:01:00Z",
                        "tx_hash": "0xdef",
                    },
                ]
            },
            {
                "provider_health": {"ok": 0, "total": 2},
                "risk_summary": {
                    "suspicious_assets": ["SCAM"],
                    "untrusted_rows": 1,
                    "blocked_rows": 0,
                },
            },
            capital=100.0,
            max_trade_pct=0.20,
            slippage_bps=75.0,
            fee_bps=20.0,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "copy_backtest_read_only")
        self.assertEqual(result["verdict"], "blocked")
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["copy_trade_enabled"])
        self.assertFalse(result["profit_guarantee_allowed"])
        self.assertFalse(result["trade_signal_allowed"])
        self.assertEqual(len(result["copied_trades"]), 1)
        self.assertEqual(result["copied_trades"][0]["allocation"], 20.0)
        self.assertEqual(result["skipped"][0]["reason"], "suspicious_asset_blocked")
        self.assertIn("no_provider_pnl_confirmation", result["blockers"])
        self.assertIn("untrusted_profit_rows_present", result["blockers"])
        self.assertIn("replay_price_liquidity_proof_missing", result["blockers"])
        self.assertEqual(result["replay_quality"]["verdict"], "inconclusive")
        self.assertIn("entry_price_proof", result["replay_quality"]["missing_proofs"])
        self.assertIn("liquidity_at_exit", result["replay_quality"]["missing_proofs"])
        self.assertFalse(result["investment_readiness"]["execution_enabled"])
        self.assertFalse(result["investment_readiness"]["trade_signal_allowed"])
        self.assertEqual(result["investment_readiness"]["verdict"], "inconclusive")
        self.assertIn("replay:entry_price_proof", result["investment_readiness"]["missing_proofs"])
        self.assertIn("RAVE:sell_proof_missing", result["investment_readiness"]["missing_proofs"])
        self.assertLess(result["current_value"], result["capital"])

    def test_copy_backtest_requires_explicit_price_and_liquidity_proofs(self) -> None:
        result = _wallet_copy_backtest_from_surface(
            "0xec9ab39bffbb7f164b555b8474baa41b67739550",
            {
                "activity": [
                    {
                        "event_type": "swap",
                        "direction": "out",
                        "chain": "bsc",
                        "asset": "LAB",
                        "amount_usd": 100.0,
                        "timestamp": "2026-05-11T00:00:00Z",
                        "tx_hash": "0xlab",
                    }
                ]
            },
            {
                "provider_health": {"ok": 2, "total": 2},
                "risk_summary": {"suspicious_assets": [], "untrusted_rows": 0, "blocked_rows": 0},
                "intel": {
                    "pnl": [
                        {
                            "token": "LAB",
                            "chain": "bsc",
                            "missing_proofs": ["liquidity_snapshot"],
                            "source_policy": "test token source",
                        }
                    ]
                },
            },
            capital=100.0,
            max_trade_pct=0.20,
            slippage_bps=75.0,
            fee_bps=20.0,
        )

        gates = result["investment_readiness"]["required_gates"]
        self.assertEqual(result["replay_quality"]["verdict"], "inconclusive")
        self.assertFalse(gates["entry_price_proof"])
        self.assertFalse(gates["exit_price_proof"])
        self.assertFalse(gates["liquidity_at_entry"])
        self.assertFalse(gates["liquidity_at_exit"])
        self.assertTrue(gates["slippage_model"])
        self.assertTrue(gates["fee_model"])
        self.assertFalse(gates["liquidity_snapshot_ok"])
        self.assertIn("LAB:liquidity_snapshot_missing", result["investment_readiness"]["missing_proofs"])

    def test_copy_backtest_accepts_explicit_event_market_proof_contract(self) -> None:
        result = _wallet_copy_backtest_from_surface(
            "0xec9ab39bffbb7f164b555b8474baa41b67739550",
            {
                "activity": [
                    {
                        "event_type": "swap",
                        "direction": "out",
                        "chain": "bsc",
                        "asset": "LAB",
                        "amount_usd": 100.0,
                        "timestamp": "2026-05-11T00:00:00Z",
                        "tx_hash": "0xproof",
                        "market_provider": "local_exact_swap_cache",
                        "dex": "pancakeswap",
                        "pair_address": "0xpair",
                        "entry_price_usd": 1.0,
                        "exit_price_usd": 1.2,
                        "entry_liquidity_usd": 250000.0,
                        "exit_liquidity_usd": 300000.0,
                    }
                ]
            },
            {
                "provider_health": {"ok": 2, "total": 2},
                "risk_summary": {"suspicious_assets": [], "untrusted_rows": 0, "blocked_rows": 0},
                "intel": {
                    "pnl": [
                        {
                            "token": "LAB",
                            "chain": "bsc",
                            "copy_allowed": True,
                            "missing_proofs": [],
                            "source_policy": "test token source",
                        }
                    ]
                },
            },
            capital=100.0,
            max_trade_pct=0.20,
            slippage_bps=75.0,
            fee_bps=20.0,
        )

        gates = result["replay_quality"]["proof_gates"]
        self.assertTrue(gates["entry_price_proof"])
        self.assertTrue(gates["exit_price_proof"])
        self.assertFalse(gates["liquidity_at_entry"])
        self.assertFalse(gates["liquidity_at_exit"])
        self.assertIn("liquidity_at_entry", result["replay_quality"]["missing_proofs"])
        self.assertTrue(result["replay_quality"]["price_proxy_hint"])
        self.assertEqual(result["copied_trades"][0]["market_proof"]["provider"], "local_exact_swap_cache")
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["trade_signal_allowed"])

    def test_copy_backtest_accepts_explicit_pool_snapshot_for_liquidity_gates(self) -> None:
        result = _wallet_copy_backtest_from_surface(
            "0xec9ab39bffbb7f164b555b8474baa41b67739550",
            {
                "activity": [
                    {
                        "event_type": "swap",
                        "direction": "out",
                        "chain": "bsc",
                        "asset": "LAB",
                        "amount_usd": 100.0,
                        "timestamp": "2026-05-11T00:00:00Z",
                        "tx_hash": "0xpoolproof",
                        "market_provider": "local_exact_swap_cache",
                        "pool_snapshot_provider": "local_pool_reserve_snapshot",
                        "dex": "pancakeswap",
                        "pair_address": "0xpair",
                        "block_number": 123456,
                        "entry_price_usd": 1.0,
                        "exit_price_usd": 1.2,
                        "entry_liquidity_usd": 250000.0,
                        "exit_liquidity_usd": 300000.0,
                        "reserve0": 100000.0,
                        "reserve1": 500.0,
                    }
                ]
            },
            {
                "provider_health": {"ok": 2, "total": 2},
                "risk_summary": {"suspicious_assets": [], "untrusted_rows": 0, "blocked_rows": 0},
                "intel": {"pnl": [{"token": "LAB", "chain": "bsc", "copy_allowed": True, "missing_proofs": [], "source_policy": "test"}]},
            },
            capital=100.0,
        )

        gates = result["replay_quality"]["proof_gates"]
        self.assertTrue(gates["liquidity_at_entry"])
        self.assertTrue(gates["liquidity_at_exit"])
        snapshot = result["copied_trades"][0]["market_proof"]["pool_snapshot"]
        self.assertEqual(snapshot["snapshot_quality"], "historical_reserves_and_liquidity")
        self.assertFalse(snapshot["liquidity_proxy_hint"])

    def test_copy_backtest_maps_local_exact_swap_context_as_proxy_only(self) -> None:
        local_context = {
            "market_provider": "local_exact_swap_cache",
            "chain": "bsc",
            "timestamp": 1778457600,
            "tx_hash": "0xlocal",
            "dex": "pancakeswap",
            "pair_address": "0xpool",
            "block_number": 987,
            "token_in": "0xtoken",
            "token_out": "0xwbnb",
            "amount_in": 100.0,
            "amount_out": 1.0,
            "amount_usd": 200.0,
            "token_identity_quality": "exact_pair_log_direction",
            "local_price_proxy": {
                "provider": "local_swaps.amount_usd_over_token_amount",
                "candidates": [
                    {
                        "token": "0xtoken",
                        "price_proxy_usd": 2.0,
                        "price_quality": "local_swap_timestamped_proxy",
                        "distance_blocks": 0,
                        "missing_proofs": ["oracle_historical_price"],
                    }
                ],
                "source_policy": "proxy only",
            },
            "pool_snapshot": {
                "pool_snapshot_provider": "mock_rpc",
                "pool_address": "0xpool",
                "chain": "bsc",
                "block_number": 987,
                "reserve0": 1000.0,
                "reserve1": 4.0,
                "liquidity_usd": None,
                "snapshot_quality": "historical_reserves_normalized",
                "liquidity_proxy_hint": True,
                "missing_proofs": ["token_price_usd", "pool_liquidity_usd"],
                "source_policy": "historical reserves only; no timestamped token prices",
            },
        }
        funder_graph = {
            "ok": True,
            "provider": "local_onchain_db",
            "wallet": "0xec9ab39bffbb7f164b555b8474baa41b67739550",
            "chain": "bsc",
            "funders": [{"address": "0xfunder", "source": "onchain.db.transactions"}],
            "gas_distributors": [{"address": "0xfunder", "recipient_count": 2}],
            "linked_wallet_count": 2,
            "cluster_hints": [{"type": "shared_native_funder", "source": "onchain.db.transactions"}],
            "missing_proofs": [],
            "source_policy": "test local graph",
        }

        with (
            patch("routers.alpha_lab._local_exact_swap_context", return_value=local_context),
            patch("routers.alpha_lab._wallet_funder_graph_readiness", return_value=funder_graph),
        ):
            result = _wallet_copy_backtest_from_surface(
                "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                {
                    "activity": [
                        {
                            "event_type": "swap",
                            "direction": "out",
                            "chain": "bsc",
                            "asset": "LAB",
                            "amount_usd": 100.0,
                            "timestamp": "2026-05-11T00:00:00Z",
                            "tx_hash": "0xlocal",
                        }
                    ]
                },
                {
                    "provider_health": {"ok": 2, "total": 2},
                    "risk_summary": {"suspicious_assets": [], "untrusted_rows": 0, "blocked_rows": 0},
                },
                capital=100.0,
                max_trade_pct=0.20,
                slippage_bps=75.0,
                fee_bps=20.0,
            )

        proof = result["copied_trades"][0]["market_proof"]
        self.assertEqual(proof["provider"], "local_exact_swap_cache")
        self.assertEqual(proof["pair_address"], "0xpool")
        self.assertEqual(proof["pool_snapshot"]["snapshot_quality"], "historical_reserves_only")
        self.assertTrue(proof["pool_snapshot"]["liquidity_proxy_hint"])
        self.assertIn("pool_snapshot:token_price_usd", proof["missing_proofs"])
        self.assertEqual(proof["price_proofs"][0]["price_quality"], "local_swap_timestamped_proxy")
        self.assertEqual(proof["price_proofs"][0]["distance_blocks"], 0)
        self.assertIn("price_proof:oracle_historical_price", proof["missing_proofs"])
        self.assertIn("pool_snapshot:pool_liquidity_usd", result["replay_quality"]["missing_proofs"])
        self.assertIn("replay:pool_snapshot:token_price_usd", result["investment_readiness"]["missing_proofs"])
        self.assertIn("replay:price_proof:oracle_historical_price", result["investment_readiness"]["missing_proofs"])
        self.assertEqual(proof["token_identity_quality"], "exact_pair_log_direction")
        self.assertEqual(proof["local_price_proxy"]["candidates"][0]["price_proxy_usd"], 2.0)
        self.assertTrue(result["replay_quality"]["price_proxy_hint"])
        self.assertFalse(result["replay_quality"]["proof_gates"]["entry_price_proof"])
        self.assertFalse(result["replay_quality"]["proof_gates"]["liquidity_at_entry"])
        self.assertEqual(result["investment_readiness"]["verdict"], "inconclusive")
        manipulation = result["manipulation_readiness"]
        self.assertEqual(manipulation["verdict"], "inconclusive")
        self.assertTrue(manipulation["evidence_present"]["pool_reserve_snapshot"])
        self.assertTrue(manipulation["evidence_present"]["local_swap_timestamped_proxy"])
        self.assertTrue(manipulation["evidence_present"]["funder_graph_surface"])
        self.assertIn("shared_native_funder", manipulation["risk_factors"])
        self.assertIn("cex_flow_or_hint", manipulation["missing_proofs"])
        self.assertIn("not a trade signal", manipulation["source_policy"])


if __name__ == "__main__":
    unittest.main()
