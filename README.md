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

> **⛔ REFUTED — HISTORICAL ONLY (evidence F-033 / F-034, PRs #91-#95).
> The figures below are DEAD: re-measured on fixed data (post
> fetch_deep_klines fix), the QUBO joint cell yields 20 real liquidations,
> DD 99.2%, final $1 — the entire cascade family (majors −0.058%/event,
> memecoin −0.428%/event) is closed. Kept for the record only; do NOT
> quote them as current results.**

Historical 1-year backtest table (100 USD, maker costs, real funding) —
**REFUTED**: *+3,905%/yr at 24.8% max drawdown, 0 liquidations* (4 streams).
Best QUBO point — **REFUTED**: *+5,082%/yr at 23.3% max drawdown* (20 real
liquidations on fixed data; the owner remembered "6").

**Current truth (2026-10-06, Research OS v14 — causalité verrouillée):**
ALL 7 W41 candidates were **INVALIDATED** — the mutation test proved the
signal looked at the bar it entered on (look-ahead); re-measured on the
causal engine (signal=close(t) → entry=open(t+1)), every one is
DISCOVERY_FAIL. Nothing is currently confirmed. The v14 engine (protocol
windows, MTM hourly wallet, temporal bootstrap, blocking budget,
provenance seals) is the asset — the search restarts from honest grounds.
(Legacy machine notes below are history, not edges.)

> **Honesty (T8, 2026-09-30):** these **absolute** ROI figures are
> **window / DB warm-up artefacts**. The same engine on three warm-up states
> yields +651% → +3,905%; the 10x cascade is liquidated in 6 of 7 deep
> regimes. **Relatives** (stream ranking, gate structure) hold. Paper
> forward is the only judge — see `docs/21-goal-performances.md` and
> `docs/20-registre-indicateurs.md` § 30/09.

Every indicator, verdict and date lives in `docs/20-registre-indicateurs.md`
— the living registry.

**Research pivot (2026-09-30):** Aster/FOMO *research* is frozen in favor of
the **OpenMarket x501** program (`docs/25`–`docs/33`). Collectors keep
running; no new research effort on those axes.

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
| `scripts/` | live tools (Aster data, X harvesting, fomo mining, backtests, paper forward) |
| `scripts/archive/` | retired one-offs (kept for the record) |
| `docs/00-CARTE.md` | **the living map** — everything, one page (FR) |
| `docs/19-liquidations-aster.md` | Aster liquidation mechanics study |
| `docs/25`–`docs/33` | OpenMarket x501 (mission, data, kScript powers, A/B, maker fill, local benches) |
| `backend/` | FastAPI backend (onchain services, legacy research artifacts) |
| `data/` | warehouses (git-ignored): klines.db, fomo.db, x_posts.db, depth.db |

## Rules

- **No autonomous orders.** Execution is human-only, on Aster, always.
- API credentials live in `.env` (git-ignored), testnet for now.
- Main is protected: changes land through PRs only.

---
*Private research repository. Nothing here is financial advice.*
