from __future__ import annotations


_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}


def confidence_allows(confidence: str | None, min_confidence: str = "high") -> bool:
    return _CONFIDENCE_RANK.get(str(confidence or "").lower(), 0) >= _CONFIDENCE_RANK.get(min_confidence, 3)


def address_kind(label: str | None, code: str, tx_count: int) -> tuple[str, bool]:
    lowered = (label or "").lower()
    is_contract = bool(code and code != "0x")
    if not is_contract:
        return "wallet", False
    if "router" in lowered:
        return "router", True
    if "pool" in lowered:
        return "pool", True
    if "token" in lowered or "wrapped" in lowered or "weth" in lowered or "usdc" in lowered or "usdt" in lowered:
        return "token_contract", True
    if "safe" in lowered or "proxy" in lowered or "gnosis" in lowered:
        return "safe_or_proxy", True
    if tx_count == 0:
        return "contract", True
    return "contract", True


def activity_tier(tx_count: int) -> str:
    if tx_count <= 0:
        return "dormant"
    if tx_count < 5:
        return "fresh"
    if tx_count < 100:
        return "low"
    if tx_count < 10_000:
        return "active"
    if tx_count < 1_000_000:
        return "high_activity"
    return "hyper_active"


def risk_flags(
    address_kind_value: str,
    is_contract: bool,
    tx_count: int,
    confidence: str | None,
    native_value_usd: float,
) -> list[str]:
    flags = []
    if activity_tier(tx_count) == "fresh":
        flags.append("fresh_wallet")
    if tx_count == 0:
        flags.append("dormant_or_contract_only")
    if is_contract:
        flags.append("contract_address")
    if address_kind_value in {"router", "pool", "token_contract"}:
        flags.append(f"{address_kind_value}_not_human_wallet")
    if str(confidence or "").lower() != "high":
        flags.append("non_high_confidence_label")
    if native_value_usd > 10_000_000:
        flags.append("large_native_balance")
    return flags


def data_quality_score(
    confidence: str | None,
    is_contract: bool,
    tx_count: int,
    token_count: int,
    rpc_ok: bool = True,
) -> int:
    score = 35 if rpc_ok else 0
    score += {"high": 35, "medium": 20, "low": 5}.get(str(confidence or "").lower(), 0)
    if tx_count > 0:
        score += 10
    if token_count > 0:
        score += 10
    if is_contract:
        score -= 10
    return max(0, min(100, score))
