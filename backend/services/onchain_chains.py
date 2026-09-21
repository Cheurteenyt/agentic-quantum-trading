from __future__ import annotations

import os
from typing import Any


BSC_RPC = os.getenv("HERMES_RPC_BSC", "https://bsc-dataseed.binance.org/")
ETH_RPC = os.getenv("HERMES_RPC_ETHEREUM", "https://rpc.flashbots.net")
POLYGON_RPC = os.getenv("HERMES_RPC_POLYGON", "https://polygon-rpc.com")
BASE_RPC = os.getenv("HERMES_RPC_BASE", "https://mainnet.base.org")
ARBITRUM_RPC = os.getenv("HERMES_RPC_ARBITRUM", "https://arb1.arbitrum.io/rpc")
SOL_RPC = os.getenv("HERMES_RPC_SOLANA", "https://api.mainnet-beta.solana.com")

RPC_FALLBACKS = {
    "eth": tuple(
        item.strip()
        for item in os.getenv("HERMES_RPC_ETHEREUM_FALLBACKS", "https://eth.llamarpc.com,https://ethereum.publicnode.com").split(",")
        if item.strip()
    ),
    "bsc": tuple(
        item.strip()
        for item in os.getenv("HERMES_RPC_BSC_FALLBACKS", "https://bsc.publicnode.com,https://bsc-dataseed1.binance.org/").split(",")
        if item.strip()
    ),
    "polygon": tuple(
        item.strip()
        for item in os.getenv("HERMES_RPC_POLYGON_FALLBACKS", "https://polygon.llamarpc.com,https://polygon-bor-rpc.publicnode.com").split(",")
        if item.strip()
    ),
    "base": tuple(
        item.strip()
        for item in os.getenv("HERMES_RPC_BASE_FALLBACKS", "https://base.llamarpc.com,https://base-rpc.publicnode.com").split(",")
        if item.strip()
    ),
    "arbitrum": tuple(
        item.strip()
        for item in os.getenv("HERMES_RPC_ARBITRUM_FALLBACKS", "https://arbitrum.llamarpc.com,https://arbitrum-one-rpc.publicnode.com").split(",")
        if item.strip()
    ),
}

MAJOR_TOKENS: dict[str, dict[str, Any]] = {
    "bsc": {
        "0xe9e7cea3dedca5984780bafc599bd69add087d56": {"coin_id": "busd", "decimals": 18},
        "0x55d398326f99059ff775485246999027b3197955": {"coin_id": "tether", "decimals": 18},
        "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": {"coin_id": "usd-coin", "decimals": 18},
        "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": {"coin_id": "binancecoin", "decimals": 18},
        "0x2170ed0880ac9a755fd29b2688956bd959f933f8": {"coin_id": "ethereum", "decimals": 18},
    },
    "eth": {
        "0xdac17f958d2ee523a2206206994597c13d831ec7": {"coin_id": "tether", "decimals": 6},
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"coin_id": "usd-coin", "decimals": 6},
        "0x6b175474e89094c44da98b954eedeac495271d0f": {"coin_id": "dai", "decimals": 18},
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": {"coin_id": "ethereum", "decimals": 18},
    },
    "polygon": {
        "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": {"coin_id": "usd-coin", "decimals": 6},
        "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": {"coin_id": "tether", "decimals": 6},
        "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": {"coin_id": "ethereum", "decimals": 18},
        "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270": {"coin_id": "matic-network", "decimals": 18},
    },
    "base": {
        "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": {"coin_id": "usd-coin", "decimals": 6},
        "0x4200000000000000000000000000000000000006": {"coin_id": "ethereum", "decimals": 18},
    },
    "arbitrum": {
        "0xaf88d065e77c8cc2239327c5edb3a432268e5831": {"coin_id": "usd-coin", "decimals": 6},
        "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": {"coin_id": "tether", "decimals": 6},
        "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": {"coin_id": "ethereum", "decimals": 18},
    },
}

CHAIN_ALIASES = {
    "ethereum": "eth",
    "eth": "eth",
    "bsc": "bsc",
    "bnb": "bsc",
    "binance": "bsc",
    "polygon": "polygon",
    "matic": "polygon",
    "base": "base",
    "arbitrum": "arbitrum",
    "arbitrum_one": "arbitrum",
}

NATIVE_COIN_IDS = {
    "eth": "ethereum",
    "bsc": "binancecoin",
    "polygon": "matic-network",
    "base": "ethereum",
    "arbitrum": "ethereum",
}


def normalize_chain(chain: str) -> str:
    return CHAIN_ALIASES.get((chain or "").strip().lower(), (chain or "").strip().lower())


def evm_rpc_url(chain: str) -> str:
    normalized = normalize_chain(chain)
    if normalized == "bsc":
        return BSC_RPC
    if normalized == "eth":
        return ETH_RPC
    if normalized == "polygon":
        return POLYGON_RPC
    if normalized == "base":
        return BASE_RPC
    if normalized == "arbitrum":
        return ARBITRUM_RPC
    raise ValueError(f"unsupported_evm_chain:{chain}")


def evm_rpc_urls(chain: str) -> list[str]:
    normalized = normalize_chain(chain)
    primary = evm_rpc_url(normalized)
    urls: list[str] = []
    for url in (primary, *RPC_FALLBACKS.get(normalized, ())):
        if url and url not in urls:
            urls.append(url)
    return urls


def rpc_source_label(url: str) -> str:
    if not url:
        return "missing"
    lowered = url.lower()
    if "alchemy" in lowered:
        return "alchemy"
    if "infura" in lowered:
        return "infura"
    if "quicknode" in lowered:
        return "quicknode"
    if "llamarpc" in lowered:
        return "llamarpc"
    if "flashbots" in lowered:
        return "flashbots"
    if "binance" in lowered or "bsc-dataseed" in lowered:
        return "binance_public_rpc"
    if "solana" in lowered:
        return "solana_public_rpc"
    return "custom_rpc"
