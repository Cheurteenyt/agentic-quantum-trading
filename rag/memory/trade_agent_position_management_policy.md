# Trade Agent Position Management Policy - Read-Only Design

## Management Map Pointer

- Compact agent/control source of truth: `rag/memory/core_equity_management_map.md`.
- This file describes future trade-position behavior. The management map keeps the Trade Agent blocked until data, policy, shadow/paper results, opt-in, and risk gates are ready.

## Purpose

The future Trade Agent should manage positions intelligently according to:
- client capital
- client risk profile
- market type
- liquidity
- volatility
- opportunity quality
- execution venue
- current automation mode

The goal is to capture asymmetric opportunities when they exist, while protecting capital when the thesis is wrong.

Large outcomes such as `x50` or `x100` are possible market scenarios, especially in memecoin/high-volatility crypto, but they must never be represented as a guarantee or normal expectation.

## Core Principle

The Trade Agent is not allowed to be "confident and aggressive" by default.

It must be:
- opportunistic when asymmetry exists
- conservative with loss size
- fast to invalidate bad theses
- patient with rare winners
- unable to bypass the Policy/Risk Engine

The product should seek high upside through asymmetric sizing and disciplined exits, not through uncontrolled leverage.

## Trade Agent Brains

### Opportunity Brain

Role:
- identify candidate opportunities from Data Engine and Intelligence Engine packets
- classify setup type: spot, perps, memecoin, DEX, CEX, Solana, EVM
- describe the thesis and invalidation

It does not size or execute.

### Position Sizing Brain

Role:
- translate client capital and risk policy into position size
- reduce size when liquidity, volatility, slippage, confidence, or venue quality are weak
- scale exposure only when policy allows

It must size by risk-to-loss, not by desired ROI.

### Risk Governor

Role:
- final gate before any position can exist
- enforce max loss, drawdown, leverage, exposure, liquidity, slippage, correlation, venue, and client constraints
- stop the agent when risk limits are breached

The Risk Governor can always block the Trade Agent.

### Execution Manager

Role:
- manage entry, exit, stop, partial take profit, trailing, re-entry, cooldown, and position closure
- only active in paper or real mode when policy allows

It must be deterministic enough to audit.

## Client Capital Profiles

Core Equity must adapt to the user's means.

Example profiles:

### Micro Capital

Purpose:
- high asymmetry exploration
- very small absolute loss per attempt

Allowed style:
- mostly spot or paper/shadow
- tiny position sizes
- memecoin/high-vol allowed only after liquidity and holder checks

Blocked:
- meaningful leverage
- illiquid position size
- averaging down without explicit rule

### Small Capital

Purpose:
- controlled asymmetric growth

Allowed style:
- spot-first
- small basket of attempts
- strict max daily loss
- rare pyramiding only after trade is in profit

Blocked:
- high leverage
- position concentration beyond policy

### Medium Capital

Purpose:
- balance upside with preservation

Allowed style:
- spot and possibly paper-tested perps
- stronger liquidity requirements
- lower per-trade risk percent

Blocked:
- memecoin size that cannot exit cleanly
- perps without depth/funding/liquidation model

### Large Capital

Purpose:
- capital preservation and scalable edge

Allowed style:
- high-liquidity spot
- staged entries/exits
- strict slippage/depth gates
- perps only after advanced venue-risk model

Blocked:
- thin memecoin exposure except tiny exploratory bucket
- high leverage by default

## Position Sizing Rules

Sizing should be based on maximum acceptable loss.

Required inputs:
- account equity
- max risk per trade
- max daily loss
- max drawdown
- confidence tier
- liquidity tier
- volatility tier
- slippage estimate
- stop/invalidation distance
- venue risk

Example logic:
- base risk percent is chosen by client profile
- reduce risk if data quality is weak
- reduce risk if liquidity is weak
- reduce risk if volatility is extreme
- reduce risk if route/venue/source confidence is incomplete
- block if stop distance makes position too large or too fragile

The agent must never size a position from desired profit target alone.

## Spot Mode

Spot is the first realistic execution lane.

Required gates:
- asset allowed by client policy
- route/venue identity acceptable
- liquidity above threshold
- slippage below threshold
- source/data quality acceptable
- no unresolved manipulation/contract hazard blockers
- shadow/paper record acceptable

Spot high-vol mode can pursue asymmetric upside with limited loss.

## Memecoin High-Vol Mode

Memecoin opportunities can produce extreme multiples, but they are also where false positives, rugs, illiquidity, and execution failure are most dangerous.

Required extra checks:
- liquidity depth
- holder concentration
- LP behavior
- mint/owner/authority risk where chain supports it
- fresh wallet/funder clusters
- buy/sell tax or transfer restrictions where detectable
- route/pool validity
- exit feasibility

Position behavior:
- small initial entry
- fast invalidation
- partial take profits
- leave a runner only after principal/risk is reduced
- no averaging down unless a separate strategy explicitly allows it

`x50` or `x100` is treated as tail upside for the runner, not as the base plan.

## Perps Mode

Perps remain blocked until separate market-structure data exists.

Required extra data:
- funding rates
- open interest
- liquidation clusters
- order book/depth
- volatility
- venue-specific risk
- max leverage policy
- liquidation distance

Perps risk rules:
- leverage cap by client profile
- hard liquidation-distance minimum
- forced stop policy
- max notional exposure
- funding cost check
- no perps for clients not explicitly opted in

Perps must never be enabled only because spot thesis is strong.

## Entry Management

Entry rules should be explicit:
- trigger condition
- confirmation requirement
- max slippage
- liquidity check
- max spread
- max gas/fee
- route safety
- cooldown after failed entry

Entry types:
- probe entry
- confirmation entry
- staged entry
- breakout entry
- pullback entry

The agent should prefer missed trades over bad fills.

## Stop And Invalidation

Every trade plan needs invalidation before entry.

Invalidation examples:
- thesis data drift
- source/route contradiction
- liquidity collapse
- wallet cluster exits
- price breaks defined level
- time stop
- volume dries up
- perps funding/liquidation risk changes

If invalidation triggers, the agent exits or blocks new exposure.

## Partial Take Profits

The agent should protect capital by taking partial profits.

Example structure:
- first partial exits reduce or remove initial risk
- second partial secures profit
- remaining runner captures tail upside

This is how Core Equity can pursue extreme upside without requiring extreme risk.

## Trailing And Runner Logic

Runner logic is for rare asymmetric winners.

Allowed only if:
- original risk has been reduced
- liquidity still supports exit
- thesis is not invalidated
- volatility remains within policy
- client profile allows it

Trailing stop can be based on:
- percentage drawdown
- volatility band
- liquidity/flow deterioration
- wallet cluster selling
- time decay

## Pyramiding

Pyramiding means adding to a winning position.

Allowed only if:
- current position is profitable
- risk after add remains within max loss
- liquidity supports add and exit
- thesis is strengthened by new data
- no averaging-down behavior is hidden as pyramiding

Blocked:
- adding to losers
- adding after source/route/risk drift
- adding if max exposure or correlation limit would be exceeded

## Kill Switches

Required kill switches:
- max daily loss
- max drawdown
- max failed trades in period
- max slippage violation count
- stale data detection
- RPC/provider/data degradation
- venue/routing anomaly
- client policy missing or expired
- emergency global disable

Kill switch must override the Trade Agent.

## Shadow To Paper To Real

### Shadow

Records:
- would-enter
- would-size
- would-stop
- would-take-profit
- would-exit
- outcome after defined windows

No simulated capital movement is required.

### Paper

Adds:
- virtual capital
- simulated position ledger
- simulated PnL
- drawdown
- fees/slippage assumptions
- strategy comparison

### Real

Allowed only after:
- shadow results are measured
- paper results are measured
- client policy and opt-in exist
- execution venue is configured
- risk limits are active
- audit logs and kill switches are active

## ROI Language Policy

Core Equity can model high-upside scenarios.

Allowed language:
- "tail upside scenario"
- "asymmetric opportunity"
- "runner could capture large multiple if thesis continues"
- "paper/shadow result showed X under assumptions"

Blocked language:
- guaranteed x50/x100
- expected x100
- safe high leverage
- profit promise
- client-safe without policy/opt-in/backtest

## Current Project Implication

Before implementing any real Trade Agent:
- finish trustworthy DEX trade facts
- connect adaptive scans/backtests to curated data
- define client policy schema
- define shadow position ledger
- define paper position ledger
- define risk governor

No trade, wallet order, client signal, or opt-in should exist before those layers.
