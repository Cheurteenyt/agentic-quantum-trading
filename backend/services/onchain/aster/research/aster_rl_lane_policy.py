from __future__ import annotations

import argparse
import csv
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parents[3]
DOCS_DIR = ROOT_DIR / "docs"

JSON_OUT = BASE_DIR / "aster_rl_lane_policy_latest.json"
CSV_OUT = BASE_DIR / "aster_rl_lane_policy_latest.csv"
HTML_OUT = DOCS_DIR / "core-equity-aster-rl-lane-policy.html"

DISCOVERY_PATTERNS = [
    "paper_trading_strategy_discovery_*_v2.csv",
    "paper_trading_strategy_discovery_*_progress_v2.csv",
]
MARK_INDEX_JSON = BASE_DIR / "aster_mark_index_replay_filter_latest.json"
MICROSTRUCTURE_JSON = BASE_DIR / "aster_microstructure_replay_validator_latest.json"
REALITY_PACK_JSON = BASE_DIR / "aster_queue_reality_pack_validator_latest.json"

MEME_BASES = {"1000BONK", "1000FLOKI", "1000PEPE", "1000SATS", "BOME", "BONK", "DOGE", "FLOKI", "PEPE", "SHIB", "WIF"}
MAJOR_BASES = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK"}
COMMODITY_BASES = {"XAU", "XAG", "CLU", "BZU"}
EQUITY_BASES = {"AAPL", "AMD", "AMZN", "COIN", "CRCL", "DRAM", "GOOGL", "INTC", "META", "MSFT", "MSTR", "NVDA", "TSLA"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        parsed = float(value)
        if math.isnan(parsed) or math.isinf(parsed):
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _read_csv(path: Path) -> list[dict[str, Any]]:
    try:
        mtime_epoch = path.stat().st_mtime
        mtime_utc = datetime.fromtimestamp(mtime_epoch, timezone.utc).isoformat()
        with path.open(newline="", encoding="utf-8") as handle:
            return [
                dict(
                    row,
                    source_file=path.name,
                    source_mtime_epoch=str(mtime_epoch),
                    source_mtime_utc=mtime_utc,
                )
                for row in csv.DictReader(handle)
            ]
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _artifact_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime if path.exists() else 0.0
    except OSError:
        return 0.0


def _artifact_iso(path: Path) -> str | None:
    mtime = _artifact_mtime(path)
    if not mtime:
        return None
    return datetime.fromtimestamp(mtime, timezone.utc).isoformat()


def _freshness_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_mtimes = [_float(row.get("source_mtime_epoch")) for row in rows if _float(row.get("source_mtime_epoch"))]
    latest_source = max(source_mtimes) if source_mtimes else 0.0
    artifacts = {
        "mark_index": MARK_INDEX_JSON,
        "microstructure": MICROSTRUCTURE_JSON,
        "reality_pack": REALITY_PACK_JSON,
    }
    artifact_states = {
        name: {
            "path": str(path),
            "exists": path.exists(),
            "mtime_utc": _artifact_iso(path),
            "older_than_latest_discovery": bool(latest_source and _artifact_mtime(path) and _artifact_mtime(path) + 60 < latest_source),
        }
        for name, path in artifacts.items()
    }
    stale = [name for name, state in artifact_states.items() if state.get("older_than_latest_discovery")]
    return {
        "latest_discovery_mtime_utc": datetime.fromtimestamp(latest_source, timezone.utc).isoformat() if latest_source else None,
        "artifact_states": artifact_states,
        "freshness_verdict": "validators_stale_against_latest_discovery" if stale else "fresh_enough",
        "stale_artifacts": stale,
    }


def _row_freshness(row: dict[str, Any]) -> tuple[str, str]:
    source_mtime = _float(row.get("source_mtime_epoch"))
    if not source_mtime:
        return "unknown_source_mtime", "source_mtime_missing"
    warnings = []
    for name, path in (
        ("mark_index", MARK_INDEX_JSON),
        ("microstructure", MICROSTRUCTURE_JSON),
        ("reality_pack", REALITY_PACK_JSON),
    ):
        artifact_mtime = _artifact_mtime(path)
        if not artifact_mtime:
            warnings.append(f"{name}_missing")
        elif artifact_mtime + 60 < source_mtime:
            warnings.append(f"{name}_older_than_source")
    if warnings:
        return "stale_validation_overlays", ",".join(warnings)
    return "fresh_enough", ""


def _base(symbol: Any) -> str:
    clean = "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())
    for suffix in ("USDT", "USD1", "USDC"):
        if clean.endswith(suffix):
            return clean[: -len(suffix)]
    return clean


def _category(symbol: str) -> str:
    base = _base(symbol)
    if base in COMMODITY_BASES:
        return "commodity"
    if base in EQUITY_BASES:
        return "equity_synthetic"
    if base in MEME_BASES or base.startswith("1000"):
        return "memecoin"
    if base in MAJOR_BASES:
        return "major_crypto"
    return "altcoin"


def _lane_key(row: dict[str, Any]) -> str:
    profile = str(row.get("strategy_profile_id") or row.get("strategy_profile_key") or "").strip()
    if profile:
        return profile
    fields = [
        row.get("output_tag"),
        str(row.get("symbol") or "").upper(),
        str(row.get("interval") or ""),
        str(row.get("side") or "long").lower(),
        row.get("search_mode"),
        row.get("trigger_reference") or row.get("assumed_trigger_reference"),
        row.get("execution_model") or row.get("assumed_execution_model"),
        row.get("risk_profile"),
        row.get("best_tradable_leverage"),
        row.get("score_window_size"),
        row.get("min_aster_score"),
        row.get("min_window_volume_usd"),
        row.get("stop_loss_pct"),
        row.get("take_profit_pct"),
        row.get("max_holding_trades"),
    ]
    return "|".join(str(item or "") for item in fields)


def _recommendation_key(row: dict[str, Any]) -> str:
    fields = [
        str(row.get("symbol") or "").upper(),
        str(row.get("interval") or ""),
        str(row.get("side") or "long").lower(),
    ]
    return "|".join(str(item or "") for item in fields)


def _target_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("symbol") or "").upper(),
        str(row.get("interval") or ""),
        str(row.get("side") or "long").lower(),
    )


def _mark_overlay() -> dict[tuple[str, str], dict[str, Any]]:
    payload = _load_json(MARK_INDEX_JSON)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if isinstance(row, dict):
            symbol = str(row.get("symbol") or "").upper()
            interval = str(row.get("interval") or "")
            if symbol and interval:
                out[(symbol, interval)] = row
    return out


def _micro_overlay() -> dict[tuple[str, str, str], dict[str, Any]]:
    payload = _load_json(MICROSTRUCTURE_JSON)
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if isinstance(row, dict):
            key = _target_key(row)
            if key[0] and key[1]:
                out[key] = row
    return out


def _reality_overlay() -> dict[tuple[str, str, str], dict[str, Any]]:
    payload = _load_json(REALITY_PACK_JSON)
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or payload.get("selected_lanes") or []:
        if isinstance(row, dict):
            key = _target_key(row)
            if key[0] and key[1]:
                current = out.get(key)
                rank = {"validation_passed_clean": 3, "validation_passed_watch": 2, "validation_rejected_or_rework": 1}.get(str(row.get("validation_status") or ""), 0)
                cur_rank = {"validation_passed_clean": 3, "validation_passed_watch": 2, "validation_rejected_or_rework": 1}.get(str((current or {}).get("validation_status") or ""), 0)
                if current is None or rank > cur_rank:
                    out[key] = row
    return out


def _load_discovery_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for pattern in DISCOVERY_PATTERNS:
        for path in sorted(BASE_DIR.glob(pattern)):
            if path in seen_paths:
                continue
            seen_paths.add(path)
            rows.extend(_read_csv(path))
    return rows


def _decorate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mark = _mark_overlay()
    micro = _micro_overlay()
    reality = _reality_overlay()
    best: dict[str, dict[str, Any]] = {}
    for source in rows:
        symbol = str(source.get("symbol") or "").upper()
        interval = str(source.get("interval") or "")
        side = str(source.get("side") or "long").lower()
        if not symbol or not interval:
            continue
        row = dict(source)
        row["symbol"] = symbol
        row["side"] = side
        key = _target_key(row)
        mark_row = mark.get((symbol, interval)) or {}
        micro_row = micro.get(key) or {}
        reality_row = reality.get(key) or {}
        if mark_row.get("verdict"):
            row["mark_index_verdict"] = mark_row.get("verdict")
            row["mark_index_blockers"] = ",".join(mark_row.get("blockers") or [])
            row["mark_index_warnings"] = ",".join(mark_row.get("warnings") or [])
        elif reality_row.get("mark_index_verdict"):
            row["mark_index_verdict"] = reality_row.get("mark_index_verdict")
        elif reality_row.get("mark_index_status"):
            row["mark_index_verdict"] = reality_row.get("mark_index_status")
        row["microstructure_verdict"] = micro_row.get("verdict") or row.get("microstructure_verdict") or "not_checked"
        row["microstructure_blockers"] = ",".join(micro_row.get("blockers") or []) if micro_row else row.get("microstructure_blockers") or ""
        if reality_row.get("microstructure_verdict") and row["microstructure_verdict"] == "not_checked":
            row["microstructure_verdict"] = reality_row.get("microstructure_verdict")
        row["reality_validation_status"] = reality_row.get("validation_status") or "not_checked"
        freshness, freshness_warnings = _row_freshness(row)
        row["validation_freshness_verdict"] = freshness
        row["validation_freshness_warnings"] = freshness_warnings
        row["asset_category"] = _category(symbol)
        row["lane_key"] = _lane_key(row)
        row.update(_mistake_guardrails(row))
        row["rl_reward"] = _reward(row)
        row["rl_action_label"] = _label(row)
        current = best.get(row["lane_key"])
        if current is None or _float(row.get("rl_reward")) > _float(current.get("rl_reward")):
            best[row["lane_key"]] = row
    return list(best.values())


def _reward(row: dict[str, Any]) -> float:
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = _float(row.get("profit_factor"))
    wr = _float(row.get("win_rate"))
    closed = _int(row.get("closed_trades"))
    dd = _float(row.get("max_drawdown_usd"))
    oos = str(row.get("out_of_sample_status") or "not_available")
    mark = str(row.get("mark_index_verdict") or "not_checked")
    micro = str(row.get("microstructure_verdict") or "not_checked")
    ws = str(row.get("ws_quality_verdict") or "not_checked")
    exchange = str(row.get("exchange_filter_verdict") or "not_checked")
    reality = str(row.get("reality_validation_status") or "not_checked")
    freshness = str(row.get("validation_freshness_verdict") or "unknown_source_mtime")
    mistake_risk = _float(row.get("mistake_risk_score"))

    reward = 0.0
    reward += max(min(roi, 40.0), -20.0) * 0.08
    reward += min(pf, 10.0) * 0.20
    reward += wr * 1.5
    reward += min(closed, 80) * 0.025
    reward -= min(dd, 120.0) * 0.035

    reward += {"passed_latest_window_validation": 2.0, "failed_latest_window_validation": -6.0, "not_available": -1.5}.get(oos, -1.0)
    reward += {"mark_index_confirmed": 6.0, "mark_index_watch": 0.5, "mark_index_rejected": -12.0, "not_checked": -2.0}.get(mark, -1.0)
    reward += {"microstructure_ok": 5.0, "thin_liquidity": -7.0, "gap_risk": -8.0, "not_enough_trades": -7.0, "not_checked": -1.5}.get(micro, -2.0)
    reward += {"ws_forward_ready": 2.0, "ws_forward_watch": 0.5, "ws_forward_risky": -4.0, "not_checked": -0.5}.get(ws, -0.5)
    reward += {"ok": 1.0, "warning": -0.5, "blocked": -8.0, "not_checked": -0.5}.get(exchange, -0.5)
    reward += {"validation_passed_clean": 8.0, "validation_passed_watch": 2.0, "validation_rejected_or_rework": -10.0, "not_checked": 0.0}.get(reality, 0.0)
    reward += {"fresh_enough": 0.0, "stale_validation_overlays": -3.0, "unknown_source_mtime": -1.0}.get(freshness, -1.0)
    reward -= min(mistake_risk, 100.0) * 0.06

    if closed < 8:
        reward -= 6.0
    if roi <= 0 or pf < 1.2 or wr < 0.5:
        reward -= 4.0
    return round(max(-25.0, min(25.0, reward)), 6)


def _label(row: dict[str, Any]) -> str:
    reward = _float(row.get("rl_reward"))
    mark = str(row.get("mark_index_verdict") or "not_checked")
    micro = str(row.get("microstructure_verdict") or "not_checked")
    reality = str(row.get("reality_validation_status") or "not_checked")
    oos = str(row.get("out_of_sample_status") or "not_available")
    freshness = str(row.get("validation_freshness_verdict") or "unknown_source_mtime")
    guard = str(row.get("mistake_guardrail_verdict") or "review_required")
    roi = _float(row.get("roi_pct_on_paper_balance"))
    pf = _float(row.get("profit_factor"))
    closed = _int(row.get("closed_trades"))

    if mark == "mark_index_rejected" or micro in {"thin_liquidity", "gap_risk", "not_enough_trades"} or reward < -4:
        return "reject_or_rework"
    if reality == "validation_passed_clean" and reward >= 8 and freshness == "fresh_enough" and guard == "clean":
        return "promote_forward_candidate"
    if reality == "validation_passed_watch" or (mark == "mark_index_confirmed" and micro == "microstructure_ok" and reward >= 5):
        return "forward_watch"
    if roi > 0 and pf >= 1.3 and closed >= 8 and oos == "passed_latest_window_validation":
        return "validate_reality_pack"
    return "explore_more"


def _feature_vector(row: dict[str, Any]) -> dict[str, float]:
    interval = str(row.get("interval") or "")
    minutes = {"15m": 15, "30m": 30, "1h": 60, "2h": 120, "3h": 180, "4h": 240, "5h": 300, "6h": 360}.get(interval, 60)
    category = str(row.get("asset_category") or "altcoin")
    mark = str(row.get("mark_index_verdict") or "not_checked")
    micro = str(row.get("microstructure_verdict") or "not_checked")
    ws = str(row.get("ws_quality_verdict") or "not_checked")
    return {
        "bias": 1.0,
        "roi": max(min(_float(row.get("roi_pct_on_paper_balance")) / 50.0, 1.0), -1.0),
        "pf": min(_float(row.get("profit_factor")) / 10.0, 1.0),
        "wr": _float(row.get("win_rate")),
        "closed": min(_int(row.get("closed_trades")) / 80.0, 1.0),
        "drawdown": min(_float(row.get("max_drawdown_usd")) / 120.0, 1.0),
        "leverage": min(_float(row.get("best_tradable_leverage"), 1.0) / 20.0, 1.0),
        "mistake_risk": min(_float(row.get("mistake_risk_score")) / 100.0, 1.0),
        "family_support": min(_float(row.get("family_support_score")) / 100.0, 1.0),
        "family_blocked_rate": min(_float(row.get("family_blocked_or_review_rate")), 1.0),
        "tf_log": math.log1p(minutes) / math.log1p(360),
        f"cat_{category}": 1.0,
        f"mark_{mark}": 1.0,
        f"micro_{micro}": 1.0,
        f"ws_{ws}": 1.0,
    }


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0.0) * b.get(k, 0.0) for k in keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _action_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        action = str(row.get("rl_action_label") or "explore_more")
        bucket = stats.setdefault(action, {"count": 0, "reward_sum": 0.0, "positive": 0})
        reward = _float(row.get("rl_reward"))
        bucket["count"] += 1
        bucket["reward_sum"] += reward
        bucket["positive"] += 1 if reward > 0 else 0
    for bucket in stats.values():
        count = max(1, _int(bucket.get("count")))
        bucket["avg_reward"] = round(_float(bucket.get("reward_sum")) / count, 6)
        bucket["positive_rate"] = round(_int(bucket.get("positive")) / count, 6)
    return stats


def _category_action_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        category = str(row.get("asset_category") or "unknown")
        action = str(row.get("rl_recommended_action") or row.get("rl_action_label") or "unknown")
        bucket = stats.setdefault(category, {"count": 0, "best_score": None, "actions": {}})
        bucket["count"] += 1
        score = _float(row.get("rl_policy_score"), _float(row.get("rl_reward")))
        if bucket["best_score"] is None or score > _float(bucket["best_score"]):
            bucket["best_score"] = score
        actions = bucket["actions"]
        actions[action] = actions.get(action, 0) + 1
    for bucket in stats.values():
        bucket["best_score"] = round(_float(bucket.get("best_score")), 6)
    return stats


def _strategy_family_key(row: dict[str, Any]) -> str:
    family = str(row.get("strategy_profile_family") or "").strip()
    if not family:
        family = "|".join(
            str(row.get(key) or "").strip()
            for key in ("output_tag", "search_mode", "risk_profile")
            if str(row.get(key) or "").strip()
        )
    return "|".join(
        item
        for item in (
            family or "unknown_family",
            str(row.get("side") or "long").lower(),
            str(row.get("trigger_reference") or row.get("assumed_trigger_reference") or "unknown_trigger"),
            str(row.get("execution_model") or row.get("assumed_execution_model") or "unknown_execution"),
        )
        if item
    )


def _strategy_family_stats(rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _strategy_family_key(row)
        bucket = buckets.setdefault(
            key,
            {
                "strategy_family_key": key,
                "lanes": 0,
                "symbols": set(),
                "intervals": set(),
                "policy_score_sum": 0.0,
                "reward_sum": 0.0,
                "risk_sum": 0.0,
                "clean": 0,
                "watch": 0,
                "review": 0,
                "blocked": 0,
                "best_row": None,
                "best_score": None,
            },
        )
        bucket["lanes"] += 1
        bucket["symbols"].add(str(row.get("symbol") or "").upper())
        bucket["intervals"].add(str(row.get("interval") or ""))
        score = _float(row.get("rl_policy_score"), _float(row.get("rl_reward")))
        bucket["policy_score_sum"] += score
        bucket["reward_sum"] += _float(row.get("rl_reward"))
        bucket["risk_sum"] += _float(row.get("mistake_risk_score"))
        verdict = str(row.get("mistake_guardrail_verdict") or "")
        if verdict == "clean":
            bucket["clean"] += 1
        elif verdict == "watch_only":
            bucket["watch"] += 1
        elif verdict == "review_required":
            bucket["review"] += 1
        elif verdict == "promotion_blocked":
            bucket["blocked"] += 1
        if bucket["best_score"] is None or score > _float(bucket["best_score"]):
            bucket["best_score"] = score
            bucket["best_row"] = row

    out: list[dict[str, Any]] = []
    for bucket in buckets.values():
        lanes = max(1, _int(bucket.get("lanes")))
        unique_symbols = len(bucket["symbols"])
        blocked_rate = (_int(bucket.get("blocked")) + _int(bucket.get("review"))) / lanes
        clean_or_watch_rate = (_int(bucket.get("clean")) + _int(bucket.get("watch"))) / lanes
        avg_score = _float(bucket.get("policy_score_sum")) / lanes
        avg_risk = _float(bucket.get("risk_sum")) / lanes
        best = bucket.get("best_row") or {}
        if unique_symbols < 2 and lanes < 3:
            verdict = "isolated_lane_risk"
        elif blocked_rate >= 0.7:
            verdict = "blocked_family"
        elif unique_symbols >= 3 and clean_or_watch_rate >= 0.35 and avg_score > 0 and avg_risk < 45:
            verdict = "reproducible_watch_candidate"
        elif clean_or_watch_rate > 0:
            verdict = "needs_targeted_validation"
        else:
            verdict = "research_only"
        out.append(
            {
                "strategy_family_key": bucket["strategy_family_key"],
                "family_verdict": verdict,
                "lanes": lanes,
                "unique_symbols": unique_symbols,
                "unique_intervals": len(bucket["intervals"]),
                "avg_policy_score": round(avg_score, 6),
                "avg_reward": round(_float(bucket.get("reward_sum")) / lanes, 6),
                "avg_mistake_risk_score": round(avg_risk, 6),
                "clean_lanes": bucket.get("clean", 0),
                "watch_lanes": bucket.get("watch", 0),
                "review_lanes": bucket.get("review", 0),
                "blocked_lanes": bucket.get("blocked", 0),
                "best_symbol": best.get("symbol"),
                "best_interval": best.get("interval"),
                "best_action": best.get("rl_recommended_action"),
                "best_score": round(_float(bucket.get("best_score")), 6),
                "why_it_matters": "Promote families only when behavior repeats across symbols/timeframes, not because one lane looks lucky.",
            }
        )
    out.sort(
        key=lambda row: (
            row.get("family_verdict") == "reproducible_watch_candidate",
            row.get("family_verdict") == "needs_targeted_validation",
            _float(row.get("avg_policy_score")) - (_float(row.get("avg_mistake_risk_score")) * 0.03),
            _int(row.get("unique_symbols")),
        ),
        reverse=True,
    )
    return out[:limit]


def _family_support_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _strategy_family_key(row)
        bucket = buckets.setdefault(
            key,
            {
                "lanes": 0,
                "symbols": set(),
                "intervals": set(),
                "reward_sum": 0.0,
                "risk_sum": 0.0,
                "positive_rewards": 0,
                "clean": 0,
                "watch": 0,
                "review": 0,
                "blocked": 0,
            },
        )
        bucket["lanes"] += 1
        bucket["symbols"].add(str(row.get("symbol") or "").upper())
        bucket["intervals"].add(str(row.get("interval") or ""))
        reward = _float(row.get("rl_reward"))
        bucket["reward_sum"] += reward
        bucket["risk_sum"] += _float(row.get("mistake_risk_score"))
        bucket["positive_rewards"] += 1 if reward > 0 else 0
        verdict = str(row.get("mistake_guardrail_verdict") or "")
        if verdict == "clean":
            bucket["clean"] += 1
        elif verdict == "watch_only":
            bucket["watch"] += 1
        elif verdict == "review_required":
            bucket["review"] += 1
        elif verdict == "promotion_blocked":
            bucket["blocked"] += 1

    support: dict[str, dict[str, Any]] = {}
    for key, bucket in buckets.items():
        lanes = max(1, _int(bucket.get("lanes")))
        unique_symbols = len(bucket["symbols"])
        unique_intervals = len(bucket["intervals"])
        positive_rate = _int(bucket.get("positive_rewards")) / lanes
        avg_reward = _float(bucket.get("reward_sum")) / lanes
        avg_risk = _float(bucket.get("risk_sum")) / lanes
        blocked_rate = (_int(bucket.get("review")) + _int(bucket.get("blocked"))) / lanes
        support_score = 0.0
        support_score += min(lanes, 12) * 2.0
        support_score += min(unique_symbols, 5) * 8.0
        support_score += min(unique_intervals, 4) * 5.0
        support_score += _int(bucket.get("clean")) * 8.0
        support_score += _int(bucket.get("watch")) * 2.5
        support_score += positive_rate * 20.0
        support_score += max(min(avg_reward, 8.0), -8.0) * 1.5
        support_score -= avg_risk * 0.45
        support_score -= _int(bucket.get("review")) * 2.5
        support_score -= _int(bucket.get("blocked")) * 4.0
        support_score = round(max(0.0, min(100.0, support_score)), 6)

        if unique_symbols < 2 and lanes < 3:
            verdict = "isolated_lane_risk"
        elif blocked_rate >= 0.7:
            verdict = "family_blocked"
        elif support_score >= 65 and unique_symbols >= 3 and unique_intervals >= 2 and blocked_rate < 0.35:
            verdict = "family_supported"
        elif support_score >= 40 and blocked_rate < 0.6:
            verdict = "needs_more_family_validation"
        else:
            verdict = "research_only_family"
        support[key] = {
            "strategy_family_key": key,
            "family_support_score": support_score,
            "lane_family_verdict": verdict,
            "family_lane_count": lanes,
            "family_unique_symbols": unique_symbols,
            "family_unique_intervals": unique_intervals,
            "family_positive_reward_rate": round(positive_rate, 6),
            "family_avg_reward": round(avg_reward, 6),
            "family_avg_mistake_risk_score": round(avg_risk, 6),
            "family_blocked_or_review_rate": round(blocked_rate, 6),
        }
    return support


def _guardrail_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts: dict[str, int] = {}
    actions: dict[str, int] = {}
    total_risk = 0.0
    for row in rows:
        verdict = str(row.get("mistake_guardrail_verdict") or "unknown")
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
        total_risk += _float(row.get("mistake_risk_score"))
        for action in str(row.get("required_next_actions") or "").split(";"):
            action = action.strip()
            if action:
                actions[action] = actions.get(action, 0) + 1
    return {
        "verdict_counts": verdicts,
        "avg_mistake_risk_score": round(total_risk / max(len(rows), 1), 6),
        "top_required_actions": dict(sorted(actions.items(), key=lambda item: item[1], reverse=True)[:12]),
    }


def _compact_gate_rows(rows: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    fields = [
        "symbol",
        "interval",
        "side",
        "rl_recommended_action",
        "rl_policy_score",
        "rl_reward",
        "mistake_guardrail_verdict",
        "mistake_risk_score",
        "mistake_blockers",
        "mistake_warnings",
        "required_next_actions",
        "mark_index_verdict",
        "microstructure_verdict",
        "reality_validation_status",
        "out_of_sample_status",
        "source_file",
    ]
    return [{field: row.get(field) for field in fields} for row in rows[:limit]]


def _quality_gate(rows: list[dict[str, Any]], min_clean_lanes: int = 1) -> dict[str, Any]:
    clean_rows = [
        row
        for row in rows
        if row.get("mistake_guardrail_verdict") == "clean"
        and row.get("rl_recommended_action") == "promote_forward_candidate"
    ]
    watch_rows = [row for row in rows if row.get("mistake_guardrail_verdict") == "watch_only"]
    blocked_rows = [row for row in rows if row.get("mistake_guardrail_verdict") in {"review_required", "promotion_blocked"}]
    required = max(1, int(min_clean_lanes or 1))
    passed = len(clean_rows) >= required
    return {
        "quality_gate_passed": passed,
        "required_clean_promotions": required,
        "clean_promotions": len(clean_rows),
        "watch_only_lanes": len(watch_rows),
        "blocked_or_review_lanes": len(blocked_rows),
        "gate_verdict": "pass" if passed else "blocked_no_clean_promotions",
        "gate_reason": (
            "At least one lane is clean and promotion-ready."
            if passed
            else "No lane can be promoted without rerunning/correcting the listed validation blockers."
        ),
        "top_clean_promotions": _compact_gate_rows(clean_rows),
        "top_watch_lanes": _compact_gate_rows(watch_rows),
        "top_blocked_lanes": _compact_gate_rows(blocked_rows),
    }


def _round_robin_by_category(rows: list[dict[str, Any]], limit: int, max_per_symbol: int = 2) -> list[dict[str, Any]]:
    preferred_order = ["major_crypto", "altcoin", "memecoin", "equity_synthetic", "commodity"]
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("rl_recommended_action") == "reject_or_rework":
            continue
        category = str(row.get("asset_category") or "unknown")
        buckets.setdefault(category, []).append(row)
    category_order = preferred_order + sorted(set(buckets) - set(preferred_order))
    selected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    symbol_counts: dict[str, int] = {}
    index_by_category = {category: 0 for category in category_order}

    while len(selected) < limit:
        progressed = False
        for category in category_order:
            bucket = buckets.get(category) or []
            idx = index_by_category.get(category, 0)
            while idx < len(bucket):
                row = bucket[idx]
                idx += 1
                key = _recommendation_key(row)
                symbol = str(row.get("symbol") or "").upper()
                if key in seen_keys or symbol_counts.get(symbol, 0) >= max_per_symbol:
                    continue
                seen_keys.add(key)
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
                selected.append(dict(row, portfolio_bucket="coverage_multi_asset"))
                progressed = True
                break
            index_by_category[category] = idx
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def _exploration_queue(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    allowed = {"validate_reality_pack", "explore_more", "forward_watch"}
    candidates = [
        row
        for row in rows
        if row.get("rl_recommended_action") in allowed
        and row.get("rl_recommended_action") != "promote_forward_candidate"
        and row.get("microstructure_verdict") not in {"thin_liquidity", "gap_risk", "not_enough_trades"}
        and _int(row.get("closed_trades")) >= 6
        and _float(row.get("profit_factor")) >= 1.15
    ]
    return [dict(row, portfolio_bucket="exploration_or_validation") for row in _round_robin_by_category(candidates, limit, max_per_symbol=1)]


def _has_value(row: dict[str, Any], *fields: str) -> bool:
    return any(str(row.get(field) or "").strip() for field in fields)


def _csv_list_contains(value: Any, target: Any) -> bool:
    clean_target = str(target or "").strip()
    if not clean_target:
        return False
    return clean_target in {item.strip() for item in str(value or "").replace("[", "").replace("]", "").replace('"', "").split(",") if item.strip()}


def _mistake_guardrails(row: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    actions: list[str] = []
    risk = 0

    required_identity = {
        "symbol": _has_value(row, "symbol"),
        "interval": _has_value(row, "interval"),
        "side": _has_value(row, "side"),
        "output_tag": _has_value(row, "output_tag"),
        "strategy_profile": _has_value(row, "strategy_profile_id", "strategy_profile_key"),
        "trigger_reference": _has_value(row, "trigger_reference", "assumed_trigger_reference"),
        "execution_model": _has_value(row, "execution_model", "assumed_execution_model"),
    }
    missing_identity = [name for name, ok in required_identity.items() if not ok]
    if missing_identity:
        blockers.append("identity_incomplete:" + ",".join(missing_identity))
        actions.append("rebuild_csv_with_complete_strategy_identity")
        risk += 30

    source_file = str(row.get("source_file") or "")
    if "_progress_" in source_file:
        blockers.append("source_is_progress_snapshot_not_final_csv")
        actions.append("wait_for_or_use_final_v2_csv")
        risk += 18

    freshness = str(row.get("validation_freshness_verdict") or "unknown_source_mtime")
    if freshness != "fresh_enough":
        blockers.append(f"validator_freshness_not_clean:{freshness}")
        actions.append("rerun_mark_index_microstructure_reality_pack")
        risk += 22

    mark = str(row.get("mark_index_verdict") or "not_checked")
    if mark == "mark_index_rejected":
        blockers.append("mark_index_rejected")
        actions.append("reject_or_rework_mark_index")
        risk += 35
    elif mark == "not_checked":
        warnings.append("mark_index_not_checked")
        actions.append("run_mark_index_replay_filter")
        risk += 14
    elif mark == "mark_index_watch":
        warnings.append("mark_index_watch")
        risk += 7

    micro = str(row.get("microstructure_verdict") or "not_checked")
    if micro in {"thin_liquidity", "gap_risk", "not_enough_trades"}:
        blockers.append(f"microstructure_not_tradable:{micro}")
        actions.append("rerun_or_reduce_size_for_microstructure")
        risk += 35
    elif micro == "not_checked":
        warnings.append("microstructure_not_checked")
        actions.append("run_microstructure_replay_validator")
        risk += 14

    reality = str(row.get("reality_validation_status") or "not_checked")
    if reality == "validation_rejected_or_rework":
        blockers.append("reality_pack_rejected")
        actions.append("inspect_reality_pack_blockers")
        risk += 35
    elif reality == "not_checked":
        warnings.append("reality_pack_not_checked")
        actions.append("run_queue_reality_pack_validator")
        risk += 18
    elif reality == "validation_passed_watch":
        warnings.append("reality_pack_watch")
        risk += 8

    oos = str(row.get("out_of_sample_status") or "not_available")
    if oos == "failed_latest_window_validation":
        blockers.append("out_of_sample_failed")
        actions.append("do_not_promote_retrain_or_retest")
        risk += 35
    elif oos == "not_available":
        warnings.append("out_of_sample_missing")
        actions.append("rerun_discovery_with_train_validation_split")
        risk += 12

    min_closed = max(8, _int(row.get("min_closed_trades_required"), 8))
    closed = _int(row.get("closed_trades"))
    if closed < min_closed:
        blockers.append(f"closed_trades_below_min:{closed}<{min_closed}")
        actions.append("collect_more_history_or_lower_candidate_confidence")
        risk += 25

    exchange = str(row.get("exchange_filter_verdict") or "not_checked")
    if exchange == "blocked":
        blockers.append("exchange_filter_blocked")
        actions.append("respect_exchangeinfo_filters")
        risk += 35
    elif exchange in {"not_checked", "warning"}:
        warnings.append(f"exchange_filter_{exchange}")
        actions.append("rerun_exchangeinfo_enriched_discovery")
        risk += 8

    best_leverage = row.get("best_tradable_leverage")
    if not _has_value(row, "best_tradable_leverage"):
        warnings.append("best_tradable_leverage_missing")
        actions.append("rerun_perps_leverage_scenarios")
        risk += 12
    elif _csv_list_contains(row.get("perps_invalid_leverages"), best_leverage):
        blockers.append("best_leverage_marked_invalid")
        actions.append("fix_perps_leverage_selection")
        risk += 40
    elif _float(best_leverage) >= 20:
        warnings.append("high_leverage_requires_extra_liquidation_review")
        risk += 8

    realized = _float(row.get("pnl_realized_usd"), _float(row.get("pnl_total_usd")))
    including_unrealized = _float(row.get("pnl_total_including_unrealized_usd"), realized)
    open_unrealized = _float(row.get("open_unrealized_pnl_usd"))
    if abs(including_unrealized - realized) > 0.01 or abs(open_unrealized) > 0.01:
        warnings.append("open_unrealized_pnl_separate_from_realized")
        actions.append("rank_on_realized_pnl_not_latent")
        risk += 10

    if _float(row.get("profit_factor")) < 1.3:
        warnings.append("profit_factor_below_decision_threshold")
        risk += 8
    if _float(row.get("win_rate")) < 0.5:
        warnings.append("win_rate_below_half")
        risk += 8

    unique_actions = list(dict.fromkeys(actions))
    if blockers:
        verdict = "promotion_blocked"
    elif risk >= 35:
        verdict = "review_required"
    elif warnings:
        verdict = "watch_only"
    else:
        verdict = "clean"

    return {
        "mistake_risk_score": min(100, risk),
        "mistake_guardrail_verdict": verdict,
        "mistake_blockers": ";".join(blockers),
        "mistake_warnings": ";".join(warnings),
        "required_next_actions": ";".join(unique_actions),
    }


def _policy_score(row: dict[str, Any], training: list[dict[str, Any]]) -> tuple[float, list[str]]:
    vec = _feature_vector(row)
    neighbors: list[tuple[float, float]] = []
    for other in training:
        if other is row:
            continue
        sim = _cosine(vec, _feature_vector(other))
        if sim > 0:
            neighbors.append((sim, _float(other.get("rl_reward"))))
    neighbors.sort(reverse=True)
    top = neighbors[:25]
    if top:
        sim_sum = sum(sim for sim, _ in top)
        neighbor_reward = sum(sim * reward for sim, reward in top) / max(sim_sum, 1e-9)
    else:
        neighbor_reward = 0.0
    blended = (_float(row.get("rl_reward")) * 0.65) + (neighbor_reward * 0.35)
    family_verdict = str(row.get("lane_family_verdict") or "")
    if family_verdict == "family_supported":
        blended += 2.0
    elif family_verdict == "needs_more_family_validation":
        blended += 0.5
    elif family_verdict == "isolated_lane_risk":
        blended -= 2.0
    elif family_verdict == "family_blocked":
        blended -= 5.0
    reasons = []
    for key in ("mark_index_verdict", "microstructure_verdict", "reality_validation_status", "validation_freshness_verdict", "mistake_guardrail_verdict", "lane_family_verdict", "out_of_sample_status", "asset_category"):
        value = row.get(key)
        if value:
            reasons.append(f"{key}={value}")
    return round(blended, 6), reasons[:8]


def get_aster_rl_lane_policy_preview(dry_run: bool = True, top_n: int = 80) -> dict[str, Any]:
    if not dry_run:
        return {"ok": False, "status": "blocked", "blockers": ["dry_run_required"]}

    rows = _decorate_rows(_load_discovery_rows())
    family_support = _family_support_map(rows)
    for row in rows:
        support = family_support.get(_strategy_family_key(row)) or {}
        row.update(support)
        family_verdict = str(row.get("lane_family_verdict") or "")
        family_bonus = (_float(row.get("family_support_score")) / 100.0) * 2.5
        if family_verdict == "family_supported":
            family_bonus += 1.5
        elif family_verdict == "needs_more_family_validation":
            family_bonus += 0.25
        elif family_verdict == "isolated_lane_risk":
            family_bonus -= 2.5
        elif family_verdict == "family_blocked":
            family_bonus -= 4.0
        row["rl_reward"] = round(max(-25.0, min(25.0, _float(row.get("rl_reward")) + family_bonus)), 6)
        row["rl_action_label"] = _label(row)
    # Keep the expensive similarity pass bounded. The direct reward still uses every
    # lane, but KNN only compares the most relevant candidates.
    policy_candidates = sorted(rows, key=lambda row: _float(row.get("rl_reward")), reverse=True)[:1200]
    training_pool = policy_candidates[:500]
    scored_ids = {id(row) for row in policy_candidates}
    for row in rows:
        if id(row) in scored_ids:
            score, reasons = _policy_score(row, training_pool)
        else:
            score, reasons = _float(row.get("rl_reward")), ["outside_similarity_pool=direct_reward_only"]
        row["rl_policy_score"] = score
        row["rl_policy_reasons"] = ";".join(reasons)
        if row.get("rl_action_label") == "promote_forward_candidate" and score < 8:
            row["rl_recommended_action"] = "forward_watch"
        elif row.get("rl_action_label") == "validate_reality_pack" and score < 0:
            row["rl_recommended_action"] = "reject_or_rework"
        elif row.get("rl_action_label") == "promote_forward_candidate" and row.get("mistake_guardrail_verdict") != "clean":
            row["rl_recommended_action"] = "forward_watch"
        elif row.get("rl_action_label") == "promote_forward_candidate" and row.get("lane_family_verdict") != "family_supported":
            row["rl_recommended_action"] = "forward_watch"
        else:
            row["rl_recommended_action"] = row.get("rl_action_label")

    ranked_all = sorted(rows, key=lambda row: (_float(row.get("rl_policy_score")), _float(row.get("rl_reward"))), reverse=True)
    ranked: list[dict[str, Any]] = []
    seen_recommendations: set[str] = set()
    for row in ranked_all:
        key = _recommendation_key(row)
        if key in seen_recommendations:
            continue
        seen_recommendations.add(key)
        ranked.append(row)
    clean_limit = max(1, min(_int(top_n, 80), 500))
    balanced_limit = min(max(clean_limit, 40), 120)
    exploration_limit = min(max(clean_limit // 2, 25), 80)
    balanced = _round_robin_by_category(ranked, balanced_limit, max_per_symbol=2)
    exploration = _exploration_queue(ranked, exploration_limit)
    family_recommendations = _strategy_family_stats(ranked_all, limit=30)
    action_counts: dict[str, int] = {}
    for row in ranked_all:
        action = str(row.get("rl_recommended_action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
    quality_gate = _quality_gate(ranked, min_clean_lanes=1)

    return {
        "ok": True,
        "status": "ready",
        "dry_run": True,
        "generated_at": _now(),
        "methodology": "offline_contextual_bandit_knn_reward_shaped_by_reality_validation",
        "summary": {
            "discovery_lanes_read": len(rows),
            "unique_recommendations": len(ranked),
            "rows_returned": min(clean_limit, len(ranked)),
            "action_counts": action_counts,
            "action_stats": _action_stats(rows),
            "category_action_stats": _category_action_stats(rows),
            "guardrail_stats": _guardrail_stats(rows),
            "quality_gate": quality_gate,
            "freshness": _freshness_summary(rows),
            "top_symbol": ranked[0].get("symbol") if ranked else None,
            "top_action": ranked[0].get("rl_recommended_action") if ranked else None,
            "reward_contract": "ROI alone is insufficient; mark/index rejection and bad microstructure dominate reward penalties.",
            "portfolio_policy": "exploit_best_lanes_but_keep_multi_asset_exploration_alive",
            "balanced_recommendations_returned": len(balanced),
            "exploration_queue_returned": len(exploration),
            "strategy_families_returned": len(family_recommendations),
            "top_strategy_family": family_recommendations[0].get("strategy_family_key") if family_recommendations else None,
            "top_strategy_family_verdict": family_recommendations[0].get("family_verdict") if family_recommendations else None,
        },
        "top_recommendations": ranked[:clean_limit],
        "strategy_family_recommendations": family_recommendations,
        "balanced_portfolio_recommendations": balanced,
        "exploration_queue": exploration,
        "safety": {
            "source_policy": "local_artifacts_only_offline_rl_lane_policy",
            "would_write_db": False,
            "would_execute_trade": False,
            "would_send_wallet_transaction": False,
            "would_create_client_signal": False,
        },
    }


def _cell(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _table(rows: list[dict[str, Any]], limit: int = 80) -> str:
    headers = [
        "rl_recommended_action",
        "portfolio_bucket",
        "rl_policy_score",
        "rl_reward",
        "mistake_guardrail_verdict",
        "mistake_risk_score",
        "lane_family_verdict",
        "family_support_score",
        "family_unique_symbols",
        "symbol",
        "interval",
        "side",
        "asset_category",
        "roi_pct_on_paper_balance",
        "win_rate",
        "profit_factor",
        "closed_trades",
        "mark_index_verdict",
        "microstructure_verdict",
        "reality_validation_status",
        "validation_freshness_verdict",
        "out_of_sample_status",
        "mistake_blockers",
        "required_next_actions",
        "source_file",
    ]
    head = "".join(f"<th>{_cell(h)}</th>" for h in headers)
    body = []
    for row in rows[:limit]:
        body.append("<tr>" + "".join(f"<td>{_cell(row.get(h))}</td>" for h in headers) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _family_table(rows: list[dict[str, Any]], limit: int = 30) -> str:
    headers = [
        "family_verdict",
        "strategy_family_key",
        "lanes",
        "unique_symbols",
        "unique_intervals",
        "avg_policy_score",
        "avg_mistake_risk_score",
        "clean_lanes",
        "watch_lanes",
        "review_lanes",
        "blocked_lanes",
        "best_symbol",
        "best_interval",
        "best_action",
        "why_it_matters",
    ]
    head = "".join(f"<th>{_cell(h)}</th>" for h in headers)
    body = []
    for row in rows[:limit]:
        body.append("<tr>" + "".join(f"<td>{_cell(row.get(h))}</td>" for h in headers) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _write_csv(rows: list[dict[str, Any]]) -> None:
    fields = [
        "rl_recommended_action",
        "rl_policy_score",
        "rl_reward",
        "rl_action_label",
        "mistake_guardrail_verdict",
        "mistake_risk_score",
        "mistake_blockers",
        "mistake_warnings",
        "required_next_actions",
        "strategy_family_key",
        "lane_family_verdict",
        "family_support_score",
        "family_lane_count",
        "family_unique_symbols",
        "family_unique_intervals",
        "family_positive_reward_rate",
        "family_avg_reward",
        "family_avg_mistake_risk_score",
        "family_blocked_or_review_rate",
        "symbol",
        "interval",
        "side",
        "asset_category",
        "output_tag",
        "search_mode",
        "trigger_reference",
        "execution_model",
        "risk_profile",
        "best_tradable_leverage",
        "roi_pct_on_paper_balance",
        "win_rate",
        "profit_factor",
        "closed_trades",
        "max_drawdown_usd",
        "mark_index_verdict",
        "microstructure_verdict",
        "reality_validation_status",
        "validation_freshness_verdict",
        "validation_freshness_warnings",
        "ws_quality_verdict",
        "exchange_filter_verdict",
        "out_of_sample_status",
        "rl_policy_reasons",
        "source_file",
        "lane_key",
    ]
    with CSV_OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_html(payload: dict[str, Any]) -> None:
    rows = payload.get("top_recommendations") or []
    family_rows = payload.get("strategy_family_recommendations") or []
    balanced_rows = payload.get("balanced_portfolio_recommendations") or []
    exploration_rows = payload.get("exploration_queue") or []
    summary = payload.get("summary") or {}
    freshness = summary.get("freshness") or {}
    guardrails = summary.get("guardrail_stats") or {}
    quality_gate = summary.get("quality_gate") or {}
    HTML_OUT.write_text(
        f"""<!doctype html>
<html lang=\"fr\">
<head>
  <meta charset=\"utf-8\" />
  <title>Aster - RL lane policy</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif; margin: 32px; background: #f7f5ef; color: #1f2933; }}
    h1 {{ margin-bottom: 6px; }}
    .lead {{ max-width: 980px; line-height: 1.55; color: #43505c; }}
    .cards {{ display: grid; grid-template-columns: repeat(4, minmax(160px, 1fr)); gap: 12px; margin: 22px 0; }}
    .card {{ background: white; border: 1px solid #e1ded6; border-radius: 14px; padding: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
    .k {{ color: #667085; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
    .v {{ font-size: 24px; font-weight: 750; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; background: white; border-radius: 12px; overflow: hidden; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #ece8df; padding: 8px 9px; text-align: left; vertical-align: top; }}
    th {{ background: #20302a; color: #fff; position: sticky; top: 0; }}
    tr:nth-child(even) td {{ background: #fbfaf6; }}
    .note {{ background: #fff7d6; border: 1px solid #ead58a; border-radius: 12px; padding: 14px; margin: 16px 0 22px; }}
    h2 {{ margin-top: 30px; }}
  </style>
</head>
<body>
  <h1>Aster - RL lane policy</h1>
  <p class=\"lead\">Politique offline type contextual bandit. Ce n'est pas encore un grand modele IA neuronal: c'est un moteur de decision statistique local qui apprend sur nos artefacts de backtest et applique un reward. Il penalise fortement les faux bons backtests: mark/index rejete, microstructure faible, OOS absent ou realite non validee. Il ne trade pas et ne cree aucun signal client.</p>
  <div class=\"cards\">
    <div class=\"card\"><div class=\"k\">Lanes lues</div><div class=\"v\">{_cell(summary.get('discovery_lanes_read'))}</div></div>
    <div class=\"card\"><div class=\"k\">Top symbol</div><div class=\"v\">{_cell(summary.get('top_symbol'))}</div></div>
    <div class=\"card\"><div class=\"k\">Top action</div><div class=\"v\">{_cell(summary.get('top_action'))}</div></div>
    <div class=\"card\"><div class=\"k\">Rows</div><div class=\"v\">{_cell(summary.get('rows_returned'))}</div></div>
  </div>
  <div class=\"note\"><strong>Contrat reward:</strong> { _cell(summary.get('reward_contract')) }</div>
  <div class=\"note\"><strong>Politique portefeuille:</strong> { _cell(summary.get('portfolio_policy')) }. Le top sert a exploiter, la couverture multi-actifs sert a ne pas abandonner les autres univers.</div>
  <div class=\"note\"><strong>Fraicheur:</strong> { _cell(freshness.get('freshness_verdict')) } | artefacts stale: { _cell(', '.join(freshness.get('stale_artifacts') or [])) }</div>
  <div class=\"note\"><strong>Anti-erreur:</strong> verdicts={ _cell(guardrails.get('verdict_counts')) } | risque moyen={ _cell(guardrails.get('avg_mistake_risk_score')) } | actions frequentes={ _cell(guardrails.get('top_required_actions')) }. Une lane n'est promouvable que si <code>mistake_guardrail_verdict=clean</code>.</div>
  <div class=\"note\"><strong>Quality gate:</strong> { _cell(quality_gate.get('gate_verdict')) } | clean promotions={ _cell(quality_gate.get('clean_promotions')) }/{ _cell(quality_gate.get('required_clean_promotions')) } | raison={ _cell(quality_gate.get('gate_reason')) }</div>
  <div class=\"note\"><strong>Pourquoi les lanes ?</strong> Une lane est une experience atomique: symbole + timeframe + side + execution + levier + profil. Le RL ne doit pas croire une lane seule; la table familles ci-dessous verifie si le comportement se repete sur plusieurs lanes.</div>
  <h2>Familles de strategie</h2>
  {_family_table(family_rows)}
  <h2>Top exploitation</h2>
  {_table(rows)}
  <h2>Couverture multi-actifs</h2>
  {_table(balanced_rows)}
  <h2>Queue exploration / validation</h2>
  {_table(exploration_rows)}
</body>
</html>
""",
        encoding="utf-8",
    )


def write_aster_rl_lane_policy(top_n: int = 120) -> dict[str, Any]:
    payload = get_aster_rl_lane_policy_preview(dry_run=True, top_n=top_n)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    csv_rows: list[dict[str, Any]] = []
    for bucket_name, key in (
        ("top_exploitation", "top_recommendations"),
        ("balanced_portfolio", "balanced_portfolio_recommendations"),
        ("exploration_queue", "exploration_queue"),
    ):
        for row in payload.get(key) or []:
            csv_rows.append(dict(row, portfolio_bucket=row.get("portfolio_bucket") or bucket_name))
    _write_csv(csv_rows)
    _write_html(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline contextual-bandit policy for Aster lane selection.")
    parser.add_argument("--top-n", type=int, default=120)
    parser.add_argument("--quality-gate", action="store_true", help="Exit non-zero if no clean promotion-ready lane exists.")
    parser.add_argument("--min-clean-lanes", type=int, default=1, help="Minimum clean promotion-ready lanes required by --quality-gate.")
    args = parser.parse_args()
    payload = write_aster_rl_lane_policy(top_n=args.top_n)
    summary = payload.get("summary") or {}
    if args.quality_gate:
        gate = _quality_gate(payload.get("top_recommendations") or [], min_clean_lanes=args.min_clean_lanes)
        print(json.dumps(gate, indent=2, sort_keys=True, default=str))
        raise SystemExit(0 if gate.get("quality_gate_passed") else 2)
    print(
        f"[{payload.get('generated_at')}] lanes={summary.get('discovery_lanes_read')} "
        f"top={summary.get('top_symbol')} action={summary.get('top_action')} "
        f"csv={CSV_OUT} html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
