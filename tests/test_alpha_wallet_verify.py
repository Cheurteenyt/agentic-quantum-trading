from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Response
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import routers.alpha_lab as alpha_lab  # noqa: E402


def _request(headers: list[tuple[bytes, bytes]] | None = None, scheme: str = "http") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/alpha/wallet/verify",
            "query_string": b"",
            "headers": headers or [(b"host", b"127.0.0.1:8000")],
            "client": ("127.0.0.1", 4242),
            "server": ("127.0.0.1", 8000),
            "scheme": scheme,
        }
    )


class AlphaWalletVerificationTests(unittest.TestCase):
    def _fresh_message(self, address: str = "0xec9ab39bffbb7f164b555b8474baa41b67739550", network: str = "ethereum") -> str:
        return (
            "Core Equity wallet verification\n"
            f"Address: {address}\n"
            f"Network: {network}\n"
            f"Time: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}"
        )

    def test_wallet_ownership_reports_unverified_without_server_proof(self) -> None:
        original_path = alpha_lab.WALLET_PROOFS_PATH
        with tempfile.TemporaryDirectory() as tmp:
            alpha_lab.WALLET_PROOFS_PATH = Path(tmp) / "wallet_proofs.json"
            try:
                result = asyncio.run(
                    alpha_lab._wallet_ownership("0xec9ab39bffbb7f164b555b8474baa41b67739550", None)
                )
            finally:
                alpha_lab.WALLET_PROOFS_PATH = original_path

        self.assertTrue(result["ok"])
        self.assertFalse(result["verified"])
        self.assertEqual(result["source"], "no_server_proof")
        self.assertEqual(result["execution_gate"], "read_only_unverified_wallet")

    def test_wallet_ownership_expires_old_server_proof(self) -> None:
        original_path = alpha_lab.WALLET_PROOFS_PATH
        old_verified_at = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
        with tempfile.TemporaryDirectory() as tmp:
            alpha_lab.WALLET_PROOFS_PATH = Path(tmp) / "wallet_proofs.json"
            alpha_lab.WALLET_PROOFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            alpha_lab.WALLET_PROOFS_PATH.write_text(
                (
                    '{"proofs":[{"address":"0xec9ab39bffbb7f164b555b8474baa41b67739550",'
                    '"verified":true,"method":"personal_sign_recovered","provider":"MetaMask",'
                    f'"network":"ethereum","verified_at":{old_verified_at},'
                    '"source":"core_equity_client_wallet"}]}'
                ),
                encoding="utf-8",
            )
            try:
                result = asyncio.run(
                    alpha_lab._wallet_ownership("0xec9ab39bffbb7f164b555b8474baa41b67739550", None)
                )
            finally:
                alpha_lab.WALLET_PROOFS_PATH = original_path

        self.assertFalse(result["verified"])
        self.assertTrue(result["expired"])
        self.assertEqual(result["execution_gate"], "ownership_proof_expired")

    def test_wallet_ownership_requires_matching_client_session_even_with_fresh_proof(self) -> None:
        original_path = alpha_lab.WALLET_PROOFS_PATH
        verified_at = int(datetime.now(timezone.utc).timestamp())
        with tempfile.TemporaryDirectory() as tmp:
            alpha_lab.WALLET_PROOFS_PATH = Path(tmp) / "wallet_proofs.json"
            alpha_lab.WALLET_PROOFS_PATH.parent.mkdir(parents=True, exist_ok=True)
            alpha_lab.WALLET_PROOFS_PATH.write_text(
                (
                    '{"proofs":[{"address":"0xec9ab39bffbb7f164b555b8474baa41b67739550",'
                    '"verified":true,"method":"personal_sign_recovered","provider":"MetaMask",'
                    f'"network":"ethereum","verified_at":{verified_at},'
                    '"source":"core_equity_client_wallet"}]}'
                ),
                encoding="utf-8",
            )
            try:
                result = asyncio.run(
                    alpha_lab._wallet_ownership("0xec9ab39bffbb7f164b555b8474baa41b67739550", None)
                )
            finally:
                alpha_lab.WALLET_PROOFS_PATH = original_path

        self.assertTrue(result["verified"])
        self.assertFalse(result["session_active"])
        self.assertEqual(result["execution_gate"], "client_session_required")

    def test_sensitive_wallet_plan_requires_client_session(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(
                alpha_lab._wallet_copy_plan(
                    "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                    core_client_session=None,
                )
            )
        self.assertEqual(raised.exception.status_code, 401)

    def test_client_session_must_match_requested_wallet(self) -> None:
        previous_secret = os.environ.get("CORE_CLIENT_SESSION_SECRET")
        os.environ["CORE_CLIENT_SESSION_SECRET"] = "test-session-secret"
        try:
            session = alpha_lab._sign_client_session(
                {
                    "wallet": "0x0000000000000000000000000000000000000001",
                    "network": "ethereum",
                    "provider": "MetaMask",
                    "iat": int(datetime.now(timezone.utc).timestamp()),
                    "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                    "scope": "alpha_lab_read_only",
                }
            )
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    alpha_lab._wallet_copy_plan(
                        "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                        core_client_session=session,
                    )
                )
        finally:
            if previous_secret is None:
                os.environ.pop("CORE_CLIENT_SESSION_SECRET", None)
            else:
                os.environ["CORE_CLIENT_SESSION_SECRET"] = previous_secret
        self.assertEqual(raised.exception.status_code, 403)

    def test_evm_verification_fails_closed_without_recovery_library(self) -> None:
        original_account = alpha_lab.Account
        original_encode_defunct = alpha_lab.encode_defunct
        alpha_lab.Account = None
        alpha_lab.encode_defunct = None
        try:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    alpha_lab._wallet_verify(
                        {
                            "address": "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                            "type": "evm",
                            "provider": "MetaMask",
                            "network": "ethereum",
                            "message": self._fresh_message(),
                            "signature": "0x" + ("1" * 130),
                        },
                        _request(),
                        Response(),
                    )
                )
            self.assertEqual(raised.exception.status_code, 503)
        finally:
            alpha_lab.Account = original_account
            alpha_lab.encode_defunct = original_encode_defunct

    def test_evm_verification_rejects_stale_signature_message(self) -> None:
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(
                alpha_lab._wallet_verify(
                    {
                        "address": "0xec9ab39bffbb7f164b555b8474baa41b67739550",
                        "type": "evm",
                        "provider": "MetaMask",
                        "network": "ethereum",
                        "message": (
                            "Core Equity wallet verification\n"
                            "Address: 0xec9ab39bffbb7f164b555b8474baa41b67739550\n"
                            "Network: ethereum\n"
                            f"Time: {stale_time}"
                        ),
                        "signature": "0x" + ("1" * 130),
                    },
                    _request(),
                    Response(),
                )
            )
        self.assertEqual(raised.exception.status_code, 400)

    def test_client_session_cookie_secure_follows_https_or_forwarded_proto(self) -> None:
        self.assertFalse(alpha_lab._cookie_secure(_request()))
        self.assertTrue(alpha_lab._cookie_secure(_request(scheme="https")))
        self.assertTrue(alpha_lab._cookie_secure(_request(headers=[(b"x-forwarded-proto", b"https")])))

    def test_usage_event_extra_redacts_sensitive_fields(self) -> None:
        original_path = alpha_lab.ALPHA_USAGE_PATH
        with tempfile.TemporaryDirectory() as tmp:
            alpha_lab.ALPHA_USAGE_PATH = Path(tmp) / "usage_events.jsonl"
            try:
                stored = alpha_lab._append_usage_event(
                    {
                        "page": "alpha",
                        "action": "wallet_connected",
                        "wallet_hash": "abc",
                        "extra": {
                            "token": "client-secret",
                            "signature": "0x" + ("1" * 130),
                            "nested": {"privateKey": "very-secret", "safe": "ok"},
                        },
                        "client": {"host_hash": "host", "user_agent": "test"},
                    }
                )
            finally:
                alpha_lab.ALPHA_USAGE_PATH = original_path

        serialized = str(stored)
        self.assertNotIn("client-secret", serialized)
        self.assertNotIn("very-secret", serialized)
        self.assertEqual(stored["extra"]["token"], "[redacted]")
        self.assertEqual(stored["extra"]["nested"]["privateKey"], "[redacted]")

    def test_explicit_client_write_header_is_required_for_persistence(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            alpha_lab._require_explicit_client_write(None, "persist-rpc-snapshot", "wallet RPC snapshot persistence")
        self.assertEqual(raised.exception.status_code, 403)

        alpha_lab._require_explicit_client_write(
            "persist-rpc-snapshot",
            "persist-rpc-snapshot",
            "wallet RPC snapshot persistence",
        )

    def test_client_simulation_payloads_are_bounded(self) -> None:
        payload = {"trades": [{"price": 0.5}] * (alpha_lab.ALPHA_CLIENT_MAX_ITEMS + 1)}
        with self.assertRaises(HTTPException) as raised:
            alpha_lab._bounded_client_payload(payload, "trades")
        self.assertEqual(raised.exception.status_code, 413)

        with self.assertRaises(HTTPException) as raised_type:
            alpha_lab._bounded_client_payload({"events": {"not": "a list"}}, "events")
        self.assertEqual(raised_type.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
