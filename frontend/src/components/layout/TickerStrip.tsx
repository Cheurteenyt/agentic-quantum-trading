import { useMarket } from "../../contexts/WSContext"
import { useState, useEffect } from "react"
import LogoAvatar from "../LogoAvatar"

// =========================================================
// TICKER STRIP — Scrolling Entity Cards (ARK-style)
// Données dynamiques depuis WebSocket + fallback API Arkham
// (plus de données statiques hardcodées)
// =========================================================

interface TickerEntity {
  name: string
  symbol: string
  balance: string
  change: number | null
  entityId: string
}

interface TickerStripProps {
  onEntitySelect?: (entityId: string) => void
}

export default function TickerStrip({ onEntitySelect }: TickerStripProps) {
  const { data } = useMarket()
  const [arkhamEntities, setArkhamEntities] = useState<TickerEntity[]>([])

  // ── Build entities from WS data ──
  const wsEntities: TickerEntity[] = []

  // Hyperliquid data
  if (data?.hyperliquid) {
    for (const [symbol, info] of Object.entries(data.hyperliquid) as [string, any][]) {
      if (info?.px) {
        wsEntities.push({
          name: symbol,
          symbol,
          balance: `$${Math.round(info.px).toLocaleString()}`,
          change: info.change_24h ?? null,
          entityId: `hl_${symbol}`,
        })
      }
    }
  }

  // XAU
  if (data?.xauusd?.bid) {
    wsEntities.push({
      name: "XAU/USD",
      symbol: "XAU",
      balance: `$${parseFloat(data.xauusd.bid).toFixed(2)}`,
      change: data.xauusd.change_24h ?? null,
      entityId: "xau_usd",
    })
  }

  // ── Fetch Arkham top entities once ──
  useEffect(() => {
    const host = window.location.hostname
    fetch(`http://${host}:8000/api/arkham/top-entities?limit=8`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.entities) {
          const mapped: TickerEntity[] = data.entities.map((e: any) => ({
            name: e.name || e.label,
            symbol: (e.name || e.label).slice(0, 2).toUpperCase(),
            balance: e.total_balance ? `$${e.total_balance.toLocaleString()}` : "—",
            change: e.change_24h ?? null,
            entityId: e.id || `arkham_${e.name}`,
          }))
          setArkhamEntities(mapped)
        }
      })
      .catch(() => {})  // Silently fail — WS data still available
  }, [])

  // Merge: WS data first (real-time), then Arkham entities (enrichment)
  const entities = [...wsEntities, ...arkhamEntities]

  if (entities.length === 0) return null

  // Double the list for seamless infinite scroll
  const doubled = [...entities, ...entities]

  return (
    <div className="ticker-strip">
      <div className="ticker-track">
        {doubled.map((e, i) => (
          <div
            className="ticker-chip clickable"
            key={`${e.symbol}-${i}`}
            onClick={() => onEntitySelect?.(e.entityId)}
            title={`View ${e.name} detail`}
          >
            <span className="ticker-chip-name-group">
              <LogoAvatar name={e.name} symbol={e.symbol} size={16} square />
              <span className="ticker-chip-name">{e.name}</span>
            </span>
            <span className="ticker-chip-price">{e.balance}</span>
            {e.change != null && (
              <span className={`ticker-chip-change ${e.change >= 0 ? "positive" : "negative"}`}>
                {e.change >= 0 ? "+" : ""}{e.change.toFixed(2)}%
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
