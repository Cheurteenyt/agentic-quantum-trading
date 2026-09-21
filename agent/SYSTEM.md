# Hermes Trading Control Center — System Reference

## Vision

Hermes est un centre de controle trading temps reel qui agrège données on-chain, CEX, et web intelligence en un seul dashboard. L'agent detecte des anomalies, croise les signaux, et assiste la prise de decision.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    HERMES DATA ENGINE                         │
├──────────────────┬───────────────────┬───────────────────────┤
│   HYPERLIQUID    │    MULTI-EXCHANGE  │  FIRECRAWL WEB-AGENT  │
│   (WS direct)    │    (REST APIs)     │  (Cloud /v1/agent)   │
│                  │                   │                       │
│ • L2 Orderbook   │ • Funding rates   │ • Recherche active    │
│ • Trades stream   │ • Open Interest   │ • Navigation multi-pg │
│ • Open Interest   │ • Liquidations    │ • Extraction ciblée   │
│ • CVD / Delta     │ • Top gainers 24h │ • Cross-site reasoning│
│ • Footprint bars  │ • Long/Short ratio│ • Schema extraction   │
│ • OB Heatmap      │                   │                       │
│ • Imbalance       │                   │                       │
└────────┬─────────┴────────┬──────────┴───────────┬──────────┘
         │                  │                      │
         └──────────┬───────┴──────────────────────┘
                    │
            ┌───────▼───────────┐
            │  INTEL AGGREGATOR │ ← Rate-limiting, dedup, cooldown
            │  (Signal Router)  │
            └───────┬───────────┘
                    │
         ┌──────────┼──────────┐
         │          │          │
    ┌────▼───┐ ┌────▼────┐ ┌───▼──────┐
    │ Smart  │ │ Signal  │ │ Entity   │
    │ Engine │ │ Fusion  │ │ Search   │
    └────┬───┘ └────┬────┘ └───┬──────┘
         │          │          │
    ┌────▼──────────▼──────────▼──────┐
    │        FASTAPI BACKEND          │
    │   WS Broadcast (5s cycle)       │
    │   REST Endpoints                │
    │   Entity Search + Detail        │
    └────────────┬───────────────────┘
                 │
          ┌──────▼──────┐
          │  FRONTEND   │
          │  React/Vite  │
          │  ARK-style   │
          └─────────────┘
```

---

## Project Structure

```
/mnt/d/trading-agent/
├── agent/                          # Agent config + system docs
│   ├── client.py                   # LLM client (Zhipu/GLM)
│   ├── risk_guard.py               # Risk management
│   ├── state_manager.py            # Session state
│   └── SYSTEM.md                   # This file
│
├── backend/                        # FastAPI Backend
│   ├── main.py                     # App + lifespan services
│   ├── routers/
│   │   ├── market.py              # Market endpoints
│   │   ├── news.py                # News & sentiment
│   │   ├── vision.py              # Vision analysis
│   │   ├── chat.py                # Chat agent
│   │   ├── agents.py              # Multi-agent orchestration
│   │   ├── desktop.py             # Desktop control (screenshot, MCP)
│   │   └── intel.py               # Web-agent investigations
│   │
│   └── services/
│       ├── collector.py           # Hyperliquid WS (BTC + ETH)
│       ├── footprint.py           # Order flow: footprint, heatmap, imbalance
│       ├── smart_engine.py        # Anomaly detection
│       ├── multi_exchange.py      # Binance/Bybit aggregation (60s cycle)
│       ├── web_agent.py           # Firecrawl web-agent
│       ├── intel_aggregator.py    # Signal routing + rate-limiting
│       └── websocket_manager.py   # WS broadcast hub
│
├── frontend/                       # React Dashboard (Vite)
│   ├── src/
│   │   ├── App.tsx                # Root layout + entity detail state
│   │   ├── contexts/
│   │   │   └── WSContext.tsx      # WebSocket provider + signal dedup
│   │   ├── hooks/
│   │   │   ├── useMarketData.ts   # Market data filtering
│   │   │   ├── useIntelFeed.ts    # Firecrawl investigation stream
│   │   │   ├── useSignals.ts      # Signal fetch + filter
│   │   │   └── useTerminal.ts     # Log buffer + execution
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── TopBar.tsx     # Search bar + live tickers
│   │   │   │   ├── TickerStrip.tsx# Scrolling entity cards
│   │   │   │   ├── Sidebar.tsx   # Navigation
│   │   │   │   └── EntityDetail.tsx # Slide-in entity panel
│   │   │   ├── Card.tsx, StatBox.tsx, SignalCard.tsx
│   │   │   ├── DataTable.tsx, Btn.tsx, Ticker.tsx
│   │   │   └── LiveStatus.tsx
│   │   └── pages/
│   │       ├── Dashboard.tsx      # Markets overview
│   │       ├── Agents.tsx         # Intel & investigations
│   │       ├── Vision.tsx         # Screenshot analysis
│   │       ├── Desktop.tsx        # Desktop control
│   │       ├── Chat.tsx           # Hermes chat
│   │       └── Terminal.tsx       # System terminal
│   └── index.css                  # Full design system (ARK Intelligence)
│
├── data/                           # Runtime data
│   ├── snapshots/                 # Latest market states (JSON)
│   ├── signals/                   # Generated trading signals
│   ├── investigations/            # Web-agent investigation logs
│   ├── logs/                      # Application logs
│   └── screenshots/               # Desktop captures
│
├── .env                            # API keys
└── start_all.sh                   # Startup script
```

---

## Core Services

### 1. Hyperliquid Real-Time Collector

**Source**: WebSocket `wss://api.hyperliquid.xyz/ws`

**Coins**: BTC, ETH (configurable via `COLLECTOR_COINS` in `main.py`)

**Subscriptions per coin**:
- `trades` — price, size, side streaming
- `l2Book` — L2 orderbook updates
- `activeAssetCtx` — OI updates

**Derived metrics** (computed locally):
- CVD (Cumulative Volume Delta)
- Footprint bars — volume per price level
- Orderbook heatmap — liquidity over time
- Imbalance ratio — bid/ask depth skew
- Smart Engine triggers — whale entry, cascade detection

**Endpoints**:
```
GET /api/services/collector/{coin}     # Live snapshot
GET /api/market/footprint/{coin}       # Footprint bars
GET /api/market/heatmap/{coin}         # OB heatmap
GET /api/market/imbalance/{coin}       # Liquidity imbalance
```

---

### 2. Multi-Exchange Aggregator

**Sources** (public APIs, no auth):
- Binance Futures `/fapi/v1/*` — funding, OI, liquidations, top gainers
- Bybit V5 `/v5/market/*` — funding, tickers, OI

**Cycle**: 60 seconds

**Data merged into WS broadcast**:
- `payload.funding` — BTCUSDT/ETHUSDT/SOLUSDT rates (binance + bybit)
- `payload.oi` — Open Interest per symbol
- `payload.top_gainers` — Top 5 24h gainers

**Endpoints**:
```
GET /api/market/multi-exchange         # Aggregator status
GET /api/market/funding/{symbol}       # Per-symbol funding detail
```

---

### 3. XAU/USD Price Feed

**Primary**: MT5 Bridge at `http://host.docker.internal:8765` (Windows)
**Fallback**: Binance XAUUSDT (spot → futures) when MT5 offline

The broadcast loop checks MT5 first. If unreachable, falls back to Binance price with a typical spread added. Refresh every 15s.

---

### 4. Entity Search System

**Searchable entities** (rebuilt every 60s):
- Hyperliquid tokens (BTC, ETH) with live snapshots
- XAU/USD with Binance price
- Static entities: Binance, Coinbase, Bitfinex, Grayscale, Mt. Gox, FTX, PUPrime
- Funding rate entities (BTCUSDT, ETHUSDT, SOLUSDT)
- Top gainer entities (Binance 24h movers)

**Search scoring**: exact name (100) > prefix (80) > label contains (60) > name contains (50) > id contains (30)

**Endpoints**:
```
GET /api/search?q=...&limit=10        # Search entities
GET /api/entity/{entity_id}           # Entity detail (enriched)
```

**Frontend integration**:
- TopBar search bar — debounced fetch, dropdown with type badges (TKN/ORG/FR/TOP)
- Keyboard: `/` focus, ↑↓ navigate, Enter select, Escape close
- TickerStrip chips clickable — open EntityDetail panel
- EntityDetail — slide-in panel from right, accent color by type

---

### 5. Firecrawl Web-Agent

**API**: `https://api.firecrawl.dev/v1/agent` (Cloud)

**Auto-scan**: Binance announcement page every 30s

**Specialized agents**:

| Agent | Role | Trigger |
|-------|------|---------|
| BinanceHunter | New listing detection | Auto-scan 30s |
| ChainDetective | Whale wallet profiling | Manual / signal trigger |
| SentimentScanner | Multi-source sentiment | Manual / funding spike |

**Intel endpoints**:
```
POST /api/intel/investigate              # Custom investigation
POST /api/intel/hunt/listings            # Active listing hunt
POST /api/intel/detective/whale          # Whale investigation
POST /api/intel/sentiment/scan           # Sentiment scan
POST /api/intel/sentiment/funding-spike  # Funding spike analysis
GET  /api/intel/investigations/{id}      # Investigation status
GET  /api/intel/investigations/active    # Active investigations
GET  /api/intel/signals/recent           # Recent signals
```

---

### 6. Smart Engine (Anomaly Detection)

**Real-time detections** (fed from collector trades + orderbook):

| Signal | Condition | Priority |
|--------|-----------|----------|
| WHALE_ENTRY | Trade > 3σ average volume | HIGH |
| LIQUIDATION_CASCADE | >5 consecutive liqs same direction | CRITICAL |
| FUNDING_DIVERGENCE | Funding diverges between exchanges | MEDIUM |
| ORDERFLOW_IMBALANCE | Sudden bid/ask depth skew | HIGH |

**Endpoints**:
```
GET /api/market/signals              # Detected signals
GET /api/market/smart-stats/{coin}   # Per-coin smart stats
```

---

### 7. WebSocket Broadcast Hub

**Service**: `backend/services/websocket_manager.py`

**Broadcast cycle**: 5 seconds

**Message format**:
```json
{
  "type": "market_update",
  "ts": 1712345678,
  "hyperliquid": { "BTC": {...}, "ETH": {...} },
  "xauusd": { "bid": "3245.50", "ask": "3245.80", "source": "binance_fallback" },
  "funding": { "BTCUSDT": { "binance": 0.0001, "bybit": 0.00012 } },
  "oi": { "BTCUSDT": {...} },
  "top_gainers": [...],
  "recent_signals": [...]
}
```

**Frontend WSContext** handles:
- Auto-reconnect with exponential backoff (1s → 15s max)
- Signal dedup: 30s cooldown per type:title signature
- Priority upgrade on duplicate (LOW → CRITICAL escalation)
- Max 20 recent signals in state

---

## Frontend Design System

**Theme**: ARK Intelligence — black minimalist, electric blue accents

**Design tokens** (in `:root`):
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-app` | #050505 | Page background |
| `--bg-surface` | #0c0c0c | Cards, panels |
| `--bg-elevated` | #141414 | Inputs, dropdowns |
| `--brand-blue` | #4488ff | Primary accent |
| `--success` | #00ff88 | Positive / bullish |
| `--error` | #ff4444 | Negative / bearish |
| `--warning` | #ffaa00 | Funding, alerts |
| `--font-mono` | JetBrains Mono | Numbers, prices |

**Fonts**: Inter (body) + JetBrains Mono (data)

**Layout**: Sidebar 64px (200px hover) → TopBar 52px → TickerStrip 48px → Page content → StatusBar

**Key interactions**:
- `/` shortcut focuses search bar
- Click any ticker chip → opens EntityDetail slide-in panel
- Search dropdown: ↑↓ navigate, Enter select, Escape close
- TickerStrip animation pauses on hover

---

## Signal Fusion Logic

Cross-validation between data sources:

| Source A Detection | Source B Trigger | Expected Result |
|--------------------|------------------|-----------------|
| Whale $50M → exchange | BinanceHunter scan | Listing imminent? |
| Funding spike >1% | SentimentScanner | Organic or manipulation? |
| New token deployed | ChainDetective | Contract red flags? |
| Binance listing found | ChainDetective | Insider activity before listing? |

**Current state**: BinanceHunter auto-scan active (30s). Other cross-triggers manual via `/api/intel/*`. Automation of trigger chains is Phase 3.

---

## Setup & Configuration

### Environment Variables (`.env`)

```bash
# AI Model
ZHIPU_GLM_API_KEY=***
ZHIPU_API_URL=https://api.z.ai/api/paas/v4/chat/completions

# Firecrawl Web-Agent
FIRECRAWL_API_KEY=***
FIRECRAWL_API_URL=https://api.firecrawl.dev/v1

# MCP Configuration
MCP_PLAYWRIGHT_PORT=9222
MCP_PLAYWRIGHT_BROWSER=chromium
MCP_PLAYWRIGHT_HEADLESS=false

# Trading Risk
MAX_POSITION_SIZE=0.02
MAX_DAILY_LOSS=0.05
MAX_OPEN_POSITIONS=3
KILL_SWITCH_ENABLED=true
```

### Startup (WSL on D:)

```bash
cd /mnt/d/trading-agent
source .venv/bin/activate
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Services started automatically** (via `lifespan`):
1. Hyperliquid collector — BTC + ETH (WebSocket permanent)
2. Multi-exchange aggregator — 60s cycle
3. Firecrawl auto-scan — 30s interval
4. Intel aggregator — signal routing + rate-limiting
5. XAU/USD fallback — 15s refresh
6. Market broadcast — 5s WS push
7. Entity search DB — 60s rebuild

**Console output**:
```
[WEB-AGENT] Firecrawl agent initialized
[INTEL] Auto-scan loop started (30s interval)
[AGGR] Fetching data cycle at 20:15:30
Collector starting for: BTC, ETH
Connected to Hyperliquid WebSocket
```

---

## Risk Management

### Kill Switch Conditions

System blocks all new positions if:

1. Daily loss limit reached (`MAX_DAILY_LOSS = 0.05` → -5%)
2. Position limit reached (`MAX_OPEN_POSITIONS = 3`)
3. Position size exceeds limit (`MAX_POSITION_SIZE = 0.02` → 2%)
4. Manual trigger (user command)

### Execution Flow

```
Signal detected (web-agent + fusion)
  → Intel Aggregator (rate-limit, dedup, cooldown)
  → Smart Engine (anomaly scoring)
  → Risk Guard (size, daily PnL, open positions)
  → Hermes Agent decision (LLM analysis + confidence)
  → Approved → Execute via MT5 Bridge
  → Rejected → Log blocked + reason
```

---

## Roadmap

### Phase 1: Core Infrastructure ✅
- [x] Hyperliquid collector (BTC + ETH)
- [x] Multi-exchange aggregator (Binance, Bybit)
- [x] Firecrawl web-agent integrated
- [x] Specialized agents (BinanceHunter, ChainDetective, SentimentScanner)
- [x] WebSocket broadcast hub
- [x] Auto-scan loop (30s)
- [x] Smart Engine anomaly detection

### Phase 2: Frontend Intelligence ✅
- [x] React dashboard built (Vite + ARK theme)
- [x] Search bar functional (entity lookup with `/` shortcut)
- [x] TickerStrip with clickable entities
- [x] EntityDetail slide-in panel
- [x] Live ticker feed (BTC, ETH, XAU)
- [x] WSContext with auto-reconnect + signal dedup
- [x] Intel page for investigations
- [x] Signal feed with priority color coding

### Phase 3: Automation ⏳
- [ ] Blockchain monitor (EVM mempool via Alchemy/W3S WS)
- [ ] Automatic trigger chains (source A detection → source B investigation)
- [ ] Signal fusion scoring (weighted cross-source confidence)
- [ ] Confidence-based auto-trade (trust > 0.9 → execute without human)

### Phase 4: MT5 CFD 💼 Separate
- [ ] Activate `mt5_bridge.py` in CFD-only mode
- [ ] Configure PUPrime XAUUSD.p (account 700073915)
- [ ] Integrate MLFT strategy indicators
- [ ] Paper trading before live

---

## API Quick Reference

### Market Data
```bash
GET  /api/services/collector/{coin}     # Live Hyperliquid snapshot
GET  /api/market/footprint/{coin}       # Footprint bars
GET  /api/market/heatmap/{coin}         # OB heatmap
GET  /api/market/imbalance/{coin}       # Liquidity imbalance
GET  /api/market/multi-exchange         # Aggregator status
GET  /api/market/funding/{symbol}       # Per-symbol funding
GET  /api/market/signals                # Smart Engine signals
GET  /api/market/smart-stats/{coin}     # Per-coin smart stats
```

### Entity Search
```bash
GET  /api/search?q=BTC&limit=10         # Search entities
GET  /api/entity/hl_BTC                 # Entity detail
```

### Intel
```bash
POST /api/intel/investigate              # Custom investigation
POST /api/intel/hunt/listings            # Hunt Binance listings
POST /api/intel/detective/whale          # Whale investigation
POST /api/intel/sentiment/scan           # Sentiment scan
POST /api/intel/sentiment/funding-spike  # Funding spike analysis
GET  /api/intel/investigations/active    # Active investigations
GET  /api/intel/signals/recent           # Recent signals
```

### Services
```bash
GET  /api/services/status               # All services health
GET  /health                             # Basic health check
```

### WebSocket
```bash
ws://localhost:8000/ws                   # Real-time data stream
```

---

## Development Notes

### DO
- Use `data/` directory for all runtime data (snapshots, signals, investigations)
- Broadcast signals via `ws_manager.broadcast()`
- Schema validation for web-agent outputs
- Respect rate limits (2s min between Firecrawl requests)
- Centralize all CSS in `index.css` — no inline styles in React components
- Use design tokens (`var(--brand-blue)`, etc.) not hardcoded colors

### DON'T
- Hardcode `~/.hermes` paths (profile-aware functions if needed)
- Ignore timeouts on long-running investigations
- Send unstructured payloads to frontend
- Forget cleanup of old investigation files (garbage collection)
- Neglect error handling on Firecrawl API calls
- Add inline CSS in React components — breaks override hierarchy
- Use emojis in production code — Unicode symbols only

---

*Version 3.0 — Updated with entity search, ETH collector, XAU fallback, ARK frontend*
