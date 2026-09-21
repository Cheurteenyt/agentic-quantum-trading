"""Numeric helpers for Core Equity on-chain modules."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def _median(values: list[float]) -> float | None:
    clean = sorted(float(value) for value in values if float(value or 0) > 0)
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _decimal_amount_string(raw_value: Any, decimals: Any) -> str | None:
    try:
        raw_int = int(raw_value or 0)
        decimals_int = int(decimals)
    except (TypeError, ValueError):
        return None
    if decimals_int < 0 or decimals_int > 255:
        return None
    value = Decimal(raw_int) / (Decimal(10) ** decimals_int)
    text = format(value.normalize(), "f")
    return "0" if text == "-0" else text

