from __future__ import annotations

import sys
import unittest
import asyncio
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import services.alpha_wallets as alpha_wallets  # noqa: E402
import routers.alpha_lab as alpha_lab_router  # noqa: E402


class AlphaWalletDiscoveryTests(unittest.TestCase):
    def test_cielo_normalizer_preserves_actor_from_wallet_field(self) -> None:
        event = alpha_wallets._normalize_cielo_event(
            {
                "wallet": "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                "wallet_label": "test wallet",
                "tx_type": "swap",
                "chain": "ethereum",
                "token0_symbol": "RAVE",
                "token0_amount_usd": "1250.50",
                "first_interaction": True,
                "hash": "0xabc",
                "timestamp": "2026-05-10T12:00:00Z",
            }
        )

        self.assertEqual(event["actor"], "0xec9ab39bffbb7f164b555b8474baa41b67739550")
        self.assertEqual(event["wallet"], "0xec9ab39bffbb7f164b555b8474baa41b67739550")
        self.assertEqual(event["event_type"], "swap")
        self.assertEqual(event["source_event_id"], "0xabc")
        self.assertEqual(event["asset"], "RAVE")
        self.assertEqual(event["amount_usd"], 1250.5)

    def test_discovery_uses_wallet_fallback_when_actor_is_missing(self) -> None:
        original_get_wallet_feed = alpha_wallets.get_wallet_feed

        def fake_feed(*args, **kwargs):
            return {
                "ok": True,
                "events": [
                    {
                        "wallet": "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                        "wallet_label": "test wallet",
                        "event_type": "swap",
                        "chain": "ethereum",
                        "asset": "RAVE",
                        "amount_usd": 2500,
                        "first_interaction": True,
                        "timestamp": "2026-05-10T12:00:00Z",
                        "source_event_id": "0xabc",
                    }
                ],
                "dedupe": {"input_count": 1, "unique_count": 1, "duplicate_count": 0},
            }

        alpha_wallets.get_wallet_feed = fake_feed
        try:
            result = alpha_wallets.get_wallet_discovery(limit=5, feed_limit=5, use_cache=False)
        finally:
            alpha_wallets.get_wallet_feed = original_get_wallet_feed

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["wallet"], "0xec9ab39bffbb7f164b555b8474baa41b67739550")
        self.assertEqual(candidate["events"], 1)
        self.assertEqual(candidate["swaps"], 1)
        self.assertEqual(candidate["chains"], ["ethereum"])
        self.assertEqual(candidate["assets"], ["RAVE"])
        self.assertEqual(candidate["latest_tx"], "0xabc")
        self.assertEqual(candidate["latest_chain"], "ethereum")

    def test_discovery_keeps_latest_tx_chain_when_wallet_has_multiple_chains(self) -> None:
        original_get_wallet_feed = alpha_wallets.get_wallet_feed

        def fake_feed(*args, **kwargs):
            return {
                "ok": True,
                "events": [
                    {
                        "wallet": "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                        "event_type": "swap",
                        "chain": "bsc",
                        "asset": "BNB",
                        "amount_usd": 100,
                        "timestamp": "2026-05-10T11:00:00Z",
                        "source_event_id": "0xbsc",
                    },
                    {
                        "wallet": "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                        "event_type": "swap",
                        "chain": "ethereum",
                        "asset": "RAVE",
                        "amount_usd": 2500,
                        "timestamp": "2026-05-10T12:00:00Z",
                        "source_event_id": "0xeth",
                    },
                ],
                "dedupe": {"input_count": 2, "unique_count": 2, "duplicate_count": 0},
            }

        alpha_wallets.get_wallet_feed = fake_feed
        try:
            result = alpha_wallets.get_wallet_discovery(limit=5, feed_limit=5, use_cache=False)
        finally:
            alpha_wallets.get_wallet_feed = original_get_wallet_feed

        candidate = result["candidates"][0]
        self.assertEqual(candidate["chains"], ["bsc", "ethereum"])
        self.assertEqual(candidate["latest_tx"], "0xeth")
        self.assertEqual(candidate["latest_chain"], "ethereum")

    def test_discovery_route_honors_cache_flag(self) -> None:
        original_get_wallet_discovery = alpha_wallets.get_wallet_discovery
        observed: dict[str, object] = {}

        def fake_discovery(**kwargs):
            observed.update(kwargs)
            return {"ok": True, "count": 0, "candidates": [], "feed": {}}

        alpha_wallets.get_wallet_discovery = fake_discovery
        try:
            result = asyncio.run(alpha_lab_router._wallet_discovery(cache="false"))
        finally:
            alpha_wallets.get_wallet_discovery = original_get_wallet_discovery

        self.assertTrue(result["ok"])
        self.assertIs(observed["use_cache"], False)

    def test_wallet_surface_keeps_latest_chain_for_counterparty_and_venue(self) -> None:
        original_get_wallet_feed = alpha_wallets.get_wallet_feed
        wallet = "0xec9ab39bffbb7f164b555b8474baa41b67739550"
        counterparty = "0x1111111111111111111111111111111111111111"

        def fake_feed(*args, **kwargs):
            return {
                "ok": True,
                "events": [
                    {
                        "event_type": "transfer",
                        "chain": "bsc",
                        "asset": "BNB",
                        "amount_usd": 100,
                        "timestamp": "2026-05-10T11:00:00Z",
                        "tx_hash": "0xbsc",
                        "from": wallet,
                        "to": counterparty,
                    },
                    {
                        "event_type": "transfer",
                        "chain": "ethereum",
                        "asset": "RAVE",
                        "amount_usd": 200,
                        "timestamp": "2026-05-10T12:00:00Z",
                        "tx_hash": "0xeth",
                        "from": wallet,
                        "to": counterparty,
                    },
                    {
                        "event_type": "swap",
                        "chain": "bsc",
                        "asset": "BNB",
                        "amount_usd": 100,
                        "timestamp": "2026-05-10T11:30:00Z",
                        "tx_hash": "0xvenuebsc",
                        "dex": "PancakeSwap",
                    },
                    {
                        "event_type": "swap",
                        "chain": "ethereum",
                        "asset": "RAVE",
                        "amount_usd": 300,
                        "timestamp": "2026-05-10T12:30:00Z",
                        "tx_hash": "0xvenueeth",
                        "dex": "PancakeSwap",
                    },
                ],
                "dedupe": {"input_count": 4, "unique_count": 4, "duplicate_count": 0},
            }

        alpha_wallets.get_wallet_feed = fake_feed
        try:
            surface = alpha_wallets.get_wallet_surface(wallet, use_cache=False)
            graph = alpha_wallets.get_wallet_identity_graph(wallet, use_cache=False)
        finally:
            alpha_wallets.get_wallet_feed = original_get_wallet_feed

        direct = next(item for item in surface["counterparties"] if item["address"] == counterparty)
        venue = next(item for item in surface["venues"] if item["name"] == "PancakeSwap")
        self.assertEqual(direct["chains"], ["bsc", "ethereum"])
        self.assertEqual(direct["latest_tx"], "0xeth")
        self.assertEqual(direct["latest_chain"], "ethereum")
        self.assertEqual(venue["chains"], ["bsc", "ethereum"])
        self.assertEqual(venue["latest_tx"], "0xvenueeth")
        self.assertEqual(venue["latest_chain"], "ethereum")

        direct_edge = next(edge for edge in graph["edges"] if edge.get("target") == f"address:{counterparty}")
        venue_edge = next(edge for edge in graph["edges"] if edge.get("target") == "venue:pancakeswap")
        self.assertEqual(direct_edge["latest_chain"], "ethereum")
        self.assertEqual(venue_edge["latest_chain"], "ethereum")


if __name__ == "__main__":
    unittest.main()
