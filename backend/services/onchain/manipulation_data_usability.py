from __future__ import annotations

import sqlite3
from typing import Any


def _engine():
    from services import onchain_engine

    return onchain_engine


def _get_db() -> sqlite3.Connection:
    return _engine()._get_db()


def _load_token_metadata_cache(conn: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    return _engine()._load_token_metadata_cache(conn)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return _engine()._table_exists(conn, table_name)


def _token_metadata_for(chain: Any, token_address: Any, metadata_cache: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    return _engine()._token_metadata_for(chain, token_address, metadata_cache)


def get_swap_identity_readiness(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_swap_identity_readiness(*args, **kwargs)


def get_token_market_local_candidate_discovery_radar(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_token_market_local_candidate_discovery_radar(*args, **kwargs)


def get_adaptive_accumulation_breakout_scan(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_adaptive_accumulation_breakout_scan(*args, **kwargs)


def get_adaptive_accumulation_backtest(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_adaptive_accumulation_backtest(*args, **kwargs)


def get_adaptive_manipulation_case_file(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_adaptive_manipulation_case_file(*args, **kwargs)


def get_manipulation_detection_readiness(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _engine().get_manipulation_detection_readiness(*args, **kwargs)


def get_token_manipulation_data_usability_audit(
    limit: int = 10,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Read-only audit of whether local token/flow data is usable for manipulation research."""
    clean_limit = max(1, min(int(limit or 10), 25))
    top_blockers: list[str] = [] if dry_run else ["dry_run_required"]
    source_policy = (
        "admin-only read-only token manipulation data usability audit; reads local swaps, token_transfers, "
        "pair_tokens, wallet_chain_state and existing read-only diagnostics only; no providers, scraping, DB writes, "
        "labels, mappings, trades, wallet orders, client signals or opt-ins"
    )

    def _empty_payload(status: str, blockers: list[str]) -> dict[str, Any]:
        return {
            "ok": False,
            "dry_run": bool(dry_run),
            "audit_status": status,
            "usable_for_manipulation": False,
            "usable_for_client_signal": False,
            "summary": {
                "usable_for_manipulation": False,
                "research_only": True,
                "real_write_enabled": False,
            },
            "token_findings": [],
            "blockers": list(dict.fromkeys(blockers)),
            "source_policy": source_policy,
            "would_write": False,
            "real_write_enabled": False,
            "writes_performed": 0,
        }

    if top_blockers:
        return _empty_payload("blocked", top_blockers)

    infrastructure_coin_ids = {
        "binancecoin",
        "busd",
        "dai",
        "ethereum",
        "matic-network",
        "tether",
        "usd-coin",
    }

    metadata_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _token_meta(chain: Any, token_address: Any) -> dict[str, Any]:
        return _token_metadata_for(chain, token_address, metadata_cache)

    def _token_symbol(chain: Any, token_address: Any) -> str | None:
        meta = _token_meta(chain, token_address)
        raw = str(meta.get("symbol") or meta.get("coin_id") or "").strip()
        return raw.upper() if raw else None

    def _is_infrastructure_token(chain: Any, token_address: Any) -> bool:
        meta = _token_meta(chain, token_address)
        if not meta:
            return False
        coin_id = str(meta.get("coin_id") or "").strip().lower()
        symbol = str(meta.get("symbol") or "").strip().upper()
        return coin_id in infrastructure_coin_ids or symbol in {"WETH", "WBNB", "USDT", "USDC", "DAI", "BUSD"}

    table_counts = {
        "swaps": 0,
        "token_transfers": 0,
        "pair_tokens": 0,
        "token_metadata": 0,
        "wallet_chain_state": 0,
    }
    token_stats: dict[tuple[str, str], dict[str, Any]] = {}
    venue_summary: list[dict[str, Any]] = []
    amount_quality = {
        "zero_or_missing_amount_usd_rows": 0,
        "suspicious_large_amount_usd_rows": 0,
        "suspicious_large_amount_usd_threshold": 1_000_000,
        "suspicious_samples": [],
    }

    def _stat(chain: Any, token: Any) -> dict[str, Any] | None:
        clean_chain = str(chain or "").strip().lower()
        clean_token = str(token or "").strip().lower()
        if not clean_chain or not clean_token:
            return None
        key = (clean_chain, clean_token)
        if key not in token_stats:
            token_stats[key] = {
                "chain": clean_chain,
                "token_address": clean_token,
                "token_symbol": _token_symbol(clean_chain, clean_token),
                "is_infrastructure_token": _is_infrastructure_token(clean_chain, clean_token),
                "swap_appearances": 0,
                "exact_swap_appearances": 0,
                "legacy_swap_appearances": 0,
                "transfer_rows": 0,
                "pair_rows": 0,
                "wallets": set(),
                "pools": set(),
                "routers": set(),
                "venues": set(),
                "amount_usd_sum": 0.0,
                "first_timestamp": None,
                "last_timestamp": None,
            }
        return token_stats[key]

    def _touch_time(row: dict[str, Any], timestamp: Any) -> None:
        try:
            ts = int(timestamp or 0)
        except (TypeError, ValueError):
            return
        if ts <= 0:
            return
        first = row.get("first_timestamp")
        last = row.get("last_timestamp")
        row["first_timestamp"] = ts if not first or ts < int(first) else first
        row["last_timestamp"] = ts if not last or ts > int(last) else last

    conn = _get_db()
    conn.row_factory = sqlite3.Row
    try:
        metadata_cache = _load_token_metadata_cache(conn)
        for table in table_counts:
            if _table_exists(conn, table):
                table_counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)

        if _table_exists(conn, "swaps"):
            amount_quality["zero_or_missing_amount_usd_rows"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM swaps WHERE COALESCE(amount_usd, 0) <= 0"
                ).fetchone()[0]
                or 0
            )
            amount_quality["suspicious_large_amount_usd_rows"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM swaps WHERE COALESCE(amount_usd, 0) > ?",
                    (amount_quality["suspicious_large_amount_usd_threshold"],),
                ).fetchone()[0]
                or 0
            )
            amount_quality["suspicious_samples"] = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT chain, tx_hash, token_in, token_out, amount_usd, token_identity_quality, pool, router_addr
                    FROM swaps
                    WHERE COALESCE(amount_usd, 0) > ?
                    ORDER BY amount_usd DESC
                    LIMIT 5
                    """,
                    (amount_quality["suspicious_large_amount_usd_threshold"],),
                ).fetchall()
            ]
            venue_summary = [
                {
                    "chain": row["chain"],
                    "venue": row["dex"] or "Unknown DEX",
                    "venue_source": row["venue_source"] or "unknown",
                    "venue_confidence": round(float(row["venue_confidence"] or 0), 3),
                    "swaps": int(row["swaps"] or 0),
                    "routers": int(row["routers"] or 0),
                    "pools": int(row["pools"] or 0),
                    "usable_for_manipulation": bool(float(row["venue_confidence"] or 0) >= 0.7),
                }
                for row in conn.execute(
                    """
                    SELECT chain, COALESCE(dex, '') AS dex, COALESCE(venue_source, '') AS venue_source,
                           COALESCE(venue_confidence, 0) AS venue_confidence, COUNT(*) AS swaps,
                           COUNT(DISTINCT COALESCE(router_addr, '')) AS routers,
                           COUNT(DISTINCT COALESCE(pool, '')) AS pools
                    FROM swaps
                    GROUP BY chain, dex, venue_source, venue_confidence
                    ORDER BY swaps DESC
                    LIMIT 20
                    """
                ).fetchall()
            ]
            for row in conn.execute(
                """
                SELECT chain, token_in, token_out, wallet, pool, router_addr, dex,
                       token_identity_quality, amount_usd, timestamp
                FROM swaps
                WHERE chain IS NOT NULL
                LIMIT 10000
                """
            ).fetchall():
                for token_key in ("token_in", "token_out"):
                    stat = _stat(row["chain"], row[token_key])
                    if not stat:
                        continue
                    stat["swap_appearances"] += 1
                    if row["token_identity_quality"] == "exact_pair_log_direction":
                        stat["exact_swap_appearances"] += 1
                    elif row["token_identity_quality"] == "legacy_inferred_pair_tokens":
                        stat["legacy_swap_appearances"] += 1
                    if row["wallet"]:
                        stat["wallets"].add(str(row["wallet"]).lower())
                    if row["pool"]:
                        stat["pools"].add(str(row["pool"]).lower())
                    if row["router_addr"]:
                        stat["routers"].add(str(row["router_addr"]).lower())
                    if row["dex"]:
                        stat["venues"].add(str(row["dex"]))
                    try:
                        stat["amount_usd_sum"] += float(row["amount_usd"] or 0)
                    except (TypeError, ValueError):
                        pass
                    _touch_time(stat, row["timestamp"])

        if _table_exists(conn, "pair_tokens"):
            for row in conn.execute(
                """
                SELECT chain, pool, token0, token1, observed_at
                FROM pair_tokens
                WHERE chain IS NOT NULL
                LIMIT 10000
                """
            ).fetchall():
                for token_key in ("token0", "token1"):
                    stat = _stat(row["chain"], row[token_key])
                    if not stat:
                        continue
                    stat["pair_rows"] += 1
                    if row["pool"]:
                        stat["pools"].add(str(row["pool"]).lower())
                    _touch_time(stat, row["observed_at"])

        if _table_exists(conn, "token_transfers"):
            for row in conn.execute(
                """
                SELECT chain, token, from_addr, to_addr, timestamp
                FROM token_transfers
                WHERE chain IS NOT NULL
                LIMIT 10000
                """
            ).fetchall():
                stat = _stat(row["chain"], row["token"])
                if not stat:
                    continue
                stat["transfer_rows"] += 1
                if row["from_addr"]:
                    stat["wallets"].add(str(row["from_addr"]).lower())
                if row["to_addr"]:
                    stat["wallets"].add(str(row["to_addr"]).lower())
                _touch_time(stat, row["timestamp"])
    finally:
        conn.close()

    token_findings: list[dict[str, Any]] = []
    for stat in token_stats.values():
        observations = int(stat["swap_appearances"] or 0) + int(stat["transfer_rows"] or 0) + int(stat["pair_rows"] or 0)
        token_blockers: list[str] = []
        if stat["is_infrastructure_token"]:
            token_blockers.append("infrastructure_token_not_manipulation_target")
        if not stat["token_symbol"]:
            token_blockers.append("token_symbol_missing")
        if int(stat["swap_appearances"] or 0) < 12:
            token_blockers.append("too_few_swap_observations")
        if int(stat["exact_swap_appearances"] or 0) < 5:
            token_blockers.append("too_few_exact_swap_observations")
        if int(stat["transfer_rows"] or 0) < 5:
            token_blockers.append("too_few_transfer_observations")
        if len(stat["wallets"]) < 3:
            token_blockers.append("too_few_distinct_wallets")
        if len(stat["pools"]) < 2:
            token_blockers.append("too_few_distinct_pools")
        history_days = 0.0
        if stat.get("first_timestamp") and stat.get("last_timestamp"):
            history_days = round(max(0, int(stat["last_timestamp"]) - int(stat["first_timestamp"])) / 86400, 2)
        if history_days < 3:
            token_blockers.append("token_history_too_short")
        token_findings.append({
            "chain": stat["chain"],
            "token_address": stat["token_address"],
            "token_symbol": stat["token_symbol"],
            "is_infrastructure_token": bool(stat["is_infrastructure_token"]),
            "observations": observations,
            "swap_appearances": int(stat["swap_appearances"] or 0),
            "exact_swap_appearances": int(stat["exact_swap_appearances"] or 0),
            "legacy_swap_appearances": int(stat["legacy_swap_appearances"] or 0),
            "transfer_rows": int(stat["transfer_rows"] or 0),
            "pair_rows": int(stat["pair_rows"] or 0),
            "distinct_wallets": len(stat["wallets"]),
            "distinct_pools": len(stat["pools"]),
            "distinct_routers": len(stat["routers"]),
            "distinct_venues": len(stat["venues"]),
            "amount_usd_sum": round(float(stat["amount_usd_sum"] or 0), 6),
            "history_days": history_days,
            "first_timestamp": stat.get("first_timestamp"),
            "last_timestamp": stat.get("last_timestamp"),
            "research_status": "research_lead_only" if token_blockers else "locally_interesting_not_source_backed",
            "usable_for_manipulation": False,
            "blockers": list(dict.fromkeys(token_blockers)),
            "next_data_need": (
                "identify_token_symbol_and_source_then_collect_more_exact_swaps_transfers"
                if not stat["token_symbol"]
                else "collect_more_exact_swaps_transfers_and_backtest_history"
            ),
        })
    token_findings.sort(
        key=lambda row: (
            int(row.get("observations") or 0),
            int(row.get("exact_swap_appearances") or 0),
            int(row.get("distinct_wallets") or 0),
            int(row.get("distinct_pools") or 0),
        ),
        reverse=True,
    )

    def _read_diag(name: str, fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            payload = fn(*args, **kwargs)
            return payload if isinstance(payload, dict) else {"payload": payload}
        except Exception as exc:
            top_blockers.append(f"{name}_read_failed:{type(exc).__name__}")
            return {"ok": False, "error": type(exc).__name__, "message": str(exc)[:300]}

    swap_identity = _read_diag("swap_identity", get_swap_identity_readiness)
    token_radar = _read_diag("token_market_local_candidate_discovery_radar", get_token_market_local_candidate_discovery_radar, clean_limit, True)
    adaptive_scan = _read_diag("adaptive_accumulation_breakout_scan", get_adaptive_accumulation_breakout_scan, limit=clean_limit)
    adaptive_backtest = _read_diag("adaptive_accumulation_backtest", get_adaptive_accumulation_backtest, limit=clean_limit)
    case_file = _read_diag("adaptive_manipulation_case_file", get_adaptive_manipulation_case_file, limit=clean_limit)
    manipulation = _read_diag("manipulation_detection_readiness", get_manipulation_detection_readiness, limit=12)

    swap_summary = swap_identity.get("summary") or {}
    radar_summary = token_radar.get("summary") or {}
    adaptive_summary = adaptive_scan.get("summary") or {}
    backtest_summary = adaptive_backtest.get("summary") or {}
    case_summary = case_file.get("summary") or {}
    manipulation_summary = manipulation.get("summary") or {}

    total_swaps = int(swap_summary.get("total_swaps") or table_counts["swaps"] or 0)
    exact_swaps = int(swap_summary.get("exact_swap_token_rows") or 0)
    transfer_rows = int(manipulation_summary.get("token_transfer_rows") or table_counts["token_transfers"] or 0)
    swap_history_days = float(swap_summary.get("swap_history_days") or manipulation_summary.get("swap_history_days") or 0)
    source_backed_candidates = int(radar_summary.get("source_backed_candidates") or 0)
    adaptive_candidates = int(adaptive_summary.get("adaptive_breakout_candidates") or 0)
    backtested_candidates = int(backtest_summary.get("candidates_backtested") or 0)
    case_files = int(case_summary.get("case_files") or 0)
    unknown_venue_swaps = int(manipulation_summary.get("unknown_venue_swaps") or 0)
    unknown_router_contracts = int(manipulation_summary.get("unknown_router_contracts") or 0)
    strict_label_pct = float(manipulation_summary.get("strict_label_pct") or 0)
    wallet_label_source_pct = float(manipulation_summary.get("wallet_label_source_pct") or 0)
    unknown_symbol_tokens = sum(1 for row in token_findings if not row.get("token_symbol"))
    infrastructure_token_rows = sum(1 for row in token_findings if row.get("is_infrastructure_token"))

    hard_blockers: list[str] = []
    if total_swaps < 1000:
        hard_blockers.append("swap_count_below_manipulation_baseline")
    if exact_swaps < 100:
        hard_blockers.append("exact_swap_rows_below_manipulation_baseline")
    if transfer_rows < 500:
        hard_blockers.append("token_transfer_rows_below_manipulation_baseline")
    if swap_history_days < 14:
        hard_blockers.append("swap_history_too_short_for_manipulation")
    if source_backed_candidates <= 0:
        hard_blockers.append("source_backed_token_candidates_missing")
    if adaptive_candidates <= 0:
        hard_blockers.append("adaptive_candidates_missing")
    if backtested_candidates <= 0:
        hard_blockers.append("backtest_candidates_missing")
    if case_files <= 0:
        hard_blockers.append("manipulation_case_files_missing")
    if unknown_venue_swaps > 0:
        hard_blockers.append("unknown_venue_swaps_block_signal_quality")
    if unknown_router_contracts > 0:
        hard_blockers.append("unknown_router_contracts_block_signal_quality")
    if unknown_symbol_tokens > 0:
        hard_blockers.append("token_symbol_identity_missing")
    if int(amount_quality.get("suspicious_large_amount_usd_rows") or 0) > 0:
        hard_blockers.append("amount_usd_normalization_risk")
    if strict_label_pct < 20:
        hard_blockers.append("strict_label_coverage_too_low")
    if wallet_label_source_pct < 95:
        hard_blockers.append("wallet_label_source_evidence_incomplete")

    all_blockers = list(dict.fromkeys([*top_blockers, *hard_blockers]))
    usable_for_manipulation = not all_blockers
    audit_status = "usable_for_research_not_manipulation" if all_blockers else "usable_for_manipulation_research_thresholds_met"
    if not token_findings:
        audit_status = "blocked_no_token_observations"
        all_blockers = list(dict.fromkeys([*all_blockers, "no_token_observations_found"]))
        usable_for_manipulation = False

    next_data_actions = [
        {
            "action_id": "audit_amount_usd_normalization",
            "priority": 10,
            "why": "BSC amount_usd has suspicious large values; profit/backtest logic cannot trust it yet.",
            "mode": "read_only_or_dry_run_first",
        },
        {
            "action_id": "identify_top_unknown_token_symbols",
            "priority": 20,
            "why": "Most local leads are token addresses without symbol/source identity.",
            "mode": "read_only_source_plan_first",
        },
        {
            "action_id": "repair_unknown_router_venue_attribution",
            "priority": 30,
            "why": "Unknown venues and routers prevent grouping flows by DEX/protocol.",
            "mode": "read_only_then_confirmed_mapping_only",
        },
        {
            "action_id": "expand_exact_swap_and_transfer_history",
            "priority": 40,
            "why": "Manipulation scans need more exact token direction, transfers and days of comparable history.",
            "mode": "bounded_ingestion_plan_then_confirmed_data_collection",
        },
        {
            "action_id": "rerun_adaptive_scan_backtest_casefile",
            "priority": 50,
            "why": "Only after data depth improves should adaptive candidates, backtests and case files be trusted.",
            "mode": "read_only",
        },
    ]

    return {
        "ok": True,
        "dry_run": True,
        "audit_status": audit_status,
        "usable_for_manipulation": bool(usable_for_manipulation),
        "usable_for_client_signal": False,
        "usable_for_trade": False,
        "summary": {
            "usable_for_manipulation": bool(usable_for_manipulation),
            "research_only": not bool(usable_for_manipulation),
            "tokens_observed": len(token_findings),
            "unknown_symbol_tokens": unknown_symbol_tokens,
            "infrastructure_tokens_seen": infrastructure_token_rows,
            "local_leads_returned": int(radar_summary.get("returned_leads") or 0),
            "source_backed_candidates": source_backed_candidates,
            "total_swaps": total_swaps,
            "exact_swap_token_rows": exact_swaps,
            "legacy_inferred_swap_token_rows": int(swap_summary.get("legacy_inferred_swap_token_rows") or 0),
            "token_transfer_rows": transfer_rows,
            "swap_history_days": swap_history_days,
            "adaptive_breakout_candidates": adaptive_candidates,
            "backtest_candidates": backtested_candidates,
            "case_files": case_files,
            "unknown_venue_swaps": unknown_venue_swaps,
            "unknown_router_contracts": unknown_router_contracts,
            "strict_label_pct": strict_label_pct,
            "wallet_label_source_pct": wallet_label_source_pct,
            "real_write_enabled": False,
        },
        "thresholds": {
            "min_swaps": 1000,
            "min_exact_swaps": 100,
            "min_token_transfers": 500,
            "min_swap_history_days": 14,
            "min_strict_label_pct": 20,
            "min_wallet_label_source_pct": 95,
            "requires_source_backed_token_candidates": True,
            "requires_adaptive_backtest_casefile": True,
        },
        "table_counts": table_counts,
        "amount_quality": amount_quality,
        "venue_summary": venue_summary,
        "token_findings": token_findings[:clean_limit],
        "research_usable_now": [
            "prioritize_unknown_token_identity_repair",
            "prioritize_router_venue_repair",
            "plan_exact_swap_transfer_collection",
            "calibrate_which_data_gaps_block_manipulation",
        ],
        "not_usable_for": [
            "client_signal",
            "trade_execution",
            "copy_trade",
            "profit_claim",
            "final_manipulation_verdict",
        ],
        "diagnostics": {
            "token_market_radar": {
                "radar_status": token_radar.get("radar_status"),
                "summary": radar_summary,
                "blockers": token_radar.get("blockers") or [],
            },
            "swap_identity": {
                "summary": swap_summary,
                "blockers": swap_identity.get("blockers") or [],
            },
            "adaptive_scan": {
                "summary": adaptive_summary,
                "blockers": adaptive_scan.get("blockers") or [],
            },
            "adaptive_backtest": {
                "summary": backtest_summary,
                "blockers": adaptive_backtest.get("blockers") or [],
            },
            "manipulation_case_file": {
                "summary": case_summary,
                "blockers": case_file.get("blockers") or [],
            },
            "manipulation_readiness": {
                "status": manipulation.get("status"),
                "score": manipulation.get("signal_readiness_score"),
                "summary": manipulation_summary,
                "blockers": manipulation.get("blockers") or [],
            },
        },
        "blockers": all_blockers,
        "next_data_actions": next_data_actions,
        "source_policy": source_policy,
        "plain_summary_fr": (
            "La data actuelle sert a orienter la recherche, pas a detecter une manipulation exploitable. "
            "Il manque des symboles/source token, plus de swaps exacts, plus de transferts, plus d'historique "
            "et une meilleure attribution router/venue."
        ),
        "would_insert_candidate": False,
        "would_persist_evidence": False,
        "would_apply_label_source": False,
        "would_create_cex_label": False,
        "would_create_dex_router_evidence": False,
        "would_create_mapping": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_signal": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "next_safe_step": "amount_usd_normalization_and_token_identity_audit_read_only",
    }
