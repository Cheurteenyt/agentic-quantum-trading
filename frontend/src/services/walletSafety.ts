export const DANGEROUS_WALLET_METHODS = new Set([
  "eth_sendTransaction",
  "eth_signTransaction",
  "eth_signTypedData",
  "eth_signTypedData_v3",
  "eth_signTypedData_v4",
  "wallet_sendCalls",
  "wallet_addEthereumChain",
  "wallet_switchEthereumChain",
  "wallet_watchAsset",
  "solana_signTransaction",
  "solana_signAllTransactions",
])

export const READ_ONLY_WALLET_METHODS = new Set([
  "eth_accounts",
  "eth_requestAccounts",
  "eth_chainId",
  "eth_getBalance",
  "personal_sign",
])

type WalletRequest = {
  method: string
  params?: unknown[]
}

export async function safeWalletRequest<T = unknown>(provider: any, request: WalletRequest): Promise<T> {
  if (!provider?.request) {
    throw new Error("Wallet provider is unavailable.")
  }
  if (DANGEROUS_WALLET_METHODS.has(request.method)) {
    throw new Error(`Blocked unsafe wallet method: ${request.method}`)
  }
  if (!READ_ONLY_WALLET_METHODS.has(request.method)) {
    throw new Error(`Wallet method is not allowlisted: ${request.method}`)
  }
  return provider.request(request) as Promise<T>
}
