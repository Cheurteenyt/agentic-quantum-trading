/**
 * Hooks — Custom React hooks for Hermes Trading Dashboard
 */

// useWebSocket — TODO: implement WebSocket hook
// export { useWebSocket } from "./useWebSocket"
// export type { WSOptions } from "./useWebSocket"

export { useMarketData, usePrice } from "./useMarketData"
export type { MarketSymbol, MarketData } from "./useMarketData"

export { useSignals } from "./useSignals"
export type { Signal } from "./useSignals"

export { useIntelFeed } from "./useIntelFeed"
export type { Investigation } from "./useIntelFeed"

export { useTerminal } from "./useTerminal"
export type { TerminalLine } from "./useTerminal"
