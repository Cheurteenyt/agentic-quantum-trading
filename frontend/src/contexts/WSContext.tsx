import { createContext, useContext, useState, useEffect, useRef } from "react"

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
    function connect() {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws"
      const host = window.location.port === "5173" ? `${window.location.hostname}:8000` : window.location.host
      const ws = new WebSocket(`${protocol}://${host}/ws`)
      wsRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = e => {
        try { setData(JSON.parse(e.data)) } catch {}
      }
    }
    connect()
    return () => wsRef.current?.close()
  }, [])

  return (
    <WSContext.Provider value={{ data, connected }}>
      {children}
    </WSContext.Provider>
  )
}
