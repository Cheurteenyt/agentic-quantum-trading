import { createContext, useContext, useState, useEffect, useRef } from "react"
import { WS_ROOT } from "../services/api"

// =========================================================
// WEBSOCKET CONTEXT — shared across all pages & components
// =========================================================

interface MarketData {
  type: string
  ts: number
  hyperliquid?: Record<string, any>
  binance?: Record<string, any>
  xauusd?: any
  account?: any
  positions?: any
  recent_signals?: any[]
  funding?: any
  top_gainers?: any
  oi?: any
  opportunities?: any[]
}

interface WSCtx {
  data: MarketData | null
  connected: boolean
}

const WSContext = createContext<WSCtx>({ data: null, connected: false })

export const useMarket = () => useContext(WSContext)

export function WSProvider({ children }: { children: React.ReactNode }) {
  const [data, setData] = useState<MarketData | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    // r7 : le cleanup appelait `close()` — qui déclenche `onclose` — qui
    // re-programmait `setTimeout(connect, 3000)` JAMAIS annulé : après un
    // démontage (navigation SPA, HMR, StrictMode double-mount), un
    // WebSocket zombie était recréé toutes les 3 s sur un composant mort,
    // indéfiniment. Flag `disposed` + timer annulé dans le cleanup.
    let disposed = false
    let retry: ReturnType<typeof setTimeout> | undefined

    function connect() {
      if (disposed) return
      const ws = new WebSocket(`${WS_ROOT}/ws`)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        if (!disposed) retry = setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = e => {
        try { setData(JSON.parse(e.data)) } catch {}
      }
    }
    connect()
    return () => {
      disposed = true
      if (retry) clearTimeout(retry)
      wsRef.current?.close()
    }
  }, [])

  return (
    <WSContext.Provider value={{ data, connected }}>
      {children}
    </WSContext.Provider>
  )
}
