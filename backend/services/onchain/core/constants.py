"""Stable on-chain constants shared by extracted Core Equity modules."""

from __future__ import annotations

SUPPORTED_EVM_CHAINS = ("eth", "bsc", "polygon", "base", "arbitrum")

NATIVE_UNITS = {
    "eth": "ETH",
    "bsc": "BNB",
    "polygon": "MATIC",
    "base": "ETH",
    "arbitrum": "ETH",
}

SWAP_TOPIC = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
PAIR_CREATED_TOPIC = "0x0d3648bd0f6ba80134a33ba9275ac585d9d315f0ad8355cddefde31afa28d0e9"
GET_RESERVES_SELECTOR = "0x0902f1ac"

BLOCKSCOUT_API_BASE_URLS = {
    "eth": "https://eth.blockscout.com/api/v2",
    "bsc": "https://bsc.blockscout.com/api/v2",
    "polygon": "https://polygon.blockscout.com/api/v2",
    "base": "https://base.blockscout.com/api/v2",
    "arbitrum": "https://arbitrum.blockscout.com/api/v2",
}

SQD_PORTAL_DATASET_URLS = {
    "bsc": "https://portal.sqd.dev/datasets/binance-mainnet/stream",
    "eth": "https://portal.sqd.dev/datasets/ethereum-mainnet/stream",
    "polygon": "https://portal.sqd.dev/datasets/polygon-mainnet/stream",
    "base": "https://portal.sqd.dev/datasets/base-mainnet/stream",
    "arbitrum": "https://portal.sqd.dev/datasets/arbitrum-one/stream",
}
