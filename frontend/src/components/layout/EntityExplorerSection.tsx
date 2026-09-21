import { useEffect, useState } from "react"
import LogoAvatar from "../LogoAvatar"
import { getExplorerAddressUrl, getExplorerTxUrl } from "../../services/explorerLinks"
import { useLanguage } from "../../i18n"

interface EntityExplorerSectionProps {
  entityData: any
  entityIntelligence: any
  entityCoverage: any
  entityObservedHoldings: any[]
  entityObservedWallets: any[]
  entityActivity: any[]
  entityCounterparties: any[]
  entityTopTags: any[]
  entityChains: string[]
  entitySnapshotStatus?: string | null
  entitySnapshotRetryAfterSeconds?: number | null
  fallbackSymbol: string
  truncateAddr: (addr: string, len?: number) => string
  formatUsd: (value: number | string | null | undefined) => string
  formatTokenAmount: (value: number | null | undefined, symbol?: string) => string
  titleCase: (value: string | null | undefined) => string
  activityTimeAgo: (value: number | string | null | undefined) => string
}

type EntityTabId = "overview" | "portfolio" | "wallets" | "counterparties" | "transfers"
type OverviewPortfolioView = "portfolio" | "chains" | "wallets"
type OverviewSurfaceView = "history" | "tokens" | "chains"
type OverviewIntelView = "venues" | "counterparties" | "clusters"
type TransferFilter = "all" | "inflow" | "outflow"
type HistoryRangeId = "1w" | "1m" | "3m" | "all"

function compactLabel(value: string | null | undefined): string {
  return String(value || "").replace(/_/g, " ").trim()
}

function compactIdentifier(value: string | null | undefined, head = 12, tail = 6): string {
  const text = String(value || "").trim()
  if (!text) return "-"
  if (text.length <= head + tail + 3) return text
  if (/\s|:|\./.test(text)) return text
  return `${text.slice(0, head)}...${text.slice(-tail)}`
}

function formatPct(value: number | null | undefined, decimals = 2): string {
  if (value == null || Number.isNaN(value)) return "-"
  const sign = value >= 0 ? "+" : ""
  return `${sign}${value.toFixed(decimals)}%`
}

function safeNumber(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function normalizeMatch(value: unknown): string {
  return String(value || "").trim().toLowerCase()
}

function assetSurfaceKey(holding: any): string {
  const chain = String(holding?.chain || "unknown").trim().toLowerCase()
  const identifier = String(
    holding?.contract_address ||
      holding?.asset_id ||
      holding?.symbol ||
      holding?.name ||
      "unknown",
  )
    .trim()
    .toLowerCase()
  return `${chain}:${identifier}`
}

function formatSigned(value: number | null | undefined, formatter: (value: number) => string): string {
  if (value == null || Number.isNaN(value)) return "-"
  if (value === 0) return formatter(0)
  return `${value > 0 ? "+" : "-"}${formatter(Math.abs(value))}`
}

function formatHistoryAxisLabel(timestamp: number | null | undefined, spanDays = 0): string {
  if (!timestamp) return "-"
  const date = new Date(timestamp * 1000)
  if (spanDays > 365 * 2) {
    return date.toLocaleDateString(undefined, { year: "numeric" })
  }
  if (spanDays > 150) {
    return date.toLocaleDateString(undefined, { month: "short", year: "2-digit" })
  }
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short" })
}

function formatHistoryRange(startTs: number | null | undefined, endTs: number | null | undefined): string {
  if (!startTs && !endTs) return "-"
  if (!startTs || !endTs) {
    return formatHistoryAxisLabel(startTs || endTs || null)
  }
  const start = new Date(startTs * 1000)
  const end = new Date(endTs * 1000)
  const sameYear = start.getUTCFullYear() === end.getUTCFullYear()
  const startLabel = start.toLocaleDateString(undefined, sameYear ? { day: "numeric", month: "short" } : { day: "numeric", month: "short", year: "numeric" })
  const endLabel = end.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
  return `${startLabel} - ${endLabel}`
}

function downsampleHistorySeries<T extends { key: string }>(points: T[], maxPoints = 72): T[] {
  if (points.length <= maxPoints) return points
  const result: T[] = []
  const lastIndex = points.length - 1
  const seen = new Set<string>()
  for (let index = 0; index < maxPoints; index += 1) {
    const sourceIndex = Math.round((index * lastIndex) / (maxPoints - 1))
    const point = points[sourceIndex]
    if (point && !seen.has(point.key)) {
      seen.add(point.key)
      result.push(point)
    }
  }
  return result
}

function EmptyState({
  icon,
  title,
  description,
}: {
  icon: string
  title: string
  description: string
}) {
  return (
    <div className="arkham-empty" style={{ marginTop: 20 }}>
      <div className="arkham-empty-icon">{icon}</div>
      <div className="arkham-empty-title">{title}</div>
      <div className="arkham-empty-desc">{description}</div>
    </div>
  )
}

function PanelTabs<T extends string>({
  items,
  active,
  onChange,
}: {
  items: Array<{ id: T; label: string; count?: number }>
  active: T
  onChange: (value: T) => void
}) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
      {items.map((item) => (
        <button
          key={item.id}
          onClick={() => onChange(item.id)}
          style={{
            cursor: "pointer",
            borderRadius: 999,
            border: `1px solid ${active === item.id ? "var(--blue-bright)" : "var(--border)"}`,
            background: active === item.id ? "rgba(50,130,255,0.12)" : "var(--bg-void)",
            color: active === item.id ? "var(--blue-bright)" : "var(--text-3)",
            padding: "6px 10px",
            fontSize: 10,
            textTransform: "uppercase",
            letterSpacing: 0.45,
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span>{item.label}</span>
          {item.count != null && (
            <span
              style={{
                padding: "1px 6px",
                borderRadius: 999,
                background: "var(--bg-card)",
                color: active === item.id ? "var(--blue-bright)" : "var(--text-4)",
                fontFamily: "var(--font-mono)",
              }}
            >
              {item.count}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

function DistributionBars({
  rows,
  valueFormatter,
  onSelect,
  selectedKey,
}: {
  rows: Array<{ key: string; label: string; value: number; meta?: string }>
  valueFormatter: (value: number) => string
  onSelect?: (key: string) => void
  selectedKey?: string | null
}) {
  const maxValue = Math.max(...rows.map((row) => row.value || 0), 1)

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {rows.map((row) => (
        <button
          key={row.key}
          onClick={() => onSelect?.(row.key)}
          style={{
            cursor: onSelect ? "pointer" : "default",
            border: `1px solid ${selectedKey === row.key ? "var(--blue-bright)" : "var(--border)"}`,
            background: selectedKey === row.key ? "rgba(50,130,255,0.08)" : "var(--bg-void)",
            borderRadius: 12,
            padding: "10px 12px",
            textAlign: "left",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 6 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ color: "var(--text-1)", fontSize: 12, fontWeight: 600 }}>{row.label}</div>
              {row.meta && <div style={{ color: "var(--text-4)", fontSize: 10 }}>{row.meta}</div>}
            </div>
            <div style={{ color: "var(--text-2)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
              {valueFormatter(row.value)}
            </div>
          </div>
          <div style={{ width: "100%", height: 8, borderRadius: 999, background: "rgba(255,255,255,0.03)", overflow: "hidden" }}>
            <div
              style={{
                width: `${Math.max((row.value / maxValue) * 100, row.value > 0 ? 8 : 0)}%`,
                height: "100%",
                borderRadius: 999,
                background: "linear-gradient(90deg, var(--blue-bright), var(--cyan))",
              }}
            />
          </div>
        </button>
      ))}
    </div>
  )
}

function MiniAreaChart({
  points,
  valueKey,
  selectedKey,
  onSelect,
  color = "var(--blue-bright)",
  height = 122,
  showSelectorButtons = true,
  showAxes = false,
  showPointMarkers = true,
  valueFormatter,
}: {
  points: Array<{ key: string; label: string; [key: string]: unknown }>
  valueKey: string
  selectedKey?: string | null
  onSelect?: (key: string) => void
  color?: string
  height?: number
  showSelectorButtons?: boolean
  showAxes?: boolean
  showPointMarkers?: boolean
  valueFormatter?: (value: number) => string
}) {
  const rows = points
    .map((point, index) => ({
      key: String(point.key || `point-${index}`),
      label: String(point.label || `Point ${index + 1}`),
      value: safeNumber((point as any)[valueKey]),
      timestamp: Number((point as any).timestamp ?? (point as any).end_ts ?? (point as any).start_ts ?? 0) || null,
    }))
    .filter((point) => Number.isFinite(point.value))

  if (rows.length === 0) {
    return null
  }

  const width = 720
  const padLeft = showAxes ? 54 : 16
  const padRight = 12
  const padTop = 12
  const padBottom = showAxes ? 30 : 12
  const min = Math.min(...rows.map((point) => point.value))
  const max = Math.max(...rows.map((point) => point.value))
  const range = max - min || 1
  const firstTimestamp = rows[0]?.timestamp || null
  const lastTimestamp = rows[rows.length - 1]?.timestamp || null
  const spanDays = firstTimestamp && lastTimestamp ? Math.max(1, (lastTimestamp - firstTimestamp) / 86400) : 0
  const usableHeight = height - padTop - padBottom

  const coords = rows.map((point, index) => {
    const x = rows.length === 1 ? width / 2 : padLeft + (index * (width - padLeft - padRight)) / (rows.length - 1)
    const y = padTop + ((max - point.value) / range) * usableHeight
    return { ...point, x, y }
  })

  const linePath = coords
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ")
  const areaBase = height - padBottom
  const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${areaBase} L ${coords[0].x} ${areaBase} Z`
  const selectedPoint = coords.find((point) => point.key === selectedKey) || coords[coords.length - 1]
  const yTicks = showAxes
    ? Array.from({ length: 5 }, (_, index) => {
        const ratio = index / 4
        const value = max - ratio * range
        const y = padTop + ratio * usableHeight
        return { value, y }
      })
    : []
  const xTickIndexes = Array.from(new Set([0, Math.floor((coords.length - 1) * 0.25), Math.floor((coords.length - 1) * 0.5), Math.floor((coords.length - 1) * 0.75), coords.length - 1]))
  const xTicks = xTickIndexes.map((index) => coords[index]).filter(Boolean)
  const gradientId = `mini-area-${valueKey.replace(/[^a-z0-9_-]/gi, "")}-${rows.length}-${height}`

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} style={{ display: "block" }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={showAxes ? 0.24 : 0.12} />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        {(showAxes ? yTicks : [0.25, 0.5, 0.75].map((ratio) => ({ y: padTop + ratio * usableHeight, value: null }))).map((tick, index) => (
          <g key={`grid-${index}`}>
            <line
              x1={padLeft}
              y1={tick.y}
              x2={width - padRight}
              y2={tick.y}
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="1"
            />
            {showAxes && valueFormatter && tick.value != null && (
              <text
                x={padLeft - 8}
                y={tick.y + 4}
                textAnchor="end"
                fill="var(--text-4)"
                fontSize="10"
                fontFamily="var(--font-mono)"
              >
                {valueFormatter(tick.value)}
              </text>
            )}
          </g>
        ))}
        {selectedPoint && showAxes && (
          <line
            x1={selectedPoint.x}
            y1={padTop}
            x2={selectedPoint.x}
            y2={areaBase}
            stroke="rgba(50,130,255,0.22)"
            strokeWidth="1"
            strokeDasharray="4 4"
          />
        )}
        <path d={areaPath} fill={`url(#${gradientId})`} />
        <path d={linePath} fill="none" stroke={color} strokeWidth={showAxes ? "2.5" : "2"} strokeLinecap="round" strokeLinejoin="round" />
        {coords.map((point) => {
          const isActive = selectedPoint?.key === point.key
          if (!showPointMarkers && !isActive) return null
          return (
            <circle
              key={point.key}
              cx={point.x}
              cy={point.y}
              r={isActive ? 4.2 : showAxes ? 2.2 : 3}
              fill={isActive ? color : "var(--bg-card)"}
              stroke={color}
              strokeWidth="1.5"
              style={{ cursor: onSelect ? "pointer" : "default" }}
              onClick={() => onSelect?.(point.key)}
            />
          )
        })}
        {showAxes &&
          xTicks.map((point) => (
            <text
              key={`x-${point.key}`}
              x={point.x}
              y={height - 8}
              textAnchor="middle"
              fill="var(--text-4)"
              fontSize="10"
              fontFamily="var(--font-mono)"
            >
              {formatHistoryAxisLabel(point.timestamp, spanDays)}
            </text>
          ))}
      </svg>

      {showSelectorButtons && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
          {rows.map((point) => (
            <button
              key={point.key}
              onClick={() => onSelect?.(point.key)}
              style={{
                cursor: onSelect ? "pointer" : "default",
                borderRadius: 999,
                border: `1px solid ${selectedKey === point.key ? color : "var(--border)"}`,
                background: selectedKey === point.key ? "rgba(50,130,255,0.08)" : "var(--bg-void)",
                color: selectedKey === point.key ? "var(--text-1)" : "var(--text-3)",
                padding: "5px 9px",
                fontSize: 10,
              }}
            >
              {point.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function EntityExplorerSection({
  entityData,
  entityIntelligence,
  entityCoverage,
  entityObservedHoldings,
  entityObservedWallets,
  entityActivity,
  entityCounterparties,
  entityTopTags,
  entityChains,
  entitySnapshotStatus,
  entitySnapshotRetryAfterSeconds,
  fallbackSymbol,
  truncateAddr,
  formatUsd,
  formatTokenAmount,
  titleCase,
  activityTimeAgo,
}: EntityExplorerSectionProps) {
  const { language, t } = useLanguage()
  const flowDirectionLabel = (direction: string | null | undefined) =>
    direction === "inflow" ? t("entity.inflow", "Inflow") : direction === "outflow" ? t("entity.outflow", "Outflow") : titleCase(direction)
  const localizedActivityTimeAgo = (value: number | string | null | undefined) => {
    const raw = activityTimeAgo(value)
    if (language !== "fr") return raw
    return raw
      .replace(/\bjust now\b/gi, "maintenant")
      .replace(/\bago\b/gi, "")
      .replace(/\bminute(s)?\b/gi, "min")
      .replace(/\bmin(s)?\b/gi, "min")
      .replace(/\bhour(s)?\b/gi, "h")
      .replace(/\bday(s)?\b/gi, "j")
      .replace(/\bweek(s)?\b/gi, "sem")
      .replace(/\bmonth(s)?\b/gi, "mois")
      .replace(/\byear(s)?\b/gi, "an")
      .trim()
  }
  const [activeTab, setActiveTab] = useState<EntityTabId>("overview")
  const [portfolioView, setPortfolioView] = useState<OverviewPortfolioView>("portfolio")
  const [surfaceView, setSurfaceView] = useState<OverviewSurfaceView>("history")
  const [intelView, setIntelView] = useState<OverviewIntelView>("venues")
  const [historyRange, setHistoryRange] = useState<HistoryRangeId>("all")
  const [surfaceViewTouched, setSurfaceViewTouched] = useState(false)
  const [intelViewTouched, setIntelViewTouched] = useState(false)
  const [transferFilter, setTransferFilter] = useState<TransferFilter>("all")
  const [selectedHoldingKey, setSelectedHoldingKey] = useState<string | null>(null)
  const [selectedSurfaceTokenKey, setSelectedSurfaceTokenKey] = useState<string | null>(null)
  const [selectedHistoryKey, setSelectedHistoryKey] = useState<string | null>(null)
  const [selectedBalanceBucketKey, setSelectedBalanceBucketKey] = useState<string | null>(null)
  const [selectedNetworkKey, setSelectedNetworkKey] = useState<string | null>(null)
  const [selectedWalletAddress, setSelectedWalletAddress] = useState<string | null>(null)
  const [selectedCounterpartyKey, setSelectedCounterpartyKey] = useState<string | null>(null)
  const [selectedVenueKey, setSelectedVenueKey] = useState<string | null>(null)
  const [selectedTransferKey, setSelectedTransferKey] = useState<string | null>(null)

  const entityName = entityData?.entity?.name || fallbackSymbol
  const entityType = titleCase(entityData?.entity?.type || "entity")
  const entityCategory = entityData?.entity?.category ? titleCase(entityData.entity.category) : null
  const entityProfile = entityData?.profile || {}
  const sourceLabel = entityData?.entity?.source ? compactLabel(entityData.entity.source) : null
  const profileDescription = entityProfile?.description || entityData?.entity?.description || null
  const observedWalletCount = entityCoverage?.observed_wallets || entityData?.wallets_count || 0
  const observedAssetCount = entityCoverage?.observed_tokens || entityObservedHoldings.length || 0
  const recentActivityCount = entityCoverage?.recent_activity_count || entityActivity.length || 0
  const sourceTrace = Array.isArray(entityIntelligence?.source_trace)
    ? entityIntelligence.source_trace
    : Array.isArray(entityCoverage?.source_trace)
      ? entityCoverage.source_trace
      : []
  const rpcVerifiedTokens = safeNumber(entityCoverage?.rpc_verified_tokens)
  const highConfidenceSources = sourceTrace.filter((item: any) => item?.confidence === "high").length

  const normalizedFlow = {
    inflow: entityData?.flow?.inflow ?? entityData?.flow?.inflow_24h_usd ?? null,
    outflow: entityData?.flow?.outflow ?? entityData?.flow?.outflow_24h_usd ?? null,
    net: entityData?.flow?.net_flow ?? entityData?.flow?.net_flow_24h_usd ?? null,
    txCount: entityData?.flow?.tx_count ?? entityData?.flow?.recent_movements ?? recentActivityCount,
  }

  const badgeItems = Array.from(
    new Set(
      [
        entityType,
        entityCategory,
        ...(entityData?.entity?.badges || []),
        ...(entityData?.entity?.tags || []),
        ...(entityProfile?.badges || []),
      ]
        .map((item: any) => compactLabel(item))
        .filter(Boolean),
    ),
  )

  const profileLinks = [
    entityProfile?.website || entityData?.entity?.website
      ? { label: "Website", url: entityProfile?.website || entityData?.entity?.website }
      : null,
    entityProfile?.socials?.x ? { label: "X", url: entityProfile.socials.x } : null,
    entityProfile?.socials?.linkedin ? { label: "LinkedIn", url: entityProfile.socials.linkedin } : null,
    entityProfile?.crunchbase || entityProfile?.socials?.crunchbase
      ? { label: "Crunchbase", url: entityProfile?.crunchbase || entityProfile?.socials?.crunchbase }
      : null,
  ].filter(Boolean) as Array<{ label: string; url: string }>

  const focusAssets = Array.from(
    new Set(
      [
        ...(entityProfile?.coverage_pairs || []).map((pair: any) => String(pair?.symbol || "").toUpperCase()),
        ...(entityProfile?.coverage_tokens || []).map((symbol: any) => String(symbol || "").toUpperCase()),
      ].filter(Boolean),
    ),
  )

  const focusNetworks = Array.from(
    new Set(
      [
        ...entityChains,
        ...(entityProfile?.coverage_pairs || []).map((pair: any) => String(pair?.chain || "")),
        ...(entityProfile?.coverage_chains || []).map((chain: any) => String(chain || "")),
      ]
        .map((chain) => compactLabel(chain))
        .filter(Boolean),
    ),
  )

  const holdings = [...entityObservedHoldings]
    .map((holding) => ({
      ...holding,
      key: assetSurfaceKey(holding),
      value: safeNumber(holding.estimated_value_usd),
      walletCount: safeNumber(holding.wallet_count),
    }))
    .sort((a, b) => (b.value || b.walletCount) - (a.value || a.walletCount))

  const wallets = [...entityObservedWallets]
    .map((wallet) => ({
      ...wallet,
      key: String(wallet.address || ""),
      value: safeNumber(wallet.observed_value_usd),
      tokenCount: safeNumber(wallet.observed_token_count),
      labelText: wallet.label || truncateAddr(wallet.address),
    }))
    .sort((a, b) => (b.value || b.tokenCount) - (a.value || a.tokenCount))

  const counterparties = [...entityCounterparties]
    .map((cp) => ({
      ...cp,
      key: String(cp.address || cp.label || ""),
      value: safeNumber(cp.value_usd) || safeNumber(cp.tx_count),
      labelText: cp.label || truncateAddr(cp.address),
      tableLabel:
        cp.label && cp.address && String(cp.label).toLowerCase() === String(cp.address).toLowerCase()
          ? truncateAddr(cp.address, 6)
          : compactIdentifier(cp.label || cp.address, 18, 6),
      detailLabel:
        cp.label && cp.address && String(cp.label).toLowerCase() === String(cp.address).toLowerCase()
          ? t("entity.unknownCounterparty", "Unlabeled counterparty")
          : (cp.label || truncateAddr(cp.address)),
    }))
    .sort((a, b) => b.value - a.value)

  const allTransfers = [...entityActivity]
    .sort((a, b) => safeNumber(b.timestamp) - safeNumber(a.timestamp))

  const transfers = [...allTransfers]
    .filter((item) => {
      if (transferFilter === "all") return true
      return item.direction === transferFilter
    })

  const topRoleBreakdown = Array.from(
    wallets.reduce((acc: Map<string, number>, wallet) => {
      const roles = (wallet.flags || []).length ? wallet.flags : [wallet.wallet_type || "wallet"]
      roles
        .map((role: string) => compactLabel(role))
        .filter(Boolean)
        .forEach((role: string) => {
          acc.set(role, (acc.get(role) || 0) + 1)
        })
      return acc
    }, new Map<string, number>()),
  )
    .map(([role, count]) => ({ role, count }))
    .sort((a, b) => b.count - a.count)

  const totalObservedValue =
    safeNumber(entityIntelligence?.estimated_total_value_usd) ||
    holdings.reduce((sum, holding) => sum + holding.value, 0)

  const chainExposure = focusNetworks.map((chain) => {
    const holdingsForChain = holdings.filter((holding) => compactLabel(holding.chain).toLowerCase() === chain.toLowerCase())
    const walletsForChain = wallets.filter((wallet) => compactLabel(wallet.chain).toLowerCase() === chain.toLowerCase())
    const totalValue = holdingsForChain.reduce((sum, holding) => sum + holding.value, 0)
    return {
      key: chain.toLowerCase(),
      chain,
      holdings: holdingsForChain.length,
      wallets: walletsForChain.length,
      totalValue,
    }
  })

  const surfaceData = entityIntelligence?.surfaces || {}
  const historyByChain =
    surfaceData.history_by_chain && typeof surfaceData.history_by_chain === "object"
      ? surfaceData.history_by_chain
      : {}

  const balanceHistory = [...(surfaceData.balances_history || [])]
    .map((bucket: any, index: number) => ({
      ...bucket,
      key: String(bucket?.key || `bucket-${index}`),
      label: String(bucket?.label || `Bucket ${index + 1}`),
      timestamp: safeNumber(bucket?.end_ts) || safeNumber(bucket?.start_ts) || null,
      display_value_usd:
        bucket?.balance_estimate_usd != null
          ? safeNumber(bucket.balance_estimate_usd)
          : safeNumber(bucket?.cumulative_net_usd),
      balance_estimate_usd: safeNumber(bucket?.balance_estimate_usd),
      cumulative_net_usd: safeNumber(bucket?.cumulative_net_usd),
      inflow_usd: safeNumber(bucket?.inflow_usd),
      outflow_usd: safeNumber(bucket?.outflow_usd),
      net_usd: safeNumber(bucket?.net_usd),
      tx_count: safeNumber(bucket?.tx_count),
    }))
    .sort((a, b) => safeNumber(a.start_ts) - safeNumber(b.start_ts))

  const historyAggregateMap = new Map<number, number>()
  Object.values(historyByChain).forEach((items: any) => {
    if (!Array.isArray(items)) return
    items.forEach((point: any) => {
      const timestamp = safeNumber(point?.timestamp)
      const usd = safeNumber(point?.usd)
      if (!timestamp || !Number.isFinite(usd)) return
      historyAggregateMap.set(timestamp, (historyAggregateMap.get(timestamp) || 0) + usd)
    })
  })

  const historySeries =
    historyAggregateMap.size > 0
      ? downsampleHistorySeries(
          Array.from(historyAggregateMap.entries())
            .sort((a, b) => a[0] - b[0])
            .map(([timestamp, usd], index) => ({
              key: `history-${timestamp}-${index}`,
              label: formatHistoryAxisLabel(timestamp),
              timestamp,
              value_usd: usd,
            })),
          72,
        )
      : balanceHistory.map((bucket: any, index: number) => ({
          key: String(bucket?.key || `history-bucket-${index}`),
          label: String(bucket?.label || `Bucket ${index + 1}`),
          timestamp: bucket?.timestamp || null,
          value_usd: totalObservedValue > 0 ? safeNumber(bucket?.display_value_usd) : safeNumber(bucket?.cumulative_net_usd),
        }))

  const historyTrackedChains = Object.keys(historyByChain).length || focusNetworks.length || 0
  const latestHistoryTimestamp = safeNumber(historySeries[historySeries.length - 1]?.timestamp) || null
  const historyRangeSeconds =
    historyRange === "1w"
      ? 7 * 86400
      : historyRange === "1m"
        ? 30 * 86400
        : historyRange === "3m"
          ? 90 * 86400
          : null
  const filteredHistorySeries =
    historyRangeSeconds && latestHistoryTimestamp
      ? (() => {
          const cutoff = latestHistoryTimestamp - historyRangeSeconds
          const sliced = historySeries.filter((point: any) => safeNumber(point.timestamp) >= cutoff)
          if (sliced.length >= 2) return sliced
          return historySeries.slice(Math.max(0, historySeries.length - Math.min(historySeries.length, 18)))
        })()
      : historySeries
  const filteredHistoryStartPoint = filteredHistorySeries[0] || null
  const filteredHistoryEndPoint = filteredHistorySeries[filteredHistorySeries.length - 1] || null
  const filteredHistorySpanDays =
    filteredHistoryStartPoint && filteredHistoryEndPoint
      ? Math.max(1, Math.round((safeNumber(filteredHistoryEndPoint.timestamp) - safeNumber(filteredHistoryStartPoint.timestamp)) / 86400))
      : 0
  const historyChainSurface = Object.entries(historyByChain)
    .map(([chain, items]: [string, any]) => {
      const points = Array.isArray(items)
        ? [...items]
            .map((point: any, index: number) => ({
              key: `${chain}-${index}`,
              timestamp: safeNumber(point?.timestamp),
              usd: safeNumber(point?.usd),
            }))
            .filter((point) => point.timestamp && Number.isFinite(point.usd))
            .sort((a, b) => a.timestamp - b.timestamp)
        : []

      if (!points.length) return null

      const filteredPoints =
        historyRangeSeconds && latestHistoryTimestamp
          ? (() => {
              const cutoff = latestHistoryTimestamp - historyRangeSeconds
              const sliced = points.filter((point) => point.timestamp >= cutoff)
              return sliced.length >= 2 ? sliced : points.slice(Math.max(0, points.length - Math.min(points.length, 12)))
            })()
          : points

      const latestPoint = filteredPoints[filteredPoints.length - 1] || points[points.length - 1]
      const startPoint = filteredPoints[0] || points[0]
      if (!latestPoint) return null

      return {
        key: String(chain).toLowerCase(),
        label: compactLabel(chain),
        latestUsd: latestPoint.usd,
        changeUsd: latestPoint.usd - safeNumber(startPoint?.usd),
        pointCount: filteredPoints.length,
      }
    })
    .filter(Boolean)
    .sort((a: any, b: any) => safeNumber(b.latestUsd) - safeNumber(a.latestUsd))
  const historyRangeButtons: Array<{ id: HistoryRangeId; label: string }> = [
    { id: "1w", label: "1W" },
    { id: "1m", label: "1M" },
    { id: "3m", label: "3M" },
    { id: "all", label: "ALL" },
  ]

  const tokenBalanceSurface = (
    surfaceData.token_balance_surface?.length
      ? surfaceData.token_balance_surface
      : holdings.map((holding) => ({
          key: holding.key,
          symbol: holding.symbol,
          name: holding.name,
          chain: holding.chain,
          observed_value_usd: holding.estimated_value_usd,
          wallet_count: holding.wallet_count,
          share_pct: totalObservedValue > 0 ? (safeNumber(holding.estimated_value_usd) / totalObservedValue) * 100 : null,
          recent_inflow_usd: 0,
          recent_outflow_usd: 0,
          recent_net_usd: 0,
          recent_tx_count: 0,
          max_holder_share_pct: holding.max_holder_share_pct,
        }))
  )
    .map((token: any, index: number) => ({
      ...token,
      key: String(token?.key || `${token?.chain || "unknown"}:${token?.symbol || index}`),
      observed_value_usd: token?.observed_value_usd != null ? safeNumber(token.observed_value_usd) : null,
      wallet_count: safeNumber(token?.wallet_count),
      share_pct: token?.share_pct != null ? safeNumber(token.share_pct) : null,
      recent_inflow_usd: safeNumber(token?.recent_inflow_usd),
      recent_outflow_usd: safeNumber(token?.recent_outflow_usd),
      recent_net_usd: safeNumber(token?.recent_net_usd),
      recent_tx_count: safeNumber(token?.recent_tx_count),
      max_holder_share_pct: token?.max_holder_share_pct != null ? safeNumber(token.max_holder_share_pct) : null,
    }))
    .sort((a: any, b: any) =>
      (safeNumber(b.observed_value_usd) || safeNumber(b.recent_tx_count)) -
      (safeNumber(a.observed_value_usd) || safeNumber(a.recent_tx_count)),
    )

  const networkUsage = (
    surfaceData.network_usage?.length
      ? surfaceData.network_usage
      : chainExposure.map((item) => ({
          chain: item.chain,
          observed_value_usd: item.totalValue,
          inflow_usd: 0,
          outflow_usd: 0,
          net_usd: 0,
          tx_count: 0,
          wallet_count: item.wallets,
          asset_count: item.holdings,
        }))
  )
    .map((item: any, index: number) => ({
      ...item,
      key: String(item?.chain || `network-${index}`),
      observed_value_usd: item?.observed_value_usd != null ? safeNumber(item.observed_value_usd) : null,
      inflow_usd: safeNumber(item?.inflow_usd),
      outflow_usd: safeNumber(item?.outflow_usd),
      net_usd: safeNumber(item?.net_usd),
      tx_count: safeNumber(item?.tx_count),
      wallet_count: safeNumber(item?.wallet_count),
      asset_count: safeNumber(item?.asset_count),
    }))
    .sort((a: any, b: any) =>
      (safeNumber(b.observed_value_usd) || Math.abs(safeNumber(b.net_usd)) || safeNumber(b.tx_count)) -
      (safeNumber(a.observed_value_usd) || Math.abs(safeNumber(a.net_usd)) || safeNumber(a.tx_count)),
    )

  const venueUsage = (
    surfaceData.exchange_usage?.length
      ? surfaceData.exchange_usage
      : counterparties.map((cp) => ({
          label: cp.labelText,
          category: "counterparty",
          inflow_usd: 0,
          outflow_usd: 0,
          net_usd: cp.value_usd,
          tx_count: cp.tx_count,
          token_symbols: [],
        }))
  )
    .map((venue: any, index: number) => ({
      ...venue,
      key: String(venue?.label || `venue-${index}`),
      label: String(venue?.label || "Unknown venue"),
      inflow_usd: safeNumber(venue?.inflow_usd),
      outflow_usd: safeNumber(venue?.outflow_usd),
      net_usd: safeNumber(venue?.net_usd),
      tx_count: safeNumber(venue?.tx_count),
      token_symbols: Array.isArray(venue?.token_symbols) ? venue.token_symbols : [],
    }))
    .sort((a: any, b: any) =>
      (Math.abs(safeNumber(b.net_usd)) || safeNumber(b.tx_count)) -
      (Math.abs(safeNumber(a.net_usd)) || safeNumber(a.tx_count)),
    )

  const roleClusters = (
    surfaceData.role_clusters?.length
      ? surfaceData.role_clusters
      : topRoleBreakdown.map((item) => ({
          role: item.role,
          wallet_count: item.count,
          share_pct: wallets.length > 0 ? (item.count / wallets.length) * 100 : null,
        }))
  )
    .map((item: any) => ({
      ...item,
      role: compactLabel(item?.role),
      wallet_count: safeNumber(item?.wallet_count),
      share_pct: item?.share_pct != null ? safeNumber(item.share_pct) : null,
    }))
    .sort((a: any, b: any) => safeNumber(b.wallet_count) - safeNumber(a.wallet_count))

  const selectedHolding =
    holdings.find((holding) => holding.key === selectedHoldingKey) ||
    holdings[0] ||
    null

  const selectedSurfaceToken =
    tokenBalanceSurface.find((token: any) => token.key === selectedSurfaceTokenKey) ||
    tokenBalanceSurface[0] ||
    null

  const selectedHistoryPoint =
    filteredHistorySeries.find((point: any) => point.key === selectedHistoryKey) ||
    filteredHistorySeries[filteredHistorySeries.length - 1] ||
    null
  const selectedBalanceBucket =
    balanceHistory.find((bucket: any) => bucket.key === selectedBalanceBucketKey) ||
    balanceHistory[balanceHistory.length - 1] ||
    null
  const historyStartPoint = filteredHistorySeries[0] || null
  const historyPeakPoint =
    filteredHistorySeries.reduce((peak: any, point: any) => ((point?.value_usd || 0) > (peak?.value_usd || 0) ? point : peak), filteredHistorySeries[0] || null) || null
  const historyChangeSinceStart =
    historyStartPoint && selectedHistoryPoint
      ? safeNumber(selectedHistoryPoint.value_usd) - safeNumber(historyStartPoint.value_usd)
      : null

  const selectedNetwork =
    networkUsage.find((item: any) => item.key === selectedNetworkKey) ||
    networkUsage[0] ||
    null

  const defaultExplorerChain =
    selectedNetwork?.chain ||
    focusNetworks[0] ||
    entityData?.entity?.chains?.[0] ||
    "ethereum"

  const selectedWallet =
    wallets.find((wallet) => wallet.key === selectedWalletAddress) ||
    wallets[0] ||
    null

  const selectedCounterparty =
    counterparties.find((cp) => cp.key === selectedCounterpartyKey) ||
    counterparties[0] ||
    null

  const selectedVenue =
    venueUsage.find((item: any) => item.key === selectedVenueKey) ||
    venueUsage[0] ||
    null

  const selectedTransfer =
    transfers.find((item) => item.tx_hash === selectedTransferKey) ||
    transfers[0] ||
    null

  const selectedWalletTransferMatches = selectedWallet
    ? allTransfers.filter((item) => normalizeMatch(item.wallet_address) === normalizeMatch(selectedWallet.address))
    : []

  const selectedCounterpartyTransferMatches = selectedCounterparty
    ? allTransfers.filter((item) => {
        const counterpartyAddress = normalizeMatch(item.counterparty_address)
        const counterpartyLabel = normalizeMatch(item.counterparty_label)
        const selectedAddress = normalizeMatch(selectedCounterparty.address)
        const selectedLabel = normalizeMatch(selectedCounterparty.label)
        return (
          (!!selectedAddress && counterpartyAddress === selectedAddress) ||
          (!!selectedLabel && counterpartyLabel === selectedLabel)
        )
      })
    : []

  const selectedWalletChain = selectedWallet?.chain || defaultExplorerChain
  const selectedWalletExplorerUrl = selectedWallet?.address
    ? getExplorerAddressUrl(selectedWallet.address, selectedWalletChain)
    : null
  const selectedCounterpartyChain =
    selectedCounterpartyTransferMatches[0]?.chain ||
    selectedWalletChain ||
    defaultExplorerChain
  const selectedCounterpartyExplorerUrl = selectedCounterparty?.address
    ? getExplorerAddressUrl(selectedCounterparty.address, selectedCounterpartyChain)
    : null
  const normalizedSelectedVenueLabel = normalizeMatch(selectedVenue?.label)
  const selectedVenueTransferMatches = selectedVenue
    ? allTransfers.filter((item) => {
        const counterpartyEntity = normalizeMatch(item.counterparty_entity)
        const counterpartyLabel = normalizeMatch(item.counterparty_label)
        return !!normalizedSelectedVenueLabel && (
          counterpartyEntity === normalizedSelectedVenueLabel ||
          (!!counterpartyLabel && counterpartyLabel.includes(normalizedSelectedVenueLabel)) ||
          (!!counterpartyEntity && normalizedSelectedVenueLabel.includes(counterpartyEntity))
        )
      })
    : []
  const selectedVenueCounterpartyMatch = selectedVenue
    ? counterparties.find((cp) => {
        const counterpartyLabel = normalizeMatch(cp.label || cp.labelText)
        return !!normalizedSelectedVenueLabel && !!counterpartyLabel && (
          counterpartyLabel.includes(normalizedSelectedVenueLabel) ||
          normalizedSelectedVenueLabel.includes(counterpartyLabel)
        )
      }) || null
    : null
  const venueTotalFlow = venueUsage.reduce((sum: number, venue: any) => sum + Math.abs(safeNumber(venue.net_usd)), 0)
  const selectedVenueGrossFlow = selectedVenue
    ? safeNumber(selectedVenue.inflow_usd) + safeNumber(selectedVenue.outflow_usd)
    : null
  const selectedVenueFlowShare =
    selectedVenue && venueTotalFlow > 0
      ? (Math.abs(safeNumber(selectedVenue.net_usd)) / venueTotalFlow) * 100
      : null
  const selectedVenueDirectionBias =
    selectedVenue && safeNumber(selectedVenue.inflow_usd) > safeNumber(selectedVenue.outflow_usd)
      ? t("entity.inbound", "Inbound")
      : selectedVenue && safeNumber(selectedVenue.outflow_usd) > safeNumber(selectedVenue.inflow_usd)
        ? t("entity.outbound", "Outbound")
        : t("entity.balanced", "Balanced")
  const filteredTransferInflowUsd = transfers
    .filter((item) => item.direction === "inflow")
    .reduce((sum, item) => sum + safeNumber(item.value_usd), 0)
  const filteredTransferOutflowUsd = transfers
    .filter((item) => item.direction === "outflow")
    .reduce((sum, item) => sum + safeNumber(item.value_usd), 0)
  const filteredTransferNetUsd = filteredTransferInflowUsd - filteredTransferOutflowUsd
  const filteredTransferChains = Array.from(
    new Set(
      transfers
        .map((item) => compactLabel(item.chain))
        .filter(Boolean),
    ),
  )
  const selectedTransferChain = selectedTransfer?.chain || defaultExplorerChain
  const selectedTransferTxUrl = selectedTransfer?.tx_hash
    ? getExplorerTxUrl(selectedTransfer.tx_hash, selectedTransferChain)
    : null
  const selectedTransferWalletUrl = selectedTransfer?.wallet_address
    ? getExplorerAddressUrl(selectedTransfer.wallet_address, selectedTransferChain)
    : null
  const selectedTransferCounterpartyUrl = selectedTransfer?.counterparty_address
    ? getExplorerAddressUrl(selectedTransfer.counterparty_address, selectedTransferChain)
    : null
  const selectedTransferFromUrl = selectedTransfer?.from
    ? getExplorerAddressUrl(selectedTransfer.from, selectedTransferChain)
    : null
  const selectedTransferToUrl = selectedTransfer?.to
    ? getExplorerAddressUrl(selectedTransfer.to, selectedTransferChain)
    : null

  useEffect(() => {
    if (filteredHistorySeries.length === 0) {
      if (selectedHistoryKey !== null) setSelectedHistoryKey(null)
      return
    }
    if (!selectedHistoryKey || !filteredHistorySeries.some((point: any) => point.key === selectedHistoryKey)) {
      setSelectedHistoryKey(filteredHistorySeries[filteredHistorySeries.length - 1].key)
    }
  }, [filteredHistorySeries, selectedHistoryKey])

  useEffect(() => {
    if (balanceHistory.length === 0) {
      if (selectedBalanceBucketKey !== null) setSelectedBalanceBucketKey(null)
      return
    }
    if (!selectedBalanceBucketKey || !balanceHistory.some((bucket: any) => bucket.key === selectedBalanceBucketKey)) {
      setSelectedBalanceBucketKey(balanceHistory[balanceHistory.length - 1].key)
    }
  }, [balanceHistory, selectedBalanceBucketKey])

  useEffect(() => {
    if (surfaceViewTouched) return
    if (historySeries.length === 0) {
      if (tokenBalanceSurface.length > 0) {
        setSurfaceView("tokens")
      } else if (networkUsage.length > 0) {
        setSurfaceView("chains")
      }
    }
  }, [surfaceViewTouched, historySeries.length, tokenBalanceSurface.length, networkUsage.length])

  useEffect(() => {
    if (intelViewTouched) return
    if (venueUsage.length === 0) {
      if (counterparties.length > 0) {
        setIntelView("counterparties")
      } else if (roleClusters.length > 0) {
        setIntelView("clusters")
      }
    }
  }, [intelViewTouched, venueUsage.length, counterparties.length, roleClusters.length])

  const transferRows = {
    all: entityActivity.length,
    inflow: entityActivity.filter((item) => item.direction === "inflow").length,
    outflow: entityActivity.filter((item) => item.direction === "outflow").length,
  }

  const tabs: { id: EntityTabId; label: string; count?: number }[] = [
    { id: "overview", label: t("entity.overview", "Overview") },
    { id: "portfolio", label: t("entity.portfolio", "Portfolio"), count: observedAssetCount || undefined },
    { id: "wallets", label: t("entity.wallets", "Wallets"), count: observedWalletCount || undefined },
    { id: "counterparties", label: t("entity.counterparties", "Counterparties"), count: counterparties.length || undefined },
    { id: "transfers", label: t("entity.transfers", "Transfers"), count: recentActivityCount || undefined },
  ]
  const heroSignalItems = [
    {
      key: "snapshot",
      label:
        entitySnapshotStatus === "live"
          ? t("entity.externalSnapshot", "External Snapshot")
          : entitySnapshotStatus === "warming"
            ? t("entity.syncInProgress", "Sync In Progress")
            : entitySnapshotStatus === "disabled"
              ? t("entity.staticMirror", "Static Mirror")
              : t("entity.externalSnapshot", "External Snapshot"),
      tone:
        entitySnapshotStatus === "live"
          ? "var(--cyan)"
          : entitySnapshotStatus === "warming"
            ? "var(--blue-bright)"
            : "var(--text-2)",
      onClick: undefined,
    },
    venueUsage.length > 0
      ? {
          key: "venues",
          label: `${venueUsage.length} ${t("entity.venues", "venues")}`,
          tone: "var(--amber)",
          onClick: () => {
            setActiveTab("overview")
            setIntelViewTouched(true)
            setIntelView("venues")
          },
        }
      : null,
    counterparties.length > 0
      ? {
          key: "counterparties",
          label: `${counterparties.length} ${t("entity.counterparties", "counterparties")}`,
          tone: "var(--blue-bright)",
          onClick: () => setActiveTab("counterparties"),
        }
      : null,
    recentActivityCount > 0
      ? {
          key: "transfers",
          label: `${recentActivityCount} ${t("entity.transfers", "transfers")}`,
          tone: "var(--green)",
          onClick: () => setActiveTab("transfers"),
        }
      : null,
  ].filter(Boolean) as Array<{ key: string; label: string; tone: string; onClick?: (() => void) | undefined }>

  const renderHeroActions = () => (
    <div style={{ minWidth: 240, display: "flex", flexDirection: "column", gap: 8, alignItems: "stretch" }}>
      <button className="arkham-link" style={{ cursor: "pointer", textAlign: "left" }} onClick={() => setActiveTab("portfolio")}>
        {t("entity.portfolioView", "Portfolio View")}
      </button>
      <button
        className="arkham-link"
        style={{ cursor: "pointer", textAlign: "left" }}
        onClick={() => {
          setActiveTab("overview")
          setSurfaceViewTouched(true)
          setSurfaceView("history")
        }}
      >
        {t("entity.balancesHistory", "Balances History")}
      </button>
      <button
        className="arkham-link"
        style={{ cursor: "pointer", textAlign: "left" }}
        onClick={() => {
          setActiveTab("overview")
          setIntelViewTouched(true)
          setIntelView("venues")
        }}
      >
        {t("entity.exchangeUsage", "Exchange Usage")}
      </button>
      <button className="arkham-link" style={{ cursor: "pointer", textAlign: "left" }} onClick={() => setActiveTab("transfers")}>
        {t("entity.transferSurface", "Transfer Surface")}
      </button>
    </div>
  )

  const renderHero = () => (
    <div className="arkham-hero">
      <div className="arkham-hero-top">
        <div className="arkham-hero-icon" style={{ background: "var(--amber-dim)", color: "var(--amber)" }}>
          <LogoAvatar
            name={entityName}
            symbol={fallbackSymbol || entityName}
            size={40}
            title={entityName}
          />
        </div>
        <div className="arkham-hero-info">
          <div className="arkham-hero-name">{entityName}</div>
          <div className="arkham-hero-sym">
            {entityType}
            {entityCategory ? ` | ${entityCategory}` : ""}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
            {badgeItems.slice(0, 5).map((badge, index) => (
              <span
                key={`${badge}-${index}`}
                className="arkham-hero-badge"
                style={{
                  color: index === 0 ? "var(--amber)" : index === 1 ? "var(--cyan)" : "var(--text-2)",
                  borderColor: index === 0 ? "var(--amber)" : index === 1 ? "var(--cyan)" : "var(--border)",
                }}
              >
                {badge}
              </span>
            ))}
            {badgeItems.length > 5 && (
              <span className="arkham-hero-badge" style={{ color: "var(--blue-bright)", borderColor: "var(--blue-bright)" }}>
                +{badgeItems.length - 5} {t("entity.more", "MORE")}
              </span>
            )}
            {sourceLabel && (
              <span className="arkham-hero-badge" style={{ color: "var(--text-3)", borderColor: "var(--border)" }}>
                {sourceLabel}
              </span>
            )}
            <span className="arkham-hero-badge" style={{ color: "var(--blue-bright)", borderColor: "var(--blue-bright)" }}>
              {t("entity.allNetworks", "ALL NETWORKS")}
            </span>
          </div>

          {profileDescription && (
            <div style={{ marginTop: 10, color: "var(--text-2)", fontSize: 12, lineHeight: 1.6, maxWidth: 880 }}>
              {profileDescription}
            </div>
          )}

          {(profileLinks.length > 0 || focusAssets.length > 0 || focusNetworks.length > 0) && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
              {profileLinks.map((link) => (
                <a
                  key={link.label}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    padding: "6px 10px",
                    borderRadius: 999,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                    color: "var(--text-2)",
                    fontSize: 11,
                    textDecoration: "none",
                  }}
                >
                  <span>{link.label}</span>
                  <span style={{ color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 10 }}>{">"}</span>
                </a>
              ))}
              {focusAssets.slice(0, 5).map((asset) => (
                <button
                  key={asset}
                  onClick={() => {
                    setActiveTab("portfolio")
                    const match = holdings.find((holding) => String(holding.symbol || "").toUpperCase() === asset)
                    if (match) {
                      setSelectedHoldingKey(match.key)
                      setSelectedSurfaceTokenKey(match.key)
                    }
                  }}
                  style={{
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    padding: "6px 10px",
                    borderRadius: 999,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                    color: "var(--text-2)",
                    fontSize: 11,
                  }}
                >
                  {asset}
                </button>
              ))}
              {focusNetworks.slice(0, 4).map((network) => (
                <button
                  key={network}
                  onClick={() => {
                    setActiveTab("overview")
                    setSurfaceViewTouched(true)
                    setSurfaceView("chains")
                    setSelectedNetworkKey(network.toLowerCase())
                  }}
                  style={{
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    padding: "6px 10px",
                    borderRadius: 999,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                    color: "var(--text-3)",
                    fontSize: 11,
                  }}
                >
                  {network}
                </button>
              ))}
            </div>
          )}
        </div>
        {renderHeroActions()}
      </div>

      {/* ── Arkham-style hero metrics ── */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 12,
        marginTop: 16,
      }}>
        <div style={{
          background: "linear-gradient(135deg, rgba(50,130,255,0.08) 0%, rgba(50,130,255,0.02) 100%)",
          border: "1px solid rgba(50,130,255,0.2)",
          borderRadius: 10,
          padding: "14px 16px",
        }}>
          <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
            {t("entity.observedValue", "Observed Value")}
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: "var(--blue-bright)", fontFamily: "var(--font-mono)" }}>
            {totalObservedValue > 0 ? formatUsd(totalObservedValue) : "-"}
          </div>
          <div style={{ fontSize: 10, color: "var(--green)", marginTop: 4 }}>
            {entityData?.entity?.balance_usd ? `${((totalObservedValue / entityData.entity.balance_usd) * 100).toFixed(0)}% ${t("entity.attributed", "ATTRIBUTED")}` : t("entity.partialCoverage", "PARTIAL COVERAGE")}
          </div>
        </div>

        <div style={{
          background: "linear-gradient(135deg, rgba(255,170,0,0.08) 0%, rgba(255,170,0,0.02) 100%)",
          border: "1px solid rgba(255,170,0,0.2)",
          borderRadius: 10,
          padding: "14px 16px",
        }}>
          <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
            {t("entity.assetFlow24h", "Asset Flow (24h)")}
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: "var(--amber)", fontFamily: "var(--font-mono)" }}>
            {normalizedFlow.net != null ? formatUsd(Math.abs(normalizedFlow.net)) : "-"}
          </div>
          <div style={{ fontSize: 10, color: normalizedFlow.net >= 0 ? "var(--green)" : "var(--red)", marginTop: 4 }}>
            {normalizedFlow.net != null ? (normalizedFlow.net >= 0 ? t("entity.netInflow", "NET INFLOW") : t("entity.netOutflow", "NET OUTFLOW")) : t("entity.noFlowData", "NO FLOW DATA")}
          </div>
        </div>

        <div style={{
          background: "linear-gradient(135deg, rgba(0,255,136,0.08) 0%, rgba(0,255,136,0.02) 100%)",
          border: "1px solid rgba(0,255,136,0.2)",
          borderRadius: 10,
          padding: "14px 16px",
        }}>
          <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
            {t("entity.trackedWallets", "Tracked Wallets")}
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: "var(--green)", fontFamily: "var(--font-mono)" }}>
            {observedWalletCount.toLocaleString()}
          </div>
          <div style={{ fontSize: 10, color: "var(--text-3)", marginTop: 4 }}>
            {entityData?.wallets_count ? `${entityData.wallets_count} ${t("entity.ofKnown", "of known")}` : t("entity.fromCacheLive", "from cache + live")}
          </div>
        </div>

        <div style={{
          background: "linear-gradient(135deg, rgba(200,100,255,0.08) 0%, rgba(200,100,255,0.02) 100%)",
          border: "1px solid rgba(200,100,255,0.2)",
          borderRadius: 10,
          padding: "14px 16px",
        }}>
          <div style={{ fontSize: 10, color: "var(--text-3)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
            {t("entity.sourceLedger", "Source Ledger")}
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#c864ff", fontFamily: "var(--font-mono)" }}>
            {sourceTrace.length > 0 ? `${sourceTrace.length} ${t("entity.sources", "sources")}` : observedAssetCount > 0 ? `${observedAssetCount} ${t("entity.assets", "assets")}` : "-"}
          </div>
          <div style={{ fontSize: 10, color: "var(--text-3)", marginTop: 4 }}>
            {rpcVerifiedTokens > 0
              ? `${rpcVerifiedTokens} ${t("entity.rpcVerified", "RPC verified")} / ${highConfidenceSources} ${t("entity.highConfidence", "high confidence")}`
              : entityCoverage?.snapshots_scanned
                ? `${entityCoverage.snapshots_scanned} ${t("entity.snapshots", "snapshots")} / ${safeNumber(entityCoverage?.holder_rows_scanned).toLocaleString()} ${t("entity.rows", "rows")}`
                : t("entity.warmingSurface", "warming local surface")}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 10, color: "var(--text-3)", fontSize: 11, maxWidth: 960 }}>
        {entityCoverage?.coverage_note || t("entity.coverageNote", "Entity view is derived from local Arkham cache, tagged holder snapshots and recent on-chain signals.")}
      </div>
      {sourceTrace.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
          {sourceTrace.map((item: any) => (
            <span
              key={String(item?.id || item?.source || item?.kind)}
              title={item?.note || undefined}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "6px 10px",
                borderRadius: 999,
                border: `1px solid ${item?.confidence === "high" ? "rgba(0,255,136,0.35)" : "var(--border)"}`,
                background: "rgba(4,10,22,0.72)",
                color: item?.confidence === "high" ? "var(--green)" : "var(--text-3)",
                fontSize: 10,
                textTransform: "uppercase",
                letterSpacing: 0.45,
              }}
            >
              <span>{compactLabel(item?.kind || "source")}</span>
              <span style={{ color: "var(--text-2)" }}>{safeNumber(item?.count).toLocaleString()}</span>
              <span style={{ color: "var(--text-4)" }}>{compactLabel(item?.source || "unknown")}</span>
            </span>
          ))}
        </div>
      )}
      {entitySnapshotStatus === "warming" && (
        <div style={{ marginTop: 8, color: "var(--blue-bright)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
          {t("entity.liveSync", "Live Arkham sync in progress. This page is auto-refreshing in the background while new data lands.")}
        </div>
      )}
      {heroSignalItems.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
          {heroSignalItems.map((item) =>
            item.onClick ? (
              <button
                key={item.key}
                onClick={item.onClick}
                style={{
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 10px",
                  borderRadius: 999,
                  border: `1px solid ${item.tone === "var(--text-2)" ? "var(--border)" : item.tone}`,
                  background: "var(--bg-void)",
                  color: item.tone,
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: 0.45,
                }}
              >
                {item.label}
              </button>
            ) : (
              <span
                key={item.key}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 10px",
                  borderRadius: 999,
                  border: `1px solid ${item.tone === "var(--text-2)" ? "var(--border)" : item.tone}`,
                  background: "var(--bg-void)",
                  color: item.tone,
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: 0.45,
                }}
              >
                {item.label}
              </span>
            ),
          )}
        </div>
      )}

      <div className="arkham-stats-row" style={{ marginTop: 14 }}>
        <div className="arkham-stat">
          <div className="arkham-stat-label">{t("entity.observedWallets", "Observed Wallets")}</div>
          <div className="arkham-stat-value">{observedWalletCount.toLocaleString()}</div>
        </div>
        <div className="arkham-stat">
          <div className="arkham-stat-label">{t("entity.observedAssets", "Observed Assets")}</div>
          <div className="arkham-stat-value">{observedAssetCount.toLocaleString()}</div>
        </div>
        <div className="arkham-stat">
          <div className="arkham-stat-label">{t("entity.networks", "Networks")}</div>
          <div className="arkham-stat-value">{focusNetworks.length || 0}</div>
        </div>
        <div className="arkham-stat">
          <div className="arkham-stat-label">{t("entity.recentActivity", "Recent Activity")}</div>
          <div className="arkham-stat-value">{recentActivityCount.toLocaleString()}</div>
        </div>
        <div className="arkham-stat">
          <div className="arkham-stat-label">{t("entity.snapshotsScanned", "Snapshots Scanned")}</div>
          <div className="arkham-stat-value">{safeNumber(entityCoverage?.snapshots_scanned).toLocaleString()}</div>
        </div>
        <div className="arkham-stat">
          <div className="arkham-stat-label">{t("entity.netFlow", "Net Flow")}</div>
          <div className="arkham-stat-value" style={{ color: safeNumber(normalizedFlow.net) >= 0 ? "var(--green)" : "var(--red)" }}>
            {normalizedFlow.net != null ? formatUsd(normalizedFlow.net) : "-"}
          </div>
        </div>
      </div>
    </div>
  )

  const renderObservedPortfolioPanel = () => (
    <div className="arkham-card">
      <div className="arkham-card-header" style={{ alignItems: "flex-start", gap: 10 }}>
        <span className="arkham-card-title">{t("entity.observedPortfolio", "Observed Portfolio")}</span>
        <PanelTabs
          items={[
            { id: "portfolio", label: t("entity.portfolio", "Portfolio"), count: holdings.length || undefined },
            { id: "chains", label: t("entity.holdingsByChain", "Holdings by Chain"), count: chainExposure.length || undefined },
            { id: "wallets", label: t("entity.walletSurface", "Wallet Surface"), count: wallets.length || undefined },
          ]}
          active={portfolioView}
          onChange={setPortfolioView}
        />
      </div>
      <div className="arkham-card-body" style={{ padding: 0 }}>
        {portfolioView === "portfolio" && holdings.length > 0 && (
          <table className="arkham-holders-table">
            <thead>
              <tr>
                <th>{t("entity.asset", "Asset")}</th>
                <th>{t("entity.price", "Price")}</th>
                <th>{t("entity.holdings", "Holdings")}</th>
                <th>{t("entity.value", "Value")}</th>
              </tr>
            </thead>
            <tbody>
              {holdings.slice(0, 8).map((holding) => (
                <tr
                  key={holding.key}
                  onClick={() => {
                    setSelectedHoldingKey(holding.key)
                    setSelectedSurfaceTokenKey(holding.key)
                  }}
                  style={{
                    cursor: "pointer",
                    background: selectedHolding?.key === holding.key ? "rgba(50,130,255,0.08)" : undefined,
                  }}
                >
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span style={{ color: "var(--text-1)", fontWeight: 600 }}>{holding.symbol}</span>
                      <span style={{ color: "var(--text-4)", fontSize: 10 }}>{holding.name}</span>
                    </div>
                  </td>
                  <td className="bal">{holding.price_usd != null ? formatUsd(holding.price_usd) : "-"}</td>
                  <td className="bal">{formatTokenAmount(holding.human_balance_total, holding.symbol)}</td>
                  <td className="bal">{holding.estimated_value_usd != null ? formatUsd(holding.estimated_value_usd) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {portfolioView === "chains" && chainExposure.length > 0 && (
          <div style={{ padding: 16 }}>
            <DistributionBars
              rows={chainExposure.map((item) => ({
                key: item.key,
                label: item.chain,
                value: item.totalValue || item.holdings,
                meta: `${item.holdings} ${t("entity.assets", "assets")} | ${item.wallets} ${t("entity.wallets", "wallets")}`,
              }))}
              selectedKey={selectedNetwork?.key || null}
              onSelect={setSelectedNetworkKey}
              valueFormatter={(value) => (value > 1000 ? formatUsd(value) : `${value} rows`)}
            />
          </div>
        )}

        {portfolioView === "wallets" && wallets.length > 0 && (
          <table className="arkham-holders-table">
            <thead>
              <tr>
                <th>{t("entity.wallet", "Wallet")}</th>
                <th>{t("entity.role", "Role")}</th>
                <th>{t("entity.assets", "Assets")}</th>
                <th>{t("entity.value", "Value")}</th>
              </tr>
            </thead>
            <tbody>
              {wallets.slice(0, 8).map((wallet) => (
                <tr
                  key={wallet.key}
                  onClick={() => {
                    setSelectedWalletAddress(wallet.key)
                    setActiveTab("wallets")
                  }}
                  style={{
                    cursor: "pointer",
                    background: selectedWallet?.key === wallet.key ? "rgba(50,130,255,0.08)" : undefined,
                  }}
                >
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <span className="addr">{wallet.labelText}</span>
                      <span style={{ color: "var(--text-4)", fontSize: 10, fontFamily: "var(--font-mono)" }}>
                        {truncateAddr(wallet.address)}
                      </span>
                    </div>
                  </td>
                  <td>{(wallet.flags || []).slice(0, 2).map((flag: string) => titleCase(flag)).join(", ") || titleCase(wallet.wallet_type || "wallet")}</td>
                  <td>{wallet.tokenCount || "-"}</td>
                  <td className="bal">{wallet.observed_value_usd != null ? formatUsd(wallet.observed_value_usd) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {((portfolioView === "portfolio" && holdings.length === 0) ||
          (portfolioView === "chains" && chainExposure.length === 0) ||
          (portfolioView === "wallets" && wallets.length === 0)) && (
          <div style={{ padding: 16 }}>
            <EmptyState
              icon="[]"
              title={t("entity.portfolioSparse", "Portfolio surface still sparse")}
              description={t("entity.portfolioSparseDesc", "This panel becomes useful as more labeled holdings are discovered for the entity.")}
            />
          </div>
        )}
      </div>
    </div>
  )

  const renderObservedSurfacePanel = () => {
    const tokenRows = tokenBalanceSurface.slice(0, 8).map((token: any) => ({
      key: token.key,
      label: token.symbol,
      value: safeNumber(token.observed_value_usd) || Math.abs(safeNumber(token.recent_net_usd)) || safeNumber(token.recent_tx_count),
      meta: `${compactLabel(token.chain)} | ${safeNumber(token.wallet_count)} ${t("entity.wallets", "wallets")}`,
    }))

    const chainRows = networkUsage.slice(0, 8).map((item: any) => ({
      key: item.key,
      label: compactLabel(item.chain),
      value: safeNumber(item.observed_value_usd) || Math.abs(safeNumber(item.net_usd)) || safeNumber(item.tx_count),
      meta: `${safeNumber(item.asset_count)} ${t("entity.assets", "assets")} | ${safeNumber(item.wallet_count)} ${t("entity.wallets", "wallets")}`,
    }))

    const selectedHistoryWindow = selectedBalanceBucket
    const selectedHistoryWindowLabel = selectedHistoryWindow
      ? selectedHistoryWindow.label
      : formatHistoryRange(historyStartPoint?.timestamp, selectedHistoryPoint?.timestamp)
    const selectedHistoryWindowValue =
      selectedHistoryWindow?.display_value_usd ?? selectedHistoryPoint?.value_usd ?? null
    const selectedHistoryWindowNet =
      selectedHistoryWindow?.net_usd ?? historyChangeSinceStart ?? null
    const selectedHistoryWindowDate = selectedHistoryWindow?.timestamp
      ? formatHistoryAxisLabel(selectedHistoryWindow.timestamp, filteredHistorySpanDays)
      : selectedHistoryPoint?.timestamp
        ? formatHistoryAxisLabel(selectedHistoryPoint.timestamp, filteredHistorySpanDays)
        : "-"
    const historyStatusNote = balanceHistory.length > 0
      ? `${t("entity.historicalWindows", "Historical Windows")}: ${balanceHistory.length} | ${t("entity.trackedNetworksFull", "Tracked Networks")}: ${historyTrackedChains}.`
      : historyTrackedChains > 0
        ? `${t("entity.balancesHistory", "Balances History")} live Arkham | ${historyTrackedChains} ${t("entity.trackedNetworksFull", "Tracked Networks").toLowerCase()}.`
        : t("entity.coverageNote", "Derived from cached holder snapshots, wallet labels, and recent token-transfer activity. This is partial local coverage, not a full Arkham mirror yet.")

    return (
      <div className="arkham-card">
        <div className="arkham-card-header" style={{ alignItems: "flex-start", gap: 10 }}>
          <span className="arkham-card-title">{t("entity.balancesHistory", "Balances History")}</span>
          <PanelTabs
            items={[
              { id: "history", label: t("entity.balances", "Balances"), count: filteredHistorySeries.length || undefined },
              { id: "tokens", label: t("entity.tokenSurface", "Token Surface"), count: tokenRows.length || undefined },
              { id: "chains", label: t("entity.networkSurface", "Network Surface"), count: chainRows.length || undefined },
            ]}
            active={surfaceView}
            onChange={(value) => {
              setSurfaceViewTouched(true)
              setSurfaceView(value)
            }}
          />
        </div>
        <div className="arkham-card-body">
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 12,
              marginBottom: 12,
              flexWrap: "wrap",
            }}
          >
            <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
              {historyStatusNote}
            </div>
            {surfaceView === "history" && filteredHistorySeries.length > 0 && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {historyRangeButtons.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => setHistoryRange(item.id)}
                    style={{
                      cursor: "pointer",
                      borderRadius: 999,
                      border: `1px solid ${historyRange === item.id ? "var(--blue-bright)" : "var(--border)"}`,
                      background: historyRange === item.id ? "rgba(50,130,255,0.12)" : "transparent",
                      color: historyRange === item.id ? "var(--blue-bright)" : "var(--text-4)",
                      padding: "4px 10px",
                      fontSize: 10,
                      fontFamily: "var(--font-mono)",
                      letterSpacing: 0.5,
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {surfaceView === "history" && selectedHistoryPoint && (
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.35fr) minmax(280px, 0.85fr)", gap: 16, marginBottom: 14 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 14, minWidth: 0 }}>
                <div
                  style={{
                    padding: "14px 16px",
                    borderRadius: 14,
                    border: "1px solid var(--border)",
                    background: "linear-gradient(180deg, rgba(18,28,46,0.96), rgba(9,14,24,0.98))",
                    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.02)",
                  }}
                >
                  <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 12, alignItems: "end" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600 }}>
                        {selectedHistoryWindowLabel}
                      </div>
                      <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                        {selectedBalanceBucket ? `${selectedBalanceBucket.tx_count} tx` : `${filteredHistorySeries.length} points`}
                        {filteredHistorySpanDays > 0 ? ` | ${filteredHistorySpanDays} day view` : ""}
                        {historyTrackedChains > 0 ? ` | ${historyTrackedChains} networks` : ""}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ color: "var(--text-1)", fontFamily: "var(--font-mono)", fontSize: 18 }}>
                        {selectedHistoryWindowValue != null ? formatUsd(selectedHistoryWindowValue) : "-"}
                      </div>
                      <div style={{ color: "var(--text-4)", fontSize: 10 }}>
                        {selectedHistoryWindowDate}
                      </div>
                    </div>
                  </div>

                  <div className="arkham-metrics" style={{ marginTop: 16 }}>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.estimatedBalance", "Estimated Balance")}</span>
                      <span className="arkham-metric-value">{selectedHistoryWindowValue != null ? formatUsd(selectedHistoryWindowValue) : "-"}</span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.inflow", "Inflow")}</span>
                      <span className="arkham-metric-value" style={{ color: "var(--green)" }}>
                        {selectedBalanceBucket ? formatUsd(selectedBalanceBucket.inflow_usd) : "-"}
                      </span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.outflow", "Outflow")}</span>
                      <span className="arkham-metric-value" style={{ color: "var(--red)" }}>
                        {selectedBalanceBucket ? formatUsd(selectedBalanceBucket.outflow_usd) : "-"}
                      </span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.net", "Net")}</span>
                      <span className="arkham-metric-value" style={{ color: safeNumber(selectedHistoryWindowNet) >= 0 ? "var(--green)" : "var(--red)" }}>
                        {selectedHistoryWindowNet != null ? formatSigned(selectedHistoryWindowNet, formatUsd) : "-"}
                      </span>
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    padding: "12px 14px 10px",
                    borderRadius: 14,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                  }}
                >
                  <MiniAreaChart
                    points={filteredHistorySeries}
                    valueKey="value_usd"
                    selectedKey={selectedHistoryPoint?.key || null}
                    onSelect={setSelectedHistoryKey}
                    color="var(--blue-bright)"
                    height={290}
                    showSelectorButtons={false}
                    showAxes
                    showPointMarkers={false}
                    valueFormatter={formatUsd}
                  />
                </div>

                {balanceHistory.length > 0 && (
                  <div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>
                      {t("entity.historicalWindows", "Historical Windows")}
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {balanceHistory.map((bucket: any) => (
                        <button
                          key={bucket.key}
                          onClick={() => setSelectedBalanceBucketKey(bucket.key)}
                          style={{
                            cursor: "pointer",
                            borderRadius: 999,
                            border: `1px solid ${selectedBalanceBucket?.key === bucket.key ? "var(--blue-bright)" : "var(--border)"}`,
                            background: selectedBalanceBucket?.key === bucket.key ? "rgba(50,130,255,0.12)" : "var(--bg-void)",
                            color: selectedBalanceBucket?.key === bucket.key ? "var(--text-1)" : "var(--text-4)",
                            padding: "6px 10px",
                            fontSize: 10,
                            fontFamily: "var(--font-mono)",
                            letterSpacing: 0.35,
                          }}
                        >
                          {bucket.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 12, minWidth: 0 }}>
                <div
                  style={{
                    padding: "12px 14px",
                    borderRadius: 14,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                  }}
                >
                  <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {t("entity.chartCursor", "Chart Cursor")}
                  </div>
                  <div style={{ color: "var(--text-1)", fontSize: 15, fontWeight: 600, marginTop: 8 }}>
                    {formatHistoryAxisLabel(selectedHistoryPoint.timestamp, filteredHistorySpanDays)}
                  </div>
                  <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                    {filteredHistorySeries.length} points in current view
                  </div>
                  <div className="arkham-metrics" style={{ marginTop: 14 }}>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.selectedValue", "Selected Value")}</span>
                      <span className="arkham-metric-value">{formatUsd(selectedHistoryPoint.value_usd)}</span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.changeInView", "Change In View")}</span>
                      <span className="arkham-metric-value" style={{ color: safeNumber(historyChangeSinceStart) >= 0 ? "var(--green)" : "var(--red)" }}>
                        {historyChangeSinceStart != null ? formatSigned(historyChangeSinceStart, formatUsd) : "-"}
                      </span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.peakBalance", "Peak Balance")}</span>
                      <span className="arkham-metric-value">{historyPeakPoint ? formatUsd(historyPeakPoint.value_usd) : "-"}</span>
                    </div>
                    <div className="arkham-metric">
                      <span className="arkham-metric-label">{t("entity.trackedNetworksFull", "Tracked Networks")}</span>
                      <span className="arkham-metric-value">{historyTrackedChains || "-"}</span>
                    </div>
                  </div>
                </div>

                {historyChainSurface.length > 0 && (
                  <div
                    style={{
                      padding: "12px 14px",
                      borderRadius: 14,
                      border: "1px solid var(--border)",
                      background: "var(--bg-void)",
                    }}
                  >
                    <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      {t("entity.topNetworkSurface", "Top Network Surface")}
                    </div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {t("entity.topNetworkSurfaceDesc", "Jump into the network view with the strongest observed balance curves.")}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
                      {historyChainSurface.slice(0, 6).map((item: any) => (
                        <button
                          key={item.key}
                          onClick={() => {
                            setSurfaceViewTouched(true)
                            setSurfaceView("chains")
                            setSelectedNetworkKey(item.key)
                          }}
                          style={{
                            cursor: "pointer",
                            textAlign: "left",
                            borderRadius: 12,
                            border: `1px solid ${selectedNetwork?.key === item.key ? "var(--blue-bright)" : "var(--border)"}`,
                            background: selectedNetwork?.key === item.key ? "rgba(50,130,255,0.08)" : "rgba(255,255,255,0.01)",
                            padding: "10px 12px",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                            <span style={{ color: "var(--text-2)", fontSize: 11, textTransform: "uppercase", letterSpacing: 0.45 }}>
                              {item.label}
                            </span>
                            <span style={{ color: "var(--text-4)", fontSize: 10 }}>{item.pointCount} pts</span>
                          </div>
                          <div style={{ color: "var(--text-1)", fontFamily: "var(--font-mono)", fontSize: 14, marginTop: 6 }}>
                            {formatUsd(item.latestUsd)}
                          </div>
                          <div style={{ color: safeNumber(item.changeUsd) >= 0 ? "var(--green)" : "var(--red)", fontSize: 10, marginTop: 4 }}>
                            {formatSigned(item.changeUsd, formatUsd)}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {surfaceView === "tokens" && selectedSurfaceToken && (
            <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 0.9fr) minmax(0, 1.1fr)", gap: 16 }}>
              <div
                style={{
                  marginBottom: 14,
                  padding: "12px 14px",
                  borderRadius: 12,
                  border: "1px solid var(--border)",
                  background: "var(--bg-void)",
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <LogoAvatar
                    name={selectedSurfaceToken.name || selectedSurfaceToken.symbol}
                    symbol={selectedSurfaceToken.symbol}
                    size={30}
                    title={selectedSurfaceToken.name || selectedSurfaceToken.symbol}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600 }}>{selectedSurfaceToken.symbol}</div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {selectedSurfaceToken.name} | {compactLabel(selectedSurfaceToken.chain)}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "var(--text-1)", fontFamily: "var(--font-mono)", fontSize: 15 }}>
                      {selectedSurfaceToken.observed_value_usd != null ? formatUsd(selectedSurfaceToken.observed_value_usd) : "-"}
                    </div>
                    <div style={{ color: "var(--text-4)", fontSize: 10 }}>
                      {t("entity.recentActivity", "Recent Activity")} {formatSigned(selectedSurfaceToken.recent_net_usd, formatUsd)}
                    </div>
                  </div>
                </div>
                <div className="arkham-metrics" style={{ marginTop: 14 }}>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.walletCount", "Wallet Count")}</span>
                    <span className="arkham-metric-value">{selectedSurfaceToken.wallet_count || 0}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.observedShare", "Observed Share")}</span>
                    <span className="arkham-metric-value">{selectedSurfaceToken.share_pct != null ? formatPct(selectedSurfaceToken.share_pct) : "-"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.recentInflow", "Recent Inflow")}</span>
                    <span className="arkham-metric-value" style={{ color: "var(--green)" }}>{formatUsd(selectedSurfaceToken.recent_inflow_usd)}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.recentOutflow", "Recent Outflow")}</span>
                    <span className="arkham-metric-value" style={{ color: "var(--red)" }}>{formatUsd(selectedSurfaceToken.recent_outflow_usd)}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.recentTx", "Recent Tx")}</span>
                    <span className="arkham-metric-value">{selectedSurfaceToken.recent_tx_count || 0}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.holderConcentration", "Holder Concentration")}</span>
                    <span className="arkham-metric-value">
                      {selectedSurfaceToken.max_holder_share_pct != null ? formatPct(selectedSurfaceToken.max_holder_share_pct) : "-"}
                    </span>
                  </div>
                </div>
              </div>

              <div
                style={{
                  marginBottom: 14,
                  padding: "12px 14px",
                  borderRadius: 12,
                  border: "1px solid var(--border)",
                  background: "var(--bg-void)",
                }}
              >
                <DistributionBars
                  rows={tokenRows}
                  selectedKey={selectedSurfaceToken?.key || null}
                  onSelect={setSelectedSurfaceTokenKey}
                  valueFormatter={(value) => formatUsd(value)}
                />
              </div>
            </div>
          )}

          {surfaceView === "chains" && selectedNetwork && (
            <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 0.9fr) minmax(0, 1.1fr)", gap: 16 }}>
              <div
                style={{
                  marginBottom: 14,
                  padding: "12px 14px",
                  borderRadius: 12,
                  border: "1px solid var(--border)",
                  background: "var(--bg-void)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <div>
                    <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600 }}>{titleCase(selectedNetwork.chain)}</div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {selectedNetwork.asset_count} {t("entity.assets", "assets")} | {selectedNetwork.wallet_count} {t("entity.wallets", "wallets")}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "var(--text-1)", fontFamily: "var(--font-mono)", fontSize: 15 }}>
                      {selectedNetwork.observed_value_usd != null ? formatUsd(selectedNetwork.observed_value_usd) : "-"}
                    </div>
                    <div style={{ color: "var(--text-4)", fontSize: 10 }}>
                      {t("entity.recentActivity", "Recent Activity")} {formatSigned(selectedNetwork.net_usd, formatUsd)}
                    </div>
                  </div>
                </div>
                <div className="arkham-metrics" style={{ marginTop: 14 }}>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.observedValue", "Observed Value")}</span>
                    <span className="arkham-metric-value">{selectedNetwork.observed_value_usd != null ? formatUsd(selectedNetwork.observed_value_usd) : "-"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.inflow", "Inflow")}</span>
                    <span className="arkham-metric-value" style={{ color: "var(--green)" }}>{formatUsd(selectedNetwork.inflow_usd)}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.outflow", "Outflow")}</span>
                    <span className="arkham-metric-value" style={{ color: "var(--red)" }}>{formatUsd(selectedNetwork.outflow_usd)}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.net", "Net")}</span>
                    <span className="arkham-metric-value" style={{ color: safeNumber(selectedNetwork.net_usd) >= 0 ? "var(--green)" : "var(--red)" }}>
                      {formatSigned(selectedNetwork.net_usd, formatUsd)}
                    </span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.txCount", "Tx Count")}</span>
                    <span className="arkham-metric-value">{selectedNetwork.tx_count || 0}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.assetCount", "Asset Count")}</span>
                    <span className="arkham-metric-value">{selectedNetwork.asset_count || 0}</span>
                  </div>
                </div>
              </div>

              <div
                style={{
                  marginBottom: 14,
                  padding: "12px 14px",
                  borderRadius: 12,
                  border: "1px solid var(--border)",
                  background: "var(--bg-void)",
                }}
              >
                <DistributionBars
                  rows={chainRows}
                  selectedKey={selectedNetwork?.key || null}
                  onSelect={setSelectedNetworkKey}
                  valueFormatter={(value) => formatUsd(value)}
                />
              </div>
            </div>
          )}

          {surfaceView === "history" && filteredHistorySeries.length === 0 && (
            <EmptyState
              icon="::"
              title={t("entity.portfolioSparse", "Portfolio surface still sparse")}
              description={t("entity.portfolioSparseDesc", "This panel becomes useful as more labeled holdings are discovered for the entity.")}
            />
          )}
        </div>
      </div>
    )
  }

  const renderFlowIntelPanel = () => (
    <div className="arkham-card">
      <div className="arkham-card-header" style={{ alignItems: "flex-start", gap: 10 }}>
        <span className="arkham-card-title">{t("entity.exchangeUsage", "Exchange Usage")}</span>
        <PanelTabs
          items={[
            { id: "venues", label: t("entity.venuesTitle", "Venues"), count: venueUsage.length || undefined },
            { id: "counterparties", label: t("entity.topCounterparties", "Top Counterparties"), count: counterparties.length || undefined },
            { id: "clusters", label: t("entity.roleClusters", "Role Clusters"), count: roleClusters.length || undefined },
          ]}
          active={intelView}
          onChange={(value) => {
            setIntelViewTouched(true)
            setIntelView(value)
          }}
        />
      </div>
      <div className="arkham-card-body">
        {intelView === "venues" && venueUsage.length > 0 && selectedVenue && (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 0.95fr) minmax(0, 1.05fr)", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div
                style={{
                  padding: "12px 14px",
                  borderRadius: 14,
                  border: "1px solid var(--border)",
                  background: "var(--bg-void)",
                }}
              >
                <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <LogoAvatar
                    name={selectedVenue.label}
                    symbol={selectedVenue.label}
                    size={30}
                    title={selectedVenue.label}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600 }}>{selectedVenue.label}</div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {titleCase(selectedVenue.category || "venue")}
                      {selectedVenue.token_symbols.length ? ` | ${selectedVenue.token_symbols.slice(0, 4).join(", ")}` : ""}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div style={{ color: "var(--text-1)", fontFamily: "var(--font-mono)", fontSize: 15 }}>
                      {formatSigned(selectedVenue.net_usd, formatUsd)}
                    </div>
                    <div style={{ color: "var(--text-4)", fontSize: 10 }}>{selectedVenue.tx_count} tx</div>
                  </div>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                  {selectedVenueCounterpartyMatch && (
                    <button
                      onClick={() => {
                        setSelectedCounterpartyKey(selectedVenueCounterpartyMatch.key)
                        setActiveTab("counterparties")
                      }}
                      style={{
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        padding: "6px 10px",
                        borderRadius: 999,
                        border: "1px solid var(--blue-bright)",
                        background: "rgba(50,130,255,0.08)",
                        color: "var(--blue-bright)",
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: 0.45,
                      }}
                    >
                      {t("entity.inspectCounterparty", "Inspect counterparty")}
                    </button>
                  )}
                  {selectedVenueTransferMatches.length > 0 && (
                    <button
                      onClick={() => {
                        setTransferFilter("all")
                        setActiveTab("transfers")
                        setSelectedTransferKey(selectedVenueTransferMatches[0].tx_hash)
                      }}
                      style={{
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        padding: "6px 10px",
                        borderRadius: 999,
                        border: "1px solid var(--border)",
                        background: "var(--bg-card)",
                        color: "var(--text-2)",
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: 0.45,
                      }}
                    >
                      {selectedVenueTransferMatches.length} {t("entity.recentMatches", "recent matches")}
                    </button>
                  )}
                  {(selectedVenue.token_symbols || []).slice(0, 4).map((symbol: string) => (
                    <span
                      key={symbol}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        padding: "6px 10px",
                        borderRadius: 999,
                        border: "1px solid var(--border)",
                        color: "var(--text-3)",
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: 0.45,
                      }}
                    >
                      {symbol}
                    </span>
                  ))}
                </div>

                <div className="arkham-metrics" style={{ marginTop: 14 }}>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.inflow", "Inflow")}</span>
                    <span className="arkham-metric-value" style={{ color: "var(--green)" }}>{formatUsd(selectedVenue.inflow_usd)}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.outflow", "Outflow")}</span>
                    <span className="arkham-metric-value" style={{ color: "var(--red)" }}>{formatUsd(selectedVenue.outflow_usd)}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.grossFlow", "Gross Flow")}</span>
                    <span className="arkham-metric-value">{selectedVenueGrossFlow != null ? formatUsd(selectedVenueGrossFlow) : "-"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.net", "Net")}</span>
                    <span
                      className="arkham-metric-value"
                      style={{ color: selectedVenue.net_usd >= 0 ? "var(--green)" : "var(--red)" }}
                    >
                      {formatSigned(selectedVenue.net_usd, formatUsd)}
                    </span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.shareOfSurface", "Share Of Surface")}</span>
                    <span className="arkham-metric-value">{selectedVenueFlowShare != null ? formatPct(selectedVenueFlowShare) : "-"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">{t("entity.directionBias", "Direction Bias")}</span>
                    <span className="arkham-metric-value">{selectedVenueDirectionBias}</span>
                  </div>
                </div>
              </div>

              {selectedVenueTransferMatches.length > 0 && (
                <div
                  style={{
                    padding: "12px 14px",
                    borderRadius: 14,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                  }}
                >
                  <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
                    {t("entity.recentVenueMatches", "Recent Venue Matches")}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
                    {selectedVenueTransferMatches.slice(0, 3).map((item) => (
                      <button
                        key={item.tx_hash}
                        onClick={() => {
                          setTransferFilter("all")
                          setActiveTab("transfers")
                          setSelectedTransferKey(item.tx_hash)
                        }}
                        style={{
                          cursor: "pointer",
                          textAlign: "left",
                          borderRadius: 12,
                          border: "1px solid var(--border)",
                          background: "rgba(255,255,255,0.01)",
                          padding: "10px 12px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                          <span style={{ color: "var(--text-2)", fontSize: 11 }}>
                            {item.counterparty_label || selectedVenue.label}
                          </span>
                          <span style={{ color: item.direction === "inflow" ? "var(--green)" : "var(--red)", fontSize: 11 }}>
                            {item.value_usd != null ? formatUsd(item.value_usd) : formatTokenAmount(item.amount, item.token_symbol)}
                          </span>
                        </div>
                        <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                          {localizedActivityTimeAgo(item.timestamp)} | {item.token_symbol || t("entity.asset", "Asset")} | {flowDirectionLabel(item.direction)}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div
              style={{
                padding: "12px 14px",
                borderRadius: 14,
                border: "1px solid var(--border)",
                background: "var(--bg-void)",
              }}
            >
              <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>
                {t("entity.venueLadder", "Venue Ladder")}
              </div>
              <DistributionBars
                rows={venueUsage.slice(0, 10).map((venue: any) => ({
                  key: venue.key,
                  label: venue.label,
                  value: Math.abs(safeNumber(venue.net_usd)) || safeNumber(venue.tx_count),
                  meta: `${titleCase(venue.category || "venue")} | ${safeNumber(venue.tx_count)} tx | net ${formatSigned(venue.net_usd, formatUsd)}`,
                }))}
                selectedKey={selectedVenue?.key || null}
                onSelect={setSelectedVenueKey}
                valueFormatter={(value) => (value > 1000 ? formatUsd(value) : `${value} tx`)}
              />
            </div>
          </div>
        )}

        {intelView === "venues" && venueUsage.length === 0 && (
          <EmptyState
            icon="<>"
            title={t("entity.noExchangeUsage", "No exchange usage surface yet")}
            description={t("entity.noExchangeUsageDesc", "Venues will appear here as more labeled counterparties like PancakeSwap, Binance, MEXC or bridges enter the cached transfer history.")}
          />
        )}

        {intelView === "counterparties" && counterparties.length > 0 && selectedCounterparty && (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 0.92fr) minmax(0, 1.08fr)", gap: 16 }}>
            <div
              style={{
                padding: "12px 14px",
                borderRadius: 14,
                border: "1px solid var(--border)",
                background: "var(--bg-void)",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                <LogoAvatar
                  name={selectedCounterparty.detailLabel}
                  symbol={selectedCounterparty.detailLabel}
                  size={30}
                  title={selectedCounterparty.detailLabel}
                />
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                    {selectedCounterparty.detailLabel}
                  </div>
                  <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                    {selectedCounterparty.address ? truncateAddr(selectedCounterparty.address, 6) : t("entity.labelOnlySurface", "Label-only surface")} | {titleCase(selectedCounterpartyChain)}
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                {selectedCounterpartyExplorerUrl && (
                  <a
                    href={selectedCounterpartyExplorerUrl || undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "6px 10px",
                      borderRadius: 999,
                      border: "1px solid var(--blue-bright)",
                      color: "var(--blue-bright)",
                      textDecoration: "none",
                      fontSize: 10,
                      textTransform: "uppercase",
                      letterSpacing: 0.45,
                    }}
                  >
                    {t("entity.openExplorer", "Open Explorer")}
                  </a>
                )}
                <button
                  onClick={() => setActiveTab("counterparties")}
                  style={{
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    padding: "6px 10px",
                    borderRadius: 999,
                    border: "1px solid var(--border)",
                    background: "var(--bg-card)",
                    color: "var(--text-2)",
                    fontSize: 10,
                    textTransform: "uppercase",
                    letterSpacing: 0.45,
                  }}
                >
                  {t("entity.openDetailTab", "Open Detail Tab")}
                </button>
                {selectedCounterpartyTransferMatches.length > 0 && (
                  <button
                    onClick={() => {
                      setTransferFilter("all")
                      setActiveTab("transfers")
                      setSelectedTransferKey(selectedCounterpartyTransferMatches[0].tx_hash)
                    }}
                    style={{
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "6px 10px",
                      borderRadius: 999,
                      border: "1px solid var(--border)",
                      background: "rgba(255,255,255,0.01)",
                      color: "var(--text-2)",
                      fontSize: 10,
                      textTransform: "uppercase",
                      letterSpacing: 0.45,
                    }}
                  >
                    {selectedCounterpartyTransferMatches.length} {t("entity.relatedTransfers", "related transfers")}
                  </button>
                )}
              </div>

              <div className="arkham-metrics" style={{ marginTop: 14 }}>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">{t("entity.observedValue", "Observed Value")}</span>
                  <span className="arkham-metric-value">{selectedCounterparty.value_usd != null ? formatUsd(selectedCounterparty.value_usd) : "-"}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">{t("entity.txCount", "Tx Count")}</span>
                  <span className="arkham-metric-value">{selectedCounterparty.tx_count || 0}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">{t("entity.inflowCount", "Inflow Count")}</span>
                  <span className="arkham-metric-value">{selectedCounterparty.inflow_count || 0}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">{t("entity.outflowCount", "Outflow Count")}</span>
                  <span className="arkham-metric-value">{selectedCounterparty.outflow_count || 0}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">{t("entity.directionBias", "Direction Bias")}</span>
                  <span className="arkham-metric-value">
                    {selectedCounterparty.inflow_count > selectedCounterparty.outflow_count
                      ? t("entity.inbound", "Inbound")
                      : selectedCounterparty.outflow_count > selectedCounterparty.inflow_count
                        ? t("entity.outbound", "Outbound")
                        : t("entity.balanced", "Balanced")}
                  </span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">{t("entity.latestMatch", "Latest Match")}</span>
                  <span className="arkham-metric-value">
                    {selectedCounterpartyTransferMatches[0]
                      ? localizedActivityTimeAgo(selectedCounterpartyTransferMatches[0].timestamp)
                      : "-"}
                  </span>
                </div>
              </div>
            </div>

            <div
              style={{
                padding: "12px 14px",
                borderRadius: 14,
                border: "1px solid var(--border)",
                background: "var(--bg-void)",
              }}
            >
              <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>
                {t("entity.counterpartyLadder", "Counterparty Ladder")}
              </div>
              <DistributionBars
                rows={counterparties.slice(0, 10).map((cp) => ({
                  key: cp.key,
                  label: cp.labelText,
                  value: cp.value,
                  meta: `in ${cp.inflow_count || 0} | out ${cp.outflow_count || 0} | ${cp.tx_count || 0} tx`,
                }))}
                selectedKey={selectedCounterparty?.key || null}
                onSelect={setSelectedCounterpartyKey}
                valueFormatter={(value) => (value > 1000 ? formatUsd(value) : `${value} tx`)}
              />
            </div>
          </div>
        )}

        {intelView === "counterparties" && counterparties.length === 0 && (
          <EmptyState
            icon="<>"
            title={t("entity.noCounterpartyGraph", "No counterparty graph yet")}
            description={t("entity.noCounterpartyGraphDesc", "Counterparties will appear once labeled transfer coverage becomes denser.")}
          />
        )}

        {intelView === "clusters" && roleClusters.length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 0.9fr) minmax(0, 1.1fr)", gap: 16 }}>
            <div
              style={{
                padding: "12px 14px",
                borderRadius: 14,
                border: "1px solid var(--border)",
                background: "var(--bg-void)",
              }}
            >
              <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
                Primary Role Cluster
              </div>
              <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600, marginTop: 8 }}>
                {titleCase(roleClusters[0].role)}
              </div>
              <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                Dominant observed wallet behavior across the currently labeled graph.
              </div>
              <div className="arkham-metrics" style={{ marginTop: 14 }}>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Wallet Count</span>
                  <span className="arkham-metric-value">{roleClusters[0].wallet_count}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Observed Share</span>
                  <span className="arkham-metric-value">{roleClusters[0].share_pct != null ? formatPct(roleClusters[0].share_pct) : "-"}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Total Clusters</span>
                  <span className="arkham-metric-value">{roleClusters.length}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Observed Wallets</span>
                  <span className="arkham-metric-value">{wallets.length}</span>
                </div>
              </div>
            </div>

            <div
              style={{
                padding: "12px 14px",
                borderRadius: 14,
                border: "1px solid var(--border)",
                background: "var(--bg-void)",
              }}
            >
              <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 10 }}>
                Role Ladder
              </div>
              <DistributionBars
                rows={roleClusters.slice(0, 8).map((item: any) => ({
                  key: item.role,
                  label: titleCase(item.role),
                  value: item.wallet_count,
                  meta: item.share_pct != null ? `${formatPct(item.share_pct)} of observed wallets` : "Observed wallet role cluster",
                }))}
                valueFormatter={(value) => `${value} wallets`}
              />
            </div>
          </div>
        )}

        {intelView === "clusters" && roleClusters.length === 0 && (
          <EmptyState
            icon="##"
            title="No role clusters yet"
            description="Role clusters become useful once more exchange, deposit, router and proxy wallets are labeled."
          />
        )}
      </div>
    </div>
  )

  const renderTransferPanel = () => (
    <div className="arkham-card">
      <div className="arkham-card-header" style={{ alignItems: "flex-start", gap: 10 }}>
        <span className="arkham-card-title">{t("entity.transfers", "Transfers")}</span>
        <PanelTabs
          items={[
            { id: "all", label: t("entity.all", "All"), count: transferRows.all || undefined },
            { id: "inflow", label: t("entity.inflow", "Inflow"), count: transferRows.inflow || undefined },
            { id: "outflow", label: t("entity.outflow", "Outflow"), count: transferRows.outflow || undefined },
          ]}
          active={transferFilter}
          onChange={setTransferFilter}
        />
      </div>
      <div className="arkham-card-body" style={{ padding: 0 }}>
        {selectedTransfer && (
          <div style={{ display: "none", padding: 16, borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.015)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <div>
                <div style={{ color: "var(--text-1)", fontSize: 14, fontWeight: 600 }}>
                  {selectedTransfer.token_symbol || t("entity.unknownAsset", "Unknown Asset")} | {flowDirectionLabel(selectedTransfer.direction)}
                </div>
                <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                  {localizedActivityTimeAgo(selectedTransfer.timestamp)} | {selectedTransfer.counterparty_label || t("entity.unknownCounterparty", "Unknown counterparty")}
                </div>
                {getExplorerTxUrl(selectedTransfer.tx_hash, selectedTransfer.chain || defaultExplorerChain) && (
                  <a
                    href={getExplorerTxUrl(selectedTransfer.tx_hash, selectedTransfer.chain || defaultExplorerChain) || undefined}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: "var(--blue-bright)", fontSize: 0, marginTop: 6, display: "inline-block", textDecoration: "none" }}
                  >
                    <span style={{ fontSize: 10 }}>{"View transaction ->"}</span>
                    {t("entity.openExplorer", "Open Explorer")}
                  </a>
                )}
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ color: "var(--text-1)", fontFamily: "var(--font-mono)", fontSize: 14 }}>
                  {selectedTransfer.value_usd != null ? formatUsd(selectedTransfer.value_usd) : formatTokenAmount(selectedTransfer.amount, selectedTransfer.token_symbol)}
                </div>
                <div style={{ color: "var(--text-4)", fontSize: 10 }}>
                  {t("entity.wallet", "Wallet")} {selectedTransfer.wallet_label || t("entity.taggedWallet", "Tagged wallet")}
                </div>
              </div>
            </div>
          </div>
        )}

        {selectedTransfer && (
          <div style={{ padding: 16, borderBottom: "1px solid var(--border)", background: "rgba(255,255,255,0.015)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                  <span
                    style={{
                      display: "inline-flex",
                      padding: "4px 8px",
                      borderRadius: 999,
                      border: selectedTransfer.direction === "inflow" ? "1px solid var(--green)" : "1px solid var(--red)",
                      color: selectedTransfer.direction === "inflow" ? "var(--green)" : "var(--red)",
                      fontSize: 10,
                      textTransform: "uppercase",
                      letterSpacing: 0.45,
                    }}
                  >
                    {flowDirectionLabel(selectedTransfer.direction)}
                  </span>
                  <span style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.45 }}>
                    {compactLabel(selectedTransferChain)}
                  </span>
                  <span style={{ color: "var(--text-4)", fontSize: 10 }}>
                    {localizedActivityTimeAgo(selectedTransfer.timestamp)}
                  </span>
                </div>
                <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 700, marginTop: 10, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                  {selectedTransfer.wallet_label || t("entity.taggedWallet", "Tagged wallet")} {"->"} {selectedTransfer.counterparty_label || selectedTransfer.counterparty_entity || t("entity.unknownCounterparty", "Unknown counterparty")}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, color: "var(--text-4)", fontSize: 10, marginTop: 6 }}>
                  <span>{selectedTransfer.token_symbol || t("entity.unknownAsset", "Unknown asset")}</span>
                  <span>{formatTokenAmount(selectedTransfer.amount, selectedTransfer.token_symbol)}</span>
                  {selectedTransferTxUrl && (
                    <a
                      href={selectedTransferTxUrl || undefined}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(event) => event.stopPropagation()}
                      style={{ color: "var(--blue-bright)", textDecoration: "none" }}
                    >
                      Tx {truncateAddr(selectedTransfer.tx_hash, 8)}
                    </a>
                  )}
                </div>
              </div>
              <div style={{ textAlign: "right", flexShrink: 0 }}>
                <div style={{ color: "var(--text-1)", fontFamily: "var(--font-mono)", fontSize: 17, fontWeight: 700 }}>
                  {selectedTransfer.value_usd != null ? formatUsd(selectedTransfer.value_usd) : formatTokenAmount(selectedTransfer.amount, selectedTransfer.token_symbol)}
                </div>
                <div style={{ color: selectedTransfer.direction === "inflow" ? "var(--green)" : "var(--red)", fontSize: 10, marginTop: 4 }}>
                  {selectedTransfer.direction === "inflow" ? t("entity.receivedByEntity", "received by entity") : t("entity.sentByEntity", "sent by entity")}
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 10, marginTop: 14 }}>
              <div style={{ border: "1px solid var(--border)", borderRadius: 12, background: "var(--bg-void)", padding: "10px 12px" }}>
                <div style={{ color: "var(--text-4)", fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5 }}>{t("entity.entityWallet", "Entity Wallet")}</div>
                <div style={{ color: "var(--text-2)", fontSize: 12, fontWeight: 600, marginTop: 6, overflowWrap: "anywhere" }}>
                  {selectedTransfer.wallet_label || t("entity.taggedWallet", "Tagged wallet")}
                </div>
                <div style={{ marginTop: 4, fontSize: 10 }}>
                  {selectedTransferWalletUrl ? (
                    <a href={selectedTransferWalletUrl || undefined} target="_blank" rel="noopener noreferrer" style={{ color: "var(--blue-bright)", textDecoration: "none" }}>
                      {selectedTransfer.wallet_address ? truncateAddr(selectedTransfer.wallet_address, 6) : t("entity.openExplorer", "Open Explorer")}
                    </a>
                  ) : (
                    <span style={{ color: "var(--text-4)" }}>{selectedTransfer.wallet_address ? truncateAddr(selectedTransfer.wallet_address, 6) : "-"}</span>
                  )}
                </div>
              </div>

              <div style={{ border: "1px solid var(--border)", borderRadius: 12, background: "var(--bg-void)", padding: "10px 12px" }}>
                <div style={{ color: "var(--text-4)", fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5 }}>{t("entity.counterparty", "Counterparty")}</div>
                <div style={{ color: "var(--text-2)", fontSize: 12, fontWeight: 600, marginTop: 6, overflowWrap: "anywhere" }}>
                  {selectedTransfer.counterparty_label || selectedTransfer.counterparty_entity || t("entity.unknownCounterparty", "Unknown counterparty")}
                </div>
                <div style={{ marginTop: 4, fontSize: 10 }}>
                  {selectedTransferCounterpartyUrl ? (
                    <a href={selectedTransferCounterpartyUrl || undefined} target="_blank" rel="noopener noreferrer" style={{ color: "var(--blue-bright)", textDecoration: "none" }}>
                      {selectedTransfer.counterparty_address ? truncateAddr(selectedTransfer.counterparty_address, 6) : t("entity.openExplorer", "Open Explorer")}
                    </a>
                  ) : (
                    <span style={{ color: "var(--text-4)" }}>{selectedTransfer.counterparty_address ? truncateAddr(selectedTransfer.counterparty_address, 6) : "-"}</span>
                  )}
                </div>
              </div>

              <div style={{ border: "1px solid var(--border)", borderRadius: 12, background: "var(--bg-void)", padding: "10px 12px" }}>
                <div style={{ color: "var(--text-4)", fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5 }}>{t("entity.from", "From")}</div>
                <div style={{ marginTop: 6, fontSize: 11, overflowWrap: "anywhere" }}>
                  {selectedTransferFromUrl ? (
                    <a href={selectedTransferFromUrl || undefined} target="_blank" rel="noopener noreferrer" style={{ color: "var(--blue-bright)", textDecoration: "none" }}>
                      {selectedTransfer.from ? truncateAddr(selectedTransfer.from, 6) : "-"}
                    </a>
                  ) : (
                    <span style={{ color: "var(--text-3)" }}>{selectedTransfer.from ? truncateAddr(selectedTransfer.from, 6) : "-"}</span>
                  )}
                </div>
              </div>

              <div style={{ border: "1px solid var(--border)", borderRadius: 12, background: "var(--bg-void)", padding: "10px 12px" }}>
                <div style={{ color: "var(--text-4)", fontSize: 9, textTransform: "uppercase", letterSpacing: 0.5 }}>{t("entity.to", "To")}</div>
                <div style={{ marginTop: 6, fontSize: 11, overflowWrap: "anywhere" }}>
                  {selectedTransferToUrl ? (
                    <a href={selectedTransferToUrl || undefined} target="_blank" rel="noopener noreferrer" style={{ color: "var(--blue-bright)", textDecoration: "none" }}>
                      {selectedTransfer.to ? truncateAddr(selectedTransfer.to, 6) : "-"}
                    </a>
                  ) : (
                    <span style={{ color: "var(--text-3)" }}>{selectedTransfer.to ? truncateAddr(selectedTransfer.to, 6) : "-"}</span>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {transfers.length > 0 && (
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--border)",
              background: "rgba(255,255,255,0.01)",
            }}
          >
            <div className="arkham-metrics">
              <div className="arkham-metric">
                <span className="arkham-metric-label">{t("entity.visibleRows", "Visible Rows")}</span>
                <span className="arkham-metric-value">{transfers.length}</span>
              </div>
              <div className="arkham-metric">
                <span className="arkham-metric-label">{t("entity.inflow", "Inflow")}</span>
                <span className="arkham-metric-value" style={{ color: "var(--green)" }}>{formatUsd(filteredTransferInflowUsd)}</span>
              </div>
              <div className="arkham-metric">
                <span className="arkham-metric-label">{t("entity.outflow", "Outflow")}</span>
                <span className="arkham-metric-value" style={{ color: "var(--red)" }}>{formatUsd(filteredTransferOutflowUsd)}</span>
              </div>
              <div className="arkham-metric">
                <span className="arkham-metric-label">{t("entity.net", "Net")}</span>
                <span className="arkham-metric-value" style={{ color: filteredTransferNetUsd >= 0 ? "var(--green)" : "var(--red)" }}>
                  {formatSigned(filteredTransferNetUsd, formatUsd)}
                </span>
              </div>
              <div className="arkham-metric">
                <span className="arkham-metric-label">{t("entity.networks", "Networks")}</span>
                <span className="arkham-metric-value">{filteredTransferChains.length}</span>
              </div>
              <div className="arkham-metric">
                <span className="arkham-metric-label">{t("entity.activeFilter", "Active Filter")}</span>
                <span className="arkham-metric-value">{titleCase(transferFilter)}</span>
              </div>
            </div>

            {filteredTransferChains.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                {filteredTransferChains.slice(0, 6).map((chain) => (
                  <span
                    key={chain}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "6px 10px",
                      borderRadius: 999,
                      border: "1px solid var(--border)",
                      color: "var(--text-3)",
                      fontSize: 10,
                      textTransform: "uppercase",
                      letterSpacing: 0.45,
                    }}
                  >
                    {chain}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {transfers.length > 0 ? (
          <table className="arkham-holders-table">
            <thead>
              <tr>
                <th>{t("entity.time", "Time")}</th>
                <th>{t("entity.wallet", "Wallet")}</th>
                <th>{t("entity.counterparty", "Counterparty")}</th>
                <th>{t("entity.asset", "Asset")}</th>
                <th>{t("entity.value", "Value")}</th>
              </tr>
            </thead>
            <tbody>
              {transfers.slice(0, activeTab === "overview" ? 8 : 50).map((item) => (
                <tr
                  key={item.tx_hash}
                  onClick={() => setSelectedTransferKey(item.tx_hash)}
                  style={{
                    cursor: "pointer",
                    background: selectedTransfer?.tx_hash === item.tx_hash ? "rgba(50,130,255,0.08)" : undefined,
                  }}
                >
                  <td style={{ minWidth: 110 }}>
                    <div style={{ color: "var(--text-3)", fontSize: 11 }}>{localizedActivityTimeAgo(item.timestamp)}</div>
                    <div style={{ color: item.direction === "inflow" ? "var(--green)" : "var(--red)", fontSize: 10, marginTop: 4 }}>
                      {flowDirectionLabel(item.direction)}
                    </div>
                  </td>
                  <td style={{ minWidth: 180 }}>
                    <div style={{ color: "var(--text-2)", fontSize: 11, fontWeight: 600, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                      {item.wallet_label || t("entity.taggedWallet", "Tagged wallet")}
                    </div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {item.wallet_address && getExplorerAddressUrl(item.wallet_address, item.chain || defaultExplorerChain) ? (
                        <a
                          href={getExplorerAddressUrl(item.wallet_address, item.chain || defaultExplorerChain) || undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          style={{ color: "var(--blue-bright)", textDecoration: "none" }}
                        >
                          {truncateAddr(item.wallet_address, 4)}
                        </a>
                      ) : (
                        item.wallet_address ? truncateAddr(item.wallet_address, 4) : "-"
                      )}
                    </div>
                  </td>
                  <td style={{ minWidth: 190 }}>
                    <div style={{ color: "var(--text-2)", fontSize: 11, fontWeight: 600, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                      {item.counterparty_label || "-"}
                    </div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {item.counterparty_address && getExplorerAddressUrl(item.counterparty_address, item.chain || defaultExplorerChain) ? (
                        <a
                          href={getExplorerAddressUrl(item.counterparty_address, item.chain || defaultExplorerChain) || undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          style={{ color: "var(--blue-bright)", textDecoration: "none" }}
                        >
                          {truncateAddr(item.counterparty_address, 4)}
                        </a>
                      ) : (
                        item.counterparty_address ? truncateAddr(item.counterparty_address, 4) : "-"
                      )}
                    </div>
                  </td>
                  <td style={{ minWidth: 120 }}>
                    <div style={{ color: "var(--text-1)", fontSize: 11, fontWeight: 600 }}>{item.token_symbol || "-"}</div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {compactLabel(item.chain)}
                    </div>
                  </td>
                  <td className="bal">
                    <div style={{ color: item.direction === "inflow" ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                      {item.value_usd != null ? formatUsd(item.value_usd) : "-"}
                    </div>
                    <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                      {formatTokenAmount(item.amount, item.token_symbol)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ padding: 16 }}>
            <EmptyState
              icon="<>"
              title={t("entity.noTransferSurface", "No labeled transfer surface yet")}
              description={t("entity.noTransferSurfaceDesc", "We need more labeled inflow/outflow history before this panel looks like Arkham's transfer explorer.")}
            />
          </div>
        )}
      </div>
    </div>
  )

  const renderHoldingsTable = () => {
    if (holdings.length === 0) {
      return (
        <EmptyState
          icon="$$"
          title="No portfolio surface yet"
          description="Observed holdings will appear here as more entity-linked wallets are discovered across the tracked networks."
        />
      )
    }

    return (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: 16 }}>
        <div className="arkham-card">
          <div className="arkham-card-header">
            <span className="arkham-card-title">Observed Holdings ({holdings.length})</span>
          </div>
          <div className="arkham-card-body" style={{ padding: 0 }}>
            <table className="arkham-holders-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Chain</th>
                  <th>Wallets</th>
                  <th>Balance</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {holdings.map((holding) => (
                  <tr
                    key={holding.key}
                    onClick={() => {
                      setSelectedHoldingKey(holding.key)
                      setSelectedSurfaceTokenKey(holding.key)
                    }}
                    style={{
                      cursor: "pointer",
                      background: selectedHolding?.key === holding.key ? "rgba(50,130,255,0.08)" : undefined,
                    }}
                  >
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                        <LogoAvatar
                          name={holding.name}
                          symbol={holding.symbol}
                          size={22}
                          title={holding.name || holding.symbol}
                        />
                        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                          <span style={{ color: "var(--text-1)", fontWeight: 600 }}>{holding.symbol}</span>
                          <span style={{ color: "var(--text-4)", fontSize: 10 }}>{holding.name}</span>
                        </div>
                      </div>
                    </td>
                    <td>{holding.chain}</td>
                  <td>{holding.wallet_count ?? "-"}</td>
                    <td className="bal">{formatTokenAmount(holding.human_balance_total, holding.symbol)}</td>
                    <td className="bal">{holding.estimated_value_usd != null ? formatUsd(holding.estimated_value_usd) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="arkham-card">
          <div className="arkham-card-header">
            <span className="arkham-card-title">Asset Detail</span>
          </div>
          <div className="arkham-card-body">
            {selectedHolding ? (
              <div className="arkham-metrics">
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Symbol</span>
                  <span className="arkham-metric-value">{selectedHolding.symbol}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Chain</span>
                  <span className="arkham-metric-value">{selectedHolding.chain}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Observed Value</span>
                  <span className="arkham-metric-value">
                    {selectedHolding.estimated_value_usd != null ? formatUsd(selectedHolding.estimated_value_usd) : "-"}
                  </span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Portfolio Share</span>
                  <span className="arkham-metric-value">
                    {totalObservedValue > 0 ? formatPct((safeNumber(selectedHolding.estimated_value_usd) / totalObservedValue) * 100) : "-"}
                  </span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Wallet Count</span>
                  <span className="arkham-metric-value">{selectedHolding.wallet_count ?? "-"}</span>
                </div>
                <div className="arkham-metric">
                  <span className="arkham-metric-label">Largest Holder Share</span>
                  <span className="arkham-metric-value">{formatPct(selectedHolding.max_holder_share_pct)}</span>
                </div>
              </div>
            ) : (
              <div style={{ color: "var(--text-4)", fontSize: 11 }}>Select an asset row to inspect its observed footprint.</div>
            )}
          </div>
        </div>
      </div>
    )
  }

  const renderWalletsTable = () => {
    if (wallets.length === 0) {
      return (
        <EmptyState
          icon="OO"
          title="Wallet graph still sparse"
          description="This page already knows the entity profile, but we still need more labeled wallets and transfer history to mirror Arkham's full entity graph."
        />
      )
    }

    return (
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.8fr", gap: 16 }}>
        <div className="arkham-card">
          <div className="arkham-card-header">
            <span className="arkham-card-title">Wallet Intelligence ({wallets.length})</span>
          </div>
          <div className="arkham-card-body" style={{ padding: 0 }}>
            <table className="arkham-holders-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Wallet</th>
                  <th>Role</th>
                  <th>Assets</th>
                  <th>Observed Value</th>
                </tr>
              </thead>
              <tbody>
                {wallets.map((wallet, index) => (
                  <tr
                    key={wallet.key}
                    onClick={() => setSelectedWalletAddress(wallet.key)}
                    style={{
                      cursor: "pointer",
                      background: selectedWallet?.key === wallet.key ? "rgba(50,130,255,0.08)" : undefined,
                    }}
                  >
                    <td><span className={`arkham-rank ${index < 3 ? "top" : ""}`}>{index + 1}</span></td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                        <LogoAvatar
                          name={wallet.entity || wallet.labelText}
                          symbol={wallet.chain || wallet.labelText}
                          size={22}
                          title={wallet.entity || wallet.labelText}
                        />
                        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                          <span className="addr" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{wallet.labelText}</span>
                          <span style={{ color: "var(--text-4)", fontSize: 10, fontFamily: "var(--font-mono)" }}>
                            {truncateAddr(wallet.address)}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td>{(wallet.flags || []).slice(0, 2).map((flag: string) => titleCase(flag)).join(", ") || titleCase(wallet.wallet_type || "wallet")}</td>
                    <td>{wallet.tokenCount || "-"}</td>
                    <td className="bal">{wallet.observed_value_usd != null ? formatUsd(wallet.observed_value_usd) : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="arkham-card">
          <div className="arkham-card-header">
            <span className="arkham-card-title">Wallet Detail</span>
          </div>
          <div className="arkham-card-body">
            {selectedWallet ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div
                  style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                    <LogoAvatar
                      name={selectedWallet.entity || selectedWallet.labelText}
                      symbol={selectedWallet.chain || selectedWallet.labelText}
                      size={28}
                      title={selectedWallet.entity || selectedWallet.labelText}
                    />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                        {selectedWallet.labelText}
                      </div>
                      <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                        {selectedWallet.entity || "Observed wallet"} | {titleCase(selectedWalletChain)}
                      </div>
                      <div style={{ marginTop: 8, color: "var(--text-4)", fontFamily: "var(--font-mono)", fontSize: 11, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                        {selectedWallet.address}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                    {selectedWalletExplorerUrl && (
                      <a
                        href={selectedWalletExplorerUrl || undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid var(--blue-bright)",
                          color: "var(--blue-bright)",
                          textDecoration: "none",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: 0.45,
                        }}
                      >
                        Open Explorer
                      </a>
                    )}
                    {selectedWalletTransferMatches.length > 0 && (
                      <button
                        onClick={() => {
                          setTransferFilter("all")
                          setActiveTab("transfers")
                          setSelectedTransferKey(selectedWalletTransferMatches[0].tx_hash)
                        }}
                        style={{
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid var(--border)",
                          background: "var(--bg-card)",
                          color: "var(--text-2)",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: 0.45,
                        }}
                      >
                        {selectedWalletTransferMatches.length} related transfers
                      </button>
                    )}
                    {(selectedWallet.flags || []).slice(0, 4).map((flag: string) => (
                      <span
                        key={flag}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid var(--border)",
                          color: "var(--text-3)",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: 0.45,
                        }}
                      >
                        {flag}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="arkham-metrics">
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Confidence</span>
                    <span className="arkham-metric-value">{titleCase(selectedWallet.confidence || "unknown")}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Observed Value</span>
                    <span className="arkham-metric-value">{selectedWallet.observed_value_usd != null ? formatUsd(selectedWallet.observed_value_usd) : "-"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Activity Bucket</span>
                    <span className="arkham-metric-value">{titleCase(selectedWallet.activity_profile?.activity_bucket || "unknown")}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Transactions</span>
                    <span className="arkham-metric-value">{selectedWallet.activity_profile?.transactions_count ?? "-"}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Transfers</span>
                    <span className="arkham-metric-value">{selectedWallet.activity_profile?.token_transfers_count ?? selectedWalletTransferMatches.length}</span>
                  </div>
                  <div className="arkham-metric">
                    <span className="arkham-metric-label">Assets Seen</span>
                    <span className="arkham-metric-value">{selectedWallet.tokenCount || "-"}</span>
                  </div>
                </div>

                {selectedWalletTransferMatches.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Latest Related Transfers
                    </div>
                    {selectedWalletTransferMatches.slice(0, 3).map((item) => (
                      <button
                        key={item.tx_hash}
                        onClick={() => {
                          setTransferFilter("all")
                          setActiveTab("transfers")
                          setSelectedTransferKey(item.tx_hash)
                        }}
                        style={{
                          cursor: "pointer",
                          textAlign: "left",
                          borderRadius: 12,
                          border: "1px solid var(--border)",
                          background: "var(--bg-void)",
                          padding: "10px 12px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                          <span style={{ color: "var(--text-2)", fontSize: 11 }}>
                            {item.token_symbol || t("entity.asset", "Asset")} | {flowDirectionLabel(item.direction)}
                          </span>
                          <span style={{ color: item.direction === "inflow" ? "var(--green)" : "var(--red)", fontSize: 11 }}>
                            {item.value_usd != null ? formatUsd(item.value_usd) : formatTokenAmount(item.amount, item.token_symbol)}
                          </span>
                        </div>
                        <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                          {localizedActivityTimeAgo(item.timestamp)} | {item.counterparty_label || t("entity.unknownCounterparty", "Unknown counterparty")}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ color: "var(--text-4)", fontSize: 11 }}>Select a wallet row to inspect it.</div>
            )}
          </div>
        </div>
      </div>
    )
  }

  const renderCounterpartiesTable = () => {
    if (counterparties.length === 0) {
      return (
        <EmptyState
          icon="<>"
          title="Counterparty graph still thin"
          description="This is where we will expose exchange routing, linked-wallet clusters and manipulation-relevant counterparties once the transfer cache gets denser."
        />
      )
    }

    return (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 16 }}>
        <div className="arkham-card">
          <div className="arkham-card-header">
            <span className="arkham-card-title">Top Counterparties ({counterparties.length})</span>
          </div>
          <div className="arkham-card-body" style={{ padding: 0 }}>
            <table className="arkham-holders-table">
              <thead>
                <tr>
                  <th>Counterparty</th>
                  <th>Address</th>
                  <th>Flow</th>
                  <th>Tx</th>
                </tr>
              </thead>
              <tbody>
                {counterparties.map((cp) => (
                  <tr
                    key={cp.key}
                    onClick={() => setSelectedCounterpartyKey(cp.key)}
                    style={{
                      cursor: "pointer",
                      background: selectedCounterparty?.key === cp.key ? "rgba(50,130,255,0.08)" : undefined,
                    }}
                  >
                    <td style={{ width: "46%", minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                        <LogoAvatar
                          name={cp.detailLabel}
                          symbol={cp.detailLabel}
                          size={22}
                          title={cp.detailLabel}
                        />
                        <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
                          <span
                            style={{
                              color: "var(--text-1)",
                              fontSize: 12,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {cp.tableLabel}
                          </span>
                          <span
                            style={{
                              color: "var(--text-4)",
                              fontSize: 10,
                              fontFamily: "var(--font-mono)",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {cp.address ? truncateAddr(cp.address, 6) : "unlabeled"}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="addr">
                      {cp.address && getExplorerAddressUrl(cp.address, cp.chain || defaultExplorerChain) ? (
                        <a
                          href={getExplorerAddressUrl(cp.address, cp.chain || defaultExplorerChain) || undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          style={{ color: "var(--blue-bright)" }}
                        >
                          {truncateAddr(cp.address, 4)}
                        </a>
                      ) : (
                        cp.address ? truncateAddr(cp.address, 4) : "-"
                      )}
                    </td>
                    <td className="bal">{cp.value_usd != null ? formatUsd(cp.value_usd) : "-"}</td>
                    <td>{cp.tx_count || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="arkham-card">
          <div className="arkham-card-header">
            <span className="arkham-card-title">Counterparty Detail</span>
          </div>
          <div className="arkham-card-body">
            {selectedCounterparty ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div
                  style={{
                    padding: "12px 14px",
                    borderRadius: 12,
                    border: "1px solid var(--border)",
                    background: "var(--bg-void)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                    <LogoAvatar
                      name={selectedCounterparty.detailLabel}
                      symbol={selectedCounterparty.detailLabel}
                      size={28}
                      title={selectedCounterparty.detailLabel}
                    />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
                        Counterparty
                      </div>
                      <div style={{ color: "var(--text-1)", fontSize: 16, fontWeight: 600, marginTop: 6, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                        {selectedCounterparty.detailLabel}
                      </div>
                      <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4 }}>
                        {selectedCounterparty.address ? "Observed address" : "Label-only surface"} | {titleCase(selectedCounterpartyChain)}
                      </div>
                      <div
                        style={{
                          marginTop: 8,
                          color: "var(--text-4)",
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          overflowWrap: "anywhere",
                          wordBreak: "break-word",
                        }}
                      >
                        {selectedCounterpartyExplorerUrl ? (
                          <a
                            href={selectedCounterpartyExplorerUrl || undefined}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ color: "var(--blue-bright)", textDecoration: "none" }}
                          >
                            {selectedCounterparty.address}
                          </a>
                        ) : (
                          selectedCounterparty.address || "-"
                        )}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                    {selectedCounterpartyExplorerUrl && (
                      <a
                        href={selectedCounterpartyExplorerUrl || undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid var(--blue-bright)",
                          color: "var(--blue-bright)",
                          textDecoration: "none",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: 0.45,
                        }}
                      >
                        Open Explorer
                      </a>
                    )}
                    {selectedCounterpartyTransferMatches.length > 0 && (
                      <button
                        onClick={() => {
                          setTransferFilter("all")
                          setActiveTab("transfers")
                          setSelectedTransferKey(selectedCounterpartyTransferMatches[0].tx_hash)
                        }}
                        style={{
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid var(--border)",
                          background: "var(--bg-card)",
                          color: "var(--text-2)",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: 0.45,
                        }}
                      >
                        {selectedCounterpartyTransferMatches.length} related transfers
                      </button>
                    )}
                    {selectedCounterparty.inflow_count > 0 && (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid rgba(0,224,163,0.25)",
                          color: "var(--green)",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: 0.45,
                        }}
                      >
                        Inflow surface
                      </span>
                    )}
                    {selectedCounterparty.outflow_count > 0 && (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid rgba(255,90,122,0.25)",
                          color: "var(--red)",
                          fontSize: 10,
                          textTransform: "uppercase",
                          letterSpacing: 0.45,
                        }}
                      >
                        Outflow surface
                      </span>
                    )}
                  </div>
                </div>

                <div className="arkham-metrics">
                  <div className="arkham-metric" style={{ minWidth: 0 }}>
                    <span className="arkham-metric-label">Observed Value</span>
                    <span className="arkham-metric-value">{selectedCounterparty.value_usd != null ? formatUsd(selectedCounterparty.value_usd) : "-"}</span>
                  </div>
                  <div className="arkham-metric" style={{ minWidth: 0 }}>
                    <span className="arkham-metric-label">Tx Count</span>
                    <span className="arkham-metric-value">{selectedCounterparty.tx_count || 0}</span>
                  </div>
                  <div className="arkham-metric" style={{ minWidth: 0 }}>
                    <span className="arkham-metric-label">Inflow Count</span>
                    <span className="arkham-metric-value">{selectedCounterparty.inflow_count || 0}</span>
                  </div>
                  <div className="arkham-metric" style={{ minWidth: 0 }}>
                    <span className="arkham-metric-label">Outflow Count</span>
                    <span className="arkham-metric-value">{selectedCounterparty.outflow_count || 0}</span>
                  </div>
                  <div className="arkham-metric" style={{ minWidth: 0 }}>
                    <span className="arkham-metric-label">Direction Bias</span>
                    <span className="arkham-metric-value">
                      {selectedCounterparty.inflow_count > selectedCounterparty.outflow_count
                        ? "Inbound"
                        : selectedCounterparty.outflow_count > selectedCounterparty.inflow_count
                          ? "Outbound"
                          : "Balanced"}
                    </span>
                  </div>
                  <div className="arkham-metric" style={{ minWidth: 0 }}>
                    <span className="arkham-metric-label">Latest Match</span>
                    <span className="arkham-metric-value">
                      {selectedCounterpartyTransferMatches[0]
                    ? localizedActivityTimeAgo(selectedCounterpartyTransferMatches[0].timestamp)
                        : "-"}
                    </span>
                  </div>
                </div>

                {selectedCounterpartyTransferMatches.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ color: "var(--text-4)", fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      Latest Related Transfers
                    </div>
                    {selectedCounterpartyTransferMatches.slice(0, 4).map((item) => (
                      <button
                        key={item.tx_hash}
                        onClick={() => {
                          setTransferFilter("all")
                          setActiveTab("transfers")
                          setSelectedTransferKey(item.tx_hash)
                        }}
                        style={{
                          cursor: "pointer",
                          textAlign: "left",
                          borderRadius: 12,
                          border: "1px solid var(--border)",
                          background: "var(--bg-void)",
                          padding: "10px 12px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                          <span style={{ color: "var(--text-2)", fontSize: 11 }}>
                          {item.token_symbol || t("entity.asset", "Asset")} | {flowDirectionLabel(item.direction)}
                          </span>
                          <span style={{ color: item.direction === "inflow" ? "var(--green)" : "var(--red)", fontSize: 11 }}>
                            {item.value_usd != null ? formatUsd(item.value_usd) : formatTokenAmount(item.amount, item.token_symbol)}
                          </span>
                        </div>
                        <div style={{ color: "var(--text-4)", fontSize: 10, marginTop: 4, display: "flex", flexWrap: "wrap", gap: 8 }}>
                        <span>{localizedActivityTimeAgo(item.timestamp)}</span>
                          <span>{item.wallet_label || (item.wallet_address ? truncateAddr(item.wallet_address) : "Unknown wallet")}</span>
                          {item.tx_hash && getExplorerTxUrl(item.tx_hash, item.chain || selectedCounterpartyChain) && (
                            <a
                              href={getExplorerTxUrl(item.tx_hash, item.chain || selectedCounterpartyChain) || undefined}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(event) => event.stopPropagation()}
                              style={{ color: "var(--blue-bright)", textDecoration: "none" }}
                            >
                              View tx ↗
                            </a>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ color: "var(--text-4)", fontSize: 11 }}>Select a counterparty row to inspect it.</div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="arkham-content">
      {renderHero()}

      <div className="arkham-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`arkham-tab ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.count != null && <span className="arkham-tab-count">{tab.count}</span>}
          </button>
        ))}
      </div>

      {activeTab === "overview" && (
        <div style={{ display: "grid", gap: 16, marginTop: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1.05fr 1fr", gap: 16 }}>
            {renderObservedPortfolioPanel()}
            {renderObservedSurfacePanel()}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1.1fr", gap: 16 }}>
            {renderFlowIntelPanel()}
            {renderTransferPanel()}
          </div>
        </div>
      )}

      {activeTab === "portfolio" && (
        <div style={{ marginTop: 16 }}>
          {renderHoldingsTable()}
        </div>
      )}

      {activeTab === "wallets" && (
        <div style={{ marginTop: 16 }}>
          {renderWalletsTable()}
        </div>
      )}

      {activeTab === "counterparties" && (
        <div style={{ marginTop: 16 }}>
          {renderCounterpartiesTable()}
        </div>
      )}

      {activeTab === "transfers" && (
        <div style={{ marginTop: 16 }}>
          {renderTransferPanel()}
        </div>
      )}
    </div>
  )
}
