from __future__ import annotations

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
from services.onchain_engine import (  # noqa: E402
    get_local_swap_timestamped_price_proxy,
    get_pool_reserve_snapshot,
    get_timestamped_token_price_hint,
)


def _word(value: int) -> str:
    return f"{value:064x}"


class OnchainPoolReserveSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        onchain_engine._POOL_RESERVE_SNAPSHOT_CACHE.clear()
        onchain_engine._PRICE_CACHE.clear()

    def test_invalid_pool_snapshot_request_is_non_executable_failure(self) -> None:
        result = get_pool_reserve_snapshot("solana", "not-a-pool", None)

        self.assertFalse(result["ok"])
        self.assertEqual(result["snapshot_quality"], "invalid_request")
        self.assertIn("supported_evm_chain", result["missing_proofs"])
        self.assertIn("pool_address", result["missing_proofs"])
        self.assertIn("historical_block_number", result["missing_proofs"])
        self.assertIsNone(result["liquidity_usd"])

    def test_rpc_failure_reports_historical_block_call_missing(self) -> None:
        with patch("services.onchain_engine._rpc_evm_chain", side_effect=RuntimeError("archive unavailable")):
            result = get_pool_reserve_snapshot(
                "bsc",
                "0x1111111111111111111111111111111111111111",
                123456,
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["snapshot_quality"], "rpc_failed")
        self.assertIn("historical_block_call", result["missing_proofs"])
        self.assertIsNone(result["reserve0_raw"])
        self.assertIsNone(result["liquidity_usd"])

    def test_successful_snapshot_returns_reserves_without_inventing_liquidity(self) -> None:
        token0 = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        token1 = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        raw = "0x" + _word(5 * 10**18) + _word(2 * 10**18) + _word(123)
        major_tokens = {
            "bsc": {
                token0: {"decimals": 18},
                token1: {"decimals": 18},
            }
        }

        with patch("services.onchain_engine._rpc_evm_chain", return_value=(raw, "mock_rpc")), patch(
            "services.onchain_engine._resolve_pair_tokens",
            return_value=(token0, token1, "mock_pair_tokens"),
        ), patch("services.onchain_engine._MAJOR_TOKENS", major_tokens):
            result = get_pool_reserve_snapshot(
                "bsc",
                "0x1111111111111111111111111111111111111111",
                123456,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "mock_rpc")
        self.assertEqual(result["snapshot_quality"], "historical_reserves_normalized")
        self.assertEqual(result["reserve0_raw"], str(5 * 10**18))
        self.assertEqual(result["reserve1_raw"], str(2 * 10**18))
        self.assertEqual(result["reserve0"], 5.0)
        self.assertEqual(result["reserve1"], 2.0)
        self.assertIsNone(result["liquidity_usd"])
        self.assertIn("token_price_usd", result["missing_proofs"])

    def test_snapshot_cache_prevents_repeated_rpc_calls(self) -> None:
        raw = "0x" + _word(1) + _word(2) + _word(3)
        with patch("services.onchain_engine._rpc_evm_chain", return_value=(raw, "mock_rpc")) as rpc_call, patch(
            "services.onchain_engine._resolve_pair_tokens",
            return_value=("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "mock"),
        ):
            first = get_pool_reserve_snapshot("bsc", "0x2222222222222222222222222222222222222222", 999)
            second = get_pool_reserve_snapshot("bsc", "0x2222222222222222222222222222222222222222", 999)

        self.assertTrue(first["ok"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(rpc_call.call_count, 1)

    def test_timestamped_price_hint_exposes_current_price_as_non_historical(self) -> None:
        token = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        major_tokens = {"bsc": {token: {"coin_id": "test-token", "decimals": 18}}}
        with patch("services.onchain_engine._MAJOR_TOKENS", major_tokens), patch(
            "services.onchain_engine._get_coin_prices",
            return_value={"test-token": 1.23},
        ):
            result = get_timestamped_token_price_hint("bsc", token, 1778457600, 123456)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "coingecko_current_price_cache")
        self.assertEqual(result["price_usd"], 1.23)
        self.assertEqual(result["price_quality"], "current_price_hint")
        self.assertIn("timestamped_token_price", result["missing_proofs"])

    def test_timestamped_price_hint_never_invents_unknown_token_price(self) -> None:
        result = get_timestamped_token_price_hint(
            "bsc",
            "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            1778457600,
            123456,
        )

        self.assertFalse(result["ok"])
        self.assertIsNone(result["price_usd"])
        self.assertIn("token_coin_id", result["missing_proofs"])
        self.assertIn("timestamped_token_price", result["missing_proofs"])

    def test_local_swap_timestamped_price_proxy_uses_nearest_local_swap_only(self) -> None:
        token = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            with patch("services.onchain_engine.DB_PATH", db_path):
                onchain_engine._init_db()
                conn = onchain_engine._get_db()
                try:
                    conn.execute(
                        """
                        INSERT INTO swaps (
                            tx_hash, chain, block_number, timestamp, wallet, dex,
                            token_in, token_out, amount_in, amount_out, amount_usd,
                            pool, token_identity_quality
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "0xswap",
                            "bsc",
                            1001,
                            1778457600,
                            "0xwallet",
                            "pancakeswap",
                            token,
                            "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                            10.0,
                            1.0,
                            25.0,
                            "0xpool",
                            "exact_pair_log_direction",
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

                result = get_local_swap_timestamped_price_proxy("bsc", token, 1000, 1778457600)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "local_swaps")
        self.assertEqual(result["price_quality"], "local_swap_timestamped_proxy")
        self.assertEqual(result["price_usd"], 2.5)
        self.assertEqual(result["distance_blocks"], 1)
        self.assertEqual(result["tx_hash"], "0xswap")
        self.assertIn("oracle_historical_price", result["missing_proofs"])

    def test_timestamped_price_hint_prefers_local_swap_for_unknown_token(self) -> None:
        token = "0xcccccccccccccccccccccccccccccccccccccccc"
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "onchain.db"
            with patch("services.onchain_engine.DB_PATH", db_path):
                onchain_engine._init_db()
                conn = onchain_engine._get_db()
                try:
                    conn.execute(
                        """
                        INSERT INTO swaps (
                            tx_hash, chain, block_number, timestamp, wallet, dex,
                            token_in, token_out, amount_in, amount_out, amount_usd,
                            pool, token_identity_quality
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "0xproxyswap",
                            "bsc",
                            5000,
                            1778457600,
                            "0xwallet",
                            "pancakeswap",
                            "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                            token,
                            1.0,
                            4.0,
                            20.0,
                            "0xpool",
                            "exact_pair_log_direction",
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

                result = get_timestamped_token_price_hint("bsc", token, 1778457600, 5000)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "local_swaps")
        self.assertEqual(result["price_quality"], "local_swap_timestamped_proxy")
        self.assertEqual(result["price_usd"], 5.0)
        self.assertIn("oracle_historical_price", result["missing_proofs"])


if __name__ == "__main__":
    unittest.main()
