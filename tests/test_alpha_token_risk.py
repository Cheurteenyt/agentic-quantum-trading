from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.alpha_risk import analyze_token_risk  # noqa: E402


class AlphaTokenRiskTests(unittest.TestCase):
    def test_token_risk_exposes_source_policy_and_missing_proofs(self) -> None:
        result = analyze_token_risk({
            "token": "LAB",
            "chain": "bsc",
            "buy_count": 4,
            "sell_count": 0,
            "unrealized_usd": 1200,
        })

        self.assertIn("source_policy", result)
        self.assertIn("source_trace", result)
        self.assertIn("missing_proofs", result)
        self.assertFalse(result["block_trade"])
        self.assertEqual(result["source_trace"]["sellability_probe"], "not_run")
        self.assertIn("successful_sell_proof", result["missing_proofs"])
        self.assertIn("contract_privilege_scan", result["missing_proofs"])
        self.assertIn("holder_concentration", result["missing_proofs"])
        self.assertIn("liquidity_snapshot", result["missing_proofs"])

    def test_honeypot_probe_blocks_trade_with_trace(self) -> None:
        def probe(_token: str, _chain: str) -> dict:
            return {
                "token_address": _token,
                "chain": _chain,
                "dexscreener": {"ok": True, "liquidity_usd": 25000, "volume_24h": 1000},
                "honeypot_api": {"ok": True, "is_honeypot": True, "confidence": 0.92},
                "explorer_scrape": None,
                "consensus": "honeypot",
                "overall_sellable": False,
                "sellability_confidence": 0.92,
                "auto_flags": [
                    {
                        "code": "honeypot_confirmed",
                        "severity": "critical",
                        "points": 48,
                        "detail": "Honeypot confirmed.",
                    }
                ],
            }

        result = analyze_token_risk(
            {
                "token": "SCAM",
                "chain": "bsc",
                "token_address": "0x1111111111111111111111111111111111111111",
                "top_holder_pct": 40,
            },
            sellability_probe=probe,
        )

        self.assertTrue(result["block_trade"])
        self.assertEqual(result["profit_integrity"], "not_trustworthy")
        self.assertEqual(result["source_trace"]["sellability_probe"], "injected")
        self.assertEqual(result["source_trace"]["honeypot_api"], "ok")
        self.assertIn("honeypot_confirmed", {flag["code"] for flag in result["flags"]})
        self.assertNotIn("liquidity_snapshot", result["missing_proofs"])


if __name__ == "__main__":
    unittest.main()
