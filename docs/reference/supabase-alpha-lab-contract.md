# Core Equity Supabase Alpha Lab Contract

Status: draft, not active.

This document defines the minimum Supabase shape we can review before moving any client data out of the local Core Equity files. It is intentionally conservative: Supabase is useful for client accounts, wallet links, Alpha Lab history, audit logs and usage analytics, but it must not become a shortcut around the current safety gates.

## Safety Rules

- No seed phrase, private key, mnemonic, auth token, API key, raw signature or cookie is stored.
- `SUPABASE_SERVICE_ROLE_KEY` is backend-only and must never be bundled into frontend code.
- Client-facing reads should go through the Core Equity backend first; direct Supabase client access can come later only after RLS is tested.
- Wallet connection remains read-only. No approvals, no spend permissions, no transaction execution.
- Alpha Lab records must preserve:
  - `client_execution_enabled=false`
  - `copy_trade_enabled=false`
  - `profit_guarantee_allowed=false`
  - `source_policy`
  - `verdict=inconclusive` when proof is insufficient.

## Environment Gates

```text
SUPABASE_ENABLED=false
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
CORE_SUPABASE_WRITE_MODE=dry_run
```

Recommended behavior:

- `SUPABASE_ENABLED=false`: use current local JSONL/SQLite only.
- `CORE_SUPABASE_WRITE_MODE=dry_run`: backend may build payload previews but writes nothing.
- `CORE_SUPABASE_WRITE_MODE=mirror`: backend can write sanitized copies after RLS/schema review.
- No destructive migration mode until we have backups and rollback.

## Tables Draft

### `core_clients`

Purpose: identify a customer without storing secrets.

```sql
create table core_clients (
  id uuid primary key default gen_random_uuid(),
  display_name text,
  status text not null default 'active',
  tier text not null default 'private_beta',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

### `client_wallets`

Purpose: keep wallet links and verification status. Raw public address is optional; hashed address is mandatory.

```sql
create table client_wallets (
  id uuid primary key default gen_random_uuid(),
  client_id uuid references core_clients(id) on delete cascade,
  chain text not null,
  address_hash text not null,
  address_short text not null,
  public_address text,
  provider text,
  wallet_kind text not null default 'read_only',
  verification_status text not null default 'unverified',
  verified_at timestamptz,
  session_scope text not null default 'alpha_lab_read_only',
  created_at timestamptz not null default now(),
  unique (client_id, chain, address_hash)
);
```

### `alpha_analysis_runs`

Purpose: client-readable Alpha Lab history and 100 USD replay summaries.

```sql
create table alpha_analysis_runs (
  id uuid primary key default gen_random_uuid(),
  client_id uuid references core_clients(id) on delete cascade,
  wallet_id uuid references client_wallets(id) on delete set null,
  run_type text not null default 'wallet_research',
  status text not null default 'inconclusive',
  verdict_tier text not null default 'inconclusive',
  confidence_score integer not null default 0,
  replay_capital_usd numeric not null default 100,
  replay_value_usd numeric,
  replay_roi_pct numeric,
  safe_next_action text,
  source_policy text not null,
  client_execution_enabled boolean not null default false,
  copy_trade_enabled boolean not null default false,
  profit_guarantee_allowed boolean not null default false,
  created_at timestamptz not null default now()
);
```

### `alpha_evidence_items`

Purpose: explain why a verdict exists without storing unsafe raw payloads.

```sql
create table alpha_evidence_items (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references alpha_analysis_runs(id) on delete cascade,
  evidence_type text not null,
  label text not null,
  source text not null,
  source_url text,
  confidence text not null default 'low',
  payload_redacted jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
```

### `alpha_usage_events`

Purpose: product analytics with minimized identity.

```sql
create table alpha_usage_events (
  id uuid primary key default gen_random_uuid(),
  client_id uuid references core_clients(id) on delete set null,
  action text not null,
  page text not null default 'alpha',
  wallet_hash text,
  wallet_short text,
  status text,
  extra_redacted jsonb not null default '{}'::jsonb,
  client_host_hash text,
  user_agent text,
  created_at timestamptz not null default now()
);
```

### `core_audit_logs`

Purpose: admin/client audit trail for sensitive operations and dry-runs.

```sql
create table core_audit_logs (
  id uuid primary key default gen_random_uuid(),
  actor_type text not null,
  actor_hash text,
  action text not null,
  resource text not null,
  result text not null,
  metadata_redacted jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
```

## RLS Draft

Initial private beta recommendation: do not expose direct Supabase reads to clients. Use the backend session/token gate.

Later, if direct Supabase client reads are needed:

- Enable RLS on all tables.
- `core_clients`: client can read only their own row.
- `client_wallets`: client can read only wallets linked to their `client_id`.
- `alpha_analysis_runs`: client can read only their own runs.
- `alpha_evidence_items`: client can read only evidence for their own runs.
- `alpha_usage_events`: backend insert only; client should not query raw analytics.
- `core_audit_logs`: admin/service only.

## First Implementation Step

Do not migrate yet. Add a backend Supabase adapter only after this contract is accepted:

1. Keep local JSONL/SQLite as source of truth.
2. Add a sanitizer that converts existing usage events and Alpha Lab summaries into this schema.
3. Run in `dry_run` and compare payloads.
4. Add tests proving sensitive fields are redacted.
5. Only then allow `mirror` mode.
