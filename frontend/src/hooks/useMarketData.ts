import { useState, useEffect } from "react"

export interface MarketSymbol {
  symbol: string
  name: string
  price: number
  change24h: number
  volume?: number
}

export interface MarketData {
  hyperliquid?: Record<string, any>  // BTC, ETH, SOL...
  xauusd?: { bid: number; ask: number; high: number; low: number }
  btc?: { px: number; vol24h: number }
  xau?: { bid: number; ask: number }
  [key: string]: any  // Allow dynamic symbol access
}

/**
 * useMarketData — Filtre les données marché par symbole (BTC, XAU, ETH...)
 */
export function useMarketData(symbol?: string) {
  const [data, setData] = useState<MarketData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Polling fallback si WebSocket déconnecté
    const fetchLatest = async () => {
      try {
        const res = await fetch(`http://${window.location.hostname}:8000/api/market/snapshot`)
        if (res.ok) {
          const snapshot = await res.json()
          setData(snapshot)
        } else {
          // Le `setLoading(false)` était DANS le `if (res.ok)` : sur un 401
          // (cookie de session absent) ou un 500, `loading` restait vrai
          // POUR TOUJOURS et l'interface tournait indéfiniment, sans
          // message. `loading` décrit « une requête est en cours », pas
          // « les données sont arrivées » : il doit retomber quoi qu'il
          // arrive.
          console.error(`Snapshot marché : HTTP ${res.status}`)
        }
      } catch (err) {
        console.error("Failed to fetch market snapshot:", err)
      } finally {
        setLoading(false)
      }
    }

    fetchLatest()
    const interval = setInterval(fetchLatest, 5000) // Refresh toutes les 5s

    return () => clearInterval(interval)
  }, [])

  // Retourne toutes les données ou filtre par symbole
  const filtered = symbol
    ? data?.hyperliquid?.[symbol] || data?.[symbol.toLowerCase()]
    : data

  return {
    data: filtered,
    allData: data,
    loading,
  }
}

/**
 * usePrice — Hook simplifié pour suivre le prix d'un seul actif
 */
export function usePrice(symbol: string): { price: number | null; change: number | null } {
  const { data } = useMarketData(symbol)
  
  let price: number | null = null
  let change: number | null = null

  if (data) {
    price = typeof data === "number" ? data : data.px ?? data.bid ?? data.price ?? null
    change = data.change24h ?? data.change ?? null
  }

  return { price, change }
}
