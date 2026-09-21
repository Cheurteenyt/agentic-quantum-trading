# Local Advisor Report

Generated: 2026-05-10T01:03:45

## Question

Core Equity priority: design a read-only official source acquisition queue from unknown router proof dossiers. It should separate research-ready, blocked conflicts, and insufficient identity rows, expose exact source requirements and no writes. No edits.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Read-Only Source Acquisition Queue Design

Based on the repository context, here is the architectural design for a read-only official source acquisition queue that processes unknown router proof dossiers.

## 1. Data Model: The `Source_Dossier` Row

This row represents a single piece of evidence (a "proof dossier") from an unknown router that requires official source verification. It is stored in a read-only audit table to preserve the exact state of the dossier at the time of discovery.

**Table: `source_dossiers`** (Read-Only Audit)

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID | Unique identifier for the dossier. |
| `router_proof_id` | String | The original identifier from the unknown router. |
| `source_url` | String | The canonical URL where the proof resides (e.g., an explorer block view). |
| `evidence_hash` | String | SHA-256 hash of the raw dossier content for integrity. |
| `status` | Enum | `PENDING`, `VERIFIED`, `BLOCKED`, `INSUFFICIENT`. |
| `source_requirement` | String | The specific source needed to resolve the dossier (e.g., "RPC ETH Mainnet", "Arkham Label"). |
| `discovered_at` | Timestamp | When the dossier was first found. |
| `verified_at` | Timestamp | When the dossier was resolved by an official source. |

## 2. The Three-Stage Resolution Pipeline

The pipeline processes dossiers through three distinct stages, ensuring that no writes occur to the trusted label ledger and that the queue remains read-only.

### Stage 1: Research-Ready (PENDING)
Dossiers that have been discovered but lack official source confirmation.
*   **Action:** The system reads the `source_url` and `evidence_hash` to verify the dossier hasn't been tampered with.
*   **Outcome:** The dossier remains in `PENDING` status until an official source adapter confirms the data.

### Stage 2: Blocked Conflicts (BLOCKED)
Dossiers where the official source data contradicts the existing trusted label ledger.
*   **Action:** The system compares the dossier's entity/chain data against the `label_ledger.db`. If a conflict is detected (e.g., mismatched address kind or value), the dossier is marked `BLOCKED`.
*   **Outcome:** The dossier is flagged for manual review by an admin via the `GET /api/onchain/labels/candidates/corroborate` endpoint.

### Stage 3: Insufficient Identity (INSUFFICIENT)
Dossiers where the official source data is too vague to resolve the entity identity.
*   **Action:** The system checks if the `source_url` points to a generic page (e.g., a homepage) rather than a specific transaction or block.
*   **Outcome:** The dossier is marked `INSUFFICIENT` and removed from the active queue to prevent infinite loops.

## 3. Source Requirements Exposure

The system exposes the exact source requirements for each dossier through the read-only endpoint `GET /api/onchain/labels/candidates/corroborate`.

*   **Endpoint:** `GET /api/onchain/
