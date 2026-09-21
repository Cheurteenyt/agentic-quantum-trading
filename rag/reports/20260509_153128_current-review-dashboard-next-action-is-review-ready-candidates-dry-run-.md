# Local Advisor Report

Generated: 2026-05-09T15:31:28

## Question

Current review dashboard next_action is review_ready_candidates_dry_run with ready IDs. Dry-run promotion works and no trusted labels change. Before enabling any real trusted-label promotion, what is the safest next backend improvement: promotion impact preview, promotion audit log, backup enforcement, or UI wiring? Pick one concrete next step with tests and no automatic promotion.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

Based on the repository context, here is the analysis and recommendation.

### Analysis

1.  **Current State**: The review dashboard is in a `dry_run` state. It identifies candidates (IDs) but does not modify trusted labels. The system is stable, with data architecture centered around `label_ledger.py` and `onchain_engine.py` managing the data.
2.  **The Goal**: Enable real trusted-label promotion safely. The risk is that the current promotion logic might be brittle, causing data corruption or incorrect label assignment if run at scale.
3.  **The Requirement**: A "safest next backend improvement" that provides visibility into the impact *before* the change is applied, without automating the change itself.
4.  **Evaluating Options**:
    *   **Promotion Audit Log**: Useful for post-mortem debugging but does not prevent the "blast" of a bad promotion rule. It is reactive.
    *   **Backup Enforcement**: A safety net for data recovery, but it does not help the engineer understand *why* a promotion failed or succeeded. It is a recovery mechanism, not a prevention mechanism.
    *   **UI Wiring**: This addresses the frontend presentation of the dashboard. It does not solve the backend engineering problem of safely enabling the promotion logic.
    *   **Promotion Impact Preview**: This directly addresses the "safest next step" requirement. It allows the engineer to simulate the promotion logic against the dataset (e.g., "If we run this rule, 140 wallets will be labeled 'Exchange Hot Wallet'"). This aligns with the "Durable project memory" emphasis on data quality and "no hidden autonomous modification." It provides the "dry run" capability needed to validate the logic before committing to the write operation.

### Recommendation

**Promotion Impact Preview**

**Reasoning**:
The system is currently in a "read-only" or "dry-run" verification phase. The logical next step to enable production usage is to quantify the impact of the promotion logic. A "Promotion Impact Preview" feature would allow the backend to execute the promotion logic in memory against the candidate set and output a report (e.g., number of wallets affected, new labels assigned, potential conflicts). This satisfies the requirement for a "concrete next step with tests" (unit tests for the preview logic) and "no automatic promotion" (the preview is a read-only report). It bridges the gap between the current dry-run state and the risk of live promotion.
