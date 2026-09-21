from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "frontend" / "src"


class WalletClientSafetyTests(unittest.TestCase):
    def test_wallet_requests_are_centralized_behind_safety_wrapper(self) -> None:
        violations: list[str] = []
        for path in FRONTEND_SRC.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            if path.name == "walletSafety.ts":
                continue
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                if re.search(r"\b(?:ethereum|provider)\.request\s*\(", line):
                    violations.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")
        self.assertEqual(violations, [], "Raw wallet provider requests must use safeWalletRequest.")

    def test_client_code_does_not_call_transaction_or_approval_methods(self) -> None:
        dangerous = re.compile(
            r"\b("
            r"eth_sendTransaction|eth_signTransaction|eth_signTypedData(?:_v3|_v4)?|"
            r"wallet_sendCalls|wallet_switchEthereumChain|wallet_addEthereumChain|"
            r"sendTransaction|writeContract|setApprovalForAll|permit\s*\("
            r")\b"
        )
        violations: list[str] = []
        for path in FRONTEND_SRC.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            if path.name == "walletSafety.ts":
                continue
            text = path.read_text(encoding="utf-8")
            for match in dangerous.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: {match.group(1)}")
        self.assertEqual(violations, [], "Client code must stay read-only; no tx/signTypedData/approval calls.")

    def test_connected_wallet_state_does_not_persist_raw_signatures(self) -> None:
        dashboard = (FRONTEND_SRC / "pages" / "Dashboard.tsx").read_text(encoding="utf-8")
        self.assertNotIn("signature?:", dashboard)
        self.assertNotIn("signature:", dashboard.replace("signature = await", ""))

    def test_external_blank_links_have_noopener_or_noreferrer(self) -> None:
        violations: list[str] = []
        for path in FRONTEND_SRC.rglob("*.tsx"):
            lines = path.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                if 'target="_blank"' not in line:
                    continue
                block = "\n".join(lines[index : min(len(lines), index + 6)])
                if "rel=" not in block or ("noopener" not in block and "noreferrer" not in block):
                    violations.append(f"{path.relative_to(ROOT)}:{index + 1}: {line.strip()}")
        self.assertEqual(violations, [], 'External target="_blank" links need rel="noopener noreferrer".')


if __name__ == "__main__":
    unittest.main()
