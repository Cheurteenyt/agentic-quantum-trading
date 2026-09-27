# Agentic & Quantum Trading

A research-grade trading system for **Aster DEX perpetuals**, built around one
principle: **every signal is backtested against reality before it is believed.**

The machine combines three proprietary data layers that nobody else
systematizes:

1. **Aster on-chain mechanics** — order-book depth, liquidation streams,
   funding history (variable intervals per symbol), open-interest snapshots
   (self-built — Aster has no OI history endpoint), real per-symbol
   liquidation parameters extracted from exchangeInfo.
2. **X.com social layer** — a 45+ account watchlist, cashtag rotation over the
   full memecoin universe, call registry with forward verdicts, quote/reply
   harvesting, account reach measurement, a private API wallet list mined
   twice a day.
3. **fomo.family whale layer** — positions of ~40 tracked whales (weighted by
   realized skill), token flow panels, graduation discovery, clans, theses,
   age-of-coin lifecycle effects.

## The Machine (current state)

The validated core: an **accelerated-cascade short** on majors (3
consecutive accelerating down-candles → short 24h), conditioned by a
proprietary **anti-liquidation score** (rolling-rank composite of 6
features), executed **maker-only at 10x** — where the leverage rule
`lev ≤ 100/(maxMAE + 0.5)` guarantees **zero liquidations by
construction** (observed max MAE 7.84% vs a 9.5% death line).

Official 1-year backtest (100 USD, maker costs, real funding):
**+3,905%/yr at 24.8% max drawdown, 0 liquidations** (4 streams: majors
cascade, memecoin cascade, long-only survivor, vol_spike_6h). Two QUBO
candidates run in parallel paper-forward on the same live trades — the
best point of the project: **+5,082%/yr at 23.3% max drawdown, best month
+83.7%** (QUBO joint weights×leverage, MAE margin under permanent watch).
Every indicator, verdict and date lives in
`docs/20-registre-indicateurs.md` — the living registry.

## Discipline (the part that matters)

- **9+ large null results** recorded and archived: classic indicators,
  absorption/sweep patterns, extreme funding, the X crowd at +24h, x20
  directional scalping, funding-settlement drift. Every false door is closed
  with numbers, not opinions.
- **Pre-registered rules**: N ≥ 10, winrate ≥ 55 %, temporal 70/30 train/val
  split, multiplicity audit, **blind-baseline anti-drift** (a blind short on
  memecoins wins 71 % at +90 days — no signal is judged without it).
- **Realism stack in the harness**: selftest on synthetic data at every run,
  measured slippage from our own order-book snapshots, real funding applied
  over wall-clock holding time, real liquidation thresholds per symbol
  (100/L − maintMarginPercent, leverage capped per symbol), worst-trade and
  median next to every mean.
- **Forward paper ledger**: candidates are judged on fresh data every night.
  Weeks of accumulation decide — never a single backtest.

## Layout

| Path | What lives there |
|---|---|
| `scripts/` | 135 live tools (Aster data, X harvesting, fomo mining, backtests, paper forward) |
| `scripts/archive/` | retired one-offs (kept for the record) |
| `docs/00-CARTE.md` | **the living map** — everything, one page (FR) |
| `docs/19-liquidations-aster.md` | Aster liquidation mechanics study |
| `backend/` | FastAPI backend (onchain services, legacy research artifacts) |
| `data/` | warehouses (git-ignored): klines.db, fomo.db, x_posts.db, depth.db |

## Rules

- **No autonomous orders.** Execution is human-only, on Aster, always.
- API credentials live in `.env` (git-ignored), testnet for now.
- Main is protected: changes land through PRs only.

---
*Private research repository. Nothing here is financial advice.*
