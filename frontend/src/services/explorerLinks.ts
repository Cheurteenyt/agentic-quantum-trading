const EXPLORER_MAP: Record<string, { address: string; tx: string; token?: string }> = {
  ethereum: {
    address: "https://etherscan.io/address/",
    tx: "https://etherscan.io/tx/",
    token: "https://etherscan.io/token/",
  },
  base: {
    address: "https://basescan.org/address/",
    tx: "https://basescan.org/tx/",
    token: "https://basescan.org/token/",
  },
  arbitrum: {
    address: "https://arbiscan.io/address/",
    tx: "https://arbiscan.io/tx/",
    token: "https://arbiscan.io/token/",
  },
  bsc: {
    address: "https://bscscan.com/address/",
    tx: "https://bscscan.com/tx/",
    token: "https://bscscan.com/token/",
  },
  polygon: {
    address: "https://polygonscan.com/address/",
    tx: "https://polygonscan.com/tx/",
    token: "https://polygonscan.com/token/",
  },
  avalanche: {
    address: "https://snowtrace.io/address/",
    tx: "https://snowtrace.io/tx/",
    token: "https://snowtrace.io/token/",
  },
  optimism: {
    address: "https://optimistic.etherscan.io/address/",
    tx: "https://optimistic.etherscan.io/tx/",
    token: "https://optimistic.etherscan.io/token/",
  },
  solana: {
    address: "https://solscan.io/account/",
    tx: "https://solscan.io/tx/",
  },
  tron: {
    address: "https://tronscan.org/#/address/",
    tx: "https://tronscan.org/#/transaction/",
  },
  bitcoin: {
    address: "https://www.blockchain.com/explorer/addresses/btc/",
    tx: "https://www.blockchain.com/explorer/transactions/btc/",
  },
}

const CANONICAL_TOKEN_CHAIN: Record<string, string> = {
  // Ethereum canonical contracts. If an upstream wallet source mis-tags these as BSC,
  // prefer the chain where the contract is actually meaningful for explorer clicks.
  "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "ethereum", // WETH
  "0xdac17f958d2ee523a2206206994597c13d831ec7": "ethereum", // USDT
  "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "ethereum", // USDC
  "0x6b175474e89094c44da98b954eedeac495271d0f": "ethereum", // DAI
  "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "ethereum", // WBTC
  "0x514910771af9ca656af840dff83e8264ecf986ca": "ethereum", // LINK
  "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": "ethereum", // SHIB
}

export function normalizeExplorerChain(chain?: string | null): string {
  const value = String(chain || "").toLowerCase().trim()
  if (!value) return "ethereum"
  if (value === "eth") return "ethereum"
  if (value === "erc20") return "ethereum"
  if (value === "mainnet") return "ethereum"
  if (value === "bnb" || value === "binance-smart-chain" || value === "binance smart chain") return "bsc"
  if (value === "avax" || value === "avalanche-c-chain" || value === "avalanchec") return "avalanche"
  if (value === "matic") return "polygon"
  if (value === "arb") return "arbitrum"
  if (value === "op") return "optimism"
  if (value === "btc") return "bitcoin"
  if (value === "trx") return "tron"
  if (value === "sol") return "solana"
  if (value.includes("ethereum")) return "ethereum"
  if (value.includes("base")) return "base"
  if (value.includes("arbitrum")) return "arbitrum"
  if (value.includes("bsc")) return "bsc"
  if (value.includes("polygon")) return "polygon"
  if (value.includes("avalanche")) return "avalanche"
  if (value.includes("optimism")) return "optimism"
  if (value.includes("solana")) return "solana"
  if (value.includes("bitcoin")) return "bitcoin"
  if (value.includes("tron")) return "tron"
  return value
}

export function resolveExplorerTokenChain(address?: string | null, chain?: string | null): string {
  const tokenAddress = String(address || "").toLowerCase().trim()
  return CANONICAL_TOKEN_CHAIN[tokenAddress] || normalizeExplorerChain(chain)
}

export function getExplorerAddressUrl(address?: string | null, chain?: string | null): string | null {
  const normalized = normalizeExplorerChain(chain)
  const base = EXPLORER_MAP[normalized]
  if (!address || !base?.address) return null
  return `${base.address}${address}`
}

export function getExplorerTxUrl(txHash?: string | null, chain?: string | null): string | null {
  const normalized = normalizeExplorerChain(chain)
  const base = EXPLORER_MAP[normalized]
  if (!txHash || !base?.tx) return null
  return `${base.tx}${txHash}`
}

export function getExplorerTokenUrl(address?: string | null, chain?: string | null): string | null {
  const normalized = resolveExplorerTokenChain(address, chain)
  const base = EXPLORER_MAP[normalized]
  if (!address || !base?.token) return null
  return `${base.token}${address}`
}
