from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"
JSON_OUT = BASE_DIR / "aster_mcp_capability_audit_latest.json"
MD_OUT = DOCS_DIR / "aster-mcp-capability-audit.md"


CAPABILITIES: list[dict[str, Any]] = [
    {
        "name": "exchange_info",
        "mcp_tool": "get_exchange_info",
        "endpoint": "GET /fapi/v3/exchangeInfo",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "high",
        "uses": ["tick_size", "step_size", "min_notional", "percent_price", "market_take_bound", "liquidation_fee"],
        "next_action": "Use filters in execution-quality validation before promoting lanes.",
    },
    {
        "name": "ticker_24h",
        "mcp_tool": "get_ticker",
        "endpoint": "GET /fapi/v3/ticker/24hr",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "high",
        "uses": ["24h_quote_volume", "trade_count", "last_price"],
        "next_action": "Keep as liquidity gate in reality check.",
    },
    {
        "name": "order_book_depth",
        "mcp_tool": "get_order_book",
        "endpoint": "GET /fapi/v3/depth",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "high",
        "uses": ["spread_bps", "top10_depth", "depth_imbalance"],
        "next_action": "Use to reject thin lanes and estimate slippage proxy.",
    },
    {
        "name": "last_price_klines",
        "mcp_tool": "get_klines",
        "endpoint": "GET /fapi/v3/klines",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "high",
        "uses": ["OHLCV", "trade_count", "taker_buy_ratio"],
        "next_action": "Base replay remains last-price kline until mark/index replay is added.",
    },
    {
        "name": "mark_price_klines",
        "mcp_tool": "not_explicit_or_public_api",
        "endpoint": "GET /fapi/v3/markPriceKlines",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "very_high",
        "uses": ["liquidation_reference", "mark_price_replay", "manipulation_resistant_price"],
        "next_action": "Add mark-price replay variant to compare against last-price replay.",
    },
    {
        "name": "index_price_klines",
        "mcp_tool": "not_explicit_or_public_api",
        "endpoint": "GET /fapi/v3/indexPriceKlines?pair={symbol}",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "very_high",
        "uses": ["index_reference", "premium_replay", "basis_filter"],
        "next_action": "Use mark-index divergence as a pre-trade filter.",
    },
    {
        "name": "premium_index",
        "mcp_tool": "get_funding_info_or_public_api",
        "endpoint": "GET /fapi/v3/premiumIndex",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "very_high",
        "uses": ["mark_price", "index_price", "premium_bps", "latest_funding_rate", "next_funding_time"],
        "next_action": "Use premium_bps to filter longs/shorts when perp is too far from index.",
    },
    {
        "name": "funding_rate_history",
        "mcp_tool": "get_funding_rate",
        "endpoint": "GET /fapi/v3/fundingRate",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "high",
        "uses": ["funding_cost_estimate", "carry_filter"],
        "next_action": "Replace fixed 1 bps/8h proxy with recent funding history.",
    },
    {
        "name": "funding_info",
        "mcp_tool": "get_funding_info",
        "endpoint": "GET /fapi/v3/fundingInfo",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "medium",
        "uses": ["funding_interval", "funding_cap", "funding_floor"],
        "next_action": "Keep in reality check as a risk warning.",
    },
    {
        "name": "index_references",
        "mcp_tool": "not_explicit_or_public_api",
        "endpoint": "GET /fapi/v3/indexreferences",
        "security_type": "PUBLIC",
        "status": "integrated",
        "safe_now": True,
        "backtest_value": "medium",
        "uses": ["index_quality", "reference_count", "reference_weights"],
        "next_action": "Warn when reference count is too low.",
    },
    {
        "name": "public_websocket_trades",
        "mcp_tool": "not_integrated",
        "endpoint": "wss://fstream.asterdex.com/ws <symbol>@aggTrade or trade streams",
        "security_type": "PUBLIC_WS",
        "status": "available_not_integrated",
        "safe_now": True,
        "backtest_value": "very_high",
        "uses": ["forward_tick_feed", "less_rest_polling", "microstructure"],
        "next_action": "Create read-only websocket sampler before using for paper forward.",
    },
    {
        "name": "public_websocket_depth",
        "mcp_tool": "not_integrated",
        "endpoint": "wss://fstream.asterdex.com/ws <symbol>@depth",
        "security_type": "PUBLIC_WS",
        "status": "available_not_integrated",
        "safe_now": True,
        "backtest_value": "very_high",
        "uses": ["live_spread", "depth_changes", "order_book_pressure"],
        "next_action": "Add sampler with sequence/update-id checks; no trading.",
    },
    {
        "name": "public_websocket_mark_price",
        "mcp_tool": "not_integrated",
        "endpoint": "wss://fstream.asterdex.com/ws mark price streams",
        "security_type": "PUBLIC_WS",
        "status": "available_not_integrated",
        "safe_now": True,
        "backtest_value": "high",
        "uses": ["forward_mark_price", "liquidation_reference"],
        "next_action": "Use for forward paper monitoring once sampler exists.",
    },
    {
        "name": "leverage_bracket",
        "mcp_tool": "get_leverage_bracket",
        "endpoint": "GET /fapi/v3/leverageBracket",
        "security_type": "USER_DATA_SIGNED",
        "status": "blocked_until_readonly_credentials_policy",
        "safe_now": False,
        "backtest_value": "very_high",
        "uses": ["maintenance_margin_ratio", "notional_cap", "max_initial_leverage", "liquidation_proxy_replacement"],
        "next_action": "Test on V3 testnet/read-only credentials only; never with trade permissions.",
    },
    {
        "name": "commission_rate",
        "mcp_tool": "get_commission_rate",
        "endpoint": "GET /fapi/v3/commissionRate",
        "security_type": "USER_DATA_SIGNED",
        "status": "blocked_until_readonly_credentials_policy",
        "safe_now": False,
        "backtest_value": "high",
        "uses": ["maker_fee", "taker_fee", "fee_model_replacement"],
        "next_action": "Use only after credential policy exists.",
    },
    {
        "name": "account_balance",
        "mcp_tool": "get_balance",
        "endpoint": "GET /fapi/v3/balance",
        "security_type": "USER_DATA_SIGNED",
        "status": "blocked_until_readonly_credentials_policy",
        "safe_now": False,
        "backtest_value": "medium",
        "uses": ["paper_account_comparison", "exposure_limit"],
        "next_action": "Not needed before paper strategy has strong evidence.",
    },
    {
        "name": "positions",
        "mcp_tool": "get_positions",
        "endpoint": "GET /fapi/v3/positionRisk or account positions",
        "security_type": "USER_DATA_SIGNED",
        "status": "blocked_until_readonly_credentials_policy",
        "safe_now": False,
        "backtest_value": "medium",
        "uses": ["real_account_reconciliation", "position_monitoring"],
        "next_action": "Not needed until a real read-only account phase exists.",
    },
    {
        "name": "user_data_stream",
        "mcp_tool": "not_integrated",
        "endpoint": "WebSocket user data stream",
        "security_type": "USER_DATA_SIGNED_WS",
        "status": "blocked_until_readonly_credentials_policy",
        "safe_now": False,
        "backtest_value": "high_later",
        "uses": ["order_status", "position_updates", "balance_updates"],
        "next_action": "Only after signed read-only testnet phase.",
    },
    {
        "name": "create_or_cancel_order",
        "mcp_tool": "create_order/cancel_order/cancel_all_orders",
        "endpoint": "POST/DELETE TRADE endpoints",
        "security_type": "TRADE_SIGNED",
        "status": "blocked",
        "safe_now": False,
        "backtest_value": "none_now",
        "uses": ["real_execution"],
        "next_action": "Do not enable. Paper trading evidence is insufficient.",
    },
    {
        "name": "set_leverage_or_margin",
        "mcp_tool": "set_leverage/set_margin_mode",
        "endpoint": "POST TRADE account config endpoints",
        "security_type": "TRADE_SIGNED",
        "status": "blocked",
        "safe_now": False,
        "backtest_value": "none_now",
        "uses": ["real_account_mutation"],
        "next_action": "Do not enable in Core Equity agent.",
    },
    {
        "name": "transfers",
        "mcp_tool": "transfer_funds/transfer_spot_futures",
        "endpoint": "TRANSFER endpoints",
        "security_type": "TRANSFER_SIGNED",
        "status": "blocked",
        "safe_now": False,
        "backtest_value": "none_now",
        "uses": ["fund movement"],
        "next_action": "Never expose to the agent.",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _group(capabilities: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "available_now_public": [],
        "available_now_public_ws_not_integrated": [],
        "needs_readonly_credentials": [],
        "blocked_trade_or_transfer": [],
        "useful_for_backtest": [],
        "not_useful_now": [],
    }
    for item in capabilities:
        status = str(item.get("status") or "")
        sec = str(item.get("security_type") or "")
        value = str(item.get("backtest_value") or "")
        if item.get("safe_now") and sec == "PUBLIC" and status == "integrated":
            grouped["available_now_public"].append(item)
        if item.get("safe_now") and sec == "PUBLIC_WS":
            grouped["available_now_public_ws_not_integrated"].append(item)
        if "USER_DATA" in sec:
            grouped["needs_readonly_credentials"].append(item)
        if sec in {"TRADE_SIGNED", "TRANSFER_SIGNED"}:
            grouped["blocked_trade_or_transfer"].append(item)
        if value in {"high", "very_high", "high_later"}:
            grouped["useful_for_backtest"].append(item)
        if value in {"none_now"}:
            grouped["not_useful_now"].append(item)
    return grouped


def get_aster_mcp_capability_audit_preview(dry_run: bool = True) -> dict[str, Any]:
    if not dry_run:
        return {
            "ok": False,
            "status": "blocked",
            "blockers": ["dry_run_required"],
            "would_write": False,
            "writes_performed": 0,
            "would_call_external": False,
            "would_execute_trade": False,
        }
    grouped = _group(CAPABILITIES)
    roadmap = [
        {
            "priority": 1,
            "name": "mark_index_replay_filter",
            "why": "Les donnees mark/index publiques existent deja; elles peuvent reduire les faux edges issus du last-price.",
            "requires_credentials": False,
        },
        {
            "priority": 2,
            "name": "public_websocket_sampler",
            "why": "Les monitors forward doivent sortir du polling REST repetitif et lire un flux public plus proche du temps reel.",
            "requires_credentials": False,
        },
        {
            "priority": 3,
            "name": "funding_fee_proxy_replacement",
            "why": "L'historique funding public peut remplacer notre proxy fixe de 1 bps par 8h.",
            "requires_credentials": False,
        },
        {
            "priority": 4,
            "name": "readonly_signed_testnet_probe",
            "why": "Utile pour les leverage brackets et frais reels, mais seulement apres une politique credentials read-only.",
            "requires_credentials": True,
        },
    ]
    return {
        "ok": True,
        "dry_run": True,
        "status": "ready",
        "generated_at": _now(),
        "capability_count": len(CAPABILITIES),
        "groups": grouped,
        "capabilities": CAPABILITIES,
        "roadmap": roadmap,
        "safety": {
            "would_write": False,
            "writes_performed": 0,
            "would_call_external": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_store_credentials": False,
        },
    }


def write_aster_mcp_capability_audit_docs() -> dict[str, Any]:
    payload = get_aster_mcp_capability_audit_preview(dry_run=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    MD_OUT.write_text(_render_md(payload), encoding="utf-8")
    return payload


def _table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Aucune entree.\n"
    lines = [
        "| Capacite | Securite | Statut | Safe now | Valeur backtest | Prochaine action |",
        "|---|---|---|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(row.get(key, "")).replace("|", "/")
                for key in ("name", "security_type", "status", "safe_now", "backtest_value", "next_action")
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _render_md(payload: dict[str, Any]) -> str:
    groups = payload.get("groups") or {}
    roadmap = payload.get("roadmap") or []
    lines = [
        "# Audit des capacites Aster MCP",
        "",
        f"Genere le: `{payload.get('generated_at')}`",
        "",
        "Ce document separe ce qu'Aster/MCP peut fournir maintenant, ce qui demande des credentials read-only, et ce qui doit rester bloque.",
        "",
        "## Roadmap conseillee",
        "",
    ]
    for item in roadmap:
        lines.append(
            f"{item.get('priority')}. **{item.get('name')}** - {item.get('why')} "
            f"(credentials: {item.get('requires_credentials')})"
        )
    for key, title in [
        ("available_now_public", "Disponible maintenant - REST public"),
        ("available_now_public_ws_not_integrated", "Disponible maintenant - WebSocket public non integre"),
        ("needs_readonly_credentials", "Demande des credentials signes read-only"),
        ("blocked_trade_or_transfer", "Bloque - trade ou transfer"),
        ("useful_for_backtest", "Le plus utile pour les backtests"),
        ("not_useful_now", "Pas utile maintenant"),
    ]:
        lines.extend(["", f"## {title}", "", _table(groups.get(key) or [])])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Aucun appel externe pendant cet audit.",
            "- Aucun credential.",
            "- Aucun wallet.",
            "- Aucun trade.",
            "- Aucun write DB.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    payload = write_aster_mcp_capability_audit_docs()
    print(f"[{payload['generated_at']}] capabilities={payload['capability_count']} md={MD_OUT}")


if __name__ == "__main__":
    main()
