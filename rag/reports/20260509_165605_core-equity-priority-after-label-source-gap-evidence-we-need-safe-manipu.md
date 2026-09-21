# Local Advisor Report

Generated: 2026-05-09T16:56:05

## Question

Core Equity priority after label source gap evidence: we need safe manipulation detection readiness. What should the next read-only report measure before building alerts/signals?

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Analysis: Core Equity Priority After Label Source Gap Evidence

## Understanding the Question

The question asks about the **next read-only report measure** Core Equity should implement **before** building alerts/signals, given that:
1. We have "label source gap evidence" (we know where our label data comes from and where gaps exist)
2. We need "safe manipulation detection readiness" (we want to detect coordinated manipulation safely)

## Key Context from Repository

From `project_state.md`:

**Current Label Architecture:**
- `backend/services/label_ledger.py`: builds deduped label ledger from Scrapling normalized Arkham snapshots
- `backend/services/label_expansion.py`: derives low/medium confidence labels from local on-chain data and Scrapling transfer surfaces
- `backend/data/arkham/label_ledger.db`: high-confidence and derived label ledger (461 direct labels, 18 derived)

**Current RPC/Entity State:**
- `wallet_chain_state` tracks: address kind, contract flag, native USD value, activity tier, risk flags, data quality score, **label source evidence**, and RPC source attribution
- Entity RPC enrichment shows high coverage (e.g., Uniswap 65/65, Binance 58/58)

**Manipulation Detection Context:**
- Alpha Lab includes "manipulation detection and premium client workflows"
- `wallet_chain_state` already tracks "risk flags" and "activity tier"

## Reasoning

Given we have **label source gap evidence** and need **manipulation detection readiness**, the next read-only report should measure:

### The Critical Gap: Label Source Attribution Quality

We know labels come from sources (Arkham, Scrapling, RPC, etc.), but we need to measure **how reliably each source's labels are attributed and validated** before building manipulation alerts.

---

## Answer

### Next Read-Only Report Measure

**Measure: `label_source_attribution_score` per entity**

This metric evaluates how well each labelled entity has **multi-source corroboration** before being used in manipulation detection alerts.

#### Why This Measure?

1. **Addresses the "label source gap"**: We know our sources, but we need to measure source reliability per entity
2. **Enables "safe manipulation detection"**: Alerts should only trigger when multiple independent sources corroborate suspicious labeling
3. **Read-only**: Queries existing `wallet_chain_state` and `label_ledger.db` without mutation
4. **Prerequisite for alerts**: We need to know which labels are "well-sourced" before using them in signal generation

#### Implementation Approach

```sql
-- Pseudo-query: Calculate source attribution score per labelled entity
SELECT 
    w.address,
    w.label_source_evidence,
    COUNT(DISTINCT source_type) as source_diversity,
    MAX(source_confidence) as max_confidence,
    CASE 
        WHEN COUNT(DISTINCT source_type) >= 2 AND MAX(source_confidence) >= 0.8 THEN 'HIGH'
        WHEN COUNT(DISTINCT source_type) = 1 AND MAX(source_confidence) >= 0.9 THEN 'MEDIUM'
        ELSE 'LOW'
    END as attribution_quality
FROM wallet_chain_state w
LEFT JOIN label_ledger ll ON w.address
