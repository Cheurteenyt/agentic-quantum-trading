from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from typing import Any


def _engine():
    from services import onchain_engine

    return onchain_engine


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone())


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    if not _table_exists(conn, name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _clean_address(value: Any) -> str:
    clean = str(value or "").strip().lower()
    if clean.startswith("0x") and len(clean) == 42:
        return clean
    return ""


def _parse_addresses(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [part.strip() for part in value.replace("\n", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    addresses: list[str] = []
    seen: set[str] = set()
    for item in raw_values:
        address = _clean_address(item)
        if address and address not in seen:
            addresses.append(address)
            seen.add(address)
    return addresses


def _window_density(rows: list[sqlite3.Row], window_seconds: int) -> int:
    timestamps = sorted(_as_int(row["block_timestamp"]) for row in rows if _as_int(row["block_timestamp"]))
    if not timestamps:
        blocks = sorted(_as_int(row["block_number"]) for row in rows if _as_int(row["block_number"]))
        best_blocks = 0
        left = 0
        for right, block in enumerate(blocks):
            while block - blocks[left] > 20:
                left += 1
            best_blocks = max(best_blocks, right - left + 1)
        return best_blocks
    best = 0
    left = 0
    for right, ts in enumerate(timestamps):
        while ts - timestamps[left] > window_seconds:
            left += 1
        best = max(best, right - left + 1)
    return best


def _span_minutes(rows: list[sqlite3.Row]) -> float | None:
    timestamps = [_as_int(row["block_timestamp"]) for row in rows if _as_int(row["block_timestamp"])]
    if timestamps:
        return round((max(timestamps) - min(timestamps)) / 60.0, 4)
    blocks = [_as_int(row["block_number"]) for row in rows if _as_int(row["block_number"])]
    if blocks:
        return round((max(blocks) - min(blocks)) * 3.0 / 60.0, 4)
    return None


def _participant_concentration(participants: list[str]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for wallet in participants:
        if wallet:
            counts[wallet] = counts.get(wallet, 0) + 1
    total = sum(counts.values())
    if not total:
        return {"top_wallet": None, "top_wallet_events": 0, "top_wallet_event_share_pct": 0.0}
    top_wallet, top_count = max(counts.items(), key=lambda item: item[1])
    return {
        "top_wallet": top_wallet,
        "top_wallet_events": top_count,
        "top_wallet_event_share_pct": round((top_count / total) * 100, 4),
    }


def _raw_json_timestamp(row: sqlite3.Row) -> int:
    try:
        payload = json.loads(str(row["raw_log_json"] or "{}"))
    except (TypeError, ValueError, KeyError):
        return 0
    if isinstance(payload, dict):
        log = payload.get("log")
        if isinstance(log, dict):
            return _as_int(log.get("timestamp"))
        return _as_int(payload.get("timestamp"))
    return 0


def _pct_change(start: Decimal | None, end: Decimal | None) -> float | None:
    if start is None or end is None or start <= 0:
        return None
    return round(float(((end - start) / start) * Decimal(100)), 4)


def _quote_token_info(chain: str, token0: str, token1: str) -> dict[str, Any]:
    stable_or_native = {
        "bsc": {
            "0x55d398326f99059ff775485246999027b3197955": "USDT",
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": "USDC",
            "0xe9e7cea3dedca5984780bafc599bd69add087d56": "BUSD",
            "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": "WBNB",
        },
    }
    known = stable_or_native.get(chain, {})
    if token0 in known and token1:
        return {"quote_token": token0, "target_token": token1, "quote_symbol": known[token0]}
    if token1 in known and token0:
        return {"quote_token": token1, "target_token": token0, "quote_symbol": known[token1]}
    return {"quote_token": token0, "target_token": token1, "quote_symbol": None}


def _token_meta(conn: sqlite3.Connection, chain: str, token: str) -> dict[str, Any]:
    if not token or not _table_exists(conn, "token_metadata"):
        return {}
    row = conn.execute(
        """
        SELECT symbol, name, decimals, status
        FROM token_metadata
        WHERE lower(chain)=? AND lower(token_address)=?
        LIMIT 1
        """,
        (chain, token),
    ).fetchone()
    return dict(row) if row else {}


def _scale(decimals: Any) -> Decimal:
    try:
        clean = int(decimals if decimals is not None else 18)
    except (TypeError, ValueError):
        clean = 18
    return Decimal(10) ** max(0, min(clean, 36))


def _price_points_from_raw_context(
    conn: sqlite3.Connection,
    chain: str,
    pool: str,
    swap_rows: list[sqlite3.Row],
    sync_rows: list[sqlite3.Row],
) -> dict[str, Any]:
    token0 = ""
    token1 = ""
    if _table_exists(conn, "pair_tokens"):
        pair = conn.execute(
            """
            SELECT token0, token1
            FROM pair_tokens
            WHERE lower(chain)=? AND lower(pool)=?
            LIMIT 1
            """,
            (chain, pool),
        ).fetchone()
        if pair:
            token0 = _clean_address(pair["token0"])
            token1 = _clean_address(pair["token1"])
    quote_info = _quote_token_info(chain, token0, token1)
    quote_token = str(quote_info.get("quote_token") or "")
    target_token = str(quote_info.get("target_token") or "")
    token0_meta = _token_meta(conn, chain, token0)
    token1_meta = _token_meta(conn, chain, token1)
    token0_decimals = _as_int(token0_meta.get("decimals")) or 18
    token1_decimals = _as_int(token1_meta.get("decimals")) or 18
    target_meta = token1_meta if target_token == token1 else token0_meta
    quote_meta = token0_meta if quote_token == token0 else token1_meta
    token0_scale = _scale(token0_decimals)
    token1_scale = _scale(token1_decimals)
    points: list[dict[str, Any]] = []
    for row in swap_rows:
        amount0_in = _as_decimal(row["amount0_in"]) / token0_scale
        amount1_in = _as_decimal(row["amount1_in"]) / token1_scale
        amount0_out = _as_decimal(row["amount0_out"]) / token0_scale
        amount1_out = _as_decimal(row["amount1_out"]) / token1_scale
        price: Decimal | None = None
        quote_volume = Decimal(0)
        side = "unknown"
        if target_token == token1 and quote_token == token0:
            if amount0_in > 0 and amount1_out > 0:
                price = amount0_in / amount1_out
                quote_volume = amount0_in
                side = "buy_target"
            elif amount1_in > 0 and amount0_out > 0:
                price = amount0_out / amount1_in
                quote_volume = amount0_out
                side = "sell_target"
        elif target_token == token0 and quote_token == token1:
            if amount1_in > 0 and amount0_out > 0:
                price = amount1_in / amount0_out
                quote_volume = amount1_in
                side = "buy_target"
            elif amount0_in > 0 and amount1_out > 0:
                price = amount1_out / amount0_in
                quote_volume = amount1_out
                side = "sell_target"
        if price and price > 0:
            points.append({
                "point_source": "swap",
                "block_number": _as_int(row["block_number"]),
                "block_timestamp": _as_int(row["block_timestamp"]),
                "tx_hash": row["tx_hash"],
                "log_index": row["log_index"],
                "price_quote_per_target": price,
                "quote_liquidity_proxy": None,
                "quote_volume": quote_volume,
                "side": side,
            })
    for row in sync_rows:
        reserve0 = _as_decimal(row["reserve0"]) / token0_scale
        reserve1 = _as_decimal(row["reserve1"]) / token1_scale
        price = None
        quote_liquidity = None
        if target_token == token1 and quote_token == token0 and reserve1 > 0:
            price = reserve0 / reserve1
            quote_liquidity = reserve0
        elif target_token == token0 and quote_token == token1 and reserve0 > 0:
            price = reserve1 / reserve0
            quote_liquidity = reserve1
        if price and price > 0:
            points.append({
                "point_source": "sync",
                "block_number": _as_int(row["block_number"]),
                "block_timestamp": _raw_json_timestamp(row),
                "tx_hash": row["tx_hash"],
                "log_index": row["log_index"],
                "price_quote_per_target": price,
                "quote_liquidity_proxy": quote_liquidity,
                "quote_volume": Decimal(0),
                "side": "reserve_snapshot",
            })
    points.sort(key=lambda item: (_as_int(item.get("block_timestamp")) or 0, _as_int(item.get("block_number")), _as_int(item.get("log_index"))))
    return {
        "token0": token0,
        "token1": token1,
        "target_token": target_token,
        "target_symbol": target_meta.get("symbol"),
        "target_decimals": token1_decimals if target_token == token1 else token0_decimals,
        "quote_token": quote_token,
        "quote_symbol": quote_info.get("quote_symbol") or quote_meta.get("symbol"),
        "quote_decimals": token0_decimals if quote_token == token0 else token1_decimals,
        "price_points": points,
    }


def _wallet_state_summary(conn: sqlite3.Connection, chain: str, wallets: list[str]) -> dict[str, Any]:
    unique_wallets = sorted({wallet for wallet in wallets if wallet})
    if not unique_wallets or not _table_exists(conn, "wallet_chain_state"):
        return {
            "wallets_checked": len(unique_wallets),
            "wallet_state_rows": 0,
            "fresh_like_wallets": 0,
            "contract_wallets": 0,
            "missing_wallet_state": len(unique_wallets),
            "fresh_wallet_status": "not_enough_wallet_state",
        }
    placeholders = ",".join("?" for _ in unique_wallets)
    rows = conn.execute(
        f"""
        SELECT address, tx_count, activity_tier, is_contract, risk_flags_json, label, entity
        FROM wallet_chain_state
        WHERE lower(chain)=? AND lower(address) IN ({placeholders})
        """,
        [chain, *unique_wallets],
    ).fetchall()
    fresh_like = 0
    contract_wallets = 0
    for row in rows:
        tx_count = _as_int(row["tx_count"])
        activity_tier = str(row["activity_tier"] or "").lower()
        risk_flags = str(row["risk_flags_json"] or "").lower()
        if tx_count <= 5 or activity_tier in {"fresh", "new", "low"} or "fresh" in risk_flags:
            fresh_like += 1
        if _as_int(row["is_contract"]):
            contract_wallets += 1
    return {
        "wallets_checked": len(unique_wallets),
        "wallet_state_rows": len(rows),
        "fresh_like_wallets": fresh_like,
        "contract_wallets": contract_wallets,
        "missing_wallet_state": max(0, len(unique_wallets) - len(rows)),
        "fresh_wallet_status": "observed" if rows else "not_enough_wallet_state",
    }


def _funder_graph_preview(conn: sqlite3.Connection, chain: str, wallets: list[str]) -> dict[str, Any]:
    unique_wallets = sorted({wallet for wallet in wallets if wallet})
    if not unique_wallets or not _table_exists(conn, "transactions"):
        return {
            "funding_graph_status": "needs_funder_graph_collection",
            "shared_funders": 0,
            "funded_wallets": 0,
            "top_funder": None,
        }
    placeholders = ",".join("?" for _ in unique_wallets)
    rows = conn.execute(
        f"""
        SELECT lower(from_addr) AS funder, COUNT(DISTINCT lower(to_addr)) AS funded_wallets, COUNT(*) AS tx_rows
        FROM transactions
        WHERE lower(chain)=? AND lower(to_addr) IN ({placeholders})
        GROUP BY lower(from_addr)
        HAVING COUNT(DISTINCT lower(to_addr)) >= 2
        ORDER BY funded_wallets DESC, tx_rows DESC
        LIMIT 5
        """,
        [chain, *unique_wallets],
    ).fetchall()
    top = rows[0] if rows else None
    return {
        "funding_graph_status": "shared_funder_observed" if rows else "needs_funder_graph_collection",
        "shared_funders": len(rows),
        "funded_wallets": _as_int(top["funded_wallets"]) if top else 0,
        "top_funder": top["funder"] if top else None,
        "top_funder_tx_rows": _as_int(top["tx_rows"]) if top else 0,
    }


def _score_raw_context_candidate(
    conn: sqlite3.Connection,
    chain: str,
    pool: str,
    swap_rows: list[sqlite3.Row],
    sync_rows: list[sqlite3.Row],
    transfer_rows: list[sqlite3.Row],
) -> dict[str, Any]:
    swap_wallets = [
        wallet
        for row in swap_rows
        for wallet in (_clean_address(row["sender"]), _clean_address(row["recipient"]))
        if wallet and wallet != pool
    ]
    transfer_wallets = [
        wallet
        for row in transfer_rows
        for wallet in (_clean_address(row["from_address"]), _clean_address(row["to_address"]))
        if wallet and wallet != pool and wallet != "0x0000000000000000000000000000000000000000"
    ]
    all_wallets = sorted(set(swap_wallets + transfer_wallets))
    wallet_state = _wallet_state_summary(conn, chain, all_wallets)
    funder_graph = _funder_graph_preview(conn, chain, all_wallets)
    density_5m = _window_density(swap_rows, 5 * 60)
    density_15m = _window_density(swap_rows, 15 * 60)
    span = _span_minutes(swap_rows)
    concentration = _participant_concentration(swap_wallets + transfer_wallets)
    reserve0_values = [_as_decimal(row["reserve0"]) for row in sync_rows if str(row["reserve0"] or "")]
    reserve1_values = [_as_decimal(row["reserve1"]) for row in sync_rows if str(row["reserve1"] or "")]
    reserve_samples = min(len(reserve0_values), len(reserve1_values))
    reserve_shift_observed = bool(
        reserve_samples >= 2
        and (
            reserve0_values[0] != reserve0_values[-1]
            or reserve1_values[0] != reserve1_values[-1]
        )
    )
    transfer_in = sum(1 for row in transfer_rows if _clean_address(row["to_address"]) == pool)
    transfer_out = sum(1 for row in transfer_rows if _clean_address(row["from_address"]) == pool)
    unique_swap_txs = len({str(row["tx_hash"] or "").lower() for row in swap_rows if row["tx_hash"]})
    unique_blocks = len({_as_int(row["block_number"]) for row in swap_rows if _as_int(row["block_number"])})
    score = 0
    factors: list[str] = []
    if len(swap_rows) >= 10:
        score += min(18, len(swap_rows) // 3)
        factors.append("repeatable_exact_swaps")
    if unique_swap_txs >= 10:
        score += 10
        factors.append("many_distinct_swap_txs")
    if density_5m >= 10:
        score += 18
        factors.append("dense_grouped_buy_timing")
    elif density_15m >= 10:
        score += 10
        factors.append("grouped_buy_timing")
    if concentration["top_wallet_event_share_pct"] >= 35:
        score += 12
        factors.append("wallet_concentration")
    if transfer_in >= 10:
        score += 10
        factors.append("transfer_context_into_pool")
    if transfer_out >= 5:
        score += 8
        factors.append("transfer_context_out_of_pool")
    if reserve_shift_observed:
        score += 10
        factors.append("sync_liquidity_context_observed")
    if wallet_state["fresh_like_wallets"] >= 2:
        score += min(18, wallet_state["fresh_like_wallets"] * 4)
        factors.append("fresh_like_wallets_observed")
    if funder_graph["shared_funders"]:
        score += min(14, funder_graph["shared_funders"] * 7)
        factors.append("shared_funder_graph_hint")
    if transfer_out == 0:
        factors.append("dump_outcome_not_observed_yet")
    if wallet_state["wallet_state_rows"] == 0:
        score -= 8
        factors.append("wallet_state_missing_penalty")
    if not funder_graph["shared_funders"]:
        score -= 6
        factors.append("funder_graph_missing_penalty")
    score = max(0, min(100, int(score)))
    anomaly_tier = (
        "strong_behavioral_anomaly_candidate" if score >= 75 else
        "moderate_behavioral_anomaly_candidate" if score >= 50 else
        "weak_behavioral_anomaly_context"
    )
    next_step = (
        "shadow_outcome_backtest_next"
        if score >= 75 else
        "collect_wallet_state_and_funder_graph_next"
        if wallet_state["wallet_state_rows"] < max(1, len(all_wallets) // 3) or not funder_graph["shared_funders"] else
        "collect_outcome_dump_window_next"
    )
    return {
        "chain": chain,
        "pool_address": pool,
        "behavioral_anomaly_score": score,
        "behavioral_anomaly_tier": anomaly_tier,
        "score_factors": factors,
        "raw_context_counts": {
            "swap_rows": len(swap_rows),
            "sync_rows": len(sync_rows),
            "transfer_rows": len(transfer_rows),
            "unique_swap_txs": unique_swap_txs,
            "unique_swap_blocks": unique_blocks,
            "unique_wallets": len(all_wallets),
        },
        "timing": {
            "swap_span_minutes": span,
            "max_swaps_in_5m_or_20_blocks": density_5m,
            "max_swaps_in_15m_or_20_blocks": density_15m,
        },
        "concentration": concentration,
        "fresh_wallets": wallet_state,
        "funding_graph": funder_graph,
        "sync_liquidity_context": {
            "sync_rows": len(sync_rows),
            "reserve_samples": reserve_samples,
            "reserve_shift_observed": reserve_shift_observed,
        },
        "transfer_context": {
            "transfer_rows": len(transfer_rows),
            "transfer_in_to_pool_rows": transfer_in,
            "transfer_out_from_pool_rows": transfer_out,
            "transfer_context_status": "observed" if transfer_rows else "missing",
        },
        "repeatability": {
            "repeatability_status": "observed" if len(swap_rows) >= 10 and unique_swap_txs >= 10 else "too_thin",
            "exact_swaps_observed": len(swap_rows),
        },
        "dump_outcome": {
            "dump_outcome_status": "needs_shadow_outcome_window",
            "dump_observed_from_raw_context": bool(transfer_out >= 5),
        },
        "official_identity": {
            "official_identity_required_for_behavioral_score": False,
            "official_identity_still_required_for_mapping": True,
            "source_identity_status": "separate_from_behavioral_scoring",
        },
        "next_safe_step": next_step,
        "blockers": [
            *([] if len(swap_rows) >= 10 else ["too_few_raw_swaps"]),
            *([] if transfer_rows else ["transfer_context_missing"]),
            *([] if sync_rows else ["sync_liquidity_context_missing"]),
            *([] if wallet_state["wallet_state_rows"] else ["wallet_state_missing"]),
            *([] if funder_graph["shared_funders"] else ["funder_graph_missing_or_too_thin"]),
            "source_identity_separate_from_behavioral_score",
            "shadow_outcome_backtest_required_before_signal",
            "client_signal_disabled",
            "trade_disabled",
        ],
    }


def get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    token_addresses: list[str] | str | None = None,
) -> dict[str, Any]:
    """Score persisted top-expansion raw events as behavioral anomalies, without identity/mapping writes."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_pool = _clean_address(pool_address)
    clean_limit = max(1, min(int(limit or 3), 10))
    explicit_tokens = _parse_addresses(token_addresses)
    source_policy = (
        "admin-only read-only behavioral anomaly scoring preview over persisted top-expansion raw Swap, Sync "
        "and ERC20 Transfer context. It scores behavior only; official/source identity remains a separate gate. "
        "No mapping, label, client signal, trade, wallet order or opt-in is created."
    )
    disabled = {
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    candidates: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        required_tables = ["dex_raw_swap_events", "dex_raw_sync_events", "erc20_transfer_events"]
        missing_tables = [table for table in required_tables if not _table_exists(conn, table)]
        if missing_tables:
            blockers.extend(f"{table}_missing" for table in missing_tables)
        if not blockers:
            if clean_pool:
                pool_rows = [{"pool_address": clean_pool, "raw_rows": 0}]
            elif explicit_tokens:
                token_placeholders = ",".join("?" for _ in explicit_tokens)
                pool_rows = conn.execute(
                    f"""
                    SELECT lower(d.pair_address) AS pool_address, COUNT(*) AS raw_rows
                    FROM dex_raw_swap_events d
                    JOIN pair_tokens p
                      ON lower(p.chain)=lower(d.chain)
                     AND lower(p.pool)=lower(d.pair_address)
                    WHERE lower(d.chain)=?
                      AND (lower(p.token0) IN ({token_placeholders}) OR lower(p.token1) IN ({token_placeholders}))
                    GROUP BY lower(d.pair_address)
                    ORDER BY raw_rows DESC, pool_address ASC
                    LIMIT ?
                    """,
                    (clean_chain, *explicit_tokens, *explicit_tokens, clean_limit),
                ).fetchall()
            else:
                pool_rows = conn.execute(
                    """
                    SELECT pair_address AS pool_address, COUNT(*) AS raw_rows
                    FROM dex_raw_swap_events
                    WHERE lower(chain)=? AND source_policy LIKE '%top expansion raw context%'
                    GROUP BY pair_address
                    ORDER BY raw_rows DESC, pair_address ASC
                    LIMIT ?
                    """,
                    (clean_chain, clean_limit),
                ).fetchall()
            for pool_row in pool_rows:
                pool = _clean_address(pool_row["pool_address"])
                if not pool:
                    continue
                raw_source_filter = "" if explicit_tokens or clean_pool else "AND source_policy LIKE '%top expansion raw context%'"
                swap_rows = conn.execute(
                    f"""
                    SELECT *
                    FROM dex_raw_swap_events
                    WHERE lower(chain)=? AND lower(pair_address)=?
                      {raw_source_filter}
                    ORDER BY block_number ASC, log_index ASC
                    LIMIT 1000
                    """,
                    (clean_chain, pool),
                ).fetchall()
                sync_rows = conn.execute(
                    f"""
                    SELECT *
                    FROM dex_raw_sync_events
                    WHERE lower(chain)=? AND lower(pair_address)=?
                      {raw_source_filter}
                    ORDER BY block_number ASC, log_index ASC
                    LIMIT 1000
                    """,
                    (clean_chain, pool),
                ).fetchall()
                price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
                target_token = _clean_address(price_context.get("target_token"))
                if explicit_tokens and target_token not in explicit_tokens:
                    continue
                if explicit_tokens:
                    transfer_rows = conn.execute(
                        """
                        SELECT *
                        FROM erc20_transfer_events
                        WHERE lower(chain)=? AND lower(token_address)=?
                        ORDER BY block_number ASC, log_index ASC
                        LIMIT 1000
                        """,
                        (clean_chain, target_token),
                    ).fetchall() if target_token and _table_exists(conn, "erc20_transfer_events") else []
                else:
                    transfer_rows = conn.execute(
                        """
                        SELECT *
                        FROM erc20_transfer_events
                        WHERE lower(chain)=?
                          AND source_policy LIKE '%top expansion raw context%'
                          AND (lower(from_address)=? OR lower(to_address)=?)
                        ORDER BY block_number ASC, log_index ASC
                        LIMIT 1000
                        """,
                        (clean_chain, pool, pool),
                    ).fetchall()
                candidate = _score_raw_context_candidate(conn, clean_chain, pool, swap_rows, sync_rows, transfer_rows)
                candidate.update({
                    "token0": price_context.get("token0"),
                    "token1": price_context.get("token1"),
                    "target_token": target_token or None,
                    "target_symbol": price_context.get("target_symbol"),
                    "quote_token": price_context.get("quote_token"),
                    "quote_symbol": price_context.get("quote_symbol"),
                    "explicit_token_filter": bool(explicit_tokens),
                })
                candidates.append(candidate)
        if not candidates and not blockers:
            blockers.append("no_top_expansion_raw_context_candidates_found")
    finally:
        conn.close()

    strong = [row for row in candidates if _as_int(row.get("behavioral_anomaly_score")) >= 75]
    moderate = [row for row in candidates if 50 <= _as_int(row.get("behavioral_anomaly_score")) < 75]
    preview_digest = _digest({
        "chain": clean_chain,
        "candidates": [
            {
                "pool_address": row.get("pool_address"),
                "behavioral_anomaly_score": row.get("behavioral_anomaly_score"),
                "raw_context_counts": row.get("raw_context_counts"),
            }
            for row in candidates
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "pool_address": clean_pool or None,
        "token_addresses": explicit_tokens,
        "explicit_filter": bool(explicit_tokens),
        "behavioral_anomaly_preview_digest": preview_digest,
        "summary": {
            "candidates_scored": len(candidates),
            "strong_behavioral_anomaly_candidates": len(strong),
            "moderate_behavioral_anomaly_candidates": len(moderate),
            "max_behavioral_anomaly_score": max([_as_int(row.get("behavioral_anomaly_score")) for row in candidates] or [0]),
            "official_identity_required_for_behavioral_score": False,
            "official_identity_still_required_for_mapping": True,
            "source_backed_scoring_ready": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "candidates": candidates,
        "policy_separation": {
            "behavioral_score_can_run_without_official_docs": True,
            "mapping_and_client_signal_still_require_separate_policy": True,
            "accepted_as": "research_priority_and_shadow_backtest_input",
            "not_accepted_as": ["DEX mapping", "client signal", "trade authorization"],
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_strong_behavioral_anomaly_candidate" for _ in [1] if candidates and not strong),
            "official_identity_separate_from_behavioral_score",
            "shadow_outcome_backtest_required_before_signal",
            "client_signal_disabled",
            "trade_disabled",
            "client_opt_in_missing",
        ])),
        "next_safe_step": (
            "shadow_outcome_backtest_for_strong_candidates_read_only"
            if strong else
            "collect_wallet_state_funder_graph_or_more_raw_context_next"
        ),
        "plain_summary_fr": (
            "Cette preview note le comportement observe dans les 437 raw events top-expansion. "
            "Elle peut classer une anomalie sans attendre des docs officielles, mais elle ne cree aucun mapping, "
            "signal client ou trade."
        ),
        **disabled,
    }


def get_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    score_threshold: int = 75,
    entry_slippage_bps: int = 400,
    exit_slippage_bps: int = 400,
    mev_penalty_bps: int = 200,
) -> dict[str, Any]:
    """Read-only economic outcome preview for strong behavioral top-expansion candidates."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_pool = _clean_address(pool_address)
    clean_limit = max(1, min(int(limit or 3), 10))
    safe_threshold = max(1, min(int(score_threshold or 75), 100))
    safe_entry_bps = max(0, min(int(entry_slippage_bps or 0), 5_000))
    safe_exit_bps = max(0, min(int(exit_slippage_bps or 0), 5_000))
    safe_mev_bps = max(0, min(int(mev_penalty_bps or 0), 5_000))
    total_friction_bps = safe_entry_bps + safe_exit_bps + safe_mev_bps
    source_policy = (
        "admin-only read-only behavioral shadow outcome/backtest plan. It uses local persisted top-expansion "
        "raw Swap/Sync/Transfer events only, estimates T0, MFE, MAE, liquidity proxy and friction-adjusted "
        "outcome, and creates no mapping, label, client signal, trade, wallet order or opt-in."
    )
    disabled = {
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidate_outcomes": [],
            **disabled,
        }

    scoring = get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        limit=clean_limit,
        dry_run=True,
    )
    scored_candidates = [
        row for row in list(scoring.get("candidates") or [])
        if _as_int(row.get("behavioral_anomaly_score")) >= safe_threshold
    ]
    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    candidate_outcomes: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        for scored in scored_candidates:
            pool = _clean_address(scored.get("pool_address"))
            if not pool:
                continue
            swap_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                LIMIT 1000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_swap_events") else []
            sync_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_number ASC, log_index ASC
                LIMIT 1000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_sync_events") else []
            price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
            points = list(price_context.get("price_points") or [])
            row_blockers: list[str] = []
            if len(points) < 10:
                row_blockers.append("too_few_price_points_for_shadow_outcome_min_10")
            if not price_context.get("quote_token"):
                row_blockers.append("quote_token_missing")
            if not price_context.get("target_token"):
                row_blockers.append("target_token_missing")
            detection_index = min(max(9, len(points) // 5), len(points) - 1) if points else -1
            t0 = points[detection_index] if detection_index >= 0 else None
            window_defs = [
                ("plus_1h", 3600),
                ("plus_4h", 14_400),
                ("plus_12h", 43_200),
                ("plus_24h", 86_400),
            ]
            windows: list[dict[str, Any]] = []
            if t0:
                t0_ts = _as_int(t0.get("block_timestamp"))
                t0_block = _as_int(t0.get("block_number"))
                entry_price = t0.get("price_quote_per_target")
                for label, seconds in window_defs:
                    if t0_ts:
                        window_points = [
                            point for point in points
                            if _as_int(point.get("block_timestamp")) >= t0_ts
                            and _as_int(point.get("block_timestamp")) <= t0_ts + seconds
                        ]
                    else:
                        max_blocks = max(1, seconds // 3)
                        window_points = [
                            point for point in points
                            if _as_int(point.get("block_number")) >= t0_block
                            and _as_int(point.get("block_number")) <= t0_block + max_blocks
                        ]
                    prices = [point.get("price_quote_per_target") for point in window_points if point.get("price_quote_per_target")]
                    liquidity_values = [
                        point.get("quote_liquidity_proxy")
                        for point in window_points
                        if point.get("quote_liquidity_proxy") is not None
                    ]
                    if not prices or not entry_price:
                        windows.append({
                            "window_label": label,
                            "status": "blocked",
                            "price_points": len(window_points),
                            "blockers": ["no_price_points_in_window"],
                        })
                        continue
                    high = max(prices)
                    low = min(prices)
                    end = prices[-1]
                    max_favorable = _pct_change(entry_price, high)
                    max_adverse = _pct_change(entry_price, low)
                    net = _pct_change(entry_price, end)
                    max_favorable_after_friction = (
                        round(float(max_favorable) - (total_friction_bps / 100.0), 4)
                        if max_favorable is not None else None
                    )
                    windows.append({
                        "window_label": label,
                        "status": "measured" if len(window_points) >= 2 else "thin",
                        "price_points": len(window_points),
                        "entry_price": float(entry_price),
                        "price_high": float(high),
                        "price_low": float(low),
                        "price_end": float(end),
                        "mfe_pct": max_favorable,
                        "mae_pct": max_adverse,
                        "net_move_pct": net,
                        "friction_adjusted_mfe_pct": max_favorable_after_friction,
                        "quote_liquidity_proxy_min": float(min(liquidity_values)) if liquidity_values else None,
                        "quote_liquidity_proxy_at_end": float(liquidity_values[-1]) if liquidity_values else None,
                        "liquidity_proxy_status": "observed_from_sync" if liquidity_values else "missing_sync_liquidity_proxy",
                        "blockers": [
                            *([] if len(window_points) >= 2 else ["too_few_points_in_window"]),
                            *([] if liquidity_values else ["liquidity_proxy_missing"]),
                        ],
                    })
            measured = [row for row in windows if row.get("status") in {"measured", "thin"}]
            mfe_values = [row.get("mfe_pct") for row in measured if row.get("mfe_pct") is not None]
            mae_values = [row.get("mae_pct") for row in measured if row.get("mae_pct") is not None]
            friction_values = [
                row.get("friction_adjusted_mfe_pct")
                for row in measured
                if row.get("friction_adjusted_mfe_pct") is not None
            ]
            best_friction_mfe = max(friction_values) if friction_values else None
            exploitable = bool(
                best_friction_mfe is not None
                and best_friction_mfe >= 25
                and (min(mae_values) if mae_values else 0) >= -45
                and any(row.get("quote_liquidity_proxy_min") for row in measured)
            )
            if not measured:
                row_blockers.append("no_measured_outcome_windows")
            if best_friction_mfe is None or best_friction_mfe < 25:
                row_blockers.append("friction_adjusted_mfe_below_research_threshold")
            if mae_values and min(mae_values) < -45:
                row_blockers.append("max_adverse_excursion_too_deep")
            if not any(row.get("quote_liquidity_proxy_min") for row in measured):
                row_blockers.append("liquidity_depth_proxy_missing")
            row_blockers.extend([
                "token_tax_honeypot_check_missing",
                "negative_controls_missing",
                "policy_risk_gate_missing",
                "client_signal_disabled",
                "trade_disabled",
            ])
            candidate_outcomes.append({
                "pool_address": pool,
                "behavioral_anomaly_score": scored.get("behavioral_anomaly_score"),
                "behavioral_anomaly_tier": scored.get("behavioral_anomaly_tier"),
                "target_token": price_context.get("target_token"),
                "target_symbol": price_context.get("target_symbol"),
                "quote_token": price_context.get("quote_token"),
                "quote_symbol": price_context.get("quote_symbol"),
                "t0_detection": {
                    "method": "conservative_after_initial_behavioral_cluster_points",
                    "point_index": detection_index,
                    "block_number": t0.get("block_number") if t0 else None,
                    "block_timestamp": t0.get("block_timestamp") if t0 else None,
                    "price_quote_per_target": float(t0.get("price_quote_per_target")) if t0 else None,
                },
                "friction_model": {
                    "entry_slippage_bps": safe_entry_bps,
                    "exit_slippage_bps": safe_exit_bps,
                    "mev_penalty_bps": safe_mev_bps,
                    "total_friction_bps": total_friction_bps,
                    "token_tax_status": "unknown_requires_contract_check",
                },
                "windows": windows,
                "outcome_summary": {
                    "measured_windows": len(measured),
                    "max_favorable_move_pct": max(mfe_values) if mfe_values else None,
                    "max_adverse_move_pct": min(mae_values) if mae_values else None,
                    "best_friction_adjusted_mfe_pct": best_friction_mfe,
                    "economically_exploitable_shadow_candidate": exploitable,
                    "can_claim_alpha_now": False,
                },
                "blockers": list(dict.fromkeys(row_blockers)),
                "next_safe_step": (
                    "negative_controls_and_tax_liquidity_checks_read_only"
                    if exploitable else
                    "collect_more_outcome_or_contract_tax_context_read_only"
                ),
            })
    finally:
        conn.close()

    if not scored_candidates:
        blockers.append("no_behavioral_candidates_above_threshold")
    exploitable_candidates = [
        row for row in candidate_outcomes
        if (row.get("outcome_summary") or {}).get("economically_exploitable_shadow_candidate")
    ]
    plan_digest = _digest({
        "chain": clean_chain,
        "score_threshold": safe_threshold,
        "candidate_outcomes": [
            {
                "pool_address": row.get("pool_address"),
                "score": row.get("behavioral_anomaly_score"),
                "summary": row.get("outcome_summary"),
            }
            for row in candidate_outcomes
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled" if candidate_outcomes else "blocked",
        "chain": clean_chain,
        "score_threshold": safe_threshold,
        "behavioral_scoring_snapshot": {
            "preview_status": scoring.get("preview_status"),
            "summary": scoring.get("summary"),
            "digest": scoring.get("behavioral_anomaly_preview_digest"),
        },
        "shadow_outcome_backtest_plan_digest": plan_digest,
        "candidate_outcomes": candidate_outcomes,
        "summary": {
            "strong_candidates_selected": len(scored_candidates),
            "candidate_outcomes": len(candidate_outcomes),
            "economically_exploitable_shadow_candidates": len(exploitable_candidates),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_economically_exploitable_shadow_candidate_yet" for _ in [1] if candidate_outcomes and not exploitable_candidates),
            "negative_controls_missing",
            "token_tax_honeypot_checks_missing",
            "policy_risk_gate_missing",
            "client_opt_in_missing",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "negative_controls_and_contract_tax_checks_read_only"
            if exploitable_candidates else
            "collect_more_outcome_or_contract_tax_context_read_only"
        ),
        "plain_summary_fr": (
            "Ce plan teste si les anomalies comportementales fortes auraient eu une valeur economique apres T0. "
            "Il mesure MFE, MAE, liquidite proxy et frictions, mais ne cree aucun signal ou trade."
        ),
        **disabled,
    }


def _sell_observation_from_swap(row: sqlite3.Row, price_context: dict[str, Any]) -> dict[str, Any] | None:
    token0 = str(price_context.get("token0") or "")
    token1 = str(price_context.get("token1") or "")
    target_token = str(price_context.get("target_token") or "")
    quote_token = str(price_context.get("quote_token") or "")
    token0_scale = _scale(price_context.get("target_decimals") if target_token == token0 else price_context.get("quote_decimals"))
    token1_scale = _scale(price_context.get("target_decimals") if target_token == token1 else price_context.get("quote_decimals"))
    amount0_in = _as_decimal(row["amount0_in"]) / token0_scale
    amount1_in = _as_decimal(row["amount1_in"]) / token1_scale
    amount0_out = _as_decimal(row["amount0_out"]) / token0_scale
    amount1_out = _as_decimal(row["amount1_out"]) / token1_scale
    target_in = Decimal(0)
    quote_out = Decimal(0)
    if target_token == token1 and quote_token == token0 and amount1_in > 0 and amount0_out > 0:
        target_in = amount1_in
        quote_out = amount0_out
    elif target_token == token0 and quote_token == token1 and amount0_in > 0 and amount1_out > 0:
        target_in = amount0_in
        quote_out = amount1_out
    if target_in <= 0 or quote_out <= 0:
        return None
    return {
        "tx_hash": row["tx_hash"],
        "log_index": _as_int(row["log_index"]),
        "block_number": _as_int(row["block_number"]),
        "block_timestamp": _as_int(row["block_timestamp"]),
        "sender": _clean_address(row["sender"]),
        "recipient": _clean_address(row["recipient"]),
        "target_in": target_in,
        "quote_out": quote_out,
        "quote_per_target": quote_out / target_in if target_in > 0 else Decimal(0),
    }


def _swap_flow_from_raw_context(row: sqlite3.Row, price_context: dict[str, Any]) -> dict[str, Any] | None:
    token0 = str(price_context.get("token0") or "")
    token1 = str(price_context.get("token1") or "")
    target_token = str(price_context.get("target_token") or "")
    quote_token = str(price_context.get("quote_token") or "")
    token0_scale = _scale(price_context.get("target_decimals") if target_token == token0 else price_context.get("quote_decimals"))
    token1_scale = _scale(price_context.get("target_decimals") if target_token == token1 else price_context.get("quote_decimals"))
    amount0_in = _as_decimal(row["amount0_in"]) / token0_scale
    amount1_in = _as_decimal(row["amount1_in"]) / token1_scale
    amount0_out = _as_decimal(row["amount0_out"]) / token0_scale
    amount1_out = _as_decimal(row["amount1_out"]) / token1_scale
    side = "unknown"
    quote_amount = Decimal(0)
    target_amount = Decimal(0)
    if target_token == token1 and quote_token == token0:
        if amount0_in > 0 and amount1_out > 0:
            side = "buy_target"
            quote_amount = amount0_in
            target_amount = amount1_out
        elif amount1_in > 0 and amount0_out > 0:
            side = "sell_target"
            quote_amount = amount0_out
            target_amount = amount1_in
    elif target_token == token0 and quote_token == token1:
        if amount1_in > 0 and amount0_out > 0:
            side = "buy_target"
            quote_amount = amount1_in
            target_amount = amount0_out
        elif amount0_in > 0 and amount1_out > 0:
            side = "sell_target"
            quote_amount = amount1_out
            target_amount = amount0_in
    if side == "unknown" or quote_amount <= 0 or target_amount <= 0:
        return None
    return {
        "side": side,
        "tx_hash": row["tx_hash"],
        "log_index": _as_int(row["log_index"]),
        "block_number": _as_int(row["block_number"]),
        "block_timestamp": _as_int(row["block_timestamp"]),
        "sender": _clean_address(row["sender"]),
        "recipient": _clean_address(row["recipient"]),
        "quote_amount": quote_amount,
        "target_amount": target_amount,
    }


def _directional_intent_from_flows(
    pool: str,
    price_context: dict[str, Any],
    swap_rows: list[sqlite3.Row],
    sync_rows: list[sqlite3.Row],
    transfer_rows: list[sqlite3.Row],
) -> dict[str, Any]:
    flows = [
        flow for flow in (
            _swap_flow_from_raw_context(row, price_context) for row in swap_rows
        )
        if flow
    ]
    buy_flows = [flow for flow in flows if flow.get("side") == "buy_target"]
    sell_flows = [flow for flow in flows if flow.get("side") == "sell_target"]
    quote_buy = sum((flow["quote_amount"] for flow in buy_flows), Decimal(0))
    quote_sell = sum((flow["quote_amount"] for flow in sell_flows), Decimal(0))
    target_buy = sum((flow["target_amount"] for flow in buy_flows), Decimal(0))
    target_sell = sum((flow["target_amount"] for flow in sell_flows), Decimal(0))
    total_quote_volume = quote_buy + quote_sell
    net_quote_spent = quote_buy - quote_sell
    net_target_accumulated = target_buy - target_sell
    hold_freeze_proxy_pct = (
        round(float((net_target_accumulated / target_buy) * Decimal(100)), 4)
        if target_buy > 0 and net_target_accumulated > 0 else 0.0
    )

    circular_events = 0
    recent: list[tuple[int, str]] = []
    unique_participants: set[str] = set()
    for flow in flows:
        block = _as_int(flow.get("block_number"))
        participants = {
            wallet for wallet in (flow.get("sender"), flow.get("recipient"))
            if wallet and wallet != pool and wallet != "0x0000000000000000000000000000000000000000"
        }
        unique_participants.update(participants)
        recent = [(seen_block, wallet) for seen_block, wallet in recent if block - seen_block <= 10]
        recent_wallets = {wallet for _, wallet in recent}
        if participants and participants & recent_wallets:
            circular_events += 1
        recent.extend((block, wallet) for wallet in participants)
    circularity_ratio_pct = round((circular_events / len(flows)) * 100, 4) if flows else 0.0

    price_context_points = _price_points_from_raw_context_dummy_points(price_context)
    liquidity_values = [point.get("quote_liquidity_proxy") for point in price_context_points if point.get("quote_liquidity_proxy") is not None]
    if not liquidity_values:
        sync_context = _price_points_from_raw_context_no_conn(price_context, sync_rows)
        liquidity_values = [point.get("quote_liquidity_proxy") for point in sync_context if point.get("quote_liquidity_proxy") is not None]
    reserve_delta = abs(liquidity_values[-1] - liquidity_values[0]) if len(liquidity_values) >= 2 else None
    amm_impact_vs_volume_pct = (
        round(float((reserve_delta / total_quote_volume) * Decimal(100)), 4)
        if reserve_delta is not None and total_quote_volume > 0 else None
    )

    transfer_to_pool = sum(1 for row in transfer_rows if _clean_address(row["to_address"]) == pool)
    transfer_from_pool = sum(1 for row in transfer_rows if _clean_address(row["from_address"]) == pool)
    buy_sell_ratio = float(quote_buy / quote_sell) if quote_sell > 0 else None
    blockers: list[str] = []
    if not flows:
        blockers.append("swap_flow_rows_missing")
    if amm_impact_vs_volume_pct is None:
        blockers.append("amm_impact_sync_proxy_missing")
    if len(unique_participants) < 3:
        blockers.append("too_few_distinct_flow_participants")

    intent = "insufficient_context"
    if flows:
        if circularity_ratio_pct >= 60 and (amm_impact_vs_volume_pct is None or amm_impact_vs_volume_pct < 5):
            intent = "wash_trading_or_circular_volume"
        elif quote_sell > quote_buy or net_target_accumulated <= 0:
            intent = "distribution_or_sell_pressure"
        elif hold_freeze_proxy_pct >= 70 and quote_buy > quote_sell * Decimal("1.5"):
            intent = "accumulation_candidate"
        elif quote_buy > quote_sell:
            intent = "weak_accumulation_needs_more_holding_context"
        else:
            intent = "balanced_internal_flow"

    return {
        "intent_classification": intent,
        "flow_counts": {
            "swap_flows": len(flows),
            "buy_target_flows": len(buy_flows),
            "sell_target_flows": len(sell_flows),
            "unique_flow_participants": len(unique_participants),
            "transfer_to_pool_rows": transfer_to_pool,
            "transfer_from_pool_rows": transfer_from_pool,
        },
        "net_cluster_flow": {
            "quote_buy_amount": str(quote_buy),
            "quote_sell_amount": str(quote_sell),
            "net_quote_spent": str(net_quote_spent),
            "target_bought_amount": str(target_buy),
            "target_sold_amount": str(target_sell),
            "net_target_accumulated": str(net_target_accumulated),
            "buy_sell_quote_ratio": buy_sell_ratio,
        },
        "hold_freeze_proxy": {
            "hold_freeze_proxy_pct": hold_freeze_proxy_pct,
            "status": "proxy_only_needs_24h_holder_snapshot" if target_buy > 0 else "missing",
        },
        "circularity": {
            "circularity_ratio_pct": circularity_ratio_pct,
            "circular_events_10_block_window": circular_events,
            "status": "high_circularity" if circularity_ratio_pct >= 60 else "not_high",
        },
        "amm_impact_vs_volume": {
            "total_quote_volume": str(total_quote_volume),
            "quote_reserve_delta": str(reserve_delta) if reserve_delta is not None else None,
            "amm_impact_vs_volume_pct": amm_impact_vs_volume_pct,
            "status": (
                "low_impact_high_volume_proxy" if amm_impact_vs_volume_pct is not None and amm_impact_vs_volume_pct < 5 else
                "impact_observed" if amm_impact_vs_volume_pct is not None else
                "missing_sync_proxy"
            ),
        },
        "blockers": blockers,
    }


def _price_points_from_raw_context_dummy_points(price_context: dict[str, Any]) -> list[dict[str, Any]]:
    return list(price_context.get("price_points") or [])


def _price_points_from_raw_context_no_conn(price_context: dict[str, Any], sync_rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    token0 = str(price_context.get("token0") or "")
    target_token = str(price_context.get("target_token") or "")
    quote_token = str(price_context.get("quote_token") or "")
    token0_scale = _scale(price_context.get("target_decimals") if target_token == token0 else price_context.get("quote_decimals"))
    token1_scale = _scale(price_context.get("target_decimals") if target_token != token0 else price_context.get("quote_decimals"))
    points: list[dict[str, Any]] = []
    for row in sync_rows:
        reserve0 = _as_decimal(row["reserve0"]) / token0_scale
        reserve1 = _as_decimal(row["reserve1"]) / token1_scale
        quote_liquidity = None
        if target_token and quote_token:
            quote_liquidity = reserve0 if quote_token == price_context.get("token0") else reserve1
        if quote_liquidity is not None:
            points.append({"quote_liquidity_proxy": quote_liquidity})
    return points


def _parse_thresholds(raw: str | None) -> list[int]:
    values: list[int] = []
    for part in str(raw or "40,50,60,70,82").split(","):
        clean = part.strip()
        if not clean:
            continue
        try:
            value = int(clean)
        except ValueError:
            continue
        if 1 <= value <= 100 and value not in values:
            values.append(value)
    return sorted(values) or [40, 50, 60, 70, 82]


def _row_position(row: sqlite3.Row) -> tuple[int, int, int]:
    return (_as_int(row["block_timestamp"]), _as_int(row["block_number"]), _as_int(row["log_index"]))


def _rows_up_to_position(rows: list[sqlite3.Row], position: tuple[int, int, int], has_timestamp: bool = True) -> list[sqlite3.Row]:
    pos_ts, pos_block, pos_log = position
    selected: list[sqlite3.Row] = []
    for row in rows:
        row_ts = _as_int(row["block_timestamp"]) if has_timestamp and "block_timestamp" in row.keys() else 0
        row_block = _as_int(row["block_number"])
        row_log = _as_int(row["log_index"])
        if pos_ts and row_ts:
            if (row_ts, row_block, row_log) <= position:
                selected.append(row)
        elif (row_block, row_log) <= (pos_block, pos_log):
            selected.append(row)
    return selected


def _entry_point_for_position(points: list[dict[str, Any]], position: tuple[int, int, int]) -> dict[str, Any] | None:
    pos_ts, pos_block, pos_log = position
    for point in points:
        point_ts = _as_int(point.get("block_timestamp"))
        point_block = _as_int(point.get("block_number"))
        point_log = _as_int(point.get("log_index"))
        if pos_ts and point_ts:
            if (point_ts, point_block, point_log) >= position:
                return point
        elif (point_block, point_log) >= (pos_block, pos_log):
            return point
    return points[-1] if points else None


def _last_liquidity_before_position(points: list[dict[str, Any]], position: tuple[int, int, int]) -> Decimal | None:
    pos_ts, pos_block, pos_log = position
    latest: Decimal | None = None
    for point in points:
        liquidity = point.get("quote_liquidity_proxy")
        if liquidity is None:
            continue
        point_ts = _as_int(point.get("block_timestamp"))
        point_block = _as_int(point.get("block_number"))
        point_log = _as_int(point.get("log_index"))
        before = (point_ts, point_block, point_log) <= position if pos_ts and point_ts else (point_block, point_log) <= (pos_block, pos_log)
        if before:
            latest = liquidity
    return latest


def _outcome_after_entry(
    points: list[dict[str, Any]],
    entry_point: dict[str, Any],
    total_friction_bps: int,
) -> dict[str, Any]:
    entry_price = entry_point.get("price_quote_per_target")
    if not entry_price:
        return {
            "status": "blocked",
            "blockers": ["entry_price_missing"],
        }
    entry_ts = _as_int(entry_point.get("block_timestamp"))
    entry_block = _as_int(entry_point.get("block_number"))
    entry_log = _as_int(entry_point.get("log_index"))
    if entry_ts:
        future_points = [
            point for point in points
            if (
                _as_int(point.get("block_timestamp")),
                _as_int(point.get("block_number")),
                _as_int(point.get("log_index")),
            ) >= (entry_ts, entry_block, entry_log)
        ]
    else:
        future_points = [
            point for point in points
            if (
                _as_int(point.get("block_number")),
                _as_int(point.get("log_index")),
            ) >= (entry_block, entry_log)
        ]
    prices = [point.get("price_quote_per_target") for point in future_points if point.get("price_quote_per_target")]
    liquidity_values = [
        point.get("quote_liquidity_proxy")
        for point in future_points
        if point.get("quote_liquidity_proxy") is not None
    ]
    if not prices:
        return {
            "status": "blocked",
            "blockers": ["no_future_price_points"],
        }
    high = max(prices)
    low = min(prices)
    end = prices[-1]
    mfe = _pct_change(entry_price, high)
    mae = _pct_change(entry_price, low)
    net = _pct_change(entry_price, end)
    return {
        "status": "measured" if len(prices) >= 2 else "thin",
        "future_price_points": len(prices),
        "entry_price": float(entry_price),
        "price_high": float(high),
        "price_low": float(low),
        "price_end": float(end),
        "mfe_pct": mfe,
        "mae_pct": mae,
        "net_move_pct": net,
        "friction_adjusted_mfe_pct": round(float(mfe) - (total_friction_bps / 100.0), 4) if mfe is not None else None,
        "quote_liquidity_proxy_min": float(min(liquidity_values)) if liquidity_values else None,
        "quote_liquidity_proxy_at_end": float(liquidity_values[-1]) if liquidity_values else None,
        "blockers": [] if len(prices) >= 2 else ["too_few_future_price_points"],
    }


def _outcome_window_after_entry(
    points: list[dict[str, Any]],
    entry_point: dict[str, Any],
    window_seconds: int,
    total_friction_bps: int,
) -> dict[str, Any]:
    entry_price = entry_point.get("price_quote_per_target")
    if not entry_price:
        return {
            "status": "blocked",
            "blockers": ["entry_price_missing"],
        }
    entry_ts = _as_int(entry_point.get("block_timestamp"))
    entry_block = _as_int(entry_point.get("block_number"))
    entry_log = _as_int(entry_point.get("log_index"))
    if entry_ts:
        future_points = [
            point for point in points
            if (
                _as_int(point.get("block_timestamp")),
                _as_int(point.get("block_number")),
                _as_int(point.get("log_index")),
            ) >= (entry_ts, entry_block, entry_log)
            and _as_int(point.get("block_timestamp")) <= entry_ts + window_seconds
        ]
    else:
        max_blocks = max(1, window_seconds // 3)
        future_points = [
            point for point in points
            if (
                _as_int(point.get("block_number")),
                _as_int(point.get("log_index")),
            ) >= (entry_block, entry_log)
            and _as_int(point.get("block_number")) <= entry_block + max_blocks
        ]
    prices = [point.get("price_quote_per_target") for point in future_points if point.get("price_quote_per_target")]
    liquidity_values = [
        point.get("quote_liquidity_proxy")
        for point in future_points
        if point.get("quote_liquidity_proxy") is not None
    ]
    if not prices:
        return {
            "status": "blocked",
            "future_price_points": 0,
            "blockers": ["no_future_price_points_in_window"],
        }
    high = max(prices)
    low = min(prices)
    end = prices[-1]
    mfe = _pct_change(entry_price, high)
    mae = _pct_change(entry_price, low)
    net = _pct_change(entry_price, end)
    return {
        "status": "measured" if len(prices) >= 2 else "thin",
        "future_price_points": len(prices),
        "entry_price": float(entry_price),
        "price_high": float(high),
        "price_low": float(low),
        "price_end": float(end),
        "mfe_pct": mfe,
        "mae_pct": mae,
        "net_move_pct": net,
        "friction_adjusted_mfe_pct": round(float(mfe) - (total_friction_bps / 100.0), 4) if mfe is not None else None,
        "quote_liquidity_proxy_min": float(min(liquidity_values)) if liquidity_values else None,
        "quote_liquidity_proxy_at_end": float(liquidity_values[-1]) if liquidity_values else None,
        "blockers": [] if len(prices) >= 2 else ["too_few_future_price_points"],
    }


def get_manipulation_detection_behavioral_score_pump_backtest_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 50,
    dry_run: bool = True,
    min_swaps: int = 10,
    min_behavioral_score: int = 60,
    entry_score_threshold: int = 70,
    entry_slippage_bps: int = 400,
    exit_slippage_bps: int = 400,
    mev_penalty_bps: int = 200,
) -> dict[str, Any]:
    """Read-only DEX pump hypothesis test for local behavioral-score candidates."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_pool = _clean_address(pool_address)
    clean_limit = max(1, min(int(limit or 50), 50))
    safe_min_swaps = max(1, min(int(min_swaps or 10), 10_000))
    safe_min_score = max(1, min(int(min_behavioral_score or 60), 100))
    safe_entry_threshold = max(1, min(int(entry_score_threshold or 70), 100))
    safe_entry_bps = max(0, min(int(entry_slippage_bps or 0), 5_000))
    safe_exit_bps = max(0, min(int(exit_slippage_bps or 0), 5_000))
    safe_mev_bps = max(0, min(int(mev_penalty_bps or 0), 5_000))
    total_friction_bps = safe_entry_bps + safe_exit_bps + safe_mev_bps
    source_policy = (
        "admin-only read-only behavioral score pump backtest preview. It reads local dex_raw_swap_events, "
        "dex_raw_sync_events, erc20_transfer_events, pair_tokens, token_metadata, wallet_chain_state and "
        "transactions only. It tests whether behavioral-score threshold crossings precede DEX MFE at J+7/J+14/J+30. "
        "It creates no labels, mappings, ground truth rows, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_call_provider": False,
        "would_scrape": False,
        "would_persist_backtest": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidate_backtests": [],
            **disabled,
        }

    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    candidate_backtests: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        required_tables = ["dex_raw_swap_events", "dex_raw_sync_events", "pair_tokens"]
        missing_tables = [table for table in required_tables if not _table_exists(conn, table)]
        if missing_tables:
            blockers.extend(f"{table}_missing" for table in missing_tables)
        pool_rows: list[sqlite3.Row | dict[str, Any]] = []
        if not missing_tables:
            if clean_pool:
                pool_rows = [{"pair_address": clean_pool, "swap_rows": 0}]
            else:
                pool_rows = conn.execute(
                    """
                    SELECT lower(pair_address) AS pair_address, COUNT(*) AS swap_rows
                    FROM dex_raw_swap_events
                    WHERE lower(chain)=?
                    GROUP BY lower(pair_address)
                    HAVING COUNT(*) >= ?
                    ORDER BY COUNT(*) DESC, lower(pair_address) ASC
                    LIMIT ?
                    """,
                    (clean_chain, safe_min_swaps, max(clean_limit * 5, clean_limit)),
                ).fetchall()
        for pool_row in pool_rows:
            pool = _clean_address(pool_row["pair_address"] if isinstance(pool_row, sqlite3.Row) else pool_row.get("pair_address"))
            if not pool:
                continue
            swap_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, pool),
            ).fetchall()
            if len(swap_rows) < safe_min_swaps:
                continue
            sync_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                ORDER BY block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, pool),
            ).fetchall()
            price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
            target_token = str(price_context.get("target_token") or "")
            transfer_rows = conn.execute(
                """
                SELECT *
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=?
                ORDER BY block_number ASC, log_index ASC
                LIMIT 4000
                """,
                (clean_chain, target_token),
            ).fetchall() if target_token and _table_exists(conn, "erc20_transfer_events") else []
            final_score_row = _score_raw_context_candidate(conn, clean_chain, pool, swap_rows, sync_rows, transfer_rows)
            final_score = _as_int(final_score_row.get("behavioral_anomaly_score"))
            if final_score < safe_min_score:
                continue
            points = list(price_context.get("price_points") or [])
            threshold_cross: dict[str, Any] | None = None
            score_curve_sample: list[dict[str, Any]] = []
            sample_indexes = {0, 1, 2, 4, 9, len(swap_rows) - 1}
            for index, swap in enumerate(swap_rows):
                position = _row_position(swap)
                prefix_swaps = swap_rows[: index + 1]
                prefix_syncs = _rows_up_to_position(sync_rows, position, has_timestamp=False)
                prefix_transfers = _rows_up_to_position(transfer_rows, position, has_timestamp=False)
                score_row = _score_raw_context_candidate(conn, clean_chain, pool, prefix_swaps, prefix_syncs, prefix_transfers)
                score = _as_int(score_row.get("behavioral_anomaly_score"))
                if index in sample_indexes:
                    score_curve_sample.append({
                        "swap_index": index,
                        "block_number": _as_int(swap["block_number"]),
                        "block_timestamp": _as_int(swap["block_timestamp"]),
                        "score": score,
                        "score_factors": score_row.get("score_factors"),
                    })
                if score >= safe_entry_threshold and threshold_cross is None:
                    entry_point = _entry_point_for_position(points, position)
                    entry_liquidity = _last_liquidity_before_position(points, position)
                    threshold_cross = {
                        "score_at_cross": score,
                        "swap_index": index,
                        "block_number": _as_int(swap["block_number"]),
                        "block_timestamp": _as_int(swap["block_timestamp"]),
                        "entry_point": entry_point,
                        "entry_liquidity_proxy": float(entry_liquidity) if entry_liquidity is not None else None,
                        "raw_context_at_cross": {
                            "swap_rows": len(prefix_swaps),
                            "sync_rows": len(prefix_syncs),
                            "transfer_rows": len(prefix_transfers),
                        },
                    }
                    break
            row_blockers: list[str] = []
            if not threshold_cross:
                row_blockers.append("entry_score_threshold_not_crossed")
            if not points:
                row_blockers.append("price_points_missing")
            if not sync_rows:
                row_blockers.append("sync_liquidity_context_missing")
            windows: list[dict[str, Any]] = []
            entry_point = (threshold_cross or {}).get("entry_point") if threshold_cross else None
            for label, seconds in (("plus_7d", 7 * 86_400), ("plus_14d", 14 * 86_400), ("plus_30d", 30 * 86_400)):
                outcome = _outcome_window_after_entry(points, entry_point, seconds, total_friction_bps) if entry_point else {
                    "status": "blocked",
                    "blockers": ["entry_point_missing"],
                }
                windows.append({
                    "window_label": label,
                    "window_seconds": seconds,
                    **outcome,
                })
            measured_windows = [row for row in windows if row.get("status") in {"measured", "thin"}]
            friction_values = [
                row.get("friction_adjusted_mfe_pct")
                for row in measured_windows
                if row.get("friction_adjusted_mfe_pct") is not None
            ]
            mfe_values = [
                row.get("mfe_pct")
                for row in measured_windows
                if row.get("mfe_pct") is not None
            ]
            mae_values = [
                row.get("mae_pct")
                for row in measured_windows
                if row.get("mae_pct") is not None
            ]
            best_friction_mfe = max(friction_values) if friction_values else None
            if not measured_windows:
                row_blockers.append("no_measured_outcome_windows")
            if best_friction_mfe is None or best_friction_mfe < 50:
                row_blockers.append("friction_adjusted_mfe_below_initial_edge_threshold")
            if not any(row.get("quote_liquidity_proxy_min") for row in measured_windows):
                row_blockers.append("liquidity_depth_proxy_missing")
            candidate_backtests.append({
                "pool_address": pool,
                "target_token": price_context.get("target_token"),
                "target_symbol": price_context.get("target_symbol"),
                "quote_token": price_context.get("quote_token"),
                "quote_symbol": price_context.get("quote_symbol"),
                "final_behavioral_score": final_score,
                "final_score_factors": final_score_row.get("score_factors"),
                "entry_score_threshold": safe_entry_threshold,
                "j0_detection": {
                    key: value for key, value in (threshold_cross or {}).items()
                    if key != "entry_point"
                },
                "score_curve_sample": score_curve_sample,
                "raw_context_counts": final_score_row.get("raw_context_counts"),
                "windows": windows,
                "outcome_summary": {
                    "measured_windows": len(measured_windows),
                    "max_mfe_pct": max(mfe_values) if mfe_values else None,
                    "max_adverse_move_pct": min(mae_values) if mae_values else None,
                    "best_friction_adjusted_mfe_pct": best_friction_mfe,
                    "dex_pump_edge_candidate": bool(best_friction_mfe is not None and best_friction_mfe >= 50),
                    "can_claim_alpha_now": False,
                },
                "blockers": list(dict.fromkeys([
                    *row_blockers,
                    "negative_controls_missing",
                    "token_tax_honeypot_checks_missing",
                    "policy_risk_gate_missing",
                    "client_signal_disabled",
                    "trade_disabled",
                ])),
            })
        candidate_backtests.sort(
            key=lambda row: (
                float((row.get("outcome_summary") or {}).get("best_friction_adjusted_mfe_pct") or -1_000_000),
                _as_int(row.get("final_behavioral_score")),
            ),
            reverse=True,
        )
        candidate_backtests = candidate_backtests[:clean_limit]
    finally:
        conn.close()

    measured_candidates = [
        row for row in candidate_backtests
        if (row.get("outcome_summary") or {}).get("measured_windows")
    ]
    edge_candidates = [
        row for row in candidate_backtests
        if (row.get("outcome_summary") or {}).get("dex_pump_edge_candidate")
    ]
    by_window: dict[str, dict[str, Any]] = {}
    for label in ("plus_7d", "plus_14d", "plus_30d"):
        values = [
            (window.get("friction_adjusted_mfe_pct"), window.get("mfe_pct"))
            for row in candidate_backtests
            for window in list(row.get("windows") or [])
            if window.get("window_label") == label and window.get("mfe_pct") is not None
        ]
        friction_values = [float(value[0]) for value in values if value[0] is not None]
        mfe_values = [float(value[1]) for value in values if value[1] is not None]
        by_window[label] = {
            "measured_candidates": len(mfe_values),
            "avg_mfe_pct": round(sum(mfe_values) / len(mfe_values), 4) if mfe_values else None,
            "avg_friction_adjusted_mfe_pct": round(sum(friction_values) / len(friction_values), 4) if friction_values else None,
            "max_friction_adjusted_mfe_pct": round(max(friction_values), 4) if friction_values else None,
        }
    preview_digest = _digest({
        "chain": clean_chain,
        "pool_address": clean_pool or None,
        "min_swaps": safe_min_swaps,
        "min_behavioral_score": safe_min_score,
        "entry_score_threshold": safe_entry_threshold,
        "candidate_backtests": [
            {
                "pool_address": row.get("pool_address"),
                "final_behavioral_score": row.get("final_behavioral_score"),
                "summary": row.get("outcome_summary"),
            }
            for row in candidate_backtests
        ],
    })
    if not candidate_backtests and not blockers:
        blockers.append("no_local_behavioral_score_candidates_with_outcome_context")
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled" if candidate_backtests else "blocked",
        "chain": clean_chain,
        "pool_address": clean_pool or None,
        "limit": clean_limit,
        "min_swaps": safe_min_swaps,
        "min_behavioral_score": safe_min_score,
        "entry_score_threshold": safe_entry_threshold,
        "friction_model": {
            "entry_slippage_bps": safe_entry_bps,
            "exit_slippage_bps": safe_exit_bps,
            "mev_penalty_bps": safe_mev_bps,
            "total_friction_bps": total_friction_bps,
        },
        "behavioral_score_pump_backtest_digest": preview_digest,
        "candidate_backtests": candidate_backtests,
        "summary": {
            "candidates_checked": len(candidate_backtests),
            "candidates_with_measured_outcomes": len(measured_candidates),
            "dex_pump_edge_candidates": len(edge_candidates),
            "window_metrics": by_window,
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_dex_pump_edge_candidate_in_local_sample" for _ in [1] if candidate_backtests and not edge_candidates),
            "negative_controls_missing",
            "token_tax_honeypot_checks_missing",
            "policy_risk_gate_missing",
            "client_opt_in_missing",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "negative_controls_and_tax_checks_for_pump_edge_candidates_read_only"
            if edge_candidates else
            "honeypot_correlation_scan_or_expand_outcome_sample_read_only"
        ),
        "plain_summary_fr": (
            "Cette preview teste l'hypothese simple: est-ce que le score comportemental predit un pump DEX "
            "a J+7/J+14/J+30? Elle mesure MFE/MAE/frictions en local seulement et ne cree aucun signal ou trade."
        ),
        **disabled,
    }


def get_manipulation_detection_honeypot_correlation_scan_preview(
    chain: str | None = "bsc",
    limit: int = 50,
    dry_run: bool = True,
    min_behavioral_score: int = 60,
    min_swaps: int = 10,
    use_honeypot: bool = True,
    use_goplus: bool = True,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Read-only correlation scan: does behavioral score predict honeypot/scam classification?"""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 50), 50))
    safe_min_score = max(1, min(int(min_behavioral_score or 60), 100))
    safe_min_swaps = max(1, min(int(min_swaps or 10), 10_000))
    safe_timeout = max(1, min(int(timeout_seconds or 10), 30))
    source_policy = (
        "admin-only read-only honeypot/scam correlation scan. It selects local pools with high behavioral "
        "scores, then runs bounded Honeypot.is/GoPlus checks through the existing security intake preview. "
        "It creates no blacklist, labels, mappings, ground-truth rows, client signals, trades, wallet orders or opt-ins."
    )
    disabled = {
        "would_call_unbounded_provider": False,
        "would_scrape": False,
        "would_insert_ground_truth_rows": False,
        "would_blacklist_token": False,
        "would_create_cex_label": False,
        "would_create_dex_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "correlation_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }
    if not use_honeypot and not use_goplus:
        return {
            "ok": False,
            "dry_run": True,
            "correlation_status": "blocked",
            "blockers": ["at_least_one_security_source_required"],
            "candidates": [],
            **disabled,
        }

    pump_preview = get_manipulation_detection_behavioral_score_pump_backtest_preview(
        chain=clean_chain,
        limit=clean_limit,
        dry_run=True,
        min_swaps=safe_min_swaps,
        min_behavioral_score=safe_min_score,
        entry_score_threshold=safe_min_score,
    )
    behavioral_candidates = [
        row for row in list(pump_preview.get("candidate_backtests") or [])
        if _clean_address(row.get("target_token")) and _as_int(row.get("final_behavioral_score")) >= safe_min_score
    ][:clean_limit]
    token_addresses = [_clean_address(row.get("target_token")) for row in behavioral_candidates]
    security_preview = _engine().get_manipulation_detection_external_scam_negative_intake_preview(
        chain=clean_chain,
        token_addresses=token_addresses,
        limit=clean_limit,
        dry_run=True,
        use_honeypot=use_honeypot,
        use_goplus=use_goplus,
        timeout_seconds=safe_timeout,
    ) if token_addresses else {
        "candidates": [],
        "preview_ground_truth_rows": [],
        "summary": {"tokens_checked": 0, "documented_scam_negative_rows": 0},
        "blockers": ["no_behavioral_candidates_above_threshold"],
    }
    security_by_token = {
        _clean_address(row.get("token_address")): row
        for row in list(security_preview.get("candidates") or [])
        if _clean_address(row.get("token_address"))
    }
    candidates: list[dict[str, Any]] = []
    for row in behavioral_candidates:
        token = _clean_address(row.get("target_token"))
        security = security_by_token.get(token) or {}
        documented_negative = bool(security.get("documented_negative"))
        honeypot_detected = bool(security.get("honeypot_detected"))
        goplus_honeypot = bool(security.get("goplus_honeypot"))
        lookup_errors = [
            blocker for blocker in list(security.get("blockers") or [])
            if "lookup_failed" in str(blocker) or "http_" in str(blocker)
        ]
        candidates.append({
            "chain": clean_chain,
            "pool_address": row.get("pool_address"),
            "token_address": token,
            "token_symbol": row.get("target_symbol"),
            "behavioral_score": row.get("final_behavioral_score"),
            "score_factors": row.get("final_score_factors"),
            "pump_backtest_summary": row.get("outcome_summary"),
            "security_classification": {
                "candidate_status": security.get("candidate_status") or "security_lookup_missing",
                "documented_negative": documented_negative,
                "honeypot_detected": honeypot_detected,
                "goplus_honeypot": goplus_honeypot,
                "source_digest": security.get("source_digest"),
                "source_urls": security.get("source_urls"),
                "lookup_errors": lookup_errors,
            },
            "correlation_label": (
                "honeypot_detected"
                if honeypot_detected or goplus_honeypot else
                "documented_scam_negative"
                if documented_negative else
                "not_documented_scam_by_enabled_sources"
            ),
            "blockers": list(dict.fromkeys([
                *list(security.get("blockers") or []),
                *("security_lookup_missing" for _ in [1] if not security),
                "correlation_scan_is_not_blacklist",
                "client_signal_disabled",
                "trade_disabled",
            ])),
        })

    tested = len([row for row in candidates if row.get("security_classification")])
    honeypot_count = sum(
        1 for row in candidates
        if (row.get("security_classification") or {}).get("honeypot_detected")
        or (row.get("security_classification") or {}).get("goplus_honeypot")
    )
    documented_negative_count = sum(
        1 for row in candidates
        if (row.get("security_classification") or {}).get("documented_negative")
    )
    clean_or_unknown_count = max(0, tested - documented_negative_count)
    lookup_error_count = sum(
        1 for row in candidates
        if (row.get("security_classification") or {}).get("lookup_errors")
    )
    honeypot_precision = round((honeypot_count / tested) * 100, 2) if tested else 0.0
    scam_precision = round((documented_negative_count / tested) * 100, 2) if tested else 0.0
    verdict = (
        "strong_honeypot_detector" if honeypot_precision >= 60 else
        "moderate_honeypot_detector" if honeypot_precision >= 40 else
        "weak_honeypot_detector" if honeypot_precision >= 20 else
        "no_honeypot_correlation_in_current_sample"
    )
    preview_digest = _digest({
        "chain": clean_chain,
        "min_behavioral_score": safe_min_score,
        "min_swaps": safe_min_swaps,
        "candidates": [
            {
                "token_address": row.get("token_address"),
                "behavioral_score": row.get("behavioral_score"),
                "correlation_label": row.get("correlation_label"),
            }
            for row in candidates
        ],
    })
    blockers = [
        *("no_behavioral_candidates_above_threshold" for _ in [1] if not behavioral_candidates),
        *("security_lookup_errors_present" for _ in [1] if lookup_error_count),
        *("no_documented_honeypot_or_scam_correlation" for _ in [1] if candidates and documented_negative_count == 0),
        "correlation_scan_not_blacklist_or_client_signal",
        "ground_truth_rows_not_inserted",
        "client_signal_disabled",
        "trade_disabled",
    ]
    return {
        "ok": True,
        "dry_run": True,
        "correlation_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "limit": clean_limit,
        "min_behavioral_score": safe_min_score,
        "min_swaps": safe_min_swaps,
        "timeout_seconds": safe_timeout,
        "enabled_sources": {
            "honeypot": bool(use_honeypot),
            "goplus": bool(use_goplus),
        },
        "behavioral_pump_snapshot": {
            "preview_status": pump_preview.get("preview_status"),
            "summary": pump_preview.get("summary"),
            "digest": pump_preview.get("behavioral_score_pump_backtest_digest"),
        },
        "security_intake_snapshot": {
            "intake_status": security_preview.get("intake_status"),
            "summary": security_preview.get("summary"),
            "blockers": security_preview.get("blockers"),
        },
        "honeypot_correlation_scan_digest": preview_digest,
        "candidates": candidates,
        "summary": {
            "behavioral_candidates_checked": len(behavioral_candidates),
            "tokens_tested_by_security_api": tested,
            "honeypot_detected": honeypot_count,
            "documented_scam_or_honeypot_detected": documented_negative_count,
            "clean_or_unknown_tokens": clean_or_unknown_count,
            "lookup_error_tokens": lookup_error_count,
            "honeypot_precision_pct": honeypot_precision,
            "scam_precision_pct": scam_precision,
            "verdict": verdict,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys(blockers)),
        "next_safe_step": (
            "package_honeypot_scanner_policy_plan_read_only"
            if honeypot_precision >= 60 else
            "add_contract_security_features_or_forensic_report_packaging_read_only"
            if honeypot_precision >= 20 else
            "manual_forensic_cluster_interpretation_or_expand_sample_read_only"
        ),
        "plain_summary_fr": (
            "Cette preview teste si le score comportemental detecte plutot des honeypots/scams que des pumps. "
            "Elle utilise les APIs securite bornees deja existantes, mais ne cree aucun blacklist, signal ou trade."
        ),
        **disabled,
    }


def get_manipulation_detection_top_expansion_behavioral_tradability_filter_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    score_threshold: int = 75,
) -> dict[str, Any]:
    """Read-only honeypot/tradability preview for behavioral top-expansion candidates."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_pool = _clean_address(pool_address)
    clean_limit = max(1, min(int(limit or 3), 10))
    safe_threshold = max(1, min(int(score_threshold or 75), 100))
    source_policy = (
        "admin-only read-only behavioral tradability filter. It uses local raw Swap/Transfer context "
        "to check whether a target-token sell is observed after the conservative T0. It does not "
        "blacklist, create a signal, execute a trade, call providers, or mutate any label/mapping/client surface."
    )
    disabled = {
        "would_persist_tradability_filter": False,
        "would_blacklist_token": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    outcome_plan = get_manipulation_detection_top_expansion_behavioral_shadow_outcome_backtest_plan(
        chain=clean_chain,
        pool_address=clean_pool or None,
        limit=clean_limit,
        dry_run=True,
        score_threshold=safe_threshold,
    )
    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    candidates: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        for outcome in list(outcome_plan.get("candidate_outcomes") or []):
            pool = _clean_address(outcome.get("pool_address"))
            if not pool:
                continue
            swap_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_swap_events") else []
            sync_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_number ASC, log_index ASC
                LIMIT 1000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_sync_events") else []
            price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
            t0 = dict(outcome.get("t0_detection") or {})
            t0_ts = _as_int(t0.get("block_timestamp"))
            t0_block = _as_int(t0.get("block_number"))
            post_t0_swaps = [
                row for row in swap_rows
                if (
                    (_as_int(row["block_timestamp"]) >= t0_ts) if t0_ts else
                    (_as_int(row["block_number"]) >= t0_block if t0_block else True)
                )
            ]
            sell_rows = [
                observed for observed in (
                    _sell_observation_from_swap(row, price_context) for row in post_t0_swaps
                )
                if observed
            ]
            seller_wallets = sorted({
                wallet
                for row in sell_rows
                for wallet in (row.get("sender"), row.get("recipient"))
                if wallet and wallet != pool
            })
            target_token = str(price_context.get("target_token") or "")
            transfer_rows = []
            seller_like_transfer_rows = []
            if target_token and _table_exists(conn, "erc20_transfer_events"):
                transfer_rows = conn.execute(
                    """
                    SELECT *
                    FROM erc20_transfer_events
                    WHERE lower(chain)=? AND lower(token_address)=?
                      AND source_policy LIKE '%top expansion raw context%'
                    ORDER BY block_number ASC, log_index ASC
                    LIMIT 2000
                    """,
                    (clean_chain, target_token),
                ).fetchall()
                for row in transfer_rows:
                    if t0_block and _as_int(row["block_number"]) < t0_block:
                        continue
                    if _clean_address(row["to_address"]) == pool and _clean_address(row["from_address"]) != pool:
                        seller_like_transfer_rows.append(row)
            row_blockers: list[str] = []
            if not price_context.get("target_token"):
                row_blockers.append("target_token_missing")
            if not price_context.get("quote_token"):
                row_blockers.append("quote_token_missing")
            if not sell_rows:
                row_blockers.append("no_successful_sell_swap_observed_after_t0")
            row_blockers.extend([
                "bytecode_tax_static_analysis_missing",
                "contract_sell_tax_simulation_missing",
                "honeypot_api_not_used_by_policy",
                "client_signal_disabled",
                "trade_disabled",
            ])
            sellable_status = "sell_observed_read_only" if sell_rows else "sell_not_observed_blocked"
            candidates.append({
                "pool_address": pool,
                "behavioral_anomaly_score": outcome.get("behavioral_anomaly_score"),
                "target_token": price_context.get("target_token"),
                "target_symbol": price_context.get("target_symbol"),
                "quote_token": price_context.get("quote_token"),
                "quote_symbol": price_context.get("quote_symbol"),
                "t0_detection": t0,
                "post_t0_context": {
                    "swap_rows_post_t0": len(post_t0_swaps),
                    "transfer_rows_total_for_target": len(transfer_rows),
                    "seller_like_transfer_rows_to_pool_post_t0": len(seller_like_transfer_rows),
                },
                "sellability_checks": {
                    "successful_sell_tx_post_t0": bool(sell_rows),
                    "successful_sell_rows_post_t0": len(sell_rows),
                    "distinct_successful_sell_txs_post_t0": len({row.get("tx_hash") for row in sell_rows}),
                    "distinct_seller_like_wallets_post_t0": len(seller_wallets),
                    "sample_sell_rows": [
                        {
                            "tx_hash": row.get("tx_hash"),
                            "block_number": row.get("block_number"),
                            "target_in": str(row.get("target_in")),
                            "quote_out": str(row.get("quote_out")),
                            "quote_per_target": str(row.get("quote_per_target")),
                        }
                        for row in sell_rows[:5]
                    ],
                },
                "tax_honeypot_checks": {
                    "sellable_status": sellable_status,
                    "honeypot_risk": (
                        "lower_risk_sell_observed_not_proof" if sell_rows else
                        "blocked_no_successful_sell_observed_after_t0"
                    ),
                    "contract_static_tax_check_status": "missing_read_only_next",
                    "contract_sell_simulation_status": "missing_read_only_next",
                    "interpretation": (
                        "Une vente observee prouve seulement que la sortie existe dans les donnees locales; "
                        "cela ne prouve pas encore taxes faibles, liquidite suffisante ou trade executable."
                        if sell_rows else
                        "Aucune vente cible -> quote n'est observee apres T0 dans le contexte local; "
                        "le candidat reste bloque pour risque honeypot/untradable."
                    ),
                },
                "blockers": list(dict.fromkeys(row_blockers)),
                "next_safe_step": (
                    "t0_shift_experiment_read_only"
                    if sell_rows else
                    "collect_more_post_t0_sell_or_contract_tax_context_read_only"
                ),
                "would_blacklist_token": False,
                "would_create_client_signal": False,
                "would_execute_trade": False,
                "would_write": False,
            })
    finally:
        conn.close()

    if not candidates:
        blockers.append("no_behavioral_candidates_available_for_tradability_filter")
    sell_observed = [row for row in candidates if (row.get("sellability_checks") or {}).get("successful_sell_tx_post_t0")]
    preview_digest = _digest({
        "chain": clean_chain,
        "score_threshold": safe_threshold,
        "candidates": [
            {
                "pool_address": row.get("pool_address"),
                "score": row.get("behavioral_anomaly_score"),
                "sell_rows": (row.get("sellability_checks") or {}).get("successful_sell_rows_post_t0"),
            }
            for row in candidates
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "score_threshold": safe_threshold,
        "behavioral_shadow_outcome_snapshot": {
            "plan_status": outcome_plan.get("plan_status"),
            "summary": outcome_plan.get("summary"),
            "digest": outcome_plan.get("shadow_outcome_backtest_plan_digest"),
        },
        "tradability_filter_preview_digest": preview_digest,
        "candidates": candidates,
        "summary": {
            "candidates_checked": len(candidates),
            "sell_observed_candidates": len(sell_observed),
            "sell_not_observed_candidates": max(0, len(candidates) - len(sell_observed)),
            "honeypot_risk_candidates": max(0, len(candidates) - len(sell_observed)),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_successful_sell_observed_for_any_candidate" for _ in [1] if candidates and not sell_observed),
            "contract_tax_static_analysis_missing",
            "contract_sell_simulation_missing",
            "t0_shift_experiment_missing",
            "policy_risk_gate_missing",
            "client_opt_in_missing",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "t0_shift_experiment_read_only"
            if sell_observed else
            "collect_more_post_t0_sell_or_contract_tax_context_read_only"
        ),
        "plain_summary_fr": (
            "Cette preview verifie si les candidats suspects sont au moins sortables apres T0. "
            "C'est un filtre honeypot/tradability local et read-only: il ne cree aucun signal, mapping ou trade."
        ),
        **disabled,
    }


def get_manipulation_detection_top_expansion_behavioral_t0_shift_experiment_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    strong_score_threshold: int = 75,
    thresholds: str | None = "40,50,60,70,82",
    entry_slippage_bps: int = 400,
    exit_slippage_bps: int = 400,
    mev_penalty_bps: int = 200,
) -> dict[str, Any]:
    """Read-only alpha-lag experiment for behavioral top-expansion candidates."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_pool = _clean_address(pool_address)
    clean_limit = max(1, min(int(limit or 3), 10))
    safe_strong_threshold = max(1, min(int(strong_score_threshold or 75), 100))
    threshold_values = _parse_thresholds(thresholds)
    safe_entry_bps = max(0, min(int(entry_slippage_bps or 0), 5_000))
    safe_exit_bps = max(0, min(int(exit_slippage_bps or 0), 5_000))
    safe_mev_bps = max(0, min(int(mev_penalty_bps or 0), 5_000))
    total_friction_bps = safe_entry_bps + safe_exit_bps + safe_mev_bps
    source_policy = (
        "admin-only read-only behavioral T0 shift experiment. It replays local raw Swap/Sync/Transfer context "
        "chronologically and checks whether earlier behavioral score thresholds would have produced better "
        "friction-adjusted outcome. It creates no client signal, mapping, label, trade, wallet order or opt-in."
    )
    disabled = {
        "would_persist_t0_shift": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    tradability = get_manipulation_detection_top_expansion_behavioral_tradability_filter_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        limit=clean_limit,
        dry_run=True,
        score_threshold=safe_strong_threshold,
    )
    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    candidates: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        for candidate in list(tradability.get("candidates") or []):
            pool = _clean_address(candidate.get("pool_address"))
            if not pool:
                continue
            swap_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_swap_events") else []
            sync_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_number ASC, log_index ASC
                LIMIT 1000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_sync_events") else []
            price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
            target_token = str(price_context.get("target_token") or "")
            transfer_rows = conn.execute(
                """
                SELECT *
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, target_token),
            ).fetchall() if target_token and _table_exists(conn, "erc20_transfer_events") else []
            points = list(price_context.get("price_points") or [])
            threshold_hits: dict[int, dict[str, Any]] = {}
            score_curve_sample: list[dict[str, Any]] = []
            for index, swap in enumerate(swap_rows):
                position = _row_position(swap)
                prefix_swaps = swap_rows[: index + 1]
                prefix_syncs = _rows_up_to_position(sync_rows, position, has_timestamp=False)
                prefix_transfers = _rows_up_to_position(transfer_rows, position, has_timestamp=False)
                score_row = _score_raw_context_candidate(conn, clean_chain, pool, prefix_swaps, prefix_syncs, prefix_transfers)
                score = _as_int(score_row.get("behavioral_anomaly_score"))
                if index in {0, 1, 2, 4, 9, len(swap_rows) - 1}:
                    score_curve_sample.append({
                        "swap_index": index,
                        "block_number": _as_int(swap["block_number"]),
                        "block_timestamp": _as_int(swap["block_timestamp"]),
                        "score": score,
                        "score_factors": score_row.get("score_factors"),
                    })
                for threshold in threshold_values:
                    if threshold not in threshold_hits and score >= threshold:
                        entry_point = _entry_point_for_position(points, position)
                        entry_liquidity = _last_liquidity_before_position(points, position)
                        outcome = _outcome_after_entry(points, entry_point, total_friction_bps) if entry_point else {
                            "status": "blocked",
                            "blockers": ["entry_point_missing"],
                        }
                        threshold_hits[threshold] = {
                            "threshold": threshold,
                            "first_crossed": True,
                            "swap_index": index,
                            "score_at_cross": score,
                            "block_number": _as_int(swap["block_number"]),
                            "block_timestamp": _as_int(swap["block_timestamp"]),
                            "entry_liquidity_proxy": float(entry_liquidity) if entry_liquidity is not None else None,
                            "raw_context_at_cross": {
                                "swap_rows": len(prefix_swaps),
                                "sync_rows": len(prefix_syncs),
                                "transfer_rows": len(prefix_transfers),
                            },
                            "outcome_after_shifted_t0": outcome,
                        }
            final_hit = None
            for threshold in reversed(threshold_values):
                if threshold in threshold_hits:
                    final_hit = threshold_hits[threshold]
                    break
            threshold_rows: list[dict[str, Any]] = []
            for threshold in threshold_values:
                row = threshold_hits.get(threshold)
                if row and final_hit:
                    delta_blocks = _as_int(final_hit.get("block_number")) - _as_int(row.get("block_number"))
                    delta_seconds = _as_int(final_hit.get("block_timestamp")) - _as_int(row.get("block_timestamp"))
                    row = {
                        **row,
                        "lead_vs_latest_threshold_blocks": delta_blocks,
                        "lead_vs_latest_threshold_minutes": round(delta_seconds / 60.0, 4) if delta_seconds else None,
                    }
                    outcome = dict(row.get("outcome_after_shifted_t0") or {})
                    friction_mfe = outcome.get("friction_adjusted_mfe_pct")
                    row["threshold_interpretation"] = (
                        "potential_alpha_window_after_friction"
                        if friction_mfe is not None and friction_mfe > 0 else
                        "not_exploitable_after_friction_in_local_sample"
                    )
                else:
                    row = {
                        "threshold": threshold,
                        "first_crossed": False,
                        "blockers": ["threshold_not_reached_in_local_raw_context"],
                    }
                threshold_rows.append(row)
            positive_rows = [
                row for row in threshold_rows
                if ((row.get("outcome_after_shifted_t0") or {}).get("friction_adjusted_mfe_pct") is not None)
                and (row.get("outcome_after_shifted_t0") or {}).get("friction_adjusted_mfe_pct") > 0
            ]
            best_row = max(
                [
                    row for row in threshold_rows
                    if (row.get("outcome_after_shifted_t0") or {}).get("friction_adjusted_mfe_pct") is not None
                ],
                key=lambda row: (row.get("outcome_after_shifted_t0") or {}).get("friction_adjusted_mfe_pct"),
                default=None,
            )
            candidates.append({
                "pool_address": pool,
                "target_token": price_context.get("target_token"),
                "target_symbol": price_context.get("target_symbol"),
                "quote_token": price_context.get("quote_token"),
                "quote_symbol": price_context.get("quote_symbol"),
                "behavioral_anomaly_score": candidate.get("behavioral_anomaly_score"),
                "tradability_context": {
                    "sellable_status": (candidate.get("tax_honeypot_checks") or {}).get("sellable_status"),
                    "successful_sell_rows_post_t0": (candidate.get("sellability_checks") or {}).get("successful_sell_rows_post_t0"),
                },
                "score_thresholds": threshold_rows,
                "score_curve_sample": score_curve_sample,
                "best_threshold_after_friction": {
                    "threshold": best_row.get("threshold") if best_row else None,
                    "friction_adjusted_mfe_pct": (best_row.get("outcome_after_shifted_t0") or {}).get("friction_adjusted_mfe_pct") if best_row else None,
                    "mfe_pct": (best_row.get("outcome_after_shifted_t0") or {}).get("mfe_pct") if best_row else None,
                    "entry_liquidity_proxy": best_row.get("entry_liquidity_proxy") if best_row else None,
                },
                "alpha_lag_status": (
                    "earlier_threshold_has_positive_shadow_edge"
                    if positive_rows else
                    "no_positive_shadow_edge_in_local_t0_shift"
                ),
                "blockers": list(dict.fromkeys([
                    *([] if points else ["price_points_missing"]),
                    *([] if sync_rows else ["sync_liquidity_context_missing"]),
                    *([] if threshold_hits else ["no_threshold_crossed"]),
                    "contract_tax_static_analysis_missing",
                    "negative_controls_missing",
                    "policy_risk_gate_missing",
                    "client_signal_disabled",
                    "trade_disabled",
                ])),
                "next_safe_step": (
                    "negative_controls_and_contract_tax_checks_read_only"
                    if positive_rows else
                    "expand_candidate_sample_or_add_directional_intent_features_read_only"
                ),
            })
    finally:
        conn.close()

    if not candidates:
        blockers.append("no_sellable_behavioral_candidates_for_t0_shift")
    positive_candidates = [row for row in candidates if row.get("alpha_lag_status") == "earlier_threshold_has_positive_shadow_edge"]
    preview_digest = _digest({
        "chain": clean_chain,
        "thresholds": threshold_values,
        "candidates": [
            {
                "pool_address": row.get("pool_address"),
                "best_threshold": (row.get("best_threshold_after_friction") or {}).get("threshold"),
                "best_friction_mfe": (row.get("best_threshold_after_friction") or {}).get("friction_adjusted_mfe_pct"),
            }
            for row in candidates
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "thresholds": threshold_values,
        "strong_score_threshold": safe_strong_threshold,
        "friction_model": {
            "entry_slippage_bps": safe_entry_bps,
            "exit_slippage_bps": safe_exit_bps,
            "mev_penalty_bps": safe_mev_bps,
            "total_friction_bps": total_friction_bps,
        },
        "tradability_snapshot": {
            "preview_status": tradability.get("preview_status"),
            "summary": tradability.get("summary"),
            "digest": tradability.get("tradability_filter_preview_digest"),
        },
        "t0_shift_experiment_digest": preview_digest,
        "candidates": candidates,
        "summary": {
            "candidates_checked": len(candidates),
            "positive_shadow_edge_candidates": len(positive_candidates),
            "no_positive_shadow_edge_candidates": max(0, len(candidates) - len(positive_candidates)),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_positive_t0_shift_edge_in_local_sample" for _ in [1] if candidates and not positive_candidates),
            "contract_tax_static_analysis_missing",
            "negative_controls_missing",
            "policy_risk_gate_missing",
            "client_opt_in_missing",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "negative_controls_and_contract_tax_checks_read_only"
            if positive_candidates else
            "expand_candidate_sample_or_add_directional_intent_features_read_only"
        ),
        "plain_summary_fr": (
            "Cette experience mesure si le radar comportemental arrive trop tard. "
            "Elle rejoue les seuils 40/50/60/70/82 sur les donnees locales et compare MFE, MAE, liquidite "
            "et frictions. Aucun signal ou trade n'est cree."
        ),
        **disabled,
    }


def get_manipulation_detection_top_expansion_directional_intent_classifier_preview(
    chain: str | None = "bsc",
    pool_address: str | None = None,
    limit: int = 3,
    dry_run: bool = True,
    min_behavioral_score: int = 50,
) -> dict[str, Any]:
    """Read-only intent classifier for top-expansion behavioral candidates."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_pool = _clean_address(pool_address)
    clean_limit = max(1, min(int(limit or 3), 10))
    safe_min_score = max(1, min(int(min_behavioral_score or 50), 100))
    source_policy = (
        "admin-only read-only directional intent classifier. It uses local raw Swap/Sync/Transfer context "
        "to separate accumulation, circular/wash volume, distribution and weak internal flow. It is not a "
        "client signal, not a mapping, not a trade, and not a persisted score."
    )
    disabled = {
        "would_persist_intent_classification": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "preview_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    scoring = get_manipulation_detection_top_expansion_behavioral_anomaly_scoring_preview(
        chain=clean_chain,
        pool_address=clean_pool or None,
        limit=clean_limit,
        dry_run=True,
    )
    selected = [
        row for row in list(scoring.get("candidates") or [])
        if _as_int(row.get("behavioral_anomaly_score")) >= safe_min_score
    ]
    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    candidates: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        for scored in selected:
            pool = _clean_address(scored.get("pool_address"))
            if not pool:
                continue
            swap_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_swap_events") else []
            sync_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_number ASC, log_index ASC
                LIMIT 1000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_sync_events") else []
            price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
            target_token = str(price_context.get("target_token") or "")
            transfer_rows = conn.execute(
                """
                SELECT *
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=?
                  AND source_policy LIKE '%top expansion raw context%'
                ORDER BY block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, target_token),
            ).fetchall() if target_token and _table_exists(conn, "erc20_transfer_events") else []
            intent = _directional_intent_from_flows(pool, price_context, swap_rows, sync_rows, transfer_rows)
            classification = str(intent.get("intent_classification") or "insufficient_context")
            alpha_candidate = classification == "accumulation_candidate"
            needs_holder_freeze = classification == "weak_accumulation_needs_more_holding_context"
            row_blockers = [
                *list(intent.get("blockers") or []),
                *([] if classification == "accumulation_candidate" else ["directional_accumulation_not_confirmed"]),
                "24h_holder_freeze_snapshot_missing",
                "contract_tax_static_analysis_missing",
                "negative_controls_missing",
                "policy_risk_gate_missing",
                "client_signal_disabled",
                "trade_disabled",
            ]
            candidates.append({
                "pool_address": pool,
                "target_token": price_context.get("target_token"),
                "target_symbol": price_context.get("target_symbol"),
                "quote_token": price_context.get("quote_token"),
                "quote_symbol": price_context.get("quote_symbol"),
                "behavioral_anomaly_score": scored.get("behavioral_anomaly_score"),
                "behavioral_anomaly_tier": scored.get("behavioral_anomaly_tier"),
                "intent_classifier": intent,
                "directional_alpha_candidate_preview": alpha_candidate,
                "holder_freeze_context_needed": needs_holder_freeze,
                "intent_policy": {
                    "wash_trading_or_circular_volume": "forensic_alert_only_no_trade",
                    "distribution_or_sell_pressure": "avoid_long_shadow_trade",
                    "accumulation_candidate": "eligible_for_shadow_backtest_only_after_holder_freeze_and_controls",
                    "weak_accumulation_needs_more_holding_context": "collect_holder_freeze_context_before_backtest",
                    "balanced_internal_flow": "research_only",
                    "insufficient_context": "collect_more_raw_context",
                },
                "blockers": list(dict.fromkeys(row_blockers)),
                "next_safe_step": (
                    "holder_freeze_context_and_negative_controls_read_only"
                    if alpha_candidate or needs_holder_freeze else
                    "expand_candidate_sample_or_collect_directional_context_read_only"
                ),
            })
    finally:
        conn.close()

    if not candidates:
        blockers.append("no_behavioral_candidates_above_min_score_for_intent_classifier")
    classifications: dict[str, int] = {}
    for row in candidates:
        classification = str(((row.get("intent_classifier") or {}).get("intent_classification")) or "unknown")
        classifications[classification] = classifications.get(classification, 0) + 1
    alpha_candidates = [row for row in candidates if row.get("directional_alpha_candidate_preview")]
    holder_freeze_needed = [row for row in candidates if row.get("holder_freeze_context_needed")]
    preview_digest = _digest({
        "chain": clean_chain,
        "min_behavioral_score": safe_min_score,
        "classifications": classifications,
        "candidates": [
            {
                "pool_address": row.get("pool_address"),
                "score": row.get("behavioral_anomaly_score"),
                "intent": (row.get("intent_classifier") or {}).get("intent_classification"),
            }
            for row in candidates
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "preview_status": "ready_but_disabled" if candidates else "blocked",
        "chain": clean_chain,
        "min_behavioral_score": safe_min_score,
        "behavioral_scoring_snapshot": {
            "preview_status": scoring.get("preview_status"),
            "summary": scoring.get("summary"),
            "digest": scoring.get("behavioral_anomaly_preview_digest"),
        },
        "directional_intent_preview_digest": preview_digest,
        "candidates": candidates,
        "summary": {
            "candidates_checked": len(candidates),
            "intent_classifications": classifications,
            "directional_alpha_candidate_previews": len(alpha_candidates),
            "holder_freeze_context_needed_candidates": len(holder_freeze_needed),
            "forensic_only_candidates": len(candidates) - len(alpha_candidates),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_directional_alpha_candidate_preview" for _ in [1] if candidates and not alpha_candidates),
            "24h_holder_freeze_snapshot_missing",
            "contract_tax_static_analysis_missing",
            "negative_controls_missing",
            "policy_risk_gate_missing",
            "client_opt_in_missing",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "holder_freeze_context_and_negative_controls_read_only"
            if alpha_candidates or holder_freeze_needed else
            "expand_candidate_sample_or_collect_directional_context_read_only"
        ),
        "plain_summary_fr": (
            "Ce classificateur regarde ce que fait la meute: accumulation, wash volume, distribution ou flux interne. "
            "Il ne cree aucun signal; il decide seulement quels candidats meritent un futur shadow backtest."
        ),
        **disabled,
    }


def get_manipulation_detection_stealth_accumulation_anomaly_scan_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    max_pools: int = 50,
    max_circularity_pct: float = 30.0,
    min_hold_freeze_proxy_pct: float = 70.0,
    min_buy_flows: int = 3,
    token_addresses: list[str] | str | None = None,
    pool_addresses: list[str] | str | None = None,
) -> dict[str, Any]:
    """Read-only inverse scan: low circularity + high accumulation/hold proxy."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_max_pools = max(1, min(int(max_pools or 50), 200))
    safe_max_circularity = max(0.0, min(float(max_circularity_pct or 30.0), 100.0))
    safe_min_hold = max(0.0, min(float(min_hold_freeze_proxy_pct or 70.0), 100.0))
    safe_min_buys = max(1, min(int(min_buy_flows or 3), 100))
    explicit_tokens = _parse_addresses(token_addresses)
    explicit_pools = _parse_addresses(pool_addresses)
    source_policy = (
        "admin-only read-only stealth accumulation anomaly scan. It searches local raw pools for the inverse of "
        "wash-trading: low circularity, net target accumulation and high hold/freeze proxy. It creates no signal, "
        "mapping, label, trade, wallet order, opt-in or persisted score."
    )
    disabled = {
        "would_persist_stealth_scan": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "scan_status": "blocked",
            "blockers": ["dry_run_required"],
            "candidates": [],
            **disabled,
        }

    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    candidates: list[dict[str, Any]] = []
    rejected_samples: list[dict[str, Any]] = []
    blockers: list[str] = []
    scanned_pools = 0
    try:
        required = ["dex_raw_swap_events", "dex_raw_sync_events", "pair_tokens"]
        missing = [table for table in required if not _table_exists(conn, table)]
        if missing:
            blockers.extend([f"{table}_missing" for table in missing])
        if not missing and explicit_tokens:
            token_placeholders = ",".join("?" for _ in explicit_tokens)
            pools = conn.execute(
                f"""
                SELECT lower(d.pair_address) AS pool, COUNT(*) AS swap_rows, COUNT(DISTINCT d.tx_hash) AS txs
                FROM dex_raw_swap_events d
                JOIN pair_tokens p
                  ON lower(p.chain)=lower(d.chain)
                 AND lower(p.pool)=lower(d.pair_address)
                WHERE lower(d.chain)=?
                  AND (lower(p.token0) IN ({token_placeholders}) OR lower(p.token1) IN ({token_placeholders}))
                GROUP BY lower(d.pair_address)
                HAVING COUNT(*) >= ?
                ORDER BY swap_rows DESC, txs DESC
                LIMIT ?
                """,
                (clean_chain, *explicit_tokens, *explicit_tokens, safe_min_buys, safe_max_pools),
            ).fetchall()
        elif not missing and explicit_pools:
            pool_placeholders = ",".join("?" for _ in explicit_pools)
            pools = conn.execute(
                f"""
                SELECT lower(pair_address) AS pool, COUNT(*) AS swap_rows, COUNT(DISTINCT tx_hash) AS txs
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address) IN ({pool_placeholders})
                GROUP BY lower(pair_address)
                HAVING COUNT(*) >= ?
                ORDER BY swap_rows DESC, txs DESC
                LIMIT ?
                """,
                (clean_chain, *explicit_pools, safe_min_buys, safe_max_pools),
            ).fetchall()
        else:
            pools = conn.execute(
                """
                SELECT lower(pair_address) AS pool, COUNT(*) AS swap_rows, COUNT(DISTINCT tx_hash) AS txs
                FROM dex_raw_swap_events
                WHERE lower(chain)=?
                GROUP BY lower(pair_address)
                HAVING COUNT(*) >= ?
                ORDER BY swap_rows DESC, txs DESC
                LIMIT ?
                """,
                (clean_chain, safe_min_buys, safe_max_pools),
            ).fetchall() if not missing else []
        for pool_row in pools:
            pool = _clean_address(pool_row["pool"])
            if not pool:
                continue
            scanned_pools += 1
            swap_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, pool),
            ).fetchall()
            sync_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                ORDER BY block_number ASC, log_index ASC
                LIMIT 1000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_sync_events") else []
            price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
            target_token = str(price_context.get("target_token") or "")
            transfer_rows = conn.execute(
                """
                SELECT *
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=?
                ORDER BY block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, target_token),
            ).fetchall() if target_token and _table_exists(conn, "erc20_transfer_events") else []
            intent = _directional_intent_from_flows(pool, price_context, swap_rows, sync_rows, transfer_rows)
            flow_counts = dict(intent.get("flow_counts") or {})
            hold_proxy = float((intent.get("hold_freeze_proxy") or {}).get("hold_freeze_proxy_pct") or 0.0)
            circularity = float((intent.get("circularity") or {}).get("circularity_ratio_pct") or 0.0)
            buy_flows = _as_int(flow_counts.get("buy_target_flows"))
            net_flow = dict(intent.get("net_cluster_flow") or {})
            net_quote_spent = _as_decimal(net_flow.get("net_quote_spent"))
            net_target_accumulated = _as_decimal(net_flow.get("net_target_accumulated"))
            stealth_ready = bool(
                buy_flows >= safe_min_buys
                and circularity <= safe_max_circularity
                and hold_proxy >= safe_min_hold
                and net_quote_spent > 0
                and net_target_accumulated > 0
            )
            row = {
                "pool_address": pool,
                "target_token": price_context.get("target_token"),
                "target_symbol": price_context.get("target_symbol"),
                "quote_token": price_context.get("quote_token"),
                "quote_symbol": price_context.get("quote_symbol"),
                "stealth_accumulation_candidate": stealth_ready,
                "intent_classifier": intent,
                "thresholds": {
                    "max_circularity_pct": safe_max_circularity,
                    "min_hold_freeze_proxy_pct": safe_min_hold,
                    "min_buy_flows": safe_min_buys,
                },
                "blockers": list(dict.fromkeys([
                    *([] if buy_flows >= safe_min_buys else ["too_few_buy_flows"]),
                    *([] if circularity <= safe_max_circularity else ["circularity_too_high"]),
                    *([] if hold_proxy >= safe_min_hold else ["hold_freeze_proxy_below_threshold"]),
                    *([] if net_quote_spent > 0 else ["net_quote_spent_not_positive"]),
                    *([] if net_target_accumulated > 0 else ["net_target_accumulation_not_positive"]),
                    "24h_holder_snapshot_not_verified",
                    "future_shadow_backtest_required",
                    "client_signal_disabled",
                    "trade_disabled",
                ])),
                "next_safe_step": (
                    "holder_freeze_snapshot_and_shadow_backtest_read_only"
                    if stealth_ready else
                    "reject_for_alpha_or_collect_more_directional_context"
                ),
            }
            if stealth_ready:
                candidates.append(row)
            elif len(rejected_samples) < clean_limit:
                rejected_samples.append(row)
    finally:
        conn.close()

    scan_digest = _digest({
        "chain": clean_chain,
        "max_pools": safe_max_pools,
        "thresholds": {
            "max_circularity_pct": safe_max_circularity,
            "min_hold_freeze_proxy_pct": safe_min_hold,
            "min_buy_flows": safe_min_buys,
        },
        "candidates": [
            {
                "pool": row.get("pool_address"),
                "symbol": row.get("target_symbol"),
                "hold_proxy": ((row.get("intent_classifier") or {}).get("hold_freeze_proxy") or {}).get("hold_freeze_proxy_pct"),
                "circularity": ((row.get("intent_classifier") or {}).get("circularity") or {}).get("circularity_ratio_pct"),
            }
            for row in candidates[:clean_limit]
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "scan_status": "ready_but_disabled",
        "chain": clean_chain,
        "token_addresses": explicit_tokens,
        "pool_addresses": explicit_pools,
        "explicit_filter": bool(explicit_tokens or explicit_pools),
        "stealth_accumulation_scan_digest": scan_digest,
        "candidates": candidates[:clean_limit],
        "rejected_samples": rejected_samples,
        "summary": {
            "pools_scanned": scanned_pools,
            "stealth_accumulation_candidates": len(candidates),
            "returned_candidates": len(candidates[:clean_limit]),
            "rejected_sample_rows": len(rejected_samples),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_stealth_accumulation_candidate_found" for _ in [1] if not candidates),
            "24h_holder_snapshot_not_verified",
            "shadow_backtest_missing",
            "negative_controls_missing",
            "policy_risk_gate_missing",
            "client_opt_in_missing",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "holder_freeze_snapshot_and_shadow_backtest_read_only"
            if candidates else
            "expand_raw_context_sample_or_scan_more_pools_read_only"
        ),
        "plain_summary_fr": (
            "Ce scan cherche l'inverse du faux volume: faible circularite, accumulation nette, et tokens qui semblent "
            "rester hors vente. Il ne cree aucun signal ou trade."
        ),
        **disabled,
    }


def get_manipulation_detection_stealth_funnel_diagnostic_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    max_pools: int = 50,
    low_circularity_pct: float = 30.0,
    high_hold_freeze_proxy_pct: float = 50.0,
    min_buy_flows: int = 3,
) -> dict[str, Any]:
    """Read-only funnel diagnostic before expanding candidate collection."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_max_pools = max(1, min(int(max_pools or 50), 200))
    safe_low_circularity = max(0.0, min(float(low_circularity_pct or 30.0), 100.0))
    safe_high_hold = max(0.0, min(float(high_hold_freeze_proxy_pct or 50.0), 100.0))
    safe_min_buys = max(1, min(int(min_buy_flows or 3), 100))
    source_policy = (
        "admin-only read-only stealth funnel diagnostic. It tests whether the current local raw pool sample "
        "contains low-circularity and high-hold candidates before any new collection. It creates no signal, "
        "mapping, label, trade, wallet order, opt-in or persisted score."
    )
    disabled = {
        "would_collect_more_data": False,
        "would_persist_diagnostic": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "diagnostic_status": "blocked",
            "blockers": ["dry_run_required"],
            "rows": [],
            **disabled,
        }

    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    try:
        required = ["dex_raw_swap_events", "dex_raw_sync_events", "pair_tokens"]
        missing = [table for table in required if not _table_exists(conn, table)]
        if missing:
            blockers.extend([f"{table}_missing" for table in missing])
        pools = conn.execute(
            """
            SELECT lower(pair_address) AS pool, COUNT(*) AS swap_rows, COUNT(DISTINCT tx_hash) AS txs
            FROM dex_raw_swap_events
            WHERE lower(chain)=?
            GROUP BY lower(pair_address)
            HAVING COUNT(*) >= ?
            ORDER BY swap_rows DESC, txs DESC
            LIMIT ?
            """,
            (clean_chain, safe_min_buys, safe_max_pools),
        ).fetchall() if not missing else []
        for pool_row in pools:
            pool = _clean_address(pool_row["pool"])
            if not pool:
                continue
            swap_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                ORDER BY block_timestamp ASC, block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, pool),
            ).fetchall()
            sync_rows = conn.execute(
                """
                SELECT *
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                ORDER BY block_number ASC, log_index ASC
                LIMIT 1000
                """,
                (clean_chain, pool),
            ).fetchall() if _table_exists(conn, "dex_raw_sync_events") else []
            price_context = _price_points_from_raw_context(conn, clean_chain, pool, swap_rows, sync_rows)
            target_token = str(price_context.get("target_token") or "")
            transfer_rows = conn.execute(
                """
                SELECT *
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=?
                ORDER BY block_number ASC, log_index ASC
                LIMIT 2000
                """,
                (clean_chain, target_token),
            ).fetchall() if target_token and _table_exists(conn, "erc20_transfer_events") else []
            intent = _directional_intent_from_flows(pool, price_context, swap_rows, sync_rows, transfer_rows)
            hold_proxy = float((intent.get("hold_freeze_proxy") or {}).get("hold_freeze_proxy_pct") or 0.0)
            circularity = float((intent.get("circularity") or {}).get("circularity_ratio_pct") or 0.0)
            flow_counts = dict(intent.get("flow_counts") or {})
            net_flow = dict(intent.get("net_cluster_flow") or {})
            net_quote_spent = _as_decimal(net_flow.get("net_quote_spent"))
            net_target_accumulated = _as_decimal(net_flow.get("net_target_accumulated"))
            low_circular = circularity < safe_low_circularity
            high_hold = hold_proxy > safe_high_hold
            quiet_pool = _as_int(pool_row["swap_rows"]) < 50
            rows.append({
                "pool_address": pool,
                "target_token": price_context.get("target_token"),
                "target_symbol": price_context.get("target_symbol"),
                "quote_symbol": price_context.get("quote_symbol"),
                "swap_rows": _as_int(pool_row["swap_rows"]),
                "distinct_txs": _as_int(pool_row["txs"]),
                "quiet_pool_candidate": quiet_pool,
                "low_circularity": low_circular,
                "high_hold_freeze_proxy": high_hold,
                "low_circularity_and_high_hold": low_circular and high_hold,
                "net_positive_accumulation": net_quote_spent > 0 and net_target_accumulated > 0,
                "buy_flows": _as_int(flow_counts.get("buy_target_flows")),
                "intent_classification": intent.get("intent_classification"),
                "hold_freeze_proxy_pct": hold_proxy,
                "circularity_ratio_pct": circularity,
                "net_quote_spent": str(net_quote_spent),
                "net_target_accumulated": str(net_target_accumulated),
            })
    finally:
        conn.close()

    low_circular_rows = [row for row in rows if row.get("low_circularity")]
    high_hold_rows = [row for row in rows if row.get("high_hold_freeze_proxy")]
    stealth_rows = [row for row in rows if row.get("low_circularity_and_high_hold")]
    full_stealth_rows = [
        row for row in stealth_rows
        if row.get("net_positive_accumulation") and _as_int(row.get("buy_flows")) >= safe_min_buys
    ]
    quiet_rows = [row for row in rows if row.get("quiet_pool_candidate")]
    diagnostic_digest = _digest({
        "chain": clean_chain,
        "thresholds": {
            "low_circularity_pct": safe_low_circularity,
            "high_hold_freeze_proxy_pct": safe_high_hold,
            "min_buy_flows": safe_min_buys,
        },
        "summary": {
            "total_pools": len(rows),
            "low_circularity": len(low_circular_rows),
            "high_hold": len(high_hold_rows),
            "stealth_candidates": len(stealth_rows),
            "full_stealth_candidates": len(full_stealth_rows),
        },
    })
    next_step = (
        "debug_stealth_scan_thresholds_or_join_logic_read_only"
        if stealth_rows else
        "quiet_pool_scanner_plan_read_only"
        if not quiet_rows else
        "quiet_pool_raw_context_collection_plan_read_only"
    )
    return {
        "ok": True,
        "dry_run": True,
        "diagnostic_status": "ready_but_disabled",
        "chain": clean_chain,
        "thresholds": {
            "low_circularity_pct": safe_low_circularity,
            "high_hold_freeze_proxy_pct": safe_high_hold,
            "min_buy_flows": safe_min_buys,
        },
        "stealth_funnel_diagnostic_digest": diagnostic_digest,
        "rows": sorted(
            rows,
            key=lambda row: (
                not row.get("low_circularity_and_high_hold"),
                not row.get("low_circularity"),
                -float(row.get("hold_freeze_proxy_pct") or 0),
            ),
        )[:clean_limit],
        "summary": {
            "total_pools": len(rows),
            "low_circularity": len(low_circular_rows),
            "high_hold_freeze_proxy": len(high_hold_rows),
            "low_circularity_and_high_hold": len(stealth_rows),
            "full_stealth_candidates_with_positive_flow": len(full_stealth_rows),
            "quiet_pool_candidates_in_current_raw_sample": len(quiet_rows),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_low_circularity_high_hold_pool_in_current_raw_sample" for _ in [1] if not stealth_rows),
            *("no_quiet_pool_in_current_raw_sample" for _ in [1] if not quiet_rows),
            "larger_or_different_candidate_funnel_required",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": next_step,
        "plain_summary_fr": (
            "Ce diagnostic verifie si le probleme vient des seuils ou de l'echantillon. "
            "S'il n'y a aucun pool low-circularity + high-hold, il faut un scanner quiet-pool, pas plus du meme bruit."
        ),
        **disabled,
    }


def get_manipulation_detection_quiet_pool_scanner_plan_preview(
    chain: str | None = "bsc",
    limit: int = 10,
    dry_run: bool = True,
    max_pools: int = 100,
    max_swap_rows: int = 50,
    min_transfer_rows: int = 1,
    min_pool_age_days: int = 7,
) -> dict[str, Any]:
    """Read-only plan for selecting quiet pools instead of more top-active noise."""
    clean_chain = str(chain or "bsc").strip().lower()
    clean_limit = max(1, min(int(limit or 10), 50))
    safe_max_pools = max(1, min(int(max_pools or 100), 500))
    safe_max_swaps = max(0, min(int(max_swap_rows if max_swap_rows is not None else 50), 500))
    safe_min_transfers = max(0, min(int(min_transfer_rows if min_transfer_rows is not None else 1), 1000))
    safe_min_age = max(0, min(int(min_pool_age_days if min_pool_age_days is not None else 7), 3650))
    source_policy = (
        "admin-only read-only quiet pool scanner plan. It reads local pair_tokens, raw swaps, raw syncs, "
        "raw/legacy transfers and metadata to propose a different candidate funnel. It performs no collection, "
        "no persistence, no mapping, no signal, no trade and no client opt-in."
    )
    disabled = {
        "would_collect_raw_context": False,
        "would_persist_candidate": False,
        "would_persist_plan": False,
        "would_create_source_backed_score": False,
        "would_persist_score": False,
        "would_create_mapping": False,
        "would_create_dex_router_evidence": False,
        "would_create_cex_label": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": source_policy,
    }
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "plan_status": "blocked",
            "blockers": ["dry_run_required"],
            "quiet_pool_candidates": [],
            **disabled,
        }

    quote_tokens = {
        "bsc": {
            "0x55d398326f99059ff775485246999027b3197955",
            "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
            "0xe9e7cea3dedca5984780bafc599bd69add087d56",
            "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
        },
    }.get(clean_chain, set())
    infra_symbols = {"WBNB", "WETH", "ETH", "BNB", "USDT", "USDC", "BUSD", "DAI"}
    now_ts = int(time.time())
    conn = _engine()._get_db()
    conn.row_factory = sqlite3.Row
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    data_inventory: dict[str, Any] = {}
    try:
        tables = [
            "pair_tokens",
            "dex_raw_swap_events",
            "dex_raw_sync_events",
            "erc20_transfer_events",
            "token_transfers",
            "token_metadata",
            "wallet_chain_state",
            "transactions",
        ]
        data_inventory = {
            table: {
                "exists": _table_exists(conn, table),
                "rows": (
                    _as_int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    if _table_exists(conn, table) else 0
                ),
            }
            for table in tables
        }
        if not _table_exists(conn, "pair_tokens"):
            blockers.append("pair_tokens_missing")
            pair_rows: list[sqlite3.Row] = []
        else:
            pair_rows = conn.execute(
                """
                SELECT lower(pool) AS pool, lower(token0) AS token0, lower(token1) AS token1,
                       rpc_source, observed_at
                FROM pair_tokens
                WHERE lower(chain)=?
                ORDER BY COALESCE(observed_at, 0) DESC
                LIMIT ?
                """,
                (clean_chain, safe_max_pools),
            ).fetchall()

        has_swaps = _table_exists(conn, "dex_raw_swap_events")
        has_syncs = _table_exists(conn, "dex_raw_sync_events")
        has_raw_transfers = _table_exists(conn, "erc20_transfer_events")
        has_legacy_transfers = _table_exists(conn, "token_transfers")
        legacy_transfer_columns = _table_columns(conn, "token_transfers")

        for pair in pair_rows:
            pool = _clean_address(pair["pool"])
            token0 = _clean_address(pair["token0"])
            token1 = _clean_address(pair["token1"])
            if not pool or not token0 or not token1:
                continue
            quote_info = _quote_token_info(clean_chain, token0, token1)
            target_token = _clean_address(quote_info.get("target_token"))
            quote_token = _clean_address(quote_info.get("quote_token"))
            quote_symbol = quote_info.get("quote_symbol")
            target_meta = _token_meta(conn, clean_chain, target_token)
            target_symbol = str(target_meta.get("symbol") or "").upper() or None
            is_infra_target = target_token in quote_tokens or (target_symbol in infra_symbols if target_symbol else False)
            swap_stat = conn.execute(
                """
                SELECT COUNT(*) AS rows_count,
                       COUNT(DISTINCT tx_hash) AS tx_count,
                       COUNT(DISTINCT sender) AS senders,
                       COUNT(DISTINCT recipient) AS recipients,
                       MIN(block_number) AS first_block,
                       MAX(block_number) AS last_block,
                       MIN(block_timestamp) AS first_ts,
                       MAX(block_timestamp) AS last_ts
                FROM dex_raw_swap_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                """,
                (clean_chain, pool),
            ).fetchone() if has_swaps else None
            sync_stat = conn.execute(
                """
                SELECT COUNT(*) AS rows_count, MIN(block_number) AS first_block, MAX(block_number) AS last_block
                FROM dex_raw_sync_events
                WHERE lower(chain)=? AND lower(pair_address)=?
                """,
                (clean_chain, pool),
            ).fetchone() if has_syncs else None
            raw_transfer_stat = conn.execute(
                """
                SELECT COUNT(*) AS rows_count,
                       COUNT(DISTINCT from_address) AS senders,
                       COUNT(DISTINCT to_address) AS receivers,
                       MIN(block_number) AS first_block,
                       MAX(block_number) AS last_block
                FROM erc20_transfer_events
                WHERE lower(chain)=? AND lower(token_address)=?
                """,
                (clean_chain, target_token),
            ).fetchone() if has_raw_transfers and target_token else None
            legacy_transfer_stat = None
            if has_legacy_transfers and target_token and {"chain", "token"}.issubset(legacy_transfer_columns):
                legacy_transfer_stat = conn.execute(
                    """
                    SELECT COUNT(*) AS rows_count,
                           COUNT(DISTINCT from_addr) AS senders,
                           COUNT(DISTINCT to_addr) AS receivers,
                           MIN(block_number) AS first_block,
                           MAX(block_number) AS last_block
                    FROM token_transfers
                    WHERE lower(chain)=? AND lower(token)=?
                    """,
                    (clean_chain, target_token),
                ).fetchone()

            swap_rows = _as_int(swap_stat["rows_count"] if swap_stat else 0)
            sync_rows = _as_int(sync_stat["rows_count"] if sync_stat else 0)
            raw_transfer_rows = _as_int(raw_transfer_stat["rows_count"] if raw_transfer_stat else 0)
            legacy_transfer_rows = _as_int(legacy_transfer_stat["rows_count"] if legacy_transfer_stat else 0)
            transfer_rows = raw_transfer_rows + legacy_transfer_rows
            transfer_receivers = (
                _as_int(raw_transfer_stat["receivers"] if raw_transfer_stat else 0)
                + _as_int(legacy_transfer_stat["receivers"] if legacy_transfer_stat else 0)
            )
            observed_at = _as_int(pair["observed_at"])
            first_ts = _as_int(swap_stat["first_ts"] if swap_stat else 0)
            age_anchor = observed_at or first_ts
            pool_age_days = round((now_ts - age_anchor) / 86400.0, 4) if age_anchor else None
            quiet_enough = swap_rows <= safe_max_swaps
            transfer_context_possible = transfer_rows >= safe_min_transfers
            survival_possible = pool_age_days is not None and pool_age_days >= safe_min_age
            has_pair_bound = bool(quote_symbol and target_token and quote_token)

            score = 0
            reasons: list[str] = []
            if has_pair_bound:
                score += 20
                reasons.append("pair_tokens_quote_target_bound")
            if quiet_enough:
                score += 25
                reasons.append("low_swap_count_surface")
            if transfer_context_possible:
                score += 25
                reasons.append("transfer_holder_context_available")
            if survival_possible:
                score += 15
                reasons.append("pool_survival_proxy_available")
            if sync_rows:
                score += 10
                reasons.append("sync_liquidity_context_available")
            if transfer_receivers >= 3:
                score += 5
                reasons.append("multiple_transfer_receivers")
            pool_blockers = list(dict.fromkeys([
                *("pair_tokens_quote_target_missing" for _ in [1] if not has_pair_bound),
                *("infrastructure_or_quote_target" for _ in [1] if is_infra_target),
                *("too_many_swaps_for_quiet_pool" for _ in [1] if not quiet_enough),
                *("transfer_holder_context_missing" for _ in [1] if not transfer_context_possible),
                *("pool_age_or_survival_context_missing" for _ in [1] if not survival_possible),
            ]))
            plan_ready = bool(
                score >= 60
                and quiet_enough
                and transfer_context_possible
                and survival_possible
                and not is_infra_target
            )
            rows.append({
                "pool_address": pool,
                "token0": token0,
                "token1": token1,
                "target_token": target_token,
                "target_symbol": target_symbol,
                "quote_token": quote_token,
                "quote_symbol": quote_symbol,
                "pair_tokens_rpc_source": pair["rpc_source"],
                "observed_at": observed_at or None,
                "pool_age_days": pool_age_days,
                "swap_rows": swap_rows,
                "sync_rows": sync_rows,
                "transfer_rows": transfer_rows,
                "raw_transfer_rows": raw_transfer_rows,
                "legacy_transfer_rows": legacy_transfer_rows,
                "transfer_receivers": transfer_receivers,
                "quiet_enough": quiet_enough,
                "transfer_context_possible": transfer_context_possible,
                "survival_possible": survival_possible,
                "is_infrastructure_target": is_infra_target,
                "plan_candidate_score": min(score, 100),
                "plan_ready_for_bounded_raw_context_lookup": plan_ready,
                "candidate_reasons": reasons,
                "candidate_blockers": pool_blockers,
                "future_collection_scope": {
                    "allowed": plan_ready,
                    "events": ["Swap", "Sync", "ERC20 Transfer"],
                    "bounded_to_pool": pool,
                    "bounded_to_target_token": target_token,
                    "purpose": "repair quiet-pool holder/swap/liquidity context only; no signal or trade",
                },
            })
    finally:
        conn.close()

    sorted_rows = sorted(
        rows,
        key=lambda row: (
            not row.get("plan_ready_for_bounded_raw_context_lookup"),
            -_as_int(row.get("plan_candidate_score")),
            _as_int(row.get("swap_rows")),
            -(row.get("pool_age_days") or 0),
        ),
    )
    candidates = [row for row in sorted_rows if row.get("plan_ready_for_bounded_raw_context_lookup")]
    plan_digest = _digest({
        "chain": clean_chain,
        "thresholds": {
            "max_swap_rows": safe_max_swaps,
            "min_transfer_rows": safe_min_transfers,
            "min_pool_age_days": safe_min_age,
        },
        "candidates": [
            {
                "pool": row.get("pool_address"),
                "target": row.get("target_token"),
                "score": row.get("plan_candidate_score"),
            }
            for row in sorted_rows[:clean_limit]
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "plan_status": "ready_but_disabled",
        "chain": clean_chain,
        "plan_digest": plan_digest,
        "selection_strategy": {
            "name": "quiet_pool_scanner",
            "purpose": "invert the top-active funnel by finding low-swap pools with holder/transfer context",
            "max_swap_rows": safe_max_swaps,
            "min_transfer_rows": safe_min_transfers,
            "min_pool_age_days": safe_min_age,
            "excluded_targets": sorted(infra_symbols),
        },
        "data_inventory": data_inventory,
        "quiet_pool_candidates": sorted_rows[:clean_limit],
        "summary": {
            "pair_pools_checked": len(rows),
            "plan_ready_candidates": len(candidates),
            "quiet_pool_candidates": sum(1 for row in rows if row.get("quiet_enough")),
            "transfer_context_possible": sum(1 for row in rows if row.get("transfer_context_possible")),
            "survival_context_possible": sum(1 for row in rows if row.get("survival_possible")),
            "can_detect_reliable_manipulation_now": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "blockers": list(dict.fromkeys([
            *blockers,
            *("no_pair_tokens_pool_universe" for _ in [1] if not rows),
            *("no_quiet_pool_plan_ready_candidate" for _ in [1] if not candidates),
            "bounded_raw_context_collection_required_before_scoring",
            "holder_freeze_context_required_before_alpha_claim",
            "source_identity_separate_from_behavior",
            "client_signal_disabled",
            "trade_disabled",
        ])),
        "next_safe_step": (
            "quiet_pool_bounded_raw_context_lookup_dry_run"
            if candidates else
            "quiet_pool_candidate_universe_repair_plan_read_only"
        ),
        "plain_summary_fr": (
            "Ce plan cherche des pools plus calmes et potentiellement accumulees, au lieu de reprendre les pools "
            "tres actives qui produisent surtout du wash trading. Il ne collecte rien et ne cree aucun signal."
        ),
        **disabled,
    }


def _score_case(row: dict[str, Any]) -> dict[str, Any]:
    wallet_profiles = list(row.get("wallet_profiles") or [])
    clusters = list(row.get("clusters") or [])
    funder_graph = list(row.get("funder_graph") or [])

    fresh_wallets = sum(1 for item in wallet_profiles if item.get("is_fresh_wallet"))
    funding_observed = sum(1 for item in wallet_profiles if item.get("funding_source"))
    contract_wallets = sum(1 for item in wallet_profiles if (item.get("wallet_state") or {}).get("is_contract"))
    post_event_seller_clusters = sum(1 for item in clusters if item.get("cluster_type") == "post_event_seller_cluster")
    shared_funder_clusters = sum(1 for item in clusters if item.get("cluster_type") == "shared_funder_accumulator_cluster")
    shared_funders = len(funder_graph)
    shared_unknown_funders = sum(
        1 for item in funder_graph
        if item.get("classification") == "unknown_funder_needs_graph_expansion"
    )
    gas_fanout_funders = sum(1 for item in funder_graph if (item.get("gas_fanout_profile") or {}).get("detected"))
    pre_event_cex_deposit_funders = sum(1 for item in funder_graph if (item.get("cex_deposit_profile") or {}).get("detected"))
    high_false_positive_funders = sum(1 for item in funder_graph if item.get("false_positive_risk") == "high")

    score = 0
    factors: list[str] = []
    if fresh_wallets:
        score += min(25, fresh_wallets * 6)
        factors.append("fresh_wallet_accumulation")
    if funding_observed:
        score += min(20, funding_observed * 5)
        factors.append("funding_edges_observed")
    if post_event_seller_clusters:
        score += min(12, post_event_seller_clusters * 6)
        factors.append("post_event_seller_cluster")
    if shared_funder_clusters:
        score += min(18, shared_funder_clusters * 9)
        factors.append("shared_funder_accumulator_cluster")
    if shared_funders:
        score += min(12, shared_funders * 6)
        factors.append("shared_funders")
    if shared_unknown_funders:
        score += min(15, shared_unknown_funders * 10)
        factors.append("shared_unknown_funders")
    if gas_fanout_funders:
        score += min(10, gas_fanout_funders * 5)
        factors.append("gas_fanout_funders")
    if pre_event_cex_deposit_funders:
        score += min(10, pre_event_cex_deposit_funders * 5)
        factors.append("pre_event_cex_deposit_funders")
    if high_false_positive_funders:
        score -= min(20, high_false_positive_funders * 10)
        factors.append("high_false_positive_funder_penalty")
    if contract_wallets and contract_wallets >= max(1, len(wallet_profiles) // 2):
        score -= 8
        factors.append("contract_wallet_false_positive_penalty")

    score = max(0, min(100, int(score)))
    tier = (
        "strong_behavioral_cluster_candidate" if score >= 75 else
        "moderate_behavioral_cluster_candidate" if score >= 50 else
        "weak_behavioral_context"
    )
    gate_passed = bool(
        score >= 75
        and fresh_wallets >= 2
        and funding_observed >= 2
        and high_false_positive_funders == 0
    )
    bridge_payload = {
        "chain": row.get("chain"),
        "token": row.get("token"),
        "event_timestamp": row.get("event_timestamp"),
        "behavioral_score": score,
        "behavioral_tier": tier,
        "fresh_wallets": fresh_wallets,
        "funding_observed": funding_observed,
        "post_event_seller_clusters": post_event_seller_clusters,
        "shared_funder_clusters": shared_funder_clusters,
        "shared_funders": shared_funders,
        "shared_unknown_funders": shared_unknown_funders,
        "gas_fanout_funders": gas_fanout_funders,
        "pre_event_cex_deposit_funders": pre_event_cex_deposit_funders,
        "high_false_positive_funders": high_false_positive_funders,
        "factors": factors,
    }
    return {
        **bridge_payload,
        "behavioral_proof_class": "behavioral_cluster_proof",
        "behavioral_gate_passed": gate_passed,
        "proof_status": "behavioral_research_proof_not_identity_proof",
        "bridge_digest": _digest(bridge_payload),
        "blockers": list(dict.fromkeys([
            *([] if score >= 50 else ["behavioral_score_below_review_threshold"]),
            *([] if funding_observed >= 2 else ["funding_edges_too_thin"]),
            *([] if fresh_wallets >= 2 else ["fresh_wallet_cluster_too_thin"]),
            *("high_false_positive_funder_risk" for _ in [1] if high_false_positive_funders),
            "behavioral_proof_not_source_identity_proof",
            "shadow_backtest_required_before_policy_unlock",
            "client_signal_disabled",
            "trade_disabled",
        ])),
    }


def get_manipulation_detection_behavioral_evidence_bridge(
    chain: str | None = "bsc",
    token: str | None = None,
    limit: int = 10,
    wallet_limit: int = 10,
    dry_run: bool = True,
    breakout_threshold_pct: float = 500.0,
    baseline_swaps: int = 12,
    confirmation_swaps: int = 3,
    pre_event_swaps: int = 20,
    fresh_wallet_hours: int = 72,
    cluster_window_minutes: int = 60,
) -> dict[str, Any]:
    """Read-only bridge from adaptive behavioral case files to policy-readable proof packages."""
    clean_limit = max(1, min(int(limit or 10), 50))
    clean_wallet_limit = max(1, min(int(wallet_limit or 10), 50))
    if not dry_run:
        return {
            "ok": False,
            "dry_run": False,
            "bridge_status": "blocked",
            "blockers": ["dry_run_required"],
            "would_create_behavioral_proof": False,
            "would_persist_behavioral_proof": False,
            "would_update_reliability_policy": False,
            "would_create_client_signal": False,
            "would_execute_trade": False,
            "would_write": False,
            "writes_performed": 0,
            "source_policy": "behavioral bridge is read-only",
        }

    case_file = _engine().get_adaptive_manipulation_case_file(
        chain=chain,
        token=token,
        limit=clean_limit,
        wallet_limit=clean_wallet_limit,
        breakout_threshold_pct=breakout_threshold_pct,
        baseline_swaps=baseline_swaps,
        confirmation_swaps=confirmation_swaps,
        pre_event_swaps=pre_event_swaps,
        fresh_wallet_hours=fresh_wallet_hours,
        cluster_window_minutes=cluster_window_minutes,
    )
    rows = list(case_file.get("rows") or [])
    proofs = [_score_case(dict(row)) for row in rows]
    strong = [row for row in proofs if row.get("behavioral_gate_passed")]
    moderate_or_better = [row for row in proofs if _as_int(row.get("behavioral_score")) >= 50]
    blockers = list(dict.fromkeys([
        *([] if case_file.get("ok") else ["adaptive_case_file_not_ok"]),
        *("no_behavioral_case_rows" for _ in [1] if not rows),
        *("no_strong_behavioral_cluster_candidate" for _ in [1] if rows and not strong),
        "behavioral_bridge_is_research_only",
        "does_not_replace_source_identity_or_backtest",
        "client_signal_disabled",
        "trade_disabled",
    ]))
    bridge_digest = _digest({
        "chain": chain,
        "token": token,
        "proofs": [
            {
                "chain": row.get("chain"),
                "token": row.get("token"),
                "event_timestamp": row.get("event_timestamp"),
                "bridge_digest": row.get("bridge_digest"),
            }
            for row in proofs
        ],
    })
    return {
        "ok": True,
        "dry_run": True,
        "bridge_status": "ready_but_disabled" if proofs else "blocked",
        "chain": chain,
        "token": token,
        "behavioral_bridge_digest": bridge_digest,
        "proof_class": "behavioral_cluster_proof",
        "case_file_summary": case_file.get("summary") or {},
        "summary": {
            "case_rows": len(rows),
            "behavioral_proofs": len(proofs),
            "moderate_or_better_behavioral_candidates": len(moderate_or_better),
            "strong_behavioral_candidates": len(strong),
            "max_behavioral_score": max([_as_int(row.get("behavioral_score")) for row in proofs] or [0]),
            "source_backed_scoring_ready": False,
            "client_signal_ready": False,
            "trade_ready": False,
        },
        "proofs": proofs[:clean_limit],
        "policy_translation": {
            "accepted_as": "research_priority_signal",
            "not_accepted_as": [
                "source_identity_proof",
                "mapping_proof",
                "client_signal",
                "trade_authorization",
            ],
            "future_policy_gate": (
                "A future policy engine may treat strong behavioral_cluster_proof as sufficient to prioritize "
                "shadow replay and data collection, but not sufficient for client signal/trade without outcomes, "
                "negative controls, risk policy and opt-in."
            ),
        },
        "blockers": blockers,
        "next_safe_step": (
            "behavioral_bridge_review_queue_read_only"
            if proofs else "collect_more_adaptive_case_data"
        ),
        "plain_summary_fr": (
            "Le pont traduit les indices comportementaux existants en preuves research-only lisibles par la policy. "
            "Il ne cree aucun signal et ne debloque aucun trade."
        ),
        "would_create_behavioral_proof": False,
        "would_persist_behavioral_proof": False,
        "would_update_reliability_policy": False,
        "would_create_source_backed_score": False,
        "would_create_dex_mapping": False,
        "would_create_client_signal": False,
        "would_execute_trade": False,
        "would_create_wallet_order": False,
        "would_create_client_opt_in": False,
        "would_write": False,
        "real_write_enabled": False,
        "writes_performed": 0,
        "source_policy": (
            "read-only bridge from adaptive manipulation case files into behavioral_cluster_proof packages; "
            "no DB write, no score persistence, no mapping, no label, no client signal, no trade and no opt-in"
        ),
    }
