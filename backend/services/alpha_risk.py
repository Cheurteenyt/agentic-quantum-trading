"""Alpha Lab token-risk scoring engine.

The sellability probe is injected by the caller so network scraping/fallbacks can
stay isolated from the scoring rules.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable

from services.alpha_risk_models import SellabilityProbe, TokenRiskResult


def analyze_token_risk(
    payload: dict[str, Any],
    sellability_probe: Callable[[str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score whether a token/wallet profit is likely realizable."""
    payload = payload or {}
    flags: list[dict[str, Any]] = []

    def flag(code: str, severity: str, points: int, detail: str) -> None:
        flags.append({
            "code": code,
            "severity": severity,
            "points": points,
            "detail": detail,
        })

    can_sell = _boolish(_pick_first(payload, ["can_sell", "sellable", "can_realize"]))
    honeypot = _boolish(payload.get("honeypot"))

    _probe: dict[str, Any] = {}
    token_address = (payload.get("token_address") or payload.get("address") or "").strip()
    chain = payload.get("chain") or payload.get("network") or "ethereum"
    if sellability_probe and re.fullmatch(r"0x[0-9a-fA-F]{40}", token_address):
        _probe = sellability_probe(token_address, chain)
        for auto_flag in (_probe.get("auto_flags") or []):
            flags.append(auto_flag)

        ds = _probe.get("dexscreener") or {}
        hp = _probe.get("honeypot_api") or {}
        if ds.get("ok"):
            payload.setdefault("liquidity_usd", ds.get("liquidity_usd"))
            payload.setdefault("volume_24h_usd", ds.get("volume_24h"))
        if hp.get("ok"):
            payload.setdefault("sell_tax_pct", hp.get("sell_tax_pct"))
            payload.setdefault("buy_tax_pct", hp.get("buy_tax_pct"))
            if hp.get("is_honeypot"):
                payload["honeypot"] = True
                payload["can_sell"] = False

        can_sell = _boolish(_pick_first(payload, ["can_sell", "sellable", "can_realize"]))
        honeypot = _boolish(payload.get("honeypot"))

    if honeypot is True or can_sell is False:
        already = any(
            item["code"] in {"honeypot_confirmed", "sell_blocked_on_chain", "unsellable_or_honeypot"}
            for item in flags
        )
        if not already:
            flag(
                "unsellable_or_honeypot",
                "critical",
                45,
                "Token is marked honeypot/unsellable or sell simulation failed.",
            )

    for key, code, detail in [
        ("freeze_function", "freeze_function", "Contract exposes a freeze function."),
        ("blacklist_function", "blacklist_function", "Contract exposes blacklist controls."),
        ("trading_disabled", "trading_disabled", "Trading appears disabled or gated."),
        ("paused", "paused", "Token or transfer logic appears paused."),
        ("owner_can_mint", "owner_can_mint", "Owner or privileged role can mint supply."),
    ]:
        if _boolish(payload.get(key)) is True:
            severity = "critical" if key in {"freeze_function", "blacklist_function", "trading_disabled"} else "high"
            points = 35 if severity == "critical" else 22
            flag(code, severity, points, detail)

    sell_tax_pct = _percent(payload.get("sell_tax_pct") or payload.get("sell_tax"))
    buy_tax_pct = _percent(payload.get("buy_tax_pct") or payload.get("buy_tax"))
    if sell_tax_pct is not None:
        if sell_tax_pct >= 50:
            flag("extreme_sell_tax", "critical", 35, f"Sell tax is {sell_tax_pct:.2f}%. PnL may be impossible to realize.")
        elif sell_tax_pct >= 20:
            flag("high_sell_tax", "high", 22, f"Sell tax is {sell_tax_pct:.2f}%. Backtest must haircut exits.")
        elif sell_tax_pct >= 8:
            flag("elevated_sell_tax", "medium", 10, f"Sell tax is {sell_tax_pct:.2f}%.")
    if buy_tax_pct is not None and buy_tax_pct >= 10:
        flag("high_buy_tax", "medium", 8, f"Buy tax is {buy_tax_pct:.2f}%.")

    liquidity_usd = _float_or_none(payload.get("liquidity_usd") or payload.get("dex_liquidity_usd"))
    volume_24h = _float_or_none(payload.get("volume_24h_usd") or payload.get("volume_usd_24h"))
    if liquidity_usd is not None:
        if liquidity_usd < 10_000:
            flag("very_low_liquidity", "critical", 30, f"Liquidity is only ${liquidity_usd:,.0f}.")
        elif liquidity_usd < 75_000:
            flag("low_liquidity", "high", 18, f"Liquidity is ${liquidity_usd:,.0f}.")
    if volume_24h is not None and liquidity_usd is not None and volume_24h > liquidity_usd * 8:
        flag("wash_volume_suspected", "medium", 12, "24h volume is very high versus liquidity; wash trading is possible.")

    price_impact = _percent(payload.get("price_impact_100_usd_pct") or payload.get("price_impact_pct"))
    if price_impact is not None:
        if price_impact >= 25:
            flag("extreme_price_impact", "critical", 28, f"Estimated price impact is {price_impact:.2f}%.")
        elif price_impact >= 10:
            flag("high_price_impact", "high", 16, f"Estimated price impact is {price_impact:.2f}%.")

    top_holder_pct = _percent(payload.get("top_holder_pct"))
    top_10_pct = _percent(payload.get("top_10_pct") or payload.get("top10_holder_pct"))
    owner_balance_pct = _percent(payload.get("owner_balance_pct"))
    if top_holder_pct is not None and top_holder_pct >= 35:
        flag("top_holder_concentration", "high", 18, f"Top holder controls {top_holder_pct:.2f}%.")
    if top_10_pct is not None and top_10_pct >= 70:
        flag("top10_concentration", "medium", 10, f"Top 10 holders control {top_10_pct:.2f}%.")
    if owner_balance_pct is not None and owner_balance_pct >= 10:
        flag("owner_balance_risk", "high", 18, f"Owner wallet controls {owner_balance_pct:.2f}%.")

    lp_locked_pct = _percent(payload.get("lp_locked_pct") or payload.get("liquidity_locked_pct"))
    lp_burned = _boolish(payload.get("lp_burned"))
    if lp_locked_pct is not None and lp_locked_pct < 50 and lp_burned is not True:
        flag("lp_not_locked", "high", 18, f"Only {lp_locked_pct:.2f}% of LP appears locked/burned.")

    proxy = _boolish(payload.get("proxy") or payload.get("is_proxy"))
    verified_source = _boolish(payload.get("verified_source") or payload.get("source_verified"))
    renounced = _boolish(payload.get("renounced") or payload.get("ownership_renounced"))
    if proxy is True and verified_source is not True:
        flag("unverified_proxy", "high", 18, "Proxy contract without verified implementation.")
    if renounced is False and any(
        _boolish(payload.get(key)) is True for key in ["owner_can_mint", "blacklist_function", "freeze_function"]
    ):
        flag("privileged_owner_active", "critical", 30, "Owner is active while privileged controls exist.")

    unrealized_usd = _float_or_none(payload.get("unrealized_usd"))
    realized_usd = _float_or_none(payload.get("realized_usd"))
    sell_count = _float(payload.get("sell_count"), 0.0)
    buy_count = _float(payload.get("buy_count"), 0.0)
    if unrealized_usd and unrealized_usd > 0 and sell_count <= 0:
        flag("unrealized_only_profit", "medium", 14, "Wallet profit is unrealized with no observed sells.")
    if buy_count > 0 and sell_count <= 0 and (can_sell is not True):
        flag("missing_sell_proof", "high", 20, "Wallet bought but there is no successful sell proof yet.")

    flags = _dedupe_risk_flags(flags)
    if realized_usd is not None and realized_usd > 0 and sell_count > 0:
        profit_integrity = "realized_profit_observed"
    elif any(item["code"] in {"unsellable_or_honeypot", "honeypot_confirmed", "sell_blocked_on_chain", "freeze_function", "blacklist_function"} for item in flags):
        profit_integrity = "not_trustworthy"
    elif any(item["code"] in {"unrealized_only_profit", "missing_sell_proof"} for item in flags):
        profit_integrity = "unrealized_or_unproven"
    else:
        profit_integrity = "unknown"

    risk_score = min(100, sum(int(item["points"]) for item in flags))
    critical_codes = {item["code"] for item in flags if item["severity"] == "critical"}
    block_trade = bool(critical_codes & {
        "unsellable_or_honeypot",
        "honeypot_confirmed",
        "sell_blocked_on_chain",
        "freeze_function",
        "blacklist_function",
        "trading_disabled",
        "extreme_sell_tax",
        "very_low_liquidity",
        "extreme_price_impact",
        "privileged_owner_active",
    })

    return TokenRiskResult(
        token=payload.get("token") or payload.get("symbol") or payload.get("asset") or "unknown",
        chain=payload.get("chain") or payload.get("network") or "unknown",
        risk_score=risk_score,
        sellability_score=max(0, 100 - risk_score),
        block_trade=block_trade,
        profit_integrity=profit_integrity,
        flags=flags,
        sellability_probe=SellabilityProbe(**_probe) if _probe else None,
        source_policy=str(
            payload.get("source_policy")
            or "token_risk_requires_traceable_sources; insufficient proof keeps verdict research-only/inconclusive"
        ),
        source_trace=_build_source_trace(payload, _probe),
        missing_proofs=_missing_token_proofs(payload, _probe, flags),
    ).model_dump()


def _dedupe_risk_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    deduped: dict[str, dict[str, Any]] = {}

    for item in flags:
        code = str(item.get("code") or "unknown")
        current = dict(item)
        if code not in deduped:
            deduped[code] = current
            continue

        existing = deduped[code]
        existing_rank = severity_rank.get(str(existing.get("severity", "")).lower(), -1)
        current_rank = severity_rank.get(str(current.get("severity", "")).lower(), -1)
        if current_rank > existing_rank:
            existing["severity"] = current.get("severity", existing.get("severity"))
        existing["points"] = max(int(existing.get("points", 0)), int(current.get("points", 0)))

        existing_detail = str(existing.get("detail") or "")
        current_detail = str(current.get("detail") or "")
        if current_detail and current_detail not in existing_detail:
            existing["detail"] = f"{existing_detail} | {current_detail}" if existing_detail else current_detail

    return list(deduped.values())


def _build_source_trace(payload: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    """Expose where token-risk evidence came from without storing secrets."""
    hp = probe.get("honeypot_api") or {}
    ds = probe.get("dexscreener") or {}
    exp = probe.get("explorer_scrape") or {}
    return {
        "payload_source": payload.get("source") or payload.get("provider") or "caller_payload",
        "sellability_probe": "injected" if probe else "not_run",
        "dexscreener": "ok" if ds.get("ok") else ds.get("reason") or ds.get("error") or "missing",
        "honeypot_api": "ok" if hp.get("ok") else hp.get("reason") or hp.get("error") or "missing",
        "explorer_scrape": "ok" if exp.get("ok") else exp.get("reason") or exp.get("error") or "not_required_or_missing",
        "contract_flags_from_payload": [
            key
            for key in ["freeze_function", "blacklist_function", "trading_disabled", "paused", "owner_can_mint"]
            if _boolish(payload.get(key)) is not None
        ],
    }


def _missing_token_proofs(payload: dict[str, Any], probe: dict[str, Any], flags: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    hp = probe.get("honeypot_api") or {}
    ds = probe.get("dexscreener") or {}
    exp = probe.get("explorer_scrape") or {}

    if _float(payload.get("sell_count"), 0.0) <= 0 and _boolish(_pick_first(payload, ["can_sell", "sellable", "can_realize"])) is not True:
        missing.append("successful_sell_proof")
    if not (hp.get("ok") or exp.get("ok")) and not any(item.get("code") in {"honeypot_confirmed", "sell_blocked_on_chain"} for item in flags):
        missing.append("sellability_probe")
    contract_keys = ["freeze_function", "blacklist_function", "trading_disabled", "paused", "owner_can_mint", "proxy", "verified_source"]
    if not any(_boolish(payload.get(key)) is not None for key in contract_keys) and not exp.get("ok"):
        missing.append("contract_privilege_scan")
    if _percent(payload.get("top_holder_pct")) is None and _percent(payload.get("top_10_pct") or payload.get("top10_holder_pct")) is None:
        missing.append("holder_concentration")
    if _float_or_none(payload.get("liquidity_usd") or payload.get("dex_liquidity_usd")) is None and not ds.get("ok"):
        missing.append("liquidity_snapshot")
    return missing


def _pick_first(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    result = _float(value, math.nan)
    return None if math.isnan(result) else result


def _percent(value: Any) -> float | None:
    result = _float_or_none(value)
    if result is None:
        return None
    if 0 < result <= 1:
        return result * 100
    return result


def _boolish(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "enabled", "active"}:
        return True
    if text in {"false", "no", "n", "0", "disabled", "inactive"}:
        return False
    return None
