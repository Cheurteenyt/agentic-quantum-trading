"""JSON/coercion helpers for extracted on-chain modules."""

from __future__ import annotations

import json
import os
from typing import Any


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _coerce_int(value: Any, default: int, minimum: int, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    number = max(minimum, number)
    if maximum is not None:
        number = min(number, maximum)
    return number


def _env_int(name: str, default: int, minimum: int, maximum: int | None = None) -> int:
    return _coerce_int(os.getenv(name), default, minimum, maximum)


def _env_optional_int(name: str, minimum: int, maximum: int | None = None) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return _coerce_int(raw, minimum, minimum, maximum)


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

