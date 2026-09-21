# strategies_v2 — viable crypto strategies (post-Aster)

New modules, paper-only, read-only on market data. They do NOT modify any
existing runner. See `docs/strategy-roadmap-2026-08.md` and
`docs/aster-status-2026-08.md`.

## Why this folder exists
The legacy Aster suite (parent dir) was long-only stateful and got cooked in an
extreme-volatility 2025-26 regime. These strategies are built to survive that:

- **Directional** (long AND short).
- **Regime-aware** via `regime_filter` (ATR vs median, gap-risk skip).
- **Strict benchmark from day one**: `backtest_strict` splits train/validation
  OUT-OF-SAMPLE and models real costs on NOTIONAL (fees + funding + slippage).

## Modules
- `regime_filter.py` — ATR/vol regime, leverage cap, size multiplier.
- `vol_breakout.py` — Piste 1: directional volatility breakout (ema ± k*ATR),
  funding guard against crowded books.
- `funding_mean_reversion.py` — Piste 2: fade crowded perp funding + trend guard.
- `backtest_strict.py` — the benchmark engine (train/val OOS, real costs).

## Usage (caller supplies OHLCV + funding arrays)
```python
from services.onchain.aster.strategies_v2 import vol_breakout, backtest_strict

res = backtest_strict.run_backtest(
    symbol="BTCUSDT", interval="1h",
    opens=..., highs=..., lows=..., closes=...,
    funding_rates=...,
    cfg=vol_breakout.VolBreakoutConfig(),
)
print(res.oos_status, res.train_pnl_usd, res.val_pnl_usd)
```

## Before promotion
Reuse the legacy microstructure / mark-index / ws-quality validators on any lane
that passes OOS. No real order, no wallet, no client signal — ever.
