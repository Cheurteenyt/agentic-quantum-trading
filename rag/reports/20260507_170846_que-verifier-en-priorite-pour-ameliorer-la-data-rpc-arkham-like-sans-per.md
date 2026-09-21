# Local Advisor Report

Generated: 2026-05-07T17:08:46

## Question

Que verifier en priorite pour ameliorer la data RPC Arkham-like sans perdre nos labels ?

## Sources

- `backend/services/arkham_tracker.py`
- `backend/routers/arkham.py`

## Advisor Output

You are Core Equity's local coding RAG assistant.
Answer only from the provided repository context.
If the context is insufficient, say exactly what is missing.
Always cite source paths inline.
Prefer concise, actionable engineering guidance.

Question:
Que verifier en priorite pour ameliorer la data RPC Arkham-like sans perdre nos labels ?

Repository context:
[Source 1] backend/services/arkham_tracker.py
"""
Arkham Tracker — Real-time Smart Money Tracking
=================================================

Ce module est le CŒUR du système de tracking Hermes.
Il utilise la base de données des labels Arkham (scrapés via Firecrawl)
pour identifier en temps réel les mouvements des entités connues.

ARCHITECTURE:
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│  Blockchain   │────▶│ ArkhamTracker │────▶│  Hermes      │
│  WebSocket    │     │  (Ce module)  │     │  Frontend    │
│  (Etherscan,  │     │               │     │  Dashboard   │
│   Helius,     │     │  Lookup DB    │     └──────────────┘
│   QuickNode)  │     │  Arkham labels│
└──────────────┘     └───────┬───────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌──────────┐   ┌──────────┐   ┌──────────┐
       │SmartEngine│   │OppEngine │   │IntelAgg  │
       │(anomalie)│   │(flows)   │   │(signaux) │
       └──────────┘   └──────────┘   └──────────┘

FONCTIONNEMENT:
1. Le Collector reçoit les trades Hyperliquid WS
2. Pour chaque trade, le tracker vérifie si l'adresse est dans la DB Arkham
3. Si oui → identifie l'entité (Binance, J

---

[Source 2] backend/routers/arkham.py
},
            "chain_coverage_matrix": chain_coverage_matrix,
            "acquisition_plan": acquisition_plan,
            "rpc_ingestion_gate": {
                "decision": "manual_small_windows_only_until_chain_tier_is_useful",
                "reason": "RPC gives raw facts; Arkham-like value requires labels, attribution, and chain-scoped source quality first.",
                "safe_now": [
                    "ethereum_recent_blocks",
                    "bsc_recent_blocks",
                ],
                "not_safe_yet": [
                    "full historical archive ingestion",
                    "cross-chain wallet clustering without confidence scoring",
                    "token manipulation alerts without holder/flow baselines",
                ],
            },
        },
        "source_breakdown": dict(source_breakdown),
        "top_entities_by_value": [
            {"entity": entity, "value_usd": round(value, 2), "wallet_rows": entity_wallet_rows.get(entity, 0)}
            for entity, value in sorted(entity_values.items(), key=lambda item: item[1], reverse=True)[:15]
        ],
        "top_holder_tokens": [
            {"token": token, "holders_cached": coun

---

[Source 3] backend/routers/arkham.py
"source_catalog": ACQUISITION_SOURCE_CATALOG,
        "strategy": [
            "label-first: increase address/entity attribution before bulk RPC ingestion",
            "chain-scoped: never merge ETH/BSC/Solana activity without explicit chain source",
            "raw-vs-intel: store raw RPC facts separately from labels, confidence and entity attribution",
            "dedupe-first: every imported row needs a deterministic dedupe key",
        ],
        "priority_queue": prioritized[:10],
        "minimum_useful_thresholds": {
            "per_chain_labelled_addresses": 1000,
            "per_chain_rpc_transactions": 100000,
            "per_chain_holder_rows": 1000,
            "per_chain_transfer_rows": 10000,
        },
    }


_ARKHAM_COVERAGE_CACHE: dict[str, Any] = {"signature": None, "report": None}


def _build_arkham_coverage_report() -> dict[str, Any]:
    """Return an honest local equivalent of Arkham API coverage metrics."""
    files = sorted(SCRAPLING_NORMALIZED_DIR.glob("*.json")) if SCRAPLING_NORMALIZED_DIR.exists() else []
    signature = _normalized_files_signature(files)
    if _ARKHAM_COVERAGE_CACHE.get("signature") == signature and _ARKHAM_COVERAGE_CACHE.get(

---

[Source 4] backend/routers/arkham.py
get("family") or "unknown"

        labels = int(metrics.get("labelled_addresses") or 0)
        holders = int(metrics.get("holder_rows") or 0)
        rpc_transactions = int(metrics.get("rpc_transactions") or 0)
        transfer_rows = int(metrics.get("transfer_rows") or 0)
        assets = int(metrics.get("assets_tracked") or 0)

        priority_score = 0
        if "low_label_coverage" in gaps:
            priority_score += 45
        if "low_flow_history" in gaps:
            priority_score += 25
        if "low_holder_coverage" in gaps:
            priority_score += 18
        if metrics.get("rpc_configured") and metrics.get("rpc_ingestion_enabled"):
            priority_score += 12
        if row.get("arkham_reference_coverage_pct"):
            priority_score += min(10, int(row["arkham_reference_coverage_pct"]) // 10)
        if chain in {"ethereum", "bsc", "base", "solana", "bitcoin"}:
            priority_score += 8

        next_sources: list[str] = []
        actions: list[str] = []
        if labels < 100:
            next_sources.extend(["openlabels_blockscout", "curated_static_entities", "scrapling_arkham_snapshots"])
            actions.append("seed high-confidence


Additional role instructions:

You are the LOCAL READ-ONLY ADVISOR for Core Equity.
You are running beside Codex to save tokens and surface useful hypotheses.
You must never claim you modified files.
You must not provide bulk rewrite instructions.
You must not suggest unsafe data ingestion, secret exposure, or admin bypasses.

Return a concise engineering report with exactly these sections:

1. Most relevant facts from the retrieved context
2. Useful hypotheses Codex should verify
3. Files or endpoints worth inspecting next
4. Risks and non-goals
5. Small next experiments
6. Confidence

If the retrieved context is insufficient, say what context should be retrieved next.
