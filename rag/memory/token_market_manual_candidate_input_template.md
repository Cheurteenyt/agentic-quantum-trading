# Token Market Manual Candidate Input Template

## Purpose

Core Equity is paused before any real CEX label write.

The next step requires 2-3 manually supplied token-market candidates. Codex must not invent candidates, sources, routes, digests, venues, pools, or labels.

## Simple Status

- `LAB` is the only complete token-market candidate currently validated.
- The manual intake contract exists and is waiting for candidate input.
- Current intake state: `waiting_for_manual_candidates`.
- No new candidate rows have been inserted.
- No CEX label has been created.
- No final label table has been created or mutated.

## Required Candidate Shape

Use this structure for each candidate:

```json
{
  "token_symbol": "ABC",
  "market_type": "cex",
  "source_url": "https://...",
  "source_tier": "tier_1",
  "evidence_type": "official_exchange_market_page",
  "evidence_preview": {
    "note": "What the source shows"
  },
  "source_policy": "manual_admin_supplied_source_no_provider_or_scraping",
  "candidate_notes": "Optional short note"
}
```

## CEX Candidate Fields

For a CEX candidate, add:

```json
{
  "venue_name": "Gate",
  "pair": "ABC/USDT"
}
```

Expected route:

- `market_type=cex`
- future path: CEX review queue only
- never direct CEX label write

## DEX Candidate Fields

For a DEX candidate, add:

```json
{
  "chain": "bsc",
  "token_contract": "0x...",
  "pool_or_pair_address": "0x...",
  "router_or_factory_address": "0x..."
}
```

Expected route:

- `market_type=dex`
- future path: DEX/router review only
- never direct mapping write

## Manual Review Candidate

Use manual review when route is not clear:

```json
{
  "token_symbol": "ABC",
  "market_type": "manual_review",
  "source_url": "https://...",
  "source_tier": "tier_1",
  "evidence_type": "official_project_docs",
  "evidence_preview": {
    "note": "Route is unclear"
  }
}
```

Expected route:

- blocked/manual until classification is clear
- no label
- no mapping
- no trade

## Full Payload Template

```json
{
  "candidates": [
    {
      "token_symbol": "ABC",
      "market_type": "cex",
      "venue_name": "Gate",
      "pair": "ABC/USDT",
      "source_url": "https://...",
      "source_tier": "tier_1",
      "evidence_type": "official_exchange_market_page",
      "evidence_preview": {
        "note": "Official market page shows ABC/USDT"
      },
      "source_policy": "manual_admin_supplied_source_no_provider_or_scraping"
    },
    {
      "token_symbol": "XYZ",
      "market_type": "dex",
      "chain": "bsc",
      "token_contract": "0x...",
      "pool_or_pair_address": "0x...",
      "router_or_factory_address": "0x...",
      "source_url": "https://...",
      "source_tier": "tier_1",
      "evidence_type": "official_dex_deployment_registry",
      "evidence_preview": {
        "note": "Official registry shows pool/router"
      },
      "source_policy": "manual_admin_supplied_source_no_provider_or_scraping"
    }
  ]
}
```

## Guardrails

- No invented candidates.
- No provider calls.
- No scraping.
- No credentials.
- No DB writes.
- No migrations.
- No candidate row insertion.
- No status update.
- No CEX label.
- No final label table mutation.
- No DEX router evidence.
- No mapping.
- No trade.
- No wallet order.
- No client signal.
- No client opt-in.

## Next Step

The product owner should provide 2-3 candidates in the shape above.

After that, rerun:

```text
/goal Continue Core Equity en mode économique, priorité token market manual candidate intake preview read-only with supplied candidates.
```
