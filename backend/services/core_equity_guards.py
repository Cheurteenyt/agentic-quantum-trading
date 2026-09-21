from __future__ import annotations

from typing import Any, Mapping


DISABLED_RUNTIME_SURFACES: dict[str, bool] = {
    "would_create_cex_label": False,
    "would_create_dex_router_evidence": False,
    "would_create_mapping": False,
    "would_execute_trade": False,
    "would_create_client_signal": False,
    "would_create_client_opt_in": False,
}


def disabled_runtime_surfaces(**overrides: bool) -> dict[str, bool]:
    """Return the hard-disabled product surfaces shared by sensitive flows."""
    flags = dict(DISABLED_RUNTIME_SURFACES)
    flags.update(overrides)
    return flags


def confirm_required_detail(expected_confirm: str) -> str:
    return f"confirm_{expected_confirm}_required"


def dry_run_raw_data_collection_payload(
    *,
    status_key: str,
    status: str,
    action_type: str,
    confirm_required: str,
    params: Mapping[str, Any],
    would_call_rpc: bool,
    would_collect_raw_data: bool,
    would_update_wallet_aggregates: bool,
    source_policy: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "dry_run": True,
        status_key: status,
        "ingest_type": action_type,
        "params": dict(params),
        "confirm_required": confirm_required,
        "would_call_rpc": would_call_rpc,
        "would_collect_raw_data": would_collect_raw_data,
        "would_update_wallet_aggregates": would_update_wallet_aggregates,
        **disabled_runtime_surfaces(),
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
