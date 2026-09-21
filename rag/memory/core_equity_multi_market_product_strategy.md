# Core Equity Multi-Market Product Strategy

## Purpose

Core Equity should become a multi-market intelligence and execution-control system, not a single-chain token scanner.

Long-term target:
- detect manipulation and opportunity patterns across spot, perps, DEX, CEX, EVM chains, and Solana
- adapt recommendations to the client's capital, risk tolerance, venue access, and allowed markets
- run shadow and paper trading before any real execution
- keep final execution controlled by policy, risk limits, opt-in, audit logs, and kill switches

## Current Useful Foundation

The project already has serious early building blocks:
- local swap and transfer ingestion
- wallet/entity graph work
- CEX deposit/funding context
- DEX venue/source repair
- amount USD quarantine
- raw Swap-log provenance
- future curated DEX trade schema path
- adaptive accumulation scan
- adaptive accumulation backtest
- strategy matrix
- accumulator wallet profiles
- accumulator cluster scan
- manipulation casefile/readiness surfaces

This means Core Equity is not starting from zero. The next challenge is to make these systems faster, cleaner, broader, and more data-reliable.

## Market Lanes

### Spot Trading Lane

Purpose:
- detect spot opportunities where a token can be bought/sold directly
- focus on liquidity, slippage, venue quality, source-backed token identity, and real flow

Required before real spot execution:
- curated DEX/CEX trade facts
- token metadata quality
- source-backed route/venue identity
- liquidity and slippage simulation
- manipulation thesis packet
- shadow/paper history
- client risk policy and opt-in

Spot is the first realistic execution lane because it is easier to constrain than perps.

### Perps Trading Lane

Purpose:
- detect opportunities where leverage/perp structure is appropriate
- include funding rates, liquidation clusters, open interest, volatility, depth, and exchange-specific risk

Perps must not be treated like spot.

Required extra gates:
- venue support and account permissions
- leverage cap
- liquidation distance
- funding impact
- max notional exposure
- market depth/liquidation risk
- forced stop/kill-switch policy
- client suitability profile

Perps should remain blocked until the data engine has reliable market structure data, not just on-chain token movement.

### Memecoin Manipulation Lane

Purpose:
- detect fast manipulation patterns in chaotic token markets
- especially launch/fresh-wallet/pool/holder anomalies

Memecoin-specific signals:
- fresh wallet bursts
- shared funding
- early holder concentration
- liquidity add/remove behavior
- pool creation timing
- coordinated buys/sells
- CEX deposit hints after run-up
- social/source confirmation only as weak context unless independently verified

Memecoin lane needs speed, but speed cannot bypass source/dedupe/risk gates.

### Solana Lane

Purpose:
- cover Solana memecoin and DEX chaos where activity is fast and noisy

Solana needs a dedicated data model, not just EVM assumptions.

Required concepts:
- token mints
- associated token accounts
- program IDs
- DEX/program attribution
- instruction parsing
- pool/state accounts
- signer/funder graph
- priority fee/MEV-like behavior where observable

Solana should be treated as its own lane with separate parsers and quality gates.

### Binance/Ethereum/BSC/EVM Lane

Purpose:
- continue EVM-first maturation because current data and code are strongest here

Near-term focus:
- BSC exact swap proof
- DEX venue identity repair
- curated DEX trade facts
- wallet/entity graph
- CEX route context
- amount USD and token metadata repair

This is the fastest path to making the current system genuinely useful.

## Client Means And Suitability

Core Equity should adapt to the client, not assume one universal trade style.

Client policy should eventually include:
- available capital
- max capital at risk
- allowed markets: spot, perps, DEX, CEX, Solana, EVM
- allowed chains
- allowed venues
- max trade size
- max daily loss
- max drawdown
- max leverage
- allowed tokens/blocked tokens
- liquidity minimums
- holding time preferences
- automation level: report-only, shadow, paper, assisted, controlled execution

The same opportunity can produce different decisions for different clients.

Example:
- small capital client may be allowed only spot/paper/shadow
- larger sophisticated client may allow perps paper testing
- no client should get real execution without explicit policy and opt-in

## Speed Versus Safety

Core Equity needs to become faster, but not by skipping gates.

Good speed:
- faster bounded collection
- better local queues
- prioritized unknown-router repair
- targeted receipt replay
- faster metadata repair
- parallel read-only analysis
- automatic shadow decisions

Bad speed:
- direct labels from weak evidence
- trades from unverified data
- perps without liquidation/funding/depth data
- Solana assumptions copied from EVM
- memecoin calls without liquidity/slippage/holder checks

## Recommended Build Order

1. Finish EVM DEX data foundation:
   - raw Swap provenance -> decode amounts -> curated DEX trades
   - venue/router identity repair
   - token metadata and amount USD quality

2. Create shadow policy decisions:
   - detect candidate
   - classify route
   - grade source/local evidence
   - decide accept/repair/reject without writing final actions

3. Convert existing adaptive scans into measurable shadow/paper reports:
   - strategy matrix
   - wallet clusters
   - casefiles
   - post-event outcome tracking

4. Add client policy model:
   - capital/risk/market permissions
   - spot/perps/Solana allowlists
   - automation level

5. Add Solana-specific data lane:
   - instruction/parser plan
   - token mint/account model
   - DEX/program attribution
   - memecoin launch/holder/liquidity checks

6. Add perps lane only after market-structure data exists:
   - funding/open interest/depth/liquidation risk
   - strict leverage and suitability gates

## Current Opinion

The strongest near-term path is not to jump directly to perps or Solana execution.

Best next path:
- make EVM/BSC DEX data trustworthy first
- use existing adaptive scans/backtests as shadow intelligence
- add client policy design before any trade agent
- treat Solana and perps as separate future lanes with their own data models

This is slower than hype-agent trading, but much more likely to produce a serious product.

## Disabled Until Separate Goals

Remain disabled:
- real trades
- wallet orders
- client signals
- opt-in creation/mutation
- perps execution
- Solana execution
- CEX labels from weak evidence
- DEX mappings without source-backed route proof
- automatic code/policy mutation

