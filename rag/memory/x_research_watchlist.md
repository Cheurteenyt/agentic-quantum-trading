# Core Equity X Research Watchlist

Last updated: 2026-05-22.

Purpose:
- Use the dedicated Brave/X research profile for bounded read-only discovery.
- Treat X posts as research leads only, never as final evidence.
- Convert useful leads into local source-backed checks: chain data, explorer links, RPC/SQD logs, wallet/entity graph, repeatability, backtest.

## Current Operating Rules

- Read-only by default.
- No posting, liking, following, DMs or engagement automation.
- No aggressive scraping or 24/7 timeline crawling.
- No client signal, trade, mapping or label from X alone.
- X can suggest hypotheses; Core Equity must verify on-chain.

## Useful Source Accounts / Surfaces

- Bubblemaps: wallet clusters, insider/supply concentration narratives, exploit fund routing.
- Lookonchain: whale deposits/withdrawals, Binance/Hyperliquid/Arkham-linked addresses.
- Arkham: entity pages and public entity/wallet references.
- PeckShieldAlert / Blockaid / ZachXBT-style incident posts: exploit addresses and fund flow starting points.
- OnchainLens / EyeOnChain / Eye: whale wallet movements and fresh-wallet CEX flows.
- Scam-hunter style accounts: useful for vocabulary and raw candidates, but noisy and not proof.

## Patterns Observed Today

- Memecoin scam/rug reports repeatedly use the same primitives:
  - bundled launch or sniper bundles
  - deployer/team/insider supply control
  - supply split across many wallets
  - top-holder concentration
  - fresh/disposable deployer wallets
  - early wallets dumping into liquidity
- CEX/whale-flow reports repeatedly use:
  - fresh wallet withdraws from Binance/Bitget
  - old wallet deposits into Binance
  - a new wallet funded shortly after a CEX deposit/withdrawal
  - large movement into Hyperliquid or other trading venues
- Exploit reports repeatedly use:
  - attacker EOA
  - split across multiple addresses
  - routed through CEXs/services
  - explorer links and transaction hashes

## Product Translation

These patterns support a future Core Equity research lane:
- X lead intake read-only.
- Extract token/address/chain/source URL from a post.
- Classify lead type: memecoin supply-control, CEX flow, exploit flow, whale accumulation, DEX manipulation.
- Verify independently with local chain data:
  - token holder distribution
  - deployer/funder edges
  - pool creation proof
  - Swap/Transfer event context
  - CEX deposit/funding hints
  - repeatability across windows
- Only after independent verification can a lead become evidence-only data.

## Immediate Useful Leads

- Search phrase: `Bubblemaps insider wallet cluster token supply`
  - Useful because it surfaces cluster/supply-control language and current wallet-cluster reports.
- Search phrase: `Arkham entity wallet Binance deposit address`
  - Useful because it surfaces wallet/entity/deposit examples and Arkham links.
- Search phrase: `lookonchain whale deposit Binance wallet`
  - Useful because it surfaces fresh-wallet CEX withdrawal/deposit examples.
- Search phrase: `bundled launch supply control memecoin onchain checked`
  - Useful because it surfaces memecoin scam primitives, especially Solana pump-style tokens.

## Current Verdict

X is useful for discovery and vocabulary, not for final proof.
The best next product move is not to scrape X broadly. It is to build a small read-only X lead intake contract that accepts:
- source URL
- author/source label
- token symbol / contract / chain if present
- claimed pattern
- extracted wallet addresses / tx hashes if present
- confidence as research-only

Then Core Equity should verify the lead against chain data before any DB evidence persistence.
