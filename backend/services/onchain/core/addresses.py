"""Address validation helpers for Core Equity on-chain modules."""

from __future__ import annotations

import re
from typing import Any


def _is_evm_address(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return bool(re.fullmatch(r"0x[a-f0-9]{40}", text))

