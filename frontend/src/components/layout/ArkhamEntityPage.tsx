import { useState, useEffect, useCallback } from "react"
import EntityExplorerSection from "./EntityExplorerSection"
import LogoAvatar from "../LogoAvatar"
import { getExplorerAddressUrl, getExplorerTokenUrl, getExplorerTxUrl, normalizeExplorerChain } from "../../services/explorerLinks"

// =========================================================
// ARKHAM ENTITY PAGE — Full overlay inspired by arkham.com
// Supports: tokens, addresses, entities
// NEW: perp data, entity flows, multi-chain holders/transfers
// =========================================================

const API = `http://${window.location.hostname}:8000/api`

/* ── Types ── */

interface HolderData {
  address: string
  balance: string | number
  percentage?: number | null
  human_balance?: number | null
  value_usd?: number | null
  arkham_label?: string | null
  arkham_entity?: string | null
  wallet_type?: string | null
  wallet_flags?: string[]
  wallet_tags?: string[]
  fresh_wallet_candidate?: boolean | null
}

interface TransferData {
  tx_hash: string
  timestamp: number | string
  from: string
  to: string
  value: string
  token_symbol: string
  token_decimal: string
  token_name?: string
  human_value?: number | null
  value_usd?: number | null
  method?: string | null
  transfer_type?: string | null
  from_wallet_type?: string | null
  to_wallet_type?: string | null
  from_label?: string | null
  from_entity?: string | null
  to_label?: string | null
  to_entity?: string | null
}

type MetricValue = number | { value?: number | null; ts?: number | null } | null

interface PerpData {
  funding_rate: number | null
  funding_rate_binance: number | null
  funding_rate_bybit: number | null
  funding_next_time: number | null
  open_interest: MetricValue
  volume_24h_perp: number | null
  hyperliquid_price: number | null
  hyperliquid_cvd: number | null
  hyperliquid_oi: MetricValue
  hyperliquid_best_bid: number | null
  hyperliquid_best_ask: number | null
  hyperliquid_spread: number | null
}

interface ArkhamFlow {
  entity_balance_changes?: Array<{ entity: string; change: number; direction: string; timestamp?: number }>
  top_inflows?: Array<{ entity: string; amount: number; timestamp?: number }>
  top_outflows?: Array<{ entity: string; amount: number; timestamp?: number }>
  exchange_flows?: Array<{ exchange: string; net: number; inflow: number; outflow: number }>
  total_entities_tracked?: number
}

interface TokenDetail {
  symbol: string
  name: string
  contract_address: string
  chain: string
  source?: string | null
  price_usd: number | null
  market_cap_usd: number | null
  volume_24h?: number | null
  fdv?: number | null
  total_supply: number | null
  circulating_supply: number | null
  max_supply: number | null
  price_change_24h: number | null
  price_change_7d: number | null
  ath: number | null
  ath_date: string | null
  image: string
  holders?: HolderData[]
  holders_count?: number
  holders_note?: string
  // Perp data
  funding_rate: number | null
  funding_rate_binance: number | null
  funding_rate_bybit: number | null
  funding_next_time: number | null
  open_interest: MetricValue
  volume_24h_perp: number | null
  hyperliquid_price: number | null
  hyperliquid_cvd: number | null
  hyperliquid_oi: MetricValue
  hyperliquid_best_bid: number | null
  hyperliquid_best_ask: number | null
  hyperliquid_spread: number | null
  // Arkham flows
  arkham_flows: ArkhamFlow
  // Native coin flag
  is_native?: boolean
}

interface EntityActivityProfile {
  transactions_count?: number | null
  token_transfers_count?: number | null
  activity_bucket?: string | null
  fresh_wallet_candidate?: boolean
  fresh_wallet_note?: string | null
}

interface EntityObservedToken {
  symbol: string
  name: string
  chain: string
  contract_address: string
  human_balance_total?: number | null
  wallet_count?: number
  estimated_value_usd?: number | null
  price_usd?: number | null
  stablecoin?: boolean
  labels?: string[]
}

interface EntityObservedWalletToken {
  symbol: string
  name: string
  chain: string
  contract_address: string
  human_balance?: number | null
  value_usd?: number | null
  percentage?: number | null
}

interface EntityObservedWallet {
  address: string
  chain?: string
  label?: string
  entity?: string
  confidence?: string
  flags?: string[]
  matched_tags?: string[]
  token_symbols?: string[]
  observed_value_usd?: number | null
  activity_profile?: EntityActivityProfile | null
  observed_tokens?: EntityObservedWalletToken[]
  observed_token_count?: number
}

interface EntityActivity {
  tx_hash: string
  timestamp?: number | null
  direction: "inflow" | "outflow" | "internal" | string
  token_symbol?: string
  token_name?: string
  chain?: string
  amount?: number | null
  value_usd?: number | null
  wallet_label?: string | null
  counterparty_label?: string | null
  counterparty_address?: string | null
}

interface EntityCounterparty {
  label: string
  address?: string | null
  tx_count?: number
  inflow_count?: number
  outflow_count?: number
  value_usd?: number | null
}

interface EntityCoverage {
  snapshots_scanned?: number
  holder_rows_scanned?: number
  observed_wallets?: number
  observed_tokens?: number
  recent_activity_count?: number
  coverage_note?: string
}

interface EntityIntelligence {
  coverage?: EntityCoverage
  chains?: Array<{ chain: string; hits: number }>
  top_tags?: Array<{ tag: string; count: number }>
  observed_holdings?: EntityObservedToken[]
  wallets?: EntityObservedWallet[]
  recent_activity?: EntityActivity[]
  counterparties?: EntityCounterparty[]
  estimated_total_value_usd?: number | null
}

interface EntityDetail {
  entity?: {
    name?: string
    slug?: string
    type?: string
    category?: string
    balance_usd?: number | null
    wallet_count?: number | null
    chains?: string[]
    source?: string
  } | null
  wallets?: EntityObservedWallet[]
  wallets_count?: number
  flow?: {
    net_flow?: number | null
    inflow?: number | null
    outflow?: number | null
    tx_count?: number | null
  } | null
  intelligence?: EntityIntelligence | null
  snapshot_status?: string | null
  snapshot_retry_after_seconds?: number | null
}

interface ArkhamEntityPageProps {
  entityId: string | null
  onClose: () => void
}

/* ── Helpers ── */

const formatUsd = (v: number | string | null | undefined): string => {
  if (v == null) return "—"
  const num = typeof v === "string" ? parseFloat(v.replace(/[^0-9.-]/g, "")) : v
  if (isNaN(num)) return String(v)
  if (num >= 1e12) return `$${(num / 1e12).toFixed(2)}T`
  if (num >= 1e9) return `$${(num / 1e9).toFixed(2)}B`
  if (num >= 1e6) return `$${(num / 1e6).toFixed(2)}M`
  if (num >= 1e3) return `$${(num / 1e3).toFixed(1)}K`
  return `$${num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const formatNum = (v: number | null | undefined, decimals = 0): string => {
  if (v == null) return "—"
  return v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

const formatPct = (v: number | null | undefined, decimals = 2): string => {
  if (v == null) return "—"
  const sign = v >= 0 ? "+" : ""
  return `${sign}${v.toFixed(decimals)}%`
}

const entityDataScore = (data: any): number => {
  if (!data || data.error) return -1
  const intelligence = data.intelligence || {}
  const coverage = intelligence.coverage || {}
  const holdings = intelligence.observed_holdings || data.portfolio?.top_holdings || []
  const wallets = intelligence.wallets || data.wallets || []
  const activity = intelligence.recent_activity || []
  const counterparties = intelligence.counterparties || []
  const surfaces = intelligence.surfaces || {}
  return (
    (coverage.observed_tokens || holdings.length || 0) * 4 +
    (coverage.observed_wallets || data.wallets_count || wallets.length || 0) * 3 +
    (coverage.recent_activity_count || activity.length || 0) * 2 +
    (counterparties.length || 0) * 2 +
    Object.keys(surfaces).length
  )
}

const metricNumber = (value: MetricValue | undefined): number | null => {
  if (value == null) return null
  if (typeof value === "number") return Number.isFinite(value) ? value : null
  if (typeof value === "object" && typeof value.value === "number") {
    return Number.isFinite(value.value) ? value.value : null
  }
  return null
}

const activityUnixTs = (ts: number | string | null | undefined): number | null => {
  if (ts == null) return null
  if (typeof ts === "number") return Number.isFinite(ts) ? ts : null
  if (/^\d+$/.test(ts)) return parseInt(ts, 10)
  const parsed = Date.parse(ts)
  return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000)
}

const activityTimeAgo = (ts: number | string | null | undefined): string => {
  const unix = activityUnixTs(ts)
  if (!unix) return "â€”"
  const diff = Math.floor(Date.now() / 1000 - unix)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const formatTokenAmount = (value: number | null | undefined, symbol?: string): string => {
  if (value == null) return "â€”"
  const abs = Math.abs(value)
  const decimals = abs >= 1000 ? 0 : abs >= 1 ? 2 : 4
  const rendered = value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: decimals })
  return symbol ? `${rendered} ${symbol}` : rendered
}

const titleCase = (value: string | null | undefined): string => {
  if (!value) return "â€”"
  return value
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

const truncateAddr = (addr: string, len = 6): string => {
  if (!addr || addr.length < len * 2 + 2) return addr
  return `${addr.slice(0, len + 2)}…${addr.slice(-len)}`
}

const timeAgo = (ts: number): string => {
  if (!ts) return "—"
  const normalizedTs = ts > 1e12 ? Math.floor(ts / 1000) : ts
  const diff = Math.floor(Date.now() / 1000 - normalizedTs)
  if (diff < 0) {
    const ahead = Math.abs(diff)
    if (ahead < 60) return `in ${ahead}s`
    if (ahead < 3600) return `in ${Math.floor(ahead / 60)}m`
    if (ahead < 86400) return `in ${Math.floor(ahead / 3600)}h`
    return `in ${Math.floor(ahead / 86400)}d`
  }
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const formatValue = (value: string, decimals: string, symbol: string): string => {
  try {
    const v = parseFloat(value) / Math.pow(10, parseInt(decimals) || 18)
    if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B ${symbol}`
    if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M ${symbol}`
    if (v >= 1e3) return `${(v / 1e3).toFixed(2)}K ${symbol}`
    return `${v.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${symbol}`
  } catch {
    return value
  }
}

const holderPrimaryLabel = (holder: HolderData): string => {
  if (holder.arkham_label) {
    if (holder.arkham_label === "Gnosis Safe Proxy") {
      return `${holder.arkham_label} (${holder.address.slice(0, 5)})`
    }
    return holder.arkham_label
  }
  if (holder.arkham_entity) {
    return holder.arkham_entity
  }
  return truncateAddr(holder.address, 4)
}

const holderBalanceDisplay = (holder: HolderData, symbol: string): string => {
  if (holder.human_balance != null) return formatTokenAmount(holder.human_balance, symbol)
  if (typeof holder.balance === "number") return formatNum(holder.balance, 0)
  return holder.balance
}

const transferPartyLabel = (tx: TransferData, side: "from" | "to"): string => {
  const explicitLabel = side === "from" ? tx.from_label : tx.to_label
  const explicitEntity = side === "from" ? tx.from_entity : tx.to_entity
  const address = side === "from" ? tx.from : tx.to
  return explicitLabel || explicitEntity || truncateAddr(address, 4)
}

// Funding rate sentiment label
const fundingSentiment = (rate: number | null): { label: string; color: string } => {
  if (rate == null) return { label: "—", color: "var(--text-3)" }
  if (rate > 0.001) return { label: "EXTREME LONG", color: "var(--red)" }
  if (rate > 0.0005) return { label: "HIGH LONG", color: "var(--amber)" }
  if (rate > 0) return { label: "LONG", color: "var(--amber)" }
  if (rate > -0.0005) return { label: "SHORT", color: "var(--cyan)" }
  if (rate > -0.001) return { label: "HIGH SHORT", color: "var(--blue-bright)" }
  return { label: "EXTREME SHORT", color: "var(--blue-bright)" }
}

/* ── Sparkline (mini chart) ── */

function Sparkline({ positive }: { positive: boolean }) {
  const color = positive ? "var(--green)" : "var(--red)"
  const points = [50, 45, 48, 42, 55, 50, 60, 55, 65, 58, 70, 65, 72, 68, 75, 70, 78, 74, 80, 76]
  if (!positive) points.reverse()
  const w = 120; const h = 40
  const max = Math.max(...points); const min = Math.min(...points)
  const range = max - min || 1
  const pathD = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w
      const y = h - ((p - min) / range) * h
      return `${i === 0 ? "M" : "L"} ${x} ${y}`
    })
    .join(" ")

  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <defs>
        <linearGradient id={`spark-${positive ? "g" : "r"}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d={`${pathD} L ${w} ${h} L 0 ${h} Z`} fill={`url(#spark-${positive ? "g" : "r"})`} />
    </svg>
  )
}

/* ── Mini bar chart for flows ── */

function FlowBars({ items, maxValue }: { items: { label: string; value: number; positive: boolean }[]; maxValue: number }) {
  if (items.length === 0 || maxValue === 0) return <div style={{ color: "var(--text-4)", fontSize: 11 }}>No data</div>
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {items.map((item, i) => {
        const pct = Math.max(4, Math.abs(item.value) / maxValue * 100)
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 10, color: "var(--text-3)", width: 80, textAlign: "right", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {item.label}
            </span>
            <div style={{ flex: 1, height: 14, background: "var(--bg-void)", borderRadius: 2, position: "relative", overflow: "hidden" }}>
              <div
                style={{
                  position: "absolute", left: 0, top: 0, bottom: 0,
                  width: `${pct}%`,
                  background: item.positive ? "var(--green)" : "var(--red)",
                  opacity: 0.7, borderRadius: 2,
                  transition: "width 0.3s",
                }}
              />
            </div>
            <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-2)", width: 60 }}>
              {formatUsd(Math.abs(item.value))}
            </span>
          </div>
        )
      })}
    </div>
  )
}

/* ── Main Component ── */

type TabId = "overview" | "holders" | "transfers" | "perp" | "flows"

export default function ArkhamEntityPage({ entityId, onClose }: ArkhamEntityPageProps) {
  const [tokenDetail, setTokenDetail] = useState<TokenDetail | null>(null)
  const [holders, setHolders] = useState<HolderData[]>([])
  const [transfers, setTransfers] = useState<TransferData[]>([])
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<TabId>("overview")
  const [entityData, setEntityData] = useState<EntityDetail | null>(null)
  const [addressData, setAddressData] = useState<any>(null)

  // Detect type
  const isToken = entityId?.startsWith("cg_") || entityId?.startsWith("hl_") || entityId?.startsWith("xau_") || entityId?.startsWith("token_")
  const isAddress = entityId?.startsWith("addr_") || (entityId?.startsWith("0x") && !entityId.startsWith("token_"))
  const isEntity = entityId?.startsWith("arkham_")

  // Extract symbol for API calls
  const getSymbol = (): string => {
    if (!entityId) return ""
    let s = entityId
    for (const prefix of ["token_", "cg_", "hl_", "xau_", "addr_", "arkham_"]) {
      if (s.startsWith(prefix)) s = s.slice(prefix.length)
    }
    return s.toLowerCase()
  }

  // Fetch token data
  useEffect(() => {
    if (!entityId || !isToken) {
      setTokenDetail(null); setHolders([]); setTransfers([])
      return
    }
    let cancelled = false
    const symbol = getSymbol()

    setLoading(true)
    setTokenDetail(null)
    setHolders([])
    setTransfers([])

    ;(async () => {
      try {
        const detailRes = await fetch(`${API}/arkham/token/${encodeURIComponent(symbol)}`, { cache: "no-store" })
        const detail = detailRes.ok ? await detailRes.json() : null
        if (cancelled) return

        if (detail && !detail.error) {
          setTokenDetail(detail)
        }
        setLoading(false)

        if (!detail || detail.error) return

        const holdersRes = await fetch(`${API}/arkham/token/${encodeURIComponent(symbol)}/holders`, { cache: "no-store" })
        const holdersData = holdersRes.ok ? await holdersRes.json() : null
        if (!cancelled && holdersData) {
          setHolders(holdersData.holders || [])
        }

        const transfersRes = await fetch(`${API}/arkham/token/${encodeURIComponent(symbol)}/transfers`, { cache: "no-store" })
        const transfersData = transfersRes.ok ? await transfersRes.json() : null
        if (!cancelled && transfersData) {
          setTransfers(transfersData.transfers || [])
        }
      } catch {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [entityId])

  // Fetch entity data
  useEffect(() => {
    if (!entityId || !isEntity) {
      setEntityData(null)
      return
    }

    let cancelled = false
    let retryTimer: number | null = null
    const slug = getSymbol()
    setEntityData(null)

    const loadEntity = async (showBlockingLoader: boolean) => {
      if (showBlockingLoader) {
        setLoading(true)
      }

      let data: any = null

      try {
        const controller = new AbortController()
        const timeoutId = window.setTimeout(() => controller.abort(), 8000)

        let response = await fetch(`${API}/entity/${encodeURIComponent(slug)}`, {
          cache: "no-store",
          signal: controller.signal,
        })
        window.clearTimeout(timeoutId)

        let internalData = response.ok ? await response.json() : null

        const isPoor = !internalData || internalData.error || internalData.ok === false || (
          (!internalData.portfolio || !internalData.portfolio.net_worth_usd) &&
          (internalData.wallets_count || 0) <= 1 &&
          (internalData.portfolio?.top_holdings?.length || 0) === 0
        )

        const arkhamController = new AbortController()
        const arkhamTimeout = window.setTimeout(() => arkhamController.abort(), 22000)
        let arkhamData: any = null
        try {
          response = await fetch(`${API}/arkham/entity/${encodeURIComponent(slug)}`, {
            cache: "no-store",
            signal: arkhamController.signal,
          })
          arkhamData = response.ok ? await response.json() : null
        } catch (arkhamErr) {
          console.warn("[Entity] Arkham data fetch failed for " + slug + ":", arkhamErr)
        } finally {
          window.clearTimeout(arkhamTimeout)
        }

        if (entityDataScore(arkhamData) > entityDataScore(internalData)) {
          data = arkhamData
          console.warn("[Entity] Using richer Arkham data for " + slug)
        } else if (isPoor) {
          data = arkhamData || internalData
          console.warn("[Entity] Internal data poor for " + slug + " - using Arkham/fallback")
        } else {
          data = internalData
        }

        if (cancelled) return

        if (data) {
          setEntityData(data)
          const retryDelaySeconds = Number(data.snapshot_retry_after_seconds ?? 0)
          if (data.snapshot_status === "warming") {
            const nextRefreshMs = Math.max(4000, Math.min(retryDelaySeconds > 0 ? retryDelaySeconds * 1000 : 5000, 8000))
            retryTimer = window.setTimeout(() => {
              if (!cancelled) {
                void loadEntity(false)
              }
            }, nextRefreshMs)
          }
        }
      } catch (err) {
        console.warn("[Entity] Error loading " + slug + ":", err)
        try {
          const response = await fetch(`${API}/arkham/entity/${encodeURIComponent(slug)}`, { cache: "no-store" })
          data = response.ok ? await response.json() : null
          if (data && !cancelled) {
            setEntityData(data)
            console.warn("[Entity] Using Arkham fallback after error for " + slug)
          }
        } catch (fallbackErr) {
          console.warn("[Entity] Arkham fallback also failed for " + slug + ":", fallbackErr)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void loadEntity(true)

    return () => {
      cancelled = true
      if (retryTimer != null) {
        window.clearTimeout(retryTimer)
      }
    }
  }, [entityId])

  // Fetch address data
  useEffect(() => {
    if (!entityId || !isAddress) { setAddressData(null); return }
    setLoading(true)
    const addr = entityId.startsWith("addr_") ? entityId.slice(5) : entityId
    fetch(`${API}/arkham/lookup/${encodeURIComponent(addr)}`, { cache: "no-store" })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setAddressData(d) })
      .finally(() => setLoading(false))
  }, [entityId])

  const handleClose = useCallback(() => onClose(), [onClose])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") handleClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [handleClose])

  useEffect(() => {
    setActiveTab("overview")
  }, [entityId])

  if (!entityId) return null

  const requestedSymbol = getSymbol().toUpperCase()
  const symbol = tokenDetail?.symbol?.trim() ? tokenDetail.symbol.toUpperCase() : requestedSymbol
  const rawName = tokenDetail?.name?.trim() || requestedSymbol
  const name = rawName.toLowerCase() === symbol.toLowerCase() ? symbol : rawName
  const isSyntheticPerp = Boolean(
    isToken &&
    entityId?.startsWith("hl_") &&
    !tokenDetail?.contract_address &&
    tokenDetail?.source === "unknown"
  )
  const heroSubtitle = isSyntheticPerp ? "Synthetic perpetual market" : `$${symbol}`
  const showCoingeckoLink = !isSyntheticPerp
  const priceUp = (tokenDetail?.price_change_24h ?? 0) >= 0
  const hasPerpData = tokenDetail && (
    tokenDetail.funding_rate != null ||
    tokenDetail.hyperliquid_cvd != null ||
    metricNumber(tokenDetail.open_interest) != null ||
    metricNumber(tokenDetail.hyperliquid_oi) != null
  )
  const hasFlows = tokenDetail?.arkham_flows && (
    (tokenDetail.arkham_flows.top_inflows?.length ?? 0) > 0 ||
    (tokenDetail.arkham_flows.top_outflows?.length ?? 0) > 0 ||
    (tokenDetail.arkham_flows.exchange_flows?.length ?? 0) > 0
  )

  const hyperliquidOi = metricNumber(tokenDetail?.hyperliquid_oi)
  const entityIntelligence = entityData?.intelligence || null
  const entityCoverage = entityIntelligence?.coverage || null
  const entityObservedHoldings = entityIntelligence?.observed_holdings || []
  const entityObservedWallets = entityIntelligence?.wallets?.length ? entityIntelligence.wallets : (entityData?.wallets || [])
  const entityActivity = entityIntelligence?.recent_activity || []
  const entityCounterparties = entityIntelligence?.counterparties || []
  const entityTopTags = entityIntelligence?.top_tags || []
  const entityChains = entityIntelligence?.chains?.length
    ? entityIntelligence.chains.map(item => item.chain)
    : (entityData?.entity?.chains || [])
  const entitySnapshotStatus = entityData?.snapshot_status ?? null
  const entitySnapshotRetryAfterSeconds = entityData?.snapshot_retry_after_seconds ?? null

  // Determine tabs based on data available
  const tabs: { id: TabId; label: string; count?: number }[] = [
    { id: "overview", label: "Overview" },
  ]
  if (isToken) {
    if (!isSyntheticPerp) {
      tabs.push({ id: "holders", label: "Holders", count: holders.length || undefined })
      tabs.push({ id: "transfers", label: "Transfers", count: transfers.length || undefined })
    }
    if (hasPerpData) tabs.push({ id: "perp", label: "Perp Data" })
    if (hasFlows) tabs.push({ id: "flows", label: "Flows" })
  }

  return (
    <div className="arkham-overlay">
      {/* Top bar */}
      <div className="arkham-topbar">
        <button className="arkham-back-btn" onClick={handleClose}>← Back</button>
        <span style={{ flex: 1 }} />
        {isToken && <span className="arkham-hero-badge" style={{ color: "var(--blue-bright)", borderColor: "var(--blue-bright)" }}>TOKEN</span>}
        {isAddress && <span className="arkham-hero-badge" style={{ color: "var(--cyan)", borderColor: "var(--cyan)" }}>ADDRESS</span>}
        {isEntity && <span className="arkham-hero-badge" style={{ color: "var(--amber)", borderColor: "var(--amber)" }}>ENTITY</span>}
      </div>

      {/* Loading */}
      {loading && (
        <div className="arkham-loading">
          <div className="arkham-spinner" />
          Loading {isToken ? symbol : entityId} data...
        </div>
      )}

      {/* ── TOKEN VIEW ── */}
      {!loading && isToken && tokenDetail && (
        <>
          {/* Hero */}
          <div className="arkham-hero">
            <div className="arkham-hero-top">
              <div className="arkham-hero-icon">
                <LogoAvatar
                  name={name}
                  symbol={symbol}
                  src={tokenDetail.image}
                  size={40}
                  title={name}
                />
              </div>
              <div className="arkham-hero-info">
                <div className="arkham-hero-name">{name}</div>
                <div className="arkham-hero-sym">{heroSubtitle}</div>
                {tokenDetail.contract_address && (
                  <span className="arkham-hero-badge" style={{ color: "var(--text-3)", borderColor: "var(--border)" }}>
                    {tokenDetail.chain}
                  </span>
                )}
                {tokenDetail.is_native && (
                  <span className="arkham-hero-badge" style={{ color: "var(--amber)", borderColor: "var(--amber)" }}>
                    NATIVE
                  </span>
                )}
                {isSyntheticPerp && (
                  <span className="arkham-hero-badge" style={{ color: "var(--cyan)", borderColor: "var(--cyan)" }}>
                    PERP
                  </span>
                )}
              </div>
              <Sparkline positive={priceUp} />
            </div>

            <div className="arkham-hero-price-section">
              <span className="arkham-hero-price">
                {tokenDetail.price_usd != null ? formatUsd(tokenDetail.price_usd) : isSyntheticPerp ? "Synthetic Perp" : "—"}
              </span>
              {tokenDetail.price_change_24h != null && (
                <span className={`arkham-hero-change ${priceUp ? "up" : "down"}`}>
                  {formatPct(tokenDetail.price_change_24h)} (24h)
                </span>
              )}
              {tokenDetail.price_change_24h == null && isSyntheticPerp && tokenDetail.funding_rate != null && (
                <span className="arkham-hero-change" style={{ color: fundingSentiment(tokenDetail.funding_rate).color }}>
                  Funding {formatPct(tokenDetail.funding_rate * 100, 4)}
                </span>
              )}
              {tokenDetail.price_change_24h == null && isSyntheticPerp && tokenDetail.funding_rate == null && (
                <span className="arkham-hero-change" style={{ color: "var(--text-3)" }}>
                  Derivatives-only market
                </span>
              )}
            </div>

            {/* Stats row */}
            <div className="arkham-stats-row" style={{ marginTop: 12 }}>
              {tokenDetail.volume_24h != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">24h Volume</div>
                  <div className="arkham-stat-value">{formatUsd(tokenDetail.volume_24h)}</div>
                </div>
              )}
              {tokenDetail.market_cap_usd != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Market Cap</div>
                  <div className="arkham-stat-value">{formatUsd(tokenDetail.market_cap_usd)}</div>
                </div>
              )}
              {tokenDetail.fdv != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">FDV</div>
                  <div className="arkham-stat-value">{formatUsd(tokenDetail.fdv)}</div>
                </div>
              )}
              {tokenDetail.circulating_supply != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Circulating Supply</div>
                  <div className="arkham-stat-value">{formatNum(tokenDetail.circulating_supply, 0)}</div>
                </div>
              )}
              {tokenDetail.total_supply != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Total Supply</div>
                  <div className="arkham-stat-value">{formatNum(tokenDetail.total_supply, 0)}</div>
                </div>
              )}
              {tokenDetail.max_supply != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Max Supply</div>
                  <div className="arkham-stat-value">{formatNum(tokenDetail.max_supply, 0)}</div>
                </div>
              )}
              {tokenDetail.ath != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">ATH</div>
                  <div className="arkham-stat-value">{formatUsd(tokenDetail.ath)}</div>
                </div>
              )}
              {tokenDetail.price_change_7d != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">7d Change</div>
                  <div className="arkham-stat-value" style={{ color: tokenDetail.price_change_7d >= 0 ? "var(--green)" : "var(--red)" }}>
                    {formatPct(tokenDetail.price_change_7d)}
                  </div>
                </div>
              )}
              {/* Perp data quick stats */}
              {tokenDetail.funding_rate != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Funding Rate</div>
                  <div className="arkham-stat-value" style={{ color: fundingSentiment(tokenDetail.funding_rate).color }}>
                    {formatPct(tokenDetail.funding_rate * 100, 4)}
                  </div>
                </div>
              )}
              {tokenDetail.hyperliquid_cvd != null && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">CVD (HL)</div>
                  <div className="arkham-stat-value" style={{ color: tokenDetail.hyperliquid_cvd >= 0 ? "var(--green)" : "var(--red)" }}>
                    {formatUsd(tokenDetail.hyperliquid_cvd)}
                  </div>
                </div>
              )}
              {!isSyntheticPerp && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Holders</div>
                  <div className="arkham-stat-value">
                    {tokenDetail.holders_count?.toLocaleString() || (holders.length > 0 ? holders.length.toLocaleString() : "—")}
                  </div>
                </div>
              )}
              {isSyntheticPerp && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Market Type</div>
                  <div className="arkham-stat-value">Synthetic Perp</div>
                </div>
              )}
              {isSyntheticPerp && (
                <div className="arkham-stat">
                  <div className="arkham-stat-label">Venue</div>
                  <div className="arkham-stat-value">Hyperliquid</div>
                </div>
              )}
              {tokenDetail.contract_address && (
                <div className="arkham-stat" style={{ flex: 2 }}>
                  <div className="arkham-stat-label">Contract</div>
                  <div className="arkham-stat-mono">{tokenDetail.contract_address}</div>
                </div>
              )}
            </div>
          </div>

          {/* Tabs */}
          <div className="arkham-tabs">
            {tabs.map(t => (
              <button
                key={t.id}
                className={`arkham-tab ${activeTab === t.id ? "active" : ""}`}
                onClick={() => setActiveTab(t.id)}
              >
                {t.label}
                {t.count != null && <span className="arkham-tab-count">{t.count}</span>}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="arkham-content">
            {/* ── OVERVIEW ── */}
            {activeTab === "overview" && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                {/* Left: Token Info + Holders preview */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div className="arkham-card">
                    <div className="arkham-card-header">
                      <span className="arkham-card-title">Token Info</span>
                    </div>
                    <div className="arkham-card-body">
                      <div className="arkham-metrics">
                        {tokenDetail.price_usd != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Price</span>
                            <span className="arkham-metric-value">{formatUsd(tokenDetail.price_usd)}</span>
                          </div>
                        )}
                        {tokenDetail.market_cap_usd != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Market Cap</span>
                            <span className="arkham-metric-value">{formatUsd(tokenDetail.market_cap_usd)}</span>
                          </div>
                        )}
                        {tokenDetail.volume_24h != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">24h Volume</span>
                            <span className="arkham-metric-value">{formatUsd(tokenDetail.volume_24h)}</span>
                          </div>
                        )}
                        {tokenDetail.fdv != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">FDV</span>
                            <span className="arkham-metric-value">{formatUsd(tokenDetail.fdv)}</span>
                          </div>
                        )}
                        {tokenDetail.circulating_supply != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Circ. Supply</span>
                            <span className="arkham-metric-value">{formatNum(tokenDetail.circulating_supply, 0)}</span>
                          </div>
                        )}
                        {tokenDetail.total_supply != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Total Supply</span>
                            <span className="arkham-metric-value">{formatNum(tokenDetail.total_supply, 0)}</span>
                          </div>
                        )}
                        {tokenDetail.max_supply != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Max Supply</span>
                            <span className="arkham-metric-value">{formatNum(tokenDetail.max_supply, 0)}</span>
                          </div>
                        )}
                        {tokenDetail.ath != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">All-Time High</span>
                            <span className="arkham-metric-value">{formatUsd(tokenDetail.ath)}</span>
                          </div>
                        )}
                        {tokenDetail.ath_date && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">ATH Date</span>
                            <span className="arkham-metric-value">{tokenDetail.ath_date.slice(0, 10)}</span>
                          </div>
                        )}
                        {tokenDetail.price_change_7d != null && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">7d Change</span>
                            <span className="arkham-metric-value" style={{ color: tokenDetail.price_change_7d >= 0 ? "var(--green)" : "var(--red)" }}>
                              {formatPct(tokenDetail.price_change_7d)}
                            </span>
                          </div>
                        )}
                        {isSyntheticPerp && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Instrument</span>
                            <span className="arkham-metric-value">Synthetic Perpetual</span>
                          </div>
                        )}
                        {isSyntheticPerp && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Venue</span>
                            <span className="arkham-metric-value">Hyperliquid</span>
                          </div>
                        )}
                        {isSyntheticPerp && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Spot Contract</span>
                            <span className="arkham-metric-value">None</span>
                          </div>
                        )}
                        {isSyntheticPerp && tokenDetail.funding_next_time && (
                          <div className="arkham-metric">
                            <span className="arkham-metric-label">Next Funding</span>
                            <span className="arkham-metric-value">{timeAgo(tokenDetail.funding_next_time)}</span>
                          </div>
                        )}
                      </div>
                      <div className="arkham-links" style={{ marginTop: 12 }}>
                        {tokenDetail.contract_address && (
                          <a className="arkham-link" href={getExplorerTokenUrl(tokenDetail.contract_address, tokenDetail.chain) || undefined} target="_blank" rel="noopener noreferrer">
                            Etherscan ↗
                          </a>
                        )}
                        {showCoingeckoLink && (
                          <a className="arkham-link" href={`https://www.coingecko.com/en/coins/${getSymbol()}`} target="_blank" rel="noopener noreferrer">
                            CoinGecko ↗
                          </a>
                        )}
                        {tokenDetail.contract_address && (
                          <a className="arkham-link" href={`https://dexscreener.com/${tokenDetail.chain}/${tokenDetail.contract_address}`} target="_blank" rel="noopener noreferrer">
                            DEX Screener ↗
                          </a>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Top 5 holders preview */}
                  {holders.length > 0 && (
                    <div className="arkham-card">
                      <div className="arkham-card-header">
                        <span className="arkham-card-title">Top Holders</span>
                        <button className="arkham-link" style={{ cursor: "pointer" }} onClick={() => setActiveTab("holders")}>
                          View All →
                        </button>
                      </div>
                      <div className="arkham-card-body" style={{ padding: 0 }}>
                        <table className="arkham-holders-table">
                          <thead>
                            <tr><th>#</th><th>Holder</th><th>Balance</th><th>%</th><th>Entity</th></tr>
                          </thead>
                          <tbody>
                            {holders.slice(0, 5).map((h, i) => (
                              <tr key={h.address}>
                                <td><span className={`arkham-rank ${i < 3 ? "top" : ""}`}>{i + 1}</span></td>
                                <td className="addr">
                                  {holderPrimaryLabel(h)}
                                  <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>
                                    {getExplorerAddressUrl(h.address, tokenDetail.chain) ? (
                                      <a
                                        href={getExplorerAddressUrl(h.address, tokenDetail.chain) || undefined}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ color: "var(--blue-bright)" }}
                                      >
                                        {truncateAddr(h.address, 4)}
                                      </a>
                                    ) : (
                                      truncateAddr(h.address, 4)
                                    )}
                                  </span>
                                  {h.arkham_entity && <span className="arkham-entity-label">{h.arkham_entity}</span>}
                                </td>
                                <td className="bal">
                                  {holderBalanceDisplay(h, symbol)}
                                  {h.value_usd != null && <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>{formatUsd(h.value_usd)}</span>}
                                </td>
                                <td className="pct">{h.percentage != null ? `${h.percentage.toFixed(4)}%` : "—"}</td>
                                <td>{h.arkham_entity ? <span className="arkham-entity-label">{h.arkham_entity}</span> : <span style={{ color: "var(--text-4)" }}>—</span>}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>

                {/* Right: Perp preview + Flows preview */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  {/* Perp Data preview */}
                  {hasPerpData && (
                    <div className="arkham-card">
                      <div className="arkham-card-header">
                        <span className="arkham-card-title">Perpetual Data</span>
                        <button className="arkham-link" style={{ cursor: "pointer" }} onClick={() => setActiveTab("perp")}>
                          Details →
                        </button>
                      </div>
                      <div className="arkham-card-body">
                        <div className="arkham-metrics">
                          {tokenDetail.funding_rate != null && (
                            <div className="arkham-metric">
                              <span className="arkham-metric-label">Funding Rate</span>
                              <span className="arkham-metric-value" style={{ color: fundingSentiment(tokenDetail.funding_rate).color }}>
                                {formatPct(tokenDetail.funding_rate * 100, 4)}
                              </span>
                              <span style={{ fontSize: 9, color: "var(--text-4)" }}>{fundingSentiment(tokenDetail.funding_rate).label}</span>
                            </div>
                          )}
                          {tokenDetail.funding_rate_binance != null && (
                            <div className="arkham-metric">
                              <span className="arkham-metric-label">Funding (Binance)</span>
                              <span className="arkham-metric-value">{formatPct(tokenDetail.funding_rate_binance * 100, 4)}</span>
                            </div>
                          )}
                          {tokenDetail.funding_rate_bybit != null && (
                            <div className="arkham-metric">
                              <span className="arkham-metric-label">Funding (Bybit)</span>
                              <span className="arkham-metric-value">{formatPct(tokenDetail.funding_rate_bybit * 100, 4)}</span>
                            </div>
                          )}
                          {tokenDetail.hyperliquid_cvd != null && (
                            <div className="arkham-metric">
                              <span className="arkham-metric-label">CVD (Hyperliquid)</span>
                              <span className="arkham-metric-value" style={{ color: tokenDetail.hyperliquid_cvd >= 0 ? "var(--green)" : "var(--red)" }}>
                                {formatUsd(tokenDetail.hyperliquid_cvd)}
                              </span>
                            </div>
                          )}
                          {hyperliquidOi != null && (
                            <div className="arkham-metric">
                              <span className="arkham-metric-label">OI (Hyperliquid)</span>
                              <span className="arkham-metric-value">{formatUsd(hyperliquidOi)}</span>
                            </div>
                          )}
                          {tokenDetail.hyperliquid_price != null && (
                            <div className="arkham-metric">
                              <span className="arkham-metric-label">HL Price</span>
                              <span className="arkham-metric-value">{formatUsd(tokenDetail.hyperliquid_price)}</span>
                            </div>
                          )}
                          {tokenDetail.hyperliquid_best_bid != null && tokenDetail.hyperliquid_best_ask != null && (
                            <div className="arkham-metric">
                              <span className="arkham-metric-label">HL Spread</span>
                              <span className="arkham-metric-value">{formatUsd(tokenDetail.hyperliquid_best_ask - tokenDetail.hyperliquid_best_bid)}</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Arkham Flows preview */}
                  {hasFlows && (
                    <div className="arkham-card">
                      <div className="arkham-card-header">
                        <span className="arkham-card-title">Arkham Entity Flows</span>
                        <button className="arkham-link" style={{ cursor: "pointer" }} onClick={() => setActiveTab("flows")}>
                          Details →
                        </button>
                      </div>
                      <div className="arkham-card-body">
                        <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 8 }}>
                          {tokenDetail.arkham_flows.total_entities_tracked ?? 0} entities tracked
                        </div>
                        {/* Exchange flows */}
                        {tokenDetail.arkham_flows.exchange_flows && tokenDetail.arkham_flows.exchange_flows.length > 0 && (
                          <div style={{ marginBottom: 12 }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--text-2)", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
                              Exchange Net Flows
                            </div>
                            <FlowBars
                              items={tokenDetail.arkham_flows.exchange_flows.map((ef: any) => ({
                                label: ef.exchange,
                                value: ef.net ?? 0,
                                positive: (ef.net ?? 0) > 0,
                              }))}
                              maxValue={Math.max(...tokenDetail.arkham_flows.exchange_flows.map((ef: any) => Math.abs(ef.net ?? 0)), 1)}
                            />
                          </div>
                        )}
                        {/* Top inflows */}
                        {tokenDetail.arkham_flows.top_inflows && tokenDetail.arkham_flows.top_inflows.length > 0 && (
                          <div>
                            <div style={{ fontSize: 10, fontWeight: 700, color: "var(--green)", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
                              Top Inflows
                            </div>
                            {tokenDetail.arkham_flows.top_inflows.slice(0, 3).map((f: any, i: number) => (
                              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid var(--border)" }}>
                                <span style={{ fontSize: 11, color: "var(--text-2)" }}>{f.entity}</span>
                                <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--green)" }}>{formatUsd(f.amount)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Recent transfers preview */}
                  {transfers.length > 0 && (
                    <div className="arkham-card">
                      <div className="arkham-card-header">
                        <span className="arkham-card-title">Recent Transfers</span>
                        <button className="arkham-link" style={{ cursor: "pointer" }} onClick={() => setActiveTab("transfers")}>
                          View All →
                        </button>
                      </div>
                      <div className="arkham-card-body" style={{ padding: 0 }}>
                        <table className="arkham-holders-table">
                          <thead><tr><th>Time</th><th>From</th><th>To</th><th>Value</th></tr></thead>
                          <tbody>
                            {transfers.slice(0, 8).map((tx, i) => (
                              <tr key={tx.tx_hash || i}>
                                <td style={{ fontSize: 11, color: "var(--text-3)" }}>{activityTimeAgo(tx.timestamp)}</td>
                                <td className="addr">
                                  {transferPartyLabel(tx, "from")}
                                  <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>{truncateAddr(tx.from, 4)}</span>
                                  {tx.from_entity && <span className="arkham-entity-label">{tx.from_entity}</span>}
                                </td>
                                <td className="addr">
                                  {transferPartyLabel(tx, "to")}
                                  <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>{truncateAddr(tx.to, 4)}</span>
                                  {tx.to_entity && <span className="arkham-entity-label">{tx.to_entity}</span>}
                                </td>
                                <td className="bal">
                                  {tx.human_value != null ? formatTokenAmount(tx.human_value, tx.token_symbol) : formatValue(tx.value, tx.token_decimal, tx.token_symbol)}
                                  {tx.value_usd != null && <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>{formatUsd(tx.value_usd)}</span>}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── HOLDERS TAB ── */}
            {activeTab === "holders" && (
              <>
                {tokenDetail.holders_note ? (
                  <div className="arkham-empty">
                    <div className="arkham-empty-icon">◎</div>
                    <div className="arkham-empty-title">Native Coin</div>
                    <div className="arkham-empty-desc">{tokenDetail.holders_note}</div>
                  </div>
                ) : holders.length === 0 ? (
                  <div className="arkham-empty">
                    <div className="arkham-empty-icon">◎</div>
                    <div className="arkham-empty-title">No holders data</div>
                    <div className="arkham-empty-desc">
                      Requires a valid contract address. Try an ERC-20 token like USDT, LINK, UNI.
                    </div>
                  </div>
                ) : (
                  <div className="arkham-card">
                    <div className="arkham-card-header">
                      <span className="arkham-card-title">Token Holders ({holders.length})</span>
                      <span style={{ fontSize: 10, color: "var(--text-4)" }}>
                        Contract: {truncateAddr(tokenDetail.contract_address || "", 4)}
                      </span>
                    </div>
                    <div className="arkham-card-body" style={{ padding: 0 }}>
                      <table className="arkham-holders-table">
                        <thead>
                          <tr>
                            <th style={{ width: 40 }}>#</th>
                            <th>Holder</th>
                            <th style={{ width: 100 }}>Type</th>
                            <th>Balance</th>
                            <th style={{ width: 80 }}>Supply %</th>
                            <th style={{ width: 140 }}>Label</th>
                            <th style={{ width: 120 }}>Entity</th>
                          </tr>
                        </thead>
                        <tbody>
                          {holders.map((h, i) => (
                            <tr key={h.address}>
                              <td><span className={`arkham-rank ${i < 3 ? "top" : ""}`}>{i + 1}</span></td>
                              <td className="addr">
                                {holderPrimaryLabel(h)}
                                <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>
                                  {getExplorerAddressUrl(h.address, tokenDetail.chain) ? (
                                    <a
                                      href={getExplorerAddressUrl(h.address, tokenDetail.chain) || undefined}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      style={{ color: "var(--blue-bright)" }}
                                    >
                                      {truncateAddr(h.address, 4)}
                                    </a>
                                  ) : (
                                    truncateAddr(h.address, 4)
                                  )}
                                </span>
                              </td>
                              <td>
                                {h.wallet_type ? (
                                  <span className="arkham-entity-label">{titleCase(h.wallet_type)}</span>
                                ) : (
                                  <span style={{ color: "var(--text-4)" }}>â€”</span>
                                )}
                              </td>
                              <td className="bal">
                                {holderBalanceDisplay(h, symbol)}
                                {h.value_usd != null && <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>{formatUsd(h.value_usd)}</span>}
                              </td>
                              <td className="pct">{h.percentage != null ? `${h.percentage.toFixed(4)}%` : "—"}</td>
                              <td>
                                {h.arkham_label ? (
                                  <span className="arkham-entity-label">{h.arkham_label}</span>
                                ) : (
                                  <span style={{ color: "var(--text-4)" }}>—</span>
                                )}
                              </td>
                              <td>
                                {h.arkham_entity ? (
                                  <span className="arkham-entity-label" style={{ color: "var(--amber)" }}>{h.arkham_entity}</span>
                                ) : (
                                  <span style={{ color: "var(--text-4)" }}>—</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── TRANSFERS TAB ── */}
            {activeTab === "transfers" && (
              <>
                {transfers.length === 0 ? (
                  <div className="arkham-empty">
                    <div className="arkham-empty-icon">⇄</div>
                    <div className="arkham-empty-title">No transfer data</div>
                    <div className="arkham-empty-desc">
                      Requires a valid contract address. Blockscout API (free) is the primary source.
                    </div>
                  </div>
                ) : (
                  <div className="arkham-card">
                    <div className="arkham-card-header">
                      <span className="arkham-card-title">Recent Transfers ({transfers.length})</span>
                      <span style={{ fontSize: 10, color: "var(--text-4)" }}>
                        Source: Blockscout
                      </span>
                    </div>
                    <div className="arkham-card-body" style={{ padding: 0 }}>
                      <table className="arkham-holders-table">
                        <thead>
                          <tr>
                            <th style={{ width: 80 }}>Time</th>
                            <th style={{ width: 120 }}>Tx Hash</th>
                            <th>From</th>
                            <th>To</th>
                            <th>Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {transfers.map((tx, i) => (
                            <tr key={tx.tx_hash || i}>
                              <td style={{ fontSize: 11, color: "var(--text-3)" }}>{activityTimeAgo(tx.timestamp)}</td>
                              <td className="addr" style={{ color: "var(--blue-bright)" }}>
                                {getExplorerTxUrl(tx.tx_hash, tokenDetail.chain) ? (
                                  <a
                                    href={getExplorerTxUrl(tx.tx_hash, tokenDetail.chain) || undefined}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: "var(--blue-bright)" }}
                                  >
                                    {truncateAddr(tx.tx_hash, 8)}
                                  </a>
                                ) : (
                                  truncateAddr(tx.tx_hash, 8)
                                )}
                              </td>
                              <td className="addr">
                                {transferPartyLabel(tx, "from")}
                                <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>
                                  {getExplorerAddressUrl(tx.from, tokenDetail.chain) ? (
                                    <a
                                      href={getExplorerAddressUrl(tx.from, tokenDetail.chain) || undefined}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      style={{ color: "var(--blue-bright)" }}
                                    >
                                      {truncateAddr(tx.from, 4)}
                                    </a>
                                  ) : (
                                    truncateAddr(tx.from, 4)
                                  )}
                                </span>
                                {tx.from_entity && <span className="arkham-entity-label" style={{ color: "var(--amber)" }}>{tx.from_entity}</span>}
                              </td>
                              <td className="addr">
                                {transferPartyLabel(tx, "to")}
                                <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>
                                  {getExplorerAddressUrl(tx.to, tokenDetail.chain) ? (
                                    <a
                                      href={getExplorerAddressUrl(tx.to, tokenDetail.chain) || undefined}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      style={{ color: "var(--blue-bright)" }}
                                    >
                                      {truncateAddr(tx.to, 4)}
                                    </a>
                                  ) : (
                                    truncateAddr(tx.to, 4)
                                  )}
                                </span>
                                {tx.to_entity && <span className="arkham-entity-label" style={{ color: "var(--amber)" }}>{tx.to_entity}</span>}
                              </td>
                              <td className="bal">
                                {tx.human_value != null ? formatTokenAmount(tx.human_value, tx.token_symbol) : formatValue(tx.value, tx.token_decimal, tx.token_symbol)}
                                {tx.value_usd != null && <span style={{ color: "var(--text-4)", fontSize: 10, display: "block" }}>{formatUsd(tx.value_usd)}</span>}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── PERP DATA TAB ── */}
            {activeTab === "perp" && hasPerpData && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                {/* Left: Funding + OI */}
                <div className="arkham-card">
                  <div className="arkham-card-header">
                    <span className="arkham-card-title">Funding Rates</span>
                    {tokenDetail.funding_rate != null && (
                      <span style={{ fontSize: 10, fontWeight: 700, color: fundingSentiment(tokenDetail.funding_rate).color }}>
                        {fundingSentiment(tokenDetail.funding_rate).label}
                      </span>
                    )}
                  </div>
                  <div className="arkham-card-body">
                    <div className="arkham-metrics">
                      {tokenDetail.funding_rate != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Primary Rate</span>
                          <span className="arkham-metric-value" style={{ fontSize: 18, color: fundingSentiment(tokenDetail.funding_rate).color }}>
                            {formatPct(tokenDetail.funding_rate * 100, 4)}
                          </span>
                          <span style={{ fontSize: 10, color: "var(--text-4)" }}>
                            {tokenDetail.funding_rate > 0 ? "Longs pay shorts" : "Shorts pay longs"}
                          </span>
                        </div>
                      )}
                      {tokenDetail.funding_rate_binance != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Binance</span>
                          <span className="arkham-metric-value">{formatPct(tokenDetail.funding_rate_binance * 100, 4)}</span>
                        </div>
                      )}
                      {tokenDetail.funding_rate_bybit != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Bybit</span>
                          <span className="arkham-metric-value">{formatPct(tokenDetail.funding_rate_bybit * 100, 4)}</span>
                        </div>
                      )}
                      {tokenDetail.funding_next_time && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Next Funding</span>
                          <span className="arkham-metric-value">{timeAgo(tokenDetail.funding_next_time)}</span>
                        </div>
                      )}
                    </div>
                    {/* Funding bias bar */}
                    {tokenDetail.funding_rate != null && (
                      <div style={{ marginTop: 16, padding: 12, background: "var(--bg-void)", borderRadius: 6 }}>
                        <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 }}>
                          Market Sentiment
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                          <span style={{ fontSize: 11, color: "var(--red)", fontWeight: 600 }}>SHORT</span>
                          <div style={{ flex: 1, height: 6, background: "var(--bg-hover)", borderRadius: 3, position: "relative", overflow: "hidden" }}>
                            <div
                              style={{
                                position: "absolute", top: 0, bottom: 0,
                                left: tokenDetail.funding_rate > 0 ? "50%" : `${50 + tokenDetail.funding_rate * 1000}%`,
                                right: tokenDetail.funding_rate <= 0 ? "50%" : undefined,
                                width: tokenDetail.funding_rate > 0 ? `${Math.min(50, tokenDetail.funding_rate * 1000)}%` : undefined,
                                background: tokenDetail.funding_rate > 0 ? "var(--amber)" : "var(--cyan)",
                                borderRadius: 3,
                              }}
                            />
                          </div>
                          <span style={{ fontSize: 11, color: "var(--amber)", fontWeight: 600 }}>LONG</span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Right: Hyperliquid data */}
                <div className="arkham-card">
                  <div className="arkham-card-header">
                    <span className="arkham-card-title">Hyperliquid Data</span>
                  </div>
                  <div className="arkham-card-body">
                    <div className="arkham-metrics">
                      {tokenDetail.hyperliquid_price != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Price</span>
                          <span className="arkham-metric-value">{formatUsd(tokenDetail.hyperliquid_price)}</span>
                        </div>
                      )}
                      {tokenDetail.hyperliquid_cvd != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Cumulative Volume Delta</span>
                          <span className="arkham-metric-value" style={{ color: tokenDetail.hyperliquid_cvd >= 0 ? "var(--green)" : "var(--red)" }}>
                            {formatUsd(tokenDetail.hyperliquid_cvd)}
                          </span>
                          <span style={{ fontSize: 10, color: "var(--text-4)" }}>
                            {tokenDetail.hyperliquid_cvd >= 0 ? "Buy pressure" : "Sell pressure"}
                          </span>
                        </div>
                      )}
                      {hyperliquidOi != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Open Interest</span>
                          <span className="arkham-metric-value">{formatUsd(hyperliquidOi)}</span>
                        </div>
                      )}
                      {tokenDetail.hyperliquid_best_bid != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Best Bid</span>
                          <span className="arkham-metric-value">{formatUsd(tokenDetail.hyperliquid_best_bid)}</span>
                        </div>
                      )}
                      {tokenDetail.hyperliquid_best_ask != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Best Ask</span>
                          <span className="arkham-metric-value">{formatUsd(tokenDetail.hyperliquid_best_ask)}</span>
                        </div>
                      )}
                      {tokenDetail.hyperliquid_spread != null && (
                        <div className="arkham-metric">
                          <span className="arkham-metric-label">Spread</span>
                          <span className="arkham-metric-value">{formatUsd(tokenDetail.hyperliquid_spread)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* ── FLOWS TAB ── */}
            {activeTab === "flows" && hasFlows && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                {/* Left: Exchange flows */}
                <div className="arkham-card">
                  <div className="arkham-card-header">
                    <span className="arkham-card-title">Exchange Net Flows</span>
                  </div>
                  <div className="arkham-card-body">
                    {tokenDetail.arkham_flows.exchange_flows && tokenDetail.arkham_flows.exchange_flows.length > 0 ? (
                      <FlowBars
                        items={tokenDetail.arkham_flows.exchange_flows.map((ef: any) => ({
                          label: ef.exchange,
                          value: ef.net ?? 0,
                          positive: (ef.net ?? 0) > 0,
                        }))}
                        maxValue={Math.max(...tokenDetail.arkham_flows.exchange_flows.map((ef: any) => Math.abs(ef.net ?? 0)), 1)}
                      />
                    ) : (
                      <div style={{ color: "var(--text-4)", fontSize: 11 }}>No exchange flow data</div>
                    )}
                    <div style={{ marginTop: 12, padding: 8, background: "var(--bg-void)", borderRadius: 4 }}>
                      <div style={{ fontSize: 10, color: "var(--text-3)" }}>
                        {tokenDetail.arkham_flows.total_entities_tracked ?? 0} entities tracked for {symbol}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right: Top inflows/outflows */}
                <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                  <div className="arkham-card">
                    <div className="arkham-card-header">
                      <span className="arkham-card-title" style={{ color: "var(--green)" }}>Top Inflows</span>
                    </div>
                    <div className="arkham-card-body">
                      {tokenDetail.arkham_flows.top_inflows && tokenDetail.arkham_flows.top_inflows.length > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          {tokenDetail.arkham_flows.top_inflows.map((f: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                              <span style={{ fontSize: 12, color: "var(--text-2)" }}>{f.entity}</span>
                              <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--green)" }}>{formatUsd(f.amount)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div style={{ color: "var(--text-4)", fontSize: 11 }}>No inflow data</div>
                      )}
                    </div>
                  </div>

                  <div className="arkham-card">
                    <div className="arkham-card-header">
                      <span className="arkham-card-title" style={{ color: "var(--red)" }}>Top Outflows</span>
                    </div>
                    <div className="arkham-card-body">
                      {tokenDetail.arkham_flows.top_outflows && tokenDetail.arkham_flows.top_outflows.length > 0 ? (
                        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                          {tokenDetail.arkham_flows.top_outflows.map((f: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                              <span style={{ fontSize: 12, color: "var(--text-2)" }}>{f.entity}</span>
                              <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--red)" }}>{formatUsd(f.amount)}</span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div style={{ color: "var(--text-4)", fontSize: 11 }}>No outflow data</div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── ENTITY VIEW ── */}
      {/* legacy entity view disabled
        <div className="arkham-content">
          <div className="arkham-hero">
            <div className="arkham-hero-top">
              <div className="arkham-hero-icon" style={{ background: "var(--amber-dim)", color: "var(--amber)" }}>
                {(entityData.entity?.name || getSymbol()).slice(0, 2).toUpperCase()}
              </div>
              <div className="arkham-hero-info">
                <div className="arkham-hero-name">{entityData.entity?.name || getSymbol()}</div>
                <div className="arkham-hero-sym">{entityData.entity?.type || "Entity"}</div>
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
            <div className="arkham-card">
              <div className="arkham-card-header">
                <span className="arkham-card-title">Entity Info</span>
              </div>
              <div className="arkham-card-body">
                <div className="arkham-metrics">
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Type</span>
                    <span className="arkham-metric-value">{entityData.entity?.type || "—"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Category</span>
                    <span className="arkham-metric-value">{entityData.entity?.category || "—"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Wallets</span>
                    <span className="arkham-metric-value">{entityData.wallets_count || 0}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Chains</span>
                    <span className="arkham-metric-value">{(entityData.entity?.chains || []).join(", ") || "—"}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="arkham-card">
              <div className="arkham-card-header">
                <span className="arkham-card-title">Flow Summary</span>
              </div>
              <div className="arkham-card-body">
                {entityData.flow ? (
                  <div className="arkham-metrics">
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">Net Flow</span>
                      <span className="arkham-metric-value">{formatUsd(entityData.flow.net_flow)}</span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">Inflow</span>
                      <span className="arkham-metric-value" style={{ color: "var(--green)" }}>{formatUsd(entityData.flow.inflow)}</span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">Outflow</span>
                      <span className="arkham-metric-value" style={{ color: "var(--red)" }}>{formatUsd(entityData.flow.outflow)}</span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">Transactions</span>
                      <span className="arkham-metric-value">{entityData.flow.tx_count || 0}</span>
                    </div>
                  </div>
                ) : (
                  <div style={{ color: "var(--text-4)", fontSize: 11 }}>No flow data available</div>
                )}
              </div>
            </div>
          </div>

          {entityData.wallets && entityData.wallets.length > 0 && (
            <div className="arkham-card" style={{ marginTop: 16 }}>
              <div className="arkham-card-header">
                <span className="arkham-card-title">Known Wallets ({entityData.wallets.length})</span>
              </div>
              <div className="arkham-card-body" style={{ padding: 0 }}>
                <table className="arkham-holders-table">
                  <thead><tr><th>#</th><th>Address</th><th>Chain</th><th>Label</th></tr></thead>
                  <tbody>
                    {entityData.wallets.slice(0, 20).map((w: any, i: number) => (
                      <tr key={w.address || i}>
                        <td><span className={`arkham-rank ${i < 3 ? "top" : ""}`}>{i + 1}</span></td>
                        <td className="addr">{truncateAddr(w.address)}</td>
                        <td>{w.chain || "ethereum"}</td>
                        <td>{w.label ? <span className="arkham-entity-label">{w.label}</span> : <span style={{ color: "var(--text-4)" }}>—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      */}

      {!loading && isEntity && entityData && (
        <EntityExplorerSection
          entityData={entityData}
          entityIntelligence={entityIntelligence}
          entityCoverage={entityCoverage}
          entityObservedHoldings={entityObservedHoldings}
          entityObservedWallets={entityObservedWallets}
          entityActivity={entityActivity}
          entityCounterparties={entityCounterparties}
          entityTopTags={entityTopTags}
          entityChains={entityChains}
          entitySnapshotStatus={entitySnapshotStatus}
          entitySnapshotRetryAfterSeconds={entitySnapshotRetryAfterSeconds}
          fallbackSymbol={getSymbol()}
          truncateAddr={truncateAddr}
          formatUsd={formatUsd}
          formatTokenAmount={formatTokenAmount}
          titleCase={titleCase}
          activityTimeAgo={activityTimeAgo}
        />
      )}

      {/* ── ADDRESS VIEW ── */}
      {!loading && isAddress && addressData && (
        <div className="arkham-content">
          <div className="arkham-hero">
            <div className="arkham-hero-top">
              <div className="arkham-hero-icon" style={{ background: "var(--cyan-dim)", color: "var(--cyan)" }}>
                <LogoAvatar
                  name={addressData.data?.entity || addressData.data?.label || "Address"}
                  symbol={addressData.chain || "addr"}
                  size={40}
                  title={addressData.data?.entity || addressData.data?.label || "Address"}
                />
              </div>
              <div className="arkham-hero-info">
                <div className="arkham-hero-name" style={{ fontFamily: "var(--font-mono)", fontSize: 14 }}>
                  {addressData.address || entityId}
                </div>
                <div className="arkham-hero-sym">
                  {addressData.identified ? "Identified" : "Unknown"} · {addressData.chain || "ethereum"}
                </div>
                {addressData.data?.label && (
                  <span className="arkham-hero-badge" style={{ color: "var(--cyan)", borderColor: "var(--cyan)" }}>
                    {addressData.data.label}
                  </span>
                )}
                {addressData.data?.entity && (
                  <span className="arkham-hero-badge" style={{ color: "var(--amber)", borderColor: "var(--amber)" }}>
                    {addressData.data.entity}
                  </span>
                )}
                {getExplorerAddressUrl(addressData.address || entityId, addressData.chain) && (
                  <a
                    className="arkham-link"
                    href={getExplorerAddressUrl(addressData.address || entityId, addressData.chain) || undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ marginTop: 10, display: "inline-flex", width: "fit-content" }}
                  >
                    Open {titleCase(normalizeExplorerChain(addressData.chain))} Explorer ↗
                  </a>
                )}
              </div>
            </div>
          </div>

          {!addressData.identified && (
            <div className="arkham-empty" style={{ marginTop: 20 }}>
              <div className="arkham-empty-icon">?</div>
              <div className="arkham-empty-title">Address not identified</div>
              <div className="arkham-empty-desc">
                This address is not in the Arkham database. Run a scrape to discover labels.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty fallback */}
      {!loading && !isToken && !isEntity && !isAddress && entityId && (
        <div className="arkham-content">
          <div className="arkham-empty">
            <div className="arkham-empty-icon">◎</div>
            <div className="arkham-empty-title">Unknown entity type</div>
            <div className="arkham-empty-desc">ID: {entityId}</div>
          </div>
        </div>
      )}
    </div>
  )
}



