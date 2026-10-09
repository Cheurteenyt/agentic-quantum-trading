import { useEffect, useMemo, useRef, useState } from "react"
import { get, post } from "../services/api"
import { getExplorerAddressUrl, getExplorerTxUrl } from "../services/explorerLinks"
import WalletAnalyzer from "../components/WalletAnalyzer"
import { useLanguage } from "../i18n"

type Collector = {
  id: string
  name: string
  category: string
  status: string
  requires_api_key: boolean
  configured: boolean
  useful_for: string[]
  note: string
}

type Market = {
  source: "polymarket" | "kalshi" | string
  market_id: string
  event_id: string
  title: string
  event_title: string
  slug: string
  url?: string | null
  status: string
  close_time?: string | null
  is_stale_by_date?: boolean
  yes_bid?: number | null
  yes_ask?: number | null
  last_price?: number | null
  probability_mid?: number | null
  volume?: number | null
  volume_24h?: number | null
  liquidity?: number | null
  open_interest?: number | null
  tags?: string[]
}

type MarketsResponse = {
  source: string
  query: string | null
  count: number
  markets: Market[]
  source_status: Array<{ source: string; ok: boolean; count: number; latency_ms: number; error?: string | null }>
  latency_ms: number
  note: string
}

type RiskResult = {
  token: string
  chain: string
  risk_score: number
  sellability_score: number
  block_trade: boolean
  profit_integrity: string
  flags: Array<{ code: string; severity: string; points: number; detail: string }>
  required_proofs: string[]
}

type SimulationResult = {
  current_value?: number
  ending_value?: number
  pnl: number
  roi_pct: number
}

type WalletIntel = {
  ok: boolean
  wallet: string
  providers: Array<{ provider: string; ok: boolean; status: string; latency_ms: number; error?: string | null }>
  summary: {
    events: number
    swaps: number
    chains: string[]
    first_interactions: number
    observed_flow_usd: number
    copy_ready: boolean
    pnl: {
      rows: number
      realized_usd: number
      unrealized_usd: number
      total_pnl_usd: number
      trusted_realized_usd: number
      blocked_rows: number
      untrusted_rows: number
    }
  }
  events: Array<{
    source: string
    event_type: string
    source_event_id?: string
    tx_hash?: string | null
    chain?: string
    asset?: string
    actor?: string
    wallet_label?: string | null
    timestamp?: string | null
    from?: string | null
    to?: string | null
    dex?: string | null
  }>
  pnl: Array<{ provider: string; token: string; total_pnl_usd?: number; realized_usd?: number; unrealized_usd?: number; profit_integrity?: string; risk_score?: number }>
}

type WalletProbe = {
  ok: boolean
  wallet: string
  status: string
  status_label: string
  confidence: string
  reasons: string[]
  requirements: string[]
  provider_health: {
    ok: number
    total: number
    unstable: string[]
  }
  risk_summary: {
    blocked_rows: number
    untrusted_rows: number
    worst_risk_score: number
    suspicious_assets: string[]
  }
  asset_focus: Array<{ asset: string; chain: string; events: number; amount_usd: number }>
  copy_preview: {
    mode: string
    capital: number
    estimated_value: number
    pnl: number
    roi_pct: number
    basis: string
    note: string
  }
  intel: WalletIntel
  latency_ms?: number
  note?: string
}

const ACCOUNT_STORAGE_KEY = "core.connected.accounts"
const SELECTED_ALPHA_ACCOUNT_KEY = "core.alpha.selected.account"

type ConnectedAccount = {
  id: string
  label: string
  type: string
  provider: string
  address: string
  network: string
  status: string
  nativeBalance?: string
  nativeSymbol?: string
  verifiedAt?: number
}

type WalletCopyPlan = {
  ok: boolean
  wallet: string
  capital: number
  mode: string
  execution_enabled: boolean
  reason: string
  scorecard: {
    status: string
    label?: string | null
    confidence?: string | null
    estimated_value?: number | null
    roi_pct?: number | null
    suspect_rows: number
    blocked_rows: number
    providers_ok: number
    providers_total: number
  }
  allocation: Array<{ asset: string; chain: string; max_weight_pct: number; evidence_events: number; observed_usd: number }>
  guards: string[]
  requirements: string[]
}

type CoordinationSurface = {
  ok?: boolean
  provider?: string
  wallet?: string
  chain?: string | null
  cex_flow_present?: boolean
  cex_flow_hint_only?: boolean
  funder_graph_present?: boolean
  shared_funder_count?: number
  gas_distributor_count?: number
  fresh_wallet_surface?: boolean
  coordination_hints?: Array<{ type?: string; [key: string]: unknown }>
  missing_proofs?: string[]
  source_policy?: string
}

type RpcTxEnrichment = {
  ok?: boolean
  tx_candidates?: number
  tx_enriched?: number
  token_transfers_found?: number
  missing_proofs?: string[]
  source_policy?: string
}

type WalletCopyBacktest = {
  ok: boolean
  wallet: string
  mode: string
  capital: number
  current_value: number
  pnl: number
  roi_pct: number
  confidence_score: number
  verdict: string
  execution_enabled: boolean
  copied_trades: Array<{ asset: string; chain: string; allocation: number; estimated_cost: number; timestamp?: string | null; tx_hash?: string | null }>
  skipped: Array<{ reason: string; asset?: string; chain?: string; observed_usd?: number }>
  blockers: string[]
  source_trace?: {
    rpc_tx_enrichment?: RpcTxEnrichment
    coordination_surface?: CoordinationSurface
    [key: string]: unknown
  }
  coverage: {
    events_observed: number
    events_copied: number
    events_skipped: number
    assets_seen: number
    chains_seen: string[]
    providers_ok: number
    providers_total: number
  }
  assumptions: Record<string, unknown>
}

type WalletAutomationPlan = {
  ok: boolean
  wallet: string
  capital: number
  mode: string
  execution_enabled: boolean
  readiness_score: number
  decision: string
  blockers: string[]
  next_actions: string[]
  source_trace: {
    probe: string
    surface: string
    graph: string
    providers_ok: number
    providers_total: number
    rpc_events: number
    graph_edges: number
    freshness_policy: string
    latest_seen?: string | null
    rpc_source_rows: number
  }
  data_quality: {
    chain_count: number
    asset_count: number
    flow_confidence_score: number
    rpc_backbone_score: number
    source_freshness: string
    holder_confidence: string
    token_sellability: string
  }
  chain_coverage: Array<{ chain: string; events: number; amount_usd: number; assets: string[] }>
  token_risk_watchlist: Array<{
    asset: string
    chain: string
    events?: number
    observed_usd?: number
    risk_flag: string
    risk_score?: number
    block_trade?: boolean
    profit_integrity?: string
    missing_proofs?: string[]
    source_policy?: string
    copy_allowed?: boolean | null
  }>
  rpc_backbone: {
    ok: boolean
    wallet_label?: string | null
    primary_chain?: string | null
    tx_count?: number | null
    swap_count?: number | null
    volume?: number | null
    net_worth_usd?: number | null
    source_rows?: number | null
    traceable_rows?: number | null
    chain_rows: Array<{ chain: string; tx_count: number; native_value_usd: number; token_count: number; data_quality_score: number }>
    persisted_snapshot?: {
      ok: boolean
      updated: number
      skipped_fresh?: number
      refresh_after_hours?: number
      freshness_policy?: string
      source_policy: string
    } | null
  }
  scorecard: {
    status: string
    confidence: string
    estimated_value?: number | null
    roi_pct?: number | null
    untrusted_rows: number
    blocked_rows: number
  }
  investment_readiness?: {
    status: string
    verdict: string
    readiness_score: number
    client_investment_enabled: boolean
    execution_enabled: boolean
    copy_trade_enabled: boolean
    profit_guarantee_allowed: boolean
    trade_signal_allowed: boolean
    manual_review_allowed: boolean
    critical_blockers: string[]
    missing_proofs: string[]
    next_safe_action: string
    source_policy: string
    required_gates: Record<string, boolean>
  }
  rails: {
    contract: string
    execution_gate: string
    private_key_required: boolean
    signature_required_for_analysis: boolean
    client_visible: boolean
    trusted_auto_execution: boolean
  }
}

type WalletOwnershipStatus = {
  ok: boolean
  address: string
  verified: boolean
  session_active?: boolean
  session_expires_at?: number | null
  expired?: boolean
  proof_age_seconds?: number | null
  expires_at?: number | null
  method?: string | null
  provider?: string | null
  network?: string | null
  verified_at?: number | null
  recovery_available: boolean
  source: string
  execution_gate: string
}

type WalletSurface = {
  ok: boolean
  wallet: string
  summary: {
    events: number
    swaps: number
    transfers: number
    inflow_usd: number
    outflow_usd: number
    swap_usd: number
    net_transfer_usd: number
    counterparties: number
    venues: number
  }
  counterparties: Array<{
    label: string
    address?: string | null
    kind: string
    chains: string[]
    assets: string[]
    events: number
    inflow_usd: number
    outflow_usd: number
    swap_usd: number
    net_usd: number
    latest_tx?: string | null
    latest_chain?: string | null
    last_seen?: string | null
    dex?: string | null
  }>
  venues: Array<{
    name: string
    events: number
    amount_usd: number
    chains: string[]
    assets: string[]
    latest_tx?: string | null
    latest_chain?: string | null
    last_seen?: string | null
  }>
  activity: Array<{
    event_type: string
    direction: string
    chain?: string | null
    asset?: string | null
    amount_usd: number
    timestamp?: string | null
    tx_hash?: string | null
    counterparty: {
      label?: string | null
      address?: string | null
      kind?: string | null
    }
    dex?: string | null
  }>
  latency_ms?: number
  note?: string
}

type WalletGraph = {
  ok: boolean
  wallet: string
  summary: {
    nodes: number
    edges: number
    direct_counterparties: number
    venues: number
    assets: number
    evidence_grade: string
  }
  nodes: Array<{
    id: string
    label: string
    kind: string
    address?: string | null
    chain?: string | null
    score?: number
  }>
  edges: Array<{
    source: string
    target: string
    kind: string
    weight: number
    amount_usd: number
    events: number
    confidence: number
    latest_tx?: string | null
    latest_chain?: string | null
    direction?: string | null
  }>
  note?: string
}

type WalletCandidate = {
  wallet: string
  label?: string | null
  score: number
  events: number
  swaps: number
  chains: string[]
  assets: string[]
  flow_usd: number
  first_interactions: number
  last_seen?: string | null
  latest_asset?: string | null
  latest_tx?: string | null
  latest_chain?: string | null
  copy_status: string
}

type WalletDiscoveryResponse = {
  ok: boolean
  count: number
  candidates: WalletCandidate[]
  feed: {
    events?: number
    min_usd?: number | null
    new_trades?: boolean | null
    tx_types?: string | null
    chains?: string | null
    dedupe?: { input_count?: number; unique_count?: number; duplicate_count?: number }
  }
  latency_ms?: number
  note?: string
}

type RpcStatus = {
  ok: boolean
  chains: Record<string, {
    enabled: boolean
    env: string
    tokens_tracked: number
  }>
  db_path: string
  auto_ingest_running: boolean
}

type ArkhamCoverage = {
  ok: boolean
  generated_at: string
  coverage: {
    on_chain_value_attributed_usd: number
    asset_flow_tracked_usd: number
    asset_flow_tracked_rows: number
    addresses_labelled: number
    entities_labelled: number
    assets_tracked: number
    chains_tracked: number
    holder_rows_cached: number
    holder_tokens_cached: number
    normalized_snapshots: number
  }
  data_map?: {
    chain_coverage_matrix?: Array<{
      chain: string
      family: string
      arkham_reference_coverage_pct?: number
      local_tier: "none" | "seed" | "partial" | "useful" | "strong"
      metrics: {
        labelled_addresses: number
        assets_tracked: number
        holder_rows: number
        transfer_rows: number
        transfer_value_usd: number
        rpc_blocks: number
        rpc_transactions: number
        rpc_swaps: number
        rpc_wallets: number
        rpc_configured: boolean
        rpc_ingestion_enabled: boolean
      }
      gaps: string[]
      next_step: string
    }>
    rpc_ingestion_gate?: {
      decision: string
      reason: string
      safe_now: string[]
      not_safe_yet: string[]
    }
    acquisition_plan?: {
      reference: {
        addresses_labelled: number
        source: string
      }
      strategy: string[]
      priority_queue: Array<{
        chain: string
        family: string
        priority_score: number
        local_tier: string
        current: {
          labelled_addresses: number
          holder_rows: number
          rpc_transactions: number
          transfer_rows: number
          assets_tracked: number
        }
        next_sources: string[]
        safe_actions: string[]
        do_not_do_yet: string[]
      }>
    }
  }
  top_entities_by_value: Array<{ entity: string; value_usd: number; wallet_rows: number }>
  top_holder_tokens: Array<{ token: string; holders_cached: number }>
  limitations: string[]
}

type EntityCoverage = {
  ok: boolean
  entity?: string | null
  min_confidence: string
  total_entities: number
  rows: Array<{
    entity: string
    labelled_wallets: number
    labelled_by_chain?: Record<string, number>
    confidence_breakdown?: Record<string, number>
    sample_labels?: Array<{ chain: string; address: string; label: string; confidence: string }>
    rpc_by_chain?: Record<string, {
      wallets: number
      native_balance: number
      tx_count: number
      last_observed_at: number
      native_value_usd: number
      contracts: number
      fresh_wallets: number
      high_activity_wallets: number
      avg_quality_score: number
    }>
    rpc_wallets: number
    rpc_tx_count: number
    rpc_native_value_usd: number
    contract_wallets: number
    fresh_wallets: number
    high_activity_wallets: number
    avg_quality_score: number
    rpc_coverage_pct: number
  }>
  source_policy: string
}

type EntityGapReport = {
  ok: boolean
  min_confidence: string
  rows: Array<{
    rank: number
    entity: string
    status: "missing_labels" | "needs_rpc_enrichment" | "partial_rpc" | "weak_quality" | "usable_seed" | string
    priority_score: number
    labelled_wallets: number
    rpc_wallets: number
    rpc_coverage_pct: number
    avg_quality_score: number
    labelled_by_chain?: Record<string, number>
    next_action: string
  }>
  source_policy: string
}

type EntityChainGapReport = {
  ok: boolean
  min_confidence: string
  rows: Array<{
    entity: string
    chain: string
    status_before: string
    labelled_wallets: number
    rpc_wallets: number
    missing_wallets: number
    rpc_coverage_pct: number
    priority_score: number
    next_action: string
  }>
  source_policy: string
}

type EntityChainGapVerification = {
  ok: boolean
  min_confidence: string
  stale_after_hours: number
  summary: {
    rows_reviewed: number
    safe_to_enrich: number
    needs_audit_first: number
    blocked: number
  }
  rows: Array<{
    entity: string
    chain: string
    labelled_wallets: number
    rpc_wallets: number
    missing_wallets: number
    rpc_coverage_pct: number
    priority_score: number
    verification_status: string
    blockers: string[]
    traceability_pct: number
    stale_rows: number
    low_quality_rows: number
    missing_source_attribution: number
    avg_quality: number
    recommended_action: string
  }>
  source_policy: string
}

type DataReadiness = {
  ok: boolean
  entity?: string | null
  min_confidence: string
  status: string
  readiness_score: number
  client_safe: boolean
  trusted_auto_promotion: boolean
  summary: {
    coverage_rows: number
    labelled_wallets: number
    strict_labelled_wallets: number
    legacy_or_unverified_labelled_wallets: number
    rpc_wallets: number
    missing_rpc_wallets: number
    strict_label_pct: number
    rpc_coverage_pct: number
    wallet_chain_state_rows: number
    wallet_chain_state_by_chain: Record<string, number>
    wallet_traceability_pct: number
    wallet_stale_rows_24h: number
    wallet_low_quality_rows: number
    wallet_missing_source_attribution: number
    wallet_avg_quality: number
    ledger_labels: number
    ledger_candidates: number
    candidate_open?: number
    candidate_duplicate_groups?: number
    candidate_ambiguous_addresses?: number
    candidate_single_seen_pct?: number
    candidate_missing_source_url?: number
    swap_total_rows?: number
    swap_exact_token_rows?: number
    swap_history_days?: number
    token_transfer_rows?: number
    token_transfer_distinct_tokens?: number
    token_transfer_from_wallets?: number
    token_transfer_to_wallets?: number
    token_transfer_history_days?: number
  }
  token_transfer_coverage?: {
    summary?: {
      token_transfer_rows?: number
      distinct_tokens?: number
      from_wallets?: number
      to_wallets?: number
      chains?: number
      history_days?: number
    }
    blockers?: string[]
    source_policy?: string
  }
  wallet_state_audit?: {
    stale_after_hours: number
    traceability_pct: number
    stale_rows: number
    low_quality_rows: number
    missing_source_attribution: number
    missing_label_sources: number
    by_chain: Array<{ chain: string; wallets: number; missing_source_attribution: number; missing_label_sources: number; stale_rows: number; avg_quality: number }>
    by_rpc_source: Array<{ rpc_source: string; wallets: number }>
  }
  blockers: string[]
  next_actions: string[]
  automation_rails: Record<string, unknown>
  label_candidate_quality?: {
    totals?: Record<string, number>
    risk_summary?: Record<string, number>
  }
  client_signal_trust?: {
    score: number
    decision: string
    execution_enabled: boolean
    client_safe_label: string
    reasons: string[]
    blockers: string[]
    next_action: string
  }
  evidence_lanes?: {
    token_transfer_coverage?: {
      summary?: {
        token_transfer_rows?: number
        distinct_tokens?: number
        from_wallets?: number
        to_wallets?: number
        chains?: number
        history_days?: number
      }
      by_chain?: Array<{
        chain?: string
        token_transfer_rows?: number
        distinct_tokens?: number
        from_wallets?: number
        to_wallets?: number
        history_days?: number
      }>
      blockers?: string[]
      source_policy?: string
    }
  }
  source_policy: string
}

type AdaptiveManipulationCaseFile = {
  ok: boolean
  summary: {
    case_files: number
    client_ready_cases: number
    high_false_positive_risk_funders: number
    gas_fanout_funders?: number
    pre_event_cex_deposit_funders?: number
    only_unrealistic_policy_profitable: boolean
    client_execution_enabled: boolean
    copy_trade_enabled: boolean
  }
  rows: Array<{
    chain: string
    token: string
    event_timestamp?: number | null
    verdict: string
    client_ready: boolean
    client_alert_allowed: boolean
    copy_trade_allowed: boolean
    execution_enabled: boolean
    strategy: {
      only_unrealistic_policy_profitable: boolean
      strategies: Array<{
        policy: string
        exit_after_swaps: number
        return_pct?: number
        pnl_usd?: number
        client_candidate?: boolean
      }>
    }
    wallet_profiles: Array<{
      wallet: string
      is_fresh_wallet?: boolean
      pre_event_buy_usd?: number
      post_event_sell_usd?: number
      risk_flags?: string[]
    }>
    clusters: Array<{
      cluster_type: string
      wallet_count?: number
      fresh_wallets?: number
      total_pre_event_buy_usd?: number
      risk_flags?: string[]
    }>
    funder_graph: Array<{
      shared_funder: string
      classification: string
      false_positive_risk: string
      funding_edge_count: number
      upstream_funding_edge_count?: number
      upstream_sources?: Array<{ address: string; classification: string }>
      gas_fanout_profile?: {
        detected?: boolean
        wallet_count?: number
        edge_count?: number
        total_native_value?: number
        span_minutes?: number | null
        proof_status?: string
      }
      cex_deposit_profile?: {
        detected?: boolean
        deposit_count?: number
        depositing_wallets?: string[]
        target_entities?: string[]
        total_native_value?: number
        proof_status?: string
      }
      risk_flags?: string[]
    }>
    blockers: string[]
    plain_english: string
  }>
  component_summaries: Record<string, Record<string, unknown>>
  blockers: string[]
  next_actions: string[]
  source_policy: string
}

type ReadinessRequirement = {
  id: string
  label_fr: string
  direction: "minimum" | "maximum"
  current: number
  target: number
  missing?: number
  excess?: number
  unit: string
  passed: boolean
  recommended_action_id: string
}

type ReadinessAction = {
  requirement_id: string
  requirement_label_fr: string
  gap: number
  gap_unit: string
  action_id: string
  priority: number
  title_fr: string
  reason: string
  method: string
  endpoint: string
  admin_required: boolean
  dry_run: boolean
  source_policy: string
  execution_enabled: boolean
  client_safe: boolean
  client_visible: boolean
  write_guarded: boolean
  action: {
    id: string
    priority: number
    title_fr: string
    reason: string
    method: string
    endpoint: string
    admin_required: boolean
    confirm_required?: string | null
    dry_run_default?: boolean | null
    dry_run?: boolean
    env_required?: string | null
    source_policy?: string
    execution_enabled: boolean
    client_safe: boolean
  }
}

type CexTokenDepositEvidenceLane = {
  summary?: {
    deposits?: number
    depositing_wallets?: number
    source_backed_depositors?: number
    fresh_like_depositors?: number
    missing_state_depositors?: number
    target_exchange_wallets?: number
    source_backed_target_wallets?: number
    tokens?: number
    chains?: number
    funding_edges?: number
    funded_depositors?: number
    fresh_like_depositors_with_funding?: number
    fresh_like_depositors_without_funding?: number
    source_backed_funders?: number
    exchange_like_funders?: number
    unknown_funders?: number
    deposit_span_minutes?: number
    max_deposits_1h?: number
    max_deposits_6h?: number
    max_deposits_24h?: number
    swap_rows_around_deposits?: number
    swap_rows_after_24h?: number
    swap_tokens_with_local_swaps?: number
    swap_tokens_without_local_swaps?: number
    price_proxy_tokens?: number
    price_proxy_before_after_tokens?: number
    price_proxy_max_change_pct?: number
    holder_flow_tokens?: number
    holder_flow_high_cex_share_tokens?: number
    holder_flow_high_fresh_like_share_tokens?: number
    holder_flow_high_top_holder_concentration_tokens?: number
    holder_flow_high_supply_share_tokens?: number
    holder_flow_max_cex_share_pct?: number
    holder_flow_max_top3_depositor_share_pct?: number
    holder_flow_max_fresh_like_share_pct?: number
    holder_flow_max_top_holder_share_pct?: number
    holder_flow_max_top10_holder_share_pct?: number
    holder_flow_max_supply_share_pct?: number
    holder_supply_snapshot_tokens?: number
    holder_snapshot_refresh_needed?: number
    coordination_score?: number
    coordination_tier?: string
    coordination_factors?: string[]
  }
  aggregates?: {
    by_target_entity?: Array<{
      key: string
      deposits: number
      depositing_wallets: number
      source_backed_depositors: number
      fresh_like_depositors: number
      missing_state_depositors: number
      target_wallets: number
      source_backed_target_wallets: number
      tokens: number
      chains: number
      resolved_value_total: number
      resolved_amount_rows: number
      raw_amount_rows: number
    }>
    by_token?: Array<{
      key: string
      deposits: number
      depositing_wallets: number
      target_wallets: number
      source_backed_target_wallets: number
      tokens: number
      chains: number
      resolved_value_total: number
      resolved_amount_rows: number
      raw_amount_rows: number
    }>
    by_chain?: Array<{
      key: string
      deposits: number
      depositing_wallets: number
      target_wallets: number
      source_backed_target_wallets: number
      tokens: number
      chains: number
      resolved_value_total: number
      resolved_amount_rows: number
      raw_amount_rows: number
    }>
  }
  rows?: Array<{
    chain?: string
    tx_hash?: string
    timestamp?: number | null
    token?: string
    token_symbol?: string | null
    token_decimals?: number | null
    value_raw?: string | null
    value_display?: number | null
    value_display_source?: string
    from_addr?: string
    to_addr?: string
    depositor_label?: string | null
    depositor_entity?: string | null
    depositor_tx_count?: number | null
    depositor_has_wallet_state?: boolean
    depositor_source_backed?: boolean
    depositor_known?: boolean
    depositor_fresh_like?: boolean
    target_entity?: string | null
    target_label?: string | null
    target_source_backed?: boolean
    proof_status?: string
  }>
  funding_graph?: {
    summary?: {
      funding_edges?: number
      funded_depositors?: number
      fresh_like_depositors_with_funding?: number
      fresh_like_depositors_without_funding?: number
      source_backed_funders?: number
      exchange_like_funders?: number
      unknown_funders?: number
      shared_funders?: number
      shared_unknown_funders?: number
      shared_exchange_like_funders?: number
      shared_source_backed_funders?: number
      coordination_score?: number
      coordination_tier?: string
      coordination_factors?: string[]
    }
    edges?: Array<{
      chain?: string
      tx_hash?: string
      timestamp?: number | null
      from_addr?: string
      to_depositor?: string
      value_native?: number
      funder_label?: string | null
      funder_entity?: string | null
      funder_address_kind?: string | null
      funder_source_backed?: boolean
      funder_exchange_like?: boolean
      funder_known?: boolean
      proof_status?: string
    }>
    shared_funders?: Array<{
      funder?: string
      funded_depositors?: number
      fresh_like_depositors?: number
      total_native_value?: number
      source_backed?: boolean
      exchange_like?: boolean
      unknown?: boolean
      proof_status?: string
    }>
    source_policy?: string
  }
  temporal_profile?: {
    first_deposit_timestamp?: number | null
    last_deposit_timestamp?: number | null
    deposit_span_minutes?: number
    max_deposits_1h?: number
    max_deposits_6h?: number
    max_deposits_24h?: number
    clustered_1h?: boolean
    clustered_6h?: boolean
    clustered_24h?: boolean
    source_policy?: string
  }
  swap_corroboration?: {
    summary?: {
      swap_rows_around_deposits?: number
      swap_rows_before_24h?: number
      swap_rows_during_cluster?: number
      swap_rows_after_24h?: number
      swap_wallets?: number
      swap_dexes?: number
      tokens_with_local_swaps?: number
      tokens_without_local_swaps?: number
      usd_before_24h?: number
      usd_during_cluster?: number
      usd_after_24h?: number
    }
    blockers?: string[]
    source_policy?: string
  }
  price_proxy_profile?: {
    summary?: {
      tokens_with_price_proxy?: number
      tokens_with_before_after_price_proxy?: number
      max_before_after_change_pct?: number
      tokens_missing_price_proxy?: number
    }
    rows?: Array<{
      token?: string
      before_24h_median_price?: number | null
      during_cluster_median_price?: number | null
      after_24h_median_price?: number | null
      before_after_change_pct?: number | null
      before_observations?: number
      during_observations?: number
      after_observations?: number
    }>
    blockers?: string[]
    source_policy?: string
  }
  holder_flow_profile?: {
    summary?: {
      tokens_profiled?: number
      tokens_with_observed_transfer_flow?: number
      holder_supply_snapshot_tokens?: number
      high_cex_flow_share_tokens?: number
      high_top_depositor_share_tokens?: number
      high_fresh_like_value_share_tokens?: number
      high_top_holder_concentration_tokens?: number
      high_cex_deposit_supply_share_tokens?: number
      max_cex_deposit_share_of_observed_flow_pct?: number
      max_top_depositor_cex_share_pct?: number
      max_top3_depositor_cex_share_pct?: number
      max_fresh_like_cex_value_share_pct?: number
      max_top_holder_share_pct?: number
      max_top10_holder_share_pct?: number
      max_cex_deposit_supply_share_pct?: number
    }
    rows?: Array<{
      chain?: string
      token?: string
      token_symbol?: string | null
      local_transfer_rows?: number
      local_from_wallets?: number
      local_to_wallets?: number
      cex_deposit_rows?: number
      cex_depositors?: number
      fresh_like_depositors?: number
      observed_value_display?: number | null
      cex_deposit_value_display?: number | null
      cex_deposit_share_of_observed_flow_pct?: number | null
      top_depositor_cex_share_pct?: number | null
      top3_depositor_cex_share_pct?: number | null
      fresh_like_cex_value_share_pct?: number | null
      holder_supply_snapshot_available?: boolean
      holder_rows?: number
      top_holder_share_pct?: number | null
      top10_holder_share_pct?: number | null
      supply_estimate_display?: number | null
      supply_estimate_source?: string | null
      cex_deposit_supply_share_pct?: number | null
      flags?: string[]
    }>
    blockers?: string[]
    source_policy?: string
  }
  holder_snapshot_refresh_queue?: Array<{
    chain?: string
    token?: string
    token_symbol?: string | null
    reason?: string
    priority?: number
  }>
  blockers?: string[]
  source_policy?: string
}

type ManipulationResearchVerdict = {
  version?: string
  score?: number
  tier?: string
  confidence_score?: number
  confidence_tier?: string
  direction?: string
  evidence?: Array<{ key: string; points?: number; severity?: string; label_fr?: string; detail?: string }>
  missing_evidence?: Array<{ key: string; label_fr?: string; why_it_matters_fr?: string }>
  client_action?: string
  client_execution_enabled?: boolean
  copy_trade_enabled?: boolean
  profit_guarantee_allowed?: boolean
  plain_summary_fr?: string
  source_policy?: string
}

type HolderFlowEvidenceVerdict = {
  state?: string
  confidence?: string
  basis?: {
    source?: string
    tokens_profiled?: number
    holder_snapshot_tokens?: number
    holder_snapshot_available?: boolean
  }
  scores?: {
    max_cex_share_pct?: number
    max_fresh_like_pct?: number
    max_top_holder_pct?: number
    max_top10_holder_pct?: number
    max_supply_share_pct?: number
  }
  risk_flags?: string[]
  recommended_action_id?: string
  client_execution_enabled?: boolean
  copy_trade_enabled?: boolean
  profit_guarantee_allowed?: boolean
  plain_summary_fr?: string
  source_policy?: string
}

type ManipulationReadiness = {
  ok: boolean
  status: string
  signal_readiness_score: number
  manipulation_research_verdict?: ManipulationResearchVerdict
  evidence_verdicts?: {
    cex_token_holder_flow?: HolderFlowEvidenceVerdict
  }
  execution_enabled: boolean
  client_profit_claim_allowed: boolean
  safe_for: string[]
  not_safe_for: string[]
  blockers: string[]
  next_actions: string[]
  readiness_contract?: {
    version: string
    requirements: ReadinessRequirement[]
    failed_requirements: ReadinessRequirement[]
    failed_count: number
    passed_count: number
    total_count: number
    execution_enabled: boolean
    client_copy_trading_allowed: boolean
    profit_guarantee_allowed: boolean
    automation_scope: string
    plain_summary_fr: string
    source_policy: string
    manipulation_research_verdict?: ManipulationResearchVerdict
    evidence_verdicts?: {
      cex_token_holder_flow?: HolderFlowEvidenceVerdict
    }
    next_safe_actions?: ReadinessAction[]
    client_visible_actions?: ReadinessAction[]
    automation_data_gaps?: Array<{
      id: string
      label_fr: string
      category: string
      severity: string
      current: number
      target: number
      gap: number
      unit: string
      direction: string
      data_source: string
      why_it_matters_fr: string
      next_action_id: string
      next_action?: ReadinessAction | null
      client_automation_blocker: boolean
    }>
    missing_data_summary?: {
      total_gaps: number
      critical_gaps: number
      high_gaps: number
      medium_gaps: number
      top_categories: string[]
      client_automation_ready: boolean
    }
    gap_closure_plan?: {
      mode: string
      client_execution_enabled: boolean
      copy_trading_enabled: boolean
      profit_guarantee_allowed: boolean
      source_policy: string
      next_step?: {
        phase: string
        phase_order: number
        phase_title_fr: string
        gap_id: string
        gap_label_fr: string
        severity: string
        category: string
        gap: number
        unit: string
        data_source: string
        why_it_matters_fr: string
        action_id: string
        method: string
        endpoint: string
        admin_required: boolean
        dry_run: boolean
        client_visible: boolean
        execution_enabled: boolean
        client_safe: boolean
        status: string
      } | null
      steps: Array<{
        phase: string
        phase_order: number
        phase_title_fr: string
        gap_id: string
        gap_label_fr: string
        severity: string
        category: string
        gap: number
        unit: string
        data_source: string
        why_it_matters_fr: string
        action_id: string
        method: string
        endpoint: string
        admin_required: boolean
        dry_run: boolean
        client_visible: boolean
        execution_enabled: boolean
        client_safe: boolean
        status: string
      }>
    }
    automation_decision?: {
      status: string
      client_mode: string
      admin_mode: string
      client_can_see: string[]
      client_cannot_do: string[]
      first_client_diagnostic?: ReadinessAction | null
      first_admin_action?: ReadinessAction | null
      required_before_client_automation: string[]
      plain_summary_fr: string
    }
  }
  evidence_lanes?: {
    token_transfer_coverage?: {
      summary?: {
        token_transfer_rows?: number
        distinct_tokens?: number
        from_wallets?: number
        to_wallets?: number
        chains?: number
        history_days?: number
      }
      by_chain?: Array<{
        chain?: string
        token_transfer_rows?: number
        distinct_tokens?: number
        from_wallets?: number
        to_wallets?: number
        history_days?: number
      }>
      blockers?: string[]
      source_policy?: string
    }
  }
  source_policy: string
}

type DataJobs = {
  ok: boolean
  rows: Array<{
    id: number
    job_type: string
    status: string
    started_at: number
    finished_at?: number | null
    params: Record<string, unknown>
    result: {
      mode?: string
      rows_observed?: number
      rows_inserted?: number
      files_scanned?: number
      acquired?: Array<{ entity: string; wallets?: number; transfers?: number; counterparties?: number }>
      failed?: Array<{ entity: string; error?: string }>
      candidate_staging?: {
        rows_observed?: number
        candidates_inserted?: number
        candidates_merged?: number
        files_scanned?: number
      }
      entities_attempted?: number
      pairs_attempted?: number
      candidate_ids?: number[]
      candidates_selected?: number
      evidence_bundles_written?: number
      verified_source_ready?: number
      trusted_labels_changed?: boolean
      queue?: {
        rows_reviewed?: number
        manual_review_filtered?: number
        include_manual_review?: boolean
      }
      blocked_by_reason?: Array<{ reason: string; count: number }>
      results?: Array<{
        entity: string
        chain?: string
        wallets_updated?: number
        seeds_loaded?: number
        rpc_wallets_before?: number
        missing_wallets_before?: number
        rpc_wallets_after?: number
        missing_wallets_after?: number
        net_rpc_wallets_added?: number
        rpc_coverage_pct_after?: number
        traceable_wallets_before?: number
        traceable_wallets_after?: number
        missing_source_attribution_before?: number
        missing_source_attribution_after?: number
        low_quality_rows_before?: number
        low_quality_rows_after?: number
        errors?: Array<unknown>
      }>
    }
    error?: string | null
  }>
}

type AlphaUsageStats = {
  ok: boolean
  events: number
  actions: Record<string, number>
  wallets: number
  recent: Array<{
    ts: number
    page: string
    action: string
    wallet_short?: string | null
    connected_wallets?: number
    status?: string
  }>
}

type WalletStateAudit = {
  ok: boolean
  total_wallets: number
  traceable_wallets: number
  traceability_pct: number
  missing_rpc_source: number
  missing_label: number
  missing_entity: number
  missing_label_sources: number
  missing_source_attribution: number
  stale_rows: number
  low_quality_rows: number
  avg_quality: number
  refresh_targets: Array<{
    entity: string
    chain: string
    wallets: number
    missing_source_attribution: number
    missing_label_sources: number
    stale_rows: number
    low_quality_rows: number
    avg_quality: number
    recommended_action: string
  }>
  source_policy: string
}

type WalletQualityAudit = {
  ok: boolean
  total_wallets: number
  quality_distribution: {
    high: number
    medium: number
    low: number
  }
  low_quality_pct: number
  avg_quality: number
  by_entity_chain: Array<{
    entity: string
    chain: string
    wallets: number
    high_quality: number
    medium_quality: number
    low_quality: number
    avg_quality: number
    recommended_action: string
  }>
  by_chain: Array<{
    chain: string
    wallets: number
    high_quality: number
    medium_quality: number
    low_quality: number
    avg_quality: number
  }>
  by_rpc_source: Array<{
    rpc_source: string
    wallets: number
    low_quality: number
    avg_quality: number
  }>
  weakest_wallets: Array<{
    chain: string
    address: string
    label?: string | null
    entity?: string | null
    rpc_source?: string | null
    data_quality_score: number
    risk_flags: string[]
    traceable: boolean
    observed_at: number
  }>
  source_policy: string
}

type AutoEnrichStatus = {
  ok: boolean
  running: boolean
  locked: boolean
  config: {
    interval_seconds?: number
    limit_per_entity?: number
    max_entities?: number
    min_confidence?: string
    include_tokens?: boolean
  }
  automation_rails?: Record<string, unknown>
  source_policy: string
}

type CandidatePromotionReview = {
  ok: boolean
  min_score: number
  rows_reviewed: number
  eligible: number
  rows: Array<{
    id: number
    chain: string
    address: string
    label: string
    entity: string
    wallet_type?: string
    source: string
    source_url?: string
    seen_count: number
    decision: "promote_ready" | "hold" | string
    promotion: {
      score: number
      eligible: boolean
      confidence: string
      reasons: string[]
      blockers: string[]
    }
  }>
  source_policy: string
}

type StrictCandidatePromotionReview = {
  ok: boolean
  source_policy: string
  rows_reviewed: number
  strict_ready: number
  blocked: number
  blocked_by_reason: Array<{ reason: string; count: number }>
  rows: Array<CandidatePromotionReview["rows"][number] & {
    decision: "strict_ready" | "blocked" | string
    strict_promotion: CandidatePromotionReview["rows"][number]["promotion"] & { strict_ready: boolean }
  }>
  recommendation: string
}

type CandidateAutomationPlan = {
  ok: boolean
  rows_reviewed: number
  auto_safe_later: number
  admin_review: number
  blocked: number
  lanes: {
    auto_safe_later: CandidatePromotionReview["rows"]
    admin_review: Array<CandidatePromotionReview["rows"][number] & { automation_blockers: string[]; automation_decision: string }>
    blocked: Array<CandidatePromotionReview["rows"][number] & { automation_blockers: string[]; automation_decision: string }>
  }
  source_policy: string
}

type LabelAcquisitionPlan = {
  ok: boolean
  target_floor: number
  entities_reviewed: number
  recommendation: string
  source_policy: string
  rows: Array<{
    entity: string
    target_trusted_labels: number
    trusted_labels: number
    high_confidence_labels: number
    medium_confidence_labels: number
    open_candidates: number
    strict_ready_candidates: number
    blocked_candidates: number
    candidate_seen_count_total: number
    gap_to_target: number
    priority_score: number
    recommended_action: string
    top_candidate_ids: number[]
    top_blockers: Array<{ blocker: string; count: number }>
    suggested_sources: string[]
  }>
}

type CandidateQualityReport = {
  ok: boolean
  source_policy: string
  totals: {
    all_candidates: number
    open_candidates: number
    promoted_candidates: number
    missing_source_url: number
    single_seen_candidates: number
  }
  risk_summary: {
    duplicate_groups: number
    ambiguous_addresses: number
    stale_single_seen_sample: number
    single_seen_pct: number
  }
  duplicate_groups: Array<{
    chain: string
    address: string
    entity: string
    label: string
    source_url: string
    rows: number
    total_seen: number
    candidate_ids: number[]
  }>
  ambiguous_addresses: Array<{
    chain: string
    address: string
    entities: number
    labels: number
    rows: number
    candidate_ids: number[]
  }>
  stale_candidates: Array<{
    id: number
    chain: string
    address: string
    label?: string | null
    entity?: string | null
    source: string
    source_url?: string | null
    first_seen_at: string
    last_seen_at: string
    seen_count: number
  }>
  recommendation: string
}

type CandidateCorroborationQueue = {
  ok: boolean
  source_policy: string
  include_manual_review: boolean
  manual_review_filtered: number
  rows_reviewed: number
  blocked_by_reason: Array<{ reason: string; count: number }>
  rows: Array<{
    id: number
    chain: string
    address: string
    label?: string | null
    entity?: string | null
    wallet_type?: string | null
    confidence?: string | null
    source?: string | null
    source_url?: string | null
    seen_count: number
    evidence_bundles: number
    last_evidence_at?: number | null
    max_evidence_score: number
    promotion_blockers: string[]
    requires_manual_review: boolean
    priority_score: number
    recommended_action: string
  }>
  recommendation: string
}

type CandidateEvidenceScores = {
  ok: boolean
  source_policy: string
  limit: number
  rows_reviewed: number
  rows: Array<{
    id: number
    chain: string
    address: string
    label?: string | null
    entity?: string | null
    seen_count: number
    historical_evidence_score: number
    max_bundle_score: number
    avg_bundle_score: number
    evidence_bundles: number
    evidence_items: number
    unique_sources: string[]
    severe_blockers: string[]
    decision: "strict_review_candidate" | "manual_review_required" | "needs_more_evidence" | "hold" | string
    blockers: Array<{ reason: string; count: number }>
  }>
  recommendation: string
}

type CandidatePromotionResult = {
  ok: boolean
  dry_run: boolean
  requested: number
  reviewed: number
  promoted: number
  rows: Array<{
    id: number
    chain: string
    address: string
    label?: string | null
    entity?: string | null
    seen_count: number
    status: "would_promote" | "promoted" | "blocked" | string
    promotion: {
      score: number
      confidence: string
      eligible: boolean
      strict_ready?: boolean
      reasons: string[]
      blockers: string[]
    }
  }>
  source_policy: string
}

const ARKHAM_REFERENCE_ADDRESSES = 3_100_000_000
const PRIORITY_ENTITIES = ["Binance", "OKX", "Coinbase", "Kraken", "KuCoin", "BlackRock", "PancakeSwap", "Uniswap", "Polymarket", "Bitget"]

function formatJobDuration(startedAt: number, finishedAt?: number | null) {
  if (!finishedAt) return "running"
  const seconds = Math.max(0, finishedAt - startedAt)
  if (seconds < 60) return `${seconds}s`
  return `${Math.round(seconds / 60)}m`
}

function summarizeDataJob(job: DataJobs["rows"][number]) {
  if (job.error) return job.error
  if (job.job_type === "label_ledger_build") {
    return `${job.result?.rows_observed ?? 0} rows / +${job.result?.rows_inserted ?? 0} trusted`
  }
  if (job.job_type === "label_source_acquisition") {
    const acquired = job.result?.acquired?.length ?? 0
    const failed = job.result?.failed?.length ?? 0
    const staged = job.result?.candidate_staging?.candidates_inserted ?? 0
    const observed = job.result?.candidate_staging?.rows_observed ?? 0
    return `${acquired} sources / +${staged} candidates / ${observed} observed / ${failed} failed`
  }
  if (job.job_type === "label_candidate_corroboration") {
    const selected = job.result?.candidates_selected ?? job.result?.candidate_ids?.length ?? 0
    const bundles = job.result?.evidence_bundles_written ?? 0
    const ready = job.result?.verified_source_ready ?? 0
    const changed = job.result?.trusted_labels_changed ? "changed" : "trusted unchanged"
    return `${selected} candidates / +${bundles} evidence / ${ready} ready / ${changed}`
  }
  const rows = job.result?.results || []
  if (rows.length) {
    const updated = rows.reduce((sum, row) => sum + Number(row.wallets_updated || 0), 0)
    const netAdded = rows.reduce((sum, row) => sum + Number(row.net_rpc_wallets_added ?? row.wallets_updated ?? 0), 0)
    const seeds = rows.reduce((sum, row) => sum + Number(row.seeds_loaded || 0), 0)
    const errors = rows.reduce((sum, row) => sum + ((row.errors || []).length), 0)
    const attempted = job.result?.pairs_attempted ?? job.result?.entities_attempted ?? rows.length
    const unit = job.result?.pairs_attempted != null ? "pairs" : "entities"
    if (job.job_type === "rpc_wallet_state_audit_refresh") {
      const traceableAfter = rows.reduce((sum, row) => sum + Number(row.traceable_wallets_after || 0), 0)
      const missingAfter = rows.reduce((sum, row) => sum + Number(row.missing_source_attribution_after || 0), 0)
      const lowQualityAfter = rows.reduce((sum, row) => sum + Number(row.low_quality_rows_after || 0), 0)
      return `${attempted} ${unit} / ${updated} refreshed / ${traceableAfter} traceable / ${missingAfter} missing attribution / ${lowQualityAfter} low quality / ${errors} errors`
    }
    return `${attempted} ${unit} / +${netAdded} net RPC / ${updated} attempts / ${seeds} seeds / ${errors} errors`
  }
  return job.status
}

function dataJobDetails(job: DataJobs["rows"][number]) {
  if (job.job_type === "label_source_acquisition") {
    const acquired = job.result?.acquired || []
    if (!acquired.length) return job.result?.failed?.[0]?.error || "no source acquired"
    return acquired
      .slice(0, 4)
      .map((row) => `${row.entity}: ${row.wallets ?? 0} wallets / ${row.transfers ?? 0} transfers`)
      .join(" / ")
  }
  if (job.job_type === "label_candidate_corroboration") {
    const ids = job.result?.candidate_ids || []
    const queue = job.result?.queue
    const blocked = job.result?.blocked_by_reason || []
    const blockedText = blocked.length ? ` / ${blocked.slice(0, 2).map((row) => `${row.reason}:${row.count}`).join(", ")}` : ""
    return `IDs ${ids.slice(0, 8).map((id) => `#${id}`).join(", ") || "none"} / queue ${queue?.rows_reviewed ?? 0}${blockedText}`
  }
  const rows = job.result?.results || []
  if (!rows.length) return job.result?.mode || job.job_type
  return rows
    .slice(0, 4)
    .map((row) => {
      const scope = row.chain ? `${row.entity}/${row.chain}` : row.entity
      if (job.job_type === "rpc_wallet_state_audit_refresh") {
        const before = row.traceable_wallets_before != null ? `${row.traceable_wallets_before}` : "?"
        const after = row.traceable_wallets_after != null ? `${row.traceable_wallets_after}` : "?"
        const missing = row.missing_source_attribution_after != null ? ` / ${row.missing_source_attribution_after} missing attribution` : ""
        const lowQuality = row.low_quality_rows_after != null ? ` / ${row.low_quality_rows_after} low quality` : ""
        return `${scope}: traceable ${before} -> ${after}${missing}${lowQuality}`
      }
      const before = row.rpc_wallets_before != null ? ` from ${row.rpc_wallets_before}` : ""
      const after = row.rpc_wallets_after != null ? ` -> ${row.rpc_wallets_after}` : ""
      const missing = row.missing_wallets_after != null ? ` (${row.missing_wallets_after} missing)` : ""
      const net = row.net_rpc_wallets_added ?? row.wallets_updated ?? 0
      return `${scope}: +${net} net${before}${after}${missing}`
    })
    .join(" / ")
}

const money = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) return "-"
  if (Math.abs(value) >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(1)}K`
  return `$${value.toFixed(2)}`
}

const largeNumber = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) return "-"
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return value.toLocaleString()
}

const coverageRatio = (current?: number | null, target = ARKHAM_REFERENCE_ADDRESSES) => {
  if (!current || current <= 0) return "0.000000%"
  return `${((current / target) * 100).toFixed(6)}%`
}

const pct = (value?: number | null) => {
  if (value == null || Number.isNaN(value)) return "-"
  return `${(value * 100).toFixed(value < 0.01 ? 2 : 1)}%`
}

const shortId = (value: string) => {
  if (!value) return "-"
  if (value.length <= 16) return value
  return `${value.slice(0, 8)}...${value.slice(-5)}`
}

const sourceLabel = (source: string) => (
  source === "polymarket" ? "Polymarket" : source === "kalshi" ? "Kalshi" : source
)

const getWithTimeout = async <T,>(endpoint: string, timeoutMs = 25000, init?: RequestInit) => {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await get<T>(endpoint, { ...init, signal: controller.signal })
  } finally {
    window.clearTimeout(timer)
  }
}

export default function AlphaLabPage() {
  const { t } = useLanguage()
  const [collectors, setCollectors] = useState<Collector[]>([])
  const [markets, setMarkets] = useState<Market[]>([])
  const [sourceStatus, setSourceStatus] = useState<MarketsResponse["source_status"]>([])
  const [source, setSource] = useState("all")
  const [query, setQuery] = useState("bitcoin")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedMarket, setSelectedMarket] = useState<Market | null>(null)
  const [simulation, setSimulation] = useState<SimulationResult | null>(null)
  const [risk, setRisk] = useState<RiskResult | null>(null)
  const [riskToken, setRiskToken] = useState("0x17205fab260a7a6383a81452cE6315A39370Db97")
  const [riskLiquidity, setRiskLiquidity] = useState("50000")
  const [riskSellTax, setRiskSellTax] = useState("8")
  const [riskMode, setRiskMode] = useState<"normal" | "danger">("normal")
  const [walletQuery, setWalletQuery] = useState("")
  const [walletIntel, setWalletIntel] = useState<WalletIntel | null>(null)
  const [walletProbe, setWalletProbe] = useState<WalletProbe | null>(null)
  const [walletCopyPlan, setWalletCopyPlan] = useState<WalletCopyPlan | null>(null)
  const [walletCopyBacktest, setWalletCopyBacktest] = useState<WalletCopyBacktest | null>(null)
  const [walletAutomationPlan, setWalletAutomationPlan] = useState<WalletAutomationPlan | null>(null)
  const [walletOwnership, setWalletOwnership] = useState<WalletOwnershipStatus | null>(null)
  const [walletSurface, setWalletSurface] = useState<WalletSurface | null>(null)
  const [walletGraph, setWalletGraph] = useState<WalletGraph | null>(null)
  const [walletLoading, setWalletLoading] = useState(false)
  const [clientAccounts, setClientAccounts] = useState<ConnectedAccount[]>([])
  const [clientAutoStatus, setClientAutoStatus] = useState("Connect a wallet on the dashboard to start Alpha Lab automation.")
  const autoAnalyzedWallets = useRef<Set<string>>(new Set())
  const [walletDiscovery, setWalletDiscovery] = useState<WalletDiscoveryResponse | null>(null)
  const [discoveryLoading, setDiscoveryLoading] = useState(false)
  const [discoveryMinUsd, setDiscoveryMinUsd] = useState("1000")
  const [discoveryToken, setDiscoveryToken] = useState("")
  const [discoveryChain, setDiscoveryChain] = useState("")
  const [rpcStatus, setRpcStatus] = useState<RpcStatus | null>(null)
  const [rpcStatusLabel, setRpcStatusLabel] = useState("checking")
  const [arkhamCoverage, setArkhamCoverage] = useState<ArkhamCoverage | null>(null)
  const [dataReadiness, setDataReadiness] = useState<DataReadiness | null>(null)
  const [manipulationReadiness, setManipulationReadiness] = useState<ManipulationReadiness | null>(null)
  const [manipulationCaseFile, setManipulationCaseFile] = useState<AdaptiveManipulationCaseFile | null>(null)
  const [entityCoverage, setEntityCoverage] = useState<EntityCoverage | null>(null)
  const [entityGaps, setEntityGaps] = useState<EntityGapReport | null>(null)
  const [entityChainGaps, setEntityChainGaps] = useState<EntityChainGapReport | null>(null)
  const [entityChainGapVerification, setEntityChainGapVerification] = useState<EntityChainGapVerification | null>(null)
  const [dataJobs, setDataJobs] = useState<DataJobs | null>(null)
  const [walletStateAudit, setWalletStateAudit] = useState<WalletStateAudit | null>(null)
  const [walletQualityAudit, setWalletQualityAudit] = useState<WalletQualityAudit | null>(null)
  const [autoEnrichStatus, setAutoEnrichStatus] = useState<AutoEnrichStatus | null>(null)
  const [candidateReview, setCandidateReview] = useState<CandidatePromotionReview | null>(null)
  const [strictCandidateReview, setStrictCandidateReview] = useState<StrictCandidatePromotionReview | null>(null)
  const [candidateAutomationPlan, setCandidateAutomationPlan] = useState<CandidateAutomationPlan | null>(null)
  const [labelAcquisitionPlan, setLabelAcquisitionPlan] = useState<LabelAcquisitionPlan | null>(null)
  const [candidateQualityReport, setCandidateQualityReport] = useState<CandidateQualityReport | null>(null)
  const [candidateCorroborationQueue, setCandidateCorroborationQueue] = useState<CandidateCorroborationQueue | null>(null)
  const [candidateEvidenceScores, setCandidateEvidenceScores] = useState<CandidateEvidenceScores | null>(null)
  const [candidatePromoteIds, setCandidatePromoteIds] = useState("")
  const [candidatePromotePreview, setCandidatePromotePreview] = useState<CandidatePromotionResult | null>(null)
  const [adminToken, setAdminToken] = useState("")
  const [adminJobStatus, setAdminJobStatus] = useState<string | null>(null)
  const [alphaUsageStats, setAlphaUsageStats] = useState<AlphaUsageStats | null>(null)
  const [showManipulationDataRoom, setShowManipulationDataRoom] = useState(false)


  const activeCollectors = collectors.filter((collector) => collector.status === "active" || collector.status === "ready")
  const totalLiquidity = useMemo(
    () => markets.reduce((sum, market) => sum + Number(market.liquidity || 0), 0),
    [markets],
  )
  const sourceHealth = sourceStatus.length
    ? `${sourceStatus.filter((item) => item.ok).length}/${sourceStatus.length}`
    : "-"
  const rpcChains = Object.entries(rpcStatus?.chains || {})
  const rpcReady = rpcChains.filter(([, chain]) => chain.enabled).length
  const rpcTrackedTokens = rpcChains.reduce((sum, [, chain]) => sum + (chain.tokens_tracked || 0), 0)
  const chainCoverage = arkhamCoverage?.data_map?.chain_coverage_matrix || []
  const strongestChains = chainCoverage.slice(0, 8)
  const acquisitionQueue = arkhamCoverage?.data_map?.acquisition_plan?.priority_queue || []
  const priorityCoverageRows = useMemo(() => {
    const rows = entityCoverage?.rows || []
    const priority = new Map(PRIORITY_ENTITIES.map((entity, index) => [entity.toLowerCase(), index]))
    return rows
      .filter((row) => priority.has(row.entity.toLowerCase()) || row.rpc_wallets > 0)
      .sort((a, b) => {
        const aRank = priority.get(a.entity.toLowerCase()) ?? 999
        const bRank = priority.get(b.entity.toLowerCase()) ?? 999
        return aRank - bRank || b.rpc_wallets - a.rpc_wallets || b.labelled_wallets - a.labelled_wallets
      })
      .slice(0, 10)
  }, [entityCoverage])
  const readinessTone = dataReadiness
    ? dataReadiness.readiness_score >= 80
      ? "tier-strong"
      : dataReadiness.readiness_score >= 45
        ? "tier-useful"
        : "tier-seed"
    : "tier-seed"
  const manipulationContract = manipulationReadiness?.readiness_contract
  const manipulationVerdict = manipulationContract?.manipulation_research_verdict
    || manipulationReadiness?.manipulation_research_verdict
  const holderFlowVerdict = manipulationContract?.evidence_verdicts?.cex_token_holder_flow
    || manipulationReadiness?.evidence_verdicts?.cex_token_holder_flow
  const manipulationTokenTransferLane = manipulationReadiness?.evidence_lanes?.token_transfer_coverage
  const manipulationCexDepositLane = (
    manipulationReadiness?.evidence_lanes as ({ cex_token_deposit_scan?: CexTokenDepositEvidenceLane } | undefined)
  )?.cex_token_deposit_scan
  const manipulationContractTone = manipulationContract
    ? manipulationContract.failed_count === 0
      ? "tier-strong"
      : manipulationContract.passed_count >= Math.ceil(manipulationContract.total_count / 2)
        ? "tier-useful"
        : "tier-seed"
    : "tier-seed"
  const isLocalAdminSurface = typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)
  const walletPrimaryChain = walletIntel?.summary.chains?.[0] || walletProbe?.asset_focus?.[0]?.chain || null
  const walletExplorerUrl = walletIntel?.wallet ? getExplorerAddressUrl(walletIntel.wallet, walletPrimaryChain) : null
  const graphNodesById = useMemo(() => {
    const rows = new Map<string, WalletGraph["nodes"][number]>()
    for (const node of walletGraph?.nodes || []) rows.set(node.id, node)
    return rows
  }, [walletGraph])
  const promotionReadyIds = useMemo(() => (
    (strictCandidateReview?.rows || [])
      .filter((row) => row.decision === "strict_ready" && (row.strict_promotion?.strict_ready || row.promotion?.eligible))
      .map((row) => String(row.id))
  ), [strictCandidateReview])
  const corroborationActionable = useMemo(() => (
    (candidateCorroborationQueue?.rows || [])
      .filter((row) => !row.requires_manual_review)
      .slice(0, 5)
  ), [candidateCorroborationQueue])

  const relatedCandidates = useMemo(() => {
    const currentWallet = walletProbe?.wallet?.toLowerCase()
    if (!currentWallet || !walletDiscovery?.candidates?.length) return []

    const currentChains = new Set((walletIntel?.summary.chains || []).map((chain) => chain.toLowerCase()))
    const currentAssets = new Set<string>()
    for (const item of walletProbe?.asset_focus || []) {
      if (item.asset) currentAssets.add(item.asset.toLowerCase())
    }
    for (const event of walletIntel?.events || []) {
      if (event.asset) currentAssets.add(event.asset.toLowerCase())
    }

    return walletDiscovery.candidates
      .filter((candidate) => candidate.wallet.toLowerCase() !== currentWallet)
      .map((candidate) => {
        const sharedChains = (candidate.chains || []).filter((chain) => currentChains.has(chain.toLowerCase()))
        const sharedAssets = (candidate.assets || []).filter((asset) => currentAssets.has(asset.toLowerCase()))
        const baseRelation = sharedChains.length * 4 + sharedAssets.length * 6
        const relationScore = baseRelation > 0 ? baseRelation + Math.min(3, candidate.first_interactions) : 0
        return {
          ...candidate,
          relationScore,
          sharedChains,
          sharedAssets,
        }
      })
      .filter((candidate) => candidate.sharedChains.length > 0 || candidate.sharedAssets.length > 0)
      .sort((a, b) => (
        b.relationScore - a.relationScore
        || b.flow_usd - a.flow_usd
        || b.events - a.events
      ))
      .slice(0, 6)
  }, [walletDiscovery, walletIntel, walletProbe])

  const clientAnalysisAccounts = useMemo(() => (
    clientAccounts.filter((account) => (
      account.address
      && account.type !== "hyperliquid"
      && account.type !== "manual"
      && String(account.status || "").toLowerCase() === "connected"
    ))
  ), [clientAccounts])
  const watchOnlyAnalysisAccounts = useMemo(() => (
    clientAccounts.filter((account) => (
      account.address
      && account.type === "manual"
      && String(account.status || "").toLowerCase() === "tracked"
    ))
  ), [clientAccounts])
  const selectableAnalysisAccounts = useMemo(() => (
    [...clientAnalysisAccounts, ...watchOnlyAnalysisAccounts]
  ), [clientAnalysisAccounts, watchOnlyAnalysisAccounts])
  const requestedClientWallet = useMemo(() => {
    try {
      const fromUrl = new URLSearchParams(window.location.search).get("wallet")?.trim()
      if (fromUrl) return fromUrl
      const saved = window.localStorage.getItem(SELECTED_ALPHA_ACCOUNT_KEY)
      if (!saved) return ""
      const parsed = JSON.parse(saved)
      return typeof parsed?.address === "string" ? parsed.address.trim() : ""
    } catch {
      return ""
    }
  }, [clientAccounts])
  const selectedClientAccount = useMemo(() => {
    const requested = requestedClientWallet.toLowerCase()
    if (requested) {
      const exact = selectableAnalysisAccounts.find((account) => account.address.toLowerCase() === requested)
      if (exact) return exact
    }
    return clientAnalysisAccounts[0] || null
  }, [clientAnalysisAccounts, requestedClientWallet, selectableAnalysisAccounts])
  const alphaAccessReady = clientAnalysisAccounts.length > 0
  const primaryClientAccount = selectedClientAccount
  const serverOwnershipVerified = Boolean(walletOwnership?.verified && walletOwnership?.session_active)
  const investmentReadiness = walletAutomationPlan?.investment_readiness
  const clientDecisionVerdict = investmentReadiness?.verdict
    ? investmentReadiness.verdict.replace(/_/g, " ")
    : walletProbe?.status_label || t("alpha.inconclusive")
  const clientDecisionConfidence = investmentReadiness
    ? `${investmentReadiness.readiness_score}/100 ${t("alpha.readiness")}`
    : walletProbe ? `${walletProbe.confidence} ${t("alpha.confidence")}` : t("alpha.awaitingProbe")
  const clientDecisionEvidence = walletProbe
    ? `${walletProbe.intel?.summary?.events || 0} ${t("alpha.eventsObserved")} / ${walletProbe.provider_health.ok}/${walletProbe.provider_health.total} ${t("alpha.sourcesReady")}`
    : t("alpha.noBacktestYet")
	  const clientDecisionMissingProof = (
	    investmentReadiness?.critical_blockers?.[0]
	    || investmentReadiness?.missing_proofs?.[0]
	    || walletAutomationPlan?.blockers?.[0]
    || walletCopyBacktest?.blockers?.[0]
    || walletProbe?.requirements?.[0]
    || t("alpha.defaultAutoCopyBlocker")
  ).replace(/_/g, " ")
	  const clientDecisionNextAction = (
	    investmentReadiness?.next_safe_action
	    || walletAutomationPlan?.next_actions?.[0]
    || walletProbe?.requirements?.[0]
    || t("alpha.runAnalyzeWalletCandidate")
  ).replace(/_/g, " ")
  const clientInvestmentStatus = investmentReadiness?.status
    ? investmentReadiness.status.replace(/_/g, " ")
    : t("alpha.investmentNotReady")
  const clientSafetyFlags = investmentReadiness
    ? [
        investmentReadiness.client_investment_enabled ? t("alpha.investmentEnabled") : t("alpha.investmentDisabled"),
        investmentReadiness.execution_enabled ? t("alpha.executionEnabled") : t("alpha.executionDisabled"),
        investmentReadiness.copy_trade_enabled ? t("alpha.copyTradeEnabled") : t("alpha.copyTradeDisabled"),
        investmentReadiness.profit_guarantee_allowed ? t("alpha.profitGuaranteeAllowed") : t("alpha.noProfitGuarantee"),
      ]
    : [t("alpha.analysisOnlyExecutionDisabled"), t("alpha.noProfitGuarantee")]
  const coordinationSurface = walletCopyBacktest?.source_trace?.coordination_surface
  const rpcTxEnrichment = walletCopyBacktest?.source_trace?.rpc_tx_enrichment
  const coordinationHints = Array.isArray(coordinationSurface?.coordination_hints) ? coordinationSurface.coordination_hints : []
  const coordinationMissing = Array.isArray(coordinationSurface?.missing_proofs) ? coordinationSurface.missing_proofs : []
  const rpcMissing = Array.isArray(rpcTxEnrichment?.missing_proofs) ? rpcTxEnrichment.missing_proofs : []
  const coordinationHintLabel = (type?: string) => {
    if (type === "shared_funder_with_cex_flow") return t("alpha.coordinationSharedFunder")
    if (type === "fresh_wallet_with_cex_flow") return t("alpha.coordinationFreshWallet")
    if (type === "gas_distributor_cluster_hint") return t("alpha.coordinationGasDistributor")
    return (type || t("alpha.coordinationNoHint")).replace(/_/g, " ")
  }
  const coordinationMissingLabel = (proof?: string) => {
    if (proof === "cex_flow_or_hint") return t("alpha.coordinationMissingCex")
    if (proof === "funder_graph_surface") return t("alpha.coordinationMissingFunder")
    if (proof === "coordination_hints") return t("alpha.coordinationMissingHints")
    if (proof === "fresh_wallet_surface") return t("alpha.coordinationMissingActivity")
    return (proof || t("alpha.coordinationNoHint")).replace(/_/g, " ")
  }
  const coordinationSummary = coordinationHints.length
    ? coordinationHints.slice(0, 3).map((hint) => coordinationHintLabel(hint.type)).join(" / ")
    : coordinationMissing.slice(0, 3).map((item) => coordinationMissingLabel(item)).join(" / ") || t("alpha.coordinationAwaiting")
  const coordinationStatus = coordinationSurface
    ? coordinationSurface.ok ? t("alpha.coordinationDetected") : t("alpha.coordinationIncomplete")
    : t("alpha.coordinationAwaiting")
  const coordinationCexLabel = !coordinationSurface
    ? t("alpha.coordinationAwaitingShort")
    : coordinationSurface.cex_flow_present ? t("alpha.confirmed") : coordinationSurface.cex_flow_hint_only ? t("alpha.hintOnly") : t("alpha.coordinationMissingCex")
  const coordinationFunderLabel = !coordinationSurface
    ? t("alpha.coordinationAwaitingShort")
    : coordinationSurface.funder_graph_present ? t("alpha.available") : t("alpha.coordinationMissingFunder")
  const coordinationActivityLabel = !coordinationSurface
    ? t("alpha.coordinationAwaitingShort")
    : coordinationSurface.fresh_wallet_surface ? t("alpha.coordinationActivityDetected") : t("alpha.coordinationMissingActivity")
  const rpcEnrichmentStatus = !rpcTxEnrichment
    ? t("alpha.coordinationAwaitingShort")
    : rpcTxEnrichment.ok ? t("alpha.rpcEnrichmentActive") : t("alpha.rpcEnrichmentIncomplete")
  const rpcEnrichmentSummary = rpcTxEnrichment
    ? rpcMissing.length
      ? rpcMissing.slice(0, 2).map((item) => item.replace(/_/g, " ")).join(" / ")
      : t("alpha.rpcEnrichmentProofsAvailable")
    : t("alpha.rpcEnrichmentAwaiting")

  const trackAlphaUsage = (action: string, extra: Record<string, unknown> = {}) => {
    const wallet = String(extra.wallet || primaryClientAccount?.address || walletQuery || "").trim()
    void post("/alpha/usage/event", {
      page: "alpha",
      action,
      wallet,
      connected_wallets: clientAnalysisAccounts.length,
      status: walletProbe?.status || walletAutomationPlan?.decision || "",
      extra: {
        ...extra,
        has_connected_wallet: alphaAccessReady,
        wallet_loaded: Boolean(walletProbe || walletIntel),
      },
    }).catch(() => {
      // Analytics must never block the trading/data workflow.
    })
  }

  const loadCollectors = async () => {
    const response = await get<{ collectors: Collector[] }>("/alpha/collectors/status")
    setCollectors(response.collectors || [])
  }

  const loadMarkets = async () => {
    const params = new URLSearchParams({ source, limit: "30", cache: "true" })
    if (query.trim()) params.set("query", query.trim())
    const response = await get<MarketsResponse>(`/alpha/prediction/markets?${params.toString()}`)
    setMarkets(response.markets || [])
    setSourceStatus(response.source_status || [])
    if (!selectedMarket && response.markets?.[0]) {
      setSelectedMarket(response.markets[0])
    }
  }

  const loadRpcStatus = async () => {
    try {
      const response = await get<RpcStatus>("/onchain/rpc/status")
      setRpcStatus(response)
      setRpcStatusLabel(response.auto_ingest_running ? "indexing" : "ready")
    } catch {
      setRpcStatus(null)
      setRpcStatusLabel("offline")
    }
  }

  const loadArkhamCoverage = async () => {
    try {
      const response = await get<ArkhamCoverage>("/arkham/coverage")
      setArkhamCoverage(response)
    } catch {
      setArkhamCoverage(null)
    }
  }

  const loadEntityCoverage = async () => {
    try {
      const [readinessResponse, manipulationReadinessResponse, caseFileResponse, coverageResponse, gapsResponse, chainGapsResponse, chainGapVerificationResponse, jobsResponse, walletAuditResponse, walletQualityResponse, autoStatusResponse, candidateReviewResponse, strictReviewResponse, automationPlanResponse, acquisitionPlanResponse, qualityReportResponse, corroborationQueueResponse, evidenceScoresResponse] = await Promise.all([
        get<DataReadiness>("/onchain/rpc/data-readiness?limit=12&min_confidence=medium"),
        get<ManipulationReadiness>("/onchain/rpc/manipulation-readiness?limit=12"),
        get<AdaptiveManipulationCaseFile>("/onchain/rpc/adaptive-manipulation-case-file?limit=3&wallet_limit=5&breakout_threshold_pct=500&baseline_swaps=12&confirmation_swaps=3&pre_event_swaps=20&exit_after_swaps_options=3,10,20"),
        get<EntityCoverage>("/onchain/rpc/entity-coverage?limit=80&min_confidence=medium"),
        get<EntityGapReport>("/onchain/rpc/entity-gaps?min_confidence=medium"),
        get<EntityChainGapReport>("/onchain/rpc/entity-chain-gaps?min_confidence=medium&limit=12"),
        get<EntityChainGapVerification>("/onchain/rpc/entity-chain-gap-verification?min_confidence=medium&limit=12&stale_after_hours=24"),
        get<DataJobs>("/onchain/rpc/data-jobs?limit=8"),
        get<WalletStateAudit>("/onchain/rpc/wallet-state-audit?limit=8&stale_after_hours=24"),
        get<WalletQualityAudit>("/onchain/rpc/wallet-quality-audit?limit=8"),
        get<AutoEnrichStatus>("/onchain/rpc/auto-enrich/status"),
        get<CandidatePromotionReview>("/onchain/labels/candidates/promotion-review?limit=30&min_score=70"),
        get<StrictCandidatePromotionReview>("/onchain/labels/candidates/strict-promotion-review?limit=50"),
        get<CandidateAutomationPlan>("/onchain/labels/candidates/automation-plan?limit=100"),
        get<LabelAcquisitionPlan>("/onchain/labels/acquisition-plan?limit=12&min_trusted_per_entity=100"),
        get<CandidateQualityReport>("/onchain/labels/candidates/quality-report?limit=25"),
        get<CandidateCorroborationQueue>("/onchain/labels/candidates/corroboration-queue?limit=12"),
        get<CandidateEvidenceScores>("/onchain/labels/candidates/evidence-scores?limit=12&max_bundles_per_candidate=8"),
      ])
      setDataReadiness(readinessResponse)
      setManipulationReadiness(manipulationReadinessResponse)
      setManipulationCaseFile(caseFileResponse)
      setEntityCoverage(coverageResponse)
      setEntityGaps(gapsResponse)
      setEntityChainGaps(chainGapsResponse)
      setEntityChainGapVerification(chainGapVerificationResponse)
      setDataJobs(jobsResponse)
      setWalletStateAudit(walletAuditResponse)
      setWalletQualityAudit(walletQualityResponse)
      setAutoEnrichStatus(autoStatusResponse)
      setCandidateReview(candidateReviewResponse)
      setStrictCandidateReview(strictReviewResponse)
      setCandidateAutomationPlan(automationPlanResponse)
      setLabelAcquisitionPlan(acquisitionPlanResponse)
      setCandidateQualityReport(qualityReportResponse)
      setCandidateCorroborationQueue(corroborationQueueResponse)
      setCandidateEvidenceScores(evidenceScoresResponse)
    } catch {
      setDataReadiness(null)
      setManipulationReadiness(null)
      setManipulationCaseFile(null)
      setEntityCoverage(null)
      setEntityGaps(null)
      setEntityChainGaps(null)
      setEntityChainGapVerification(null)
      setDataJobs(null)
      setWalletStateAudit(null)
      setWalletQualityAudit(null)
      setAutoEnrichStatus(null)
      setCandidateReview(null)
      setStrictCandidateReview(null)
      setCandidateAutomationPlan(null)
      setLabelAcquisitionPlan(null)
      setCandidateQualityReport(null)
      setCandidateCorroborationQueue(null)
      setCandidateEvidenceScores(null)
    }
  }

  const refresh = async () => {
    setLoading(true)
    setError(null)
    try {
      await Promise.all([loadCollectors(), loadMarkets(), loadRpcStatus(), loadArkhamCoverage(), loadEntityCoverage()])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load Alpha Lab")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    const timer = window.setInterval(() => void refresh(), 60000)
    return () => window.clearInterval(timer)
  }, [source])

  const runCopyPreview = async (market: Market) => {
    setSelectedMarket(market)
    // FIX ronde 8 : le fallback a 0.5 fabriquait un prix d'entree pour un
    // marche SANS prix (tape affiche honnetement « - ») — le garde-fou
    // backend missing_price etait contourne et le PnL affichait un resultat
    // calcule sur une entree inventee.
    const price = market.probability_mid || market.last_price || market.yes_ask || market.yes_bid
    if (!price || price <= 0) {
      setError("Aucun prix de marche disponible — simulation impossible")
      return
    }
    const mark = Math.min(0.99, Math.max(0.01, price * 1.08))
    const result = await post<SimulationResult>("/alpha/simulate/prediction-copy", {
      capital: 100,
      lag_seconds: 60,
      slippage_bps: 75,
      max_trade_pct: 0.25,
      trades: [{ market_id: market.market_id, outcome: "YES", side: "buy", price, current_price: mark, size_usd: 25 }],
    })
    setSimulation(result)
  }

  const runRiskCheck = async () => {
    const tokenInput = riskToken.trim()
    const isContract = /^0x[a-fA-F0-9]{40}$/.test(tokenInput)
    const result = await post<RiskResult>("/alpha/risk/token", {
      token: isContract ? "contract" : tokenInput,
      token_address: isContract ? tokenInput : undefined,
      chain: "ethereum",
      liquidity_usd: Number(riskLiquidity),
      sell_tax_pct: Number(riskSellTax),
      honeypot: riskMode === "danger",
      freeze_function: riskMode === "danger",
      blacklist_function: riskMode === "danger",
      buy_count: 6,
      sell_count: riskMode === "danger" ? 0 : 3,
      unrealized_usd: riskMode === "danger" ? 12000 : 0,
      realized_usd: riskMode === "danger" ? 0 : 950,
      can_sell: riskMode === "danger" ? false : true,
    })
    setRisk(result)
  }

  const runWalletIntel = async (overrideWallet?: string | null) => {
    const wallet = (overrideWallet || walletQuery).trim()
    if (!wallet) return
    if (!alphaAccessReady) {
      setClientAutoStatus("Connecte d'abord un wallet client sur le dashboard pour ouvrir Alpha Lab.")
      trackAlphaUsage("alpha_blocked_no_connected_wallet", { requested_wallet: wallet ? shortId(wallet) : null })
      return
    }
    if (overrideWallet) setWalletQuery(overrideWallet)
    try {
      window.localStorage.setItem(SELECTED_ALPHA_ACCOUNT_KEY, JSON.stringify({
        address: wallet,
        provider: clientAnalysisAccounts.find((account) => account.address.toLowerCase() === wallet.toLowerCase())?.provider || "Alpha Lab",
        selectedAt: Date.now(),
      }))
    } catch {
      // Browser storage is a convenience only; analysis must not depend on it.
    }
    setWalletLoading(true)
    trackAlphaUsage("wallet_analysis_started", { wallet, manual: !overrideWallet })
        try {
      setWalletProbe(null)
      setWalletCopyPlan(null)
      setWalletCopyBacktest(null)
      setWalletAutomationPlan(null)
      setWalletOwnership(null)
      setWalletIntel(null)
      setWalletSurface(null)
      setWalletGraph(null)
      const [ownershipResult, probeResult, copyPlanResult, surfaceResult, graphResult, automationResult, backtestResult] = await Promise.allSettled([
        getWithTimeout<WalletOwnershipStatus>(`/alpha/wallet/ownership/${encodeURIComponent(wallet)}`),
        getWithTimeout<WalletProbe>(`/alpha/wallet/probe/${encodeURIComponent(wallet)}?limit=20&timeframe=30d`),
        getWithTimeout<WalletCopyPlan>(`/alpha/wallet/copy-plan/${encodeURIComponent(wallet)}?capital=100&limit=20&timeframe=30d`),
        getWithTimeout<WalletSurface>(`/alpha/wallet/surface/${encodeURIComponent(wallet)}?limit=30`),
            getWithTimeout<WalletGraph>(`/alpha/wallet/graph/${encodeURIComponent(wallet)}?limit=30`),
        getWithTimeout<WalletAutomationPlan>(
          `/alpha/wallet/automation-plan/${encodeURIComponent(wallet)}?capital=100&limit=20&timeframe=30d`,
          25000,
          { headers: { "x-core-client-action": "persist-rpc-snapshot" } },
        ),
        getWithTimeout<WalletCopyBacktest>(`/alpha/wallet/copy-backtest/${encodeURIComponent(wallet)}?capital=100&limit=30&timeframe=30d`),
      ])
      if (ownershipResult.status === "fulfilled") {
        setWalletOwnership(ownershipResult.value)
      }
      if (probeResult.status === "fulfilled") {
        setWalletProbe(probeResult.value)
            setWalletIntel(probeResult.value.intel)
          }
          if (copyPlanResult.status === "fulfilled") {
            setWalletCopyPlan(copyPlanResult.value)
          }
          if (surfaceResult.status === "fulfilled") {
            setWalletSurface(surfaceResult.value)
          }
      if (graphResult.status === "fulfilled") {
        setWalletGraph(graphResult.value)
      }
      if (automationResult.status === "fulfilled") {
        setWalletAutomationPlan(automationResult.value)
      }
      if (backtestResult.status === "fulfilled") {
        setWalletCopyBacktest(backtestResult.value)
      }
      if (copyPlanResult.status === "rejected" || automationResult.status === "rejected" || backtestResult.status === "rejected") {
        setClientAutoStatus("Read-only probe loaded. Copy plan/backtest require an active verified client session.")
      }
      trackAlphaUsage("wallet_analysis_completed", {
        wallet,
        ownership: ownershipResult.status,
        ownership_verified: ownershipResult.status === "fulfilled" ? ownershipResult.value.verified : false,
        probe: probeResult.status,
        copy_plan: copyPlanResult.status,
        automation_plan: automationResult.status,
        backtest: backtestResult.status,
      })
    } finally {
      setWalletLoading(false)
    }
  }

  useEffect(() => {
    const loadClientAccounts = () => {
      try {
        const saved = window.localStorage.getItem(ACCOUNT_STORAGE_KEY)
        const parsed = saved ? JSON.parse(saved) : []
        setClientAccounts(Array.isArray(parsed) ? parsed : [])
      } catch {
        setClientAccounts([])
      }
    }
    loadClientAccounts()
    window.addEventListener("storage", loadClientAccounts)
    const timer = window.setInterval(loadClientAccounts, 5000)
    return () => {
      window.removeEventListener("storage", loadClientAccounts)
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    if (walletLoading || walletProbe || walletIntel) return
    const next = primaryClientAccount
    if (!next?.address) return
    const key = `${next.network}:${next.address.toLowerCase()}`
    if (autoAnalyzedWallets.current.has(key)) return
    autoAnalyzedWallets.current.add(key)
    setClientAutoStatus(`Auto-analysis started for ${shortId(next.address)} from ${next.provider}.`)
    void runWalletIntel(next.address)
  }, [primaryClientAccount, walletLoading, walletProbe, walletIntel])

  useEffect(() => {
    trackAlphaUsage("alpha_page_view", {
      connected_wallets: clientAnalysisAccounts.length,
      primary_wallet: primaryClientAccount ? shortId(primaryClientAccount.address) : null,
    })
  }, [clientAnalysisAccounts.length])

  const runAdminJob = async (label: string, endpoint: string) => {
    if (!adminToken.trim()) {
      setAdminJobStatus("Admin token required")
      return
    }
    setAdminJobStatus(`${label}: running`)
    try {
      const result = await post<any>(endpoint, undefined, {
        headers: { "x-core-admin-token": adminToken.trim() },
      })
      setAdminJobStatus(`${label}: ok (${JSON.stringify(result).slice(0, 180)})`)
      await loadArkhamCoverage()
      await loadEntityCoverage()
      await loadRpcStatus()
    } catch (err) {
      setAdminJobStatus(`${label}: failed (${err instanceof Error ? err.message : "unknown error"})`)
    }
  }

  const loadAlphaUsageStats = async () => {
    if (!adminToken.trim()) {
      setAdminJobStatus("Usage stats: admin token required")
      return
    }
    try {
      const response = await get<AlphaUsageStats>("/alpha/usage/stats?limit=500", {
        headers: { "x-core-admin-token": adminToken.trim() },
      })
      setAlphaUsageStats(response)
      setAdminJobStatus(`Usage stats loaded: ${response.events} events / ${response.wallets} wallets`)
    } catch {
      setAlphaUsageStats(null)
      setAdminJobStatus("Usage stats failed: check CORE_ADMIN_TOKEN")
    }
  }

  const runCandidatePromoteDryRun = async () => {
    const ids = candidatePromoteIds
      .split(/[,\s]+/)
      .map((value) => value.trim())
      .filter(Boolean)

    if (!adminToken.trim()) {
      setAdminJobStatus("Candidate dry-run: admin token required")
      setCandidatePromotePreview(null)
      return
    }
    if (!ids.length) {
      setAdminJobStatus("Candidate dry-run: add explicit candidate IDs first")
      setCandidatePromotePreview(null)
      return
    }

    setAdminJobStatus(`Candidate dry-run: checking ${ids.length} candidate(s)`)
    try {
      const params = new URLSearchParams({
        candidate_ids: ids.join(","),
        min_score: "90",
        dry_run: "true",
      })
      const result = await post<CandidatePromotionResult>(`/onchain/labels/candidates/promote?${params.toString()}`, undefined, {
        headers: { "x-core-admin-token": adminToken.trim() },
      })
      setCandidatePromotePreview(result)
      const wouldPromote = result.rows.filter((row) => row.status === "would_promote").length
      const rejected = result.rows.length - wouldPromote
      const preview = result.rows
        .slice(0, 4)
        .map((row) => `#${row.id}:${row.status}:${row.promotion?.score ?? "-"}`)
        .join(" / ")
      setAdminJobStatus(`Candidate dry-run: ${wouldPromote} would promote, ${rejected} rejected (${preview || "no rows"})`)
      await loadEntityCoverage()
    } catch (err) {
      setCandidatePromotePreview(null)
      setAdminJobStatus(`Candidate dry-run: failed (${err instanceof Error ? err.message : "unknown error"})`)
    }
  }

  const runCandidateDedupeDryRun = async () => {
    if (!adminToken.trim()) {
      setAdminJobStatus("Candidate dedupe dry-run: admin token required")
      return
    }
    setAdminJobStatus("Candidate dedupe dry-run: checking exact duplicate groups")
    try {
      const result = await post<{
        ok: boolean
        dry_run: boolean
        groups_reviewed: number
        rows_removed: number
        actions: Array<{ keeper_id: number; duplicate_ids: number[]; action: string }>
      }>("/onchain/labels/candidates/consolidate-duplicates?limit=25&dry_run=true", undefined, {
        headers: { "x-core-admin-token": adminToken.trim() },
      })
      const preview = result.actions
        .slice(0, 4)
        .map((row) => `keep #${row.keeper_id} <- ${row.duplicate_ids.map((id) => `#${id}`).join(",")}`)
        .join(" / ")
      setAdminJobStatus(`Candidate dedupe dry-run: ${result.groups_reviewed} groups (${preview || "no duplicates"})`)
      await loadEntityCoverage()
    } catch (err) {
      setAdminJobStatus(`Candidate dedupe dry-run: failed (${err instanceof Error ? err.message : "unknown error"})`)
    }
  }

const runWalletDiscovery = async () => {
    setDiscoveryLoading(true)
    try {
      const params = new URLSearchParams({
        limit: "12",
        feed_limit: "50",
        tx_types: "swap",
        new_trades: "true",
        cache: "true",
      })
      const minUsd = Number(discoveryMinUsd)
      if (!Number.isNaN(minUsd) && minUsd >= 0) params.set("min_usd", String(minUsd))
      if (discoveryToken.trim()) params.set("tokens", discoveryToken.trim())
      if (discoveryChain.trim()) params.set("chains", discoveryChain.trim())
      const result = await get<WalletDiscoveryResponse>(`/alpha/wallet/discovery?${params.toString()}`)
      setWalletDiscovery(result)
    } finally {
      setDiscoveryLoading(false)
    }
  }

  useEffect(() => {
    void runRiskCheck()
    void runWalletDiscovery()
  }, [])

  return (
    <div className="alpha-page anim-fadeUp">
      <section className="alpha-hero scan-overlay">
        <div className="alpha-hero-copy">
          <div className="alpha-kicker">{t("alpha.kicker")}</div>
          <h1>{t("alpha.title")}</h1>
          <p>
            {t("alpha.clientSubtitle")}
          </p>
          <div className="alpha-command-strip">
            <span>{t("alpha.chipCopyTest")}</span>
            <span>{t("alpha.chipProfitIntegrity")}</span>
            <span>{t("alpha.chipWalletEvidence")}</span>
            <span>{t("alpha.chipSourceTrace")}</span>
          </div>
        </div>
        <div className="alpha-hero-actions">
          <button className="alpha-button" onClick={refresh} disabled={loading}>
            {loading ? t("alpha.syncing") : t("alpha.refresh")}
          </button>
          <div className="alpha-live-pill"><span className="live-dot connected" />{t("alpha.beta")}</div>
        </div>
      </section>

      {!alphaAccessReady && (
        <section className="alpha-access-gate alpha-panel">
          <div>
            <div className="alpha-kicker">{t("alpha.clientWalletRequired")}</div>
            <h2>{t("alpha.connectWalletTitle")}</h2>
            <p>
              {t("alpha.connectWalletDesc")}
            </p>
            <div className="alpha-command-strip">
              <span>{t("alpha.noSeedPhrase")}</span>
              <span>{t("alpha.readOnlyStats")}</span>
              <span>{t("alpha.executionOff")}</span>
            </div>
            <div className="alpha-lock-preview">
              <div>
                <span>{t("alpha.lockPreviewVerdict")}</span>
                <strong>Inconclusive</strong>
                <em>{t("alpha.lockPreviewVerdictSub")}</em>
              </div>
              <div>
                <span>{t("alpha.lockPreviewReplay")}</span>
                <strong>$100</strong>
                <em>{t("alpha.lockPreviewReplaySub")}</em>
              </div>
              <div>
                <span>{t("alpha.lockPreviewSafety")}</span>
                <strong>Read-only</strong>
                <em>{t("alpha.lockPreviewSafetySub")}</em>
              </div>
            </div>
          </div>
          <button className="alpha-button" onClick={() => { window.location.href = "/" }}>
            {t("alpha.connectWallet")}
          </button>
        </section>
      )}

      <div className={alphaAccessReady ? "alpha-client-workflow" : "alpha-client-workflow is-locked"}>
      <section className="alpha-client-results alpha-panel">
        <div className="alpha-panel-header">
          <div>
            <div className="alpha-panel-title">{t("alpha.clientResultsHub")}</div>
            <div className="alpha-panel-subtitle">
              {t("alpha.clientResultsSub")}
            </div>
          </div>
          <div className="alpha-live-pill">
            <span className={`live-dot ${walletLoading ? "connected" : walletProbe ? "connected" : ""}`} />
            {walletLoading ? t("alpha.analysisRunning") : walletProbe ? t("alpha.walletAnalyzedStatus") : t("alpha.waitingWallet")}
          </div>
        </div>
	        <div className="alpha-client-result-grid">
	          <div className="alpha-client-result-card primary">
            <span>{t("alpha.walletAnalyzed")}</span>
            <strong>{walletProbe?.wallet ? shortId(walletProbe.wallet) : primaryClientAccount ? shortId(primaryClientAccount.address) : t("alpha.noWalletYet")}</strong>
            <em>{walletProbe?.status_label || t("alpha.connectOrPasteWallet")}</em>
          </div>
          <div className="alpha-client-result-card">
            <span>{t("alpha.historicalReplay")}</span>
            <strong className={(walletCopyBacktest?.pnl || 0) >= 0 ? "positive" : "negative"}>
              {walletCopyBacktest ? `${money(walletCopyBacktest.current_value)}` : "-"}
            </strong>
            <em>
              {walletCopyBacktest
                ? `${t("alpha.replayPrefix")}: ${walletCopyBacktest.roi_pct >= 0 ? "+" : ""}${walletCopyBacktest.roi_pct.toFixed(2)}%`
                : t("alpha.pastResultHint")}
            </em>
          </div>
          <div className="alpha-client-result-card">
            <span>{t("alpha.currentCopyProxy")}</span>
            <strong className={(walletProbe?.copy_preview?.pnl || 0) >= 0 ? "positive" : "negative"}>
              {walletProbe ? money(walletProbe.copy_preview.estimated_value) : "-"}
            </strong>
            <em>
              {walletProbe
                ? `${walletProbe.copy_preview.roi_pct >= 0 ? "+" : ""}${walletProbe.copy_preview.roi_pct.toFixed(2)}% ${t("alpha.proxyNotExecution")}`
                : t("alpha.currentOpportunityHint")}
            </em>
          </div>
	          <div className="alpha-client-result-card">
	            <span>{t("alpha.investmentReadiness")}</span>
	            <strong className={investmentReadiness?.manual_review_allowed ? "positive" : "negative"}>
	              {clientInvestmentStatus}
	            </strong>
	            <em>
	              {investmentReadiness
	                ? `${investmentReadiness.readiness_score}/100 - ${investmentReadiness.verdict.replace(/_/g, " ")}`
	                : t("alpha.executionNotReady")}
	            </em>
	          </div>
	        </div>
	        <div className="alpha-client-decision-strip">
	          <div>
	            <span>{t("alpha.clientDecisionVerdict")}</span>
	            <strong>{clientDecisionVerdict}</strong>
	            <em>{clientDecisionConfidence}</em>
	          </div>
	          <div>
	            <span>{t("alpha.clientDecisionEvidence")}</span>
	            <strong>{clientDecisionEvidence}</strong>
	            <em>{t("alpha.sourcePolicyRequired")}</em>
	          </div>
	          <div>
	            <span>{t("alpha.clientDecisionMissing")}</span>
	            <strong>{clientDecisionMissingProof}</strong>
	            <em>{t("alpha.inconclusiveIfMissingProof")}</em>
	          </div>
	          <div>
	            <span>{t("alpha.clientDecisionNext")}</span>
	            <strong>{clientDecisionNextAction}</strong>
	            <em>{t("alpha.analysisOnlyExecutionDisabled")}</em>
	          </div>
	        </div>
	        <div className="alpha-investment-safety">
	          <div>
	            <span>{t("alpha.investmentGuardrails")}</span>
	            <strong>{clientSafetyFlags.join(" / ")}</strong>
	            <em>{investmentReadiness?.source_policy || t("alpha.sourcePolicyRequired")}</em>
	          </div>
	          <div>
	            <span>{t("alpha.blockersClient")}</span>
	            <strong>
	              {investmentReadiness
	                ? [...investmentReadiness.critical_blockers, ...investmentReadiness.missing_proofs].slice(0, 3).map((item) => item.replace(/_/g, " ")).join(" / ") || t("alpha.noBlockingProofs")
	                : t("alpha.defaultAutoCopyBlocker")}
	            </strong>
	            <em>{t("alpha.noTradeSignal")}</em>
	          </div>
	        </div>
	        <div className="alpha-coordination-surface">
	          <div className="alpha-coordination-head">
	            <span>{t("alpha.coordinationSurface")}</span>
	            <strong className={coordinationSurface?.ok ? "positive" : "negative"}>{coordinationStatus}</strong>
	            <em>{t("alpha.coordinationResearchOnly")}</em>
	          </div>
	          <div className="alpha-coordination-grid">
	            <div>
	              <span>{t("alpha.rpcEnrichment")}</span>
	              <strong className={rpcTxEnrichment?.ok ? "positive" : "negative"}>{rpcEnrichmentStatus}</strong>
	            </div>
	            <div>
	              <span>{t("alpha.rpcTxEnriched")}</span>
	              <strong>{largeNumber(rpcTxEnrichment?.tx_enriched || 0)}</strong>
	            </div>
	            <div>
	              <span>{t("alpha.rpcTokenTransfers")}</span>
	              <strong>{largeNumber(rpcTxEnrichment?.token_transfers_found || 0)}</strong>
	            </div>
	            <div>
	              <span>{t("alpha.coordinationCexFlow")}</span>
	              <strong>{coordinationCexLabel}</strong>
	            </div>
	            <div>
	              <span>{t("alpha.coordinationFunderGraph")}</span>
	              <strong>{coordinationFunderLabel}</strong>
	            </div>
	            <div>
	              <span>{t("alpha.coordinationSharedFunders")}</span>
	              <strong>{largeNumber(coordinationSurface?.shared_funder_count || 0)}</strong>
	            </div>
	            <div>
	              <span>{t("alpha.coordinationGasDistributors")}</span>
	              <strong>{largeNumber(coordinationSurface?.gas_distributor_count || 0)}</strong>
	            </div>
	          </div>
	          <div className="alpha-coordination-foot">
	            <span>{t("alpha.coordinationWalletActivity")}</span>
	            <strong>{coordinationActivityLabel}</strong>
	          </div>
	          <p>{rpcEnrichmentSummary}</p>
	          <p>{coordinationSummary}</p>
	        </div>
	        <div className="alpha-client-explain">
          <div>
            <span>{t("alpha.clientNeedsToKnow")}</span>
            <strong>
              {walletCopyBacktest
                ? `${walletCopyBacktest.coverage.events_copied} ${t("alpha.eventsCopied")}, ${walletCopyBacktest.coverage.events_skipped} ${t("alpha.eventsSkippedReadOnly")}.`
                : t("alpha.noBacktestYet")}
            </strong>
          </div>
          <div>
            <span>{t("alpha.whyNotAutoCopy")}</span>
            <strong>
              {(walletAutomationPlan?.blockers?.[0] || walletCopyBacktest?.blockers?.[0] || t("alpha.defaultAutoCopyBlocker")).replace(/_/g, " ")}
            </strong>
          </div>
        </div>
      </section>

      {/* Wallet Analyzer */}
      <section className="alpha-single">
        <div className="alpha-panel alpha-panel-large">
          <div className="alpha-panel-header">
            <div>
              <div className="alpha-panel-title">{t("alpha.walletAnalyzer")}</div>
              <div className="alpha-panel-subtitle">{t("alpha.walletAnalyzerSub")} Balance, transactions, swaps, volume, and smart labels.</div>
            </div>
          </div>
          <div style={{ padding: '16px 20px' }}>
            <WalletAnalyzer />
          </div>
        </div>
      </section>

      <section className="alpha-focus-board">
        <div className="alpha-focus-main alpha-panel">
          <div className="alpha-panel-header">
            <div>
              <div className="alpha-panel-title">{t("alpha.copySimulator")}</div>
              <div className="alpha-panel-subtitle">{t("alpha.copySimulatorSub")}</div>
            </div>
            <div className="alpha-toolbar">
              <input
                className="alpha-wallet-input"
                value={walletQuery}
                onChange={(event) => setWalletQuery(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") void runWalletIntel() }}
                placeholder={t("alpha.pasteWalletAddress")}
              />
              <button onClick={() => void runWalletIntel()} disabled={walletLoading || !walletQuery.trim()}>
                {walletLoading ? t("alpha.analyzing") : t("alpha.analyzeWallet")}
              </button>
            </div>
          </div>

          <div className="alpha-chain-coverage" style={{ margin: "0 20px 16px" }}>
            <div className="alpha-panel-title mini">{t("alpha.clientWalletAutomation")}</div>
            <div className="alpha-panel-subtitle">
              {t("alpha.clientWalletAutomationSub")}
            </div>
            <div className="alpha-metric-grid compact">
              <div className="alpha-metric-card">
                <span>{t("alpha.clientWallets")}</span>
                <strong>{clientAnalysisAccounts.length}</strong>
                <em>{watchOnlyAnalysisAccounts.length} {t("alpha.watchOnlyTargets")}</em>
              </div>
              <div className="alpha-metric-card">
                <span>{t("alpha.automation")}</span>
                <strong className={walletLoading ? "tier-useful" : walletProbe ? (serverOwnershipVerified ? "tier-strong" : "tier-seed") : "tier-seed"}>
                  {walletLoading ? t("alpha.running") : walletProbe ? (serverOwnershipVerified ? t("alpha.ready") : t("alpha.readOnly")) : t("alpha.waiting")}
                </strong>
                <em>{serverOwnershipVerified ? clientAutoStatus : t("alpha.serverProofRequired")}</em>
              </div>
              <div className="alpha-metric-card">
                <span>{t("alpha.ownershipProof")}</span>
                <strong className={serverOwnershipVerified ? "tier-strong" : "tier-seed"}>
                  {serverOwnershipVerified ? t("alpha.verified") : walletOwnership?.expired ? t("alpha.expired") : t("alpha.unverified")}
                </strong>
                <em>
                  {walletOwnership
                    ? `${walletOwnership.execution_gate.replace(/_/g, " ")}${walletOwnership.session_expires_at ? ` / session ${new Date(walletOwnership.session_expires_at * 1000).toLocaleString()}` : walletOwnership.expires_at ? ` / proof ${new Date(walletOwnership.expires_at * 1000).toLocaleString()}` : ""}`
                    : t("alpha.serverProofNotLoaded")}
                </em>
              </div>
              <div className="alpha-metric-card">
                <span>{t("alpha.planReadiness")}</span>
                <strong className={walletAutomationPlan?.readiness_score && walletAutomationPlan.readiness_score >= 70 ? "tier-strong" : walletAutomationPlan?.readiness_score && walletAutomationPlan.readiness_score >= 45 ? "tier-useful" : "tier-seed"}>
                  {walletAutomationPlan ? `${walletAutomationPlan.readiness_score}/100` : t("alpha.waiting")}
                </strong>
                <em>{walletAutomationPlan ? walletAutomationPlan.mode.replace(/_/g, " ") : t("alpha.analysisOnlyExecutionDisabled")}</em>
              </div>
            </div>
            {selectableAnalysisAccounts.slice(0, 4).map((account) => (
              <div className="alpha-wallet-row" key={`client-auto-${account.id}`}>
                <span>
                  <strong>{account.provider} / {shortId(account.address)}</strong>
                  <em>{account.network} / {account.type === "manual" ? "watch-only target" : account.status}{account.verifiedAt ? " / verified" : ""}</em>
                </span>
                <button className="alpha-mini-button" onClick={() => void runWalletIntel(account.address)} disabled={walletLoading}>
                  {t("alpha.analyzeNow")}
                </button>
              </div>
            ))}
            {walletAutomationPlan && (
              <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
                <div>
                  <div className="alpha-panel-title mini">Automation Plan</div>
                  <div className="alpha-wallet-row">
                    <span>
                      <strong>{walletAutomationPlan.decision}</strong>
                      <em>{walletAutomationPlan.rails.contract} / {walletAutomationPlan.rails.execution_gate}</em>
                    </span>
                    <strong>{walletAutomationPlan.execution_enabled ? "ON" : "OFF"}</strong>
                  </div>
                  {walletAutomationPlan.blockers.slice(0, 4).map((blocker) => (
                    <div className="alpha-wallet-row" key={`blocker-${blocker}`}><span>{blocker}</span></div>
                  ))}
                  {walletAutomationPlan.blockers.length === 0 && (
                    <div className="alpha-wallet-row"><span>No blocking issue surfaced yet, but manual review is still required.</span></div>
                  )}
                </div>
                <div>
                  <div className="alpha-panel-title mini">Source Trace</div>
                  <div className="alpha-wallet-row">
                    <span>Providers</span>
                    <strong>{walletAutomationPlan.source_trace.providers_ok}/{walletAutomationPlan.source_trace.providers_total}</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>RPC events</span>
                    <strong>{walletAutomationPlan.source_trace.rpc_events}</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Graph edges</span>
                    <strong>{walletAutomationPlan.source_trace.graph_edges}</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Flow confidence</span>
                    <strong>{walletAutomationPlan.data_quality.flow_confidence_score}/100</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>RPC backbone</span>
                    <strong>{walletAutomationPlan.data_quality.rpc_backbone_score}/100</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Snapshot rows</span>
                    <strong>
                      {walletAutomationPlan.rpc_backbone.persisted_snapshot?.updated ?? 0}
                      {walletAutomationPlan.rpc_backbone.persisted_snapshot?.skipped_fresh
                        ? ` / ${walletAutomationPlan.rpc_backbone.persisted_snapshot.skipped_fresh} fresh`
                        : ""}
                    </strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Freshness</span>
                    <strong>
                      {walletAutomationPlan.data_quality.source_freshness.replace(/_/g, " ")}
                      {walletAutomationPlan.rpc_backbone.persisted_snapshot?.refresh_after_hours
                        ? ` / ttl ${walletAutomationPlan.rpc_backbone.persisted_snapshot.refresh_after_hours}h`
                        : ""}
                    </strong>
                  </div>
                </div>
              </div>
            )}
            {walletAutomationPlan && (
              <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
                <div>
                  <div className="alpha-panel-title mini">RPC Chain Coverage</div>
                  {walletAutomationPlan.rpc_backbone?.ok && (
                    <div className="alpha-wallet-row">
                      <span>
                        <strong>{walletAutomationPlan.rpc_backbone.wallet_label || "rpc wallet"}</strong>
                        <em>
                          {walletAutomationPlan.rpc_backbone.primary_chain || "multi-chain"} / {walletAutomationPlan.rpc_backbone.source_rows ?? 0} source rows / {walletAutomationPlan.rpc_backbone.traceable_rows ?? 0} traceable
                        </em>
                      </span>
                      <strong>{money(walletAutomationPlan.rpc_backbone.net_worth_usd)}</strong>
                    </div>
                  )}
                  {walletAutomationPlan.chain_coverage.slice(0, 4).map((row) => (
                    <div className="alpha-wallet-row" key={`auto-chain-${row.chain}`}>
                      <span>
                        <strong>{row.chain}</strong>
                        <em>{row.assets.slice(0, 4).join(", ") || "no assets surfaced"}</em>
                      </span>
                      <strong>{row.events} ev / {money(row.amount_usd)}</strong>
                    </div>
                  ))}
                  {walletAutomationPlan.chain_coverage.length === 0 && (
                    <div className="alpha-empty small">No chain sample yet. RPC/provider data must be refreshed before copy analysis.</div>
                  )}
                </div>
                <div>
                  <div className="alpha-panel-title mini">Token Risk Watchlist</div>
                  {walletAutomationPlan.token_risk_watchlist.slice(0, 4).map((row) => (
                    <div className="alpha-wallet-row" key={`auto-token-${row.chain}-${row.asset}`}>
                      <span>
                        <strong>{row.asset} / {row.chain}</strong>
                        <em>{row.risk_flag.replace(/_/g, " ")}</em>
                      </span>
                      <strong>{row.copy_allowed === false ? "BLOCK" : "PROVE"}</strong>
                    </div>
                  ))}
                  {walletAutomationPlan.token_risk_watchlist.length === 0 && (
                    <div className="alpha-empty small">No token focus yet. Wallet needs observable swaps or transfers.</div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="alpha-simulator-hero">
            <div className={`alpha-verdict-card ${walletProbe?.status || "idle"}`}>
              <span>Verdict</span>
              <strong>{walletProbe?.status_label || "No wallet loaded"}</strong>
              <em>{walletProbe ? `${walletProbe.confidence} confidence` : "Paste a wallet, then run the probe."}</em>
            </div>
            <div className="alpha-verdict-card">
              <span>100 USD copy proxy</span>
              <strong className={(walletProbe?.copy_preview?.pnl || 0) >= 0 ? "positive" : "negative"}>
                {walletProbe ? money(walletProbe.copy_preview.estimated_value) : "-"}
              </strong>
              <em>
                {walletProbe
                  ? `${(walletProbe.copy_preview.pnl || 0) >= 0 ? "+" : ""}${money(walletProbe.copy_preview.pnl)} / ${walletProbe.copy_preview.roi_pct.toFixed(2)}%`
                  : "No simulation yet"}
              </em>
            </div>
            <div className="alpha-verdict-card">
              <span>Profit trust</span>
              <strong>{walletProbe ? `${walletProbe.risk_summary.untrusted_rows} suspect` : "-"}</strong>
              <em>{walletProbe ? `${walletProbe.risk_summary.blocked_rows} blocked rows` : "Sell proof and fake-mark filters"}</em>
            </div>
            <div className={`alpha-verdict-card ${walletCopyPlan?.mode || "idle"}`}>
              <span>Copy mode</span>
              <strong>{walletCopyPlan ? (walletCopyPlan.execution_enabled ? "Enabled" : "Manual only") : "-"}</strong>
              <em>{walletCopyPlan ? walletCopyPlan.mode.replace(/_/g, " ") : "No execution without guards"}</em>
            </div>
            <div className={`alpha-verdict-card ${walletCopyBacktest?.verdict || "idle"}`}>
              <span>Read-only backtest</span>
              <strong className={(walletCopyBacktest?.pnl || 0) >= 0 ? "positive" : "negative"}>
                {walletCopyBacktest ? `${money(walletCopyBacktest.current_value)} / ${walletCopyBacktest.roi_pct.toFixed(2)}%` : "-"}
              </strong>
              <em>
                {walletCopyBacktest
                  ? `${walletCopyBacktest.verdict.replace(/_/g, " ")} / trust ${walletCopyBacktest.confidence_score}/100`
                  : "100 USD cost replay, no execution"}
              </em>
            </div>
          </div>

          <div className="alpha-decision-lane">
            <div>
              <div className="alpha-panel-title mini">Why this verdict</div>
              {(walletProbe?.reasons || []).slice(0, 4).map((reason) => (
                <div className="alpha-wallet-row" key={reason}><span>{reason}</span></div>
              ))}
              {!walletProbe && <div className="alpha-empty small">Run a wallet to see the reasons, not just raw tables.</div>}
              {walletProbe && walletProbe.reasons.length === 0 && <div className="alpha-empty small">No clear reason surfaced yet.</div>}
            </div>
            <div>
              <div className="alpha-panel-title mini">Required before copy</div>
              {(walletProbe?.requirements || []).slice(0, 4).map((requirement) => (
                <div className="alpha-wallet-row" key={requirement}><span>{requirement}</span></div>
              ))}
              {!walletProbe && <div className="alpha-empty small">The checklist appears after a probe.</div>}
              {walletProbe && walletProbe.requirements.length === 0 && <div className="alpha-empty small">No blocking requirement on this probe.</div>}
            </div>
          </div>
          {walletCopyPlan && (
            <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
              <div>
                <div className="alpha-panel-title mini">Smart copy allocation</div>
                {walletCopyPlan.allocation.slice(0, 4).map((item) => (
                  <div className="alpha-wallet-row" key={`${item.chain}:${item.asset}`}>
                    <span>{item.asset} / {item.chain}</span>
                    <strong>{item.max_weight_pct.toFixed(1)}%</strong>
                  </div>
                ))}
                {walletCopyPlan.allocation.length === 0 && <div className="alpha-empty small">No asset allocation until useful wallet flow appears.</div>}
              </div>
              <div>
                <div className="alpha-panel-title mini">Execution guards</div>
                {walletCopyPlan.guards.slice(0, 4).map((guard) => (
                  <div className="alpha-wallet-row" key={guard}><span>{guard}</span></div>
                ))}
              </div>
            </div>
          )}
          {walletCopyBacktest && (
            <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
              <div>
                <div className="alpha-panel-title mini">Backtest trace</div>
                <div className="alpha-wallet-row">
                  <span>Copied / skipped</span>
                  <strong>{walletCopyBacktest.coverage.events_copied} / {walletCopyBacktest.coverage.events_skipped}</strong>
                </div>
                <div className="alpha-wallet-row">
                  <span>Chains</span>
                  <strong>{walletCopyBacktest.coverage.chains_seen.join(", ") || "-"}</strong>
                </div>
                <div className="alpha-wallet-row">
                  <span>Execution</span>
                  <strong>{walletCopyBacktest.execution_enabled ? "ON" : "OFF"}</strong>
                </div>
                <div className="alpha-empty small">
                  {String(walletCopyBacktest.assumptions.profit_policy || "Cost-only replay until stronger marks are available.")}
                </div>
              </div>
              <div>
                <div className="alpha-panel-title mini">Backtest blockers</div>
                {walletCopyBacktest.blockers.slice(0, 5).map((blocker) => (
                  <div className="alpha-wallet-row" key={blocker}><span>{blocker.replace(/_/g, " ")}</span></div>
                ))}
                {walletCopyBacktest.blockers.length === 0 && (
                  <div className="alpha-wallet-row"><span>Ready for manual review, not auto-copy.</span></div>
                )}
                {walletCopyBacktest.skipped.slice(0, 3).map((item, index) => (
                  <div className="alpha-wallet-row" key={`${item.reason}:${item.asset}:${index}`}>
                    <span>{item.reason.replace(/_/g, " ")} {item.asset ? `/${item.asset}` : ""}</span>
                    <strong>{item.observed_usd ? money(item.observed_usd) : item.chain || ""}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <aside className="alpha-panel alpha-focus-side">
          <div className="alpha-panel-header compact">
            <div>
              <div className="alpha-panel-title">Evidence Snapshot</div>
              <div className="alpha-panel-subtitle">Seulement les preuves utiles, pas le labyrinthe.</div>
            </div>
          </div>
          <div className="alpha-proof-stack">
            <div><span>Providers</span><strong>{walletProbe ? `${walletProbe.provider_health.ok}/${walletProbe.provider_health.total}` : sourceHealth}</strong><em>Cielo / Zerion / RPC</em></div>
            <div><span>Graph edges</span><strong>{walletGraph?.summary.edges ?? "-"}</strong><em>{walletGraph?.summary.evidence_grade || "waiting for wallet"}</em></div>
            <div><span>Transfers</span><strong>{walletSurface?.summary.transfers ?? "-"}</strong><em>net {money(walletSurface?.summary.net_transfer_usd)}</em></div>
            <div><span>RPC backbone</span><strong>{rpcStatus ? `${rpcReady}/${rpcChains.length}` : "-"}</strong><em>{rpcStatusLabel} / {rpcTrackedTokens} tokens</em></div>
          </div>
        </aside>
      </section>
      </div>

      <section className="alpha-panel alpha-data-ledger">
        <div className="alpha-panel-header">
          <div>
            <div className="alpha-panel-title">Arkham Data Ledger</div>
            <div className="alpha-panel-subtitle">
              Ce qu'on a reellement en local: labels, holders caches, flows observes et valeur attribuee.
            </div>
          </div>
          <div className="alpha-live-pill">
            <span className={`live-dot ${arkhamCoverage ? "connected" : ""}`} />
            {arkhamCoverage ? "coverage live" : "coverage loading"}
          </div>
        </div>
        <div className="alpha-arkham-gap">
          <div>
            <span>Arkham public scale</span>
            <strong>{largeNumber(ARKHAM_REFERENCE_ADDRESSES)}</strong>
            <em>addresses labelled reference</em>
          </div>
          <div>
            <span>Core Equity local</span>
            <strong>{largeNumber(arkhamCoverage?.coverage.addresses_labelled)}</strong>
            <em>{coverageRatio(arkhamCoverage?.coverage.addresses_labelled)} of Arkham address scale</em>
          </div>
          <div>
            <span>Data decision</span>
            <strong>NO BULK INGEST</strong>
            <em>{arkhamCoverage?.data_map?.rpc_ingestion_gate?.decision || "manual chain windows first"}</em>
          </div>
        </div>
        <div className="alpha-metric-grid" style={{ padding: 14 }}>
          <div className="alpha-metric-card"><span>On-chain value attributed</span><strong>{money(arkhamCoverage?.coverage.on_chain_value_attributed_usd)}</strong><em>from normalized entity holdings</em></div>
          <div className="alpha-metric-card"><span>Asset flow tracked</span><strong>{money(arkhamCoverage?.coverage.asset_flow_tracked_usd)}</strong><em>{arkhamCoverage?.coverage.asset_flow_tracked_rows ?? "-"} observed rows</em></div>
          <div className="alpha-metric-card"><span>Addresses labelled</span><strong>{arkhamCoverage?.coverage.addresses_labelled ?? "-"}</strong><em>{arkhamCoverage?.coverage.entities_labelled ?? "-"} entities / labels</em></div>
          <div className="alpha-metric-card"><span>Holders cached</span><strong>{arkhamCoverage?.coverage.holder_rows_cached ?? "-"}</strong><em>{arkhamCoverage?.coverage.holder_tokens_cached ?? "-"} token holder sets</em></div>
        </div>
        {strongestChains.length > 0 && (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Chain Coverage Matrix</div>
            <div className="alpha-chain-head">
              <span>Chain</span>
              <span>Tier</span>
              <span>Labels</span>
              <span>RPC tx</span>
              <span>Holders</span>
              <span>Gap</span>
            </div>
            {strongestChains.map((row) => (
              <div className="alpha-chain-row" key={row.chain}>
                <strong>{row.chain}</strong>
                <em className={`tier-${row.local_tier}`}>{row.local_tier}</em>
                <span>{largeNumber(row.metrics.labelled_addresses)}</span>
                <span>{largeNumber(row.metrics.rpc_transactions)}</span>
                <span>{largeNumber(row.metrics.holder_rows)}</span>
                <span>{row.gaps.slice(0, 2).join(", ") || "measurable"}</span>
              </div>
            ))}
          </div>
        )}
        {acquisitionQueue.length > 0 && (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Acquisition Priority Queue</div>
            {acquisitionQueue.slice(0, 5).map((row) => (
              <div className="alpha-wallet-row" key={`acq-${row.chain}`}>
                <span>
                  <strong>{row.chain}</strong>
                  <em>
                    score {row.priority_score} / {row.local_tier} / {row.next_sources.slice(0, 3).join(", ")}
                  </em>
                </span>
                <strong>{row.safe_actions[0] || "measure first"}</strong>
              </div>
            ))}
          </div>
        )}
        {dataReadiness && (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Data Readiness Control</div>
            <div className="alpha-panel-subtitle">
              Read-only control plane: ce bloc dit si notre data est exploitable avant de lancer plus d'automatisation RPC.
            </div>
            <div className="alpha-metric-grid compact">
              <div className="alpha-metric-card">
                <span>Status</span>
                <strong className={readinessTone}>{dataReadiness.status.replace(/_/g, " ")}</strong>
                <em>score {dataReadiness.readiness_score}/100</em>
              </div>
              <div className="alpha-metric-card">
                <span>Signal trust</span>
                <strong className={
                  dataReadiness.client_signal_trust?.decision === "ready_for_manual_review"
                    ? "tier-strong"
                    : dataReadiness.client_signal_trust?.decision === "blocked"
                      ? "tier-seed"
                      : "tier-useful"
                }>
                  {dataReadiness.client_signal_trust ? `${dataReadiness.client_signal_trust.score}/100` : "WAIT"}
                </strong>
                <em>
                  {(dataReadiness.client_signal_trust?.client_safe_label || "watch_only").replace(/_/g, " ")}
                </em>
              </div>
              <div className="alpha-metric-card">
                <span>Strict labels</span>
                <strong>{dataReadiness.summary.strict_label_pct.toFixed(1)}%</strong>
                <em>{largeNumber(dataReadiness.summary.strict_labelled_wallets)} strict / {largeNumber(dataReadiness.summary.labelled_wallets)} total</em>
              </div>
              <div className="alpha-metric-card">
                <span>RPC coverage</span>
                <strong>{dataReadiness.summary.rpc_coverage_pct.toFixed(1)}%</strong>
                <em>{largeNumber(dataReadiness.summary.missing_rpc_wallets)} missing RPC wallets</em>
              </div>
              <div className="alpha-metric-card">
                <span>Trusted auto</span>
                <strong className={dataReadiness.trusted_auto_promotion ? "tier-seed" : "tier-strong"}>
                  {dataReadiness.trusted_auto_promotion ? "ON" : "OFF"}
                </strong>
                <em>{largeNumber(dataReadiness.summary.ledger_candidates)} candidates / {largeNumber(dataReadiness.summary.ledger_labels)} labels</em>
              </div>
              <div className="alpha-metric-card">
                <span>Wallet freshness</span>
                <strong>{dataReadiness.summary.wallet_traceability_pct.toFixed(1)}%</strong>
                <em>
                  {largeNumber(dataReadiness.summary.wallet_stale_rows_24h)} stale / {largeNumber(dataReadiness.summary.wallet_low_quality_rows)} low quality
                </em>
              </div>
              <div className="alpha-metric-card">
                <span>Candidate hygiene</span>
                <strong>
                  {largeNumber(dataReadiness.summary.candidate_duplicate_groups ?? 0)} dup / {largeNumber(dataReadiness.summary.candidate_ambiguous_addresses ?? 0)} amb
                </strong>
                <em>
                  {largeNumber(dataReadiness.summary.candidate_open ?? dataReadiness.summary.ledger_candidates)} open / {Number(dataReadiness.summary.candidate_single_seen_pct ?? 0).toFixed(1)}% single seen
                </em>
              </div>
              <div className="alpha-metric-card">
                <span>Token transfers</span>
                <strong className={(dataReadiness.summary.token_transfer_rows ?? 0) >= 500 ? "tier-strong" : "tier-seed"}>
                  {largeNumber(dataReadiness.summary.token_transfer_rows ?? 0)}
                </strong>
                <em>
                  {largeNumber(dataReadiness.summary.token_transfer_distinct_tokens ?? dataReadiness.token_transfer_coverage?.summary?.distinct_tokens ?? 0)} tokens / {Number(dataReadiness.summary.token_transfer_history_days ?? 0).toFixed(1)}d
                </em>
              </div>
              <div className="alpha-metric-card">
                <span>Exact market flow</span>
                <strong className={(dataReadiness.summary.swap_exact_token_rows ?? 0) >= 100 ? "tier-strong" : "tier-useful"}>
                  {largeNumber(dataReadiness.summary.swap_exact_token_rows ?? 0)}
                </strong>
                <em>
                  {largeNumber(dataReadiness.summary.swap_total_rows ?? 0)} swaps / {Number(dataReadiness.summary.swap_history_days ?? 0).toFixed(1)}d
                </em>
              </div>
            </div>
            <div className="alpha-chain-head">
              <span>Blockers</span>
              <span>Next action</span>
              <span>Wallet state</span>
              <span>Rails</span>
            </div>
            <div className="alpha-chain-row">
              <span title={dataReadiness.blockers.join(" / ")}>
                {dataReadiness.blockers.slice(0, 3).map((blocker) => blocker.replace(/_/g, " ")).join(", ") || "none"}
              </span>
              <strong title={dataReadiness.next_actions.join(" / ")}>
                {dataReadiness.next_actions[0] || "Keep monitoring coverage before scaling."}
              </strong>
              <span>
                {largeNumber(dataReadiness.summary.wallet_chain_state_rows)} rows / {" "}
                {Object.entries(dataReadiness.summary.wallet_chain_state_by_chain || {})
                  .slice(0, 3)
                  .map(([chain, count]) => `${chain}:${count}`)
                  .join(", ") || "no chains"}
              </span>
              <span>
                audit {String(dataReadiness.automation_rails.audit_refresh_enabled ?? "?")} / dedup {String(dataReadiness.automation_rails.candidate_dedup_enabled ?? "?")} / source {String(dataReadiness.automation_rails.source_acquire_enabled ?? "?")} / evidence {String(dataReadiness.automation_rails.candidate_corroboration_enabled ?? "?")}
              </span>
            </div>
            {dataReadiness.client_signal_trust && (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Signal Trust Layer</div>
                <div className="alpha-panel-subtitle">
                  Client-safe verdict. This is analysis only: automatic copy execution stays disabled until data quality is strong enough.
                </div>
                <div className="alpha-chain-head">
                  <span>Decision</span>
                  <span>Why</span>
                  <span>Next</span>
                  <span>Execution</span>
                </div>
                <div className="alpha-chain-row">
                  <strong>{dataReadiness.client_signal_trust.decision.replace(/_/g, " ")}</strong>
                  <span title={dataReadiness.client_signal_trust.reasons.join(" / ")}>
                    {dataReadiness.client_signal_trust.reasons.slice(0, 3).map((reason) => reason.replace(/_/g, " ")).join(", ") || "measuring"}
                  </span>
                  <span>{dataReadiness.client_signal_trust.next_action}</span>
                  <strong className={dataReadiness.client_signal_trust.execution_enabled ? "tier-strong" : "tier-seed"}>
                    {dataReadiness.client_signal_trust.execution_enabled ? "enabled" : "disabled"}
                  </strong>
                </div>
              </div>
            )}
            {dataReadiness.wallet_state_audit?.by_chain?.length ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Wallet State Freshness</div>
                <div className="alpha-panel-subtitle">
                  Read-only snapshot of RPC provenance. It tells us which chains are fresh enough before using them for Alpha Lab decisions.
                </div>
                <div className="alpha-chain-head">
                  <span>Chain</span>
                  <span>Wallets</span>
                  <span>Trace gaps</span>
                  <span>Stale 24h</span>
                  <span>Quality</span>
                </div>
                {dataReadiness.wallet_state_audit.by_chain.slice(0, 6).map((row) => (
                  <div className="alpha-chain-row" key={`readiness-wallet-fresh-${row.chain}`}>
                    <strong>{row.chain}</strong>
                    <span>{largeNumber(row.wallets)}</span>
                    <span>{largeNumber(row.missing_source_attribution)} attr / {largeNumber(row.missing_label_sources)} labels</span>
                    <span>{largeNumber(row.stale_rows)}</span>
                    <em className={row.avg_quality >= 70 ? "tier-strong" : row.avg_quality >= 45 ? "tier-useful" : "tier-seed"}>
                      {row.avg_quality.toFixed(1)}
                    </em>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}
        {manipulationContract && (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Manipulation Readiness Contract</div>
            <div className="alpha-panel-subtitle">
              Client-safe data contract: ce bloc explique exactement pourquoi Alpha Lab reste en analyse seule avant toute automatisation.
            </div>
            <div className="alpha-metric-grid compact">
              <div className="alpha-metric-card">
                <span>Contract</span>
                <strong className={manipulationContractTone}>
                  {manipulationContract.passed_count}/{manipulationContract.total_count}
                </strong>
                <em>requirements passed</em>
              </div>
              <div className="alpha-metric-card">
                <span>Signal</span>
                <strong className={manipulationContractTone}>
                  {manipulationReadiness ? `${manipulationReadiness.signal_readiness_score}/100` : "WAIT"}
                </strong>
                <em>{manipulationReadiness?.status.replace(/_/g, " ") || "measuring"}</em>
              </div>
              <div className="alpha-metric-card">
                <span>Execution</span>
                <strong className="tier-seed">
                  {manipulationContract.execution_enabled ? "ON" : "OFF"}
                </strong>
                <em>copy {manipulationContract.client_copy_trading_allowed ? "allowed" : "blocked"}</em>
              </div>
              <div className="alpha-metric-card">
                <span>Guarantee</span>
                <strong className="tier-seed">
                  {manipulationContract.profit_guarantee_allowed ? "ALLOWED" : "FORBIDDEN"}
                </strong>
                <em>{manipulationContract.automation_scope.replace(/_/g, " ")}</em>
              </div>
            </div>
            {(manipulationVerdict || holderFlowVerdict) ? (
              <div className="alpha-verdict-panel">
                <div className="alpha-verdict-main">
                  <span className="alpha-kicker">Manipulation Research Verdict</span>
                  <strong className={(manipulationVerdict?.score ?? 0) >= 75 ? "tier-seed" : (manipulationVerdict?.score ?? 0) >= 55 ? "tier-useful" : "tier-strong"}>
                    {(manipulationVerdict?.tier || "inconclusive").replace(/_/g, " ")}
                  </strong>
                  <p>
                    {manipulationVerdict?.plain_summary_fr || "Verdict inconclusive: continue data collection before client-facing signals."}
                  </p>
                  <div className="alpha-verdict-pills">
                    <span>{largeNumber(manipulationVerdict?.score ?? 0)}/100 case score</span>
                    <span>{largeNumber(manipulationVerdict?.confidence_score ?? 0)}/100 confidence</span>
                    <span>{(manipulationVerdict?.direction || "no_local_case").replace(/_/g, " ")}</span>
                  </div>
                </div>
                <div className="alpha-verdict-side">
                  <div>
                    <span>Holder-flow</span>
                    <strong className={holderFlowVerdict?.state === "review_required" ? "tier-useful" : "tier-seed"}>
                      {(holderFlowVerdict?.state || "inconclusive").replace(/_/g, " ")}
                    </strong>
                    <em>{holderFlowVerdict?.plain_summary_fr || "Holder-flow not yet decisive."}</em>
                  </div>
                  <div>
                    <span>Safety lock</span>
                    <strong className="tier-seed">
                      {(manipulationVerdict?.client_execution_enabled || holderFlowVerdict?.client_execution_enabled) ? "EXECUTION ON" : "EXECUTION OFF"}
                    </strong>
                    <em>no copy trading / no profit guarantee</em>
                  </div>
                </div>
                <div className="alpha-verdict-proof-grid">
                  <div>
                    <span>Evidence now</span>
                    <strong title={(manipulationVerdict?.evidence || []).map((item) => item.detail || item.label_fr || item.key).join(" / ")}>
                      {(manipulationVerdict?.evidence || []).slice(0, 3).map((item) => item.label_fr || item.key.replace(/_/g, " ")).join(" / ") || "No strong evidence yet"}
                    </strong>
                  </div>
                  <div>
                    <span>Missing proof</span>
                    <strong title={(manipulationVerdict?.missing_evidence || []).map((item) => item.why_it_matters_fr || item.label_fr || item.key).join(" / ")}>
                      {(manipulationVerdict?.missing_evidence || []).slice(0, 3).map((item) => item.label_fr || item.key.replace(/_/g, " ")).join(" / ") || "No critical missing proof"}
                    </strong>
                  </div>
                  <div>
                    <span>Holder flags</span>
                    <strong title={(holderFlowVerdict?.risk_flags || []).join(" / ")}>
                      {(holderFlowVerdict?.risk_flags || []).slice(0, 3).map((item) => item.replace(/_/g, " ")).join(" / ") || "Holder risk inconclusive"}
                    </strong>
                  </div>
                  <div>
                    <span>Next safe action</span>
                    <strong>
                      {holderFlowVerdict?.recommended_action_id?.replace(/_/g, " ") || manipulationContract.automation_decision?.first_client_diagnostic?.title_fr || "Watch only"}
                    </strong>
                  </div>
                </div>
                <div className="alpha-verdict-policy" title={`${manipulationVerdict?.source_policy || ""} ${holderFlowVerdict?.source_policy || ""}`}>
                  <span>{holderFlowVerdict?.basis?.holder_snapshot_available ? `${largeNumber(holderFlowVerdict.basis.holder_snapshot_tokens ?? 0)} holder snapshots` : "snapshot missing or proxy-only"}</span>
                  <span>{holderFlowVerdict?.basis?.source || "local evidence only"}</span>
                  <span>source_policy preserved</span>
                </div>
              </div>
            ) : null}
            <div className="alpha-data-room-toggle">
              <div>
                <span>Technical data room</span>
                <strong>
                  {showManipulationDataRoom
                    ? "Detailed evidence visible"
                    : `${largeNumber(manipulationContract.failed_count)} blockers hidden behind a cleaner client view`}
                </strong>
                <em>
                  Transfer lanes, CEX deposits, funding graph, gap closure and diagnostics stay available without overwhelming the client.
                </em>
              </div>
              <button className="alpha-mini-button" onClick={() => setShowManipulationDataRoom((value) => !value)}>
                {showManipulationDataRoom ? "Hide data room" : "Open data room"}
              </button>
            </div>
            {showManipulationDataRoom ? (
              <>
            <div className="alpha-chain-head">
              <span>Requirement</span>
              <span>Current</span>
              <span>Target</span>
              <span>Gap</span>
              <span>Next</span>
            </div>
            {manipulationContract.failed_requirements.slice(0, 5).map((row) => (
              <div className="alpha-chain-row" key={`manip-readiness-${row.id}`}>
                <strong>{row.label_fr}</strong>
                <span>{largeNumber(row.current)} {row.unit}</span>
                <span>{row.direction === "minimum" ? ">=" : "<="} {largeNumber(row.target)} {row.unit}</span>
                <em className={row.passed ? "tier-strong" : "tier-seed"}>
                  {row.direction === "minimum"
                    ? `${largeNumber(row.missing || 0)} missing`
                    : `${largeNumber(row.excess || 0)} excess`}
                </em>
                <span>{row.recommended_action_id.replace(/_/g, " ")}</span>
              </div>
            ))}
            <div className="alpha-chain-row">
              <span>{manipulationContract.plain_summary_fr}</span>
              <strong>{manipulationContract.failed_count ? `${largeNumber(manipulationContract.failed_count)} blockers` : "ready for watchlist"}</strong>
              <span>{manipulationReadiness?.blockers.slice(0, 2).map((item) => item.replace(/_/g, " ")).join(", ") || "no blockers"}</span>
              <span>{manipulationReadiness?.next_actions[0] || "Keep observing data quality."}</span>
              <em>{manipulationContract.source_policy.replace("read-only ", "")}</em>
            </div>
            {manipulationContract.automation_decision ? (
              <div className="alpha-chain-row">
                <strong>{manipulationContract.automation_decision.status.replace(/_/g, " ")}</strong>
                <span>{manipulationContract.automation_decision.client_mode.replace(/_/g, " ")}</span>
                <span>
                  {manipulationContract.automation_decision.first_client_diagnostic?.title_fr
                    || manipulationContract.automation_decision.first_client_diagnostic?.action.title_fr
                    || "read-only diagnostics only"}
                </span>
                <span title={manipulationContract.automation_decision.client_cannot_do.join(" / ")}>
                  blocked: {manipulationContract.automation_decision.client_cannot_do.slice(0, 2).map((item) => item.replace(/_/g, " ")).join(", ")}
                </span>
                <em>{manipulationContract.automation_decision.plain_summary_fr}</em>
              </div>
            ) : null}
            {manipulationTokenTransferLane ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Token Transfer Evidence Lane</div>
                <div className="alpha-panel-subtitle">
                  ERC20/BEP20 Transfer depth used to confirm CEX deposits and holder-flow trails before any client automation.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card">
                    <span>Transfer rows</span>
                    <strong className={(manipulationTokenTransferLane.summary?.token_transfer_rows ?? 0) >= 500 ? "tier-strong" : "tier-seed"}>
                      {largeNumber(manipulationTokenTransferLane.summary?.token_transfer_rows ?? 0)}
                    </strong>
                    <em>{Number(manipulationTokenTransferLane.summary?.history_days ?? 0).toFixed(1)}d history</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Surface</span>
                    <strong>{largeNumber(manipulationTokenTransferLane.summary?.distinct_tokens ?? 0)}</strong>
                    <em>{largeNumber(manipulationTokenTransferLane.summary?.chains ?? 0)} chains / {largeNumber(manipulationTokenTransferLane.summary?.from_wallets ?? 0)} senders</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Proof status</span>
                    <strong className={(manipulationTokenTransferLane.blockers || []).length ? "tier-seed" : "tier-strong"}>
                      {(manipulationTokenTransferLane.blockers || []).length ? "BLOCKED" : "USABLE"}
                    </strong>
                    <em title={(manipulationTokenTransferLane.blockers || []).join(" / ")}>
                      {(manipulationTokenTransferLane.blockers || [])[0]?.replace(/_/g, " ") || "no transfer blocker"}
                    </em>
                  </div>
                </div>
                {(manipulationTokenTransferLane.by_chain || []).length ? (
                  <>
                    <div className="alpha-chain-head">
                      <span>Chain</span>
                      <span>Rows</span>
                      <span>Tokens</span>
                      <span>Wallets</span>
                      <span>History</span>
                    </div>
                    {(manipulationTokenTransferLane.by_chain || []).slice(0, 4).map((row) => (
                      <div className="alpha-chain-row" key={`manip-token-transfer-${row.chain}`}>
                        <strong>{row.chain || "unknown"}</strong>
                        <span>{largeNumber(row.token_transfer_rows ?? 0)}</span>
                        <span>{largeNumber(row.distinct_tokens ?? 0)}</span>
                        <span>{largeNumber(row.from_wallets ?? 0)} from / {largeNumber(row.to_wallets ?? 0)} to</span>
                        <em>{Number(row.history_days ?? 0).toFixed(1)}d</em>
                      </div>
                    ))}
                  </>
                ) : null}
              </div>
            ) : null}
            {manipulationCexDepositLane ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">CEX Token Deposit Lane</div>
                <div className="alpha-panel-subtitle">
                  Read-only candidate deposits into exchange-like wallets. Useful for Bitget/Gate/Binance pre-pump investigations, not proof of intent.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card">
                    <span>Coordination risk</span>
                    <strong className={(manipulationCexDepositLane.summary?.coordination_score ?? 0) >= 50 ? "tier-useful" : "tier-seed"}>
                      {largeNumber(manipulationCexDepositLane.summary?.coordination_score ?? 0)}/100
                    </strong>
                    <em title={(manipulationCexDepositLane.summary?.coordination_factors || []).join(" / ")}>
                      {(manipulationCexDepositLane.summary?.coordination_tier || "insufficient_evidence").replace(/_/g, " ")}
                    </em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Timing cluster</span>
                    <strong className={(manipulationCexDepositLane.temporal_profile?.clustered_6h ?? false) ? "tier-useful" : "tier-seed"}>
                      {largeNumber(manipulationCexDepositLane.temporal_profile?.max_deposits_6h ?? 0)}
                    </strong>
                    <em>
                      {Number(manipulationCexDepositLane.temporal_profile?.deposit_span_minutes ?? 0).toFixed(1)} min span
                    </em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Swap corroboration</span>
                    <strong className={(manipulationCexDepositLane.swap_corroboration?.summary?.swap_rows_around_deposits ?? 0) > 0 ? "tier-useful" : "tier-seed"}>
                      {largeNumber(manipulationCexDepositLane.swap_corroboration?.summary?.swap_rows_around_deposits ?? 0)}
                    </strong>
                    <em>
                      {largeNumber(manipulationCexDepositLane.swap_corroboration?.summary?.swap_rows_after_24h ?? 0)} after 24h
                    </em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Price proxy</span>
                    <strong className={(manipulationCexDepositLane.price_proxy_profile?.summary?.tokens_with_before_after_price_proxy ?? 0) > 0 ? "tier-useful" : "tier-seed"}>
                      {Number(manipulationCexDepositLane.price_proxy_profile?.summary?.max_before_after_change_pct ?? 0).toFixed(1)}%
                    </strong>
                    <em>
                      {largeNumber(manipulationCexDepositLane.price_proxy_profile?.summary?.tokens_with_before_after_price_proxy ?? 0)} before/after tokens
                    </em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Holder-flow proxy</span>
                    <strong className={(manipulationCexDepositLane.holder_flow_profile?.summary?.high_cex_flow_share_tokens ?? 0) > 0 ? "tier-useful" : "tier-seed"}>
                      {Number(manipulationCexDepositLane.holder_flow_profile?.summary?.max_cex_deposit_share_of_observed_flow_pct ?? 0).toFixed(1)}%
                    </strong>
                    <em>
                      {largeNumber(manipulationCexDepositLane.holder_flow_profile?.summary?.tokens_profiled ?? 0)} profiled tokens
                    </em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Holder snapshot</span>
                    <strong className={(manipulationCexDepositLane.holder_flow_profile?.summary?.holder_supply_snapshot_tokens ?? 0) > 0 ? "tier-useful" : "tier-seed"}>
                      {largeNumber(manipulationCexDepositLane.holder_flow_profile?.summary?.holder_supply_snapshot_tokens ?? 0)}
                    </strong>
                    <em>
                      top holder {Number(manipulationCexDepositLane.holder_flow_profile?.summary?.max_top_holder_share_pct ?? 0).toFixed(1)}%
                    </em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Snapshot queue</span>
                    <strong className={(manipulationCexDepositLane.summary?.holder_snapshot_refresh_needed ?? 0) > 0 ? "tier-useful" : "tier-strong"}>
                      {largeNumber(manipulationCexDepositLane.summary?.holder_snapshot_refresh_needed ?? 0)}
                    </strong>
                    <em>admin refresh candidates</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Deposits</span>
                    <strong className={(manipulationCexDepositLane.summary?.deposits ?? 0) > 0 ? "tier-useful" : "tier-seed"}>
                      {largeNumber(manipulationCexDepositLane.summary?.deposits ?? 0)}
                    </strong>
                    <em>{largeNumber(manipulationCexDepositLane.summary?.depositing_wallets ?? 0)} depositing wallets</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Fresh-like depositors</span>
                    <strong className={(manipulationCexDepositLane.summary?.fresh_like_depositors ?? 0) > 0 ? "tier-useful" : "tier-strong"}>
                      {largeNumber(manipulationCexDepositLane.summary?.fresh_like_depositors ?? 0)}
                    </strong>
                    <em>{largeNumber(manipulationCexDepositLane.summary?.missing_state_depositors ?? 0)} missing wallet state</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Exchange targets</span>
                    <strong>
                      {largeNumber(manipulationCexDepositLane.summary?.source_backed_target_wallets ?? 0)}
                      /{largeNumber(manipulationCexDepositLane.summary?.target_exchange_wallets ?? 0)}
                    </strong>
                    <em>source-backed targets</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>CEX proof status</span>
                    <strong className={(manipulationCexDepositLane.blockers || []).includes("no_cex_token_deposit_rows") ? "tier-seed" : "tier-useful"}>
                      {(manipulationCexDepositLane.blockers || []).includes("no_cex_token_deposit_rows") ? "NO ROWS" : "REVIEW"}
                    </strong>
                    <em title={(manipulationCexDepositLane.blockers || []).join(" / ")}>
                      {(manipulationCexDepositLane.blockers || [])[0]?.replace(/_/g, " ") || "review deposits"}
                    </em>
                  </div>
                </div>
                {(manipulationCexDepositLane.holder_flow_profile?.rows || []).length ? (
                  <>
                    <div className="alpha-panel-title mini" style={{ marginTop: 12 }}>Holder-Flow Impact Proxy</div>
                    <div className="alpha-panel-subtitle">
                      Local transfer-flow concentration for deposited tokens. This is a supply-impact hint until true holder snapshots are indexed.
                    </div>
                    <div className="alpha-chain-head">
                      <span>Token</span>
                      <span>CEX share</span>
                      <span>Fresh-like value</span>
                      <span>Observed flow</span>
                      <span>Status</span>
                    </div>
                    {(manipulationCexDepositLane.holder_flow_profile?.rows || []).slice(0, 4).map((row) => (
                      <div className="alpha-chain-row" key={`holder-flow-${row.chain}-${row.token}`}>
                        <strong title={row.token || ""}>{row.token_symbol || shortId(row.token || "")}</strong>
                        <span>{Number(row.cex_deposit_share_of_observed_flow_pct ?? 0).toFixed(1)}% / {largeNumber(row.cex_deposit_rows ?? 0)} deposits</span>
                        <span>{Number(row.fresh_like_cex_value_share_pct ?? 0).toFixed(1)}% fresh / top3 {Number(row.top3_depositor_cex_share_pct ?? 0).toFixed(1)}%</span>
                        <span>
                          {row.holder_supply_snapshot_available
                            ? `${Number(row.cex_deposit_supply_share_pct ?? 0).toFixed(2)}% supply`
                            : row.observed_value_display != null
                              ? largeNumber(row.observed_value_display)
                              : `${largeNumber(row.local_transfer_rows ?? 0)} rows`}
                        </span>
                        <em className={row.holder_supply_snapshot_available ? "tier-strong" : "tier-seed"}>
                          {row.holder_supply_snapshot_available
                            ? `${largeNumber(row.holder_rows ?? 0)} holders`
                            : "proxy only"}
                        </em>
                      </div>
                    ))}
                  </>
                ) : null}
                {manipulationCexDepositLane.funding_graph ? (
                  <>
                    <div className="alpha-panel-title mini" style={{ marginTop: 12 }}>Depositor Funding Graph</div>
                    <div className="alpha-panel-subtitle">
                      Native funding edges into deposit senders. This helps separate fresh-wallet coordination from normal exchange withdrawal noise.
                    </div>
                    <div className="alpha-metric-grid compact">
                      <div className="alpha-metric-card">
                        <span>Funding edges</span>
                        <strong className={(manipulationCexDepositLane.funding_graph.summary?.funding_edges ?? 0) > 0 ? "tier-useful" : "tier-seed"}>
                          {largeNumber(manipulationCexDepositLane.funding_graph.summary?.funding_edges ?? 0)}
                        </strong>
                        <em>{largeNumber(manipulationCexDepositLane.funding_graph.summary?.funded_depositors ?? 0)} funded depositors</em>
                      </div>
                      <div className="alpha-metric-card">
                        <span>Fresh funded</span>
                        <strong className={(manipulationCexDepositLane.funding_graph.summary?.fresh_like_depositors_with_funding ?? 0) > 0 ? "tier-useful" : "tier-seed"}>
                          {largeNumber(manipulationCexDepositLane.funding_graph.summary?.fresh_like_depositors_with_funding ?? 0)}
                        </strong>
                        <em>{largeNumber(manipulationCexDepositLane.funding_graph.summary?.fresh_like_depositors_without_funding ?? 0)} still missing</em>
                      </div>
                      <div className="alpha-metric-card">
                        <span>Unknown funders</span>
                        <strong className={(manipulationCexDepositLane.funding_graph.summary?.unknown_funders ?? 0) > 0 ? "tier-seed" : "tier-strong"}>
                          {largeNumber(manipulationCexDepositLane.funding_graph.summary?.unknown_funders ?? 0)}
                        </strong>
                        <em>{largeNumber(manipulationCexDepositLane.funding_graph.summary?.source_backed_funders ?? 0)} source-backed</em>
                      </div>
                      <div className="alpha-metric-card">
                        <span>CEX-like funders</span>
                        <strong className={(manipulationCexDepositLane.funding_graph.summary?.exchange_like_funders ?? 0) > 0 ? "tier-useful" : "tier-strong"}>
                          {largeNumber(manipulationCexDepositLane.funding_graph.summary?.exchange_like_funders ?? 0)}
                        </strong>
                        <em>false-positive risk</em>
                      </div>
                      <div className="alpha-metric-card">
                        <span>Shared funders</span>
                        <strong className={(manipulationCexDepositLane.funding_graph.summary?.shared_unknown_funders ?? 0) > 0 ? "tier-useful" : "tier-strong"}>
                          {largeNumber(manipulationCexDepositLane.funding_graph.summary?.shared_funders ?? 0)}
                        </strong>
                        <em>{largeNumber(manipulationCexDepositLane.funding_graph.summary?.shared_unknown_funders ?? 0)} unknown shared</em>
                      </div>
                    </div>
                    {(manipulationCexDepositLane.funding_graph.shared_funders || []).length ? (
                      <>
                        <div className="alpha-chain-head">
                          <span>Shared funder</span>
                          <span>Deposit wallets</span>
                          <span>Fresh-like</span>
                          <span>Native value</span>
                          <span>Status</span>
                        </div>
                        {(manipulationCexDepositLane.funding_graph.shared_funders || []).slice(0, 3).map((funder) => (
                          <div className="alpha-chain-row" key={`cex-shared-funder-${funder.funder}`}>
                            <strong title={funder.funder || ""}>{shortId(funder.funder || "")}</strong>
                            <span>{largeNumber(funder.funded_depositors ?? 0)} funded</span>
                            <span>{largeNumber(funder.fresh_like_depositors ?? 0)} fresh-like</span>
                            <span>{Number(funder.total_native_value ?? 0).toFixed(4)}</span>
                            <em className={funder.exchange_like ? "tier-useful" : funder.source_backed ? "tier-strong" : "tier-seed"}>
                              {funder.exchange_like
                                ? "exchange-like"
                                : funder.source_backed
                                  ? "source-backed"
                                  : funder.unknown ? "unknown" : "known"}
                            </em>
                          </div>
                        ))}
                      </>
                    ) : null}
                    {(manipulationCexDepositLane.funding_graph.edges || []).length ? (
                      <>
                        <div className="alpha-chain-head">
                          <span>Chain</span>
                          <span>Funder</span>
                          <span>Depositor</span>
                          <span>Native value</span>
                          <span>Status</span>
                        </div>
                        {(manipulationCexDepositLane.funding_graph.edges || []).slice(0, 4).map((edge) => (
                          <div className="alpha-chain-row" key={`cex-funding-edge-${edge.chain}-${edge.tx_hash}-${edge.to_depositor}`}>
                            <strong>{edge.chain || "unknown"}</strong>
                            <span title={edge.from_addr || ""}>{edge.funder_entity || edge.funder_label || shortId(edge.from_addr || "")}</span>
                            <span title={edge.to_depositor || ""}>{shortId(edge.to_depositor || "")}</span>
                            <span>{Number(edge.value_native ?? 0).toFixed(4)}</span>
                            <em className={edge.funder_exchange_like ? "tier-useful" : edge.funder_source_backed ? "tier-strong" : "tier-seed"}>
                              {edge.funder_exchange_like
                                ? "exchange-like"
                                : edge.funder_source_backed
                                  ? "source-backed"
                                  : edge.funder_known ? "known" : "unknown"}
                            </em>
                          </div>
                        ))}
                      </>
                    ) : null}
                  </>
                ) : null}
                {(manipulationCexDepositLane.aggregates?.by_target_entity || []).length ? (
                  <>
                    <div className="alpha-chain-head">
                      <span>Exchange</span>
                      <span>Deposits</span>
                      <span>Wallets</span>
                      <span>Resolved amount</span>
                      <span>Proof</span>
                    </div>
                    {(manipulationCexDepositLane.aggregates?.by_target_entity || []).slice(0, 3).map((row) => (
                      <div className="alpha-chain-row" key={`cex-aggregate-exchange-${row.key}`}>
                        <strong>{row.key}</strong>
                        <span>{largeNumber(row.deposits)} deposits / {largeNumber(row.tokens)} tokens</span>
                        <span>{largeNumber(row.depositing_wallets)} from / {largeNumber(row.fresh_like_depositors)} fresh-like</span>
                        <span>
                          {row.resolved_amount_rows
                            ? `${largeNumber(row.resolved_value_total)} resolved`
                            : `${largeNumber(row.raw_amount_rows)} raw rows`}
                        </span>
                        <em className={row.source_backed_target_wallets >= row.target_wallets ? "tier-strong" : "tier-seed"}>
                          {largeNumber(row.source_backed_target_wallets)}/{largeNumber(row.target_wallets)} backed
                        </em>
                      </div>
                    ))}
                  </>
                ) : null}
                {(manipulationCexDepositLane.aggregates?.by_token || []).length ? (
                  <>
                    <div className="alpha-chain-head">
                      <span>Token</span>
                      <span>Deposits</span>
                      <span>Exchange targets</span>
                      <span>Resolved amount</span>
                      <span>Chains</span>
                    </div>
                    {(manipulationCexDepositLane.aggregates?.by_token || []).slice(0, 3).map((row) => (
                      <div className="alpha-chain-row" key={`cex-aggregate-token-${row.key}`}>
                        <strong>{row.key}</strong>
                        <span>{largeNumber(row.deposits)} deposits</span>
                        <span>{largeNumber(row.target_wallets)} targets / {largeNumber(row.source_backed_target_wallets)} backed</span>
                        <span>
                          {row.resolved_amount_rows
                            ? `${largeNumber(row.resolved_value_total)} resolved`
                            : `${largeNumber(row.raw_amount_rows)} raw rows`}
                        </span>
                        <em>{largeNumber(row.chains)} chains</em>
                      </div>
                    ))}
                  </>
                ) : null}
                {(manipulationCexDepositLane.rows || []).length ? (
                  <>
                    <div className="alpha-chain-head">
                      <span>Chain</span>
                      <span>Target</span>
                      <span>Amount</span>
                      <span>Depositor</span>
                      <span>Proof</span>
                    </div>
                    {(manipulationCexDepositLane.rows || []).slice(0, 4).map((row) => (
                      <div className="alpha-chain-row" key={`cex-token-deposit-${row.chain}-${row.tx_hash}-${row.to_addr}`}>
                        <strong>{row.chain || "unknown"}</strong>
                        <span title={row.to_addr || ""}>{row.target_entity || row.target_label || shortId(row.to_addr || "")}</span>
                        <span title={row.value_raw || row.token || ""}>
                          {row.value_display != null
                            ? `${largeNumber(row.value_display)} ${row.token_symbol || shortId(row.token || "")}`
                            : `raw ${shortId(row.token || "")}`}
                        </span>
                        <em className={row.depositor_fresh_like ? "tier-useful" : row.depositor_source_backed ? "tier-strong" : "tier-seed"}>
                          {row.depositor_fresh_like
                            ? "fresh-like"
                            : row.depositor_source_backed
                              ? "source-backed"
                              : row.depositor_has_wallet_state ? "known state" : "missing state"}
                        </em>
                        <span title={row.proof_status || ""}>{(row.proof_status || "pending").replace(/_/g, " ")}</span>
                      </div>
                    ))}
                  </>
                ) : null}
              </div>
            ) : null}
            {manipulationContract.missing_data_summary ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Missing Data For Client Automation</div>
                <div className="alpha-panel-subtitle">
                  Ce bloc liste les donnees qui manquent encore avant une automatisation client fiable. Execution et profit guarantee restent bloques.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card">
                    <span>Total gaps</span>
                    <strong>{largeNumber(manipulationContract.missing_data_summary.total_gaps)}</strong>
                    <em>{manipulationContract.missing_data_summary.client_automation_ready ? "automation-ready" : "blocked"}</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>Critical</span>
                    <strong className={manipulationContract.missing_data_summary.critical_gaps ? "tier-seed" : "tier-strong"}>
                      {largeNumber(manipulationContract.missing_data_summary.critical_gaps)}
                    </strong>
                    <em>must fix first</em>
                  </div>
                  <div className="alpha-metric-card">
                    <span>High</span>
                    <strong className={manipulationContract.missing_data_summary.high_gaps ? "tier-useful" : "tier-strong"}>
                      {largeNumber(manipulationContract.missing_data_summary.high_gaps)}
                    </strong>
                    <em>{manipulationContract.missing_data_summary.top_categories.slice(0, 3).join(", ") || "no gaps"}</em>
                  </div>
                </div>
                <div className="alpha-chain-head">
                  <span>Data gap</span>
                  <span>Severity</span>
                  <span>Current / target</span>
                  <span>Source</span>
                  <span>Why</span>
                </div>
                {(manipulationContract.automation_data_gaps || []).slice(0, 6).map((gap) => (
                  <div className="alpha-chain-row" key={`automation-data-gap-${gap.id}`}>
                    <strong>{gap.label_fr}</strong>
                    <em className={gap.severity === "critical" ? "tier-seed" : gap.severity === "high" ? "tier-useful" : "tier-strong"}>
                      {gap.severity}
                    </em>
                    <span>{largeNumber(gap.current)} / {largeNumber(gap.target)} {gap.unit}</span>
                    <span>{gap.data_source}</span>
                    <span title={gap.why_it_matters_fr}>{gap.next_action_id.replace(/_/g, " ")}</span>
                  </div>
                ))}
                {manipulationContract.gap_closure_plan?.steps.length ? (
                  <>
                    <div className="alpha-panel-title mini" style={{ marginTop: 12 }}>Gap Closure Plan</div>
                    <div className="alpha-panel-subtitle">
                      Ordre recommande pour combler les gaps data. Les etapes admin restent bloquees derriere token/confirm; aucune execution client.
                    </div>
                    <div className="alpha-chain-head">
                      <span>Phase</span>
                      <span>Gap</span>
                      <span>Action</span>
                      <span>Guard</span>
                      <span>Status</span>
                    </div>
                    {manipulationContract.gap_closure_plan.steps.slice(0, 6).map((step) => (
                      <div className="alpha-chain-row" key={`gap-closure-${step.phase}-${step.gap_id}`}>
                        <strong>{step.phase_title_fr}</strong>
                        <span>{step.gap_label_fr} / {largeNumber(step.gap)} {step.unit}</span>
                        <span>{step.method} {step.endpoint.replace("/api", "")}</span>
                        <span>
                          {step.admin_required ? "admin" : "read-only"}
                          {step.dry_run ? " / dry-run" : ""}
                        </span>
                        <em>{step.status.replace(/_/g, " ")}</em>
                      </div>
                    ))}
                  </>
                ) : null}
              </div>
            ) : null}
            {(manipulationContract.client_visible_actions || []).length ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Next Safe Diagnostics</div>
                <div className="alpha-panel-subtitle">
                  Read-only diagnostics only. Admin writes and copy execution stay hidden from the client flow.
                </div>
                <div className="alpha-chain-head">
                  <span>Priority</span>
                  <span>Why</span>
                  <span>Method</span>
                  <span>Endpoint</span>
                </div>
                {(manipulationContract.client_visible_actions || []).map((item) => (
                  <div className="alpha-chain-row" key={`client-safe-action-${item.action.id}-${item.requirement_id}`}>
                    <strong>{item.title_fr || item.action.title_fr}</strong>
                    <span>{item.requirement_label_fr} / gap {largeNumber(item.gap)} {item.gap_unit}</span>
                    <em>{item.method}</em>
                    <span>{item.endpoint.replace("/api", "")}</span>
                  </div>
                ))}
              </div>
            ) : null}
              </>
            ) : null}
          </div>
        )}
        {manipulationCaseFile && (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Manipulation Case Files</div>
            <div className="alpha-panel-subtitle">
              Research-only dossier: timing, wallets, clusters and funders in one view. Copy trading and execution stay disabled.
            </div>
            <div className="alpha-metric-grid compact">
              <div className="alpha-metric-card">
                <span>Cases</span>
                <strong>{largeNumber(manipulationCaseFile.summary.case_files)}</strong>
                <em>{largeNumber(manipulationCaseFile.summary.client_ready_cases)} client-ready</em>
              </div>
              <div className="alpha-metric-card">
                <span>False-positive risk</span>
                <strong className={manipulationCaseFile.summary.high_false_positive_risk_funders ? "tier-seed" : "tier-strong"}>
                  {largeNumber(manipulationCaseFile.summary.high_false_positive_risk_funders)}
                </strong>
                <em>CEX-like or upstream CEX funders</em>
              </div>
              <div className="alpha-metric-card">
                <span>Gas fan-out</span>
                <strong className={manipulationCaseFile.summary.gas_fanout_funders ? "tier-useful" : "tier-strong"}>
                  {largeNumber(manipulationCaseFile.summary.gas_fanout_funders || 0)}
                </strong>
                <em>shared gas funders before breakout</em>
              </div>
              <div className="alpha-metric-card">
                <span>Pre-event CEX</span>
                <strong className={manipulationCaseFile.summary.pre_event_cex_deposit_funders ? "tier-useful" : "tier-strong"}>
                  {largeNumber(manipulationCaseFile.summary.pre_event_cex_deposit_funders || 0)}
                </strong>
                <em>deposit hints before breakout</em>
              </div>
              <div className="alpha-metric-card">
                <span>Timing realism</span>
                <strong className={manipulationCaseFile.summary.only_unrealistic_policy_profitable ? "tier-seed" : "tier-useful"}>
                  {manipulationCaseFile.summary.only_unrealistic_policy_profitable ? "UNREALISTIC EDGE" : "MEASURED"}
                </strong>
                <em>event-entry hindsight is separated</em>
              </div>
            </div>
            <div className="alpha-chain-head">
              <span>Token</span>
              <span>Evidence</span>
              <span>Funder risk</span>
              <span>Decision</span>
            </div>
            {manipulationCaseFile.rows.length ? manipulationCaseFile.rows.slice(0, 4).map((row) => {
              const topFunder = row.funder_graph[0]
              const freshWallets = row.wallet_profiles.filter((wallet) => wallet.is_fresh_wallet).length
              const clusters = row.clusters.length
              const bestStrategy = row.strategy.strategies
                .filter((item) => item.client_candidate)
                .sort((a, b) => Number(b.pnl_usd || 0) - Number(a.pnl_usd || 0))[0]
              return (
                <div className="alpha-chain-row" key={`manip-case-${row.chain}-${row.token}-${row.event_timestamp || 0}`}>
                  <strong title={row.token}>{row.chain}:{shortId(row.token)}</strong>
                  <span>
                    {largeNumber(row.wallet_profiles.length)} wallets / {largeNumber(freshWallets)} fresh / {largeNumber(clusters)} clusters
                  </span>
                  <span title={(topFunder?.risk_flags || []).join(" / ")}>
                    {topFunder
                      ? `${topFunder.classification.replace(/_/g, " ")} / ${topFunder.false_positive_risk}${topFunder.gas_fanout_profile?.detected ? ` / gas fan-out ${topFunder.gas_fanout_profile.wallet_count || 0}w` : ""}${topFunder.cex_deposit_profile?.detected ? ` / CEX deposit ${topFunder.cex_deposit_profile.deposit_count || 0}` : ""}`
                      : "no shared funder"}
                  </span>
                  <span title={row.blockers.join(" / ")}>
                    {bestStrategy
                      ? `${Number(bestStrategy.return_pct || 0).toFixed(2)}% after ${bestStrategy.exit_after_swaps} swaps`
                      : row.verdict.replace(/_/g, " ")}
                  </span>
                </div>
              )
            }) : (
              <div className="alpha-empty">
                No manipulation case files yet. We need more exact swap history before this becomes useful.
              </div>
            )}
            <div className="alpha-chain-row">
              <span title={manipulationCaseFile.blockers.join(" / ")}>
                {manipulationCaseFile.blockers.slice(0, 3).map((blocker) => blocker.replace(/_/g, " ")).join(", ") || "no blockers"}
              </span>
              <strong title={manipulationCaseFile.next_actions.join(" / ")}>
                {manipulationCaseFile.next_actions[0] || "Keep collecting exact swaps and source-backed labels."}
              </strong>
              <span>{manipulationCaseFile.source_policy.replace("read-only ", "")}</span>
              <strong className="tier-seed">RESEARCH ONLY</strong>
            </div>
          </div>
        )}
        <div className="alpha-chain-coverage">
          <div className="alpha-panel-title mini">Entity RPC Coverage</div>
          <div className="alpha-panel-subtitle">
            Priorite label-first: on mesure les entites importantes avant toute ingestion massive.
          </div>
          <div className="alpha-chain-head">
            <span>Entity</span>
            <span>Labels</span>
            <span>RPC wallets</span>
            <span>RPC value</span>
            <span>Quality</span>
            <span>Fresh / contracts</span>
          </div>
          {priorityCoverageRows.length > 0 ? priorityCoverageRows.map((row) => (
            <div className="alpha-chain-row" key={`entity-cov-${row.entity}`}>
              <strong>{row.entity}</strong>
              <span>{largeNumber(row.labelled_wallets)}</span>
              <span>{largeNumber(row.rpc_wallets)} / {row.rpc_coverage_pct.toFixed(1)}%</span>
              <span>{money(row.rpc_native_value_usd)}</span>
              <em className={row.avg_quality_score >= 70 ? "tier-strong" : row.avg_quality_score >= 45 ? "tier-useful" : "tier-seed"}>
                {row.avg_quality_score.toFixed(1)}
              </em>
              <span>{row.fresh_wallets} fresh / {row.contract_wallets} contracts</span>
            </div>
          )) : (
            <div className="alpha-empty">
              No entity RPC coverage loaded yet. Build labels first, then enrich high-value entities.
            </div>
          )}
        </div>
        {entityGaps?.rows?.length ? (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Priority Entity Gaps</div>
            <div className="alpha-panel-subtitle">
              Ce tableau dit quoi faire ensuite sans spammer les RPC ni melanger les sources.
            </div>
            <div className="alpha-chain-head">
              <span>Entity</span>
              <span>Status</span>
              <span>Labels</span>
              <span>RPC</span>
              <span>Next action</span>
              <span>Score</span>
            </div>
            {entityGaps.rows.slice(0, 8).map((row) => (
              <div className="alpha-chain-row" key={`entity-gap-${row.entity}`}>
                <strong>{row.entity}</strong>
                <em className={row.status === "usable_seed" ? "tier-strong" : row.status === "partial_rpc" ? "tier-useful" : "tier-seed"}>
                  {row.status.replace(/_/g, " ")}
                </em>
                <span>{largeNumber(row.labelled_wallets)}</span>
                <span>{largeNumber(row.rpc_wallets)} / {row.rpc_coverage_pct.toFixed(1)}%</span>
                <span>{row.next_action}</span>
                <strong>{row.priority_score}</strong>
              </div>
            ))}
          </div>
        ) : null}
        {entityChainGaps?.rows?.length ? (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Entity Chain Gaps</div>
            <div className="alpha-panel-subtitle">
              Le vrai backlog RPC: entite + chain. C'est plus precis que l'ancien score global.
            </div>
            <div className="alpha-chain-head">
              <span>Entity</span>
              <span>Chain</span>
              <span>Missing</span>
              <span>RPC coverage</span>
              <span>Next action</span>
              <span>Score</span>
            </div>
            {entityChainGaps.rows.slice(0, 8).map((row) => (
              <div className="alpha-chain-row" key={`entity-chain-gap-${row.entity}-${row.chain}`}>
                <strong>{row.entity}</strong>
                <em className={row.missing_wallets <= 2 ? "tier-strong" : row.rpc_coverage_pct >= 50 ? "tier-useful" : "tier-seed"}>
                  {row.chain}
                </em>
                <span>{row.missing_wallets} / {row.labelled_wallets}</span>
                <span>{row.rpc_wallets} / {row.rpc_coverage_pct.toFixed(1)}%</span>
                <span>{row.next_action}</span>
                <strong>{row.priority_score}</strong>
              </div>
            ))}
          </div>
        ) : null}
        {entityChainGapVerification?.rows?.length ? (
          <div className="alpha-chain-coverage">
            <div className="alpha-panel-title mini">Gap Verification Gate</div>
            <div className="alpha-panel-subtitle">
              Read-only preflight before enrichment: verifies the next entity-chain gaps are consistent, traceable and not hiding stale/low-quality wallet state.
            </div>
            <div className="alpha-metric-grid compact">
              <div className="alpha-metric-card"><span>Reviewed</span><strong>{largeNumber(entityChainGapVerification.summary.rows_reviewed)}</strong><em>entity-chain gaps</em></div>
              <div className="alpha-metric-card"><span>Safe</span><strong className="tier-strong">{largeNumber(entityChainGapVerification.summary.safe_to_enrich)}</strong><em>can enrich directly</em></div>
              <div className="alpha-metric-card"><span>Audit first</span><strong className="tier-useful">{largeNumber(entityChainGapVerification.summary.needs_audit_first)}</strong><em>refresh existing rows first</em></div>
              <div className="alpha-metric-card"><span>Blocked</span><strong className="tier-seed">{largeNumber(entityChainGapVerification.summary.blocked)}</strong><em>inconsistent gap inputs</em></div>
            </div>
            <div className="alpha-chain-head">
              <span>Entity</span>
              <span>Chain</span>
              <span>Status</span>
              <span>Trace</span>
              <span>Data debt</span>
              <span>Action</span>
            </div>
            {entityChainGapVerification.rows.slice(0, 8).map((row) => (
              <div className="alpha-chain-row" key={`entity-chain-gap-verify-${row.entity}-${row.chain}`}>
                <strong>{row.entity}</strong>
                <em className={row.verification_status === "safe_to_enrich" ? "tier-strong" : row.verification_status === "enrich_but_audit_existing_rows" ? "tier-useful" : "tier-seed"}>
                  {row.chain}
                </em>
                <span title={row.blockers.join(" / ")}>{row.verification_status.replace(/_/g, " ")}</span>
                <span>{row.traceability_pct.toFixed(1)}%</span>
                <span>{largeNumber(row.stale_rows)} stale / {largeNumber(row.low_quality_rows)} low / {largeNumber(row.missing_source_attribution)} attr</span>
                <strong>{row.recommended_action.replace(/_/g, " ")}</strong>
              </div>
            ))}
          </div>
        ) : null}
        {isLocalAdminSurface && (
          <div className="alpha-chain-coverage alpha-admin-ops">
            <div className="alpha-panel-title mini">Local Admin Data Ops</div>
            <div className="alpha-panel-subtitle">
              Hidden on remote client URLs. Automated priority enrichment is audited and can be stopped here.
            </div>
            <div className="alpha-live-pill" style={{ width: "fit-content", marginBottom: 10 }}>
              <span className={`live-dot ${autoEnrichStatus?.running ? "connected" : ""}`} />
              auto enrich {autoEnrichStatus?.running ? "running" : "stopped"}
              {autoEnrichStatus?.config?.interval_seconds ? ` / ${Math.round(autoEnrichStatus.config.interval_seconds / 60)}m` : ""}
            </div>
            <div className="alpha-admin-row">
              <input
                type="password"
                value={adminToken}
                onChange={(event) => setAdminToken(event.target.value)}
                placeholder="CORE_ADMIN_TOKEN"
              />
              <button onClick={() => runAdminJob("Start auto enrich", "/onchain/rpc/auto-enrich/start?interval_seconds=3600&limit_per_entity=10&max_entities=4&min_confidence=medium&include_tokens=true&mode=chain_gaps")}>Start Auto</button>
              <button onClick={() => runAdminJob("Stop auto enrich", "/onchain/rpc/auto-enrich/stop")}>Stop Auto</button>
              <button onClick={() => runAdminJob("Build labels", "/onchain/labels/build")}>Build labels</button>
              <button onClick={() => runAdminJob("Acquire sources", "/onchain/labels/acquire-sources?limit=3&min_trusted_per_entity=100&timeout_ms=30000&max_xhr=60")}>Acquire Sources</button>
              <button onClick={() => runAdminJob("Corroborate evidence", "/onchain/labels/candidates/corroborate-job?limit=5&timeout=12")}>Corroborate Evidence</button>
              <button onClick={() => runAdminJob("Expand labels", "/onchain/labels/expand?min_evidence=2&limit=50000")}>Expand labels</button>
              <button onClick={() => runAdminJob("Seed ETH", "/onchain/labels/ingest-seeds?chain=ethereum&seed_limit=5&tx_per_seed=10")}>Seed ETH</button>
              <button onClick={() => runAdminJob("Enrich priority queue", "/onchain/rpc/enrich-priority?limit_per_entity=20&max_entities=6&min_confidence=medium&include_tokens=true")}>Enrich Priority</button>
              <button onClick={() => runAdminJob("Enrich chain gaps", "/onchain/rpc/enrich-chain-gaps?limit_per_pair=8&max_pairs=8&min_confidence=medium&include_tokens=true")}>Enrich Chain Gaps</button>
              <button onClick={() => runAdminJob("Enrich Binance", "/onchain/rpc/enrich-labels?entity=Binance&limit=30&min_confidence=medium&include_tokens=true")}>Enrich Binance</button>
              <button onClick={() => runAdminJob("Enrich BlackRock", "/onchain/rpc/enrich-labels?entity=BlackRock&limit=20&min_confidence=medium&include_tokens=true")}>Enrich BlackRock</button>
              <button onClick={() => runAdminJob("Enrich Coinbase", "/onchain/rpc/enrich-labels?entity=Coinbase&limit=20&min_confidence=medium&include_tokens=true")}>Enrich Coinbase</button>
              <button onClick={() => runAdminJob("Enrich Kraken", "/onchain/rpc/enrich-labels?entity=Kraken&limit=10&min_confidence=medium&include_tokens=true")}>Enrich Kraken</button>
              <button onClick={() => runAdminJob("Enrich KuCoin", "/onchain/rpc/enrich-labels?entity=KuCoin&limit=10&min_confidence=medium&include_tokens=true")}>Enrich KuCoin</button>
              <button onClick={() => runAdminJob("Enrich OKX", "/onchain/rpc/enrich-labels?entity=OKX&limit=20&min_confidence=medium&include_tokens=true")}>Enrich OKX</button>
              <button onClick={() => runAdminJob("Enrich Uniswap", "/onchain/rpc/enrich-labels?entity=Uniswap&limit=20&min_confidence=medium&include_tokens=true")}>Enrich Uniswap</button>
              <button onClick={() => runAdminJob("Enrich Bitget", "/onchain/rpc/enrich-labels?entity=Bitget&limit=20&min_confidence=medium&include_tokens=true")}>Enrich Bitget</button>
              <button onClick={() => runAdminJob("Enrich Polymarket", "/onchain/rpc/enrich-labels?entity=Polymarket&limit=10&min_confidence=medium&include_tokens=true")}>Enrich Polymarket</button>
              <button onClick={() => runAdminJob("Refresh audit targets", "/onchain/rpc/refresh-wallet-state-audit-targets?limit_per_target=3&max_targets=3&min_confidence=medium&include_tokens=false&stale_after_hours=24&quality_below=50")}>Refresh Audit Targets</button>
              <button onClick={() => void loadAlphaUsageStats()}>Load Usage Stats</button>
            </div>
            {adminJobStatus && <div className="alpha-admin-status">{adminJobStatus}</div>}
            {manipulationContract ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Admin Manipulation Contract Detail</div>
                <div className="alpha-panel-subtitle">
                  Read-only thresholds for owner decisions. This is a data roadmap, not a client execution switch.
                </div>
                <div className="alpha-chain-head">
                  <span>Gate</span>
                  <span>Current</span>
                  <span>Target</span>
                  <span>Delta</span>
                  <span>Action id</span>
                </div>
                {manipulationContract.requirements.map((row) => (
                  <div className="alpha-chain-row" key={`admin-manip-readiness-${row.id}`}>
                    <strong className={row.passed ? "tier-strong" : "tier-seed"}>{row.label_fr}</strong>
                    <span>{largeNumber(row.current)} {row.unit}</span>
                    <span>{row.direction === "minimum" ? ">=" : "<="} {largeNumber(row.target)} {row.unit}</span>
                    <span>
                      {row.passed
                        ? "passed"
                        : row.direction === "minimum"
                          ? `${largeNumber(row.missing || 0)} missing`
                          : `${largeNumber(row.excess || 0)} excess`}
                    </span>
                    <em>{row.recommended_action_id}</em>
                  </div>
                ))}
                {(manipulationContract.next_safe_actions || []).slice(0, 8).map((item) => (
                  <div className="alpha-chain-row" key={`admin-next-safe-action-${item.action.id}-${item.requirement_id}`}>
                    <strong>{item.title_fr || item.action.title_fr}</strong>
                    <span>{item.requirement_label_fr}</span>
                    <span>{item.method} {item.endpoint}</span>
                    <span>
                      {item.admin_required ? "admin token required" : "read only"}
                      {item.dry_run ? " / dry-run" : ""}
                    </span>
                    <em>{item.source_policy || item.action.confirm_required || item.action.env_required || "guarded"}</em>
                  </div>
                ))}
                {manipulationContract.automation_decision ? (
                  <div className="alpha-chain-row">
                    <strong>Automation decision</strong>
                    <span>{manipulationContract.automation_decision.admin_mode.replace(/_/g, " ")}</span>
                    <span>
                      next admin: {manipulationContract.automation_decision.first_admin_action?.title_fr
                        || manipulationContract.automation_decision.first_admin_action?.action.title_fr
                        || "none"}
                    </span>
                    <span title={manipulationContract.automation_decision.required_before_client_automation.join(" / ")}>
                      gates: {largeNumber(manipulationContract.automation_decision.required_before_client_automation.length)}
                    </span>
                    <em>{manipulationContract.automation_decision.status}</em>
                  </div>
                ) : null}
                <div className="alpha-chain-row">
                  <span>{manipulationContract.version}</span>
                  <strong>{largeNumber(manipulationContract.failed_count)} failed / {largeNumber(manipulationContract.passed_count)} passed</strong>
                  <span>{manipulationContract.automation_scope.replace(/_/g, " ")}</span>
                  <span>execution off / guarantee off</span>
                  <em>{manipulationContract.source_policy}</em>
                </div>
              </div>
            ) : null}
            {alphaUsageStats ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Client Product Usage</div>
                <div className="alpha-panel-subtitle">
                  Owner-only telemetry. Wallets are hashed server-side; this is for activation/funnel quality, not private wallet surveillance.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Events</span><strong>{largeNumber(alphaUsageStats.events)}</strong><em>dashboard + alpha</em></div>
                  <div className="alpha-metric-card"><span>Unique wallets</span><strong>{largeNumber(alphaUsageStats.wallets)}</strong><em>hashed ids</em></div>
                  <div className="alpha-metric-card"><span>Connects</span><strong>{largeNumber(alphaUsageStats.actions.wallet_connected ?? 0)}</strong><em>browser wallet success</em></div>
                  <div className="alpha-metric-card"><span>Analyses</span><strong>{largeNumber(alphaUsageStats.actions.wallet_analysis_completed ?? 0)}</strong><em>completed wallet probes</em></div>
                </div>
                {Object.entries(alphaUsageStats.actions)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 8)
                  .map(([action, count]) => (
                    <div className="alpha-wallet-row" key={`usage-action-${action}`}>
                      <span>{action.replace(/_/g, " ")}</span>
                      <strong>{largeNumber(count)}</strong>
                    </div>
                  ))}
                {alphaUsageStats.recent.slice(-5).reverse().map((row, index) => (
                  <div className="alpha-wallet-row" key={`usage-recent-${row.ts}-${index}`}>
                    <span>
                      <strong>{row.action.replace(/_/g, " ")}</strong>
                      <em>{row.page} / {row.wallet_short || "no wallet"} / {new Date(row.ts * 1000).toLocaleString()}</em>
                    </span>
                    <strong>{row.status || "-"}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {walletStateAudit ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">RPC Wallet State Audit</div>
                <div className="alpha-panel-subtitle">
                  Source traceability before more automation. This answers: can we explain where each attributed wallet state came from?
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Total wallets</span><strong>{largeNumber(walletStateAudit.total_wallets)}</strong><em>RPC wallet state rows</em></div>
                  <div className="alpha-metric-card"><span>Traceable</span><strong>{walletStateAudit.traceability_pct.toFixed(1)}%</strong><em>{largeNumber(walletStateAudit.traceable_wallets)} explainable rows</em></div>
                  <div className="alpha-metric-card"><span>Missing attribution</span><strong>{largeNumber(walletStateAudit.missing_source_attribution)}</strong><em>{largeNumber(walletStateAudit.missing_label_sources)} missing label evidence</em></div>
                  <div className="alpha-metric-card"><span>Refresh needed</span><strong>{largeNumber(walletStateAudit.stale_rows + walletStateAudit.low_quality_rows)}</strong><em>{largeNumber(walletStateAudit.stale_rows)} stale / {largeNumber(walletStateAudit.low_quality_rows)} low quality</em></div>
                </div>
                <div className="alpha-chain-head">
                  <span>Entity</span>
                  <span>Chain</span>
                  <span>Wallets</span>
                  <span>Missing</span>
                  <span>Quality</span>
                  <span>Action</span>
                </div>
                {walletStateAudit.refresh_targets.slice(0, 8).map((row) => (
                  <div className="alpha-chain-row" key={`wallet-state-audit-${row.entity}-${row.chain}`}>
                    <strong>{row.entity}</strong>
                    <em className={row.missing_source_attribution || row.low_quality_rows ? "tier-seed" : "tier-useful"}>{row.chain}</em>
                    <span>{largeNumber(row.wallets)}</span>
                    <span>{largeNumber(row.missing_source_attribution)} attr / {largeNumber(row.missing_label_sources)} labels</span>
                    <span>{Math.round(row.avg_quality)} avg / {largeNumber(row.low_quality_rows)} low</span>
                    <strong>{row.recommended_action.replace(/_/g, " ")}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {walletQualityAudit ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Wallet Quality Distribution</div>
                <div className="alpha-panel-subtitle">
                  Read-only quality lens before more RPC volume. Low quality rows should be refreshed or source-reviewed before they feed automation.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Total RPC wallets</span><strong>{largeNumber(walletQualityAudit.total_wallets)}</strong><em>quality-audited rows</em></div>
                  <div className="alpha-metric-card"><span>High quality</span><strong>{largeNumber(walletQualityAudit.quality_distribution.high)}</strong><em>score {">="} 80</em></div>
                  <div className="alpha-metric-card"><span>Medium quality</span><strong>{largeNumber(walletQualityAudit.quality_distribution.medium)}</strong><em>score 50-79</em></div>
                  <div className="alpha-metric-card"><span>Low quality</span><strong>{walletQualityAudit.low_quality_pct.toFixed(1)}%</strong><em>{largeNumber(walletQualityAudit.quality_distribution.low)} rows below 50</em></div>
                </div>
                <div className="alpha-chain-head">
                  <span>Entity</span>
                  <span>Chain</span>
                  <span>Wallets</span>
                  <span>High / Med / Low</span>
                  <span>Avg</span>
                  <span>Action</span>
                </div>
                {walletQualityAudit.by_entity_chain.slice(0, 6).map((row) => (
                  <div className="alpha-chain-row" key={`wallet-quality-${row.entity}-${row.chain}`}>
                    <strong>{row.entity}</strong>
                    <em className={row.low_quality ? "tier-seed" : row.avg_quality >= 80 ? "tier-strong" : "tier-useful"}>{row.chain}</em>
                    <span>{largeNumber(row.wallets)}</span>
                    <span>{largeNumber(row.high_quality)} / {largeNumber(row.medium_quality)} / {largeNumber(row.low_quality)}</span>
                    <span>{Math.round(row.avg_quality)}</span>
                    <strong>{row.recommended_action.replace(/_/g, " ")}</strong>
                  </div>
                ))}
                {walletQualityAudit.weakest_wallets.slice(0, 5).map((row) => (
                  <div className="alpha-wallet-row" key={`weak-wallet-${row.chain}-${row.address}`}>
                    <span>
                      <strong>{row.entity || "unknown"} / {row.label || shortId(row.address)}</strong>
                      <em>{row.chain} / {shortId(row.address)} / {row.rpc_source || "unknown rpc"} / {row.traceable ? "traceable" : "missing attribution"}</em>
                      <em>{row.risk_flags.slice(0, 3).join(", ") || "no risk flags"}</em>
                    </span>
                    <strong>{row.data_quality_score}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {candidateReview?.rows?.length ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Candidate Label Review</div>
                <div className="alpha-panel-subtitle">
                  {candidateReview.eligible}/{candidateReview.rows_reviewed} candidates look promotion-ready. Review only: no trusted label is changed here.
                </div>
                <div className="alpha-admin-row" style={{ marginBottom: 12 }}>
                  <input
                    value={candidatePromoteIds}
                    onChange={(event) => setCandidatePromoteIds(event.target.value)}
                    placeholder="Candidate IDs, e.g. 12, 19, 44"
                  />
                  <button
                    onClick={() => setCandidatePromoteIds(promotionReadyIds.join(", "))}
                    disabled={!promotionReadyIds.length}
                  >
                    Fill strict-ready IDs
                  </button>
                  <button onClick={() => void runCandidatePromoteDryRun()}>
                    Dry-run Promote
                  </button>
                </div>
                <div className="alpha-proof-note" style={{ marginBottom: 12 }}>
                  Dry-run only: this calls the guarded admin endpoint with <strong>dry_run=true</strong>. Only strict-ready candidates are eligible, and trusted labels are not changed.
                </div>
                {candidatePromotePreview ? (
                  <div className="alpha-chain-coverage" style={{ marginBottom: 12 }}>
                    <div className="alpha-panel-title mini">Strict Dry-run Report</div>
                    <div className="alpha-panel-subtitle">
                      {candidatePromotePreview.rows.filter((row) => row.status === "would_promote").length}/{candidatePromotePreview.reviewed} would be added to trusted labels. Policy: {candidatePromotePreview.source_policy}.
                    </div>
                    {candidatePromotePreview.rows.slice(0, 6).map((row) => (
                      <div className="alpha-wallet-row" key={`candidate-promote-preview-${row.id}`}>
                        <span>
                          <strong>{row.entity || "unknown"} / {row.label || row.address}</strong>
                          <em>{row.chain} / seen {row.seen_count} / score {row.promotion.score} / #{row.id}</em>
                          <em>
                            {row.status === "would_promote"
                              ? `why add: ${row.promotion.reasons.slice(0, 2).join(", ") || "strict evidence passed"}`
                              : `blocked: ${row.promotion.blockers.slice(0, 2).join(", ") || "strict gate failed"}`}
                          </em>
                        </span>
                        <strong className={row.status === "would_promote" ? "tier-strong" : "tier-seed"}>
                          {row.status.replace(/_/g, " ")}
                        </strong>
                      </div>
                    ))}
                  </div>
                ) : null}
                <div className="alpha-chain-head">
                  <span>Candidate</span>
                  <span>Decision</span>
                  <span>Score</span>
                  <span>Evidence</span>
                  <span>Blockers</span>
                  <span>ID</span>
                </div>
                {candidateReview.rows.slice(0, 8).map((row) => (
                  <div className="alpha-chain-row" key={`candidate-review-${row.id}`}>
                    <strong title={row.address}>{row.entity || "unknown"} / {row.label}</strong>
                    <em className={row.decision === "promote_ready" ? "tier-strong" : "tier-seed"}>
                      {row.decision.replace(/_/g, " ")}
                    </em>
                    <span>{row.promotion.score} / {row.promotion.confidence}</span>
                    <span>{row.chain} / seen {row.seen_count}</span>
                    <span title={row.promotion.blockers.join(" / ")}>
                      {row.promotion.blockers.length ? row.promotion.blockers.slice(0, 2).join(", ") : row.promotion.reasons.slice(0, 2).join(", ")}
                    </span>
                    <strong>#{row.id}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {labelAcquisitionPlan ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Label Acquisition Plan</div>
                <div className="alpha-panel-subtitle">
                  Next-label queue before more RPC scaling. {labelAcquisitionPlan.recommendation}
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Entities reviewed</span><strong>{labelAcquisitionPlan.entities_reviewed}</strong><em>target floor {labelAcquisitionPlan.target_floor}</em></div>
                  <div className="alpha-metric-card"><span>Top gap</span><strong>{labelAcquisitionPlan.rows[0]?.gap_to_target ?? 0}</strong><em>{labelAcquisitionPlan.rows[0]?.entity || "none"}</em></div>
                  <div className="alpha-metric-card"><span>Strict-ready queue</span><strong>{labelAcquisitionPlan.rows.reduce((sum, row) => sum + row.strict_ready_candidates, 0)}</strong><em>dry-run first</em></div>
                </div>
                {labelAcquisitionPlan.rows.slice(0, 8).map((row) => (
                  <div className="alpha-wallet-row" key={`label-acquisition-${row.entity}`}>
                    <span>
                      <strong>{row.entity}</strong>
                      <em>
                        trusted {row.trusted_labels}/{row.target_trusted_labels} / candidates {row.open_candidates} / strict {row.strict_ready_candidates}
                      </em>
                      <em>
                        {row.recommended_action.replace(/_/g, " ")}
                        {row.top_candidate_ids.length ? ` / IDs ${row.top_candidate_ids.slice(0, 4).join(", ")}` : ""}
                      </em>
                    </span>
                    <strong>{row.gap_to_target}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {strictCandidateReview ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Strict Promotion Gate</div>
                <div className="alpha-panel-subtitle">
                  {strictCandidateReview.strict_ready}/{strictCandidateReview.rows_reviewed} candidates pass the stricter trusted-label gate. {strictCandidateReview.recommendation}
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Strict ready</span><strong>{strictCandidateReview.strict_ready}</strong><em>entity URL + repeated evidence</em></div>
                  <div className="alpha-metric-card"><span>Blocked</span><strong>{strictCandidateReview.blocked}</strong><em>needs review</em></div>
                  <div className="alpha-metric-card"><span>Top blocker</span><strong>{strictCandidateReview.blocked_by_reason[0]?.count ?? 0}</strong><em>{strictCandidateReview.blocked_by_reason[0]?.reason?.replace(/_/g, " ") || "none"}</em></div>
                </div>
                {strictCandidateReview.rows.filter((row) => row.decision === "strict_ready").slice(0, 5).map((row) => (
                  <div className="alpha-wallet-row" key={`strict-ready-${row.id}`}>
                    <span>
                      <strong>{row.entity} / {row.label}</strong>
                      <em>{row.chain} / score {row.strict_promotion.score} / candidate #{row.id}</em>
                    </span>
                    <strong>STRICT READY</strong>
                  </div>
                ))}
                {strictCandidateReview.blocked_by_reason.slice(0, 4).map((row) => (
                  <div className="alpha-wallet-row" key={`strict-blocker-${row.reason}`}>
                    <span>{row.reason.replace(/_/g, " ")}</span>
                    <strong>{row.count}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {candidateAutomationPlan ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Automation Plan</div>
                <div className="alpha-panel-subtitle">
                  Future rail only: {candidateAutomationPlan.auto_safe_later} auto-safe later / {candidateAutomationPlan.admin_review} admin review / {candidateAutomationPlan.blocked} blocked.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Auto-safe later</span><strong>{candidateAutomationPlan.auto_safe_later}</strong><em>no action yet</em></div>
                  <div className="alpha-metric-card"><span>Admin review</span><strong>{candidateAutomationPlan.admin_review}</strong><em>too ambiguous</em></div>
                  <div className="alpha-metric-card"><span>Blocked</span><strong>{candidateAutomationPlan.blocked}</strong><em>do not automate</em></div>
                </div>
                {candidateAutomationPlan.lanes.auto_safe_later.slice(0, 5).map((row) => (
                  <div className="alpha-wallet-row" key={`auto-safe-${row.id}`}>
                    <span>
                      <strong>{row.entity} / {row.label}</strong>
                      <em>{row.chain} / score {row.promotion.score} / candidate #{row.id}</em>
                    </span>
                    <strong>AUTO-SAFE LATER</strong>
                  </div>
                ))}
                {candidateAutomationPlan.lanes.admin_review.slice(0, 3).map((row) => (
                  <div className="alpha-wallet-row" key={`admin-review-${row.id}`}>
                    <span>
                      <strong>{row.entity} / {row.label}</strong>
                      <em>{row.automation_blockers.slice(0, 2).join(", ") || "manual confidence check"}</em>
                    </span>
                    <strong>REVIEW</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {candidateCorroborationQueue ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Corroboration Queue</div>
                <div className="alpha-panel-subtitle">
                  Evidence collection queue only. Manual-review rows filtered: {candidateCorroborationQueue.manual_review_filtered}. No trusted labels are changed here.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Actionable rows</span><strong>{corroborationActionable.length}</strong><em>{candidateCorroborationQueue.rows_reviewed} reviewed</em></div>
                  <div className="alpha-metric-card"><span>Manual filtered</span><strong>{candidateCorroborationQueue.manual_review_filtered}</strong><em>hidden by default</em></div>
                  <div className="alpha-metric-card"><span>Top priority</span><strong>{candidateCorroborationQueue.rows[0]?.priority_score ?? 0}</strong><em>{candidateCorroborationQueue.rows[0]?.recommended_action?.replace(/_/g, " ") || "none"}</em></div>
                  <div className="alpha-metric-card"><span>Evidence gaps</span><strong>{candidateCorroborationQueue.rows.filter((row) => row.evidence_bundles === 0).length}</strong><em>need first pass</em></div>
                </div>
                <div className="alpha-chain-head">
                  <span>Candidate</span>
                  <span>Entity</span>
                  <span>Seen</span>
                  <span>Evidence</span>
                  <span>Action</span>
                  <span>Score</span>
                </div>
                {candidateCorroborationQueue.rows.slice(0, 6).map((row) => (
                  <div className="alpha-chain-row" key={`corroboration-queue-${row.id}`}>
                    <strong>#{row.id} {shortId(row.address)}</strong>
                    <em className={row.requires_manual_review ? "tier-seed" : "tier-useful"}>{row.entity || row.label || "unknown"}</em>
                    <span>{largeNumber(row.seen_count)}</span>
                    <span>{row.evidence_bundles} bundles / max {row.max_evidence_score}</span>
                    <span>{row.recommended_action.replace(/_/g, " ")}</span>
                    <strong>{row.priority_score}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {candidateEvidenceScores ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Evidence Scores</div>
                <div className="alpha-panel-subtitle">
                  Historical evidence scoring for candidates already corroborated. Use strict-review rows as inputs, not as automatic promotions.
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Scored candidates</span><strong>{candidateEvidenceScores.rows_reviewed}</strong><em>persisted evidence only</em></div>
                  <div className="alpha-metric-card"><span>Strict-review inputs</span><strong>{candidateEvidenceScores.rows.filter((row) => row.decision === "strict_review_candidate").length}</strong><em>still admin-reviewed</em></div>
                  <div className="alpha-metric-card"><span>Manual blockers</span><strong>{candidateEvidenceScores.rows.filter((row) => row.severe_blockers.length > 0).length}</strong><em>must not automate</em></div>
                  <div className="alpha-metric-card"><span>Unique sources</span><strong>{largeNumber(new Set(candidateEvidenceScores.rows.flatMap((row) => row.unique_sources || [])).size)}</strong><em>deduped evidence</em></div>
                </div>
                {candidateEvidenceScores.rows.slice(0, 5).map((row) => (
                  <div className="alpha-wallet-row" key={`candidate-evidence-score-${row.id}`}>
                    <span>
                      <strong>#{row.id} {row.entity || row.label || shortId(row.address)}</strong>
                      <em>{row.chain} / score {row.historical_evidence_score} / {row.evidence_bundles} bundles / {row.evidence_items} items</em>
                      <em>{row.unique_sources.slice(0, 3).join(", ") || "no source"}{row.severe_blockers.length ? ` / blockers: ${row.severe_blockers.slice(0, 2).join(", ")}` : ""}</em>
                    </span>
                    <strong>{row.decision.replace(/_/g, " ")}</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {candidateQualityReport ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Candidate Quality Gate</div>
                <div className="alpha-panel-subtitle">
                  Read-only dedupe/freshness gate before any real automation. {candidateQualityReport.recommendation}
                </div>
                <div className="alpha-admin-row" style={{ marginBottom: 12 }}>
                  <button onClick={() => void runCandidateDedupeDryRun()}>
                    Dry-run Dedupe
                  </button>
                </div>
                <div className="alpha-metric-grid compact">
                  <div className="alpha-metric-card"><span>Open candidates</span><strong>{candidateQualityReport.totals.open_candidates}</strong><em>{candidateQualityReport.totals.missing_source_url} missing URLs</em></div>
                  <div className="alpha-metric-card"><span>Duplicate groups</span><strong>{candidateQualityReport.risk_summary.duplicate_groups}</strong><em>must be resolved first</em></div>
                  <div className="alpha-metric-card"><span>Ambiguous addresses</span><strong>{candidateQualityReport.risk_summary.ambiguous_addresses}</strong><em>entity/label conflict</em></div>
                  <div className="alpha-metric-card"><span>Single-seen</span><strong>{candidateQualityReport.risk_summary.single_seen_pct.toFixed(1)}%</strong><em>{candidateQualityReport.totals.single_seen_candidates} rows</em></div>
                </div>
                {candidateQualityReport.duplicate_groups.slice(0, 5).map((row) => (
                  <div className="alpha-wallet-row" key={`candidate-dup-${row.chain}-${row.address}-${row.candidate_ids.join("-")}`}>
                    <span>
                      <strong>{row.entity} / {row.label || shortId(row.address)}</strong>
                      <em>{row.chain} / {row.rows} rows / seen {row.total_seen} / IDs {row.candidate_ids.join(", ")}</em>
                    </span>
                    <strong>DUPLICATE</strong>
                  </div>
                ))}
                {candidateQualityReport.ambiguous_addresses.slice(0, 3).map((row) => (
                  <div className="alpha-wallet-row" key={`candidate-ambiguous-${row.chain}-${row.address}`}>
                    <span>
                      <strong>{shortId(row.address)}</strong>
                      <em>{row.chain} / {row.entities} entities / {row.labels} labels / IDs {row.candidate_ids.join(", ")}</em>
                    </span>
                    <strong>REVIEW</strong>
                  </div>
                ))}
              </div>
            ) : null}
            {dataJobs?.rows?.length ? (
              <div className="alpha-chain-coverage" style={{ marginTop: 12 }}>
                <div className="alpha-panel-title mini">Recent Data Jobs</div>
                <div className="alpha-panel-subtitle">
                  Audit trail for source acquisition, label builds and RPC enrichment. Mutation jobs stay admin-only; this view is read-only.
                </div>
                {dataJobs.rows.slice(0, 5).map((job) => (
                  <div className="alpha-wallet-row" key={`data-job-${job.id}`}>
                    <span>
                      <strong>#{job.id} {job.status} / {formatJobDuration(job.started_at, job.finished_at)}</strong>
                      <em>
                        {job.job_type} / {new Date(job.started_at * 1000).toLocaleString()}
                      </em>
                      <em>{dataJobDetails(job)}</em>
                    </span>
                    <strong>{summarizeDataJob(job)}</strong>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}
        {arkhamCoverage && (
          <div className="alpha-decision-lane" style={{ paddingTop: 0 }}>
            <div>
              <div className="alpha-panel-title mini">Top attributed entities</div>
              {arkhamCoverage.top_entities_by_value.slice(0, 5).map((row) => (
                <div className="alpha-wallet-row" key={row.entity}>
                  <span>{row.entity} / {row.wallet_rows} wallets</span>
                  <strong>{money(row.value_usd)}</strong>
                </div>
              ))}
            </div>
            <div>
              <div className="alpha-panel-title mini">Holder coverage</div>
              {arkhamCoverage.top_holder_tokens.slice(0, 5).map((row) => (
                <div className="alpha-wallet-row" key={row.token}>
                  <span>{shortId(row.token.replace("holders:", ""))}</span>
                  <strong>{row.holders_cached}</strong>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Wallet Analyzer */}
      <section className="alpha-single">
        <div className="alpha-panel alpha-panel-large">
          <div className="alpha-panel-header">
            <div>
              <div className="alpha-panel-title">{t("alpha.walletAnalyzer")}</div>
              <div className="alpha-panel-subtitle">{t("alpha.walletAnalyzerSub")} Balance, transactions, swaps, volume, and smart labels.</div>
            </div>
          </div>
          <div style={{ padding: '16px 20px' }}>
            <WalletAnalyzer />
          </div>
        </div>
      </section>

      <section className="alpha-focus-board">
        <div className="alpha-focus-main alpha-panel">
          <div className="alpha-panel-header">
            <div>
              <div className="alpha-panel-title">{t("alpha.copySimulator")}</div>
              <div className="alpha-panel-subtitle">{t("alpha.copySimulatorSub")}</div>
            </div>
            <div className="alpha-toolbar">
              <input
                className="alpha-wallet-input"
                value={walletQuery}
                onChange={(event) => setWalletQuery(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") void runWalletIntel() }}
                placeholder={t("alpha.pasteWalletAddress")}
              />
              <button onClick={() => void runWalletIntel()} disabled={walletLoading || !walletQuery.trim()}>
                {walletLoading ? t("alpha.analyzing") : t("alpha.analyzeWallet")}
              </button>
            </div>
          </div>

          <div className="alpha-chain-coverage" style={{ margin: "0 20px 16px" }}>
            <div className="alpha-panel-title mini">{t("alpha.clientWalletAutomation")}</div>
            <div className="alpha-panel-subtitle">
              {t("alpha.clientWalletAutomationSub")}
            </div>
            <div className="alpha-metric-grid compact">
              <div className="alpha-metric-card">
                <span>{t("alpha.clientWallets")}</span>
                <strong>{clientAnalysisAccounts.length}</strong>
                <em>{watchOnlyAnalysisAccounts.length} {t("alpha.watchOnlyTargets")}</em>
              </div>
              <div className="alpha-metric-card">
                <span>{t("alpha.automation")}</span>
                <strong className={walletLoading ? "tier-useful" : walletProbe ? (serverOwnershipVerified ? "tier-strong" : "tier-seed") : "tier-seed"}>
                  {walletLoading ? t("alpha.running") : walletProbe ? (serverOwnershipVerified ? t("alpha.ready") : t("alpha.readOnly")) : t("alpha.waiting")}
                </strong>
                <em>{serverOwnershipVerified ? clientAutoStatus : t("alpha.serverProofRequired")}</em>
              </div>
              <div className="alpha-metric-card">
                <span>{t("alpha.ownershipProof")}</span>
                <strong className={serverOwnershipVerified ? "tier-strong" : "tier-seed"}>
                  {serverOwnershipVerified ? t("alpha.verified") : walletOwnership?.expired ? t("alpha.expired") : t("alpha.unverified")}
                </strong>
                <em>
                  {walletOwnership
                    ? `${walletOwnership.execution_gate.replace(/_/g, " ")}${walletOwnership.session_expires_at ? ` / session ${new Date(walletOwnership.session_expires_at * 1000).toLocaleString()}` : walletOwnership.expires_at ? ` / proof ${new Date(walletOwnership.expires_at * 1000).toLocaleString()}` : ""}`
                    : t("alpha.serverProofNotLoaded")}
                </em>
              </div>
              <div className="alpha-metric-card">
                <span>{t("alpha.planReadiness")}</span>
                <strong className={walletAutomationPlan?.readiness_score && walletAutomationPlan.readiness_score >= 70 ? "tier-strong" : walletAutomationPlan?.readiness_score && walletAutomationPlan.readiness_score >= 45 ? "tier-useful" : "tier-seed"}>
                  {walletAutomationPlan ? `${walletAutomationPlan.readiness_score}/100` : t("alpha.waiting")}
                </strong>
                <em>{walletAutomationPlan ? walletAutomationPlan.mode.replace(/_/g, " ") : t("alpha.analysisOnlyExecutionDisabled")}</em>
              </div>
            </div>
            {selectableAnalysisAccounts.slice(0, 4).map((account) => (
              <div className="alpha-wallet-row" key={`client-auto-${account.id}`}>
                <span>
                  <strong>{account.provider} / {shortId(account.address)}</strong>
                  <em>{account.network} / {account.type === "manual" ? "watch-only target" : account.status}{account.verifiedAt ? " / verified" : ""}</em>
                </span>
                <button className="alpha-mini-button" onClick={() => void runWalletIntel(account.address)} disabled={walletLoading}>
                  {t("alpha.analyzeNow")}
                </button>
              </div>
            ))}
            {walletAutomationPlan && (
              <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
                <div>
                  <div className="alpha-panel-title mini">Automation Plan</div>
                  <div className="alpha-wallet-row">
                    <span>
                      <strong>{walletAutomationPlan.decision}</strong>
                      <em>{walletAutomationPlan.rails.contract} / {walletAutomationPlan.rails.execution_gate}</em>
                    </span>
                    <strong>{walletAutomationPlan.execution_enabled ? "ON" : "OFF"}</strong>
                  </div>
                  {walletAutomationPlan.blockers.slice(0, 4).map((blocker) => (
                    <div className="alpha-wallet-row" key={`blocker-${blocker}`}><span>{blocker}</span></div>
                  ))}
                  {walletAutomationPlan.blockers.length === 0 && (
                    <div className="alpha-wallet-row"><span>No blocking issue surfaced yet, but manual review is still required.</span></div>
                  )}
                </div>
                <div>
                  <div className="alpha-panel-title mini">Source Trace</div>
                  <div className="alpha-wallet-row">
                    <span>Providers</span>
                    <strong>{walletAutomationPlan.source_trace.providers_ok}/{walletAutomationPlan.source_trace.providers_total}</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>RPC events</span>
                    <strong>{walletAutomationPlan.source_trace.rpc_events}</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Graph edges</span>
                    <strong>{walletAutomationPlan.source_trace.graph_edges}</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Flow confidence</span>
                    <strong>{walletAutomationPlan.data_quality.flow_confidence_score}/100</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>RPC backbone</span>
                    <strong>{walletAutomationPlan.data_quality.rpc_backbone_score}/100</strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Snapshot rows</span>
                    <strong>
                      {walletAutomationPlan.rpc_backbone.persisted_snapshot?.updated ?? 0}
                      {walletAutomationPlan.rpc_backbone.persisted_snapshot?.skipped_fresh
                        ? ` / ${walletAutomationPlan.rpc_backbone.persisted_snapshot.skipped_fresh} fresh`
                        : ""}
                    </strong>
                  </div>
                  <div className="alpha-wallet-row">
                    <span>Freshness</span>
                    <strong>
                      {walletAutomationPlan.data_quality.source_freshness.replace(/_/g, " ")}
                      {walletAutomationPlan.rpc_backbone.persisted_snapshot?.refresh_after_hours
                        ? ` / ttl ${walletAutomationPlan.rpc_backbone.persisted_snapshot.refresh_after_hours}h`
                        : ""}
                    </strong>
                  </div>
                </div>
              </div>
            )}
            {walletAutomationPlan && (
              <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
                <div>
                  <div className="alpha-panel-title mini">RPC Chain Coverage</div>
                  {walletAutomationPlan.rpc_backbone?.ok && (
                    <div className="alpha-wallet-row">
                      <span>
                        <strong>{walletAutomationPlan.rpc_backbone.wallet_label || "rpc wallet"}</strong>
                        <em>
                          {walletAutomationPlan.rpc_backbone.primary_chain || "multi-chain"} / {walletAutomationPlan.rpc_backbone.source_rows ?? 0} source rows / {walletAutomationPlan.rpc_backbone.traceable_rows ?? 0} traceable
                        </em>
                      </span>
                      <strong>{money(walletAutomationPlan.rpc_backbone.net_worth_usd)}</strong>
                    </div>
                  )}
                  {walletAutomationPlan.chain_coverage.slice(0, 4).map((row) => (
                    <div className="alpha-wallet-row" key={`auto-chain-${row.chain}`}>
                      <span>
                        <strong>{row.chain}</strong>
                        <em>{row.assets.slice(0, 4).join(", ") || "no assets surfaced"}</em>
                      </span>
                      <strong>{row.events} ev / {money(row.amount_usd)}</strong>
                    </div>
                  ))}
                  {walletAutomationPlan.chain_coverage.length === 0 && (
                    <div className="alpha-empty small">No chain sample yet. RPC/provider data must be refreshed before copy analysis.</div>
                  )}
                </div>
                <div>
                  <div className="alpha-panel-title mini">Token Risk Watchlist</div>
                  {walletAutomationPlan.token_risk_watchlist.slice(0, 4).map((row) => (
                    <div className="alpha-wallet-row" key={`auto-token-${row.chain}-${row.asset}`}>
                      <span>
                        <strong>{row.asset} / {row.chain}</strong>
                        <em>{row.risk_flag.replace(/_/g, " ")}</em>
                      </span>
                      <strong>{row.copy_allowed === false ? "BLOCK" : "PROVE"}</strong>
                    </div>
                  ))}
                  {walletAutomationPlan.token_risk_watchlist.length === 0 && (
                    <div className="alpha-empty small">No token focus yet. Wallet needs observable swaps or transfers.</div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="alpha-simulator-hero">
            <div className={`alpha-verdict-card ${walletProbe?.status || "idle"}`}>
              <span>Verdict</span>
              <strong>{walletProbe?.status_label || "No wallet loaded"}</strong>
              <em>{walletProbe ? `${walletProbe.confidence} confidence` : "Paste a wallet, then run the probe."}</em>
            </div>
            <div className="alpha-verdict-card">
              <span>100 USD copy proxy</span>
              <strong className={(walletProbe?.copy_preview?.pnl || 0) >= 0 ? "positive" : "negative"}>
                {walletProbe ? money(walletProbe.copy_preview.estimated_value) : "-"}
              </strong>
              <em>
                {walletProbe
                  ? `${(walletProbe.copy_preview.pnl || 0) >= 0 ? "+" : ""}${money(walletProbe.copy_preview.pnl)} / ${walletProbe.copy_preview.roi_pct.toFixed(2)}%`
                  : "No simulation yet"}
              </em>
            </div>
            <div className="alpha-verdict-card">
              <span>Profit trust</span>
              <strong>{walletProbe ? `${walletProbe.risk_summary.untrusted_rows} suspect` : "-"}</strong>
              <em>{walletProbe ? `${walletProbe.risk_summary.blocked_rows} blocked rows` : "Sell proof and fake-mark filters"}</em>
            </div>
            <div className={`alpha-verdict-card ${walletCopyPlan?.mode || "idle"}`}>
              <span>Copy mode</span>
              <strong>{walletCopyPlan ? (walletCopyPlan.execution_enabled ? "Enabled" : "Manual only") : "-"}</strong>
              <em>{walletCopyPlan ? walletCopyPlan.mode.replace(/_/g, " ") : "No execution without guards"}</em>
            </div>
            <div className={`alpha-verdict-card ${walletCopyBacktest?.verdict || "idle"}`}>
              <span>Read-only backtest</span>
              <strong className={(walletCopyBacktest?.pnl || 0) >= 0 ? "positive" : "negative"}>
                {walletCopyBacktest ? `${money(walletCopyBacktest.current_value)} / ${walletCopyBacktest.roi_pct.toFixed(2)}%` : "-"}
              </strong>
              <em>
                {walletCopyBacktest
                  ? `${walletCopyBacktest.verdict.replace(/_/g, " ")} / trust ${walletCopyBacktest.confidence_score}/100`
                  : "100 USD cost replay, no execution"}
              </em>
            </div>
          </div>

          <div className="alpha-decision-lane">
            <div>
              <div className="alpha-panel-title mini">Why this verdict</div>
              {(walletProbe?.reasons || []).slice(0, 4).map((reason) => (
                <div className="alpha-wallet-row" key={reason}><span>{reason}</span></div>
              ))}
              {!walletProbe && <div className="alpha-empty small">Run a wallet to see the reasons, not just raw tables.</div>}
              {walletProbe && walletProbe.reasons.length === 0 && <div className="alpha-empty small">No clear reason surfaced yet.</div>}
            </div>
            <div>
              <div className="alpha-panel-title mini">Required before copy</div>
              {(walletProbe?.requirements || []).slice(0, 4).map((requirement) => (
                <div className="alpha-wallet-row" key={requirement}><span>{requirement}</span></div>
              ))}
              {!walletProbe && <div className="alpha-empty small">The checklist appears after a probe.</div>}
              {walletProbe && walletProbe.requirements.length === 0 && <div className="alpha-empty small">No blocking requirement on this probe.</div>}
            </div>
          </div>
          {walletCopyPlan && (
            <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
              <div>
                <div className="alpha-panel-title mini">Smart copy allocation</div>
                {walletCopyPlan.allocation.slice(0, 4).map((item) => (
                  <div className="alpha-wallet-row" key={`${item.chain}:${item.asset}`}>
                    <span>{item.asset} / {item.chain}</span>
                    <strong>{item.max_weight_pct.toFixed(1)}%</strong>
                  </div>
                ))}
                {walletCopyPlan.allocation.length === 0 && <div className="alpha-empty small">No asset allocation until useful wallet flow appears.</div>}
              </div>
              <div>
                <div className="alpha-panel-title mini">Execution guards</div>
                {walletCopyPlan.guards.slice(0, 4).map((guard) => (
                  <div className="alpha-wallet-row" key={guard}><span>{guard}</span></div>
                ))}
              </div>
            </div>
          )}
          {walletCopyBacktest && (
            <div className="alpha-decision-lane" style={{ marginTop: 14 }}>
              <div>
                <div className="alpha-panel-title mini">Backtest trace</div>
                <div className="alpha-wallet-row">
                  <span>Copied / skipped</span>
                  <strong>{walletCopyBacktest.coverage.events_copied} / {walletCopyBacktest.coverage.events_skipped}</strong>
                </div>
                <div className="alpha-wallet-row">
                  <span>Chains</span>
                  <strong>{walletCopyBacktest.coverage.chains_seen.join(", ") || "-"}</strong>
                </div>
                <div className="alpha-wallet-row">
                  <span>Execution</span>
                  <strong>{walletCopyBacktest.execution_enabled ? "ON" : "OFF"}</strong>
                </div>
                <div className="alpha-empty small">
                  {String(walletCopyBacktest.assumptions.profit_policy || "Cost-only replay until stronger marks are available.")}
                </div>
              </div>
              <div>
                <div className="alpha-panel-title mini">Backtest blockers</div>
                {walletCopyBacktest.blockers.slice(0, 5).map((blocker) => (
                  <div className="alpha-wallet-row" key={blocker}><span>{blocker.replace(/_/g, " ")}</span></div>
                ))}
                {walletCopyBacktest.blockers.length === 0 && (
                  <div className="alpha-wallet-row"><span>Ready for manual review, not auto-copy.</span></div>
                )}
                {walletCopyBacktest.skipped.slice(0, 3).map((item, index) => (
                  <div className="alpha-wallet-row" key={`${item.reason}:${item.asset}:${index}`}>
                    <span>{item.reason.replace(/_/g, " ")} {item.asset ? `/${item.asset}` : ""}</span>
                    <strong>{item.observed_usd ? money(item.observed_usd) : item.chain || ""}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        <aside className="alpha-panel alpha-focus-side">
          <div className="alpha-panel-header compact">
            <div>
              <div className="alpha-panel-title">Evidence Snapshot</div>
              <div className="alpha-panel-subtitle">Seulement les preuves utiles, pas le labyrinthe.</div>
            </div>
          </div>
          <div className="alpha-proof-stack">
            <div><span>Providers</span><strong>{walletProbe ? `${walletProbe.provider_health.ok}/${walletProbe.provider_health.total}` : sourceHealth}</strong><em>Cielo / Zerion / RPC</em></div>
            <div><span>Graph edges</span><strong>{walletGraph?.summary.edges ?? "-"}</strong><em>{walletGraph?.summary.evidence_grade || "waiting for wallet"}</em></div>
            <div><span>Transfers</span><strong>{walletSurface?.summary.transfers ?? "-"}</strong><em>net {money(walletSurface?.summary.net_transfer_usd)}</em></div>
            <div><span>RPC backbone</span><strong>{rpcStatus ? `${rpcReady}/${rpcChains.length}` : "-"}</strong><em>{rpcStatusLabel} / {rpcTrackedTokens} tokens</em></div>
          </div>
        </aside>
      </section>

      <details className="alpha-legacy-drawer">
        <summary>
          <span>Advanced raw data</span>
          <em>Prediction markets, collector matrix, discovery feed, graph and transfer tables</em>
        </summary>

      <section className="alpha-metric-grid">
        <div className="alpha-metric-card"><span>{t("alpha.collectors")}</span><strong>{activeCollectors.length}/{collectors.length || "-"}</strong><em>active or key-ready</em></div>
        <div className="alpha-metric-card"><span>{t("alpha.marketsLoaded")}</span><strong>{markets.length}</strong><em>{query ? `query: ${query}` : "all active"}</em></div>
        <div className="alpha-metric-card"><span>{t("alpha.totalLiquidity")}</span><strong>{money(totalLiquidity)}</strong><em>visible sample</em></div>
        <div className="alpha-metric-card"><span>{t("alpha.sourceHealth")}</span><strong>{sourceHealth}</strong><em>last request</em></div>
        <div className="alpha-metric-card">
          <span>RPC backbone</span>
          <strong>{rpcStatus ? `${rpcReady}/${rpcChains.length}` : "-"}</strong>
          <em>{rpcStatusLabel} / {rpcTrackedTokens} tracked tokens</em>
        </div>
      </section>

      {error && <div className="alpha-error">{error}</div>}

      <section className="alpha-grid">
        <div className="alpha-panel alpha-panel-large">
          <div className="alpha-panel-header">
            <div>
              <div className="alpha-panel-title">{t("alpha.predictionTape")}</div>
              <div className="alpha-panel-subtitle">{t("alpha.predictionTapeSub")}</div>
            </div>
            <div className="alpha-toolbar">
              <select value={source} onChange={(event) => setSource(event.target.value)}>
                <option value="all">{t("common.all")}</option>
                <option value="polymarket">Polymarket</option>
                <option value="kalshi">Kalshi</option>
              </select>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") void refresh() }}
                placeholder="bitcoin, election, fed..."
              />
              <button onClick={() => void refresh()}>{t("common.search")}</button>
            </div>
          </div>

          <div className="alpha-market-table">
            <div className="alpha-market-row alpha-market-head">
              <span>Market</span><span>Prob</span><span>24h Vol</span><span>Liquidity</span><span>Action</span>
            </div>
            {markets.map((market) => (
              <button
                key={`${market.source}:${market.market_id}`}
                className={`alpha-market-row${selectedMarket?.market_id === market.market_id ? " active" : ""}`}
                onClick={() => setSelectedMarket(market)}
              >
                <span>
                  <strong>{market.title}</strong>
                  <em>{sourceLabel(market.source)} / {shortId(market.market_id)}{market.is_stale_by_date ? " / stale close date" : ""}</em>
                </span>
                <span className="alpha-mono">{pct(market.probability_mid)}</span>
                <span className="alpha-mono">{money(market.volume_24h)}</span>
                <span className="alpha-mono">{money(market.liquidity)}</span>
                <span>
                  <button
                    className="alpha-mini-button"
                    onClick={(event) => {
                      event.stopPropagation()
                      void runCopyPreview(market)
                    }}
                  >
                    simulate 100
                  </button>
                </span>
              </button>
            ))}
            {!loading && markets.length === 0 && <div className="alpha-empty">No markets for this query yet.</div>}
          </div>
        </div>

        <div className="alpha-panel">
          <div className="alpha-panel-header compact">
            <div>
              <div className="alpha-panel-title">{t("alpha.copyPreview")}</div>
              <div className="alpha-panel-subtitle">Counterfactual only until user trade history is connected.</div>
            </div>
          </div>
          <div className="alpha-selected-market">
            <span>Selected</span>
            <strong>{selectedMarket?.title || "No market selected"}</strong>
            <em>{selectedMarket ? `${sourceLabel(selectedMarket.source)} / ${pct(selectedMarket.probability_mid)}` : "Pick a market from the tape"}</em>
          </div>
          {simulation ? (
            <div className="alpha-sim-card">
              <div>
                <span>100 USD result</span>
                <strong className={simulation.pnl >= 0 ? "positive" : "negative"}>{money(simulation.current_value || simulation.ending_value)}</strong>
              </div>
              <div>
                <span>PnL</span>
                <strong className={simulation.pnl >= 0 ? "positive" : "negative"}>
                  {simulation.pnl >= 0 ? "+" : ""}{money(simulation.pnl)} / {simulation.roi_pct.toFixed(2)}%
                </strong>
              </div>
            </div>
          ) : (
            <div className="alpha-empty small">Run a 100 USD preview from a market row.</div>
          )}
          <div className="alpha-proof-note">
            Real premium mode will require timestamped orderbook depth, trader fills, partial fill rules and settlement state.
          </div>
        </div>
      </section>

      <section className="alpha-grid bottom">
        <div className="alpha-panel">
          <div className="alpha-panel-header compact">
            <div>
              <div className="alpha-panel-title">{t("alpha.collectorMatrix")}</div>
              <div className="alpha-panel-subtitle">What is live now, and what waits for keys.</div>
            </div>
          </div>
          <div className="alpha-collector-list">
            {collectors.map((collector) => (
              <div className="alpha-collector" key={collector.id}>
                <div><strong>{collector.name}</strong><span>{collector.category}</span></div>
                <em className={collector.configured ? "ready" : "missing"}>{collector.status}</em>
              </div>
            ))}
          </div>
        </div>

        <div className="alpha-panel alpha-panel-large">
          <div className="alpha-panel-header">
            <div>
              <div className="alpha-panel-title">{t("alpha.integrityGuard")}</div>
              <div className="alpha-panel-subtitle">Contract address = real DexScreener/Honeypot probe. Symbol only = manual sandbox.</div>
            </div>
            <div className="alpha-toolbar">
              <input value={riskToken} onChange={(event) => setRiskToken(event.target.value)} placeholder="0x contract or symbol" />
              <input value={riskLiquidity} onChange={(event) => setRiskLiquidity(event.target.value)} />
              <input value={riskSellTax} onChange={(event) => setRiskSellTax(event.target.value)} />
              <select value={riskMode} onChange={(event) => setRiskMode(event.target.value as "normal" | "danger")}>
                <option value="normal">normal</option>
                <option value="danger">danger</option>
              </select>
              <button onClick={() => void runRiskCheck()}>Run guard</button>
            </div>
          </div>
          {risk && (
            <div className="alpha-risk-layout">
              <div className={`alpha-risk-score ${risk.block_trade ? "blocked" : "clear"}`}>
                <span>Risk score</span>
                <strong>{risk.risk_score}</strong>
                <em>{risk.block_trade ? "trade blocked" : risk.profit_integrity.replace(/_/g, " ")}</em>
              </div>
              <div className="alpha-risk-flags">
                {risk.flags.length ? risk.flags.slice(0, 6).map((flag) => (
                  <div className="alpha-risk-flag" data-severity={flag.severity} key={flag.code}>
                    <strong>{flag.code.replace(/_/g, " ")}</strong>
                    <span>{flag.detail}</span>
                  </div>
                )) : (
                  <div className="alpha-empty small">No blocking risk flags. If you entered only a symbol, this is a manual sandbox, not live token stats.</div>
                )}
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="alpha-panel">
        <div className="alpha-panel-header">
          <div>
            <div className="alpha-panel-title">{t("alpha.walletDiscovery")}</div>
            <div className="alpha-panel-subtitle">Global Cielo feed ranking. Not tied to the connected wallet.</div>
          </div>
          <div className="alpha-toolbar">
            <input
              value={discoveryMinUsd}
              onChange={(event) => setDiscoveryMinUsd(event.target.value)}
              placeholder="min USD"
            />
            <input
              value={discoveryToken}
              onChange={(event) => setDiscoveryToken(event.target.value)}
              placeholder="token filter"
            />
            <input
              value={discoveryChain}
              onChange={(event) => setDiscoveryChain(event.target.value)}
              placeholder="chain"
            />
            <button onClick={() => void runWalletDiscovery()} disabled={discoveryLoading}>
              {discoveryLoading ? "Scanning" : "Scan feed"}
            </button>
          </div>
        </div>

        <div className="alpha-discovery-summary">
          <div><span>Candidates</span><strong>{walletDiscovery?.count ?? "-"}</strong></div>
          <div><span>Feed events</span><strong>{walletDiscovery?.feed?.events ?? "-"}</strong></div>
          <div><span>Dedupe</span><strong>{walletDiscovery?.feed?.dedupe?.unique_count ?? "-"}</strong></div>
          <div><span>Latency</span><strong>{walletDiscovery?.latency_ms ? `${walletDiscovery.latency_ms}ms` : "-"}</strong></div>
        </div>

        <div className="alpha-discovery-table">
          <div className="alpha-discovery-row alpha-discovery-head">
            <span>Wallet</span><span>Score</span><span>Flow</span><span>Signals</span><span>Action</span>
          </div>
          {(walletDiscovery?.candidates || []).map((candidate) => (
            <div className="alpha-discovery-row" key={candidate.wallet}>
              <span>
                <strong>{candidate.label || shortId(candidate.wallet)}</strong>
                <em>{shortId(candidate.wallet)} / {(candidate.chains || []).join(", ") || "any chain"}</em>
              </span>
              <span className="alpha-mono">{candidate.score.toFixed(1)}</span>
              <span className="alpha-mono">{money(candidate.flow_usd)}</span>
              <span>
                <strong>{candidate.events} events / {candidate.first_interactions} first</strong>
                <em>{(candidate.assets || []).slice(0, 4).join(", ") || candidate.latest_asset || "no asset"}</em>
              </span>
              <span>
                <div className="alpha-link-actions">
                  <button className="alpha-mini-button" onClick={() => void runWalletIntel(candidate.wallet)} disabled={walletLoading}>
                    analyze
                  </button>
                  {getExplorerAddressUrl(candidate.wallet, candidate.chains?.[0]) && (
                    <a
                      className="alpha-mini-link"
                      href={getExplorerAddressUrl(candidate.wallet, candidate.chains?.[0]) || "#"}
                      target="_blank"
                      rel="noreferrer"
                    >
                      wallet
                    </a>
                  )}
                  {getExplorerTxUrl(candidate.latest_tx, candidate.latest_chain || candidate.chains?.[0]) && (
                    <a
                      className="alpha-mini-link"
                      href={getExplorerTxUrl(candidate.latest_tx, candidate.latest_chain || candidate.chains?.[0]) || "#"}
                      target="_blank"
                      rel="noreferrer"
                    >
                      tx
                    </a>
                  )}
                </div>
              </span>
            </div>
          ))}
          {!discoveryLoading && walletDiscovery && walletDiscovery.candidates.length === 0 && (
            <div className="alpha-empty">No wallet candidates for this filter yet.</div>
          )}
          {!walletDiscovery && <div className="alpha-empty">Scan the global feed to rank wallets before running expensive PnL probes.</div>}
        </div>
      </section>

      <section className="alpha-panel">
        <div className="alpha-panel-header">
          <div>
            <div className="alpha-panel-title">{t("alpha.walletIntel")}</div>
            <div className="alpha-panel-subtitle">{t("alpha.walletIntelSub")}</div>
          </div>
          <div className="alpha-toolbar">
            <input
              className="alpha-wallet-input"
              value={walletQuery}
              onChange={(event) => setWalletQuery(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") void runWalletIntel() }}
              placeholder={t("alpha.walletIntelPlaceholder")}
            />
            <button onClick={() => void runWalletIntel()} disabled={walletLoading}>
              {walletLoading ? t("common.loading") : t("alpha.analyzeWallet")}
            </button>
          </div>
        </div>

        <div className="alpha-wallet-layout">
          <div className="alpha-wallet-summary">
            <span>{t("alpha.wallet")}</span>
            <strong>{walletIntel?.wallet ? shortId(walletIntel.wallet) : t("alpha.notLoaded")}</strong>
            <em>{walletProbe?.status_label ? `${walletProbe.status_label} / ${walletProbe.confidence} ${t("alpha.confidence")}` : walletIntel?.summary.copy_ready ? t("alpha.copyReadyCandidate") : t("alpha.notProbedYet")}</em>
            <div className="alpha-link-actions">
              {walletExplorerUrl && (
                <a className="alpha-mini-link" href={walletExplorerUrl} target="_blank" rel="noreferrer">
                  {t("alpha.openWallet")}
                </a>
              )}
            </div>
            <div className="alpha-wallet-stat-row">
              <div><span>Events</span><strong>{walletIntel?.summary.events ?? "-"}</strong></div>
              <div><span>Swaps</span><strong>{walletIntel?.summary.swaps ?? "-"}</strong></div>
              <div><span>Flow</span><strong>{money(walletIntel?.summary.observed_flow_usd)}</strong></div>
              <div><span>Total PnL</span><strong>{money(walletIntel?.summary.pnl.total_pnl_usd)}</strong></div>
            </div>
          </div>

          <div className="alpha-wallet-providers">
            {(walletIntel?.providers || []).map((provider) => (
              <div className="alpha-provider-row" key={provider.provider}>
                <div>
                  <strong>{provider.provider}</strong>
                  <span>{provider.ok ? `${provider.latency_ms}ms` : provider.error || provider.status}</span>
                </div>
                <em className={provider.ok ? "ready" : "missing"}>{provider.status}</em>
              </div>
            ))}
            {!walletIntel && <div className="alpha-empty small">Run a wallet analysis to check providers.</div>}
          </div>
        </div>

        <div className="alpha-probe-strip">
          <div className={`alpha-probe-card ${walletProbe?.status || "idle"}`}>
            <span>{t("alpha.verdict")}</span>
            <strong>{walletProbe?.status_label || t("alpha.awaitingProbe")}</strong>
            <em>{walletProbe ? `${walletProbe.confidence} ${t("alpha.confidence")}` : t("alpha.runAnalyzeWalletCandidate")}</em>
          </div>
          <div className="alpha-probe-card">
            <span>100 EUR Proxy</span>
            <strong className={(walletProbe?.copy_preview?.pnl || 0) >= 0 ? "positive" : "negative"}>
              {walletProbe ? money(walletProbe.copy_preview.estimated_value) : "-"}
            </strong>
            <em>
              {walletProbe
                ? `${walletProbe.copy_preview.mode} / ${(walletProbe.copy_preview.pnl || 0) >= 0 ? "+" : ""}${money(walletProbe.copy_preview.pnl)} / ${walletProbe.copy_preview.roi_pct.toFixed(2)}%`
                : "No copy proxy yet"}
            </em>
          </div>
          <div className="alpha-probe-card">
            <span>Provider Coverage</span>
            <strong>{walletProbe ? `${walletProbe.provider_health.ok}/${walletProbe.provider_health.total}` : "-"}</strong>
            <em>
              {walletProbe
                ? `blocked rows ${walletProbe.risk_summary.blocked_rows} / untrusted ${walletProbe.risk_summary.untrusted_rows}`
                : "Need a wallet probe"}
            </em>
          </div>
        </div>

        <div className="alpha-probe-notes">
          <div className="alpha-probe-list">
            <div className="alpha-panel-title mini">Reasons</div>
            {(walletProbe?.reasons || []).map((reason) => (
              <div className="alpha-wallet-row" key={reason}>
                <span>{reason}</span>
              </div>
            ))}
            {walletProbe && walletProbe.reasons.length === 0 && (
              <div className="alpha-empty small">No reasons yet.</div>
            )}
          </div>
          <div className="alpha-probe-list">
            <div className="alpha-panel-title mini">Requirements</div>
            {(walletProbe?.requirements || []).map((requirement) => (
              <div className="alpha-wallet-row" key={requirement}>
                <span>{requirement}</span>
              </div>
            ))}
            {walletProbe && walletProbe.requirements.length === 0 && (
              <div className="alpha-empty small">No extra requirements on this probe.</div>
            )}
          </div>
        </div>

        <div className="alpha-related-section">
          <div className="alpha-panel-title mini">Related Wallets</div>
          <div className="alpha-panel-subtitle alpha-inline-note">Current feed sample only. Shared assets/chains, not a full identity graph yet.</div>
          <div className="alpha-related-grid">
            {relatedCandidates.map((candidate) => {
              const candidateChain = candidate.latest_chain || candidate.chains?.[0]
              const explorerUrl = getExplorerAddressUrl(candidate.wallet, candidateChain)
              const txUrl = getExplorerTxUrl(candidate.latest_tx, candidateChain)
              return (
                <div className="alpha-related-card" key={candidate.wallet}>
                  <div>
                    <strong>{candidate.label || shortId(candidate.wallet)}</strong>
                    <em>{shortId(candidate.wallet)} / {(candidate.chains || []).join(", ") || "any chain"}</em>
                  </div>
                  <div className="alpha-related-meta">
                    <span>relation {candidate.relationScore}</span>
                    <span>{money(candidate.flow_usd)} / {candidate.events} events</span>
                  </div>
                  <div className="alpha-related-meta">
                    <span>shared chains: {candidate.sharedChains.join(", ") || "-"}</span>
                    <span>shared assets: {candidate.sharedAssets.slice(0, 3).join(", ") || "-"}</span>
                  </div>
                  <div className="alpha-link-actions">
                    <button className="alpha-mini-button" onClick={() => void runWalletIntel(candidate.wallet)} disabled={walletLoading}>
                      analyze
                    </button>
                    {explorerUrl && (
                      <a className="alpha-mini-link" href={explorerUrl} target="_blank" rel="noreferrer">
                        wallet
                      </a>
                    )}
                    {txUrl && (
                      <a className="alpha-mini-link" href={txUrl} target="_blank" rel="noreferrer">
                        tx
                      </a>
                    )}
                  </div>
                </div>
              )
            })}
            {walletProbe && relatedCandidates.length === 0 && (
              <div className="alpha-empty small">No related wallets surfaced in the current discovery sample.</div>
            )}
          </div>
        </div>

        <div className="alpha-related-section">
          <div className="alpha-panel-title mini">{t("alpha.evidenceGraph")}</div>
          <div className="alpha-panel-subtitle alpha-inline-note">
            Weighted evidence graph from direct flows, swap venues and touched assets. It is a proof surface, not an ownership claim.
          </div>

          <div className="alpha-graph-summary">
            <div>
              <span>Nodes</span>
              <strong>{walletGraph?.summary.nodes ?? "-"}</strong>
            </div>
            <div>
              <span>Edges</span>
              <strong>{walletGraph?.summary.edges ?? "-"}</strong>
            </div>
            <div>
              <span>Venues</span>
              <strong>{walletGraph?.summary.venues ?? "-"}</strong>
            </div>
            <div>
              <span>Assets</span>
              <strong>{walletGraph?.summary.assets ?? "-"}</strong>
            </div>
          </div>

          <div className="alpha-graph-map">
            <div className="alpha-graph-root">
              <span>Root wallet</span>
              <strong>{walletGraph?.wallet ? shortId(walletGraph.wallet) : "-"}</strong>
              <em>{walletGraph?.summary.evidence_grade || "waiting for probe"}</em>
            </div>
            <div className="alpha-graph-edge-list">
              {(walletGraph?.edges || []).slice(0, 10).map((edge, index) => {
                const target = graphNodesById.get(edge.target)
                const chain = edge.latest_chain || target?.chain || walletPrimaryChain
                const targetExplorerUrl = getExplorerAddressUrl(target?.address, chain)
                const txUrl = getExplorerTxUrl(edge.latest_tx, chain)
                return (
                  <div className="alpha-graph-edge-row" key={`${edge.source}:${edge.target}:${index}`}>
                    <div className="alpha-graph-node">
                      <span>{target?.kind || edge.kind}</span>
                      <strong>{target?.label || edge.target}</strong>
                      <em>{money(edge.amount_usd)} / {edge.events} events</em>
                    </div>
                    <div className="alpha-graph-edge-metrics">
                      <span>weight {edge.weight.toFixed(1)}</span>
                      <span>confidence {pct(edge.confidence)}</span>
                    </div>
                    <div className="alpha-link-actions">
                      {target?.address && (
                        <button className="alpha-mini-button" onClick={() => void runWalletIntel(target.address || "")} disabled={walletLoading}>
                          analyze
                        </button>
                      )}
                      {targetExplorerUrl && (
                        <a className="alpha-mini-link" href={targetExplorerUrl} target="_blank" rel="noreferrer">
                          wallet
                        </a>
                      )}
                      {txUrl && (
                        <a className="alpha-mini-link" href={txUrl} target="_blank" rel="noreferrer">
                          tx
                        </a>
                      )}
                    </div>
                  </div>
                )
              })}
              {walletProbe && (!walletGraph || walletGraph.edges.length === 0) && (
                <div className="alpha-empty small">No graph edges in the current wallet sample.</div>
              )}
            </div>
          </div>
        </div>

        <div className="alpha-related-section">
          <div className="alpha-panel-title mini">{t("alpha.transferSurface")}</div>
          <div className="alpha-panel-subtitle alpha-inline-note">
            Feed-derived counterparties and venues from recent wallet activity. Useful for spotting routing habits and real interaction surfaces.
          </div>

          <div className="alpha-surface-strip">
            <div className="alpha-surface-card">
              <span>Inflow</span>
              <strong>{money(walletSurface?.summary.inflow_usd)}</strong>
              <em>{walletSurface?.summary.transfers ?? "-"} transfers</em>
            </div>
            <div className="alpha-surface-card">
              <span>Outflow</span>
              <strong>{money(walletSurface?.summary.outflow_usd)}</strong>
              <em>net {money(walletSurface?.summary.net_transfer_usd)}</em>
            </div>
            <div className="alpha-surface-card">
              <span>Swap Surface</span>
              <strong>{money(walletSurface?.summary.swap_usd)}</strong>
              <em>{walletSurface?.summary.venues ?? "-"} venues</em>
            </div>
            <div className="alpha-surface-card">
              <span>Counterparties</span>
              <strong>{walletSurface?.summary.counterparties ?? "-"}</strong>
              <em>{walletSurface?.summary.events ?? "-"} feed events</em>
            </div>
          </div>

          <div className="alpha-surface-grid">
            <div>
              <div className="alpha-panel-title mini">Top Counterparties</div>
              {(walletSurface?.counterparties || []).slice(0, 6).map((item) => (
                <div className="alpha-wallet-row" key={`${item.kind}:${item.address || item.label}`}>
                  <div className="alpha-row-main">
                    <span>{item.label}</span>
                    <strong>{money(item.inflow_usd + item.outflow_usd + item.swap_usd)}</strong>
                    <em>
                      in {money(item.inflow_usd)} / out {money(item.outflow_usd)} / swap {money(item.swap_usd)}
                    </em>
                  </div>
                  <div className="alpha-link-actions">
                    {item.address && (
                      <button className="alpha-mini-button" onClick={() => void runWalletIntel(item.address)} disabled={walletLoading}>
                        analyze
                      </button>
                    )}
                    {item.address && getExplorerAddressUrl(item.address, item.latest_chain || item.chains?.[0]) && (
                      <a className="alpha-mini-link" href={getExplorerAddressUrl(item.address, item.latest_chain || item.chains?.[0]) || "#"} target="_blank" rel="noreferrer">
                        wallet
                      </a>
                    )}
                    {getExplorerTxUrl(item.latest_tx, item.latest_chain || item.chains?.[0]) && (
                      <a className="alpha-mini-link" href={getExplorerTxUrl(item.latest_tx, item.latest_chain || item.chains?.[0]) || "#"} target="_blank" rel="noreferrer">
                        tx
                      </a>
                    )}
                  </div>
                </div>
              ))}
              {walletSurface && walletSurface.counterparties.length === 0 && (
                <div className="alpha-empty small">No direct counterparties in the current surface sample.</div>
              )}
            </div>

            <div>
              <div className="alpha-panel-title mini">Venue Surface</div>
              {(walletSurface?.venues || []).slice(0, 6).map((venue) => (
                <div className="alpha-wallet-row" key={venue.name}>
                  <div className="alpha-row-main">
                    <span>{venue.name}</span>
                    <strong>{money(venue.amount_usd)}</strong>
                    <em>{venue.events} events / {(venue.assets || []).slice(0, 3).join(", ") || "no asset"}</em>
                  </div>
                  <div className="alpha-link-actions">
                    {getExplorerTxUrl(venue.latest_tx, venue.latest_chain || venue.chains?.[0]) && (
                      <a className="alpha-mini-link" href={getExplorerTxUrl(venue.latest_tx, venue.latest_chain || venue.chains?.[0]) || "#"} target="_blank" rel="noreferrer">
                        tx
                      </a>
                    )}
                  </div>
                </div>
              ))}
              {walletSurface && walletSurface.venues.length === 0 && (
                <div className="alpha-empty small">No venue surface detected yet.</div>
              )}
            </div>

            <div>
              <div className="alpha-panel-title mini">Recent Flow</div>
              {(walletSurface?.activity || []).slice(0, 6).map((activity, index) => (
                <div className="alpha-wallet-row" key={`${activity.tx_hash || activity.timestamp || index}`}>
                  <div className="alpha-row-main">
                    <span>{activity.direction} / {activity.event_type}</span>
                    <strong>{activity.asset || activity.dex || activity.counterparty.label || "-"}</strong>
                    <em>{money(activity.amount_usd)} / {activity.chain || "-"} / {activity.timestamp || "no timestamp"}</em>
                  </div>
                  <div className="alpha-link-actions">
                    {activity.counterparty?.address && getExplorerAddressUrl(activity.counterparty.address, activity.chain) && (
                      <a className="alpha-mini-link" href={getExplorerAddressUrl(activity.counterparty.address, activity.chain) || "#"} target="_blank" rel="noreferrer">
                        wallet
                      </a>
                    )}
                    {getExplorerTxUrl(activity.tx_hash, activity.chain) && (
                      <a className="alpha-mini-link" href={getExplorerTxUrl(activity.tx_hash, activity.chain) || "#"} target="_blank" rel="noreferrer">
                        tx
                      </a>
                    )}
                  </div>
                </div>
              ))}
              {walletSurface && walletSurface.activity.length === 0 && (
                <div className="alpha-empty small">No recent activity rows in this sample.</div>
              )}
            </div>
          </div>
        </div>

        <div className="alpha-wallet-detail">
          <div>
            <div className="alpha-panel-title mini">PnL Rows</div>
            {(walletIntel?.pnl || []).slice(0, 5).map((row, index) => (
              <div className="alpha-wallet-row" key={`${row.provider}:${row.token}:${index}`}>
                <span>{row.provider} / {row.token}</span>
                <strong>{money(row.total_pnl_usd)}</strong>
                <em>{row.profit_integrity || "unknown"} / risk {row.risk_score ?? "-"}</em>
              </div>
            ))}
            {walletIntel && walletIntel.pnl.length === 0 && (
              <div className="alpha-empty small">No PnL rows yet. Add CIELO_API_KEY or ZERION_API_KEY to enable live wallet PnL.</div>
            )}
          </div>
          <div>
            <div className="alpha-panel-title mini">Recent Events</div>
            {(walletIntel?.events || []).slice(0, 5).map((event, index) => (
              <div className="alpha-wallet-row" key={`${event.source}:${index}`}>
                <div className="alpha-row-main">
                  <span>{event.source} / {event.event_type}</span>
                  <strong>{event.asset || event.chain || "-"}</strong>
                  <em>{event.timestamp || "no timestamp"}</em>
                </div>
                <div className="alpha-link-actions">
                  {getExplorerAddressUrl(event.actor || walletIntel?.wallet, event.chain) && (
                    <a
                      className="alpha-mini-link"
                      href={getExplorerAddressUrl(event.actor || walletIntel?.wallet, event.chain) || "#"}
                      target="_blank"
                      rel="noreferrer"
                    >
                      wallet
                    </a>
                  )}
                  {getExplorerTxUrl(event.tx_hash || event.source_event_id, event.chain) && (
                    <a
                      className="alpha-mini-link"
                      href={getExplorerTxUrl(event.tx_hash || event.source_event_id, event.chain) || "#"}
                      target="_blank"
                      rel="noreferrer"
                    >
                      tx
                    </a>
                  )}
                </div>
              </div>
            ))}
            {walletIntel && walletIntel.events.length === 0 && (
              <div className="alpha-empty small">No wallet feed events yet. Cielo feed activates after CIELO_API_KEY is configured.</div>
            )}
          </div>
          <div>
            <div className="alpha-panel-title mini">Asset Focus</div>
            {(walletProbe?.asset_focus || []).slice(0, 5).map((asset) => (
              <div className="alpha-wallet-row" key={`${asset.chain}:${asset.asset}`}>
                <div className="alpha-row-main">
                  <span>{asset.asset} / {asset.chain}</span>
                  <strong>{money(asset.amount_usd)}</strong>
                  <em>{asset.events} events</em>
                </div>
                {walletExplorerUrl && (
                  <div className="alpha-link-actions">
                    <a className="alpha-mini-link" href={walletExplorerUrl} target="_blank" rel="noreferrer">
                      wallet
                    </a>
                  </div>
                )}
              </div>
            ))}
            {walletProbe && walletProbe.asset_focus.length === 0 && (
              <div className="alpha-empty small">No ranked asset focus yet for this wallet.</div>
            )}
          </div>
        </div>
      </section>
      </details>
    </div>
  )
}
