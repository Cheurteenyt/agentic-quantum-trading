import { apiRequest } from "./api"

export interface MarketSymbol {
  symbol: string
  name: string
  price: number
  change24h: number
  volume?: number
  lastUpdate: number
}

export interface AccountInfo {
  balance: number
  equity: number
  margin: number
  freeMargin: number
  profit: number
  leverage: number
  currency: string
  source: string
}

export interface Position {
  ticket: number
  symbol: string
  type: "BUY" | "SELL"
  volume: number
  openPrice: number
  currentPrice: number
  sl: number
  tp: number
  profit: number
  openTime: string
}

/**
 * Market Service — Appels API marché (prix, positions, metrics)
 */
export const marketService = {
  /** Récupérer le snapshot complet du marché */
  getSnapshot: () => 
    apiRequest.get<any>("/market/snapshot"),

  /** Liste des symboles disponibles */
  getSymbols: () =>
    apiRequest.get<MarketSymbol[]>("/market/symbols"),

  /** Détail d'un symbole spécifique */
  getSymbol: (symbol: string) =>
    apiRequest.get<MarketSymbol>(`/market/symbols/${symbol}`),

  // === MT5 / PUPrime ===
  getMT5Account: () =>
    apiRequest.get<AccountInfo>("/market/mt5/account"),

  getMT5Positions: () =>
    apiRequest.get<{ positions: Position[] }>("/market/mt5/positions"),

  closeMT5Position: (ticket: number) =>
    apiRequest.post<{ success: boolean }>(`/market/mt5/positions/${ticket}/close`, {}),

  // === Smart Stats (Order Flow Imbalance) ===
  getSmartStats: (symbol: string) =>
    apiRequest.get<any>(`/market/smart-stats/${symbol}`),

  /** Historique des prix */
  getPriceHistory: (symbol: string, timeframe: string = "1h", limit: number = 100) =>
    apiRequest.get<any[]>(`/market/history/${symbol}?timeframe=${timeframe}&limit=${limit}`),

  /** Orderbook depth */
  getOrderBook: (symbol: string, depth: number = 20) =>
    apiRequest.get<any>(`/market/orderbook/${symbol}?depth=${depth}`),
}
