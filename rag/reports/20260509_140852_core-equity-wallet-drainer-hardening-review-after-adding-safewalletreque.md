# Local Advisor Report

Generated: 2026-05-09T14:08:52

## Question

Core Equity wallet-drainer hardening review: after adding safeWalletRequest, CSP/security headers, read-only Alpha Lab sessions, and wallet threat model, what should Codex verify next to reduce wallet drain, XSS, CSRF, token leakage, or unsafe future automation risk? Give no edits, only checks.

## Sources

- `rag/memory/project_state.md`
- `rag/memory/agent_improvement_protocol.md`
- `rag/memory/rag_operating_playbook.md`
- `rag/memory/model_routing_guide.md`

## Advisor Output

# Core Equity Wallet Hardening Review: Next Checks

## Summary

Based on the repository context, Core Equity has implemented several wallet security measures. Here are the critical checks Codex should verify next to reduce wallet drain, XSS, CSRF, token leakage, and unsafe automation risk.

---

## 1. Admin Endpoint Security Verification

**What to check:**
```
backend/routers/onchain.py
backend/services/onchain_quality.py
```

**Checks:**
- Verify `CORE_ADMIN_TOKEN` validation is enforced on all mutation endpoints
- Confirm admin endpoints are not exposed in production without tunnel authentication
- Check if `wallet_chain_state` mutation endpoints require proper admin gating

**Risk:** Admin token leakage could allow unauthorized wallet manipulation or label promotion

---

## 2. Private Client Access Audit

**What to check:**
```
backend/routers/arkham.py
backend/services/label_ledger.py
```

**Checks:**
- Verify private client access uses strict token gates as documented
- Confirm local machine/tunnel model is enforced for premium clients
- Check if client data is properly isolated from public endpoints

**Risk:** Token leakage could expose private client wallet data or enable unauthorized access

---

## 3. Alpha Lab Wallet Analysis Security

**What to check:**
```
backend/services/onchain_engine.py
backend/data/onchain/onchain.db
```

**Checks:**
- Verify Alpha Lab sessions are read-only as documented
- Confirm wallet analysis doesn't trigger unintended RPC calls or wallet interactions
- Check if `wallet_chain_state` enrichment is properly bounded

**Risk:** Read-only violations could enable wallet drain through simulated transactions

---

## 4. Label Promotion Risk Review

**What to check:**
```
backend/services/onchain_entities.py
backend/services/label_expansion.py
```

**Checks:**
- Verify derived labels require external confirmation before promotion to high-confidence
- Confirm `onchain_entities.py` doesn't invent missing labels automatically
- Check if label promotion could be exploited for manipulation detection bypass

**Risk:** Label manipulation could affect wallet classification and client targeting

---

## 5. RPC State Integrity Verification

**What to check:**
```
backend/data/onchain/onchain.db
wallet_chain_state table schema
```

**Checks:**
- Verify `wallet_chain_state` tracks risk flags and data quality scores
- Confirm RPC source attribution is properly logged
- Check if address quality classification helpers are properly isolated

**Risk:** Corrupted RPC state could lead to incorrect wallet risk assessment

---

## 6. Data Ingestion Bounds Review

**What to check:**
```
backend/services/seed_ingestion.py
backend/services/label_ledger.py
```

**Checks:**
- Verify data ingestion has bounded limits to prevent bulk backfills
- Confirm Scrapling adapters don't exceed rate limits
- Check if label ledger updates are properly versioned

**Risk:** Unbounded ingestion could corrupt label data or expose client data

---

## 7. Frontend API Security

**What to check:**
```
frontend/ (React UI components)
Backend API endpoints called by frontend
```

**Checks:**
- Verify frontend doesn't expose admin tokens or client secrets
- Confirm Alpha Lab UI properly gates sensitive wallet operations
- Check if CSP/security headers are applied to frontend builds

**Risk:** XSS/CSRF could enable wallet drain through UI manipulation

---

## 8. Token Handling Audit

**What to check:**
```
All files containing "token" in backend/services/
```

**Checks:**
- Verify tokens are never logged or written to disk
- Confirm token gates use secure storage (not environment variables in production)
- Check if token expiration and rotation is implemented

**Risk:** Token leakage could enable unauthorized wallet access

---

## Verification Commands

```powershell
# Health check for data domain
D:\trading-agent\.venv-rag\Scripts\python.exe D:\trading-agent\rag\scripts\rag_tool.py health --domain data

# Inspect wallet_chain_state schema
sqlite3 backend/data/onchain/onchain.db ".schema wallet_chain_state"

# Verify admin endpoint protection
curl -X POST "http://localhost:8000/api/admin/mutate" -H "Content-Type: application/json" -
