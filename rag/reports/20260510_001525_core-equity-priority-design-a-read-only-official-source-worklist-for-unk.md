# Local Advisor Report

Generated: 2026-05-10T00:15:25

## Question

Core Equity priority: design a read-only official source worklist for unknown routers with RPC state but no source evidence. Should output search packages/status without mapping or labels. No edits.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/generated_project_map.md`
- `rag/memory/model_routing_guide.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`

## Advisor Output

# Analysis: Core Equity Read-Only Worklist Design

## Understanding the Request

The user wants to design a **read-only official source worklist** for:
- **Unknown routers** (endpoints not yet mapped in the router surface)
- **With RPC state** (they have observed on-chain/RPC data)
- **Without source evidence** (no Arkham-like label evidence backing them)

**Expected output behavior:**
- Search packages/status without mapping them
- No label assignment
- No edits to existing data

---

## What I Found in the Context

### 1. Router Surface Analysis

From `rag/memory/generated_project_map.md`:

```
### `backend/routers/__init__.py`
- No router endpoints detected.
### `backend/routers/agents.py`
- `POST /run` -> `run_agent` [ read] -> no direct service detected
- `GET /status` -> `?` [ read] -> no direct service detected
- `POST /stop` -> `stop_agent` [ read] -> no direct service detected
- `GET /signals` -> `?` [ read] -> no direct service detected
- `GET /signals/stats` -> `?` [ read] -> no direct service detected
```

**Finding:** The router surface shows endpoints with **unknown service mappings** (marked with `?`). These are candidates for the worklist.

---

### 2. RPC State Storage

From `rag/memory/project_state.md`:

```
- `wallet_chain_state` now tracks address kind, contract flag, native USD value, activity tier, risk flags, data quality score, label source evidence, and RPC source attribution.
- `wallet_chain_state` has 267 rows across arbitrum 4, base 12, bsc 18, eth 227 and polygon 6.
```

**Finding:** RPC state exists and is stored in `wallet_chain_state` with rich metadata including source attribution.

---

### 3. Label Evidence Model

From `rag/memory/project_state.md`:

```
- Labels-first before RPC scale.
- Treat `label_candidates` as untrusted until strict admin promotion.
- Treat `label_candidate_evidence` as evidence bundles, not trusted labels.
```

**Finding:** The system already has a model for separating **labels** (trusted) from **label_candidates** (untrusted, needs promotion).

---

### 4. Admin Endpoint Pattern

From `rag/memory/generated_project_map.md`:

```
Any endpoint with `Depends(_require_data_admin)` requires `CORE_ADMIN_TOKEN`.
```

**Finding:** Admin protection exists via `CORE_ADMIN_TOKEN` gate.

---

## What's Missing from Context

| Required Information | Status | Why It Matters |
|---------------------|--------|----------------|
| **Router endpoint discovery mechanism** | Not found | Need to know how unknown endpoints are detected |
| **RPC state schema** | Partial | Need to see the actual `wallet_chain_state` table structure |
| **Label candidate promotion workflow** | Partial | Need to understand the admin promotion path |
| **Source attribution fields** | Not found | Need to know what "source evidence" looks like |
| **Worklist storage location** | Not found
