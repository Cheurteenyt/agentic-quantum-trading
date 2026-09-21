# Core Equity Prompt Manager - Read-Only

Last updated: 2026-05-23.

## Purpose

The Core Equity Prompt Manager is a read-only project pilot.

It turns RAG memory into:
- where the project is now in simple language
- what is ready
- what is blocked
- the next safest mission prompt
- mandatory guardrails
- validation checklist

It does not operate Core Equity.

Important:
- Do not depend on the UI `/goal` command.
- If `/goal` fails or is unavailable, output `MISSION DIRECTE:` instead.
- If the user says `continue`, Codex should execute the current recommended mission from this file.

## Allowed Inputs

Read only:
- `rag/memory/core_equity_operating_map.md`
- `rag/memory/current_automation_state.md`
- `rag/memory/core_equity_management_map.md`
- `rag/memory/core_equity_agent_control_plane.md`
- `rag/memory/core_equity_agent_task_graph.md`
- `rag/memory/core_equity_agent_os_runtime_policy.md`
- `rag/memory/dex_local_event_reader_plan.md`
- `rag/memory/project_state.md` only when history is needed

## Forbidden Actions

The Prompt Manager must never:
- run endpoints
- read or write the live DB
- create migrations
- update statuses
- create CEX labels
- create DEX mappings
- create DEX router evidence
- create client signals
- execute trades, swaps, wallet orders or perps
- create or modify opt-ins/consent
- call unrestricted providers
- scrape external sources without explicit product decision
- handle credentials or secrets
- operate Hermes/CrewAI/agents against Core Equity runtime

## Output Format

Every Prompt Manager answer should include:

### 1. Simple Status

Use simple wording.

Template:

```text
On en est ici:
- La meilleure piste actuelle est: <lead>.
- Elle est utile parce que: <why>.
- Elle bloque encore parce que: <blockers>.
- Elle ne produit toujours pas: <mapping/signal/trade/etc>.
```

### 2. Ready

List only what is actually ready according to RAG.

### 3. Still Disabled

Always include:
- real CEX label
- final label table mutation
- DEX router evidence
- DEX mapping
- client signal
- trade/swap/wallet order/perps
- client opt-in/consent
- unrestricted providers/scraping
- Hermes/CrewAI as Core Equity operators

### 4. Recommended Next Mission

Generate exactly one primary mission.

Rules:
- Prefer `MISSION DIRECTE:` over `/goal`.
- Keep the mission short enough to paste in chat.
- Prefer data-quality progress.
- Prefer read-only first.
- Use dry-run-first inserts only when data-only and already planned.
- Require strict expected digest/dedupe guards.

Avoid:
- extra review plumbing when a data blocker is obvious
- mapping/signal/trade/label/opt-in
- famous-token manual picks
- repeating provider paths already known to fail

### 5. Validation Checklist

Always include:
- admin token if endpoint-facing
- dry-run default or dry-run required
- exact expected digest/dedupe when real insert is allowed
- duplicate blocked
- DB write scope exact
- no mapping/signal/trade/label/opt-in
- post-check counters

## Current Recommended Output

### Simple Status

On en est ici:
- Core Equity ne detecte pas encore une manipulation fiable pour client/trading.
- UFLOKI reste une recherche utile, mais son replay long-style est rejete par les seuils actuels.
- Les 3 candidats top-expansion ont maintenant 437 raw events persistés.
- La nouvelle preview comportementale score ces 3 candidats sans exiger de docs officielles.
- Resultat: 2 candidats forts a 82, 1 candidat modere a 70.
- Le shadow outcome/backtest read-only des 2 candidats forts dit: comportement suspect, mais pas encore exploitable economiquement dans l'echantillon local.
- Le filtre tradability/honeypot read-only observe des ventes apres T0 pour les 2 candidats forts: le blocage principal devient donc le timing T0, pas un honeypot evident.
- Le T0 shift read-only a ete execute: les seuils plus tot `40/50/60/70` ne produisent toujours pas d'edge positif apres frictions sur wkeyDAO2 et ARK.
- Le directional intent classifier read-only a ete execute: 0 candidat alpha-ready, 2 candidats demandent holder-freeze context, 1 candidat ressemble a distribution/sell pressure.
- Le stealth accumulation scan read-only a ete execute: 4 pools scannes, 0 stealth accumulator trouve. La data actuelle est trop etroite et biaisee vers wash/distribution/active pools.
- Le stealth funnel diagnostic read-only confirme que ce n'est pas juste un seuil trop strict:
  total pools `4`, low circularity `1`, high hold `0`, low circularity + high hold `0`, quiet pools `0`.
- Cela ne cree toujours aucun mapping, signal client, trade, label ou opt-in.

### Ready

Pret:
- UFLOKI evidence/replay lane read-only, including rejection of current long-style signal.
- Top-expansion raw context persisted: 150 Swap, 150 Sync, 137 ERC20 Transfer rows.
- Behavioral anomaly scoring preview ready:
  `/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-anomaly-scoring-preview`
- Strong behavioral candidates:
  `0xb720ea2a201c03578cca05191e8b4ab859704cfe`, score 82, `wkeyDAO2`, friction-adjusted MFE about -9.72%.
  `0xcaaf3c41a40103a23eeaa4bba468af3cf5b0e0d8`, score 82, `ARK`, friction-adjusted MFE about -9.75%.
- Moderate candidate:
  `0xd7f940ba6954900b2f12ba3a9dee603d6f485452`, score 70.
- Behavioral shadow outcome/backtest plan ready:
  `/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-shadow-outcome-backtest-plan`
- Behavioral tradability filter preview ready:
  `/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-tradability-filter-preview`
- Tradability live result:
  `wkeyDAO2`: 28 successful sell rows after T0.
  `ARK`: 20 successful sell rows after T0.
- Behavioral T0 shift experiment ready:
  `/api/onchain/rpc/manipulation-detection-top-expansion-behavioral-t0-shift-experiment-preview`
- T0 shift live result:
  `wkeyDAO2`: best threshold `70`, MFE about `0.25%`, friction-adjusted MFE about `-9.75%`.
  `ARK`: best threshold `40`, MFE about `0.5032%`, friction-adjusted MFE about `-9.4968%`.
- Directional intent classifier ready:
  `/api/onchain/rpc/manipulation-detection-top-expansion-directional-intent-classifier-preview`
- Directional intent live result:
  `wkeyDAO2`: weak accumulation needing holder context, hold proxy about `44.26%`, circularity about `66%`.
  `ARK`: weak accumulation needing holder context, hold proxy about `17.58%`, circularity about `70%`.
  `Bun`: distribution/sell pressure, hold proxy `0%`.
- Stealth accumulation scan ready:
  `/api/onchain/rpc/manipulation-detection-stealth-accumulation-anomaly-scan-preview`
- Stealth scan live result:
  `4` pools scanned, `0` stealth accumulation candidates.
- Stealth funnel diagnostic ready:
  `/api/onchain/rpc/manipulation-detection-stealth-funnel-diagnostic-preview`
- Funnel diagnostic live result:
  `4` pools checked, `0` low-circularity + high-hold pools, `0` quiet pools.
- Quiet Pool Scanner plan ready:
  `/api/onchain/rpc/manipulation-detection-quiet-pool-scanner-plan-preview`
- Quiet Pool Scanner live result with strict 7-day survival:
  `100` pair pools checked, `99` quiet surface candidates, `100` transfer-context possible, `0` survival-context possible, `0` plan-ready candidates.
- CEX Listing Probability Bridge ready:
  `/api/onchain/rpc/manipulation-detection-cex-listing-probability-bridge-preview`
- CEX Listing Bridge live result:
  `3` behavioral candidates checked, `0` matching CEX token deposits, `0` high/medium listing-priority candidates, `0` CEX-deposit-only tokens.
- Behavior score can run without official docs.
- Official/source identity is still separate and required before mapping/signal/trade.
- Agent Control Plane and Task Graph remain read-only.

### Still Disabled

Toujours desactive:
- real CEX label
- final label table mutation
- DEX router evidence
- DEX mapping
- client signal
- trade/swap/wallet order/perps
- client opt-in/consent
- unrestricted providers/scraping
- Hermes/CrewAI as Core Equity operators

### Recommended Next Mission

```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite CEX Listing Ground Truth Dataset Plan read-only.

Objectif:
Preparer un plan read-only pour construire un dataset de ground truth listing CEX afin de backtester le CEX Listing Bridge.

Pourquoi:
Le CEX Listing Bridge est code et fonctionne, mais la DB actuelle ne contient aucun depot CEX correspondant aux 3 candidats comportementaux.
Pour savoir si l'hypothese LAB/RAVE est exploitable, il faut un dataset read-only de listings connus:
- token
- chain
- CEX
- announcement/listing date
- source URL
- tier
- pre-listing on-chain window
- matching token_transfers / CEX deposits if available

Garde-fous:
- admin token obligatoire
- read-only
- aucune mutation DB
- aucun provider/scraping
- aucun score client persiste
- aucun signal client
- aucun mapping DEX
- aucun router evidence DEX
- aucun label CEX
- aucun trade
- aucun ordre wallet
- aucun opt-in client

Validation:
- lit seulement les tables locales existantes
- propose schema/format dataset sans creer de table
- liste sources autorisees futures: CEX announcement pages, CoinGecko/CCXT metadata, manual source-backed rows
- aucun provider/scraping actif sans mission explicite
- explique comment backtester J-30/J-7/J-1 contre le bridge
- indique quels champs manquent aujourd'hui
- garde source identity separee du comportement
- indique si une future bounded raw context lookup serait justifiee
- official/source identity reste separee
- can_detect_reliable_manipulation_now=false
- would_write=false
- writes_performed=0
- aucun mapping/signal/trade/label/opt-in
```

Important:
- Use `rag/memory/core_equity_agent_control_plane.md` as the current machine-readable source before generating the next mission.
- Do not promote behavioral anomaly score into client signal/trade unless shadow outcome/backtest, negative controls, policy/risk gates and opt-in pass under a future explicit mission.

### Validation Checklist

Valider:
- non-admin refuse
- dry-run ne modifie rien
- route/service retourne les candidats forts
- no mapping/signal/trade/label/opt-in
- DB metier inchangee

### Current Recommended Next Mission

```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite older CEX-like behavioral candidate collection plan read-only.

Objectif:
Preparer un plan read-only pour obtenir des candidats plus anciens et plus CEX-like afin de construire des negatifs valides pour le CEX Listing Bridge.

Pourquoi:
Le seed positif est pret, mais la negative cohort discovery montre que les 3 candidats locaux actuels sont trop recents et sans contexte CEX deposit. Il faut une selection/collecte differente pour trouver de vrais negatifs `never_listed_90d`.

Garde-fous:
- read-only
- aucun insert DB
- aucun provider payant
- aucun scraping non borne
- aucun listing signal
- aucun label CEX
- aucun mapping DEX
- aucun router evidence DEX
- aucun signal client
- aucun trade
- aucun ordre wallet
- aucun opt-in client

Validation:
- expliquer quelles donnees locales manquent
- proposer une collecte ou selection bornee d'anciens candidats (>90 jours) avec CEX-like context
- separer candidats pour negative verification vs candidats a rejeter
- aucun signal/trade/label/mapping/opt-in
- would_write=false
- writes_performed=0

Resume attendu:
- pourquoi les negatifs ne sont pas encore disponibles
- plan de collecte/selection pour negatifs
- comment cela debloque le backtest CEX Listing Bridge
```

### Superseding Recommended Next Mission

```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite LAB/B targeted raw context backfill plan read-only.

Objectif:
Preparer un plan read-only de backfill raw context pour LAB et B afin de rendre possible le futur feature backfill orchestrator.

Pourquoi:
L'orchestrateur feature backfill confirme que LAB/B ne sont pas raw-ready.
LAB a seulement 4 transfers, 0 pool, 0 raw swaps.
B a 22 transfers, 1 pool, mais 0 raw swaps/syncs.
On ne peut pas rejouer proprement les pipelines de features sans Swap/Sync/Transfer context suffisant.

Garde-fous:
- dry-run obligatoire
- read-only
- aucun insert DB
- aucun raw event persisté
- aucun provider/scraping libre sans plan borne
- aucun feature table write
- aucun ground truth insert
- aucun signal listing
- aucun signal client
- aucun label CEX
- aucun mapping DEX
- aucun trade
- aucun ordre wallet
- aucun opt-in client

Validation:
- entree: LAB et B seed tokens
- lister raw context actuel par token
- proposer windows/filtres Swap, Sync, Transfer bornes
- indiquer si pair discovery est necessaire avant Swap/Sync pour LAB
- aucun appel provider non borne
- aucun write
- no DB write
- would_write=false
- writes_performed=0

Resume attendu:
- plan de backfill raw LAB/B
- pourquoi feature backfill reste bloque
- prochaine action: bounded raw lookup dry-run, pas signal/trade
- pourquoi aucun insert/signal/trade n'est cree
```

## 2026-05-23 Prompt Manager Note - CEX Listing Raw Context Repair

Current product direction:
- Do not add more ad-hoc scoring code for LAB/B.
- Use the generic feature repair lane:
  1. diagnose feature wiring,
  2. plan raw context backfill,
  3. run bounded raw lookup dry-run,
  4. only then consider evidence-only persistence and feature replay.

Current state:
- LAB/B targeted raw context backfill plan is exposed and smoke-tested.
- `B` is ready for a bounded raw Swap/Sync/Transfer lookup dry-run.
- `LAB` needs bounded pair discovery before Swap/Sync lookup.
- No signal/trade/mapping/label/ground-truth insert is allowed at this stage.

Prompt Manager next preferred goal:
```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite B seed bounded raw Swap/Sync/Transfer lookup dry-run read-only.
```

## 2026-05-23 Prompt Manager Note - B Raw Context Found

Current state:
- `B` seed bounded SQD lookup succeeded in read-only dry-run.
- Found in memory: 60 Swap, 60 Sync, 60 ERC20 Transfer logs.
- No persistence happened.
- This is now the concrete data bridge needed before replaying CEX listing features.

Prompt Manager next preferred goal:
```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite B raw context evidence-only schema-plan read-only.
```

Do not jump to scoring/trading yet. The correct next step is evidence-only schema/insert dry-run-first, then feature backfill orchestrator replay preview.

## 2026-05-23 Prompt Manager Correction - Raw Schema Exists

Correction:
- Do not propose `B raw context evidence-only schema-plan` as the next goal.
- The raw schema/table lane already exists through the top-expansion raw context evidence endpoints.
- The useful next step is a B-only insert dry-run-first adapter/path that reuses existing tables and dedupe rules.

Correct next preferred goal:
```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite B raw context evidence insert dry-run-first using existing raw tables.
```

## 2026-05-23 Prompt Manager Note - B Raw Evidence Dry-Run Ready

Current state:
- B raw context evidence insert dry-run-first is implemented and smoke-tested.
- Dry-run found 180 clean insertable raw events into existing tables:
  - 60 Swap -> dex_raw_swap_events
  - 60 Sync -> dex_raw_sync_events
  - 60 ERC20 Transfer -> erc20_transfer_events
- Required real insert confirm: `INSERT_B_SEED_RAW_CONTEXT_EVIDENCE`.
- Required expected digest: `9c901d4e76ba57d00d2e5654f92a3b72954ef71f7e74cfe4ba2fe6b7ef7d961d`.

Prompt Manager next preferred goal:
```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite B raw context evidence confirmed insert evidence-only.
```

After confirmed evidence-only insert, the correct next step is feature backfill orchestrator replay preview for B, not signal/trade.

## 2026-05-23 Prompt Manager Note - B Raw Evidence Inserted

Current state:
- B seed raw evidence has been inserted evidence-only into existing raw tables.
- Inserted rows: 180 total = 60 Swap + 60 Sync + 60 ERC20 Transfer.
- Business/signal tables remain unchanged.
- Duplicate protection verified.

Prompt Manager next preferred goal:
```text
MISSION DIRECTE: Continue Core Equity en mode economique, priorite B feature backfill orchestrator replay preview read-only.
```

The goal is to see whether the generic feature pipelines now become executable from SQL-visible B raw data. Do not create signals/trades.
