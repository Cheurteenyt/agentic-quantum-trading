from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.onchain.aster import dexscreener_enrichment_layer as layer  # noqa: E402


TOKEN = "0x1111111111111111111111111111111111111111"
POOL = "0x2222222222222222222222222222222222222222"


class DexScreenerEnrichmentLayerTests(unittest.TestCase):
    def test_preview_scores_suspicious_market_without_writes(self) -> None:
        candidates = [
            {
                "chain": "bsc",
                "pool_address": POOL,
                "token_address": TOKEN,
                "behavioral_score": 82,
                "token_status": "resolved",
            }
        ]
        payload = [
            {
                "pairAddress": POOL,
                "dexId": "pancakeswap",
                "volume": {"h24": 40000},
                "liquidity": {"usd": 10000},
                "txns": {"h24": {"buys": 90, "sells": 10}},
                "priceChange": {"h24": 12.5},
            }
        ]
        with patch.object(layer, "_behavioral_candidates", return_value=candidates), patch.object(
            layer,
            "_dexscreener_token_request",
            return_value={"status": "ok", "url": "https://example.test", "payload": payload},
        ):
            preview = layer.get_dexscreener_enrichment_preview()

        self.assertTrue(preview["ok"])
        self.assertEqual(preview["http_calls_attempted"], 1)
        self.assertFalse(preview["would_write"])
        self.assertFalse(preview["would_call_scrapling"])
        self.assertFalse(preview["would_call_rpc"])
        row = preview["enrichment_rows"][0]
        self.assertEqual(row["dexscreener_status"], "ok")
        self.assertEqual(row["volume_24h_usd"], 40000)
        self.assertEqual(row["liquidity_usd"], 10000)
        self.assertEqual(row["txns_24h_buys"], 90)
        self.assertEqual(row["txns_24h_sells"], 10)
        self.assertTrue(row["is_suspicious"])

    def test_preview_treats_404_and_429_as_non_blocking_statuses(self) -> None:
        candidates = [
            {"chain": "bsc", "pool_address": POOL, "token_address": TOKEN, "behavioral_score": 75},
            {"chain": "bsc", "pool_address": POOL, "token_address": TOKEN, "behavioral_score": 75},
        ]
        responses = [
            {"status": "not_found", "url": "https://example.test/a", "http_status": 404},
            {"status": "rate_limited", "url": "https://example.test/b", "http_status": 429},
        ]
        with patch.object(layer, "_behavioral_candidates", return_value=candidates), patch.object(
            layer,
            "_dexscreener_token_request",
            side_effect=responses,
        ):
            preview = layer.get_dexscreener_enrichment_preview()
            blocked = layer.get_dexscreener_enrichment_preview(dry_run=False)

        statuses = [row["dexscreener_status"] for row in preview["enrichment_rows"]]
        self.assertEqual(statuses, ["not_found", "rate_limited"])
        self.assertEqual(preview["blockers"], [])
        self.assertFalse(any(row["is_suspicious"] for row in preview["enrichment_rows"]))
        self.assertFalse(preview["would_create_client_signal"])
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["blockers"], ["dry_run_required"])
        self.assertEqual(blocked["writes_performed"], 0)


if __name__ == "__main__":
    unittest.main()
