import { useState, useRef, useEffect, useCallback } from "react"
import { useMarket } from "../../contexts/WSContext"
import LogoAvatar from "../LogoAvatar"
import { useLanguage } from "../../i18n"
import { apiUrl } from "../../services/api"

// =========================================================
// TOPBAR — with Live Search (ARK Intelligence Style)
// Now supports: tokens, addresses (0x...), entities, and CoinGecko results
// =========================================================

const PAGE_LABELS: Record<string, string> = {
  dashboard: "MARKETS",
  agents: "AGENTS",
  vision: "VISION",
  desktop: "CONTROL",
  chat: "CHAT",
  terminal: "TERMINAL",
  entity: "ENTITY",
}

interface SearchResult {
  id: string
  type: string
  name: string
  label: string
  price?: number | string
  balance?: string
  address?: string
  source?: string
  score?: number
  // Token-specific
  symbol?: string
  contract_address?: string
  market_cap_rank?: number
  thumb?: string
  // Arkham-specific
  slug?: string
  category?: string
  wallet_count?: number
  chains?: string[]
}

interface TopBarProps {
  page: string
  onEntitySelect?: (entityId: string) => void
  onArkhamPageOpen?: (entityId: string) => void
}

// Normalize for dedup: "BTCUSDT" → "btc"
const normalizeForDedup = (name: string): string => {
  return name.toLowerCase().trim()
    .replace(/usdt$/, "").replace(/usd$/, "").replace(/_?usd$/, "").replace(/\/usd$/, "")
    .replace(/perp$/, "").replace(/_?funding$/, "")
    .replace(/[^a-z0-9]/g, "")
    .trim()
}

const TYPE_PRIORITY: Record<string, number> = {
  arkham_entity: 0, entity: 1, arkham_label: 2, address: 3, token: 4, funding: 5, gainer: 6,
}

const formatCategory = (value?: string): string | null => {
  if (!value) return null
  return value.replace(/_/g, " ").toUpperCase()
}

const toFiniteNumber = (value: unknown): number | null => {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

const firstFiniteNumber = (...values: unknown[]): number | null => {
  for (const value of values) {
    const numeric = toFiniteNumber(value)
    if (numeric != null) return numeric
  }
  return null
}

const firstUsefulPercent = (...values: unknown[]): number | null => {
  for (const value of values) {
    const numeric = toFiniteNumber(value)
    if (numeric != null && Math.abs(numeric) >= 0.0001) return numeric
  }
  return null
}

const formatTickerPrice = (value: number | null, decimals = 0) => (
  value == null
    ? "-"
    : `$${value.toLocaleString(undefined, {
        maximumFractionDigits: decimals,
        minimumFractionDigits: decimals,
      })}`
)

const formatTickerPercent = (value: number | null) => (
  value == null ? null : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`
)

export default function TopBar({ page, onEntitySelect, onArkhamPageOpen }: TopBarProps) {
  const { data, connected } = useMarket()
  const { language, toggleLanguage, t } = useLanguage()
  const btc = data?.hyperliquid?.BTC
  const eth = data?.hyperliquid?.ETH
  const xau = data?.xauusd

  const [query, setQuery] = useState("")
  const [prices, setPrices] = useState<any>({})
  const [results, setResults] = useState<SearchResult[]>([])
  const [isOpen, setIsOpen] = useState(false)
  const [selectedIdx, setSelectedIdx] = useState(-1)
  const [loading, setLoading] = useState(false)
  const [clock, setClock] = useState(new Date())
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    const fetchPrices = async () => {
      try {
        const response = await fetch("/api/market/prices")
        if (!response.ok) return
        setPrices(await response.json())
      } catch {}
    }
    void fetchPrices()
    const timer = window.setInterval(fetchPrices, 15000)
    return () => window.clearInterval(timer)
  }, [])

  // Search: merge local + Arkham + CoinGecko results with dedup
  const search = useCallback(async (q: string) => {
    if (!q || q.length < 1) { setResults([]); setIsOpen(false); return }
    setLoading(true)
    try {
      const qLower = q.trim().toLowerCase()
      const rankMatch = (candidate?: string, exact = 110, prefix = 90, contains = 70): number => {
        const text = (candidate || "").toLowerCase().trim()
        if (!text) return 0
        if (text === qLower) return exact
        if (text.startsWith(qLower)) return prefix
        if (text.includes(qLower)) return contains
        return 0
      }

      const host = window.location.hostname
      const [localRes, arkhamRes] = await Promise.allSettled([
        fetch(apiUrl(`/search?q=${encodeURIComponent(q)}&limit=8`)),
        fetch(apiUrl(`/arkham/search?q=${encodeURIComponent(q)}&limit=8`)),
      ])
      const merged: SearchResult[] = []

      // Local results
      if (localRes.status === "fulfilled" && localRes.value.ok) {
        const d = await localRes.value.json()
        merged.push(...(d.results || []))
      }

      // Arkham results (entities + wallets + tokens)
      if (arkhamRes.status === "fulfilled" && arkhamRes.value.ok) {
        const d = await arkhamRes.value.json()

        // Arkham entities
        const arkhamEntities = (d.entities || []).map((e: any) => ({
          id: e.slug ? `arkham_${e.slug}` : `arkham_${e.name}`,
          type: e.type === "exchange" || e.type === "fund" || e.type === "market_maker" ? "arkham_entity" : "arkham_entity",
          name: e.name || e.slug,
          label: e.name || e.slug,
          balance: e.balance_usd ? `$${e.balance_usd}` : undefined,
          slug: e.slug,
          category: e.category,
          wallet_count: e.wallet_count,
          chains: e.chains,
          source: e.source || "arkham",
          score: Math.max(rankMatch(e.name, 145, 120, 95), rankMatch(e.slug, 140, 115, 92), 55),
        }))
        merged.push(...arkhamEntities)

        // Arkham wallets
        const arkhamWallets = (d.wallets || []).map((w: any) => ({
          id: `arkham_${w.address || w.label}`,
          type: "arkham_label",
          name: w.label || w.address?.slice(0, 10) || "Wallet",
          label: w.label || w.address?.slice(0, 10) || "Wallet",
          address: w.address,
          source: "arkham",
          score: Math.max(rankMatch(w.label, 100, 85, 70), rankMatch(w.entity, 95, 80, 68), 40),
        }))
        merged.push(...arkhamWallets)

        // CoinGecko/Arkham token results
        const arkhamTokens = (d.tokens || []).map((t: any) => ({
          id: t.id ? `token_${t.id}` : `token_${t.symbol}`,
          type: "token",
          name: t.symbol || t.name,
          label: t.name || t.symbol,
          symbol: t.symbol,
          contract_address: t.contract_address,
          market_cap_rank: t.market_cap_rank,
          thumb: t.thumb,
          source: t.source || "coingecko",
          score: Math.max(rankMatch(t.symbol, 95, 82, 70), rankMatch(t.name, 88, 76, 62), 60),
        }))
        merged.push(...arkhamTokens)
      }

      // Dedup: 1 result per base name, keep highest priority
      const seenBases: Record<string, SearchResult> = {}
      for (const r of merged) {
        const base = normalizeForDedup(r.name)
        if (!base) continue
        const existing = seenBases[base]
        if (!existing) { seenBases[base] = r; continue }
        const ep = TYPE_PRIORITY[existing.type] ?? 99
        const np = TYPE_PRIORITY[r.type] ?? 99
        if (np < ep || (np === ep && (r.score || 0) > (existing.score || 0))) {
          seenBases[base] = r
        }
      }

      const seenIds = new Set<string>()
      const deduped = Object.values(seenBases)
        .sort((a, b) => (b.score || 0) - (a.score || 0))
        .filter(r => { if (seenIds.has(r.id)) return false; seenIds.add(r.id); return true })

      setResults(deduped.slice(0, 12))
      setIsOpen(true)
      setSelectedIdx(-1)
    } catch { setResults([]) }
    finally { setLoading(false) }
  }, [])

  const onQueryChange = useCallback((val: string) => {
    setQuery(val)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => search(val), 250)
  }, [search])

  // Keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "/" && document.activeElement !== inputRef.current && !e.ctrlKey && !e.metaKey) {
        const tag = (e.target as HTMLElement)?.tagName
        if (tag === "INPUT" || tag === "TEXTAREA") return
        e.preventDefault()
        inputRef.current?.focus()
        return
      }
      if (!isOpen) return
      if (e.key === "Escape") { setIsOpen(false); inputRef.current?.blur() }
      else if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIdx(i => Math.min(i + 1, results.length - 1)) }
      else if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIdx(i => Math.max(i - 1, 0)) }
      else if (e.key === "Enter" && selectedIdx >= 0 && results[selectedIdx]) {
        e.preventDefault()
        selectEntity(results[selectedIdx])
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [isOpen, results, selectedIdx])

  // Close dropdown on outside click
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setIsOpen(false)
    }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [])

  function selectEntity(entity: SearchResult) {
    setIsOpen(false); setQuery(""); inputRef.current?.blur()

    // Route by type
    if (entity.type === "arkham_entity" || entity.type === "arkham_label") {
      // Arkham entity → full overlay page
      onArkhamPageOpen?.(entity.id)
    } else if (entity.type === "token") {
      // Token → open ArkhamEntityPage with token_ prefix for token detail view
      const tokenId = entity.id.startsWith("token_") ? entity.id : `token_${entity.id}`
      onArkhamPageOpen?.(tokenId)
    } else if (entity.type === "address") {
      // Address → open ArkhamEntityPage with address lookup
      onArkhamPageOpen?.(`addr_${entity.address}`)
    } else {
      // Local entities → slide-in panel
      onEntitySelect?.(entity.id)
    }
  }

  const TYPE_BADGE: Record<string, { label: string; color: string }> = {
    token: { label: "TKN", color: "var(--blue-bright)" },
    entity: { label: "ORG", color: "var(--purple)" },
    funding: { label: "FR", color: "var(--amber)" },
    gainer: { label: "TOP", color: "var(--green)" },
    arkham_entity: { label: "ARK", color: "var(--cyan)" },
    arkham_label: { label: "LBL", color: "var(--cyan)" },
    address: { label: "ADR", color: "var(--amber)" },
  }

  // Group results by category for Arkham-style sections
  const CATEGORIES = [
    { key: "token", label: "Tokens", icon: "◆", types: new Set(["token"]) },
    { key: "entity", label: "Entities", icon: "▣", types: new Set(["entity", "arkham_entity", "arkham_label"]) },
    { key: "address", label: "Addresses", icon: "◎", types: new Set(["address"]) },
    { key: "market", label: "Markets", icon: "⚗", types: new Set(["funding", "gainer"]) },
  ]

  const groupedResults = CATEGORIES.map(cat => ({
    ...cat,
    items: results.filter(r => cat.types.has(r.type)),
  }))
    .filter(g => g.items.length > 0)
    .sort((a, b) => {
      const bestA = Math.max(...a.items.map(item => item.score || 0))
      const bestB = Math.max(...b.items.map(item => item.score || 0))
      return bestB - bestA
    })

  // Flatten with section markers for keyboard navigation
  const flatNav: (SearchResult | { section: string })[] = []
  for (const g of groupedResults) {
    flatNav.push({ section: g.label })
    for (const item of g.items) flatNav.push(item)
  }

  // Map flat index to actual result index
  const resultIndexMap: number[] = []
  let idx = 0
  for (const item of flatNav) {
    if ("section" in item) continue
    resultIndexMap.push(idx)
    idx++
  }

  const btcPrice = firstFiniteNumber(btc?.px, data?.binance?.btc?.price, prices?.btc?.price)
  const ethPrice = firstFiniteNumber(eth?.px, data?.binance?.eth?.price, prices?.eth?.price)
  const xauPrice = firstFiniteNumber(xau?.bid, xau?.price, prices?.xau?.bid, prices?.xau?.price)
  const btcChange = firstUsefulPercent(data?.binance?.btc?.change_24h, prices?.btc?.change_24h, btc?.change_24h)
  const ethChange = firstUsefulPercent(data?.binance?.eth?.change_24h, prices?.eth?.change_24h, eth?.change_24h)
  const xauChange = firstUsefulPercent(xau?.change_24h, prices?.xau?.change_24h)

  return (
    <div className="topbar">
      <span className="topbar-title">{t(`nav.${page}`, PAGE_LABELS[page] || page)}</span>

      {/* Search bar */}
      <div className="topbar-search-container" ref={containerRef}>
        <div className="topbar-search">
          <span className="topbar-search-icon">{loading ? "◎" : "⌕"}</span>
          <input
            ref={inputRef}
            className="topbar-search-input"
            type="text"
            placeholder={t("search.placeholder")}
            value={query}
            onChange={e => onQueryChange(e.target.value)}
            onFocus={() => { if (results.length) setIsOpen(true) }}
          />
          <span className="topbar-search-hint">/</span>
        </div>

        {isOpen && results.length > 0 && (
          <div className="search-dropdown">
            {groupedResults.map(group => (
              <div key={group.key}>
                <div className="search-section-header">
                  <span className="search-section-icon">{group.icon}</span>
                  {group.label}
                  <span style={{ marginLeft: "auto", opacity: 0.5 }}>{group.items.length}</span>
                </div>
                {group.items.map((r) => {
                  const globalIdx = results.indexOf(r)
                  const isActive = selectedIdx === globalIdx
                  return (
                    <div
                      key={r.id}
                      className={`search-result${isActive ? " active" : ""}`}
                      onClick={() => selectEntity(r)}
                      onMouseEnter={() => setSelectedIdx(globalIdx)}
                    >
                      <LogoAvatar
                        name={r.name}
                        symbol={r.symbol || r.name}
                        src={r.thumb}
                        size={18}
                        title={r.name}
                      />
                      <span className="search-result-name">{r.name}</span>
                      {r.symbol && r.symbol !== r.name && (
                        <span className="search-result-label">${r.symbol}</span>
                      )}
                      {r.address && (
                        <span className="search-result-meta">
                          {r.address.slice(0, 6)}...{r.address.slice(-4)}
                        </span>
                      )}
                      {!r.address && r.category && (
                        <span className="search-result-meta">{formatCategory(r.category)}</span>
                      )}
                      {r.market_cap_rank && (
                        <span className="search-result-meta">#{r.market_cap_rank}</span>
                      )}
                      {r.balance && <span className="search-result-price">{r.balance}</span>}
                    </div>
                  )
                })}
              </div>
            ))}
            <div className="search-footer">
              {results.length} {t("search.footer")}
            </div>
          </div>
        )}

        {isOpen && query && !loading && results.length === 0 && (
          <div className="search-dropdown">
            <div className="search-empty">{t("search.empty")} "{query}"</div>
          </div>
        )}

        {isOpen && loading && (
          <div className="search-dropdown">
            <div className="search-loading">◎ {t("search.loading")}</div>
          </div>
        )}
      </div>

      {/* Ticker chips */}
      <div className="topbar-right">
        {btcPrice != null && (
          <div className="ticker-chip" onClick={() => onEntitySelect?.("hl_BTC")} title="BTC detail">
            <span className="ticker-chip-name-group">
              <LogoAvatar name="Bitcoin" symbol="BTC" size={16} square />
              <span className="ticker-chip-name">BTC</span>
            </span>
            <span className="ticker-chip-price">{formatTickerPrice(btcPrice)}</span>
            {formatTickerPercent(btcChange) && (
              <span className={`ticker-chip-change ${btcChange != null && btcChange >= 0 ? "positive" : "negative"}`}>
                {formatTickerPercent(btcChange)}
              </span>
            )}
          </div>
        )}
        {ethPrice != null && (
          <div className="ticker-chip" onClick={() => onEntitySelect?.("hl_ETH")} title="ETH detail">
            <span className="ticker-chip-name-group">
              <LogoAvatar name="Ethereum" symbol="ETH" size={16} square />
              <span className="ticker-chip-name">ETH</span>
            </span>
            <span className="ticker-chip-price">{formatTickerPrice(ethPrice)}</span>
            {formatTickerPercent(ethChange) && (
              <span className={`ticker-chip-change ${ethChange != null && ethChange >= 0 ? "positive" : "negative"}`}>
                {formatTickerPercent(ethChange)}
              </span>
            )}
          </div>
        )}
        {xauPrice != null && (
          <div className="ticker-chip" onClick={() => onEntitySelect?.("xau_usd")} title="XAU detail">
            <span className="ticker-chip-name-group">
              <LogoAvatar name="Gold" symbol="XAU" size={16} square />
              <span className="ticker-chip-name">XAU</span>
            </span>
            <span className="ticker-chip-price">{formatTickerPrice(xauPrice, 2)}</span>
            {formatTickerPercent(xauChange) && (
              <span className={`ticker-chip-change ${xauChange != null && xauChange >= 0 ? "positive" : "negative"}`}>
                {formatTickerPercent(xauChange)}
              </span>
            )}
          </div>
        )}

        {/* Live status */}
        <div className={`live-status${connected ? "" : " offline"}`}>
          <span className={`live-dot ${connected ? "connected" : "disconnected"}`} />
          <span>{connected ? "LIVE" : "OFF"}</span>
        </div>

        <button className="language-toggle" onClick={toggleLanguage} title="Switch language">
          {language.toUpperCase()}
        </button>

        {/* Clock */}
        <span style={{ fontSize: 10, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
          {clock.toLocaleTimeString()}
        </span>
      </div>
    </div>
  )
}
