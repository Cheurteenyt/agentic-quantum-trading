"""
Arkham Intelligence Scraper — Stratégie de Crédits Intelligent
================================================================

OBJECTIF: Extraire les labels d'entités Arkham en préservant les crédits Firecrawl.

RÈGLE D'OR: Firecrawl (500 crédits one-time) est UNE RESSOURCE FINIE.
Chaque crédit dépensé doit apporter une donnée QU'ON NE PEUT PAS obtenir
gratuitement ailleurs.

STRATÉGIE CREDIT-PRESERVING:
──────────────────────────────
  ✅ UTILISE FIRECRAWL POUR:
    - Labels d'entités (name → address mapping, pages Arkham)
    - Adresses de wallets d'échanges (pas d'API gratuite)
    - Labels de funds / portfolios
    - Calendrier de unlocks (si pas d'API)

  ❌ N'UTILISE JAMAIS FIRECRAWL POUR:
    - Historique de transactions → Etherscan / BSCScan (GRATUIT)
    - Balances de tokens → Blockchain API (GRATUIT)
    - Prix → Binance / Hyperliquid (GRATUIT)
    - Funding / OI → Coinglass / Binance (GRATUIT)

CACHE AGRESSIF:
  Chaque donnée scrapée est sauvegardée dans data/arkham/cache.json.
  Avant chaque appel Firecrawl, on vérifie le cache.
  → On ne re-scrape JAMAIS une entité déjà en cache.

IMPORT:
  from services.arkham_scraper import ArkhamScraper

ARCHITECTURE:
  ┌──────────────────┐
  │  ArkhamScraper   │ ← Orchestrateur
  └───┬──────────┬───┘
      │          │
      ▼          ▼
  ┌────────┐  ┌──────────────┐
  │ Cache  │  │  Firecrawl   │  ← DERNIER RECOURS (crédits)
  │ JSON   │  │  API Agent   │
  └────────┘  └──────────────┘
      │
      ▼  (une fois l'adresse connue)
  ┌──────────────────────────────┐
  │  APIs Blockchain GRATUITES   │
  │  Etherscan · BSCScan · etc.  │
  └──────────────────────────────┘
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiohttp

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger("arkham_scraper")


# =========================================================
# CONSTANTS
# =========================================================

FIRECRAWL_API_KEY_ENV="FIRECRAWL_API_KEY"
ETHERSCAN_API_KEY_ENV="ETHERSCAN_API_KEY"
BSCSCAN_API_KEY_ENV="BSCSCAN_API_KEY"
COVALENT_API_KEY_ENV="COVALENT_API_KEY"

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1"
ARKHAM_BASE = "https://platform.arkhamintelligence.com"

DATA_DIR = Path("data/arkham")
CACHE_FILE = DATA_DIR / "cache.json"

FIRECRAWL_MAX_CREDITS = 500

# Rate limiting
MIN_REQUEST_INTERVAL = 3.0  # secondes entre chaque requête Firecrawl

# Etherscan endpoints
ETHERSCAN_API_URLS = {
    'ethereum': 'https://api.etherscan.io/v2/api',
    'bsc':      'https://api.etherscan.io/v2/api',
    'arbitrum': 'https://api.etherscan.io/v2/api',
    'polygon':  'https://api.etherscan.io/v2/api',
    'optimism': 'https://api.etherscan.io/v2/api',
    'avalanche':'https://api.etherscan.io/v2/api',
}

ETHERSCAN_CHAIN_IDS = {
    'ethereum': '1',
    'bsc':      '56',
    'arbitrum': '42161',
    'polygon':  '137',
    'optimism': '10',
    'avalanche':'43114',
}

# NATIVE COINS — blockchains natives (pas de contrat ERC-20)
NATIVE_COINS = {
    "bitcoin":    {"symbol": "BTC", "chain": "bitcoin",    "is_native": True},
    "btc":        {"symbol": "BTC", "chain": "bitcoin",    "is_native": True},
    "solana":     {"symbol": "SOL", "chain": "solana",     "is_native": True},
    "sol":        {"symbol": "SOL", "chain": "solana",     "is_native": True},
    "ethereum":   {"symbol": "ETH", "chain": "ethereum",   "is_native": True},
    "eth":        {"symbol": "ETH", "chain": "ethereum",   "is_native": True},
    "avalanche":  {"symbol": "AVAX", "chain": "avalanche", "is_native": True},
    "avax":       {"symbol": "AVAX", "chain": "avalanche", "is_native": True},
    "matic":      {"symbol": "MATIC", "chain": "polygon",  "is_native": True},
    "polygon":    {"symbol": "MATIC", "chain": "polygon",  "is_native": True},
    "bnb":        {"symbol": "BNB", "chain": "bsc",        "is_native": True},
    "binancecoin":{"symbol": "BNB", "chain": "bsc",        "is_native": True},
    "xrp":        {"symbol": "XRP", "chain": "xrp",        "is_native": True},
    "ripple":     {"symbol": "XRP", "chain": "xrp",        "is_native": True},
    "cardano":    {"symbol": "ADA", "chain": "cardano",    "is_native": True},
    "ada":        {"symbol": "ADA", "chain": "cardano",    "is_native": True},
    "dogecoin":   {"symbol": "DOGE", "chain": "dogecoin",  "is_native": True},
    "doge":       {"symbol": "DOGE", "chain": "dogecoin",  "is_native": True},
    "toncoin":    {"symbol": "TON", "chain": "ton",        "is_native": True},
    "ton":        {"symbol": "TON", "chain": "ton",        "is_native": True},
    "near":       {"symbol": "NEAR", "chain": "near",      "is_native": True},
    "near-protocol": {"symbol": "NEAR", "chain": "near",   "is_native": True},
    "sui":        {"symbol": "SUI", "chain": "sui",        "is_native": True},
    "aptos":      {"symbol": "APT", "chain": "aptos",      "is_native": True},
    "apt":        {"symbol": "APT", "chain": "aptos",      "is_native": True},
    "injective":  {"symbol": "INJ", "chain": "injective",  "is_native": True},
    "inj":        {"symbol": "INJ", "chain": "injective",  "is_native": True},
    "celestia":   {"symbol": "TIA", "chain": "celestia",   "is_native": True},
    "tia":        {"symbol": "TIA", "chain": "celestia",   "is_native": True},
    "sei":        {"symbol": "SEI", "chain": "sei",        "is_native": True},
    "xau":        {"symbol": "XAU", "chain": "commodity",  "is_native": True},
    "gold":       {"symbol": "XAU", "chain": "commodity",  "is_native": True},
}

# KNOWN ERC-20 CONTRACT ADDRESSES (hardcoded, gratuit, pas d'API)
KNOWN_CONTRACTS: dict[str, dict[str, str]] = {
    "usdt": {
        "ethereum": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "bsc": "0x55d398326f99059ff775485246999027b3197955",
        "arbitrum": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
        "polygon": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
        "optimism": "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58",
    },
    "usdc": {
        "ethereum": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "bsc": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd180d",
        "arbitrum": "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8",
        "polygon": "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
        "optimism": "0x7f5c764cbc14f9669b889fd633d6f76c3862c568",
        "base": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
    },
    "link": {
        "ethereum": "0x514910771af9ca656af840dff83e8264ecf986ca",
        "bsc": "0xf8a0bf9cf54bb92f17374d9e9a321e6a111a51bd",
        "arbitrum": "0xf97f4df75117a78c1a5a0dbb814af92458539fb4",
    },
    "uni": {
        "ethereum": "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
        "arbitrum": "0xfa7f8980b0f1e64a2062791cc3b0871572f1f7f0",
    },
    "dai": {
        "ethereum": "0x6b175474e89094c44da98b954eedeac495271d0f",
        "bsc": "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3",
        "arbitrum": "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1",
        "polygon": "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063",
    },
    "aave": {
        "ethereum": "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
        "arbitrum": "0xba5ddd1f9d7f570dc94a51479a000e3bce967196",
    },
    "mkr": {
        "ethereum": "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2",
    },
    "shib": {
        "ethereum": "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce",
    },
    "pepe": {
        "ethereum": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
    },
    "wbtc": {
        "ethereum": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599",
        "arbitrum": "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f",
    },
    "weth": {
        "ethereum": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
        "arbitrum": "0x82af49447d8a07e3bd95bd0d56f35241523fbab1",
        "optimism": "0x4200000000000000000000000000000000000006",
        "base": "0x4200000000000000000000000000000000000006",
    },
}

# Mapping CoinGecko ID → Symbole pour les perps Hyperliquid
CG_TO_HYPERLIQUID = {
    "bitcoin": "BTC",
    "solana": "SOL",
    "ethereum": "ETH",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "toncoin": "TON",
    "near-protocol": "NEAR",
    "sui": "SUI",
    "aptos": "APT",
    "injective-protocol": "INJ",
    "celestia": "TIA",
    "sei-network": "SEI",
    "avalanche-2": "AVAX",
}

# Mapping Symbole → CoinGecko ID pour les ERC-20 courants
SYMBOL_TO_CG_ID = {
    "usdt": "tether",
    "usdc": "usd-coin",
    "dai": "dai",
    "busd": "binance-usd",
    "link": "chainlink",
    "uni": "uniswap",
    "wbtc": "wrapped-bitcoin",
    "weth": "weth",
    "aave": "aave",
    "mkr": "maker",
    "shib": "shiba-inu",
    "pepe": "pepe",
}

STATIC_ENTITY_CATALOG = [
    {"name": "Binance", "slug": "binance", "type": "exchange", "category": "cex", "chains": ["bitcoin", "ethereum", "bsc", "arbitrum", "polygon"], "aliases": ["binance exchange", "binance wallet", "binance hot wallet"], "tags": ["exchange", "cex"]},
    {"name": "Coinbase", "slug": "coinbase", "type": "exchange", "category": "cex", "chains": ["bitcoin", "ethereum", "arbitrum", "polygon", "optimism"], "aliases": ["coinbase exchange", "coinbase wallet"], "tags": ["exchange", "cex"]},
    {"name": "Coinbase Prime", "slug": "coinbase-prime", "type": "exchange", "category": "prime_broker", "chains": ["bitcoin", "ethereum"], "aliases": ["cb prime", "prime wallet"], "tags": ["broker", "custody", "institutional"]},
    {"name": "OKX", "slug": "okx", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon", "optimism", "avalanche"], "aliases": ["okex"], "tags": ["exchange", "cex"]},
    {"name": "Bybit", "slug": "bybit", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon"], "aliases": ["bybit exchange"], "tags": ["exchange", "cex"]},
    {"name": "Bitfinex", "slug": "bitfinex", "type": "exchange", "category": "cex", "chains": ["ethereum", "avalanche"], "aliases": ["bitfinex exchange"], "tags": ["exchange", "cex"]},
    {"name": "Kraken", "slug": "kraken", "type": "exchange", "category": "cex", "chains": ["bitcoin", "ethereum", "arbitrum", "polygon"], "aliases": ["kraken exchange"], "tags": ["exchange", "cex"]},
    {"name": "Kraken Prime", "slug": "kraken-prime", "type": "exchange", "category": "prime_broker", "chains": ["bitcoin", "ethereum"], "aliases": ["kraken otc"], "tags": ["broker", "custody", "institutional"]},
    {"name": "KuCoin", "slug": "kucoin", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon"], "aliases": ["ku coin"], "tags": ["exchange", "cex"]},
    {"name": "Gate.io", "slug": "gate-io", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "bsc"], "aliases": ["gateio", "gate", "gate exchange"], "tags": ["exchange", "cex"]},
    {"name": "HTX", "slug": "htx", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum"], "aliases": ["huobi", "huobi global"], "tags": ["exchange", "cex"]},
    {"name": "MEXC", "slug": "mexc", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "bsc"], "aliases": ["mexc global"], "tags": ["exchange", "cex"]},
    {"name": "Bitget", "slug": "bitget", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "bsc"], "aliases": ["bit get"], "tags": ["exchange", "cex"]},
    {"name": "Crypto.com", "slug": "crypto-com", "type": "exchange", "category": "cex", "chains": ["bitcoin", "ethereum"], "aliases": ["cryptocom", "crypto.com exchange"], "tags": ["exchange", "cex"]},
    {"name": "Gemini", "slug": "gemini", "type": "exchange", "category": "cex", "chains": ["bitcoin", "ethereum"], "aliases": ["gemini exchange"], "tags": ["exchange", "cex"]},
    {"name": "Upbit", "slug": "upbit", "type": "exchange", "category": "cex", "chains": ["bitcoin", "ethereum"], "aliases": ["up bit"], "tags": ["exchange", "cex"]},
    {"name": "FalconX", "slug": "falconx", "type": "exchange", "category": "prime_broker", "chains": ["bitcoin", "ethereum"], "aliases": ["falcon x"], "tags": ["broker", "institutional", "otc"]},
    {"name": "Circle", "slug": "circle", "type": "fund", "category": "issuer", "chains": ["ethereum", "arbitrum", "base", "solana"], "aliases": ["circle internet financial", "usdc issuer"], "tags": ["issuer", "stablecoin"]},
    {"name": "Robinhood", "slug": "robinhood", "type": "exchange", "category": "broker", "chains": ["bitcoin", "ethereum"], "aliases": ["robin hood"], "tags": ["broker", "retail"]},
    {"name": "Revolut", "slug": "revolut", "type": "exchange", "category": "broker", "chains": ["bitcoin", "ethereum"], "aliases": ["revolut crypto"], "tags": ["broker", "retail"]},
    {"name": "Polymarket", "slug": "polymarket", "type": "protocol", "category": "prediction_market", "chains": ["polygon"], "aliases": ["poly market", "prediction market", "polymarket markets"], "tags": ["prediction market", "protocol", "consumer"]},
    {"name": "BlackRock", "slug": "blackrock", "type": "fund", "category": "asset_manager", "chains": ["bitcoin", "ethereum"], "aliases": ["black rock", "ibit", "blackrock etf", "blackrock bitcoin etf"], "tags": ["etf", "issuer", "fund"]},
    {"name": "Grayscale", "slug": "grayscale", "type": "fund", "category": "asset_manager", "chains": ["bitcoin", "ethereum"], "aliases": ["grayscale investments", "gbtc", "grayscale etf"], "tags": ["etf", "issuer", "fund"]},
    {"name": "Fidelity", "slug": "fidelity", "type": "fund", "category": "asset_manager", "chains": ["bitcoin", "ethereum"], "aliases": ["fidelity digital assets", "fbtc"], "tags": ["etf", "issuer", "fund"]},
    {"name": "Franklin Templeton", "slug": "franklin-templeton", "type": "fund", "category": "asset_manager", "chains": ["bitcoin", "ethereum"], "aliases": ["franklin", "benji"], "tags": ["fund", "issuer"]},
    {"name": "VanEck", "slug": "vaneck", "type": "fund", "category": "asset_manager", "chains": ["bitcoin", "ethereum"], "aliases": ["van eck", "hodl etf"], "tags": ["etf", "issuer", "fund"]},
    {"name": "WisdomTree", "slug": "wisdomtree", "type": "fund", "category": "asset_manager", "chains": ["bitcoin", "ethereum"], "aliases": ["wisdom tree"], "tags": ["etf", "issuer", "fund"]},
    {"name": "Jump Trading", "slug": "jump-trading", "type": "fund", "category": "market_maker", "chains": ["ethereum", "solana"], "aliases": ["jump", "jump crypto"], "tags": ["market maker", "fund"]},
    {"name": "Wintermute", "slug": "wintermute", "type": "fund", "category": "market_maker", "chains": ["ethereum", "arbitrum", "solana"], "aliases": ["wintermute trading"], "tags": ["market maker", "fund"]},
    {"name": "Jane Street", "slug": "jane-street", "type": "fund", "category": "market_maker", "chains": ["ethereum"], "aliases": ["jane street capital"], "tags": ["market maker", "fund"]},
    {"name": "Cumberland", "slug": "cumberland", "type": "fund", "category": "market_maker", "chains": ["bitcoin", "ethereum"], "aliases": ["cumberland drw"], "tags": ["market maker", "otc"]},
    {"name": "B2C2", "slug": "b2c2", "type": "fund", "category": "market_maker", "chains": ["bitcoin", "ethereum"], "aliases": ["b2 c2"], "tags": ["market maker", "otc"]},
    {"name": "Alameda Research", "slug": "alameda-research", "type": "fund", "category": "trading_firm", "chains": ["ethereum", "solana"], "aliases": ["alameda"], "tags": ["fund", "trading"]},
    {"name": "a16z crypto", "slug": "a16z-crypto", "type": "fund", "category": "vc", "chains": ["ethereum"], "aliases": ["a16z", "andreessen horowitz"], "tags": ["vc", "fund"]},
    {"name": "Paradigm", "slug": "paradigm", "type": "fund", "category": "vc", "chains": ["ethereum"], "aliases": ["paradigm fund"], "tags": ["vc", "fund"]},
    {"name": "Polychain Capital", "slug": "polychain-capital", "type": "fund", "category": "vc", "chains": ["ethereum"], "aliases": ["polychain"], "tags": ["vc", "fund"]},
    {"name": "DWF Labs", "slug": "dwf-labs", "type": "fund", "category": "market_maker", "chains": ["ethereum", "bsc"], "aliases": ["dwf"], "tags": ["market maker", "fund"]},
    {"name": "GSR", "slug": "gsr", "type": "fund", "category": "market_maker", "chains": ["ethereum"], "aliases": ["gsr markets"], "tags": ["market maker", "fund"]},
    {"name": "Amber Group", "slug": "amber-group", "type": "fund", "category": "market_maker", "chains": ["ethereum", "arbitrum"], "aliases": ["amber"], "tags": ["market maker", "fund"]},
    {"name": "Galaxy Digital", "slug": "galaxy-digital", "type": "fund", "category": "fund", "chains": ["bitcoin", "ethereum"], "aliases": ["galaxy"], "tags": ["fund", "asset manager"]},
    {"name": "Uniswap", "slug": "uniswap", "type": "protocol", "category": "dex", "chains": ["ethereum", "arbitrum", "base", "polygon"], "aliases": ["uni dex"], "tags": ["dex", "amm"]},
    {"name": "PancakeSwap", "slug": "pancakeswap", "type": "protocol", "category": "dex", "chains": ["bsc", "ethereum", "arbitrum", "base"], "aliases": ["pancake", "pcs"], "tags": ["dex", "amm"]},
    {"name": "Curve", "slug": "curve", "type": "protocol", "category": "dex", "chains": ["ethereum", "arbitrum"], "aliases": ["curve finance"], "tags": ["dex", "amm"]},
    {"name": "SushiSwap", "slug": "sushiswap", "type": "protocol", "category": "dex", "chains": ["ethereum", "arbitrum", "polygon"], "aliases": ["sushi", "sushi swap"], "tags": ["dex", "amm"]},
    {"name": "Balancer", "slug": "balancer", "type": "protocol", "category": "dex", "chains": ["ethereum", "arbitrum"], "aliases": ["bal"], "tags": ["dex", "amm"]},
    {"name": "1inch", "slug": "1inch", "type": "protocol", "category": "aggregator", "chains": ["ethereum", "arbitrum", "polygon", "bsc"], "aliases": ["oneinch", "1 inch"], "tags": ["aggregator", "dex"]},
    {"name": "Aerodrome", "slug": "aerodrome", "type": "protocol", "category": "dex", "chains": ["base"], "aliases": ["aero"], "tags": ["dex", "amm"]},
]

ENTITY_PROFILE_CATALOG: dict[str, dict[str, Any]] = {
    "binance": {
        "description": "Global centralized exchange with a large cross-chain footprint and publicly tracked proof-of-reserves flows.",
        "website": "https://www.binance.com/",
        "socials": {
            "x": "https://x.com/binance",
            "linkedin": "https://www.linkedin.com/company/binance/",
        },
        "badges": ["Binance Proof of Reserves", "Centralized Exchange", "CEX"],
        "coverage_chains": ["ethereum", "bsc", "arbitrum"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc", "dai"],
    },
    "coinbase": {
        "description": "US-listed exchange and custody platform with extensive institutional and Prime brokerage activity.",
        "website": "https://www.coinbase.com/",
        "socials": {
            "x": "https://x.com/coinbase",
            "linkedin": "https://www.linkedin.com/company/coinbase/",
        },
        "badges": ["Public Company", "Centralized Exchange", "Custody"],
        "coverage_chains": ["ethereum", "base", "arbitrum"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc", "dai"],
    },
    "coinbase-prime": {
        "description": "Institutional trading and custody arm of Coinbase, often visible in ETF and large-fund settlement flows.",
        "website": "https://www.coinbase.com/prime",
        "socials": {
            "x": "https://x.com/coinbase",
            "linkedin": "https://www.linkedin.com/company/coinbase/",
        },
        "badges": ["Prime Broker", "Institutional", "Custody"],
        "coverage_chains": ["ethereum", "base"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc"],
    },
    "blackrock": {
        "description": "Global asset manager with tokenized fund products and publicly watched ETF-related crypto flows.",
        "website": "https://www.blackrock.com/",
        "socials": {
            "x": "https://x.com/blackrock",
            "linkedin": "https://www.linkedin.com/company/blackrock/",
        },
        "badges": ["Asset Manager", "ETF Issuer", "Fund"],
        "coverage_chains": ["ethereum"],
        "coverage_tokens": ["wbtc", "weth", "usdc", "usdt"],
    },
    "okx": {
        "description": "Global exchange venue with active spot, routing and treasury movement across major EVM chains.",
        "website": "https://www.okx.com/",
        "socials": {
            "x": "https://x.com/okx",
        },
        "badges": ["Centralized Exchange", "CEX", "Perps Venue"],
        "coverage_chains": ["ethereum", "arbitrum", "polygon", "optimism", "avalanche"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc", "dai"],
        "coverage_pairs": [
            {"symbol": "USDT", "chain": "ethereum"},
            {"symbol": "USDC", "chain": "arbitrum"},
            {"symbol": "WETH", "chain": "ethereum"},
            {"symbol": "WBTC", "chain": "polygon"},
        ],
    },
    "bybit": {
        "description": "Exchange and derivatives venue with fast-moving treasury, routing and market-maker visible flows.",
        "website": "https://www.bybit.com/",
        "socials": {
            "x": "https://x.com/Bybit_Official",
        },
        "badges": ["Centralized Exchange", "CEX", "Derivatives"],
        "coverage_chains": ["ethereum", "arbitrum", "polygon"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc", "dai"],
        "coverage_pairs": [
            {"symbol": "USDT", "chain": "ethereum"},
            {"symbol": "WETH", "chain": "arbitrum"},
            {"symbol": "WBTC", "chain": "ethereum"},
        ],
    },
    "kraken": {
        "description": "Long-running centralized exchange and custody venue with large BTC, ETH and stablecoin settlement flows.",
        "website": "https://www.kraken.com/",
        "socials": {
            "x": "https://x.com/krakenfx",
        },
        "badges": ["Centralized Exchange", "CEX", "Custody"],
        "coverage_chains": ["bitcoin", "ethereum", "arbitrum", "polygon"],
        "coverage_tokens": ["btc", "eth", "usdt", "usdc", "weth"],
        "coverage_pairs": [
            {"symbol": "BTC", "chain": "bitcoin"},
            {"symbol": "ETH", "chain": "ethereum"},
            {"symbol": "USDT", "chain": "ethereum"},
        ],
    },
    "kraken-prime": {
        "description": "Institutional prime and OTC settlement surface connected to large custody and market-access flows.",
        "website": "https://www.kraken.com/institutions",
        "socials": {
            "x": "https://x.com/krakenfx",
        },
        "badges": ["Prime Broker", "Institutional", "Custody"],
        "coverage_chains": ["bitcoin", "ethereum"],
        "coverage_tokens": ["btc", "eth", "usdt", "usdc"],
        "coverage_pairs": [
            {"symbol": "BTC", "chain": "bitcoin"},
            {"symbol": "ETH", "chain": "ethereum"},
        ],
    },
    "kucoin": {
        "description": "Centralized exchange with broad altcoin and stablecoin activity that frequently shows up in listing-era flows.",
        "website": "https://www.kucoin.com/",
        "socials": {
            "x": "https://x.com/kucoincom",
        },
        "badges": ["Centralized Exchange", "CEX", "Altcoin Venue"],
        "coverage_chains": ["ethereum", "arbitrum", "polygon"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc", "dai"],
        "coverage_pairs": [
            {"symbol": "USDT", "chain": "ethereum"},
            {"symbol": "WETH", "chain": "arbitrum"},
            {"symbol": "WBTC", "chain": "ethereum"},
        ],
    },
    "htx": {
        "description": "Exchange venue previously branded as Huobi, with cross-chain stablecoin routing and exchange treasury flows.",
        "website": "https://www.htx.com/",
        "socials": {
            "x": "https://x.com/HTX_Global",
        },
        "badges": ["Centralized Exchange", "CEX", "Global Venue"],
        "coverage_chains": ["ethereum", "arbitrum"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc"],
        "coverage_pairs": [
            {"symbol": "USDT", "chain": "ethereum"},
            {"symbol": "WETH", "chain": "ethereum"},
            {"symbol": "WBTC", "chain": "ethereum"},
        ],
    },
    "bitget": {
        "description": "Global centralized exchange with growing spot and derivatives footprint across EVM chains.",
        "website": "https://www.bitget.com/",
        "socials": {
            "x": "https://x.com/bitgetglobal",
            "linkedin": "https://www.linkedin.com/company/bitget/",
        },
        "badges": ["Centralized Exchange", "CEX"],
        "coverage_chains": ["ethereum", "bsc", "arbitrum"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc"],
    },
    "gate-io": {
        "description": "Centralized exchange with broad altcoin support and frequent stablecoin settlement activity.",
        "website": "https://www.gate.io/",
        "socials": {
            "x": "https://x.com/gate_io",
            "linkedin": "https://www.linkedin.com/company/gate-io/",
        },
        "badges": ["Centralized Exchange", "CEX"],
        "coverage_chains": ["ethereum", "bsc", "arbitrum"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc"],
    },
    "mexc": {
        "description": "Centralized exchange active across EVM chains, with heavy stablecoin and listing-driven flows.",
        "website": "https://www.mexc.com/",
        "socials": {
            "x": "https://x.com/MEXC_Official",
            "linkedin": "https://www.linkedin.com/company/mexcglobal/",
        },
        "badges": ["Centralized Exchange", "CEX"],
        "coverage_chains": ["ethereum", "bsc", "arbitrum"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc"],
    },
    "grayscale": {
        "description": "Asset manager behind GBTC, ETHE and related trust or ETF vehicles that are closely watched for custody flows.",
        "website": "https://www.grayscale.com/",
        "socials": {
            "x": "https://x.com/Grayscale",
        },
        "badges": ["Asset Manager", "ETF Issuer", "Fund"],
        "coverage_chains": ["bitcoin", "ethereum"],
        "coverage_tokens": ["btc", "eth", "wbtc", "weth", "usdc"],
        "coverage_pairs": [
            {"symbol": "BTC", "chain": "bitcoin"},
            {"symbol": "ETH", "chain": "ethereum"},
        ],
    },
    "fidelity": {
        "description": "Institutional asset manager and custody platform with ETF-adjacent settlement and treasury movement.",
        "website": "https://www.fidelity.com/",
        "socials": {
            "x": "https://x.com/Fidelity",
        },
        "badges": ["Asset Manager", "ETF Issuer", "Custody"],
        "coverage_chains": ["bitcoin", "ethereum"],
        "coverage_tokens": ["btc", "eth", "usdc", "wbtc", "weth"],
        "coverage_pairs": [
            {"symbol": "BTC", "chain": "bitcoin"},
            {"symbol": "ETH", "chain": "ethereum"},
        ],
    },
    "franklin-templeton": {
        "description": "Asset manager with tokenized fund activity and ETF-linked flows that increasingly appear on public rails.",
        "website": "https://www.franklintempleton.com/",
        "socials": {
            "x": "https://x.com/FTI_US",
        },
        "badges": ["Asset Manager", "Tokenized Fund", "ETF Issuer"],
        "coverage_chains": ["ethereum", "polygon"],
        "coverage_tokens": ["usdc", "usdt", "weth", "wbtc"],
        "coverage_pairs": [
            {"symbol": "USDC", "chain": "ethereum"},
            {"symbol": "USDC", "chain": "polygon"},
        ],
    },
    "vaneck": {
        "description": "ETF issuer and asset manager with public crypto product flows visible through custody and settlement wallets.",
        "website": "https://www.vaneck.com/",
        "socials": {
            "x": "https://x.com/vaneck_us",
        },
        "badges": ["Asset Manager", "ETF Issuer", "Fund"],
        "coverage_chains": ["bitcoin", "ethereum"],
        "coverage_tokens": ["btc", "eth", "usdc", "wbtc"],
        "coverage_pairs": [
            {"symbol": "BTC", "chain": "bitcoin"},
            {"symbol": "ETH", "chain": "ethereum"},
        ],
    },
    "wisdomtree": {
        "description": "Asset manager and tokenized-asset issuer with stable settlement and custody-linked crypto flows.",
        "website": "https://www.wisdomtree.com/",
        "socials": {
            "x": "https://x.com/WisdomTreeFunds",
        },
        "badges": ["Asset Manager", "ETF Issuer", "Tokenized Assets"],
        "coverage_chains": ["bitcoin", "ethereum"],
        "coverage_tokens": ["btc", "eth", "usdc", "wbtc"],
        "coverage_pairs": [
            {"symbol": "BTC", "chain": "bitcoin"},
            {"symbol": "ETH", "chain": "ethereum"},
        ],
    },
    "falconx": {
        "description": "Institutional prime brokerage and OTC venue that often sits between funds, ETFs and exchange settlement surfaces.",
        "website": "https://www.falconx.io/",
        "socials": {
            "x": "https://x.com/falconxnetwork",
        },
        "badges": ["Prime Broker", "Institutional", "OTC"],
        "coverage_chains": ["bitcoin", "ethereum"],
        "coverage_tokens": ["btc", "eth", "usdt", "usdc"],
        "coverage_pairs": [
            {"symbol": "BTC", "chain": "bitcoin"},
            {"symbol": "ETH", "chain": "ethereum"},
        ],
    },
    "wintermute": {
        "description": "Market-making and OTC trading firm with fast-moving routing, rebalancing and exchange interaction surfaces.",
        "website": "https://www.wintermute.com/",
        "socials": {
            "x": "https://x.com/wintermute_t",
        },
        "badges": ["Market Maker", "OTC", "Trading Firm"],
        "coverage_chains": ["ethereum", "arbitrum", "solana"],
        "coverage_tokens": ["usdt", "usdc", "weth", "wbtc", "dai"],
        "coverage_pairs": [
            {"symbol": "USDT", "chain": "ethereum"},
            {"symbol": "USDC", "chain": "arbitrum"},
            {"symbol": "WETH", "chain": "ethereum"},
        ],
    },
    "pancakeswap": {
        "description": "DEX and AMM ecosystem centered on BNB Chain, with routers, vaults and pool activity visible on-chain.",
        "website": "https://pancakeswap.finance/",
        "socials": {
            "x": "https://x.com/PancakeSwap",
        },
        "badges": ["DEX", "AMM", "Protocol"],
        "coverage_chains": ["bsc", "ethereum", "arbitrum"],
        "coverage_tokens": ["usdt", "usdc", "weth", "dai"],
    },
    "uniswap": {
        "description": "Major DEX and routing surface where pools, routers, vaults and LP entities reveal token distribution changes early.",
        "website": "https://uniswap.org/",
        "socials": {
            "x": "https://x.com/Uniswap",
        },
        "badges": ["DEX", "AMM", "Protocol"],
        "coverage_chains": ["ethereum", "arbitrum", "base", "polygon"],
        "coverage_tokens": ["uni", "weth", "usdc", "usdt", "dai"],
        "coverage_pairs": [
            {"symbol": "UNI", "chain": "ethereum"},
            {"symbol": "WETH", "chain": "ethereum"},
            {"symbol": "USDC", "chain": "base"},
            {"symbol": "USDT", "chain": "arbitrum"},
        ],
    },
    "curve": {
        "description": "Stable-swap focused DEX with pool and gauge surfaces that often matter in treasury and liquidity rotations.",
        "website": "https://curve.fi/",
        "socials": {
            "x": "https://x.com/CurveFinance",
        },
        "badges": ["DEX", "Stable Swap", "Protocol"],
        "coverage_chains": ["ethereum", "arbitrum"],
        "coverage_tokens": ["crv", "usdt", "usdc", "dai", "weth"],
        "coverage_pairs": [
            {"symbol": "USDT", "chain": "ethereum"},
            {"symbol": "USDC", "chain": "ethereum"},
            {"symbol": "DAI", "chain": "ethereum"},
        ],
    },
    "sushiswap": {
        "description": "Multi-chain DEX surface with router and pool flows that often shows up in token migration and liquidity events.",
        "website": "https://www.sushi.com/",
        "socials": {
            "x": "https://x.com/SushiSwap",
        },
        "badges": ["DEX", "AMM", "Protocol"],
        "coverage_chains": ["ethereum", "arbitrum", "polygon"],
        "coverage_tokens": ["sushi", "weth", "usdc", "usdt", "dai"],
        "coverage_pairs": [
            {"symbol": "SUSHI", "chain": "ethereum"},
            {"symbol": "WETH", "chain": "arbitrum"},
            {"symbol": "USDC", "chain": "polygon"},
        ],
    },
    "balancer": {
        "description": "Vault-based liquidity protocol where weighted pools and treasury vaults can reveal concentrated entity behavior.",
        "website": "https://balancer.fi/",
        "socials": {
            "x": "https://x.com/Balancer",
        },
        "badges": ["DEX", "Vaults", "Protocol"],
        "coverage_chains": ["ethereum", "arbitrum"],
        "coverage_tokens": ["bal", "weth", "usdc", "usdt", "dai"],
        "coverage_pairs": [
            {"symbol": "BAL", "chain": "ethereum"},
            {"symbol": "WETH", "chain": "arbitrum"},
            {"symbol": "USDC", "chain": "ethereum"},
        ],
    },
    "1inch": {
        "description": "Aggregator and router surface useful for spotting smart-order routing, token exits and distribution reshuffles.",
        "website": "https://1inch.io/",
        "socials": {
            "x": "https://x.com/1inch",
        },
        "badges": ["Aggregator", "Router", "Protocol"],
        "coverage_chains": ["ethereum", "arbitrum", "polygon", "bsc"],
        "coverage_tokens": ["1inch", "weth", "usdc", "usdt", "dai"],
        "coverage_pairs": [
            {"symbol": "1INCH", "chain": "ethereum"},
            {"symbol": "USDC", "chain": "polygon"},
            {"symbol": "USDT", "chain": "bsc"},
        ],
    },
    "aerodrome": {
        "description": "Base-native DEX and liquidity hub whose pool and incentive surfaces can highlight token rotation early.",
        "website": "https://aerodrome.finance/",
        "socials": {
            "x": "https://x.com/aerodromefi",
        },
        "badges": ["DEX", "Base", "Protocol"],
        "coverage_chains": ["base"],
        "coverage_tokens": ["aero", "weth", "usdc", "dai"],
        "coverage_pairs": [
            {"symbol": "AERO", "chain": "base"},
            {"symbol": "WETH", "chain": "base"},
            {"symbol": "USDC", "chain": "base"},
        ],
    },
    "polymarket": {
        "description": "Prediction market protocol on Polygon where treasury, market resolution and router activity can cluster around major events.",
        "website": "https://polymarket.com/",
        "socials": {
            "x": "https://x.com/Polymarket",
        },
        "badges": ["Prediction Market", "Protocol", "Consumer App"],
        "coverage_chains": ["polygon"],
        "coverage_tokens": ["usdc"],
        "coverage_pairs": [
            {"symbol": "USDC", "chain": "polygon"},
        ],
    },
}


def get_entity_profile(slug: str, entity: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_slug = str(slug or "").strip().lower()
    if normalized_slug in ENTITY_PROFILE_CATALOG:
        return dict(ENTITY_PROFILE_CATALOG[normalized_slug])

    normalized_name = _slugify_text((entity or {}).get("name", ""))
    if normalized_name in ENTITY_PROFILE_CATALOG:
        return dict(ENTITY_PROFILE_CATALOG[normalized_name])

    return {}


def _compact_search_text(value: str) -> str:
    return "".join(ch for ch in value.lower().strip() if ch.isalnum())


def _score_static_entity(entity: dict[str, Any], query: str) -> int:
    query_raw = query.lower().strip()
    query_compact = _compact_search_text(query_raw)
    if not query_raw:
        return 0

    primary_fields = [entity.get("name", ""), entity.get("slug", ""), *(entity.get("aliases") or [])]
    secondary_fields = [
        entity.get("type", ""),
        entity.get("category", ""),
        *(entity.get("tags") or []),
        *(entity.get("chains") or []),
    ]

    for field in primary_fields:
        text = str(field).lower().strip()
        compact = _compact_search_text(text)
        if not text:
            continue
        if text == query_raw or compact == query_compact:
            return 140

    for field in primary_fields:
        text = str(field).lower().strip()
        compact = _compact_search_text(text)
        if not text:
            continue
        if text.startswith(query_raw) or compact.startswith(query_compact):
            return 110

    for field in primary_fields:
        text = str(field).lower().strip()
        compact = _compact_search_text(text)
        if not text:
            continue
        if query_raw in text:
            return 85

    for field in secondary_fields:
        text = str(field).lower().strip()
        if not text:
            continue
        if query_raw in text:
            return 45

    return 0

# Blockscout API URLs (free, no API key needed)
BLOCKSCOUT_API_URLS = {
    "ethereum": "https://eth.blockscout.com/api/v2",
    "bsc": "https://bsc.blockscout.com/api/v2",
    "arbitrum": "https://arbitrum.blockscout.com/api/v2",
    "polygon": "https://polygon.blockscout.com/api/v2",
    "optimism": "https://optimism.blockscout.com/api/v2",
    "avalanche": "https://scan.avax.network/graphiql",
    "base": "https://base.blockscout.com/api/v2",
}

# TTL du cache en secondes (7 jours par défaut)
CACHE_TTL = 7 * 24 * 3600


# =========================================================
# ARKHAM DATABASE — Couche d'abstraction pour le cache Arkham
# =========================================================


class ArkhamDatabase:
    """
    Base de données Arkham en mémoire, chargée depuis le cache JSON.

    Fournit des méthodes de lookup et recherche pour le tracker et le router.
    Utilise le même fichier cache que ArkhamScraper (data/arkham/cache.json).
    """

    def __init__(self) -> None:
        self._cache: dict[str, Any] = self._load()
        self._entities_by_name: dict[str, dict] = {}
        self._addresses_by_hash: dict[str, dict] = {}
        self._build_indexes()

    def _load(self) -> dict[str, Any]:
        """Charge le cache depuis le disque."""
        default = {
            "entities": {}, "addresses": {},
            "metadata": {"firecrawl_credits_used": 0, "last_scrape": 0, "created_at": time.time()},
            "entities_search_cache": {}, "holders_cache": {}, "exchange_wallets": None,
        }
        if not CACHE_FILE.exists():
            return default
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            for key, default_val in default.items():
                if key not in data:
                    data[key] = default_val
            return data
        except Exception:
            return default

    def load(self) -> None:
        """Recharge le cache depuis le disque (utile après un scrape)."""
        self._cache = self._load()
        self._build_indexes()

    def _build_indexes(self) -> None:
        """Construit les index de recherche à partir du cache."""
        self._entities_by_name = {}
        self._addresses_by_hash = {}

        for slug, entity_data in self._cache.get("entities", {}).items():
            if isinstance(entity_data, dict):
                name = entity_data.get("name", "").lower()
                self._entities_by_name[slug] = entity_data
                if name:
                    self._entities_by_name[name] = entity_data

        for addr, addr_data in self._cache.get("addresses", {}).items():
            if isinstance(addr_data, dict):
                addr_lower = addr.lower() if addr.startswith("0x") else addr
                self._addresses_by_hash[addr_lower] = addr_data

    @property
    def entities_by_name(self) -> dict[str, dict]:
        """Retourne le dictionnaire des entités indexées par nom/slug."""
        return self._entities_by_name

    def lookup_wallet(self, address: str, chain: str = "ethereum") -> Optional[dict]:
        """
        Lookup une adresse dans la DB Arkham.
        Retourne: dict avec label, entity, wallet_type si trouvé, None sinon.
        """
        addr_lower = address.lower() if address.startswith("0x") else address
        return self._addresses_by_hash.get(addr_lower)

    def search_wallets(self, query: str) -> list[dict]:
        """Recherche floue de wallets par label ou adresse."""
        q = query.lower()
        results = []
        for addr, data in self._addresses_by_hash.items():
            label = data.get("label", "").lower()
            entity = data.get("entity", "").lower()
            if q in label or q in entity or q in addr:
                results.append({"address": addr, **data})
        return results[:50]

    def get_entity_info(self, slug: str) -> Optional[dict]:
        """Retourne les infos d'une entité par slug."""
        return self._cache.get("entities", {}).get(slug.lower())

    def get_entity_wallets(self, slug: str) -> list[dict]:
        """Retourne les wallets d'une entité."""
        entity = self._cache.get("entities", {}).get(slug.lower(), {})
        return entity.get("addresses", [])

    def search_tokens(self, query: str) -> list[dict]:
        """
        Recherche de tokens dans le cache Arkham DB.

        Parcourt les entités et le holders_cache pour trouver des tokens
        correspondant au query (symbole, nom, adresse de contrat).

        Retourne une liste de dicts: {id, symbol, name, contract_address, market_cap_usd, price_usd}
        """
        q = query.lower().strip()
        if not q:
            return []

        results = []
        seen = set()

        # Chercher dans les tokens mentionnés dans les entités scrapées
        for slug, entity_data in self._cache.get("entities", {}).items():
            if not isinstance(entity_data, dict):
                continue
            tokens = entity_data.get("tokens", [])
            if isinstance(tokens, list):
                for t in tokens:
                    t_symbol = (t.get("symbol") or "").lower()
                    t_name = (t.get("name") or "").lower()
                    t_id = t.get("id", t.get("symbol", ""))
                    if t_id and t_id not in seen and (q in t_symbol or q in t_name):
                        seen.add(t_id)
                        results.append({
                            "id": t_id,
                            "symbol": t.get("symbol", "").upper(),
                            "name": t.get("name", ""),
                            "contract_address": t.get("contract_address", ""),
                            "market_cap_usd": t.get("market_cap_usd"),
                            "price_usd": t.get("price_usd"),
                        })

        # Chercher dans le holders_cache (clés de type "holders:{chain}:{contract}")
        for key in self._cache.get("holders_cache", {}):
            if key.startswith("holders:") and q in key.lower():
                parts = key.split(":")
                token_addr = parts[-1] if len(parts) >= 3 else key
                if token_addr and token_addr not in seen:
                    seen.add(token_addr)
                    results.append({
                        "id": token_addr,
                        "symbol": "",
                        "name": "",
                        "contract_address": token_addr,
                        "market_cap_usd": None,
                        "price_usd": None,
                    })

        return results[:20]

    def get_stats(self) -> dict:
        """Statistiques de la DB."""
        metadata = self._cache.get("metadata", {})
        return {
            "total_entities": len(self._cache.get("entities", {})),
            "total_addresses": len(self._cache.get("addresses", {})),
            "total_search_cache_entries": len(self._cache.get("entities_search_cache", {})),
            "total_token_entries": len(self._cache.get("holders_cache", {})),
            "firecrawl_credits_used": metadata.get("firecrawl_credits_used", 0),
            "last_scrape": metadata.get("last_scrape", 0),
        }


# Instance globale
_db_instance: Optional[ArkhamDatabase] = None


def get_arkham_db() -> ArkhamDatabase:
    """Récupère ou crée l'instance singleton de la DB Arkham."""
    global _db_instance
    if _db_instance is None:
        _db_instance = ArkhamDatabase()
    return _db_instance


# =========================================================
# ARKHAM SCRAPER — Moteur principal avec préservation des crédits
# =========================================================


class ArkhamScraper:
    """
    Smart Arkham Intelligence scraper with credit-preserving strategy.

    Firecrawl credits are PRECIOUS (500 one-time, non-renewable).
    Only use Firecrawl for data that NO free API can provide:

    USES FIRECRAWL FOR:
    - Entity labels (name → address mapping from Arkham pages)
    - Exchange wallet addresses (not available via API)
    - Fund/portfolio labels
    - Token unlock calendar (if no API available)

    NEVER USES FIRECRAWL FOR:
    - Transaction history (use Etherscan/BSCScan API — FREE)
    - Token balances (use blockchain API — FREE)
    - Price data (use Binance/Hyperliquid — FREE)
    - Funding/OI data (use Coinglass/Binance — FREE)
    """

    def _load_env_manually(self) -> None:
        """
        Charge les clés API depuis .env directement.
        Contourne la perte d'environnement causée par uvicorn --reload.
        """
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k in ("FIRECRAWL_API_KEY", "ETHERSCAN_API_KEY", "BSCSCAN_API_KEY", "COVALENT_API_KEY"):
                        if k not in os.environ or not os.environ.get(k):
                            os.environ[k] = v

    def __init__(self) -> None:
        """
        Initialise le scraper. Charge les clés API depuis l'environnement
        et le cache depuis le disque.
        """
        # Charger l'environnement manuellement (nécessaire car uvicorn --reload le perd)
        self._load_env_manually()

        # --- Clés API ---
        self.firecrawl_api_key: str = os.getenv(FIRECRAWL_API_KEY_ENV, "")
        self.etherscan_api_key: str = os.getenv(ETHERSCAN_API_KEY_ENV, "")
        self.bscscan_api_key: str = os.getenv(BSCSCAN_API_KEY_ENV, "")
        self.covalent_api_key: str = os.getenv(COVALENT_API_KEY_ENV, "")

        if not self.firecrawl_api_key or self.firecrawl_api_key == "fc-YOUR_KEY_HERE":
            logger.warning(
                "[ARKHAM] FIRECRAWL_API_KEY non configurée — "
                "le scraping sera désactivé (cache-only mode)"
            )
            self._firecrawl_available = False
        else:
            self._firecrawl_available = True

        if not self.etherscan_api_key or self.etherscan_api_key.startswith("YOUR_"):
            logger.warning(
                "[ARKHAM] ETHERSCAN_API_KEY non configurée — "
                "les requêtes blockchain Ethereum seront limitées"
            )

        # --- Headers Firecrawl ---
        self._firecrawl_headers = {
            "Authorization": f"Bearer {self.firecrawl_api_key}",
            "Content-Type": "application/json",
        }

        # --- Rate limiting ---
        self._last_request_ts: float = 0.0

        # --- Cache ---
        self._cache: dict[str, Any] = self._load_cache()
        logger.info(
            f"[ARKHAM] Cache chargé: "
            f"{len(self._cache.get('entities', {}))} entités, "
            f"{len(self._cache.get('addresses', {}))} adresses, "
            f"{self._cache.get('metadata', {}).get('firecrawl_credits_used', 0)} crédits Firecrawl utilisés"
        )

    # =========================================================
    # MÉTHODES PUBLIQUES
    # =========================================================

    def search_entity(self, name: str) -> list[dict]:
        """
        Recherche une entité Arkham par nom.

        Stratégie:
        1. Vérifier le cache local (GRATUIT)
        2. Si pas en cache → utiliser Firecrawl pour scraper la page Arkham
        3. Sauvegarder le résultat en cache

        Args:
            name: Nom de l'entité (ex: "Binance", "Jump Trading")

        Returns:
            Liste de dicts avec les entités trouvées.
            Chaque dict contient: name, slug, type, addresses, etc.
        """
        name_lower = name.lower().strip()

        # 1. Vérifier le cache
        cached = self._check_cache(f"entity_search:{name_lower}")
        if cached is not None:
            logger.info(f"[ARKHAM] Cache HIT pour recherche '{name}'")
            return cached

        # 2. Vérifier aussi dans les entités déjà scrapées
        entities = self._cache.get("entities", {})
        matches = []
        for slug, entity_data in entities.items():
            if name_lower in slug or name_lower in entity_data.get("name", "").lower():
                matches.append(entity_data)

        if matches:
            logger.info(f"[ARKHAM] Cache HIT (entités existantes) pour '{name}': {len(matches)} résultats")
            self._cache.setdefault("entities_search_cache", {})[f"entity_search:{name_lower}"] = matches
            self._save_cache()
            return matches

        # 3. Pas en cache → Firecrawl (si disponible)
        if not self._firecrawl_available:
            logger.warning(f"[ARKHAM] '{name}' pas en cache et Firecrawl non disponible — retour vide")
            return []

        logger.info(f"[ARKHAM] Cache MISS pour '{name}' — utilisation Firecrawl (coûte 1 crédit)")

        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # On est dans un event loop async — créer une task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    self._firecrawl_search_entity(name),
                ).result()
        else:
            result = asyncio.run(self._firecrawl_search_entity(name))

        if result:
            # Mettre en cache
            self._cache.setdefault("entities_search_cache", {})[f"entity_search:{name_lower}"] = result
            self._save_cache()

        return result or []

    def get_entity_addresses(self, entity_name: str) -> list[dict]:
        """
        Récupère les adresses wallet d'une entité connue.

        Stratégie:
        1. Vérifier le cache (entité déjà scrapée ?)
        2. Si pas en cache → Firecrawl pour scraper la page entity d'Arkham
        3. Sauvegarder les adresses en cache

        Args:
            entity_name: Nom ou slug de l'entité (ex: "binance", "wintermute")

        Returns:
            Liste de dicts avec: address, chain, label, wallet_type, entity
        """
        entity_slug = entity_name.lower().strip().replace(" ", "-")

        # 1. Vérifier le cache
        cached_entity = self._cache.get("entities", {}).get(entity_slug)
        if cached_entity and cached_entity.get("addresses"):
            logger.info(f"[ARKHAM] Cache HIT pour adresses de '{entity_slug}': {len(cached_entity['addresses'])} wallets")
            return cached_entity["addresses"]

        # 2. Vérifier aussi par nom exact
        for slug, data in self._cache.get("entities", {}).items():
            if data.get("name", "").lower() == entity_name.lower() and data.get("addresses"):
                logger.info(f"[ARKHAM] Cache HIT (nom exact) pour '{entity_name}'")
                return data["addresses"]

        # 3. Pas en cache → Firecrawl
        if not self._firecrawl_available:
            logger.warning(f"[ARKHAM] Adresses de '{entity_name}' pas en cache et Firecrawl non disponible")
            return []

        logger.info(f"[ARKHAM] Cache MISS pour adresses de '{entity_name}' — Firecrawl (coûte 1 crédit)")

        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    self._firecrawl_get_entity_addresses(entity_slug),
                ).result()
        else:
            result = asyncio.run(self._firecrawl_get_entity_addresses(entity_slug))

        return result or []

    def get_exchange_wallets(self) -> dict:
        """
        Récupère les adresses wallet de tous les exchanges connus.

        Stratégie: Cache agressif — les wallets d'échanges changent rarement.
        On ne re-scrape que si le cache est expiré (> 7 jours).

        Returns:
            Dict {exchange_name: {"addresses": [...], "scraped_at": timestamp}}
        """
        # Vérifier le cache global des exchanges
        cached_exchanges = self._cache.get("exchange_wallets")
        if cached_exchanges:
            last_scrape = cached_exchanges.get("scraped_at", 0)
            age = time.time() - last_scrape
            if age < CACHE_TTL:
                total_addrs = sum(
                    len(v.get("addresses", []))
                    for v in cached_exchanges.get("exchanges", {}).values()
                    if isinstance(v, dict)
                )
                logger.info(
                    f"[ARKHAM] Cache HIT pour exchange_wallets "
                    f"({total_addrs} adresses, âge: {age / 3600:.1f}h)"
                )
                return cached_exchanges

        # Pas en cache ou expiré → Firecrawl
        if not self._firecrawl_available:
            logger.warning("[ARKHAM] Exchange wallets pas en cache et Firecrawl non disponible")
            # Retourner ce qu'on a dans les entités scrapées
            return self._build_exchange_wallets_from_entities()

        logger.info("[ARKHAM] Cache MISS/EXPIRÉ pour exchange_wallets — Firecrawl")

        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    asyncio.run,
                    self._firecrawl_get_exchange_wallets(),
                ).result()
        else:
            result = asyncio.run(self._firecrawl_get_exchange_wallets())

        return result or self._build_exchange_wallets_from_entities()

    def lookup_address(self, address: str, chain: str = "ethereum") -> Optional[dict]:
        """
        Lookup une adresse on-chain dans la DB Arkham.

        Combinaison du lookup en cache + données blockchain live.

        Retourne un dict avec label, entity, wallet_type, balance_usd, balance_eth
        si l'adresse est identifiée. Sinon retourne les données blockchain brutes.
        """
        addr_lower = address.lower() if address.startswith("0x") else address

        # 1. Vérifier le cache Arkham DB
        db = get_arkham_db()
        cached = db.lookup_wallet(address, chain)
        if cached:
            return {
                "address": address,
                "chain": chain,
                "identified": True,
                "label": cached.get("label", ""),
                "entity": cached.get("entity", ""),
                "wallet_type": cached.get("wallet_type", ""),
                "balance_usd": cached.get("balance_usd"),
                "balance_eth": cached.get("balance_eth"),
            }

        # 2. Pas en cache → récupérer les données blockchain
        blockchain_data = self._fetch_blockchain_data(address, chain)
        if blockchain_data and not blockchain_data.get("error"):
            return {
                "address": address,
                "chain": chain,
                "identified": False,
                "label": "",
                "entity": "",
                "wallet_type": "",
                "balance_eth": blockchain_data.get("balance_eth"),
                "transaction_count": blockchain_data.get("transaction_count"),
                "tokens_count": len(blockchain_data.get("tokens", [])),
            }

        return None

    def search_entity_free(self, query: str) -> list[dict]:
        """
        Recherche une entité dans une base statique gratuite (sans Firecrawl).

        Contient les principaux exchanges, funds, et entités connues avec
        leurs slugs et métadonnées de base. Sert de fallback quand le cache
        Arkham est vide et Firecrawl non disponible.

        Retourne une liste de dicts: {name, slug, type, category, balance_usd, wallet_count, chains}
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        # Base statique d'entités connues (exchanges majeurs, funds, market makers)
        STATIC_ENTITIES = [
            {"name": "Binance", "slug": "binance", "type": "exchange", "category": "cex", "chains": ["ethereum", "bsc", "arbitrum", "polygon"]},
            {"name": "Coinbase", "slug": "coinbase", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon", "optimism"]},
            {"name": "OKX", "slug": "okx", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon", "optimism", "avalanche"]},
            {"name": "Bybit", "slug": "bybit", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon"]},
            {"name": "Bitfinex", "slug": "bitfinex", "type": "exchange", "category": "cex", "chains": ["ethereum", "avalanche"]},
            {"name": "Kraken", "slug": "kraken", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon"]},
            {"name": "KuCoin", "slug": "kucoin", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "polygon"]},
            {"name": "Gate.io", "slug": "gate-io", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "bsc"]},
            {"name": "Huobi", "slug": "huobi", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum"]},
            {"name": "MEXC", "slug": "mexc", "type": "exchange", "category": "cex", "chains": ["ethereum", "arbitrum", "bsc"]},
            {"name": "Jump Trading", "slug": "jump-trading", "type": "fund", "category": "market_maker", "chains": ["ethereum"]},
            {"name": "Wintermute", "slug": "wintermute", "type": "fund", "category": "market_maker", "chains": ["ethereum", "arbitrum"]},
            {"name": "Jane Street", "slug": "jane-street", "type": "fund", "category": "market_maker", "chains": ["ethereum"]},
            {"name": "Alameda Research", "slug": "alameda-research", "type": "fund", "category": "trading_firm", "chains": ["ethereum", "solana"]},
            {"name": "Celsius", "slug": "celsius", "type": "fund", "category": "lending", "chains": ["ethereum"]},
            {"name": "FTX", "slug": "ftx", "type": "exchange", "category": "cex", "chains": ["ethereum", "solana"]},
            {"name": "a16z crypto", "slug": "a16z-crypto", "type": "fund", "category": "vc", "chains": ["ethereum"]},
            {"name": "Paradigm", "slug": "paradigm", "type": "fund", "category": "vc", "chains": ["ethereum"]},
            {"name": "Polychain Capital", "slug": "polychain-capital", "type": "fund", "category": "vc", "chains": ["ethereum"]},
            {"name": "Three Arrows Capital", "slug": "three-arrows-capital", "type": "fund", "category": "fund", "chains": ["ethereum"]},
            {"name": "DWF Labs", "slug": "dwf-labs", "type": "fund", "category": "market_maker", "chains": ["ethereum", "bsc"]},
            {"name": "GSR", "slug": "gsr", "type": "fund", "category": "market_maker", "chains": ["ethereum"]},
            {"name": "Amber Group", "slug": "amber-group", "type": "fund", "category": "market_maker", "chains": ["ethereum", "arbitrum"]},
            {"name": "Galaxy Digital", "slug": "galaxy-digital", "type": "fund", "category": "fund", "chains": ["ethereum"]},
        ]

        results = []
        for entity in STATIC_ENTITIES:
            name_match = query_lower in entity["name"].lower()
            slug_match = query_lower in entity["slug"]
            type_match = query_lower in entity.get("type", "").lower()
            cat_match = query_lower in entity.get("category", "").lower()

            if name_match or slug_match or type_match or cat_match:
                results.append({
                    "name": entity["name"],
                    "slug": entity["slug"],
                    "type": entity["type"],
                    "category": entity.get("category", ""),
                    "balance_usd": None,
                    "wallet_count": None,
                    "chains": entity.get("chains", []),
                    "source": "static_db",
                })

        return results[:10]

    def search_entity_free(self, query: str) -> list[dict]:
        """
        Recherche une entite dans une base statique gratuite (sans Firecrawl).

        Sert de fallback quand le cache Arkham est vide et Firecrawl non
        disponible. La recherche supporte aussi les alias courants comme
        "black rock", "gate", "ibit" ou "pancake".
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        ranked: list[tuple[int, dict[str, Any]]] = []
        for entity in STATIC_ENTITY_CATALOG:
            score = _score_static_entity(entity, query_lower)
            if score <= 0:
                continue
            ranked.append((score, entity))

        ranked.sort(key=lambda item: (-item[0], item[1].get("name", "")))

        results = []
        for score, entity in ranked[:10]:
            results.append({
                "name": entity["name"],
                "slug": entity["slug"],
                "type": entity["type"],
                "category": entity.get("category", ""),
                "balance_usd": None,
                "wallet_count": entity.get("wallet_count"),
                "chains": entity.get("chains", []),
                "aliases": entity.get("aliases", []),
                "source": "static_db",
                "score": score,
            })

        return results

    def search_tokens(self, query: str) -> list[dict]:
        """
        Recherche des tokens dans le cache Arkham DB.

        Parcourt les entités et données cached pour trouver des tokens
        mentionnés (symboles, noms, contrats).

        Retourne une liste de dicts: {id, symbol, name, contract_address, market_cap_usd, price_usd}
        """
        query_lower = query.lower().strip()
        if not query_lower:
            return []

        results = []
        seen = set()

        # Chercher dans le cache des entités — les données de tokens peuvent
        # être stockées dans les métadonnées d'entités scrapées
        entities = self._cache.get("entities", {})
        for slug, entity_data in entities.items():
            if isinstance(entity_data, dict):
                tokens = entity_data.get("tokens", [])
                if isinstance(tokens, list):
                    for t in tokens:
                        t_symbol = (t.get("symbol") or "").lower()
                        t_name = (t.get("name") or "").lower()
                        t_id = t.get("id", t.get("symbol", ""))
                        if t_id not in seen and (query_lower in t_symbol or query_lower in t_name):
                            seen.add(t_id)
                            results.append({
                                "id": t_id,
                                "symbol": t.get("symbol", "").upper(),
                                "name": t.get("name", ""),
                                "contract_address": t.get("contract_address", ""),
                                "market_cap_usd": t.get("market_cap_usd"),
                                "price_usd": t.get("price_usd"),
                            })

        # Chercher aussi dans le holders_cache (les adresses de tokens)
        holders_cache = self._cache.get("holders_cache", {})
        for key in holders_cache:
            if key.startswith("holders:") and query_lower in key.lower():
                token_addr = key.split(":")[-1] if ":" in key else key
                if token_addr not in seen:
                    seen.add(token_addr)
                    results.append({
                        "id": token_addr,
                        "symbol": "",
                        "name": "",
                        "contract_address": token_addr,
                        "market_cap_usd": None,
                        "price_usd": None,
                    })

        return results[:20]

    async def search_coingecko(self, query: str) -> list[dict]:
        """
        Recherche de tokens via l'API CoinGecko gratuite (sans clé API).

        Utilise l'endpoint /search qui ne nécessite pas d'authentification.
        Rate limit: ~30 req/min.

        Retourne une liste de dicts: {id, symbol, name, market_cap_rank, thumb}
        """
        query_stripped = query.strip()
        if not query_stripped:
            return []

        url = f"https://api.coingecko.com/api/v3/search?query={query_stripped}"

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.get(
                    url,
                    headers={"User-Agent": "Hermes/1.0", "Accept": "application/json"},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"[ARKHAM] CoinGecko search HTTP {resp.status}")
                        return []

                    data = await resp.json()
                    coins = data.get("coins", [])

                    results = []
                    for coin in coins[:10]:
                        results.append({
                            "id": coin.get("id", ""),
                            "symbol": coin.get("symbol", "").upper(),
                            "name": coin.get("name", ""),
                            "market_cap_rank": coin.get("market_cap_rank"),
                            "thumb": coin.get("thumb", ""),
                        })

                    return results

        except Exception as e:
            logger.error(f"[ARKHAM] CoinGecko search error: {e}")
            return []

    def get_token_detail(self, symbol: str, chain: str = "ethereum") -> dict:
        """
        Agrège toutes les données disponibles pour un token donné.

        Stratégie en cascade:
        1. Détecter si c'est une chaîne native (BTC, SOL, ETH...)
        2. Cache local Arkham (GRATUIT)
        3. CoinGecko API pour prix, market cap, supply (GRATUIT, 30 req/min)
        4. Etherscan pour contract verification (si clé API)
        5. Données perpétuelles (funding, OI, volume) si disponible

        Retourne un dict complet avec toutes les données trouvées.
        """
        symbol_lower = symbol.lower().strip()
        token_detail_cache = self._cache.setdefault("token_detail_cache", {})
        cache_ttl = 300
        cache_keys = [
            f"token_detail:{chain}:{symbol_lower}",
        ]
        cg_alias = SYMBOL_TO_CG_ID.get(symbol_lower)
        if cg_alias:
            cache_keys.append(f"token_detail:{chain}:{cg_alias.lower()}")

        fresh_cached_result = None
        stale_cached_result = None
        now = time.time()
        for cache_key in cache_keys:
            cache_entry = token_detail_cache.get(cache_key)
            if not isinstance(cache_entry, dict):
                continue
            cached_data = cache_entry.get("data")
            if not isinstance(cached_data, dict):
                continue
            if stale_cached_result is None:
                stale_cached_result = dict(cached_data)
            cache_age = now - float(cache_entry.get("ts", 0) or 0)
            if cache_age <= cache_ttl and (
                cached_data.get("contract_address")
                or cached_data.get("price_usd") is not None
                or cached_data.get("source") not in (None, "", "unknown")
            ):
                fresh_cached_result = dict(cached_data)
                break

        if fresh_cached_result is not None:
            return fresh_cached_result

        # ── 0. Détection chaîne native ──
        native_info = NATIVE_COINS.get(symbol_lower)
        if native_info:
            chain = native_info["chain"]

        result = {
            "symbol": symbol,
            "chain": chain,
            "source": "unknown",
            "is_native": bool(native_info),
            "native_info": native_info,
        }

        # ── 0b. Lookup KNOWN_CONTRACTS (hardcoded, gratuit, pas d'API) ──
        if not result.get("is_native"):
            known_addr = KNOWN_CONTRACTS.get(symbol_lower, {}).get(chain)
            if known_addr:
                result["contract_address"] = known_addr
                result["source"] = "known_contracts"
                result["name"] = symbol.upper()

        # ── 1. Vérifier le cache local ──
        db = get_arkham_db()

        # Pour les natives coins, chercher dans le cache par symbole ou nom
        if result.get("is_native"):
            for slug, data in db._cache.get("entities", {}).items():
                if not isinstance(data, dict):
                    continue
                # Chercher par symbole natif
                if slug == symbol_lower or data.get("name", "").lower() == symbol_lower:
                    tokens = data.get("tokens", [])
                    for t in tokens:
                        if (t.get("symbol") or "").lower() == symbol_lower:
                            result.update({
                                "name": t.get("name", data.get("name", symbol)),
                                "contract_address": None,  # Pas de contrat pour native
                                "price_usd": t.get("price_usd"),
                                "market_cap_usd": t.get("market_cap_usd"),
                                "entity_name": data.get("name"),
                                "source": "cache",
                            })
                            break
                    if result.get("source") == "cache":
                        break
            # Si pas trouvé dans entities, on continue vers CoinGecko
            if not result.get("name"):
                result["name"] = native_info.get("symbol", symbol) if native_info else symbol
        else:
            token_matches = db._cache.get("entities", {}).get(symbol_lower, {})
            if token_matches.get("contract_address"):
                result.update({
                    "name": token_matches.get("name", symbol),
                    "contract_address": token_matches["contract_address"],
                    "price_usd": token_matches.get("price_usd"),
                    "market_cap_usd": token_matches.get("market_cap_usd"),
                    "source": "cache",
                })

        # ── FIX USDT lookup bug ──
        # Si pas de contract mais symbol connu dans KNOWN_CONTRACTS, forcer lookup
        if not result.get("contract_address") and symbol_lower in KNOWN_CONTRACTS:
            chain_map = {
                "ethereum": "eth",
                "bsc": "bsc",
                "arbitrum": "arb",
                "polygon": "poly",
                "optimism": "opt",
                "base": "base",
            }
            chain_key = chain_map.get(chain, chain.lower())
            if chain_key in KNOWN_CONTRACTS.get(symbol_lower, {}):
                ca = KNOWN_CONTRACTS[symbol_lower][chain_key]
                result.update({
                    "contract_address": ca,
                    "name": "Tether USD",
                    "source": "known_contracts",
                })
                if not result.get("price_usd"):
                    # Appel CoinGecko uniquement pour le prix
                    pass

        # Chercher aussi dans les entités par nom (sauf si native coin)
        if not result.get("contract_address") and not result.get("is_native"):
            entities = self._cache.get("entities", {})
            for slug, entity_data in entities.items():
                if isinstance(entity_data, dict):
                    entity_name = entity_data.get("name", "").lower()
                    if symbol_lower in entity_name or symbol_lower == slug:
                        tokens = entity_data.get("tokens", [])
                        for t in tokens:
                            if (t.get("symbol") or "").lower() == symbol_lower:
                                result.update({
                                    "name": t.get("name", entity_data.get("name", "")),
                                    "contract_address": t.get("contract_address", ""),
                                    "price_usd": t.get("price_usd"),
                                    "market_cap_usd": t.get("market_cap_usd"),
                                    "source": "cache",
                                })
                                break
                        if result.get("contract_address"):
                            break

        # ── 2. CoinGecko — prix, market cap, supply ──
        # Pour les natives coins, on appelle toujours CoinGecko pour les data fraîches
        if not result.get("price_usd") or result.get("is_native"):
            try:
                import urllib.request
                import urllib.parse

                # Utiliser l'ID CoinGecko correct
                cg_id = symbol_lower
                if native_info:
                    # Trouver l'ID CoinGecko depuis le symbole natif
                    for cg_key, hl_sym in CG_TO_HYPERLIQUID.items():
                        if hl_sym == (native_info.get("symbol") or symbol).upper():
                            cg_id = cg_key
                            break
                elif symbol_lower in SYMBOL_TO_CG_ID:
                    # ERC-20 tokens: symbole ≠ ID CoinGecko
                    cg_id = SYMBOL_TO_CG_ID[symbol_lower]

                cg_url = f"https://api.coingecko.com/api/v3/coins/{cg_id}"
                params = {
                    "localization": "false",
                    "tickers": "false",
                    "community_data": "false",
                    "developer_data": "false",
                }
                full_url = f"{cg_url}?{urllib.parse.urlencode(params)}"

                req = urllib.request.Request(
                    full_url,
                    headers={"User-Agent": "Hermes/1.0", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    cg_data = json.loads(response.read().decode("utf-8"))

                md = cg_data.get("market_data", {})
                platforms = cg_data.get("platforms", {})

                # Pour les natives coins, forcer le bon symbole
                final_symbol = native_info.get("symbol", symbol).upper() if native_info else (cg_data.get("symbol") or symbol).upper()

                result.update({
                    "name": cg_data.get("name", symbol),
                    "id": cg_data.get("id", cg_id),
                    "symbol": final_symbol,
                    "price_usd": md.get("current_price", {}).get("usd"),
                    "market_cap_usd": md.get("market_cap", {}).get("usd"),
                    "total_supply": md.get("total_supply"),
                    "circulating_supply": md.get("circulating_supply"),
                    "max_supply": md.get("max_supply"),
                    "decimals": None,  # sera rempli depuis detail_platforms plus bas
                    "price_change_24h": md.get("price_change_percentage_24h"),
                    "price_change_7d": md.get("price_change_percentage_7d"),
                    "ath": md.get("ath", {}).get("usd"),
                    "ath_date": md.get("ath_date", {}).get("usd"),
                    "atl": md.get("atl", {}).get("usd"),
                    "atl_date": md.get("atl_date", {}).get("usd"),
                    "volume_24h": md.get("total_volume", {}).get("usd"),
                    "fdv": md.get("fully_diluted_valuation", {}).get("usd"),
                    "market_cap_rank": cg_data.get("market_cap_rank"),
                    "image": cg_data.get("image", {}).get("large", ""),
                    "genesis_date": cg_data.get("genesis_date"),
                    "hashing_algorithm": cg_data.get("hashing_algorithm"),
                    "description": cg_data.get("description", {}).get("en", "")[:500] if cg_data.get("description") else "",
                    "homepage": cg_data.get("links", {}).get("homepage", [""])[0] if cg_data.get("links", {}).get("homepage") else "",
                    "blockchain_site": cg_data.get("links", {}).get("blockchain_site", [""])[0] if cg_data.get("links", {}).get("blockchain_site") else "",
                    "subreddit": cg_data.get("links", {}).get("subreddit_url", ""),
                    "source": "coingecko",
                })

                # Pour les natives coins, pas de contract address
                if not result.get("is_native"):
                    # Trouver l'adresse du contrat sur la chain demandée
                    chain_map = {
                        "ethereum": "ethereum",
                        "bsc": "binance-smart-chain",
                        "arbitrum": "arbitrum-one",
                        "polygon": "polygon-pos",
                        "optimism": "optimistic-ethereum",
                        "avalanche": "avalanche",
                    }
                    cg_chain = chain_map.get(chain, chain)
                    if cg_chain in platforms and not result.get("contract_address"):
                        result["contract_address"] = platforms[cg_chain]
                    # Extraire decimals depuis detail_platforms
                    detail_platforms = cg_data.get("detail_platforms", {})
                    if cg_chain in detail_platforms:
                        dp = detail_platforms[cg_chain]
                        result["decimals"] = dp.get("decimal_place", 18)
                    elif platforms:
                        # fallback: essayer toutes les plateformes
                        for plat, pdata in detail_platforms.items():
                            if pdata.get("decimal_place"):
                                result["decimals"] = pdata["decimal_place"]
                                break

            except Exception as e:
                logger.warning(f"[ARKHAM] CoinGecko detail for {symbol}: {e}")
                if stale_cached_result is not None:
                    stale_cached_result["_cache_stale"] = True
                    return stale_cached_result
                if not result.get("name"):
                    result["name"] = native_info.get("symbol", symbol) if native_info else symbol

        # ── 3. Etherscan — vérification du contrat ──
        if result.get("contract_address"):
            api_key = self._get_api_key_for_chain(chain)
            if api_key:
                api_url = ETHERSCAN_API_URLS.get(chain, ETHERSCAN_API_URLS["ethereum"])
                try:
                    params = {
                        "module": "contract",
                        "action": "getsourcecode",
                        "address": result["contract_address"],
                        "apikey": api_key,
                    }
                    contract_data = self._etherscan_get(api_url, params)
                    if contract_data and contract_data.get("status") == "1":
                        contract_info = contract_data.get("result", [{}])[0]
                        result.update({
                            "contract_name": contract_info.get("ContractName", ""),
                            "compiler_version": contract_info.get("CompilerVersion", ""),
                            "verified": bool(contract_info.get("SourceCode")),
                            "implementation": contract_info.get("Implementation", ""),
                        })
                except Exception as e:
                    logger.warning(f"[ARKHAM] Etherscan contract for {symbol}: {e}")

        if (
            result.get("contract_address")
            or result.get("price_usd") is not None
            or result.get("source") not in (None, "", "unknown")
        ):
            cache_payload = {"ts": time.time(), "data": dict(result)}
            alias_keys = {
                symbol_lower,
                str(result.get("id") or "").lower(),
                str(result.get("symbol") or "").lower(),
            }
            if cg_alias:
                alias_keys.add(cg_alias.lower())
            for alias_key in alias_keys:
                cleaned = str(alias_key or "").strip().lower()
                if cleaned:
                    token_detail_cache[f"token_detail:{chain}:{cleaned}"] = cache_payload
            try:
                self._save_cache()
            except Exception:
                pass

        return result

    def enrich_with_perp_data(self, result: dict) -> dict:
        """
        Enrichit les données d'un token avec les données perpétuelles (funding, OI, volume).

        Utilise les données du collector Hyperliquid et de l'agrégateur multi-exchange.
        """
        symbol = result.get("symbol", "").upper()
        if not symbol:
            return result

        perp_data = {
            "funding_rate": None,
            "funding_rate_binance": None,
            "funding_rate_bybit": None,
            "open_interest": None,
            "volume_24h_perp": None,
            "hyperliquid_price": None,
            "hyperliquid_cvd": None,
            "hyperliquid_oi": None,
        }

        # ── Hyperliquid via collector state ──
        try:
            from services.collector import get_market_snapshot
            # Mapper le symbole vers Hyperliquid
            hl_symbol = symbol
            if symbol == "XAU":
                hl_symbol = None  # XAU pas sur Hyperliquid
            elif symbol == "BTC" or symbol == "ETH" or symbol == "SOL":
                hl_symbol = symbol

            if hl_symbol:
                snapshot = get_market_snapshot(hl_symbol)
                if snapshot:
                    oi_data = snapshot.get("oi")
                    oi_value = oi_data.get("value") if isinstance(oi_data, dict) else oi_data
                    perp_data.update({
                        "hyperliquid_price": snapshot.get("px"),
                        "hyperliquid_cvd": snapshot.get("cvd"),
                        "hyperliquid_oi": oi_value,
                        "open_interest": oi_value,
                        "hyperliquid_best_bid": snapshot.get("best_bid"),
                        "hyperliquid_best_ask": snapshot.get("best_ask"),
                        "hyperliquid_spread": snapshot.get("orderbook", {}).get("spread"),
                    })
        except Exception as e:
            logger.debug(f"[ARKHAM] Hyperliquid perp data for {symbol}: {e}")

        # ── Binance Funding ──
        try:
            from services.multi_exchange import state as aggr_state
            funding = aggr_state.funding_data
            # Chercher le symbole avec suffixe USDT
            for suffix in ["USDT", "USD", ""]:
                key = f"{symbol}{suffix}" if suffix else symbol
                if key in funding:
                    binance_data = funding[key].get("binance")
                    if binance_data:
                        perp_data["funding_rate_binance"] = binance_data.get("rate")
                    bybit_data = funding[key].get("bybit")
                    if bybit_data:
                        perp_data["funding_rate_bybit"] = bybit_data.get("rate")
                    # Prendre le premier disponible
                    perp_data["funding_rate"] = (
                        binance_data.get("rate") if binance_data
                        else bybit_data.get("rate") if bybit_data
                        else None
                    )
                    perp_data["funding_next_time"] = binance_data.get("next_time") if binance_data else None
                    break
        except Exception as e:
            logger.debug(f"[ARKHAM] Multi-exchange funding for {symbol}: {e}")

        # Merge dans le résultat
        result.update(perp_data)
        return result

    def get_token_arkham_flows(self, symbol: str) -> dict:
        """
        Récupère les flows Arkham pour un token spécifique.

        Retourne:
        - entity_balance_changes: changements récents de balance par entité
        - top_flows: plus gros inflows/outflows
        - exchange_flows: flows vers/depuis les exchanges
        """
        symbol_lower = symbol.lower()
        flows = {
            "entity_balance_changes": [],
            "top_inflows": [],
            "top_outflows": [],
            "exchange_flows": [],
            "total_entities_tracked": 0,
        }

        try:
            from services.arkham_tracker import get_arkham_tracker
            tracker = get_arkham_tracker()

            # Récupérer les signaux récents liés à ce token
            all_signals = tracker.get_recent_signals(100)
            token_signals = [
                s for s in all_signals
                if s.get("token", "").lower() == symbol_lower
                or s.get("symbol", "").lower() == symbol_lower
            ]

            # Extraire les flows
            inflows = []
            outflows = []
            exchange_flows = []

            for sig in token_signals:
                sig_type = sig.get("signal_type", "")
                entity = sig.get("entity", "")
                value = sig.get("value_usd", 0)
                timestamp = sig.get("timestamp", 0)

                entry = {
                    "entity": entity,
                    "value_usd": value,
                    "timestamp": timestamp,
                    "signal_type": sig_type,
                    "token": symbol,
                }

                if "DEPOSIT" in sig_type or "INFLOW" in sig_type:
                    inflows.append(entry)
                elif "WITHDRAWAL" in sig_type or "OUTFLOW" in sig_type:
                    outflows.append(entry)

                if "EXCHANGE" in sig_type:
                    exchange_flows.append(entry)

            flows.update({
                "entity_balance_changes": token_signals[:50],
                "top_inflows": sorted(inflows, key=lambda x: x["value_usd"], reverse=True)[:20],
                "top_outflows": sorted(outflows, key=lambda x: x["value_usd"], reverse=True)[:20],
                "exchange_flows": exchange_flows[:20],
                "total_entities_tracked": len(set(s.get("entity") for s in token_signals)),
            })

        except Exception as e:
            logger.debug(f"[ARKHAM] Arkham flows for {symbol}: {e}")

        return flows


    def get_cached_entities(self) -> list[dict]:
        """
        Retourne toutes les entités en cache. AUCUN appel API.

        Returns:
            Liste de toutes les entités cached.
        """
        entities = self._cache.get("entities", {})
        return list(entities.values())

    # =========================================================
    # MÉTHODES BLOCKCHAIN GRATUITES (Etherscan / BSCScan)
    # =========================================================

    def _fetch_blockchain_data(self, address: str, chain: str = "ethereum") -> dict:
        """
        Récupère les données on-chain d'une adresse via les APIs blockchain GRATUITES.

        IMPORTANT: Cette méthode N'utilise JAMAIS Firecrawl.
        Elle utilise Etherscan, BSCScan, etc. (tous gratuits).

        Args:
            address: Adresse blockchain (0x...)
            chain: "ethereum", "bsc", "arbitrum", "polygon", "optimism", "avalanche"

        Returns:
            Dict avec: balance, transactions, tokens, last_updated
        """
        # Normaliser l'adresse
        if not address.startswith("0x"):
            logger.warning(f"[ARKHAM] Adresse invalide: {address}")
            return {"error": "invalid_address", "address": address}

        address = address.lower()

        # Vérifier le cache d'adresses
        cached_addr = self._cache.get("addresses", {}).get(address)
        if cached_addr:
            age = time.time() - cached_addr.get("last_updated", 0)
            if age < 3600:  # Cache 1h pour les données blockchain (plus frais)
                logger.info(f"[ARKHAM] Cache HIT pour données blockchain de {address[:10]}...")
                return cached_addr

        # Choisir l'API selon la chain
        api_url = ETHERSCAN_API_URLS.get(chain, ETHERSCAN_API_URLS["ethereum"])
        chain_id = ETHERSCAN_CHAIN_IDS.get(chain, "1")
        api_key = self._get_api_key_for_chain(chain)

        # BSC: utiliser le RPC officiel Binance (gratuit, illimite)
        if chain == "bsc":
            return self._fetch_bsc_via_rpc(address)

        if not api_key:
            logger.warning(f"[ARKHAM] Pas de clé API pour {chain} — données blockchain limitées")
            return {"error": f"no_api_key_for_{chain}", "address": address, "chain": chain}

        result = {
            "address": address,
            "chain": chain,
            "balance_eth": None,
            "balance_wei": None,
            "transaction_count": None,
            "tokens": [],
            "last_updated": time.time(),
        }

        try:
            # 1. Balance ETH/BNB
            balance_params = {
                "chainid": chain_id,
                "module": "account",
                "action": "balance",
                "address": address,
                "tag": "latest",
                "apikey": api_key,
            }
            balance_data = self._etherscan_get(api_url, balance_params)
            if balance_data and balance_data.get("status") == "1":
                result["balance_wei"] = int(balance_data["result"])
                denom = 1e18
                result["balance_eth"] = result["balance_wei"] / denom

            # 2. Token balances (ERC-20)
            token_params = {
                "chainid": chain_id,
                "module": "account",
                "action": "tokentx",
                "address": address,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": api_key,
            }
            token_data = self._etherscan_get(api_url, token_params)
            if token_data and token_data.get("status") == "1":
                seen_tokens = set()
                for tx in token_data.get("result", [])[:50]:
                    contract = tx.get("contractAddress", "")
                    if contract not in seen_tokens:
                        seen_tokens.add(contract)
                        result["tokens"].append({
                            "symbol": tx.get("tokenSymbol", ""),
                            "name": tx.get("tokenName", ""),
                            "contract": contract,
                        })

            # 3. Transaction count
            tx_count_params = {
                "chainid": chain_id,
                "module": "proxy",
                "action": "eth_getTransactionCount",
                "address": address,
                "tag": "latest",
                "apikey": api_key,
            }
            tx_data = self._etherscan_get(api_url, tx_count_params)
            if tx_data and tx_data.get("result"):
                try:
                    result["transaction_count"] = int(tx_data["result"], 16)
                except (ValueError, TypeError):
                    pass

        except Exception as e:
            logger.error(f"[ARKHAM] Erreur blockchain data pour {address}: {e}")
            result["error"] = str(e)

        # Mettre en cache
        self._cache.setdefault("addresses", {})[address] = result
        self._save_cache()

        logger.info(
            f"[ARKHAM] Blockchain data récupérée pour {address[:10]}... "
            f"sur {chain}: {result.get('transaction_count', '?')} tx, "
            f"{len(result.get('tokens', []))} tokens"
        )

        return result



    def _fetch_bsc_via_rpc(self, address: str) -> dict:
        """Fetch BSC data via official Binance RPC endpoint (free, unlimited)."""
        import urllib.request, json
        
        rpc_url = "https://bsc-dataseed.binance.org/"
        result = {
            "address": address.lower(),
            "chain": "bsc",
            "balance_eth": None,
            "balance_wei": None,
            "transaction_count": None,
            "tokens": [],
            "last_updated": __import__('time').time(),
            "source": "bsc_rpc",
        }
        
        try:
            # 1. Get balance via eth_getBalance
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "latest"],
                "id": 1,
            }).encode('utf-8')
            req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data.get('result'):
                wei = int(data['result'], 16)
                result['balance_wei'] = wei
                result['balance_eth'] = wei / 1e18
        except Exception as e:
            result['balance_error'] = str(e)
        
        try:
            # 2. Get transaction count via eth_getTransactionCount
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_getTransactionCount",
                "params": [address, "latest"],
                "id": 2,
            }).encode('utf-8')
            req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            if data.get('result'):
                result['transaction_count'] = int(data['result'], 16)
        except Exception as e:
            result['tx_count_error'] = str(e)
        
        try:
            # 3. Get BEP-20 token transfers via eth_getLogs (simplified)
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "eth_getLogs",
                "params": [{
                    "fromBlock": "0x0",
                    "toBlock": "latest",
                    "topics": [
                        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                        None,
                        "0x" + address.lower()[2:].zfill(64),
                    ],
                }],
                "id": 3,
            }).encode('utf-8')
            req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            logs = data.get('result', [])
            seen = set()
            for log in logs[:20]:
                addr = log.get('address', '')
                if addr and addr not in seen:
                    seen.add(addr)
                    result['tokens'].append({'contract': addr, 'symbol': '', 'name': ''})
        except Exception:
            pass
        
        # Cache result
        self._cache.setdefault('addresses', {})[address.lower()] = result
        self._save_cache()
        return result
    def _fetch_bsc_via_covalent(self, address: str) -> dict:
        """Fallback BSC data via Covalent GoldRush (free tier)."""
        import urllib.request
        covalent_key = os.getenv("COVALENT_API_KEY", "")
        if not covalent_key:
            return {"error": "no_covalent_key", "address": address, "chain": "bsc"}
        
        result = {
            "address": address.lower(),
            "chain": "bsc",
            "balance_eth": None,
            "balance_wei": None,
            "transaction_count": None,
            "tokens": [],
            "last_updated": __import__('time').time(),
            "source": "covalent_fallback",
        }
        
        try:
            url = f"https://api.covalenthq.com/v1/bsc-mainnet/address/{address}/balances_v2/?key={covalent_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "Hermes/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                d = json.loads(resp.read().decode("utf-8"))
            items = d.get("data", {}).get("items", [])
            for item in items:
                sym = item.get("contract_ticker_symbol", "")
                if sym:
                    result["tokens"].append({
                        "symbol": sym,
                        "name": item.get("contract_name", ""),
                        "contract": item.get("contract_address", ""),
                        "balance": item.get("balance", "0"),
                    })
            if items:
                native = next((i for i in items if not i.get("contract_address")), None)
                if native:
                    result["balance_wei"] = int(native.get("balance", "0"))
                    result["balance_eth"] = result["balance_wei"] / 1e18
        except Exception as e:
            result["error"] = str(e)
        
        return result

    def _fetch_token_holders(self, token_address: str, chain: str = "ethereum") -> list[dict]:
        """
        Récupère les top holders d'un token.

        Stratégie en cascade:
        1. Cache local
        2. Blockscout API (GRATUIT, no key)
        3. Covalent GoldRush (GRATUIT, données exactes)
        4. Etherscan tokenholderlist (peut marcher en free)
        5. Fallback: reconstruction via Transfer events (approximatif)

        Args:
            token_address: Adresse du contrat du token (0x...)
            chain: Blockchain

        Returns:
            Liste de dicts avec: address, balance, percentage
        """
        api_url = ETHERSCAN_API_URLS.get(chain, ETHERSCAN_API_URLS["ethereum"])
        api_key = self._get_api_key_for_chain(chain)

        # Vérifier le cache
        cache_key = f"holders:{chain}:{token_address.lower()}"
        cached = self._check_cache(cache_key)
        if cached is not None and len(cached) > 0:
            logger.info(f"[ARKHAM] Cache HIT pour holders de {token_address[:10]}... ({len(cached)} holders)")
            return cached

        holders = []

        # ── Tiers 1: Blockscout API (GRATUIT, no key needed) ──
        if not holders:
            bs_url = BLOCKSCOUT_API_URLS.get(chain, BLOCKSCOUT_API_URLS.get("ethereum"))
            if bs_url and "graphiql" not in bs_url:  # Skip Avalanche (GraphQL only)
                try:
                    import urllib.request
                    holders_url = f"{bs_url}/tokens/{token_address}/holders"
                    req = urllib.request.Request(
                        holders_url,
                        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        raw = resp.read().decode()
                        bs_data = json.loads(raw)
                        items = bs_data.get("items", [])
                        if not items:
                            logger.debug(f"[ARKHAM] Blockscout returned 0 items for {token_address[:10]}...")
                        for item in items[:100]:
                            addr_obj = item.get("address", {})
                            holders.append({
                                "address": addr_obj.get("hash", ""),
                                "balance": item.get("value", "0"),
                                "percentage": item.get("percentage", None),
                                "is_contract": addr_obj.get("is_contract", False),
                                "ens_domain_name": addr_obj.get("ens_domain_name"),
                                "metadata_tags": (addr_obj.get("metadata") or {}).get("tags", []),
                            })
                        if holders:
                            logger.info(f"[ARKHAM] {len(holders)} holders via Blockscout for {token_address[:10]}...")
                except Exception as e:
                    logger.warning(f"[ARKHAM] Blockscout FAILED for {token_address[:10]}...: {e}")

        # ── Tiers 2: Covalent GoldRush (exact, gratuit) ──
        if self.covalent_api_key and not holders:
            chain_id_map = {
                "ethereum": "1", "bsc": "56", "arbitrum": "42161",
                "polygon": "137", "optimism": "10", "avalanche": "43114",
            }
            chain_id = chain_id_map.get(chain, "1")
            covalent_url = f"https://api.covalenthq.com/v1/{chain_id}/tokens/{token_address}/token_holders/"
            try:
                import urllib.request
                import base64
                auth_str = base64.b64encode(f"{self.covalent_api_key}:".encode()).decode()
                req = urllib.request.Request(
                    covalent_url,
                    headers={
                        "User-Agent": "Hermes/1.0",
                        "Authorization": f"Basic {auth_str}",
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get("data") and data["data"].get("items"):
                        for item in data["data"]["items"][:100]:
                            holders.append({
                                "address": item.get("address", ""),
                                "balance": item.get("balance", "0"),
                                "percentage": item.get("percent_of_total_supply"),
                            })
                        logger.info(f"[ARKHAM] {len(holders)} holders via Covalent pour {token_address[:10]}...")
            except Exception as e:
                logger.debug(f"[ARKHAM] Covalent fallback pour {token_address[:10]}...: {e}")

        # ── Tiers 3: Etherscan tokenholderlist ──
        if not holders and api_key:
            try:
                params = {
                    "module": "token",
                    "action": "tokenholderlist",
                    "contractaddress": token_address,
                    "page": 1,
                    "offset": 100,
                    "apikey": api_key,
                }
                data = self._etherscan_get(api_url, params)
                if data and data.get("status") == "1":
                    for entry in data.get("result", []):
                        holders.append({
                            "address": entry.get("TokenHolderAddress", ""),
                            "balance": entry.get("TokenHolderQuantity", ""),
                        })
                    if holders:
                        logger.info(f"[ARKHAM] {len(holders)} holders via Etherscan pour {token_address[:10]}...")
            except Exception:
                pass

        # ── Tiers 4: Fallback Transfer events ──
        if not holders and api_key:
            logger.info(f"[ARKHAM] Fallback: reconstruction holders via Transfer events pour {token_address[:10]}...")
            try:
                params = {
                    "module": "account",
                    "action": "tokentx",
                    "contractaddress": token_address,
                    "startblock": 0,
                    "endblock": 99999999,
                    "page": 1,
                    "offset": 1000,
                    "sort": "desc",
                    "apikey": api_key,
                }
                data = self._etherscan_get(api_url, params)
                if data and data.get("status") == "1":
                    balance_map = {}
                    for tx in data.get("result", []):
                        to_addr = tx.get("to", "").lower()
                        from_addr = tx.get("from", "").lower()
                        try:
                            value = int(tx.get("tokenValue", "0"))
                        except (ValueError, TypeError):
                            continue
                        if to_addr and to_addr != "0x0000000000000000000000000000000000000000":
                            balance_map[to_addr] = balance_map.get(to_addr, 0) + value
                        if from_addr and from_addr != "0x0000000000000000000000000000000000000000":
                            balance_map[from_addr] = balance_map.get(from_addr, 0) - value
                    for addr, bal in sorted(
                        ((a, b) for a, b in balance_map.items() if b > 0),
                        key=lambda x: x[1],
                        reverse=True,
                    )[:100]:
                        holders.append({"address": addr, "balance": str(bal)})
            except Exception as e:
                logger.error(f"[ARKHAM] Erreur reconstruction holders pour {token_address}: {e}")

        # Mettre en cache
        self._cache.setdefault("holders_cache", {})[cache_key] = holders
        self._save_cache()

        logger.info(f"[ARKHAM] {len(holders)} holders récupérés pour {token_address[:10]}... sur {chain}")
        return holders

    # =========================================================
    # GESTION DU CACHE
    # =========================================================

    def _fetch_token_transfers(self, token_address: str, chain: str = "ethereum", page: int = 1, limit: int = 50) -> list[dict]:
        """
        Récupère les transferts ERC-20 récents d'un token via Blockscout (GRATUIT, no key).
        
        Fallback: Etherscan tokentx (nécessite clé API).
        """
        transfers = []

        # ── Tiers 1: Blockscout API ──
        bs_url = BLOCKSCOUT_API_URLS.get(chain, BLOCKSCOUT_API_URLS.get("ethereum"))
        if bs_url and "graphiql" not in bs_url:
            try:
                import urllib.request
                transfers_url = f"{bs_url}/tokens/{token_address}/transfers"
                
                req = urllib.request.Request(
                    transfers_url,
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    bs_data = json.loads(resp.read().decode())
                    items = bs_data.get("items", [])
                    for item in items[: max(limit, 1)]:
                        from_addr = item.get("from", {})
                        to_addr = item.get("to", {})
                        token = item.get("token", {})
                        transfers.append({
                            "tx_hash": item.get("transaction_hash", ""),
                            "block_number": item.get("block_number"),
                            "timestamp": item.get("timestamp", ""),
                            "from": from_addr.get("hash", ""),
                            "to": to_addr.get("hash", ""),
                            "value": item.get("total", {}).get("value", "0"),
                            "token_name": token.get("name", ""),
                            "token_symbol": token.get("symbol", ""),
                            "token_decimal": str(token.get("decimals", "18")),
                            "method": item.get("method", ""),
                            "transfer_type": item.get("type", ""),
                            "from_is_contract": from_addr.get("is_contract", False),
                            "to_is_contract": to_addr.get("is_contract", False),
                            "from_name": from_addr.get("name"),
                            "to_name": to_addr.get("name"),
                            "from_ens": from_addr.get("ens_domain_name"),
                            "to_ens": to_addr.get("ens_domain_name"),
                            "from_tags": [t.get("name", "") for t in ((from_addr.get("metadata") or {}).get("tags", []))],
                            "to_tags": [t.get("name", "") for t in ((to_addr.get("metadata") or {}).get("tags", []))],
                            "from_metadata_tags": (from_addr.get("metadata") or {}).get("tags", []),
                            "to_metadata_tags": (to_addr.get("metadata") or {}).get("tags", []),
                        })
                    logger.info(f"[ARKHAM] {len(transfers)} transfers via Blockscout for {token_address[:10]}...")
            except Exception as e:
                logger.debug(f"[ARKHAM] Blockscout transfers fallback for {token_address[:10]}...: {e}")

        # ── Tiers 2: Etherscan tokentx (if API key available) ──
        if not transfers:
            api_url = ETHERSCAN_API_URLS.get(chain, ETHERSCAN_API_URLS["ethereum"])
            api_key = self._get_api_key_for_chain(chain)
            if api_key:
                try:
                    params = {
                        "module": "account",
                        "action": "tokentx",
                        "contractaddress": token_address,
                        "startblock": 0,
                        "endblock": 99999999,
                        "page": page,
                        "offset": limit,
                        "sort": "desc",
                        "apikey": api_key,
                    }
                    data = self._etherscan_get(api_url, params)
                    if data and data.get("status") == "1":
                        for tx in data.get("result", []):
                            transfers.append({
                                "tx_hash": tx.get("hash", ""),
                                "block_number": tx.get("blockNumber", ""),
                                "timestamp": int(tx.get("timeStamp", "0")),
                                "from": tx.get("from", ""),
                                "to": tx.get("to", ""),
                                "value": tx.get("value", "0"),
                                "token_name": tx.get("tokenName", ""),
                                "token_symbol": tx.get("tokenSymbol", ""),
                                "token_decimal": tx.get("tokenDecimal", "18"),
                            })
                        logger.info(f"[ARKHAM] {len(transfers)} transfers via Etherscan for {token_address[:10]}...")
                except Exception as e:
                    logger.debug(f"[ARKHAM] Etherscan transfers fallback for {token_address[:10]}...: {e}")

        return transfers


    def _check_cache(self, key: str) -> Any:
        """
        Vérifie si une donnée existe dans le cache.

        Args:
            key: Clé de cache (ex: "entity_search:binance")

        Returns:
            La donnée si elle existe et n'est pas expirée, None sinon.
        """
        # Vérifier dans le cache de recherche
        search_cache = self._cache.get("entities_search_cache", {})
        if key in search_cache:
            return search_cache[key]

        # Vérifier dans le cache de holders
        holders_cache = self._cache.get("holders_cache", {})
        if key in holders_cache:
            return holders_cache[key]

        return None

    def _save_cache(self) -> None:
        """
        Sauvegarde le cache sur disque.
        Crée le répertoire data/arkham/ si nécessaire.
        """
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            # Ajouter timestamp de sauvegarde
            self._cache.setdefault("metadata", {})["last_save"] = time.time()
            CACHE_FILE.write_text(
                json.dumps(self._cache, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[ARKHAM] Erreur sauvegarde cache: {e}")

    def _load_cache(self) -> dict[str, Any]:
        """
        Charge le cache depuis le disque.

        Returns:
            Structure de cache:
            {
              "entities": { "binance": {"name": "Binance", "addresses": [...], ...}, ... },
              "addresses": { "0x123...": {"label": "...", "entity": "...", ...}, ... },
              "metadata": { "firecrawl_credits_used": 12, "last_scrape": 123456, ... },
              "entities_search_cache": { ... },
              "holders_cache": { ... },
              "exchange_wallets": { ... }
            }
        """
        default_cache: dict[str, Any] = {
            "entities": {},
            "addresses": {},
            "metadata": {
                "firecrawl_credits_used": 0,
                "last_scrape": 0,
                "created_at": time.time(),
            },
            "entities_search_cache": {},
            "holders_cache": {},
            "exchange_wallets": None,
        }

        if not CACHE_FILE.exists():
            logger.info("[ARKHAM] Pas de cache existant — création d'un nouveau cache")
            return default_cache

        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            # Fusionner avec le default pour les clés manquantes
            for key, default_val in default_cache.items():
                if key not in data:
                    data[key] = default_val
            return data
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"[ARKHAM] Erreur chargement cache: {e} — nouveau cache créé")
            return default_cache

    def _get_credits_remaining(self) -> int:
        """
        Retourne le nombre de crédits Firecrawl restants.

        Returns:
            Nombre de crédits restants (sur 500).
        """
        used = self._cache.get("metadata", {}).get("firecrawl_credits_used", 0)
        return max(0, FIRECRAWL_MAX_CREDITS - used)

    # =========================================================
    # FIRECRAWL — Dernier recours (coûte des crédits)
    # =========================================================

    async def _use_firecrawl(self, goal: str, url: str) -> dict:
        """
        Utilise l'API Firecrawl /agent pour scraper une page.

        ATTENTION: Chaque appel coûte 1 crédit Firecrawl (500 au total).
        Cette méthode ne doit être appelée QUE si le cache ne contient
        pas la donnée.

        Args:
            goal: Description de ce qu'on veut extraire (pour l'agent Firecrawl)
            url: URL de la page à scraper

        Returns:
            Dict avec les données extraites, ou {} en cas d'erreur.
        """
        # Vérifier les crédits
        remaining = self._get_credits_remaining()
        if remaining <= 0:
            logger.error("[ARKHAM] 🔴 AUCUN crédit Firecrawl restant ! Scraping impossible.")
            return {}

        if remaining <= 50:
            logger.warning(
                f"[ARKHAM] ⚠️ Attention: seulement {remaining} crédits Firecrawl restants !"
            )

        # Rate limiting
        elapsed = time.time() - self._last_request_ts
        if elapsed < MIN_REQUEST_INTERVAL:
            import asyncio

            await asyncio.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_ts = time.time()

        logger.info(f"[ARKHAM] 🔥 Firecrawl: {goal[:60]}... ({remaining - 1} crédits restants après)")

        payload = {
            "goal": goal,
            "url": url,
            "timeout": 90000,  # 90s
        }

        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=150)
            ) as session:
                async with session.post(
                    f"{FIRECRAWL_API_URL}/scrape",
                    headers=self._firecrawl_headers,
                    json=payload,
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()

                        # Format 1: Résultat direct
                        if isinstance(result.get("result"), dict):
                            extracted = result["result"]
                        elif isinstance(result, dict) and "data" in result:
                            extracted = result["data"]
                        else:
                            # Format 2: Async — polling
                            task_id = result.get("id")
                            if task_id:
                                extracted = await self._poll_firecrawl_result(task_id)
                            else:
                                extracted = result

                        # Décrémenter les crédits et sauvegarder
                        self._cache.setdefault("metadata", {})["firecrawl_credits_used"] = (
                            self._cache.get("metadata", {}).get("firecrawl_credits_used", 0) + 1
                        )
                        self._cache["metadata"]["last_scrape"] = time.time()
                        self._save_cache()

                        logger.info(
                            f"[ARKHAM] ✅ Firecrawl succès — "
                            f"{self._get_credits_remaining()} crédits restants"
                        )
                        return extracted if isinstance(extracted, dict) else {}

                    elif resp.status == 429:
                        logger.warning("[ARKHAM] Rate limited par Firecrawl — backoff 30s")
                        import asyncio

                        await asyncio.sleep(30)
                        return {}
                    else:
                        error_text = await resp.text()
                        logger.error(f"[ARKHAM] Firecrawl error {resp.status}: {error_text[:200]}")
                        return {}

        except Exception as e:
            logger.error(f"[ARKHAM] Firecrawl exception: {e}")
            return {}

    async def _poll_firecrawl_result(self, task_id: str, timeout: int = 90) -> dict:
        """
        Poll le résultat d'une tâche Firecrawl asynchrone.

        Args:
            task_id: ID de la tâche Firecrawl
            timeout: Timeout en secondes

        Returns:
            Dict avec les données extraites.
        """
        elapsed = 0
        interval = 5

        while elapsed < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"{FIRECRAWL_API_URL}/scrape/{task_id}",
                        headers=self._firecrawl_headers,
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            status = result.get("status", "")

                            if status == "completed":
                                return result.get("result", result)
                            elif status in ("failed", "error"):
                                logger.error(f"[ARKHAM] Agent Firecrawl échoué: {result.get('error')}")
                                return {}
                            else:
                                import asyncio

                                await asyncio.sleep(interval)
                                elapsed += interval
                        else:
                            import asyncio

                            await asyncio.sleep(interval)
                            elapsed += interval
            except Exception:
                import asyncio

                await asyncio.sleep(interval)
                elapsed += interval

        logger.error(f"[ARKHAM] Poll timeout pour tâche {task_id}")
        return {}

    # =========================================================
    # FIRECRAWL HELPERS — Méthodes de scraping spécifiques
    # =========================================================

    async def _firecrawl_search_entity(self, name: str) -> list[dict]:
        """
        Utilise Firecrawl pour rechercher une entité sur Arkham.

        Args:
            name: Nom de l'entité à rechercher

        Returns:
            Liste d'entités trouvées.
        """
        result = await self._use_firecrawl(
            goal=f"""
            Search for the entity '{name}' on Arkham Intelligence.
            Extract:
            - Full entity name
            - URL slug (e.g., binance, jump-trading)
            - Entity type (exchange, fund, whale, market_maker, defi_protocol, government)
            - Number of identified wallets if shown
            - Total balance in USD if shown
            - Which chains they operate on
            Return ALL matching entities found.
            """,
            url=f"{ARKHAM_BASE}/intelligence",
        )

        entities = []
        if result:
            raw_entities = result.get("entities", result.get("data", []))
            if isinstance(raw_entities, list):
                for e in raw_entities:
                    if isinstance(e, dict):
                        slug = e.get("slug", e.get("name", "").lower().replace(" ", "-"))
                        e["slug"] = slug
                        # Sauvegarder dans le cache d'entités
                        self._cache.setdefault("entities", {})[slug] = {
                            "name": e.get("name", ""),
                            "slug": slug,
                            "type": e.get("type", ""),
                            "category": e.get("category", ""),
                            "balance_usd": e.get("balance_usd"),
                            "wallet_count": e.get("wallet_count"),
                            "chains": e.get("chains", []),
                            "addresses": [],  # Sera rempli par get_entity_addresses
                            "scraped_at": int(time.time()),
                        }
                        entities.append(e)
            elif isinstance(result, dict) and "name" in result:
                # Résultat unique
                slug = result.get("slug", result.get("name", "").lower().replace(" ", "-"))
                result["slug"] = slug
                self._cache.setdefault("entities", {})[slug] = {
                    "name": result.get("name", ""),
                    "slug": slug,
                    "type": result.get("type", ""),
                    "category": result.get("category", ""),
                    "balance_usd": result.get("balance_usd"),
                    "wallet_count": result.get("wallet_count"),
                    "chains": result.get("chains", []),
                    "addresses": [],
                    "scraped_at": int(time.time()),
                }
                entities.append(result)

        self._save_cache()
        return entities

    async def _firecrawl_get_entity_addresses(self, entity_slug: str) -> list[dict]:
        """
        Utilise Firecrawl pour récupérer les adresses wallet d'une entité.

        Args:
            entity_slug: Slug de l'entité (ex: "binance")

        Returns:
            Liste de dicts: {address, chain, label, wallet_type, entity}
        """
        result = await self._use_firecrawl(
            goal=f"""
            Extract ALL identified wallets for entity '{entity_slug}' from this Arkham page.
            For EACH wallet:
            - Full blockchain address (0x... for EVM, bc1... for BTC, etc.)
            - Chain (Ethereum, Bitcoin, Solana, BSC, Arbitrum, Polygon, etc.)
            - Label assigned by Arkham (e.g., "Binance Hot Wallet 7")
            - Wallet type (hot, cold, deposit, withdrawal, trading, treasury, fee, multisig)
            - Current balance in USD if shown

            CRITICAL: Scroll through ALL wallets. Many entities have 50+ wallets.
            Do NOT stop at the first few.
            """,
            url=f"{ARKHAM_BASE}/entity/{entity_slug}",
        )

        addresses = []
        if result:
            raw_wallets = result.get("wallets", result.get("data", []))
            if isinstance(raw_wallets, list):
                for w in raw_wallets:
                    if isinstance(w, dict):
                        addr = w.get("address", "")
                        chain = w.get("chain", "ethereum")

                        # Normaliser l'adresse EVM
                        if addr.startswith("0x"):
                            addr = addr.lower()

                        wallet_entry = {
                            "address": addr,
                            "chain": chain,
                            "label": w.get("label", ""),
                            "wallet_type": w.get("wallet_type", w.get("type", "")),
                            "entity": entity_slug,
                            "balance_usd": w.get("balance_usd"),
                        }

                        addresses.append(wallet_entry)

                        # Indexer par adresse dans le cache
                        self._cache.setdefault("addresses", {})[addr] = {
                            "label": w.get("label", ""),
                            "entity": entity_slug,
                            "chain": chain,
                            "wallet_type": w.get("wallet_type", ""),
                            "balance_usd": w.get("balance_usd"),
                            "last_updated": int(time.time()),
                        }

            elif isinstance(result, dict) and "address" in result:
                # Résultat unique
                addr = result.get("address", "")
                if addr.startswith("0x"):
                    addr = addr.lower()
                wallet_entry = {
                    "address": addr,
                    "chain": result.get("chain", "ethereum"),
                    "label": result.get("label", ""),
                    "wallet_type": result.get("wallet_type", ""),
                    "entity": entity_slug,
                    "balance_usd": result.get("balance_usd"),
                }
                addresses.append(wallet_entry)

        # Mettre à jour l'entité dans le cache
        if entity_slug in self._cache.get("entities", {}):
            self._cache["entities"][entity_slug]["addresses"] = addresses
            self._cache["entities"][entity_slug]["scraped_at"] = int(time.time())

        self._save_cache()

        logger.info(f"[ARKHAM] {len(addresses)} adresses récupérées pour '{entity_slug}'")
        return addresses

    async def _firecrawl_get_exchange_wallets(self) -> dict:
        """
        Utilise Firecrawl pour scraper les wallets des principaux exchanges.
        Stratégie optimisée: scrape les top exchanges en une seule passe.

        Returns:
            Dict {exchange_name: {"addresses": [...], "scraped_at": timestamp}}
        """
        priority_exchanges = [
            "binance", "coinbase", "okx", "bybit", "bitfinex",
            "kraken", "kucoin", "gate-io", "huobi", "mexc",
        ]

        exchange_data = {}

        for slug in priority_exchanges:
            addresses = await self._firecrawl_get_entity_addresses(slug)
            exchange_data[slug] = {
                "addresses": addresses,
                "scraped_at": int(time.time()),
            }
            # Petite pause entre les entités
            import asyncio

            await asyncio.sleep(1)

        # Sauvegarder dans le cache global
        self._cache["exchange_wallets"] = {
            "exchanges": exchange_data,
            "scraped_at": int(time.time()),
        }
        self._save_cache()

        total = sum(len(v.get("addresses", [])) for v in exchange_data.values())
        logger.info(f"[ARKHAM] Exchange wallets: {total} adresses pour {len(exchange_data)} exchanges")
        return self._cache["exchange_wallets"]

    # =========================================================
    # HELPERS INTERNES
    # =========================================================

    def _get_api_key_for_chain(self, chain: str) -> Optional[str]:
        """
        Retourne la clé API appropriée pour la blockchain demandée.

        Args:
            chain: Nom de la blockchain

        Returns:
            Clé API ou None.
        """
        if chain == "bsc":
            return self.bscscan_api_key or os.getenv(BSCSCAN_API_KEY_ENV, "")
        else:
            # Toutes les autres chains EVM utilisent des clés Etherscan
            # (ou des clés spécifiques si configurées)
            return self.etherscan_api_key or os.getenv(ETHERSCAN_API_KEY_ENV, "")

    @staticmethod
    def _etherscan_get(api_url: str, params: dict) -> Optional[dict]:
        """
        Effectue une requête GET synchrone vers l'API Etherscan/BSCScan.

        Args:
            api_url: URL de base de l'API
            params: Paramètres de la requête

        Returns:
            Dict JSON de la réponse, ou None en cas d'erreur.
        """
        import urllib.request
        import urllib.parse

        try:
            query_string = urllib.parse.urlencode(params)
            full_url = f"{api_url}?{query_string}"

            req = urllib.request.Request(
                full_url,
                headers={"User-Agent": "Hermes/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))

        except Exception as e:
            logger.error(f"[ARKHAM] Etherscan GET error: {e}")
            return None

    def _build_exchange_wallets_from_entities(self) -> dict:
        """
        Construit les wallets d'échanges à partir des entités en cache.
        Utilisé quand Firecrawl n'est pas disponible.

        Returns:
            Dict avec les wallets d'échanges trouvés dans le cache.
        """
        exchange_types = {"exchange", "cex"}
        exchanges = {}

        for slug, entity_data in self._cache.get("entities", {}).items():
            entity_type = entity_data.get("type", "").lower()
            if entity_type in exchange_types and entity_data.get("addresses"):
                exchanges[slug] = {
                    "addresses": entity_data["addresses"],
                    "scraped_at": entity_data.get("scraped_at", 0),
                }

        return {
            "exchanges": exchanges,
            "scraped_at": max(
                (v.get("scraped_at", 0) for v in exchanges.values()), default=0
            ),
            "source": "cache_fallback",
        }

    def get_stats(self) -> dict:
        """
        Retourne les statistiques du scraper.

        Returns:
            Dict avec: crédits restants, entités en cache, adresses en cache, etc.
        """
        metadata = self._cache.get("metadata", {})
        entities = self._cache.get("entities", {})
        addresses = self._cache.get("addresses", {})

        return {
            "firecrawl_credits_used": metadata.get("firecrawl_credits_used", 0),
            "firecrawl_credits_remaining": self._get_credits_remaining(),
            "firecrawl_available": self._firecrawl_available,
            "cached_entities": len(entities),
            "cached_addresses": len(addresses),
            "last_scrape": metadata.get("last_scrape", 0),
            "last_scrape_human": (
                datetime.fromtimestamp(metadata.get("last_scrape", 0), tz=timezone.utc).isoformat()
                if metadata.get("last_scrape")
                else None
            ),
            "cache_file_exists": CACHE_FILE.exists(),
            "cache_file_size_kb": round(CACHE_FILE.stat().st_size / 1024, 1) if CACHE_FILE.exists() else 0,
        }


# =========================================================
# INSTANCE GLOBALE
# =========================================================

_scraper_instance: Optional[ArkhamScraper] = None


def get_arkham_scraper() -> ArkhamScraper:
    """
    Récupère ou crée l'instance singleton du scraper.

    Returns:
        Instance de ArkhamScraper.
    """
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = ArkhamScraper()
    return _scraper_instance


# =========================================================
# POINT D'ENTRÉE CLI — Pour tester le scraper manuellement
# =========================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Arkham Intelligence Scraper — Hermes")
    parser.add_argument("--stats", action="store_true", help="Afficher les statistiques du cache")
    parser.add_argument("--search", type=str, help="Rechercher une entité par nom")
    parser.add_argument("--addresses", type=str, help="Récupérer les adresses d'une entité")
    parser.add_argument("--exchanges", action="store_true", help="Récupérer les wallets d'échanges")
    parser.add_argument("--blockchain", type=str, help="Récupérer les données blockchain d'une adresse")
    parser.add_argument("--chain", type=str, default="ethereum", help="Chain pour --blockchain")
    parser.add_argument("--holders", type=str, help="Récupérer les holders d'un token")

    args = parser.parse_args()

    scraper = get_arkham_scraper()

    if args.stats:
        stats = scraper.get_stats()
        print("\n=== Arkham Scraper Stats ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")

    elif args.search:
        results = scraper.search_entity(args.search)
        print(f"\n=== Recherche: '{args.search}' ===")
        print(f"  {len(results)} résultat(s)")
        for r in results:
            print(f"  - {r.get('name', '?')} ({r.get('slug', '?')}) — {r.get('type', '?')}")

    elif args.addresses:
        addrs = scraper.get_entity_addresses(args.addresses)
        print(f"\n=== Adresses: '{args.addresses}' ===")
        print(f"  {len(addrs)} adresse(s)")
        for a in addrs[:20]:
            print(f"  - {a.get('address', '?')[:20]}... ({a.get('chain', '?')}) — {a.get('label', '?')}")

    elif args.exchanges:
        ex_data = scraper.get_exchange_wallets()
        exchanges = ex_data.get("exchanges", {})
        print(f"\n=== Exchange Wallets ===")
        for name, data in exchanges.items():
            n = len(data.get("addresses", []))
            print(f"  {name}: {n} adresse(s)")

    elif args.blockchain:
        data = scraper._fetch_blockchain_data(args.blockchain, args.chain)
        print(f"\n=== Blockchain Data: {args.blockchain[:20]}... ({args.chain}) ===")
        for k, v in data.items():
            if k != "tokens":
                print(f"  {k}: {v}")
            else:
                print(f"  tokens: {len(v)} token(s)")

    elif args.holders:
        holders = scraper._fetch_token_holders(args.holders, args.chain)
        print(f"\n=== Token Holders: {args.holders[:20]}... ({args.chain}) ===")
        print(f"  {len(holders)} holder(s)")
        for h in holders[:10]:
            print(f"  - {h.get('address', '?')[:20]}... — balance: {h.get('balance', '?')}")

    else:
        parser.print_help()
