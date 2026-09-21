from __future__ import annotations

import json
import html
import os
import re
import shutil
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "arkham"
NORMALIZED_DIR = DATA_DIR / "scrapling" / "normalized"
MANUAL_LABELS_PATH = DATA_DIR / "manual" / "verified_entity_labels.json"
DB_PATH = DATA_DIR / "label_ledger.db"
BACKUP_DIR = DATA_DIR / "backups"

EVM_ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
BLOCKSCOUT_API_URLS = {
    "ethereum": "https://eth.blockscout.com/api/v2",
    "eth": "https://eth.blockscout.com/api/v2",
    "bsc": "https://bsc.blockscout.com/api/v2",
    "polygon": "https://polygon.blockscout.com/api/v2",
    "base": "https://base.blockscout.com/api/v2",
    "arbitrum": "https://arbitrum.blockscout.com/api/v2",
    "optimism": "https://optimism.blockscout.com/api/v2",
}
ETHERSCAN_V2_API = "https://api.etherscan.io/v2/api"
EXPLORER_ADDRESS_URLS = {
    "ethereum": "https://etherscan.io/address/{address}",
    "eth": "https://etherscan.io/address/{address}",
    "bsc": "https://bscscan.com/address/{address}",
    "polygon": "https://polygonscan.com/address/{address}",
    "base": "https://basescan.org/address/{address}",
    "arbitrum": "https://arbiscan.io/address/{address}",
    "optimism": "https://optimistic.etherscan.io/address/{address}",
    "avalanche": "https://snowtrace.io/address/{address}",
}
ETHERSCAN_CHAIN_IDS = {
    "ethereum": "1",
    "eth": "1",
    "bsc": "56",
    "polygon": "137",
    "base": "8453",
    "arbitrum": "42161",
    "optimism": "10",
    "avalanche": "43114",
}

PRIORITY_LABEL_TARGETS = {
    "Binance": 500,
    "OKX": 300,
    "Coinbase": 300,
    "Kraken": 200,
    "KuCoin": 200,
    "Bitget": 200,
    "MEXC": 200,
    "Gate": 200,
    "BlackRock": 100,
    "PancakeSwap": 200,
    "Uniswap": 300,
    "Polymarket": 100,
}

PRIORITY_ENTITY_SLUGS = {
    "Binance": "binance",
    "OKX": "okx",
    "Coinbase": "coinbase",
    "Kraken": "kraken",
    "KuCoin": "kucoin",
    "Bitget": "bitget",
    "MEXC": "mexc",
    "Gate": "gate-io",
    "BlackRock": "blackrock",
    "PancakeSwap": "pancakeswap",
    "Uniswap": "uniswap",
    "Polymarket": "polymarket",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _chain_key(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "eth": "ethereum",
        "ethereum-mainnet": "ethereum",
        "bnb": "bsc",
        "bnb-chain": "bsc",
        "binance-smart-chain": "bsc",
        "arbitrum-one": "arbitrum",
        "matic": "polygon",
        "op": "optimism",
        "avax": "avalanche",
    }
    return aliases.get(raw, raw or "unknown")


def _confidence_rank(value: str | None) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(str(value or "").lower(), 0)


def _address_is_valid_for_chain(chain: str, address: str) -> bool:
    if chain in {"ethereum", "bsc", "polygon", "base", "arbitrum", "optimism", "avalanche"}:
        return bool(EVM_ADDRESS_RE.fullmatch(address))
    if chain == "tron":
        return bool(re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{25,40}", address))
    if chain == "solana":
        return bool(re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", address))
    return bool(address)


def _infer_flags(*parts: Any) -> list[str]:
    text = " ".join(str(part or "") for part in parts).lower()
    rules = {
        "exchange": ("exchange", "cex", "binance", "okx", "kraken", "coinbase", "kucoin", "mexc", "bitget", "gate"),
        "dex": ("dex", "uniswap", "pancakeswap", "amm", "pool", "router"),
        "hot wallet": ("hot wallet", "deposit", "withdrawal"),
        "cold wallet": ("cold wallet", "cold"),
        "fund": ("fund", "blackrock", "etf", "ibit"),
        "protocol": ("protocol", "vault", "bridge", "proxy", "contract"),
        "signer": ("signer", "gnosis safe"),
        "whale": ("whale",),
    }
    flags: list[str] = []
    for label, needles in rules.items():
        if any(needle in text for needle in needles):
            flags.append(label)
    return flags


def _promotion_grade(row: dict[str, Any]) -> dict[str, Any]:
    """Conservative promotion score; this never promotes by itself."""
    chain = _chain_key(row.get("chain"))
    address = str(row.get("address") or "").strip().lower()
    label = str(row.get("label") or "").strip()
    entity = str(row.get("entity") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    evidence = row.get("evidence") or []
    seen_count = int(row.get("seen_count") or 0)
    flags = _infer_flags(label, entity, row.get("wallet_type"))

    score = 0
    reasons: list[str] = []
    blockers: list[str] = []
    if _address_is_valid_for_chain(chain, address):
        score += 20
        reasons.append("chain_address_format_valid")
    else:
        blockers.append("invalid_chain_address_format")
    if source_url.startswith("https://intel.arkm.com/explorer/"):
        score += 25
        reasons.append("arkham_source_url")
    elif source_url:
        score += 10
        reasons.append("source_url_present")
    else:
        blockers.append("missing_source_url")
    if entity:
        score += 15
        reasons.append("entity_present")
    else:
        blockers.append("missing_entity")
    if label and label.lower() != address.lower():
        score += 10
        reasons.append("label_present")
    else:
        blockers.append("missing_human_label")
    if seen_count >= 2:
        score += min(20, seen_count)
        reasons.append("repeated_observation")
    if len(evidence) >= 2:
        score += 10
        reasons.append("multiple_evidence_items")
    if "signer" in flags:
        blockers.append("signer_candidate_requires_manual_review")
    if "Null Address".lower() in label.lower() or address in {"0x0000000000000000000000000000000000000000"}:
        blockers.append("null_or_burn_address")

    eligible = score >= 70 and not blockers
    confidence = "high" if score >= 85 else "medium" if score >= 70 else "low"
    return {
        "score": min(score, 100),
        "eligible": eligible,
        "confidence": confidence,
        "reasons": reasons,
        "blockers": blockers,
    }


def _strict_promotion_grade(row: dict[str, Any]) -> dict[str, Any]:
    """Stricter gate for real trusted-label promotion candidates."""
    base = _promotion_grade(row)
    blockers = list(base.get("blockers") or [])
    reasons = list(base.get("reasons") or [])
    source_url = str(row.get("source_url") or "")
    chain = _chain_key(row.get("chain"))
    entity = str(row.get("entity") or "").strip()
    label = str(row.get("label") or "").strip()
    evidence = row.get("evidence") or []
    seen_count = int(row.get("seen_count") or 0)
    flags = _infer_flags(label, entity, row.get("wallet_type"))
    source = str(row.get("source") or "").strip().lower()
    evidence_text = json.dumps(evidence, ensure_ascii=False, default=str).lower()

    if "/explorer/entity/" not in source_url:
        blockers.append("strict_requires_entity_source_url")
    else:
        reasons.append("strict_entity_source_url")
    source_text = f"{source} {source_url.lower()} {evidence_text}"
    has_verified_source = any(
        marker in source_text
        for marker in (
            "manual_verified",
            "candidate_promotion:",
            "etherscan",
            "blockscout",
            "bscscan",
            "polygonscan",
            "basescan",
            "arbiscan",
            "snowtrace",
            "zerion",
            "cielo",
        )
    )
    if has_verified_source:
        reasons.append("strict_verified_source")
    else:
        blockers.append("strict_requires_verified_or_external_source")
    if "scrapling" in source_text and not has_verified_source:
        blockers.append("strict_blocks_scrapling_only_evidence")
    if seen_count < 5:
        blockers.append("strict_requires_seen_count_5")
    else:
        reasons.append("strict_seen_count_5")
    if len(evidence) < 2:
        blockers.append("strict_requires_multiple_evidence_items")
    else:
        reasons.append("strict_multiple_evidence_items")
    if chain not in {"ethereum", "bsc", "polygon", "base", "arbitrum"}:
        blockers.append("strict_evm_only_for_now")
    if "protocol" in flags and not any(flag in flags for flag in ("exchange", "dex", "fund")):
        blockers.append("strict_protocol_requires_manual_review")
    if not entity or entity.lower() in {"unknown", "null address"}:
        blockers.append("strict_missing_entity")

    blockers = list(dict.fromkeys(blockers))
    reasons = list(dict.fromkeys(reasons))
    score = min(int(base.get("score") or 0), 100)
    strict_ready = bool(base.get("eligible")) and score >= 90 and not blockers
    return {
        **base,
        "score": score,
        "strict_ready": strict_ready,
        "eligible": strict_ready,
        "confidence": "high" if strict_ready else base.get("confidence", "low"),
        "reasons": reasons,
        "blockers": blockers,
    }


def _http_json(url: str, timeout: int = 12) -> dict[str, Any] | list[Any] | None:
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "CoreEquityLabelCorroborator/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _http_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "Mozilla/5.0 CoreEquityLabelCorroborator/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(200_000).decode("utf-8", errors="replace")


def _blockscout_address_url(chain: str, address: str) -> str | None:
    base = BLOCKSCOUT_API_URLS.get(_chain_key(chain))
    if not base:
        return None
    return f"{base}/addresses/{urllib.parse.quote(address)}"


def _explorer_address_url(chain: str, address: str) -> str | None:
    template = EXPLORER_ADDRESS_URLS.get(_chain_key(chain))
    if not template:
        return None
    return template.format(address=urllib.parse.quote(address))


def _explorer_html_evidence(candidate: dict[str, Any], timeout: int = 12) -> tuple[list[dict[str, Any]], list[str], int]:
    chain = _chain_key(candidate.get("chain"))
    address = str(candidate.get("address") or "").strip().lower()
    url = _explorer_address_url(chain, address)
    if not url:
        return [], ["explorer_chain_not_supported"], 0
    try:
        text = _http_text(url, timeout=timeout)
    except Exception as exc:
        return [], [f"explorer_html_error:{type(exc).__name__}"], 0

    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""
    body_hint = " ".join(re.findall(r"(?:data-bs-title|title|aria-label)=[\"']([^\"']{2,120})[\"']", text[:80_000], flags=re.I))[:800]
    haystack = f"{title} {body_hint}".lower()
    entity = str(candidate.get("entity") or "").strip().lower()
    label = str(candidate.get("label") or "").strip().lower()
    label_parts = [part.strip() for part in re.split(r"[:|/\\-]", label) if len(part.strip()) >= 3]
    score = 10
    blockers: list[str] = []
    if entity and entity in haystack:
        score += 35
    elif label_parts and any(part in haystack for part in label_parts):
        score += 25
    else:
        blockers.append("explorer_html_does_not_confirm_entity")

    return [
        {
            "source": "explorer_html_title",
            "url": url,
            "title": title[:180],
            "chain": chain,
        }
    ], blockers, score


def _etherscan_api_key() -> str:
    return os.getenv("ETHERSCAN_API_KEY", "").strip()


def _etherscan_get(params: dict[str, Any], timeout: int = 12) -> dict[str, Any] | None:
    key = _etherscan_api_key()
    if not key:
        return None
    query = urllib.parse.urlencode({**params, "apikey": key})
    payload = _http_json(f"{ETHERSCAN_V2_API}?{query}", timeout=timeout)
    return payload if isinstance(payload, dict) else None


def _etherscan_activity_evidence(chain: str, address: str, timeout: int = 12) -> tuple[list[dict[str, Any]], list[str], int]:
    chain_id = ETHERSCAN_CHAIN_IDS.get(_chain_key(chain))
    if not chain_id:
        return [], ["etherscan_chain_not_supported"], 0
    if not _etherscan_api_key():
        return [], ["etherscan_api_key_missing"], 0

    evidence: list[dict[str, Any]] = []
    blockers: list[str] = []
    score = 0
    try:
        balance = _etherscan_get(
            {
                "chainid": chain_id,
                "module": "account",
                "action": "balance",
                "address": address,
                "tag": "latest",
            },
            timeout=timeout,
        )
        if balance and str(balance.get("status")) in {"1", "0"}:
            evidence.append(
                {
                    "source": "etherscan_balance",
                    "chain_id": chain_id,
                    "result_wei": str(balance.get("result") or "0"),
                }
            )
            score += 10
    except Exception as exc:
        blockers.append(f"etherscan_balance_error:{type(exc).__name__}")

    try:
        txs = _etherscan_get(
            {
                "chainid": chain_id,
                "module": "account",
                "action": "txlist",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "page": 1,
                "offset": 1,
                "sort": "desc",
            },
            timeout=timeout,
        )
        result = txs.get("result") if txs else None
        if isinstance(result, list) and result:
            latest = result[0]
            evidence.append(
                {
                    "source": "etherscan_recent_tx",
                    "chain_id": chain_id,
                    "hash": latest.get("hash"),
                    "from": latest.get("from"),
                    "to": latest.get("to"),
                    "timeStamp": latest.get("timeStamp"),
                }
            )
            score += 15
        else:
            blockers.append("etherscan_no_recent_tx")
    except Exception as exc:
        blockers.append(f"etherscan_txlist_error:{type(exc).__name__}")

    return evidence, blockers, score


def _corroborate_candidate(candidate: dict[str, Any], timeout: int = 12) -> dict[str, Any]:
    chain = _chain_key(candidate.get("chain"))
    address = str(candidate.get("address") or "").strip().lower()
    evidence: list[dict[str, Any]] = []
    blockers: list[str] = []
    score = 0

    if not _address_is_valid_for_chain(chain, address):
        blockers.append("invalid_chain_address_format")
        return {
            **candidate,
            "corroboration": {
                "status": "blocked",
                "score": 0,
                "evidence": evidence,
                "blockers": blockers,
                "source_policy": "read-only corroboration; no trusted labels are written",
            },
        }

    blockscout_url = _blockscout_address_url(chain, address)
    if blockscout_url:
        try:
            payload = _http_json(blockscout_url, timeout=timeout)
            if isinstance(payload, dict):
                score += 20
                name = payload.get("name") or payload.get("ens_domain_name") or ""
                metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
                evidence.append(
                    {
                        "source": "blockscout_address",
                        "url": blockscout_url,
                        "address": payload.get("hash") or address,
                        "name": name,
                        "is_contract": bool(payload.get("is_contract")),
                        "tags": tags[:8],
                    }
                )
                text = " ".join(
                    [
                        str(name or ""),
                        " ".join(str(tag.get("name") if isinstance(tag, dict) else tag) for tag in tags),
                    ]
                ).lower()
                entity = str(candidate.get("entity") or "").lower()
                label = str(candidate.get("label") or "").lower()
                if entity and entity in text:
                    score += 45
                elif label and any(part and part in text for part in re.split(r"[:|/\\-]", label)):
                    score += 25
                else:
                    blockers.append("blockscout_public_page_does_not_confirm_entity")
            else:
                blockers.append("blockscout_unexpected_response")
        except Exception as exc:
            blockers.append(f"blockscout_error:{type(exc).__name__}")
    else:
        blockers.append("blockscout_chain_not_supported")

    explorer_evidence, explorer_blockers, explorer_score = _explorer_html_evidence(
        candidate,
        timeout=timeout,
    )
    evidence.extend(explorer_evidence)
    blockers.extend(explorer_blockers)
    score += explorer_score

    etherscan_evidence, etherscan_blockers, etherscan_score = _etherscan_activity_evidence(
        chain,
        address,
        timeout=timeout,
    )
    evidence.extend(etherscan_evidence)
    blockers.extend(etherscan_blockers)
    score += etherscan_score

    candidate_grade = _strict_promotion_grade(
        {
            **candidate,
            "evidence": _merge_unique(candidate.get("evidence") or [], evidence),
        }
    )
    if candidate_grade.get("strict_ready"):
        score += 25
    else:
        blockers.extend(candidate_grade.get("blockers") or [])

    blockers = list(dict.fromkeys(blockers))
    warnings: list[str] = []
    if score >= 70 and len(evidence) >= 2 and "etherscan_api_key_missing" in blockers:
        blockers = [blocker for blocker in blockers if blocker != "etherscan_api_key_missing"]
        warnings.append("etherscan_api_key_missing")
    status = "verified_source_ready" if score >= 70 and not blockers else "needs_more_evidence"
    return {
        **candidate,
        "corroboration": {
            "status": status,
            "score": min(score, 100),
            "evidence": evidence,
            "blockers": blockers,
            "warnings": warnings,
            "source_policy": "read-only corroboration; no trusted labels are written",
        },
    }


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS labels (
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                label TEXT,
                entity TEXT,
                wallet_type TEXT,
                confidence TEXT,
                flags_json TEXT NOT NULL DEFAULT '[]',
                tags_json TEXT NOT NULL DEFAULT '[]',
                sources_json TEXT NOT NULL DEFAULT '[]',
                first_seen_source_at TEXT,
                last_seen_source_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chain, address)
            );
            CREATE INDEX IF NOT EXISTS idx_labels_entity ON labels(entity);
            CREATE INDEX IF NOT EXISTS idx_labels_chain ON labels(chain);
            CREATE INDEX IF NOT EXISTS idx_labels_confidence ON labels(confidence);

            CREATE TABLE IF NOT EXISTS derived_labels (
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                derived_label TEXT NOT NULL,
                related_entity TEXT,
                relation_type TEXT NOT NULL,
                confidence TEXT NOT NULL,
                evidence_count INTEGER NOT NULL DEFAULT 0,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (chain, address, derived_label, relation_type)
            );
            CREATE INDEX IF NOT EXISTS idx_derived_entity ON derived_labels(related_entity);
            CREATE INDEX IF NOT EXISTS idx_derived_chain ON derived_labels(chain);
            CREATE INDEX IF NOT EXISTS idx_derived_confidence ON derived_labels(confidence);

            CREATE TABLE IF NOT EXISTS label_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                proposed_label TEXT,
                proposed_entity TEXT,
                proposed_wallet_type TEXT,
                confidence TEXT NOT NULL DEFAULT 'low',
                status TEXT NOT NULL DEFAULT 'candidate',
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                source_url TEXT,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                seen_count INTEGER NOT NULL DEFAULT 1,
                UNIQUE (chain, address, source_key)
            );
            CREATE INDEX IF NOT EXISTS idx_label_candidates_status ON label_candidates(status);
            CREATE INDEX IF NOT EXISTS idx_label_candidates_entity ON label_candidates(proposed_entity);
            CREATE INDEX IF NOT EXISTS idx_label_candidates_chain ON label_candidates(chain);

            CREATE TABLE IF NOT EXISTS label_candidate_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL,
                chain TEXT NOT NULL,
                address TEXT NOT NULL,
                source TEXT NOT NULL,
                source_key TEXT NOT NULL,
                status TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                evidence_json TEXT NOT NULL DEFAULT '[]',
                blockers_json TEXT NOT NULL DEFAULT '[]',
                observed_at TEXT NOT NULL,
                UNIQUE(candidate_id, source_key)
            );
            CREATE INDEX IF NOT EXISTS idx_label_candidate_evidence_candidate ON label_candidate_evidence(candidate_id);
            CREATE INDEX IF NOT EXISTS idx_label_candidate_evidence_status ON label_candidate_evidence(status);
            CREATE INDEX IF NOT EXISTS idx_label_candidate_evidence_chain ON label_candidate_evidence(chain);

            CREATE TABLE IF NOT EXISTS label_promotion_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                dry_run INTEGER NOT NULL,
                confirm TEXT,
                candidate_ids_json TEXT NOT NULL DEFAULT '[]',
                result_json TEXT NOT NULL DEFAULT '{}',
                backup_path TEXT,
                requested INTEGER NOT NULL DEFAULT 0,
                reviewed INTEGER NOT NULL DEFAULT 0,
                promoted INTEGER NOT NULL DEFAULT 0,
                source_policy TEXT NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


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


def _merge_unique(left: list[Any], right: list[Any]) -> list[Any]:
    seen: set[str] = set()
    merged: list[Any] = []
    for item in [*left, *right]:
        key = json.dumps(item, sort_keys=True, default=str) if isinstance(item, (dict, list)) else str(item)
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _source_name_from_entry(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("source") or "unknown").strip() or "unknown"
    return str(entry or "unknown").strip() or "unknown"


def _trusted_label_source_audit(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT sources_json FROM labels").fetchall()
    source_counts: dict[str, int] = {}
    buckets = {
        "manual_verified": 0,
        "candidate_promotion": 0,
        "external_public": 0,
        "legacy_scrapling": 0,
        "unknown": 0,
    }

    for (sources_json,) in rows:
        sources = _json_list(sources_json)
        names = {_source_name_from_entry(source) for source in sources} or {"unknown"}
        for name in names:
            source_counts[name] = source_counts.get(name, 0) + 1

        lowered = " ".join(sorted(names)).lower()
        if any(name.startswith("candidate_promotion:") for name in names):
            buckets["candidate_promotion"] += 1
        elif "manual_verified" in lowered:
            buckets["manual_verified"] += 1
        elif any(public in lowered for public in ("etherscan", "blockscout", "zerion", "cielo")):
            buckets["external_public"] += 1
        elif "scrapling" in lowered:
            buckets["legacy_scrapling"] += 1
        else:
            buckets["unknown"] += 1

    return {
        "by_source": [
            {"source": source, "labels": count}
            for source, count in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)
        ],
        "trust_buckets": buckets,
        "warning": (
            "legacy_scrapling labels are preserved for display/backward compatibility, "
            "but new Scrapling/Arkham observations are candidates only until strict promotion."
        ),
    }


def _evidence_source_key(candidate_id: int, evidence: list[dict[str, Any]], blockers: list[str]) -> str:
    source_names = sorted({str(item.get("source") or "unknown") for item in evidence if isinstance(item, dict)})
    blocker_names = sorted(str(item) for item in blockers)
    raw = json.dumps(
        {
            "candidate_id": candidate_id,
            "sources": source_names,
            "blockers": blocker_names,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return raw[:500]


def _store_candidate_evidence(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    candidate_id = int(row.get("id") or 0)
    if candidate_id <= 0:
        return False
    corroboration = row.get("corroboration") if isinstance(row.get("corroboration"), dict) else {}
    evidence = corroboration.get("evidence") if isinstance(corroboration.get("evidence"), list) else []
    blockers = corroboration.get("blockers") if isinstance(corroboration.get("blockers"), list) else []
    if not evidence and not blockers:
        return False
    now = _utc_now()
    source_key = _evidence_source_key(candidate_id, evidence, blockers)
    before = conn.total_changes
    conn.execute(
        """
        INSERT INTO label_candidate_evidence (
            candidate_id, chain, address, source, source_key, status, score,
            evidence_json, blockers_json, observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(candidate_id, source_key) DO UPDATE SET
            status = excluded.status,
            score = excluded.score,
            evidence_json = excluded.evidence_json,
            blockers_json = excluded.blockers_json,
            observed_at = excluded.observed_at
        """,
        (
            candidate_id,
            _chain_key(row.get("chain")),
            str(row.get("address") or "").lower(),
            "corroboration_bundle",
            source_key,
            str(corroboration.get("status") or "unknown"),
            int(corroboration.get("score") or 0),
            json.dumps(evidence, ensure_ascii=False, sort_keys=True),
            json.dumps(blockers, ensure_ascii=False, sort_keys=True),
            now,
        ),
    )
    return conn.total_changes > before


def _backup_label_ledger_db(reason: str) -> str:
    """Create a point-in-time SQLite file backup before trusted label writes."""
    if not DB_PATH.exists():
        return ""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "_", reason).strip("_") or "backup"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"label_ledger_{safe_reason}_{stamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    return str(backup_path)


def _upsert_label(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    address = str(row.get("address") or "").strip().lower()
    if not address:
        return False
    chain = _chain_key(row.get("chain"))
    now = _utc_now()
    source = {
        "source": row.get("source") or "unknown",
        "file": row.get("file"),
        "generated_at": row.get("generated_at"),
    }
    if row.get("source_url"):
        source["url"] = row.get("source_url")
    if row.get("evidence"):
        source["evidence"] = row.get("evidence")
    flags = _merge_unique(
        [str(flag).strip() for flag in row.get("flags") or [] if str(flag).strip()],
        _infer_flags(row.get("label"), row.get("entity"), row.get("wallet_type")),
    )
    tags = [str(tag).strip() for tag in row.get("tags") or [] if str(tag).strip()]

    existing = conn.execute(
        "SELECT label, entity, wallet_type, confidence, flags_json, tags_json, sources_json, first_seen_source_at FROM labels WHERE chain = ? AND address = ?",
        (chain, address),
    ).fetchone()

    if existing:
        old_label, old_entity, old_type, old_confidence, old_flags, old_tags, old_sources, first_seen = existing
        confidence = row.get("confidence") or old_confidence or "medium"
        if _confidence_rank(old_confidence) > _confidence_rank(confidence):
            confidence = old_confidence
        label = row.get("label") or old_label
        entity = row.get("entity") or old_entity
        wallet_type = row.get("wallet_type") or old_type
        conn.execute(
            """
            UPDATE labels
            SET label = ?, entity = ?, wallet_type = ?, confidence = ?, flags_json = ?,
                tags_json = ?, sources_json = ?, last_seen_source_at = ?, updated_at = ?
            WHERE chain = ? AND address = ?
            """,
            (
                label,
                entity,
                wallet_type,
                confidence,
                json.dumps(_merge_unique(_json_list(old_flags), flags), ensure_ascii=False),
                json.dumps(_merge_unique(_json_list(old_tags), tags), ensure_ascii=False),
                json.dumps(_merge_unique(_json_list(old_sources), [source]), ensure_ascii=False),
                str(row.get("generated_at") or now),
                now,
                chain,
                address,
            ),
        )
        return False

    conn.execute(
        """
        INSERT INTO labels (
            chain, address, label, entity, wallet_type, confidence, flags_json, tags_json,
            sources_json, first_seen_source_at, last_seen_source_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chain,
            address,
            row.get("label"),
            row.get("entity"),
            row.get("wallet_type"),
            row.get("confidence") or "medium",
            json.dumps(flags, ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
            json.dumps([source], ensure_ascii=False),
            str(row.get("generated_at") or now),
            str(row.get("generated_at") or now),
            now,
        ),
    )
    return True


def _candidate_source_key(row: dict[str, Any]) -> str:
    parts = [
        row.get("source") or "unknown",
        row.get("source_url") or "",
        row.get("file") or "",
        row.get("label") or "",
        row.get("entity") or "",
        row.get("wallet_type") or "",
    ]
    return "|".join(str(part).strip().lower() for part in parts if str(part or "").strip())[:500] or "unknown"


def _entity_source_slug(entity: str) -> str:
    if entity in PRIORITY_ENTITY_SLUGS:
        return PRIORITY_ENTITY_SLUGS[entity]
    slug = re.sub(r"[^a-z0-9]+", "-", str(entity or "").strip().lower()).strip("-")
    return slug or "unknown"


def _stage_label_candidate(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    """Track every observed label proposal without promoting it to trusted intelligence."""
    address = str(row.get("address") or "").strip().lower()
    if not address:
        return False
    chain = _chain_key(row.get("chain"))
    now = _utc_now()
    evidence = []
    if row.get("evidence"):
        evidence.append(row.get("evidence"))
    if row.get("file"):
        evidence.append({"file": row.get("file")})
    if row.get("tags"):
        evidence.append({"tags": row.get("tags")})
    source_key = _candidate_source_key(row)

    existing = conn.execute(
        "SELECT id, evidence_json, seen_count FROM label_candidates WHERE chain = ? AND address = ? AND source_key = ?",
        (chain, address, source_key),
    ).fetchone()
    if not existing and row.get("source_url"):
        legacy_key = _candidate_source_key({**row, "source_url": None})
        existing = conn.execute(
            "SELECT id, evidence_json, seen_count FROM label_candidates WHERE chain = ? AND address = ? AND source_key = ?",
            (chain, address, legacy_key),
        ).fetchone()
    if existing:
        candidate_id, old_evidence, seen_count = existing
        conn.execute(
            """
            UPDATE label_candidates
            SET proposed_label = ?, proposed_entity = ?, proposed_wallet_type = ?, confidence = ?,
                source_key = ?, source_url = ?, evidence_json = ?, last_seen_at = ?, seen_count = ?
            WHERE id = ?
            """,
            (
                row.get("label"),
                row.get("entity"),
                row.get("wallet_type"),
                row.get("confidence") or "low",
                source_key,
                row.get("source_url"),
                json.dumps(_merge_unique(_json_list(old_evidence), evidence), ensure_ascii=False),
                now,
                int(seen_count or 0) + 1,
                candidate_id,
            ),
        )
        return False

    conn.execute(
        """
        INSERT INTO label_candidates (
            chain, address, proposed_label, proposed_entity, proposed_wallet_type,
            confidence, status, source, source_key, source_url, evidence_json,
            first_seen_at, last_seen_at, seen_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            chain,
            address,
            row.get("label"),
            row.get("entity"),
            row.get("wallet_type"),
            row.get("confidence") or "low",
            "candidate",
            row.get("source") or "unknown",
            source_key,
            row.get("source_url"),
            json.dumps(evidence, ensure_ascii=False),
            now,
            now,
            1,
        ),
    )
    return True


def _merge_legacy_url_candidates(conn: sqlite3.Connection) -> int:
    """Merge pre-URL candidate rows into their newer URL-backed candidate row."""
    rows = conn.execute(
        """
        SELECT id, chain, address, source_key, source_url, evidence_json, seen_count
        FROM label_candidates
        WHERE source_url IS NOT NULL AND source_url != ''
        """
    ).fetchall()
    merged = 0
    for row in rows:
        candidate_id, chain, address, source_key, _source_url, evidence_json, seen_count = row
        parts = str(source_key or "").split("|")
        if len(parts) < 2:
            continue
        legacy_key = "|".join([parts[0], *parts[2:]])
        legacy = conn.execute(
            """
            SELECT id, evidence_json, seen_count
            FROM label_candidates
            WHERE chain = ? AND address = ? AND source_key = ? AND id != ?
            """,
            (chain, address, legacy_key, candidate_id),
        ).fetchone()
        if not legacy:
            continue
        legacy_id, legacy_evidence, legacy_seen = legacy
        conn.execute(
            """
            UPDATE label_candidates
            SET evidence_json = ?, seen_count = ?
            WHERE id = ?
            """,
            (
                json.dumps(_merge_unique(_json_list(evidence_json), _json_list(legacy_evidence)), ensure_ascii=False),
                int(seen_count or 0) + int(legacy_seen or 0),
                candidate_id,
            ),
        )
        conn.execute("DELETE FROM label_candidates WHERE id = ?", (legacy_id,))
        merged += 1
    return merged


def _rows_from_scrapling_file(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    generated_at = payload.get("generated_at")
    source = payload.get("source") or "scrapling_normalized"
    source_url = payload.get("final_url") or payload.get("url")
    entity = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
    profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
    entity_name = str(entity.get("name") or profile.get("name") or payload.get("target") or "").strip()

    def add_row(raw: dict[str, Any], *, fallback_entity: str = "", row_source: str = source) -> None:
        address = str(raw.get("address") or "").strip()
        if not address:
            return
        label = str(raw.get("label") or raw.get("name") or "").strip()
        row_entity = str(raw.get("entity") or fallback_entity or "").strip()
        rows.append({
            "address": address,
            "chain": raw.get("chain") or raw.get("network") or "unknown",
            "label": label or address,
            "entity": row_entity,
            "wallet_type": raw.get("wallet_type") or raw.get("type") or "",
            "confidence": raw.get("confidence") or ("high" if row_entity else "medium"),
            "flags": raw.get("flags") or [],
            "tags": raw.get("matched_tags") or raw.get("tags") or raw.get("token_symbols") or [],
            "source": row_source,
            "source_url": source_url,
            "file": path.name,
            "generated_at": generated_at,
        })

    for wallet in payload.get("wallets") or []:
        if isinstance(wallet, dict):
            add_row(wallet, fallback_entity=entity_name, row_source="scrapling_wallet")

    for counterparty in payload.get("counterparties") or []:
        if isinstance(counterparty, dict):
            add_row(counterparty, fallback_entity="", row_source="scrapling_counterparty")

    for transfer in payload.get("transfers") or []:
        if not isinstance(transfer, dict):
            continue
        for side in ("from", "to"):
            address = str(transfer.get(side) or "").strip()
            if not address:
                continue
            rows.append({
                "address": address,
                "chain": transfer.get(f"{side}_chain") or transfer.get("chain") or "unknown",
                "label": transfer.get(f"{side}_display_label") or transfer.get(f"{side}_label") or address,
                "entity": transfer.get(f"{side}_entity") or "",
                "wallet_type": transfer.get(f"{side}_wallet_type") or "",
                "confidence": "medium",
                "flags": _infer_flags(
                    transfer.get(f"{side}_display_label"),
                    transfer.get(f"{side}_entity"),
                    transfer.get(f"{side}_wallet_type"),
                ),
                "tags": [transfer.get("token_symbol")] if transfer.get("token_symbol") else [],
                "source": "scrapling_transfer_side",
                "source_url": source_url,
                "file": path.name,
                "generated_at": generated_at,
            })

    for tag in [*(entity.get("tags") or []), *(profile.get("tags") or [])]:
        if not isinstance(tag, str):
            continue
        for match in EVM_ADDRESS_RE.findall(tag):
            rows.append({
                "address": match,
                "chain": "ethereum",
                "label": tag[:180],
                "entity": entity_name,
                "wallet_type": "signer" if "signer" in tag.lower() else "",
                "confidence": "medium",
                "flags": _infer_flags(tag),
                "tags": [tag[:180]],
                "source": "scrapling_profile_tag",
                "source_url": source_url,
                "file": path.name,
                "generated_at": generated_at,
            })

    return rows


def _rows_from_manual_label_file(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    generated_at = payload.get("generated_at")
    for raw in payload.get("labels") or []:
        if not isinstance(raw, dict):
            continue
        address = str(raw.get("address") or "").strip()
        if not address:
            continue
        rows.append(
            {
                "address": address,
                "chain": raw.get("chain") or "ethereum",
                "label": raw.get("label") or address,
                "entity": raw.get("entity") or "",
                "wallet_type": raw.get("wallet_type") or "",
                "confidence": raw.get("confidence") or "medium",
                "flags": raw.get("flags") or [],
                "tags": raw.get("tags") or [],
                "source": raw.get("source") or payload.get("source") or "manual_verified",
                "source_url": raw.get("source_url"),
                "evidence": raw.get("evidence"),
                "file": path.name,
                "generated_at": raw.get("verified_at") or generated_at,
            }
        )
    return rows


def build_label_ledger(limit_files: int | None = None) -> dict[str, Any]:
    """Build local candidate evidence plus trusted labels from verified manual seeds.

    Scrapling/Arkham snapshots are evidence, not trusted labels. They are staged
    as candidates only; promotion to `labels` must pass the explicit strict gate.
    """
    _init_db()
    files = sorted(NORMALIZED_DIR.glob("*.json")) if NORMALIZED_DIR.exists() else []
    if limit_files:
        files = files[: max(1, int(limit_files))]

    conn = sqlite3.connect(str(DB_PATH))
    inserted = 0
    candidates_inserted = 0
    candidates_merged = 0
    observed = 0
    try:
        for path in files:
            for row in _rows_from_scrapling_file(path):
                observed += 1
                if _stage_label_candidate(conn, row):
                    candidates_inserted += 1
        if MANUAL_LABELS_PATH.exists():
            for row in _rows_from_manual_label_file(MANUAL_LABELS_PATH):
                observed += 1
                if _stage_label_candidate(conn, row):
                    candidates_inserted += 1
                if _upsert_label(conn, row):
                    inserted += 1
        candidates_merged = _merge_legacy_url_candidates(conn)
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "db_path": str(DB_PATH),
        "files_scanned": len(files),
        "rows_observed": observed,
        "rows_inserted": inserted,
        "candidates_inserted": candidates_inserted,
        "candidates_merged": candidates_merged,
        "summary": get_label_ledger_summary(),
    }


def stage_label_candidates_from_normalized_sources(
    limit_files: int | None = None,
    target_stems: list[str] | None = None,
) -> dict[str, Any]:
    """Stage observed source rows as candidates only; never writes trusted labels."""
    _init_db()
    allowed_stems = {str(stem).strip() for stem in target_stems or [] if str(stem).strip()}
    files = sorted(NORMALIZED_DIR.glob("*.json")) if NORMALIZED_DIR.exists() else []
    if allowed_stems:
        files = [path for path in files if path.stem in allowed_stems]
    if limit_files:
        files = files[: max(1, int(limit_files))]

    conn = sqlite3.connect(str(DB_PATH))
    candidates_inserted = 0
    candidates_merged = 0
    observed = 0
    try:
        for path in files:
            for row in _rows_from_scrapling_file(path):
                observed += 1
                if _stage_label_candidate(conn, row):
                    candidates_inserted += 1
        candidates_merged = _merge_legacy_url_candidates(conn)
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "db_path": str(DB_PATH),
        "files_scanned": len(files),
        "target_stems": sorted(allowed_stems),
        "rows_observed": observed,
        "candidates_inserted": candidates_inserted,
        "candidates_merged": candidates_merged,
        "summary": get_label_ledger_summary(),
        "source_policy": "candidate-only staging; trusted labels are never changed by this function",
    }


def stage_label_candidates_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Stage explicit candidate rows only; never writes trusted labels."""
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    observed = 0
    candidates_inserted = 0
    candidates_merged = 0
    try:
        for row in rows:
            observed += 1
            if _stage_label_candidate(conn, row):
                candidates_inserted += 1
        candidates_merged = _merge_legacy_url_candidates(conn)
        conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "db_path": str(DB_PATH),
        "rows_observed": observed,
        "candidates_inserted": candidates_inserted,
        "candidates_merged": candidates_merged,
        "summary": get_label_ledger_summary(),
        "source_policy": "explicit candidate-only staging; trusted labels are never changed by this function",
    }


def backfill_candidate_entity_source_urls(
    source: str = "rpc_label_source_gap",
    limit: int = 25,
    entity: str | None = None,
    chain: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Backfill canonical Arkham entity source URLs on candidates only.

    This improves traceability for review/corroboration, but never promotes or
    writes trusted labels.
    """
    _init_db()
    safe_limit = max(1, min(int(limit or 25), 100))
    where = [
        "status = 'candidate'",
        "source = ?",
        "(source_url IS NULL OR TRIM(source_url) = '')",
        "COALESCE(proposed_entity, '') != ''",
    ]
    params: list[Any] = [source]
    if entity:
        where.append("LOWER(proposed_entity) LIKE ?")
        params.append(f"%{entity.lower()}%")
    if chain:
        where.append("chain = ?")
        params.append(_chain_key(chain))

    conn = sqlite3.connect(str(DB_PATH))
    rows_updated = 0
    conflicts_skipped = 0
    rows_out: list[dict[str, Any]] = []
    try:
        rows = conn.execute(
            f"""
            SELECT id, chain, address, proposed_label, proposed_entity,
                   proposed_wallet_type, confidence, source, source_key,
                   evidence_json, seen_count
            FROM label_candidates
            WHERE {' AND '.join(where)}
            ORDER BY seen_count DESC, last_seen_at DESC, id ASC
            LIMIT ?
            """,
            [*params, safe_limit],
        ).fetchall()
        for row in rows:
            candidate_id = int(row[0])
            candidate = {
                "id": candidate_id,
                "chain": row[1],
                "address": row[2],
                "label": row[3],
                "entity": row[4],
                "wallet_type": row[5],
                "confidence": row[6],
                "source": row[7],
                "source_key": row[8],
                "evidence": _json_list(row[9]),
                "seen_count": int(row[10] or 0),
            }
            slug = _entity_source_slug(str(candidate["entity"] or ""))
            if slug == "unknown":
                rows_out.append({**candidate, "action": "skipped_unknown_entity_slug"})
                continue
            source_url = f"https://intel.arkm.com/explorer/entity/{slug}"
            new_key = _candidate_source_key(
                {
                    "source": candidate["source"],
                    "source_url": source_url,
                    "label": candidate["label"],
                    "entity": candidate["entity"],
                    "wallet_type": candidate["wallet_type"],
                }
            )
            conflict = conn.execute(
                """
                SELECT id
                FROM label_candidates
                WHERE chain = ? AND address = ? AND source_key = ? AND id != ?
                """,
                (_chain_key(candidate["chain"]), str(candidate["address"] or "").lower(), new_key, candidate_id),
            ).fetchone()
            if conflict:
                conflicts_skipped += 1
                rows_out.append({**candidate, "source_url": source_url, "action": "skipped_source_key_conflict"})
                continue

            backfill_evidence = {
                "source": "candidate_entity_source_url_backfill",
                "url": source_url,
                "reason": "canonical_entity_slug",
                "trusted_label_promotion": False,
            }
            merged_evidence = _merge_unique(candidate["evidence"], [backfill_evidence])
            rows_out.append({**candidate, "source_url": source_url, "action": "would_update" if dry_run else "updated"})
            if dry_run:
                continue
            conn.execute(
                """
                UPDATE label_candidates
                SET source_url = ?, source_key = ?, evidence_json = ?, last_seen_at = ?
                WHERE id = ?
                """,
                (
                    source_url,
                    new_key,
                    json.dumps(merged_evidence, ensure_ascii=False, sort_keys=True),
                    _utc_now(),
                    candidate_id,
                ),
            )
            rows_updated += 1
        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "dry_run": dry_run,
        "source": source,
        "rows_reviewed": len(rows_out),
        "rows_updated": rows_updated,
        "conflicts_skipped": conflicts_skipped,
        "rows": rows_out,
        "source_policy": (
            "candidate source_url backfill only; no trusted labels are changed "
            "and no candidates are promoted"
        ),
    }


def acquire_priority_label_source_snapshots(
    limit: int = 3,
    min_trusted_per_entity: int = 100,
    timeout_ms: int = 30000,
    max_xhr: int = 60,
    fresh_for: int = 0,
    *,
    snapshot_service: Any | None = None,
) -> dict[str, Any]:
    """Acquire missing priority entity source snapshots and stage candidates only."""
    safe_limit = max(1, min(int(limit or 3), 10))
    plan = get_label_acquisition_plan(limit=50, min_trusted_per_entity=min_trusted_per_entity)
    actionable = [
        row for row in plan.get("rows", [])
        if row.get("recommended_action") in {
            "acquire_new_source_snapshots",
            "collect_more_evidence_for_candidates",
        }
    ][:safe_limit]

    if snapshot_service is None:
        from services.scrapling_probe import get_scrapling_probe_service

        snapshot_service = get_scrapling_probe_service()

    acquired: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    target_stems: list[str] = []
    for row in actionable:
        entity = str(row.get("entity") or "").strip()
        slug = _entity_source_slug(entity)
        if not entity or slug == "unknown":
            continue
        try:
            snapshot = snapshot_service.get_entity_snapshot(
                slug,
                timeout_ms=timeout_ms,
                max_xhr=max_xhr,
                fresh_for=fresh_for,
                persist=True,
            )
            target_stems.append(f"entity_{slug}")
            acquired.append(
                {
                    "entity": entity,
                    "slug": slug,
                    "recommended_action": row.get("recommended_action"),
                    "final_url": snapshot.get("final_url") or snapshot.get("url"),
                    "wallets": len(snapshot.get("wallets") or []),
                    "transfers": len(snapshot.get("transfers") or []),
                    "counterparties": len(snapshot.get("counterparties") or []),
                    "artifact_path": snapshot.get("artifact_path"),
                }
            )
        except Exception as exc:
            failed.append(
                {
                    "entity": entity,
                    "slug": slug,
                    "recommended_action": row.get("recommended_action"),
                    "error": str(exc)[:500],
                }
            )

    staging = stage_label_candidates_from_normalized_sources(target_stems=target_stems) if target_stems else {
        "ok": True,
        "files_scanned": 0,
        "rows_observed": 0,
        "candidates_inserted": 0,
        "candidates_merged": 0,
        "summary": get_label_ledger_summary(),
        "source_policy": "no snapshots acquired; trusted labels unchanged",
    }

    return {
        "ok": True,
        "requested": safe_limit,
        "attempted": len(actionable),
        "acquired": acquired,
        "failed": failed,
        "candidate_staging": staging,
        "source_policy": (
            "Scrapling acquisition creates/refreshes source snapshots and stages label candidates only. "
            "Trusted labels still require strict dry-run review and explicit promotion."
        ),
    }


def get_label_ledger_summary() -> dict[str, Any]:
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        total = conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]
        derived_total = conn.execute("SELECT COUNT(*) FROM derived_labels").fetchone()[0]
        by_chain = [
            {"chain": row[0], "labels": row[1]}
            for row in conn.execute("SELECT chain, COUNT(*) FROM labels GROUP BY chain ORDER BY COUNT(*) DESC").fetchall()
        ]
        derived_by_chain = [
            {"chain": row[0], "labels": row[1]}
            for row in conn.execute("SELECT chain, COUNT(*) FROM derived_labels GROUP BY chain ORDER BY COUNT(*) DESC").fetchall()
        ]
        by_entity = [
            {"entity": row[0] or "unknown", "labels": row[1]}
            for row in conn.execute(
                "SELECT entity, COUNT(*) FROM labels GROUP BY entity ORDER BY COUNT(*) DESC LIMIT 20"
            ).fetchall()
        ]
        high_confidence = conn.execute("SELECT COUNT(*) FROM labels WHERE confidence = 'high'").fetchone()[0]
        candidates = conn.execute("SELECT COUNT(*) FROM label_candidates").fetchone()[0]
        open_candidates = conn.execute("SELECT COUNT(*) FROM label_candidates WHERE status = 'candidate'").fetchone()[0]
        source_audit = _trusted_label_source_audit(conn)
        return {
            "ok": True,
            "db_path": str(DB_PATH),
            "labels": total,
            "derived_labels": derived_total,
            "label_candidates": candidates,
            "open_label_candidates": open_candidates,
            "high_confidence": high_confidence,
            "chains": by_chain,
            "derived_chains": derived_by_chain,
            "top_entities": by_entity,
            "trusted_source_audit": source_audit,
        }
    finally:
        conn.close()


def get_label_candidates(limit: int = 50, entity: str | None = None, chain: str | None = None) -> dict[str, Any]:
    _init_db()
    where = ["status = 'candidate'"]
    params: list[Any] = []
    if entity:
        where.append("LOWER(proposed_entity) LIKE ?")
        params.append(f"%{entity.lower()}%")
    if chain:
        where.append("chain = ?")
        params.append(_chain_key(chain))
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            f"""
            SELECT chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, first_seen_at, last_seen_at, seen_count
            FROM label_candidates
            WHERE {' AND '.join(where)}
            ORDER BY seen_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            [*params, max(1, min(int(limit or 50), 200))],
        ).fetchall()
    finally:
        conn.close()
    return {
        "ok": True,
        "source_policy": "candidate rows are audit-only and are not trusted labels until promoted by explicit verified rules",
        "rows": [
            {
                "chain": row[0],
                "address": row[1],
                "label": row[2],
                "entity": row[3],
                "wallet_type": row[4],
                "confidence": row[5],
                "source": row[6],
                "source_url": row[7],
                "evidence": _json_list(row[8]),
                "first_seen_at": row[9],
                "last_seen_at": row[10],
                "seen_count": row[11],
            }
            for row in rows
        ],
    }


def get_label_candidate_audit() -> dict[str, Any]:
    """Read-only quality metrics for candidate labels before any promotion policy exists."""
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        totals = conn.execute(
            """
            SELECT
                COUNT(*),
                SUM(CASE WHEN source_url IS NULL OR source_url = '' THEN 1 ELSE 0 END),
                SUM(CASE WHEN seen_count >= 5 THEN 1 ELSE 0 END),
                SUM(CASE WHEN json_array_length(evidence_json) >= 2 THEN 1 ELSE 0 END),
                SUM(CASE WHEN proposed_entity IS NULL OR proposed_entity = '' THEN 1 ELSE 0 END)
            FROM label_candidates
            WHERE status = 'candidate'
            """
        ).fetchone()
        by_source = [
            {
                "source": row[0],
                "candidates": row[1],
                "missing_source_url": row[2],
                "avg_seen_count": round(float(row[3] or 0), 2),
            }
            for row in conn.execute(
                """
                SELECT source,
                       COUNT(*),
                       SUM(CASE WHEN source_url IS NULL OR source_url = '' THEN 1 ELSE 0 END),
                       AVG(seen_count)
                FROM label_candidates
                WHERE status = 'candidate'
                GROUP BY source
                ORDER BY COUNT(*) DESC
                LIMIT 15
                """
            ).fetchall()
        ]
        promotion_ready = [
            {
                "chain": row[0],
                "address": row[1],
                "label": row[2],
                "entity": row[3],
                "source": row[4],
                "seen_count": row[5],
                "evidence_count": row[6],
                "promotion": _promotion_grade(
                    {
                        "chain": row[0],
                        "address": row[1],
                        "label": row[2],
                        "entity": row[3],
                        "source": row[4],
                        "source_url": row[7],
                        "seen_count": row[5],
                        "evidence": _json_list(row[8]),
                    }
                ),
            }
            for row in conn.execute(
                """
                SELECT chain, address, proposed_label, proposed_entity, source, seen_count,
                       json_array_length(evidence_json) AS evidence_count, source_url, evidence_json
                FROM label_candidates
                WHERE status = 'candidate'
                  AND proposed_entity IS NOT NULL AND proposed_entity != ''
                  AND source_url IS NOT NULL AND source_url != ''
                  AND seen_count >= 2
                ORDER BY seen_count DESC, evidence_count DESC
                LIMIT 25
                """
            ).fetchall()
        ]
    finally:
        conn.close()

    total = int(totals[0] or 0)
    missing_url = int(totals[1] or 0)
    repeated = int(totals[2] or 0)
    rich_evidence = int(totals[3] or 0)
    missing_entity = int(totals[4] or 0)
    return {
        "ok": True,
        "source_policy": "read-only audit; no candidate is promoted by this endpoint",
        "total_candidates": total,
        "missing_source_url": missing_url,
        "missing_source_url_pct": round((missing_url / total) * 100, 2) if total else 0,
        "repeated_candidates": repeated,
        "rich_evidence_candidates": rich_evidence,
        "missing_entity": missing_entity,
        "by_source": by_source,
        "promotion_review_queue": promotion_ready,
        "recommendation": "Review promotion_review_queue manually or with explicit verified rules before any trusted-label promotion.",
    }


def get_label_candidate_quality_report(limit: int = 50) -> dict[str, Any]:
    """Read-only candidate quality report for dedupe/freshness before promotion."""
    _init_db()
    limit = max(1, min(int(limit or 50), 200))
    conn = sqlite3.connect(str(DB_PATH))
    try:
        duplicate_groups = [
            {
                "chain": row[0],
                "address": row[1],
                "entity": row[2] or "unknown",
                "label": row[3] or "",
                "source_url": row[4] or "",
                "rows": int(row[5] or 0),
                "total_seen": int(row[6] or 0),
                "candidate_ids": [int(item) for item in str(row[7] or "").split(",") if item],
            }
            for row in conn.execute(
                """
                SELECT chain, address, proposed_entity, proposed_label, COALESCE(source_url, ''),
                       COUNT(*) AS row_count,
                       SUM(seen_count) AS total_seen,
                       GROUP_CONCAT(id) AS candidate_ids
                FROM label_candidates
                WHERE status = 'candidate'
                GROUP BY chain, address, proposed_entity, proposed_label, COALESCE(source_url, '')
                HAVING row_count > 1
                ORDER BY row_count DESC, total_seen DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
        ambiguous_addresses = [
            {
                "chain": row[0],
                "address": row[1],
                "entities": int(row[2] or 0),
                "labels": int(row[3] or 0),
                "rows": int(row[4] or 0),
                "candidate_ids": [int(item) for item in str(row[5] or "").split(",") if item],
            }
            for row in conn.execute(
                """
                SELECT chain, address,
                       COUNT(DISTINCT COALESCE(proposed_entity, '')) AS entity_count,
                       COUNT(DISTINCT COALESCE(proposed_label, '')) AS label_count,
                       COUNT(*) AS row_count,
                       GROUP_CONCAT(id) AS candidate_ids
                FROM label_candidates
                WHERE status = 'candidate'
                GROUP BY chain, address
                HAVING entity_count > 1 OR label_count > 2
                ORDER BY entity_count DESC, label_count DESC, row_count DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
        stale_candidates = [
            {
                "id": row[0],
                "chain": row[1],
                "address": row[2],
                "label": row[3],
                "entity": row[4],
                "source": row[5],
                "source_url": row[6],
                "first_seen_at": row[7],
                "last_seen_at": row[8],
                "seen_count": row[9],
            }
            for row in conn.execute(
                """
                SELECT id, chain, address, proposed_label, proposed_entity, source, source_url,
                       first_seen_at, last_seen_at, seen_count
                FROM label_candidates
                WHERE status = 'candidate'
                  AND seen_count = 1
                ORDER BY last_seen_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        ]
        totals = conn.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN status = 'candidate' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status = 'promoted' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN source_url IS NULL OR source_url = '' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN seen_count = 1 THEN 1 ELSE 0 END)
            FROM label_candidates
            """
        ).fetchone()
        duplicate_total = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM label_candidates
                WHERE status = 'candidate'
                GROUP BY chain, address, proposed_entity, proposed_label, COALESCE(source_url, '')
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()[0]
        ambiguous_total = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT 1
                FROM label_candidates
                WHERE status = 'candidate'
                GROUP BY chain, address
                HAVING COUNT(DISTINCT COALESCE(proposed_entity, '')) > 1
                    OR COUNT(DISTINCT COALESCE(proposed_label, '')) > 2
            )
            """
        ).fetchone()[0]
    finally:
        conn.close()

    open_total = int(totals[1] or 0)
    single_seen = int(totals[4] or 0)
    return {
        "ok": True,
        "source_policy": "read-only quality report; no dedupe, promotion, or trusted-label writes are performed",
        "totals": {
            "all_candidates": int(totals[0] or 0),
            "open_candidates": open_total,
            "promoted_candidates": int(totals[2] or 0),
            "missing_source_url": int(totals[3] or 0),
            "single_seen_candidates": single_seen,
        },
        "risk_summary": {
            "duplicate_groups": int(duplicate_total or 0),
            "ambiguous_addresses": int(ambiguous_total or 0),
            "stale_single_seen_sample": len(stale_candidates),
            "single_seen_pct": round((single_seen / open_total) * 100, 2) if open_total else 0,
        },
        "duplicate_groups": duplicate_groups,
        "ambiguous_addresses": ambiguous_addresses,
        "stale_candidates": stale_candidates,
        "recommendation": "Resolve ambiguous addresses and review stale single-seen candidates before enabling any automatic promotion lane.",
    }


def consolidate_label_candidate_duplicates(limit: int = 50, dry_run: bool = True) -> dict[str, Any]:
    """Merge exact duplicate candidate groups into one candidate row; defaults to dry-run."""
    _init_db()
    limit = max(1, min(int(limit or 50), 200))
    conn = sqlite3.connect(str(DB_PATH))
    actions: list[dict[str, Any]] = []
    groups_processed = 0
    rows_removed = 0
    rows_would_remove = 0
    evidence_reassigned = 0
    evidence_merged = 0
    try:
        groups = conn.execute(
            """
            SELECT chain, address, proposed_entity, proposed_label, COALESCE(source_url, ''),
                   GROUP_CONCAT(id) AS candidate_ids
            FROM label_candidates
            WHERE status = 'candidate'
            GROUP BY chain, address, proposed_entity, proposed_label, COALESCE(source_url, '')
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, SUM(seen_count) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        for group in groups:
            chain, address, entity, label, source_url, ids_text = group
            ids = [int(item) for item in str(ids_text or "").split(",") if item]
            if len(ids) < 2:
                continue
            placeholders = ",".join("?" for _ in ids)
            rows = conn.execute(
                f"""
                SELECT id, evidence_json, seen_count, first_seen_at, last_seen_at, source, source_key
                FROM label_candidates
                WHERE id IN ({placeholders})
                ORDER BY seen_count DESC, last_seen_at DESC, id ASC
                """,
                ids,
            ).fetchall()
            if len(rows) < 2:
                continue

            keeper = rows[0]
            keeper_id = int(keeper[0])
            duplicate_ids = [int(row[0]) for row in rows[1:]]
            rows_would_remove += len(duplicate_ids)
            merged_evidence: list[Any] = []
            total_seen = 0
            first_seen_values: list[str] = []
            last_seen_values: list[str] = []
            sources = []
            source_keys = []
            for row in rows:
                merged_evidence = _merge_unique(merged_evidence, _json_list(row[1]))
                total_seen += int(row[2] or 0)
                if row[3]:
                    first_seen_values.append(str(row[3]))
                if row[4]:
                    last_seen_values.append(str(row[4]))
                if row[5]:
                    sources.append(str(row[5]))
                if row[6]:
                    source_keys.append(str(row[6]))

            action = {
                "chain": chain,
                "address": address,
                "entity": entity,
                "label": label,
                "source_url": source_url,
                "keeper_id": keeper_id,
                "duplicate_ids": duplicate_ids,
                "rows_before": len(rows),
                "merged_seen_count": total_seen,
                "merged_evidence_count": len(merged_evidence),
                "sources": sorted(set(sources)),
                "source_keys": sorted(set(source_keys))[:8],
                "action": "would_merge" if dry_run else "merged",
            }
            actions.append(action)
            groups_processed += 1

            if not dry_run:
                conn.execute(
                    """
                    UPDATE label_candidates
                    SET evidence_json = ?, seen_count = ?, first_seen_at = ?, last_seen_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(merged_evidence, ensure_ascii=False),
                        total_seen,
                        min(first_seen_values) if first_seen_values else keeper[3],
                        max(last_seen_values) if last_seen_values else keeper[4],
                        keeper_id,
                    ),
                )
                duplicate_placeholders = ",".join("?" for _ in duplicate_ids)
                evidence_rows = conn.execute(
                    f"""
                    SELECT id, source_key, status, score, evidence_json, blockers_json, observed_at
                    FROM label_candidate_evidence
                    WHERE candidate_id IN ({duplicate_placeholders})
                    """,
                    duplicate_ids,
                ).fetchall()
                for evidence_row in evidence_rows:
                    evidence_id, evidence_source_key, status, score, evidence_json, blockers_json, observed_at = evidence_row
                    existing = conn.execute(
                        """
                        SELECT id, status, score, evidence_json, blockers_json, observed_at
                        FROM label_candidate_evidence
                        WHERE candidate_id = ? AND source_key = ?
                        """,
                        (keeper_id, evidence_source_key),
                    ).fetchone()
                    if existing:
                        existing_id, existing_status, existing_score, existing_evidence, existing_blockers, existing_observed = existing
                        incoming_score = int(score or 0)
                        current_score = int(existing_score or 0)
                        conn.execute(
                            """
                            UPDATE label_candidate_evidence
                            SET status = ?, score = ?, evidence_json = ?, blockers_json = ?, observed_at = ?
                            WHERE id = ?
                            """,
                            (
                                status if incoming_score >= current_score else existing_status,
                                max(current_score, incoming_score),
                                json.dumps(
                                    _merge_unique(_json_list(existing_evidence), _json_list(evidence_json)),
                                    ensure_ascii=False,
                                    sort_keys=True,
                                ),
                                json.dumps(
                                    _merge_unique(_json_list(existing_blockers), _json_list(blockers_json)),
                                    ensure_ascii=False,
                                    sort_keys=True,
                                ),
                                max(str(existing_observed or ""), str(observed_at or "")),
                                existing_id,
                            ),
                        )
                        conn.execute("DELETE FROM label_candidate_evidence WHERE id = ?", (evidence_id,))
                        evidence_merged += 1
                    else:
                        conn.execute(
                            "UPDATE label_candidate_evidence SET candidate_id = ? WHERE id = ?",
                            (keeper_id, evidence_id),
                        )
                        evidence_reassigned += 1
                delete_placeholders = ",".join("?" for _ in duplicate_ids)
                conn.execute(
                    f"UPDATE label_candidates SET status = 'merged_duplicate' WHERE id IN ({delete_placeholders})",
                    duplicate_ids,
                )
                rows_removed += len(duplicate_ids)
        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    return {
        "ok": True,
        "dry_run": dry_run,
        "groups_reviewed": groups_processed,
        "rows_removed": rows_removed,
        "rows_would_remove": rows_would_remove,
        "evidence_reassigned": evidence_reassigned,
        "evidence_merged": evidence_merged,
        "actions": actions,
        "source_policy": (
            "exact duplicate candidate consolidation retires duplicate candidates instead of deleting them, "
            "so future source ingestion cannot recreate the same source_key rows; no trusted labels are promoted or changed"
        ),
    }


def review_label_candidate_promotions(limit: int = 25, min_score: int = 70) -> dict[str, Any]:
    """Return candidate promotion decisions without mutating trusted labels."""
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            """
            SELECT id, chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, seen_count
            FROM label_candidates
            WHERE status = 'candidate'
            ORDER BY seen_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 25), 200)),),
        ).fetchall()
    finally:
        conn.close()

    decisions = []
    eligible = 0
    for row in rows:
        candidate = {
            "id": row[0],
            "chain": row[1],
            "address": row[2],
            "label": row[3],
            "entity": row[4],
            "wallet_type": row[5],
            "confidence": row[6],
            "source": row[7],
            "source_url": row[8],
            "evidence": _json_list(row[9]),
            "seen_count": row[10],
        }
        grade = _promotion_grade(candidate)
        decision = "promote_ready" if grade["eligible"] and grade["score"] >= min_score else "hold"
        if decision == "promote_ready":
            eligible += 1
        decisions.append({**candidate, "promotion": grade, "decision": decision})

    return {
        "ok": True,
        "source_policy": "dry-run review only; no trusted labels are changed",
        "min_score": min_score,
        "rows_reviewed": len(decisions),
        "eligible": eligible,
        "rows": decisions,
    }


def review_strict_label_candidate_promotions(limit: int = 50) -> dict[str, Any]:
    """Stricter read-only review before any candidate can become a trusted label."""
    _init_db()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            """
            SELECT id, chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, seen_count
            FROM label_candidates
            WHERE status = 'candidate'
            ORDER BY seen_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit or 50), 200)),),
        ).fetchall()
        candidates = [
            {
                "id": row[0],
                "chain": row[1],
                "address": row[2],
                "label": row[3],
                "entity": row[4],
                "wallet_type": row[5],
                "confidence": row[6],
                "source": row[7],
                "source_url": row[8],
                "evidence": _json_list(row[9]),
                "seen_count": row[10],
            }
            for row in rows
        ]
        evidence_scores = _candidate_evidence_score_map(conn, candidates)
    finally:
        conn.close()

    rows_out = []
    strict_ready = 0
    blocked_by_reason: dict[str, int] = {}
    for candidate in candidates:
        scored = evidence_scores.get(int(candidate["id"]))
        candidate_for_grade = _candidate_with_persisted_evidence(candidate, scored)
        grade = _apply_persisted_evidence_gate(_strict_promotion_grade(candidate_for_grade), candidate_for_grade)
        if grade["strict_ready"]:
            strict_ready += 1
        for blocker in grade.get("blockers") or []:
            blocked_by_reason[blocker] = blocked_by_reason.get(blocker, 0) + 1
        rows_out.append({
            **candidate_for_grade,
            "strict_promotion": grade,
            "decision": "strict_ready" if grade["strict_ready"] else "blocked",
        })

    return {
        "ok": True,
        "source_policy": "strict read-only review; no trusted labels are changed",
        "rows_reviewed": len(rows_out),
        "strict_ready": strict_ready,
        "blocked": len(rows_out) - strict_ready,
        "blocked_by_reason": [
            {"reason": reason, "count": count}
            for reason, count in sorted(blocked_by_reason.items(), key=lambda item: item[1], reverse=True)
        ],
        "rows": rows_out,
        "recommendation": "Promote only strict_ready candidates, and still prefer dry-run before any real promotion.",
    }


def plan_label_candidate_automation(limit: int = 100) -> dict[str, Any]:
    """Classify candidates for future automation without mutating trusted labels."""
    review = review_label_candidate_promotions(limit=limit, min_score=70)
    evm_auto_chains = {"ethereum", "bsc", "polygon", "base", "arbitrum"}
    auto_safe: list[dict[str, Any]] = []
    admin_review: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for row in review["rows"]:
        promotion = row["promotion"]
        source_url = str(row.get("source_url") or "")
        source = str(row.get("source") or "")
        chain = str(row.get("chain") or "")
        seen_count = int(row.get("seen_count") or 0)
        automation_blockers = list(promotion.get("blockers") or [])

        if chain not in evm_auto_chains:
            automation_blockers.append("automation_evm_only_for_now")
        if source == "scrapling_profile_tag":
            automation_blockers.append("profile_tag_requires_review")
        if not source_url.startswith("https://intel.arkm.com/explorer/"):
            automation_blockers.append("non_arkham_source_requires_review")
        if seen_count < 5:
            automation_blockers.append("insufficient_repeated_observations")
        if promotion.get("score", 0) < 90:
            automation_blockers.append("score_below_auto_safe_threshold")

        enriched = {
            **row,
            "automation_blockers": automation_blockers,
            "automation_policy": "future-auto-safe requires EVM chain, Arkham URL, repeated observations, no signer/profile-tag blockers",
        }
        if promotion.get("eligible") and promotion.get("score", 0) >= 90 and not automation_blockers:
            enriched["automation_decision"] = "auto_safe_later"
            auto_safe.append(enriched)
        elif promotion.get("eligible") and promotion.get("score", 0) >= 70:
            enriched["automation_decision"] = "admin_review"
            admin_review.append(enriched)
        else:
            enriched["automation_decision"] = "blocked"
            blocked.append(enriched)

    return {
        "ok": True,
        "source_policy": "planning only; no labels are promoted and no RPC enrichment is started",
        "rows_reviewed": review["rows_reviewed"],
        "auto_safe_later": len(auto_safe),
        "admin_review": len(admin_review),
        "blocked": len(blocked),
        "lanes": {
            "auto_safe_later": auto_safe,
            "admin_review": admin_review,
            "blocked": blocked[:25],
        },
    }


def corroborate_label_candidates(
    limit: int = 25,
    entity: str | None = None,
    chain: str | None = None,
    timeout: int = 12,
    persist: bool = True,
    candidate_ids: list[int] | None = None,
) -> dict[str, Any]:
    """External-source corroboration for candidate labels.

    Persistence writes evidence bundles only; trusted labels are never changed.
    """
    _init_db()
    where = ["status = 'candidate'"]
    params: list[Any] = []
    clean_ids = sorted({int(value) for value in (candidate_ids or []) if int(value) > 0})
    if clean_ids:
        placeholders = ",".join("?" for _ in clean_ids)
        where.append(f"id IN ({placeholders})")
        params.extend(clean_ids)
    if entity:
        where.append("LOWER(proposed_entity) LIKE ?")
        params.append(f"%{entity.lower()}%")
    if chain:
        where.append("chain = ?")
        params.append(_chain_key(chain))
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            f"""
            SELECT id, chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, seen_count
            FROM label_candidates
            WHERE {' AND '.join(where)}
            ORDER BY seen_count DESC, last_seen_at DESC
            LIMIT ?
            """,
            [*params, max(1, min(int(limit or 25), 50))],
        ).fetchall()
    finally:
        conn.close()

    reviewed = []
    ready = 0
    evidence_written = 0
    blocked_by_reason: dict[str, int] = {}
    for row in rows:
        candidate = {
            "id": row[0],
            "chain": row[1],
            "address": row[2],
            "label": row[3],
            "entity": row[4],
            "wallet_type": row[5],
            "confidence": row[6],
            "source": row[7],
            "source_url": row[8],
            "evidence": _json_list(row[9]),
            "seen_count": row[10],
        }
        enriched = _corroborate_candidate(candidate, timeout=max(2, min(int(timeout or 12), 20)))
        if enriched["corroboration"]["status"] == "verified_source_ready":
            ready += 1
        for blocker in enriched["corroboration"].get("blockers") or []:
            blocked_by_reason[blocker] = blocked_by_reason.get(blocker, 0) + 1
        reviewed.append(enriched)

    if persist and reviewed:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            for row in reviewed:
                if _store_candidate_evidence(conn, row):
                    evidence_written += 1
            conn.commit()
        finally:
            conn.close()

    return {
        "ok": True,
        "source_policy": "external corroboration may persist evidence bundles; no candidates are promoted and no trusted labels are changed",
        "persist": persist,
        "rows_reviewed": len(reviewed),
        "evidence_bundles_written": evidence_written,
        "verified_source_ready": ready,
        "needs_more_evidence": len(reviewed) - ready,
        "blocked_by_reason": [
            {"reason": reason, "count": count}
            for reason, count in sorted(blocked_by_reason.items(), key=lambda item: item[1], reverse=True)
        ],
        "rows": reviewed,
    }


def get_label_candidate_evidence(candidate_id: int | None = None, limit: int = 50) -> dict[str, Any]:
    """Read persisted evidence bundles for label candidates."""
    _init_db()
    where: list[str] = []
    params: list[Any] = []
    if candidate_id:
        where.append("candidate_id = ?")
        params.append(int(candidate_id))
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            f"""
            SELECT candidate_id, chain, address, source, status, score,
                   evidence_json, blockers_json, observed_at
            FROM label_candidate_evidence
            {where_sql}
            ORDER BY observed_at DESC, id DESC
            LIMIT ?
            """,
            [*params, max(1, min(int(limit or 50), 200))],
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM label_candidate_evidence").fetchone()[0]
    finally:
        conn.close()
    return {
        "ok": True,
        "candidate_id": candidate_id,
        "total_evidence_bundles": total,
        "source_policy": "read-only evidence bundle view; trusted labels are unchanged",
        "rows": [
            {
                "candidate_id": row[0],
                "chain": row[1],
                "address": row[2],
                "source": row[3],
                "status": row[4],
                "score": row[5],
                "evidence": _json_list(row[6]),
                "blockers": _json_list(row[7]),
                "observed_at": row[8],
            }
            for row in rows
        ],
    }


def _score_evidence_history(candidate: dict[str, Any], bundles: list[dict[str, Any]]) -> dict[str, Any]:
    unique_sources: set[str] = set()
    blockers: dict[str, int] = {}
    evidence_from_bundles: list[Any] = []
    evidence_items = 0
    max_bundle_score = 0
    score_sum = 0

    for bundle in bundles:
        bundle_score = int(bundle.get("score") or 0)
        max_bundle_score = max(max_bundle_score, bundle_score)
        score_sum += bundle_score
        evidence = bundle.get("evidence") if isinstance(bundle.get("evidence"), list) else []
        evidence_items += len(evidence)
        evidence_from_bundles = _merge_unique(evidence_from_bundles, evidence)
        for item in evidence:
            if isinstance(item, dict):
                unique_sources.add(str(item.get("source") or "unknown"))
        for blocker in bundle.get("blockers") or []:
            blocker_key = str(blocker)
            blockers[blocker_key] = blockers.get(blocker_key, 0) + 1

    blocker_keys = set(blockers)
    severe_blockers = {
        "invalid_chain_address_format",
        "signer_candidate_requires_manual_review",
        "strict_protocol_requires_manual_review",
    }
    if "blockscout_address" not in unique_sources and "explorer_html_title" not in unique_sources:
        severe_blockers.update(
            {
                "strict_blocks_scrapling_only_evidence",
                "strict_requires_verified_or_external_source",
            }
        )
    severe = sorted(blocker_keys & severe_blockers)
    source_bonus = min(15, max(0, len(unique_sources) - 1) * 5)
    history_bonus = min(10, max(0, len(bundles) - 1) * 2)
    blocker_penalty = min(30, len(severe) * 8 + max(0, len(blocker_keys) - len(severe)) * 2)
    historical_score = max(0, min(100, max_bundle_score + source_bonus + history_bonus - blocker_penalty))

    if severe:
        decision = "manual_review_required"
    elif historical_score >= 80 and len(unique_sources) >= 2:
        decision = "strict_review_candidate"
    elif historical_score >= 50:
        decision = "collect_more_evidence"
    else:
        decision = "hold"

    avg_score = round(score_sum / max(len(bundles), 1), 2)
    return {
        **candidate,
        "historical_evidence_score": historical_score,
        "max_bundle_score": max_bundle_score,
        "avg_bundle_score": avg_score,
        "evidence_bundles": len(bundles),
        "evidence_items": evidence_items,
        "evidence_from_bundles": evidence_from_bundles[:25],
        "unique_sources": sorted(unique_sources),
        "blockers": [
            {"reason": reason, "count": count}
            for reason, count in sorted(blockers.items(), key=lambda item: item[1], reverse=True)
        ],
        "severe_blockers": severe,
        "decision": decision,
    }


PUBLIC_CORROBORATION_SOURCES = {"blockscout_address", "explorer_html_title", "etherscan_label"}


def _is_verified_review_ready(scored_candidate: dict[str, Any]) -> bool:
    sources = set(scored_candidate.get("unique_sources") or [])
    return (
        str(scored_candidate.get("decision") or "") == "strict_review_candidate"
        and bool(sources & PUBLIC_CORROBORATION_SOURCES)
        and not scored_candidate.get("severe_blockers")
    )


def _candidate_evidence_score_map(
    conn: sqlite3.Connection,
    candidates: list[dict[str, Any]],
    max_depth: int = 10,
) -> dict[int, dict[str, Any]]:
    candidate_by_id = {int(row.get("id") or 0): row for row in candidates if int(row.get("id") or 0) > 0}
    if not candidate_by_id:
        return {}
    placeholders = ",".join("?" for _ in candidate_by_id)
    grouped: dict[int, list[dict[str, Any]]] = {candidate_id: [] for candidate_id in candidate_by_id}
    rows = conn.execute(
        f"""
        SELECT candidate_id, status, score, evidence_json, blockers_json, observed_at
        FROM label_candidate_evidence
        WHERE candidate_id IN ({placeholders})
        ORDER BY candidate_id, observed_at DESC, id DESC
        """,
        list(candidate_by_id),
    ).fetchall()
    depth = max(1, min(int(max_depth or 10), 50))
    for row in rows:
        candidate_id = int(row[0] or 0)
        if candidate_id not in grouped or len(grouped[candidate_id]) >= depth:
            continue
        grouped[candidate_id].append(
            {
                "status": row[1],
                "score": int(row[2] or 0),
                "evidence": _json_list(row[3]),
                "blockers": _json_list(row[4]),
                "observed_at": row[5],
            }
        )
    return {
        candidate_id: _score_evidence_history(candidate_by_id[candidate_id], bundles)
        for candidate_id, bundles in grouped.items()
    }


def _candidate_with_persisted_evidence(
    candidate: dict[str, Any],
    scored_candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    if not scored_candidate:
        return candidate
    evidence_bundles = int(scored_candidate.get("evidence_bundles") or 0)
    evidence_score = int(scored_candidate.get("historical_evidence_score") or 0)
    evidence_decision = str(scored_candidate.get("decision") or "")
    evidence_ready = _is_verified_review_ready(scored_candidate)
    return {
        **candidate,
        "evidence": _merge_unique(
            _json_list(candidate.get("evidence")),
            _json_list(scored_candidate.get("evidence_from_bundles")),
        ),
        "persisted_evidence_bundles": evidence_bundles,
        "persisted_evidence_score": evidence_score,
        "persisted_evidence_decision": evidence_decision,
        "persisted_evidence_ready": evidence_ready,
        "persisted_evidence_sources": scored_candidate.get("unique_sources", []),
    }


def _apply_persisted_evidence_gate(
    grade: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed when persisted evidence exists but is not review-ready."""
    evidence_bundles = int(candidate.get("persisted_evidence_bundles") or 0)
    if evidence_bundles <= 0:
        return grade
    if candidate.get("persisted_evidence_ready"):
        return {
            **grade,
            "reasons": list(dict.fromkeys([*(grade.get("reasons") or []), "persisted_evidence_review_ready"])),
        }

    blockers = list(grade.get("blockers") or [])
    blockers.append("persisted_evidence_not_review_ready")
    reasons = list(grade.get("reasons") or [])
    reasons.append(f"persisted_evidence_score_{int(candidate.get('persisted_evidence_score') or 0)}")
    blockers = list(dict.fromkeys(blockers))
    reasons = list(dict.fromkeys(reasons))
    return {
        **grade,
        "strict_ready": False,
        "eligible": False,
        "confidence": "low",
        "reasons": reasons,
        "blockers": blockers,
    }


def get_label_candidate_evidence_scores(
    limit: int = 50,
    entity: str | None = None,
    chain: str | None = None,
    max_bundles_per_candidate: int = 10,
) -> dict[str, Any]:
    """Aggregate persisted evidence bundles into an audit-only candidate score."""
    _init_db()
    limit = max(1, min(int(limit or 50), 200))
    max_depth = max(1, min(int(max_bundles_per_candidate or 10), 50))
    where = ["c.status = 'candidate'"]
    params: list[Any] = []
    if entity:
        where.append("LOWER(c.proposed_entity) LIKE ?")
        params.append(f"%{entity.lower()}%")
    if chain:
        where.append("c.chain = ?")
        params.append(_chain_key(chain))

    conn = sqlite3.connect(str(DB_PATH))
    try:
        candidates = conn.execute(
            f"""
            SELECT c.id, c.chain, c.address, c.proposed_label, c.proposed_entity,
                   c.proposed_wallet_type, c.confidence, c.source, c.source_url, c.seen_count
            FROM label_candidates c
            WHERE {' AND '.join(where)}
              AND EXISTS (
                  SELECT 1 FROM label_candidate_evidence e WHERE e.candidate_id = c.id
              )
            ORDER BY c.seen_count DESC, c.last_seen_at DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()

        rows: list[dict[str, Any]] = []
        for candidate_row in candidates:
            candidate_id = int(candidate_row[0])
            bundle_rows = conn.execute(
                """
                SELECT status, score, evidence_json, blockers_json, observed_at
                FROM label_candidate_evidence
                WHERE candidate_id = ?
                ORDER BY observed_at DESC, id DESC
                LIMIT ?
                """,
                (candidate_id, max_depth),
            ).fetchall()
            bundles = [
                {
                    "status": row[0],
                    "score": int(row[1] or 0),
                    "evidence": _json_list(row[2]),
                    "blockers": _json_list(row[3]),
                    "observed_at": row[4],
                }
                for row in bundle_rows
            ]
            candidate = {
                "id": candidate_id,
                "chain": candidate_row[1],
                "address": candidate_row[2],
                "label": candidate_row[3],
                "entity": candidate_row[4],
                "wallet_type": candidate_row[5],
                "confidence": candidate_row[6],
                "source": candidate_row[7],
                "source_url": candidate_row[8],
                "seen_count": int(candidate_row[9] or 0),
            }
            rows.append(_score_evidence_history(candidate, bundles))
    finally:
        conn.close()

    rows.sort(
        key=lambda item: (
            item.get("decision") == "strict_review_candidate",
            item.get("historical_evidence_score", 0),
            item.get("evidence_bundles", 0),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "source_policy": "read-only historical evidence scoring; no candidates are promoted and no trusted labels are changed",
        "limit": limit,
        "max_bundles_per_candidate": max_depth,
        "rows_reviewed": len(rows),
        "rows": rows,
        "recommendation": "Use strict_review_candidate rows only as review inputs; severe blockers must be resolved before any promotion.",
    }


def get_verified_label_candidate_review_queue(
    limit: int = 50,
    entity: str | None = None,
    chain: str | None = None,
    max_bundles_per_candidate: int = 10,
) -> dict[str, Any]:
    """Read-only queue of externally corroborated candidates for admin review."""
    scored = get_label_candidate_evidence_scores(
        limit=max(1, min(int(limit or 50), 200)),
        entity=entity,
        chain=chain,
        max_bundles_per_candidate=max_bundles_per_candidate,
    )
    rows = list(scored.get("rows") or [])
    ready: list[dict[str, Any]] = []
    manual_review: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for row in rows:
        sources = set(row.get("unique_sources") or [])
        has_public_source = bool(sources & PUBLIC_CORROBORATION_SOURCES)
        severe_blockers = list(row.get("severe_blockers") or [])
        score = int(row.get("historical_evidence_score") or 0)
        enriched = {
            **row,
            "review_policy": "admin-review-only; use dry-run promotion before any trusted label write",
            "promotion_endpoint": "/api/onchain/labels/candidates/promote",
        }

        if _is_verified_review_ready(row):
            ready.append(enriched)
        elif has_public_source and score >= 60:
            manual_review.append(enriched)
        else:
            blocked.append(enriched)

    return {
        "ok": True,
        "source_policy": (
            "read-only verified candidate queue; no labels are promoted and no trusted label data is changed"
        ),
        "rows_reviewed": scored.get("rows_reviewed", 0),
        "ready_for_admin_review": len(ready),
        "manual_review": len(manual_review),
        "blocked": len(blocked),
        "lanes": {
            "ready_for_admin_review": ready[:limit],
            "manual_review": manual_review[:limit],
            "blocked": blocked[:limit],
        },
        "next_action": (
            "Inspect evidence, then POST candidate IDs to /api/onchain/labels/candidates/promote "
            "with dry_run=true before any real promotion."
        ),
    }


def get_label_candidate_review_dashboard(limit: int = 25) -> dict[str, Any]:
    """Read-only operations dashboard for candidate label review and evidence work."""
    safe_limit = max(1, min(int(limit or 25), 100))
    quality = get_label_candidate_quality_report(limit=safe_limit)
    verified = get_verified_label_candidate_review_queue(limit=safe_limit)
    acquisition = get_label_acquisition_plan(limit=safe_limit)
    corroboration = get_label_corroboration_queue(limit=safe_limit)

    ready_rows = list((verified.get("lanes") or {}).get("ready_for_admin_review") or [])
    queue_rows = list(corroboration.get("rows") or [])
    weak_evidence = [
        row
        for row in queue_rows
        if row.get("recommended_action") == "refresh_weak_evidence"
        or (row.get("max_evidence_score") is not None and int(row.get("max_evidence_score") or 0) < 60)
    ]
    first_pass = [row for row in queue_rows if row.get("recommended_action") == "corroborate_first_pass"]
    duplicate_groups = list(quality.get("duplicate_groups") or [])
    ambiguous_addresses = list(quality.get("ambiguous_addresses") or [])

    if ready_rows:
        next_action = "review_ready_candidates_dry_run"
    elif weak_evidence:
        next_action = "refresh_weak_evidence"
    elif first_pass:
        next_action = "corroborate_first_pass"
    elif duplicate_groups:
        next_action = "dedupe_exact_candidates"
    else:
        next_action = "acquire_new_source_snapshots"

    return {
        "ok": True,
        "source_policy": (
            "read-only review dashboard; no evidence is fetched, no candidates are deduped, "
            "and no trusted labels are promoted"
        ),
        "next_action": next_action,
        "summary": {
            "open_candidates": (quality.get("totals") or {}).get("open_candidates", 0),
            "duplicate_groups": (quality.get("risk_summary") or {}).get("duplicate_groups", 0),
            "ambiguous_addresses": (quality.get("risk_summary") or {}).get("ambiguous_addresses", 0),
            "ready_for_admin_review": verified.get("ready_for_admin_review", 0),
            "weak_evidence_rows": len(weak_evidence),
            "first_pass_rows": len(first_pass),
        },
        "lanes": {
            "ready_for_admin_review": [
                {
                    "id": row.get("id"),
                    "entity": row.get("entity"),
                    "chain": row.get("chain"),
                    "address": row.get("address"),
                    "label": row.get("label"),
                    "score": row.get("historical_evidence_score"),
                    "sources": row.get("unique_sources", []),
                }
                for row in ready_rows[:safe_limit]
            ],
            "weak_evidence_refresh": [
                {
                    "id": row.get("id"),
                    "entity": row.get("entity"),
                    "chain": row.get("chain"),
                    "address": row.get("address"),
                    "label": row.get("label"),
                    "max_evidence_score": row.get("max_evidence_score"),
                    "recommended_action": row.get("recommended_action"),
                    "blockers": row.get("promotion_blockers", []),
                }
                for row in weak_evidence[:safe_limit]
            ],
            "first_pass_corroboration": [
                {
                    "id": row.get("id"),
                    "entity": row.get("entity"),
                    "chain": row.get("chain"),
                    "address": row.get("address"),
                    "label": row.get("label"),
                    "recommended_action": row.get("recommended_action"),
                }
                for row in first_pass[:safe_limit]
            ],
            "duplicate_groups": duplicate_groups[:safe_limit],
            "ambiguous_addresses": ambiguous_addresses[:safe_limit],
            "acquisition_priorities": [
                {
                    "entity": row.get("entity"),
                    "trusted_labels": row.get("trusted_labels"),
                    "open_candidates": row.get("open_candidates"),
                    "strict_ready_candidates": row.get("strict_ready_candidates"),
                    "recommended_action": row.get("recommended_action"),
                    "top_candidate_ids": row.get("top_candidate_ids", []),
                }
                for row in list(acquisition.get("rows") or [])[:safe_limit]
            ],
        },
        "safe_actions": [
            "POST /api/onchain/labels/candidates/promote?dry_run=true for ready IDs only",
            "POST /api/onchain/labels/candidates/corroborate-job for weak/first-pass evidence only",
            "POST /api/onchain/labels/candidates/consolidate-duplicates with dry_run=true before real merge",
        ],
    }


def preview_label_candidate_promotion_impact(
    candidate_ids: list[int],
    min_score: int = 90,
) -> dict[str, Any]:
    """Read-only impact preview for explicit candidate promotion IDs."""
    _init_db()
    min_score = max(90, int(min_score or 90))
    clean_ids = sorted({int(value) for value in candidate_ids if int(value) > 0})
    if not clean_ids:
        return {
            "ok": True,
            "source_policy": "read-only promotion impact preview; no trusted labels are changed",
            "requested": 0,
            "would_promote": 0,
            "would_insert": 0,
            "would_update_existing": 0,
            "blocked": 0,
            "rows": [],
        }

    placeholders = ",".join("?" for _ in clean_ids)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        candidate_rows = conn.execute(
            f"""
            SELECT id, chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, seen_count
            FROM label_candidates
            WHERE id IN ({placeholders}) AND status = 'candidate'
            ORDER BY id ASC
            """,
            clean_ids,
        ).fetchall()
        candidates = [
            {
                "id": row[0],
                "chain": row[1],
                "address": row[2],
                "label": row[3],
                "entity": row[4],
                "wallet_type": row[5],
                "confidence": row[6],
                "source": row[7],
                "source_url": row[8],
                "evidence": _json_list(row[9]),
                "seen_count": row[10],
            }
            for row in candidate_rows
        ]
        evidence_scores = _candidate_evidence_score_map(conn, candidates)
        rows: list[dict[str, Any]] = []
        for candidate in candidates:
            scored = evidence_scores.get(int(candidate["id"]))
            candidate_for_grade = _candidate_with_persisted_evidence(candidate, scored)
            grade = _apply_persisted_evidence_gate(_strict_promotion_grade(candidate_for_grade), candidate_for_grade)
            existing = conn.execute(
                """
                SELECT label, entity, wallet_type, confidence, sources_json, updated_at
                FROM labels
                WHERE chain = ? AND address = ?
                """,
                (_chain_key(candidate["chain"]), str(candidate["address"] or "").lower()),
            ).fetchone()
            if not grade["eligible"] or int(grade.get("score") or 0) < min_score:
                operation = "blocked"
            elif existing:
                operation = "update_existing_label"
            else:
                operation = "insert_new_label"
            current_label = None
            if existing:
                current_label = {
                    "label": existing[0],
                    "entity": existing[1],
                    "wallet_type": existing[2],
                    "confidence": existing[3],
                    "sources": _json_list(existing[4]),
                    "updated_at": existing[5],
                }
            rows.append(
                {
                    **candidate_for_grade,
                    "operation": operation,
                    "promotion": grade,
                    "current_label": current_label,
                    "proposed_label": {
                        "label": candidate_for_grade.get("label"),
                        "entity": candidate_for_grade.get("entity"),
                        "wallet_type": candidate_for_grade.get("wallet_type"),
                        "confidence": grade.get("confidence"),
                    },
                }
            )
    finally:
        conn.close()

    would_insert = sum(1 for row in rows if row["operation"] == "insert_new_label")
    would_update = sum(1 for row in rows if row["operation"] == "update_existing_label")
    blocked = sum(1 for row in rows if row["operation"] == "blocked")
    by_entity: dict[str, int] = {}
    by_chain: dict[str, int] = {}
    for row in rows:
        if row["operation"] == "blocked":
            continue
        entity = str(row.get("entity") or "unknown")
        chain = str(row.get("chain") or "unknown")
        by_entity[entity] = by_entity.get(entity, 0) + 1
        by_chain[chain] = by_chain.get(chain, 0) + 1
    return {
        "ok": True,
        "source_policy": "read-only promotion impact preview; no trusted labels are changed",
        "min_score": min_score,
        "requested": len(clean_ids),
        "reviewed": len(rows),
        "would_promote": would_insert + would_update,
        "would_insert": would_insert,
        "would_update_existing": would_update,
        "blocked": blocked,
        "by_entity": [{"entity": key, "count": value} for key, value in sorted(by_entity.items())],
        "by_chain": [{"chain": key, "count": value} for key, value in sorted(by_chain.items())],
        "rows": rows,
        "next_action": "If this preview is clean, run promote with dry_run=true again before any dry_run=false request.",
    }


def get_label_corroboration_queue(
    limit: int = 50,
    entity: str | None = None,
    chain: str | None = None,
    include_manual_review: bool = False,
) -> dict[str, Any]:
    """Rank candidates that should receive the next external corroboration pass."""
    _init_db()
    limit = max(1, min(int(limit or 50), 200))
    where = ["c.status = 'candidate'"]
    params: list[Any] = []
    if entity:
        where.append("LOWER(c.proposed_entity) LIKE ?")
        params.append(f"%{entity.lower()}%")
    if chain:
        where.append("c.chain = ?")
        params.append(_chain_key(chain))

    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            f"""
            SELECT c.id, c.chain, c.address, c.proposed_label, c.proposed_entity,
                   c.proposed_wallet_type, c.confidence, c.source, c.source_url,
                   c.evidence_json, c.seen_count, c.last_seen_at,
                   COUNT(e.id) AS evidence_bundles,
                   MAX(e.observed_at) AS last_evidence_at,
                   MAX(e.score) AS max_evidence_score
            FROM label_candidates c
            LEFT JOIN label_candidate_evidence e ON e.candidate_id = c.id
            WHERE {' AND '.join(where)}
            GROUP BY c.id
            ORDER BY c.seen_count DESC, c.last_seen_at DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        candidates = [
            {
                "id": int(row[0]),
                "chain": row[1],
                "address": row[2],
                "label": row[3],
                "entity": row[4],
                "wallet_type": row[5],
                "confidence": row[6],
                "source": row[7],
                "source_url": row[8],
                "evidence": _json_list(row[9]),
                "seen_count": int(row[10] or 0),
            }
            for row in rows
        ]
        evidence_scores = _candidate_evidence_score_map(conn, candidates)
    finally:
        conn.close()

    output: list[dict[str, Any]] = []
    blocked_by_reason: dict[str, int] = {}
    manual_review_blockers = {
        "signer_candidate_requires_manual_review",
        "strict_protocol_requires_manual_review",
        "invalid_chain_address_format",
        "strict_evm_only_for_now",
    }
    manual_review_filtered = 0
    for row, candidate in zip(rows, candidates):
        scored = evidence_scores.get(int(candidate["id"]))
        candidate_for_grade = _candidate_with_persisted_evidence(candidate, scored)
        grade = _apply_persisted_evidence_gate(_strict_promotion_grade(candidate_for_grade), candidate_for_grade)
        blockers = list(grade.get("blockers") or [])
        for blocker in blockers:
            blocked_by_reason[blocker] = blocked_by_reason.get(blocker, 0) + 1

        evidence_bundles = int(row[12] or 0)
        max_evidence_score = int(row[14] or 0)
        needs_first_evidence = evidence_bundles == 0
        ready_for_review = _is_verified_review_ready(scored or {})
        needs_refresh = evidence_bundles > 0 and max_evidence_score < 50 and not ready_for_review
        priority_score = int(candidate["seen_count"])
        if candidate["entity"] in PRIORITY_LABEL_TARGETS:
            priority_score += 40
        if needs_first_evidence:
            priority_score += 35
        elif needs_refresh:
            priority_score += 15
        if any(blocker in blockers for blocker in ("invalid_chain_address_format", "strict_evm_only_for_now")):
            priority_score -= 50
        if "signer_candidate_requires_manual_review" in blockers:
            priority_score -= 120
        if "strict_protocol_requires_manual_review" in blockers:
            priority_score -= 80
        priority_score = max(0, priority_score)

        if ready_for_review:
            action = "ready_for_admin_review"
        elif needs_first_evidence:
            action = "corroborate_first_pass"
        elif needs_refresh:
            action = "refresh_weak_evidence"
        else:
            action = "wait_for_new_source"

        item = {
            **candidate_for_grade,
            "evidence_bundles": evidence_bundles,
            "last_evidence_at": row[13],
            "max_evidence_score": max_evidence_score,
            "verified_review_ready": ready_for_review,
            "promotion_blockers": blockers,
            "requires_manual_review": bool(set(blockers) & manual_review_blockers),
            "priority_score": priority_score,
            "recommended_action": action,
        }
        if item["requires_manual_review"] and not include_manual_review:
            manual_review_filtered += 1
            continue
        output.append(item)

    output.sort(key=lambda item: (item["priority_score"], item["seen_count"]), reverse=True)
    return {
        "ok": True,
        "source_policy": "read-only corroboration queue; no evidence is fetched and no labels are changed",
        "include_manual_review": include_manual_review,
        "manual_review_filtered": manual_review_filtered,
        "rows_reviewed": len(output),
        "blocked_by_reason": [
            {"reason": reason, "count": count}
            for reason, count in sorted(blocked_by_reason.items(), key=lambda item: item[1], reverse=True)
        ][:10],
        "rows": output[:limit],
        "recommendation": "Run admin POST corroboration only for high priority rows without severe format/chain blockers.",
    }


def get_label_acquisition_plan(limit: int = 50, min_trusted_per_entity: int = 100) -> dict[str, Any]:
    """Read-only plan for what entity labels to acquire next before RPC scaling."""
    _init_db()
    floor = max(10, min(int(min_trusted_per_entity or 100), 10_000))
    targets = {entity: max(target, floor) for entity, target in PRIORITY_LABEL_TARGETS.items()}
    conn = sqlite3.connect(str(DB_PATH))
    try:
        trusted_rows = conn.execute(
            """
            SELECT entity, confidence, sources_json
            FROM labels
            WHERE COALESCE(entity, '') != ''
            """
        ).fetchall()
        candidate_rows = conn.execute(
            """
            SELECT id, chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, seen_count
            FROM label_candidates
            WHERE status = 'candidate'
              AND COALESCE(proposed_entity, '') != ''
            ORDER BY seen_count DESC, id ASC
            """
        ).fetchall()
        candidate_items = [
            {
                "id": int(row[0]),
                "chain": row[1],
                "address": row[2],
                "label": row[3],
                "entity": str(row[4] or "").strip(),
                "wallet_type": row[5],
                "confidence": row[6],
                "source": row[7],
                "source_url": row[8],
                "evidence": _json_list(row[9]),
                "seen_count": int(row[10] or 0),
            }
            for row in candidate_rows
        ]
        evidence_scores = _candidate_evidence_score_map(conn, candidate_items)
    finally:
        conn.close()

    trusted_by_entity: dict[str, dict[str, int]] = {}
    for entity, confidence, sources_json in trusted_rows:
        name = str(entity or "").strip()
        if not name:
            continue
        sources = [_source_name_from_entry(source) for source in _json_list(sources_json)]
        source_text = " ".join(sources).lower()
        is_strict_source = (
            any(source.startswith("candidate_promotion:") for source in sources)
            or "manual_verified" in source_text
            or any(public in source_text for public in ("etherscan", "blockscout", "zerion", "cielo"))
        )
        source_bucket = "strict" if is_strict_source else "legacy_or_unverified"
        bucket = trusted_by_entity.setdefault(
            name,
            {
                "trusted_labels": 0,
                "strict_trusted_labels": 0,
                "legacy_or_unverified_labels": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
            },
        )
        bucket["trusted_labels"] += 1
        bucket["strict_trusted_labels" if source_bucket == "strict" else "legacy_or_unverified_labels"] += 1
        conf = str(confidence or "low").lower()
        if is_strict_source and conf in {"high", "medium", "low"}:
            bucket[conf] += 1

    candidates_by_entity: dict[str, dict[str, Any]] = {}
    for candidate in candidate_items:
        entity = str(candidate.get("entity") or "").strip()
        if not entity:
            continue
        scored = evidence_scores.get(int(candidate["id"]))
        candidate_for_grade = _candidate_with_persisted_evidence(candidate, scored)
        grade = _apply_persisted_evidence_gate(_strict_promotion_grade(candidate_for_grade), candidate_for_grade)
        review_ready = _is_verified_review_ready(scored or {}) or bool(grade.get("strict_ready"))
        bucket = candidates_by_entity.setdefault(
            entity,
            {
                "open_candidates": 0,
                "strict_ready": 0,
                "blocked": 0,
                "seen_count_total": 0,
                "top_candidate_ids": [],
                "top_blockers": {},
            },
        )
        bucket["open_candidates"] += 1
        bucket["seen_count_total"] += candidate["seen_count"]
        if len(bucket["top_candidate_ids"]) < 8:
            bucket["top_candidate_ids"].append(candidate["id"])
        if review_ready:
            bucket["strict_ready"] += 1
        else:
            bucket["blocked"] += 1
            for blocker in grade.get("blockers") or []:
                bucket["top_blockers"][blocker] = int(bucket["top_blockers"].get(blocker, 0)) + 1

    entity_names = set(targets) | set(trusted_by_entity) | set(candidates_by_entity)
    rows: list[dict[str, Any]] = []
    for entity in sorted(entity_names):
        trusted = trusted_by_entity.get(entity, {})
        candidates = candidates_by_entity.get(entity, {})
        target = targets.get(entity, floor)
        trusted_count = int(trusted.get("strict_trusted_labels", 0))
        legacy_count = int(trusted.get("legacy_or_unverified_labels", 0))
        strict_ready = int(candidates.get("strict_ready", 0))
        open_candidates = int(candidates.get("open_candidates", 0))
        gap = max(0, target - trusted_count)
        if gap <= 0:
            action = "monitor"
        elif strict_ready > 0:
            action = "dry_run_promote_strict_ready"
        elif open_candidates > 0:
            action = "collect_more_evidence_for_candidates"
        else:
            action = "acquire_new_source_snapshots"
        rows.append(
            {
                "entity": entity,
                "target_trusted_labels": target,
                "trusted_labels": trusted_count,
                "total_label_rows": int(trusted.get("trusted_labels", 0)),
                "legacy_or_unverified_labels": legacy_count,
                "high_confidence_labels": int(trusted.get("high", 0)),
                "medium_confidence_labels": int(trusted.get("medium", 0)),
                "open_candidates": open_candidates,
                "strict_ready_candidates": strict_ready,
                "blocked_candidates": int(candidates.get("blocked", 0)),
                "candidate_seen_count_total": int(candidates.get("seen_count_total", 0)),
                "gap_to_target": gap,
                "priority_score": round(gap + max(0, 25 - strict_ready) + (10 if open_candidates == 0 else 0), 2),
                "recommended_action": action,
                "top_candidate_ids": candidates.get("top_candidate_ids", []),
                "top_blockers": [
                    {"blocker": blocker, "count": count}
                    for blocker, count in sorted(
                        (candidates.get("top_blockers") or {}).items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )[:5]
                ],
                "suggested_sources": [
                    f"https://intel.arkm.com/explorer/entity/{entity.lower().replace(' ', '-')}",
                    "scrapling_normalized_entity_snapshot",
                    "verified_manual_seed_if_source_is_public",
                ],
            }
        )

    rows.sort(key=lambda item: (item["priority_score"], item["gap_to_target"]), reverse=True)
    rows = rows[: max(1, min(int(limit or 50), 200))]
    return {
        "ok": True,
        "target_floor": floor,
        "entities_reviewed": len(entity_names),
        "rows": rows,
        "source_policy": "read-only acquisition plan; no candidates are promoted and no trusted labels are changed",
        "recommendation": "Acquire or re-scrape high-value entity pages first, then promote only strict-ready candidates after dry-run review.",
    }


def promote_label_candidates(
    candidate_ids: list[int],
    min_score: int = 90,
    dry_run: bool = True,
    confirm: str | None = None,
) -> dict[str, Any]:
    """Promote explicitly selected candidates into trusted labels after the strict safety gate."""
    _init_db()
    min_score = max(90, int(min_score or 90))
    clean_ids = sorted({int(value) for value in candidate_ids if int(value) > 0})
    if not clean_ids:
        return {"ok": True, "dry_run": dry_run, "promoted": 0, "rows": []}
    if not dry_run and confirm != "PROMOTE_TRUSTED_LABELS":
        return {
            "ok": False,
            "dry_run": dry_run,
            "promoted": 0,
            "rows": [],
            "error": "confirm_PROMOTE_TRUSTED_LABELS_required",
            "source_policy": "real trusted-label promotion requires explicit confirmation",
        }

    placeholders = ",".join("?" for _ in clean_ids)
    conn = sqlite3.connect(str(DB_PATH))
    promoted = 0
    reviewed = []
    backup_path = ""
    audit_id: int | None = None
    try:
        rows = conn.execute(
            f"""
            SELECT id, chain, address, proposed_label, proposed_entity, proposed_wallet_type,
                   confidence, source, source_url, evidence_json, seen_count
            FROM label_candidates
            WHERE id IN ({placeholders}) AND status = 'candidate'
            """,
            clean_ids,
        ).fetchall()
        candidates = [
            {
                "id": row[0],
                "chain": row[1],
                "address": row[2],
                "label": row[3],
                "entity": row[4],
                "wallet_type": row[5],
                "confidence": row[6],
                "source": row[7],
                "source_url": row[8],
                "evidence": _json_list(row[9]),
                "seen_count": row[10],
            }
            for row in rows
        ]
        evidence_scores = _candidate_evidence_score_map(conn, candidates)
        promotable: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for candidate in candidates:
            scored = evidence_scores.get(int(candidate["id"]))
            candidate_for_grade = _candidate_with_persisted_evidence(candidate, scored)
            grade = _apply_persisted_evidence_gate(_strict_promotion_grade(candidate_for_grade), candidate_for_grade)
            if not grade["eligible"] or grade["score"] < min_score:
                reviewed.append({**candidate_for_grade, "promotion": grade, "status": "blocked"})
                continue
            trusted_row = {
                **candidate_for_grade,
                "confidence": grade["confidence"],
                "source": f"candidate_promotion:{candidate['source']}",
                "evidence": {
                    "candidate_id": candidate["id"],
                    "score": grade["score"],
                    "reasons": grade["reasons"],
                    "source_url": candidate["source_url"],
                },
            }
            promotable.append((candidate, candidate_for_grade, trusted_row))
            reviewed.append({**candidate_for_grade, "promotion": grade, "status": "would_promote" if dry_run else "promoted"})

        if not dry_run and promotable:
            backup_path = _backup_label_ledger_db("before_promotion")
        for candidate, candidate_for_grade, trusted_row in promotable:
            if not dry_run:
                _upsert_label(conn, trusted_row)
                conn.execute(
                    "UPDATE label_candidates SET status = 'promoted', last_seen_at = ? WHERE id = ?",
                    (_utc_now(), candidate["id"]),
                )
                promoted += 1
        if not dry_run:
            source_policy = (
                "explicit candidate IDs only; strict score; no automatic bulk promotion; "
                "dry_run=false requires confirm=PROMOTE_TRUSTED_LABELS and creates a pre-write backup plus audit row"
            )
            cur = conn.execute(
                """
                INSERT INTO label_promotion_audit (
                    created_at, dry_run, confirm, candidate_ids_json, result_json,
                    backup_path, requested, reviewed, promoted, source_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _utc_now(),
                    0,
                    confirm,
                    json.dumps(clean_ids),
                    json.dumps(reviewed, ensure_ascii=False, sort_keys=True),
                    backup_path,
                    len(clean_ids),
                    len(reviewed),
                    promoted,
                    source_policy,
                ),
            )
            audit_id = int(cur.lastrowid)
            conn.commit()
    finally:
        conn.close()

    source_policy = (
        "explicit candidate IDs only; strict score; no automatic bulk promotion; "
        "dry_run=false requires confirm=PROMOTE_TRUSTED_LABELS"
    )
    if not dry_run:
        source_policy += " and creates a pre-write backup plus audit row"
    return {
        "ok": True,
        "dry_run": dry_run,
        "requested": len(clean_ids),
        "reviewed": len(reviewed),
        "promoted": promoted,
        "backup_path": backup_path or None,
        "audit_id": audit_id,
        "rows": reviewed,
        "source_policy": source_policy,
    }


__all__ = [
    "acquire_priority_label_source_snapshots",
    "build_label_ledger",
    "stage_label_candidates_from_normalized_sources",
    "get_label_ledger_summary",
    "get_label_candidates",
    "get_label_candidate_audit",
    "get_label_candidate_quality_report",
    "consolidate_label_candidate_duplicates",
    "review_label_candidate_promotions",
    "review_strict_label_candidate_promotions",
    "plan_label_candidate_automation",
    "corroborate_label_candidates",
    "get_label_candidate_evidence",
    "get_label_candidate_evidence_scores",
    "get_verified_label_candidate_review_queue",
    "get_label_candidate_review_dashboard",
    "get_label_corroboration_queue",
    "get_label_acquisition_plan",
    "preview_label_candidate_promotion_impact",
    "promote_label_candidates",
]
