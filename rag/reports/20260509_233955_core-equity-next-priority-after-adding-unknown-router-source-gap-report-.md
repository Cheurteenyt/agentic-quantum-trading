# Local Advisor Report

Generated: 2026-05-09T23:39:55

## Question

Core Equity next priority after adding unknown-router-source-gap-report: should we integrate router source gaps into data-readiness/manipulation-readiness before more enrichment? Suggest safest no-client-execution path. No edits.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/generated_project_map.md`
- `rag/memory/model_routing_guide.md`
- `backend/routers/onchain.py`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

# Analysis: Core Equity Next Priority After unknown-router-source-gap-report

## Summary

Based on the repository context, the next priority should be **integrating router source gaps into data-readiness/manipulation-readiness checks before further enrichment**. This is the safest no-client-execution path.

---

## Key Findings

### 1. Current State (from project_state.md)

The system already has:
- **Entity/chain gap reporting** via `get_rpc_entity_chain_gap_report` endpoint
- **Auto-enrichment** with `CORE_AUTO_ENRICH_MODE=chain_gaps|entities`
- **Data readiness** tracking via `get_onchain_data_readiness` endpoint

### 2. The Gap

The `unknown-router-source-gap-report` appears to be a **reporting endpoint** that identifies when router source data is missing or incomplete. However, this gap detection is **not yet integrated into the data-readiness validation pipeline**.

### 3. Recommended Integration Path

```
Router Source Gap Report → Data-Readiness Gate → Enrichment Pipeline
```

**Safest no-client-execution path:**

1. **Add router-source-gap-check to `get_onchain_data_readiness`** (no client execution)
2. **Create a read-only validation endpoint** that checks gap coverage before enrichment
3. **Use existing admin token gates** (`Depends(_require_data_admin)`) for safety

---

## Specific Recommendations

### Immediate Next Steps (No Edits Required)

1. **Inspect `backend/services/onchain_coverage.py`** — This service owns "labelled-vs-RPC entity coverage summaries" and is the natural place to add router-source gap metrics.

2. **Check `backend/routers/onchain.py`** — The data readiness endpoint is here; add router-source-gap validation as a read-only check.

3. **Verify the gap report endpoint** — Find the exact endpoint that produces `unknown-router-source-gap-report` output and ensure it's chain-scoped and read-only (as per regression tests in project_state.md).

### Verification Commands

```powershell
# Check data readiness endpoint (no client execution)
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "How is data readiness validated?" --domain backend

# Inspect onchain coverage service
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py ask "Where is entity coverage computed?" --domain backend
```

---

## Confidence: HIGH

**Why:** The architecture already supports read-only gap detection via the entity-chain gap model. The router-source gap is the same pattern applied to a different data dimension (router sources vs. entity/chain). The safest path is to integrate it into the existing data-readiness gate before enrichment proceeds, following the established `Frontend -> API -> Router -> Service -> Data` pattern.
