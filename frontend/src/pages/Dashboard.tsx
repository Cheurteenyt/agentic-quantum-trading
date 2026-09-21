import { useState, useEffect, useMemo } from "react"
import { useMarket } from "../contexts/WSContext"
import { OpportunityFeed } from "../components/OpportunityFeed"
import { OpportunitiesSidebar } from "../components/layout/OpportunitiesSidebar"
import LogoAvatar from "../components/LogoAvatar"
import { useLanguage } from "../i18n"
import { safeWalletRequest } from "../services/walletSafety"

const API = `/api`

interface AccountData {
  balance: number; equity: number; margin: number
  free_margin: number; profit: number; leverage: number
  currency: string; source: string
}

interface PositionData {
  ticket: number; symbol: string; type: "BUY" | "SELL"
  volume: number; open_price: number; current_price: number
  sl: number; tp: number; profit: number; time: string
}

interface SystemStatus {
  hyperliquid_collector: { connected: boolean }
  mt5_bridge: { status: string }
  multi_exchange_aggregator: {
    last_update: number
    funding_data_count?: number
    oi_data?: Record<string, unknown>
    top_gainers?: unknown[]
  }
}

interface IntelWatchEntity {
  id: string
  slug: string
  name: string
  type?: string
  category?: string
  source?: string
  wallet_count?: number | null
  chains?: string[]
}

interface ConnectedAccount {
  id: string
  label: string
  type: "evm" | "solana" | "hyperliquid" | "manual"
  provider: string
  address: string
  network: string
  status: "connected" | "tracked" | "pending"
  addedAt: number
  chainId?: string
  nativeBalance?: string
  nativeSymbol?: string
  verifiedAt?: number
}

type Eip6963Provider = {
  info: { uuid?: string; name?: string; rdns?: string; icon?: string }
  provider: any
}

interface DashboardProps {
  onEntitySelect?: (entityId: string) => void
}

const WATCH_QUERIES = ["binance", "blackrock", "okx", "uniswap", "polymarket", "pancakeswap"]
const WATCH_LABELS: Record<string, string> = {
  binance: "Binance",
  blackrock: "BlackRock",
  okx: "OKX",
  uniswap: "Uniswap",
  polymarket: "Polymarket",
  pancakeswap: "PancakeSwap",
}

const formatIntelCategory = (value?: string | null) =>
  String(value || "entity")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())

const formatIntelSource = (value?: string | null) => {
  if (!value) return "ARKHAM"
  if (value === "pending") return "SYNCING"
  if (value === "live_search") return "SCRAPLING"
  if (value === "free_db") return "STATIC DB"
  return String(value).replace(/_/g, " ").toUpperCase()
}

const getIntelSourceTone = (value?: string | null) => {
  if (value === "live_search") return "scrapling"
  if (value === "free_db") return "static"
  return "arkham"
}

const slugifyEntity = (value: string) =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")

const createWatchSeed = (query: string): IntelWatchEntity => {
  const slug = slugifyEntity(query)
  return {
    id: `arkham_${slug}`,
    slug,
    name: WATCH_LABELS[query] || formatIntelCategory(query),
    category: "tracked entity",
    source: "pending",
    wallet_count: null,
    chains: [],
  }
}

const mergeWatchEntity = (items: IntelWatchEntity[], next: IntelWatchEntity) =>
  items.map((item) => (item.id === next.id ? { ...item, ...next } : item))

const ACCOUNT_STORAGE_KEY = "core.connected.accounts"
const SELECTED_ALPHA_ACCOUNT_KEY = "core.alpha.selected.account"

const shortWallet = (value: string) =>
  value.length > 14 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value

const EVM_CHAINS: Record<string, { name: string; symbol: string }> = {
  "0x1": { name: "Ethereum", symbol: "ETH" },
  "0x38": { name: "BNB Chain", symbol: "BNB" },
  "0xa4b1": { name: "Arbitrum", symbol: "ETH" },
  "0x2105": { name: "Base", symbol: "ETH" },
  "0x89": { name: "Polygon", symbol: "MATIC" },
}

const formatNativeBalance = (hex?: string) => {
  if (!hex) return "-"
  try {
    const wei = BigInt(hex)
    const whole = Number(wei / 10n ** 14n) / 10_000
    return whole >= 100 ? whole.toFixed(2) : whole.toFixed(4)
  } catch {
    return "-"
  }
}

const pickEvmProvider = (providerLabel: "MetaMask" | "Rabby") => {
  const ethereum = (window as any).ethereum
  if (!ethereum) return null
  const providers = Array.isArray(ethereum?.providers) ? ethereum.providers : [ethereum]
  if (providerLabel === "Rabby") return providers.find((provider: any) => provider?.isRabby) || null
  return providers.find((provider: any) => provider?.isMetaMask) || (ethereum?.isMetaMask ? ethereum : null)
}

const detectWalletProviders = (eip6963: Eip6963Provider[] = []) => {
  const ethereum = (window as any).ethereum
  const providers = Array.isArray(ethereum?.providers) ? ethereum.providers : [ethereum].filter(Boolean)
  const eipNames = eip6963.map(({ info }) => `${info.rdns || ""} ${info.name || ""}`.toLowerCase())
  return {
    metamask: eipNames.some((name) => name.includes("metamask")) || providers.some((provider: any) => provider?.isMetaMask),
    rabby: eipNames.some((name) => name.includes("rabby")) || providers.some((provider: any) => provider?.isRabby),
    phantom: Boolean((window as any).phantom?.solana?.connect),
  }
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

const formatUsdPrice = (value: number | null, locale: string, decimals = 0) => (
  value == null
    ? "-"
    : `$${value.toLocaleString(locale, {
        maximumFractionDigits: decimals,
        minimumFractionDigits: decimals,
      })}`
)

const formatPercent = (value: number | null) => (
  value == null ? null : `${value >= 0 ? "+" : ""}${value.toFixed(Math.abs(value) < 1 ? 2 : 2)}%`
)

export default function Dashboard({ onEntitySelect }: DashboardProps) {
  const { t, language } = useLanguage()
  const { data: wsData, connected } = useMarket()
  const [account, setAccount] = useState<AccountData | null>(null)
  const [positions, setPositions] = useState<PositionData[]>([])
  const [stats, setStats] = useState<any>({})
  const [prices, setPrices] = useState<any>({})
  const [system, setSystem] = useState<SystemStatus>({
    hyperliquid_collector: { connected: false },
    mt5_bridge: { status: "checking" },
    multi_exchange_aggregator: { last_update: 0 },
  })
  const [intelWatchlist, setIntelWatchlist] = useState<IntelWatchEntity[]>(WATCH_QUERIES.map(createWatchSeed))
  const [intelLoading, setIntelLoading] = useState(false)
  const [showOpportunities, setShowOpportunities] = useState(false)
  const [connectedAccounts, setConnectedAccounts] = useState<ConnectedAccount[]>([])
  const [walletDraft, setWalletDraft] = useState("")
  const [walletNetwork, setWalletNetwork] = useState("ethereum")
  const [accountNotice, setAccountNotice] = useState("")
  const [walletProviders, setWalletProviders] = useState({ metamask: false, rabby: false, phantom: false })
  const [evmProviderList, setEvmProviderList] = useState<Eip6963Provider[]>([])
  const alphaWallets = useMemo(() => (
    connectedAccounts.filter((item) => (
      item.type !== "manual"
      && item.type !== "hyperliquid"
      && item.status === "connected"
    ))
  ), [connectedAccounts])
  const watchOnlyWallets = useMemo(() => (
    connectedAccounts.filter((item) => item.type === "manual" && item.status === "tracked")
  ), [connectedAccounts])
  const verifiedWallets = useMemo(() => (
    connectedAccounts.filter((item) => item.verifiedAt)
  ), [connectedAccounts])

  const trackAlphaUsage = (action: string, wallet?: string, extra: Record<string, unknown> = {}) => {
    void fetch(`${API}/alpha/usage/event`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page: "dashboard",
        action,
        wallet: wallet || "",
        connected_wallets: connectedAccounts.length,
        status: extra.status || "",
        extra,
      }),
    }).catch(() => {
      // Product analytics must never block wallet UX.
    })
  }

  const openAlphaLabForAccount = (item?: ConnectedAccount | null, action = "open_alpha_lab_clicked") => {
    if (!item?.address) return
    if (item.type === "manual" && alphaWallets.length === 0) {
      setAccountNotice("Connecte d'abord MetaMask, Rabby ou Phantom. Une adresse manuelle est watch-only et ne prouve pas l'identite du client.")
      trackAlphaUsage("open_alpha_lab_blocked_watch_only", item.address, { provider: item.provider, network: item.network, status: "blocked_watch_only" })
      return
    }
    try {
      localStorage.setItem(SELECTED_ALPHA_ACCOUNT_KEY, JSON.stringify({
        address: item.address,
        provider: item.provider,
        network: item.network,
        role: item.type === "manual" ? "analysis_target" : "client_wallet",
        selectedAt: Date.now(),
      }))
    } catch {
      // Navigation should still work if browser storage is unavailable.
    }
    trackAlphaUsage(action, item.address, { provider: item.provider, network: item.network, status: "selected" })
    window.location.href = "/alpha"
  }

  const fetchData = async () => {
    try {
      const [a, p, pr, sy] = await Promise.allSettled([
        fetch(`${API}/market/mt5/account`).then(r => r.json()),
        fetch(`${API}/market/mt5/positions`).then(r => r.json()),
        fetch(`${API}/market/prices`).then(r => r.json()),
        fetch(`${API}/services/status`).then(r => r.json()),
      ])
      if (a.status === "fulfilled" && a.value.source === "mt5_live") setAccount(a.value)
      else setAccount(null)
      if (p.status === "fulfilled" && p.value.source === "mt5_live") setPositions(p.value.positions || [])
      else setPositions([])
      if (pr.status === "fulfilled") setPrices(pr.value)
      if (sy.status === "fulfilled") setSystem(sy.value)
    } catch {}
  }

  useEffect(() => { fetchData(); const t = setInterval(fetchData, 3000); return () => clearInterval(t) }, [])

  useEffect(() => {
    const seen = new Set<string>()
    const discovered: Eip6963Provider[] = []
    const onProvider = (event: Event) => {
      const detail = (event as CustomEvent).detail
      if (!detail?.provider) return
      const key = detail.info?.uuid || detail.info?.rdns || detail.info?.name || String(discovered.length)
      if (seen.has(key)) return
      seen.add(key)
      discovered.push({ info: detail.info || {}, provider: detail.provider })
      setEvmProviderList([...discovered])
      setWalletProviders(detectWalletProviders(discovered))
    }

    window.addEventListener("eip6963:announceProvider", onProvider as EventListener)
    window.dispatchEvent(new Event("eip6963:requestProvider"))
    const timer = window.setTimeout(() => setWalletProviders(detectWalletProviders(discovered)), 500)

    return () => {
      window.removeEventListener("eip6963:announceProvider", onProvider as EventListener)
      window.clearTimeout(timer)
    }
  }, [])

  useEffect(() => {
    setWalletProviders(detectWalletProviders())
    try {
      const saved = localStorage.getItem(ACCOUNT_STORAGE_KEY)
      if (saved) setConnectedAccounts(JSON.parse(saved))
    } catch {}

    const ethereum = (window as any).ethereum
    if (ethereum?.request) {
      safeWalletRequest<string[]>(ethereum, { method: "eth_accounts" })
        .then(async (accounts: string[]) => {
          const address = accounts?.[0]
          if (!address) return
          const chainMeta = await refreshEvmAccount(address, "MetaMask")
          upsertConnectedAccount({
            id: `evm:${address.toLowerCase()}`,
            label: "Injected wallet",
            type: "evm",
            provider: "MetaMask",
            address,
            network: chainMeta?.network || "ethereum",
            status: "connected",
            addedAt: Date.now(),
            chainId: chainMeta?.chainId,
            nativeBalance: chainMeta?.nativeBalance,
            nativeSymbol: chainMeta?.nativeSymbol,
          })
        })
        .catch(() => {})
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(ACCOUNT_STORAGE_KEY, JSON.stringify(connectedAccounts))
  }, [connectedAccounts])

  const upsertConnectedAccount = (next: ConnectedAccount) => {
    setConnectedAccounts((current) => {
      const withoutDuplicate = current.filter((item) => item.address.toLowerCase() !== next.address.toLowerCase())
      return [next, ...withoutDuplicate].slice(0, 12)
    })
  }

  const removeConnectedAccount = (id: string) => {
    setConnectedAccounts((current) => {
      const removed = current.find((item) => item.id === id)
      if (removed) trackAlphaUsage("wallet_removed", removed.address, { provider: removed.provider, network: removed.network, status: "removed" })
      return current.filter((item) => item.id !== id)
    })
  }

  const selectEvmProvider = (providerLabel: "MetaMask" | "Rabby") => {
    const label = providerLabel.toLowerCase()
    const eip = evmProviderList.find(({ info }) => {
      const haystack = `${info.rdns || ""} ${info.name || ""}`.toLowerCase()
      return haystack.includes(label)
    })
    return eip?.provider || pickEvmProvider(providerLabel)
  }

  const refreshEvmAccount = async (address: string, providerLabel: "MetaMask" | "Rabby" = "MetaMask", providerOverride?: any) => {
    const provider = providerOverride || selectEvmProvider(providerLabel)
    if (!provider?.request) return null
    const [chainId, balanceHex] = await Promise.all([
      safeWalletRequest<string>(provider, { method: "eth_chainId" }).catch(() => "0x1"),
      safeWalletRequest<string | undefined>(provider, { method: "eth_getBalance", params: [address, "latest"] }).catch(() => undefined),
    ])
    const chain = EVM_CHAINS[String(chainId)] || { name: `Chain ${chainId}`, symbol: "NATIVE" }
    return {
      chainId: String(chainId),
      network: chain.name.toLowerCase().replace(/\s+/g, "_"),
      nativeSymbol: chain.symbol,
      nativeBalance: formatNativeBalance(balanceHex),
    }
  }

  const verifyEvmOwnership = async (item: ConnectedAccount) => {
    const provider = selectEvmProvider(item.provider === "Rabby" ? "Rabby" : "MetaMask")
    if (!provider?.request) {
      setWalletProviders(detectWalletProviders())
      setAccountNotice("Provider EVM non detecte pour signer la preuve. Reconnecte MetaMask ou Rabby.")
      return
    }
    if (false) {
      setAccountNotice("Provider EVM non detecte pour signer la preuve.")
      return
    }
    const message = `Core Equity wallet verification\nAddress: ${item.address}\nNetwork: ${item.network}\nTime: ${new Date().toISOString()}`
    try {
      const signature = await safeWalletRequest<string>(provider, {
        method: "personal_sign",
        params: [message, item.address],
      })
      const response = await fetch(`${API}/alpha/wallet/verify`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address: item.address,
          type: item.type,
          provider: item.provider,
          network: item.network,
          message,
          signature,
        }),
      })
      if (!response.ok) throw new Error("server verification failed")
      const result = await response.json()
      if (!result?.verified) throw new Error("server could not cryptographically verify this wallet")
      setConnectedAccounts((current) =>
        current.map((accountItem) =>
          accountItem.id === item.id
            ? { ...accountItem, verifiedAt: (result.verified_at || Date.now() / 1000) * 1000, status: "connected" }
            : accountItem,
        ),
      )
      setAccountNotice("Signature verifiee cryptographiquement cote serveur. Wallet lie a Core Equity.")
      trackAlphaUsage("wallet_verified", item.address, { provider: item.provider, network: item.network, status: "verified" })
    } catch (error: any) {
      const detail = String(error?.message || "")
      setAccountNotice(
        detail.includes("server")
          ? "Verification refusee: le serveur n'a pas pu prouver cryptographiquement que ce wallet t'appartient."
          : "Signature refusee, annulee ou rejetee par le serveur.",
      )
      trackAlphaUsage("wallet_verify_failed", item.address, { provider: item.provider, network: item.network, status: "failed", reason: detail.slice(0, 120) })
    }
  }

  const addManualWallet = () => {
    const address = walletDraft.trim()
    if (!address) return
    upsertConnectedAccount({
      id: `${walletNetwork}:${address.toLowerCase()}`,
      label: `${walletNetwork.toUpperCase()} wallet`,
      type: "manual",
      provider: "Manual track",
      address,
      network: walletNetwork,
      status: "tracked",
      addedAt: Date.now(),
    })
    setWalletDraft("")
    setAccountNotice("Wallet ajouté au suivi local. Alpha Lab pourra l'analyser sans reconnexion.")
    trackAlphaUsage("wallet_manual_added", address, { provider: "Manual track", network: walletNetwork, status: "tracked" })
  }

  const connectEvmWallet = async (providerLabel: "MetaMask" | "Rabby") => {
    const provider = pickEvmProvider(providerLabel)
    if (!provider?.request) {
      setAccountNotice(`${providerLabel} non détecté dans ce navigateur.`)
      return
    }
    try {
      const accounts = await safeWalletRequest<string[]>(provider, { method: "eth_requestAccounts" })
      const address = accounts?.[0]
      if (!address) return
      const chainMeta = await refreshEvmAccount(address, providerLabel)
      upsertConnectedAccount({
        id: `evm:${address.toLowerCase()}`,
        label: providerLabel,
        type: "evm",
        provider: providerLabel,
        address,
        network: chainMeta?.network || "ethereum",
        status: "connected",
        addedAt: Date.now(),
        chainId: chainMeta?.chainId,
        nativeBalance: chainMeta?.nativeBalance,
        nativeSymbol: chainMeta?.nativeSymbol,
      })
      setAccountNotice(`${providerLabel} connecté. Les soldes restent validés côté API/RPC avant affichage.`)
      trackAlphaUsage("wallet_connected", address, { provider: providerLabel, network: chainMeta?.network || "ethereum", status: "connected" })
    } catch {
      setAccountNotice(`${providerLabel} a refusé ou annulé la connexion.`)
      trackAlphaUsage("wallet_connect_failed", "", { provider: providerLabel, status: "failed" })
    }
  }

  const connectBrowserWallet = async (providerLabel: "MetaMask" | "Rabby") => {
    const provider = selectEvmProvider(providerLabel)
    if (!provider?.request) {
      setWalletProviders(detectWalletProviders(evmProviderList))
      setAccountNotice(`${providerLabel} non detecte. Ouvre Core Equity dans Brave/Chrome avec l'extension active, puis recharge la page.`)
      return
    }
    try {
      setAccountNotice(`${providerLabel}: ouverture de la demande de connexion...`)
      const accounts = await safeWalletRequest<string[]>(provider, { method: "eth_requestAccounts" })
      const address = accounts?.[0]
      if (!address) {
        setAccountNotice(`${providerLabel}: aucun compte retourne par l'extension.`)
        return
      }
      const chainMeta = await refreshEvmAccount(address, providerLabel, provider)
      upsertConnectedAccount({
        id: `evm:${address.toLowerCase()}`,
        label: providerLabel,
        type: "evm",
        provider: providerLabel,
        address,
        network: chainMeta?.network || "ethereum",
        status: "connected",
        addedAt: Date.now(),
        chainId: chainMeta?.chainId,
        nativeBalance: chainMeta?.nativeBalance,
        nativeSymbol: chainMeta?.nativeSymbol,
      })
      setAccountNotice(`${providerLabel} connecte. Core Equity ne demandera jamais ta seed phrase ni une transaction pour analyser.`)
      trackAlphaUsage("wallet_connected", address, { provider: providerLabel, network: chainMeta?.network || "ethereum", status: "connected" })
    } catch (error: any) {
      const code = error?.code
      const message = String(error?.message || "")
      if (code === 4001) {
        setAccountNotice(`${providerLabel}: connexion annulee dans l'extension. Si aucune popup ne s'est ouverte, desactive Brave Wallet par defaut ou choisis MetaMask comme wallet principal.`)
      } else if (code === -32002) {
        setAccountNotice(`${providerLabel}: une demande est deja ouverte. Regarde la popup de l'extension.`)
      } else if (message) {
        setAccountNotice(`${providerLabel}: ${message.slice(0, 140)}`)
      } else {
        setAccountNotice(`${providerLabel}: connexion impossible. Deverrouille l'extension puis recharge la page.`)
      }
      trackAlphaUsage("wallet_connect_failed", "", { provider: providerLabel, status: "failed", code })
    }
  }

  const connectPhantom = async () => {
    const phantom = (window as any).phantom?.solana
    if (!phantom?.connect) {
      setWalletProviders(detectWalletProviders())
      setAccountNotice("Phantom non detecte dans ce navigateur. Installe/active l'extension, puis recharge la page.")
      return
    }
    if (false) {
      setAccountNotice("Phantom non détecté dans ce navigateur.")
      return
    }
    try {
      const result = await phantom.connect()
      const address = result?.publicKey?.toString?.()
      if (!address) return
      upsertConnectedAccount({
        id: `solana:${address}`,
        label: "Phantom",
        type: "solana",
        provider: "Phantom",
        address,
        network: "solana",
        status: "connected",
        addedAt: Date.now(),
      })
      setAccountNotice("Phantom connecté. La valorisation Solana devra être enrichie côté RPC.")
      trackAlphaUsage("wallet_connected", address, { provider: "Phantom", network: "solana", status: "connected" })
    } catch {
      setAccountNotice("Phantom a refusé ou annulé la connexion.")
      trackAlphaUsage("wallet_connect_failed", "", { provider: "Phantom", status: "failed" })
    }
  }

  const trackHyperliquid = () => {
    const address = walletDraft.trim()
    if (!address) {
      setAccountNotice("Colle d'abord l'adresse wallet Hyperliquid à suivre.")
      return
    }
    upsertConnectedAccount({
      id: `hyperliquid:${address.toLowerCase()}`,
      label: "Hyperliquid",
      type: "hyperliquid",
      provider: "Hyperliquid account",
      address,
      network: "hyperliquid",
      status: "tracked",
      addedAt: Date.now(),
    })
    setWalletDraft("")
    setAccountNotice("Compte Hyperliquid ajouté au suivi. L'étape suivante sera la synchro PnL/perps via API.")
    trackAlphaUsage("wallet_manual_added", address, { provider: "Hyperliquid", network: "hyperliquid", status: "tracked" })
  }

  useEffect(() => {
    const ethereum = (window as any).ethereum
    if (!ethereum?.on) return

    const handleAccountsChanged = async (accounts: string[]) => {
      const address = accounts?.[0]
      if (!address) {
        setConnectedAccounts((current) => current.filter((item) => item.type !== "evm"))
        setAccountNotice("Wallet EVM deconnecte.")
        return
      }
      const chainMeta = await refreshEvmAccount(address, "MetaMask")
      upsertConnectedAccount({
        id: `evm:${address.toLowerCase()}`,
        label: "Injected wallet",
        type: "evm",
        provider: "MetaMask",
        address,
        network: chainMeta?.network || "ethereum",
        status: "connected",
        addedAt: Date.now(),
        chainId: chainMeta?.chainId,
        nativeBalance: chainMeta?.nativeBalance,
        nativeSymbol: chainMeta?.nativeSymbol,
      })
    }

    const handleChainChanged = () => {
      setAccountNotice("Reseau wallet change. Reconnecte ou rafraichis le wallet pour mettre a jour la balance.")
    }

    ethereum.on("accountsChanged", handleAccountsChanged)
    ethereum.on("chainChanged", handleChainChanged)
    return () => {
      ethereum.removeListener?.("accountsChanged", handleAccountsChanged)
      ethereum.removeListener?.("chainChanged", handleChainChanged)
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    const fetchWatchEntity = async (query: string): Promise<IntelWatchEntity | null> => {
      const controller = new AbortController()
      const timeout = window.setTimeout(() => controller.abort(), 4500)
      try {
        const response = await fetch(`${API}/arkham/search?q=${encodeURIComponent(query)}`, {
          signal: controller.signal,
        })
        if (!response.ok) return null
        const payload = await response.json()
        if (!payload?.entities?.length) return null
        const match = payload.entities.find((entity: any) => entity?.slug || entity?.name) || payload.entities[0]
        if (!match) return null
        const slug = String(match.slug || slugifyEntity(match.name || query))
        return {
          id: `arkham_${slug}`,
          slug,
          name: match.name || WATCH_LABELS[query] || query,
          type: match.type,
          category: match.category,
          source: match.source,
          wallet_count: match.wallet_count,
          chains: Array.isArray(match.chains) ? match.chains : [],
        } satisfies IntelWatchEntity
      } catch {
        return null
      } finally {
        window.clearTimeout(timeout)
      }
    }

    const fetchIntelWatchlist = async () => {
      setIntelLoading(true)
      setIntelWatchlist((current) => (current.length > 0 ? current : WATCH_QUERIES.map(createWatchSeed)))
      try {
        const responses = await Promise.allSettled(
          WATCH_QUERIES.map(async (query) => {
            const entity = await fetchWatchEntity(query)
            if (cancelled || !entity) return null
            setIntelWatchlist((current) => mergeWatchEntity(current, entity))
            return entity
          }),
        )

        if (cancelled) return

        const next = responses
          .map((result) => (result.status === "fulfilled" ? result.value : null))
          .filter(Boolean) as IntelWatchEntity[]

        if (next.length > 0) {
          setIntelWatchlist((current) =>
            current.map((item) => next.find((candidate) => candidate.id === item.id) || item),
          )
        }
      } catch {
        if (!cancelled) setIntelWatchlist(WATCH_QUERIES.map(createWatchSeed))
      } finally {
        if (!cancelled) setIntelLoading(false)
      }
    }

    void fetchIntelWatchlist()
    const timer = window.setInterval(() => {
      void fetchIntelWatchlist()
    }, 180000)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  const locale = language === "fr" ? "fr-FR" : "en-US"
  const fmt = (v: number) => v.toLocaleString(locale, { style: "currency", currency: "USD" })
  const btcPrice = firstFiniteNumber(wsData?.hyperliquid?.BTC?.px, wsData?.binance?.btc?.price, prices?.btc?.price)
  const ethPrice = firstFiniteNumber(wsData?.hyperliquid?.ETH?.px, wsData?.binance?.eth?.price, prices?.eth?.price)
  const xauPrice = firstFiniteNumber(wsData?.xauusd?.bid, wsData?.xauusd?.price, prices?.xau?.bid, prices?.xau?.price)
  const btcChange = firstUsefulPercent(wsData?.binance?.btc?.change_24h, prices?.btc?.change_24h, wsData?.hyperliquid?.BTC?.change_24h)
  const ethChange = firstUsefulPercent(wsData?.binance?.eth?.change_24h, prices?.eth?.change_24h, wsData?.hyperliquid?.ETH?.change_24h)
  const xauChange = firstUsefulPercent(wsData?.xauusd?.change_24h, prices?.xau?.change_24h)
  const aggregatorAge = system.multi_exchange_aggregator?.last_update
    ? Math.max(0, Math.round(Date.now() / 1000 - system.multi_exchange_aggregator.last_update))
    : null
  const fundingPairs = Number(system.multi_exchange_aggregator?.funding_data_count || 0)
  const oiMarkets = Object.keys(system.multi_exchange_aggregator?.oi_data || {}).length
  const topMovers = Array.isArray(system.multi_exchange_aggregator?.top_gainers)
    ? system.multi_exchange_aggregator.top_gainers.length
    : 0
  const displayIntelCategory = (value?: string | null) => {
    const normalized = String(value || "tracked entity").toLowerCase().replace(/[_-]/g, " ").trim()
    if (normalized === "cex") return t("dashboard.cex", "Cex")
    if (normalized === "dex") return t("dashboard.dex", "Dex")
    if (normalized === "fund") return t("dashboard.fund", "Fund")
    if (normalized === "tracked entity" || normalized === "entity") return t("dashboard.trackedEntity", "Tracked Entity")
    return formatIntelCategory(value)
  }

  return (
    <div className="dashboard-layout anim-fade-up">
      <div className="dashboard-main has-sidebar">
        <section className="dashboard-command-center scan-overlay">
          <div className="dashboard-hero-copy">
            <div>
              <div className="dashboard-eyebrow">{t("dashboard.marketOverview", "Market Overview")}</div>
              <strong className="dashboard-command-title">Core Equity Command Center</strong>
            </div>
            <div className="dashboard-status-row">
              <div className={`dashboard-status-pill ${connected ? "live" : ""}`}>
                <strong>{connected ? t("dashboard.wsLive", "WS Live") : t("dashboard.wsSyncing", "WS Syncing")}</strong>
                <span>{connected ? t("dashboard.wsConnected", "Hyperliquid feed connected") : t("dashboard.wsWaiting", "Waiting for websocket heartbeat")}</span>
              </div>
              <div className="dashboard-status-pill mirror">
                <strong>{t("dashboard.scraplingMirror", "Scrapling Mirror")}</strong>
                <span>
                  {intelLoading
                    ? t("dashboard.refreshingWatchlist", "Refreshing explorer watchlist")
                    : `${intelWatchlist.length} ${t("dashboard.trackedEntitiesReady", "tracked entities ready")}`}
                </span>
              </div>
            </div>
          </div>
          <div className="dashboard-hero-actions">
            {!showOpportunities && (
              <button className="opp-panel-toggle premium" onClick={() => setShowOpportunities(true)}>
                <span>{t("dashboard.opportunities", "LIVE Opportunities")}</span>
                <span>{t("dashboard.showPanel", "Show Panel ->")}</span>
              </button>
            )}
            <button className="opp-panel-toggle premium secondary" onClick={() => openAlphaLabForAccount(alphaWallets[0] || null, "dashboard_hero_alpha_clicked")}>
              <span>Alpha Lab</span>
              <span>{alphaWallets.length ? "client ready ->" : "connect wallet"}</span>
            </button>
          </div>
        </section>

        <section className="dashboard-market-strip">
          <button className="entity-card asset-btc" onClick={() => onEntitySelect?.("hl_BTC")}>
            <div className="entity-card-row">
              <LogoAvatar name="Bitcoin" symbol="BTC" size={38} square />
              <div>
                <div className="entity-card-name">Bitcoin <span className="entity-card-verified">{t("common.live", "LIVE")}</span></div>
                <div className="entity-card-source">Hyperliquid / Binance</div>
              </div>
            </div>
            <div className="entity-card-balance">{formatUsdPrice(btcPrice, locale)}</div>
            {formatPercent(btcChange) && (
              <div className={`entity-card-change ${btcChange != null && btcChange >= 0 ? "positive" : "negative"}`}>
                {formatPercent(btcChange)}
              </div>
            )}
          </button>

          <button className="entity-card asset-eth" onClick={() => onEntitySelect?.("hl_ETH")}>
            <div className="entity-card-row">
              <LogoAvatar name="Ethereum" symbol="ETH" size={38} square />
              <div>
                <div className="entity-card-name">Ethereum <span className="entity-card-verified">{t("common.live", "LIVE")}</span></div>
                <div className="entity-card-source">Hyperliquid / RPC</div>
              </div>
            </div>
            <div className="entity-card-balance">{formatUsdPrice(ethPrice, locale)}</div>
            {formatPercent(ethChange) && (
              <div className={`entity-card-change ${ethChange != null && ethChange >= 0 ? "positive" : "negative"}`}>
                {formatPercent(ethChange)}
              </div>
            )}
          </button>

          <button className="entity-card asset-xau" onClick={() => onEntitySelect?.("xau_usd")}>
            <div className="entity-card-row">
              <LogoAvatar name="Gold" symbol="XAU" size={38} square />
              <div>
                <div className="entity-card-name">XAU/USD <span className="entity-card-verified">{t("common.live", "LIVE")}</span></div>
                <div className="entity-card-source">Gold macro feed</div>
              </div>
            </div>
            <div className="entity-card-balance">{formatUsdPrice(xauPrice, locale, 2)}</div>
            {formatPercent(xauChange) && (
              <div className={`entity-card-change ${xauChange != null && xauChange >= 0 ? "positive" : "negative"}`}>
                {formatPercent(xauChange)}
              </div>
            )}
          </button>

          <div className="entity-card asset-account">
            <div className="entity-card-row">
              <LogoAvatar name="PUPrime Account" symbol="MT5" size={38} square />
              <div>
                <div className="entity-card-name">PUPrime Account</div>
                <div className="entity-card-source">MT5 bridge</div>
              </div>
            </div>
            <div className="entity-card-balance">{account ? fmt(account.balance) : "-"}</div>
            <div className={`entity-card-change ${account ? "positive" : "negative"}`}>
              {account ? t("common.live", "LIVE") : t("common.offline", "OFFLINE")}
            </div>
          </div>
        </section>

        <section className="dashboard-kpi-ribbon">
          <div className="stat-box">
            <div className="stat-box-label">{t("dashboard.equity", "Equity")}</div>
            <div className="stat-box-value">{account ? fmt(account.equity) : "-"}</div>
            {account && account.profit !== 0 && (
              <div className={`stat-box-delta ${account.profit >= 0 ? "positive" : "negative"}`}>
                {account.profit >= 0 ? "+" : ""}{fmt(account.profit)}
              </div>
            )}
          </div>
          <div className="stat-box">
            <div className="stat-box-label">{t("dashboard.freeMargin", "Free Margin")}</div>
            <div className="stat-box-value">{account ? fmt(account.free_margin) : "-"}</div>
          </div>
          <div className="stat-box">
            <div className="stat-box-label">{t("dashboard.whaleImbalance", "Whale Imbalance")}</div>
            <div className="stat-box-value" style={{ color: stats.volume_imbalance > 0.15 ? "var(--success)" : stats.volume_imbalance < -0.15 ? "var(--error)" : "var(--text-primary)" }}>
              {stats.volume_imbalance != null ? `${stats.volume_imbalance > 0 ? "+" : ""}${stats.volume_imbalance.toFixed(3)}` : "-"}
            </div>
          </div>
          <div className="stat-box">
            <div className="stat-box-label">{t("dashboard.buyPressure", "Buy Pressure")}</div>
            <div className="stat-box-value" style={{ color: "var(--success)" }}>
              {stats.buy_ratio != null ? `${(stats.buy_ratio * 100).toFixed(1)}%` : "-"}
            </div>
            {stats.buy_ratio != null && (
              <div className="progress-bar" style={{ marginTop: 6 }}>
                <div className="progress-fill green" style={{ width: `${stats.buy_ratio * 100}%` }} />
              </div>
            )}
          </div>
        </section>

        <div className="account-link-panel">
          <div className="account-link-copy">
            <span>{t("dashboard.clientAccessLayer", "Client Access Layer")}</span>
            <strong>{t("dashboard.clientAccessTitle", "Connect, analyze, then automate without exposing the wallet.")}</strong>
            <p>
              {t("dashboard.clientAccessDesc", "Read-only by default. Alpha Lab enables a strategy only after RPC validation, risk scoring and wallet proof.")}
            </p>
          </div>

          <div className="account-alpha-status">
            <div>
              <span>{t("dashboard.access", "Access")}</span>
              <strong className={alphaWallets.length ? "positive" : "warning"}>
                {alphaWallets.length ? t("dashboard.unlocked", "Unlocked") : t("dashboard.locked", "Locked")}
              </strong>
              <em>{alphaWallets.length ? `${alphaWallets.length} ${t("dashboard.clientWallet", "client wallet")}` : t("dashboard.walletRequired", "wallet required")}</em>
            </div>
            <div>
              <span>{t("dashboard.watchlist", "Watchlist")}</span>
              <strong>{watchOnlyWallets.length}</strong>
              <em>{t("dashboard.manualTargets", "manual targets")}</em>
            </div>
            <div>
              <span>{t("dashboard.verified", "Verified")}</span>
              <strong>{verifiedWallets.length}</strong>
              <em>{t("dashboard.signedProofs", "signed proofs")}</em>
            </div>
            <button
              disabled={!alphaWallets.length}
              onClick={() => openAlphaLabForAccount(alphaWallets[0], "open_alpha_lab_clicked")}
            >
              {t("dashboard.launchAlphaLab", "Launch Alpha Lab")}
            </button>
          </div>

          <div className="account-link-actions">
            <div className="account-section-label">{t("dashboard.connectWallet", "Connect wallet")}</div>
            <button data-ready={walletProviders.metamask ? "true" : "false"} onClick={() => connectBrowserWallet("MetaMask")}>
              MetaMask <small>{walletProviders.metamask ? t("dashboard.detected", "detected") : t("dashboard.missing", "missing")}</small>
            </button>
            <button data-ready={walletProviders.rabby ? "true" : "false"} onClick={() => connectBrowserWallet("Rabby")}>
              Rabby <small>{walletProviders.rabby ? t("dashboard.detected", "detected") : t("dashboard.missing", "missing")}</small>
            </button>
            <button data-ready={walletProviders.phantom ? "true" : "false"} onClick={connectPhantom}>
              Phantom <small>{walletProviders.phantom ? t("dashboard.detected", "detected") : t("dashboard.missing", "missing")}</small>
            </button>
          </div>

          <div className="account-link-form">
            <div className="account-section-label">{t("dashboard.trackAddress", "Track address manually")}</div>
            <select value={walletNetwork} onChange={(event) => setWalletNetwork(event.target.value)}>
              <option value="ethereum">Ethereum</option>
              <option value="bsc">BNB Chain</option>
              <option value="arbitrum">Arbitrum</option>
              <option value="base">Base</option>
              <option value="solana">Solana</option>
              <option value="hyperliquid">Hyperliquid</option>
            </select>
            <input
              value={walletDraft}
              onChange={(event) => setWalletDraft(event.target.value)}
              placeholder="0x..., Solana address, or Hyperliquid wallet"
            />
            <button onClick={walletNetwork === "hyperliquid" ? trackHyperliquid : addManualWallet}>
              Ajouter
            </button>
          </div>

          {accountNotice && <div className="account-link-notice">{accountNotice}</div>}
          {evmProviderList.length > 0 && (
            <div className="account-provider-strip">
              {evmProviderList.map(({ info }, index) => (
                <span key={info.uuid || `${info.rdns}-${index}`}>
                  {info.name || "Wallet"}{info.rdns ? ` · ${info.rdns}` : ""}
                </span>
              ))}
            </div>
          )}
          <div className="account-security-note">
            {t("dashboard.readOnlyRule", "Read-only rule: Core Equity never asks for seed phrase or transaction approval from this dashboard.")}
          </div>

          {connectedAccounts.length > 0 && (
            <div className="account-link-list">
              {connectedAccounts.map((item) => (
                <div
                  key={item.id}
                  className="account-chip-card"
                  title={item.address}
                >
                  <span>{item.provider}</span>
                  <strong>{shortWallet(item.address)}</strong>
                  {item.type === "manual" && <small>watch-only target</small>}
                  {item.nativeBalance && item.nativeSymbol && (
                    <small>{item.nativeBalance} {item.nativeSymbol}</small>
                  )}
                  {item.verifiedAt && <small>verified signature</small>}
                  <div className="account-chip-actions">
                    {item.type !== "hyperliquid" && (
                      <button onClick={() => openAlphaLabForAccount(item, "open_alpha_lab_wallet_clicked")}>Alpha Lab</button>
                    )}
                    {item.type === "evm" && (
                      <button onClick={() => verifyEvmOwnership(item)}>
                        {item.verifiedAt ? "Reverify" : "Verify"}
                      </button>
                    )}
                    <button onClick={() => removeConnectedAccount(item.id)}>Disconnect</button>
                  </div>
                  <em>{item.network} · {item.status}</em>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="dashboard-surface-grid">
          <div className="card">
            <div className="card-accent" style={{ background: "var(--cyan)" }} />
            <div className="card-header" style={{ alignItems: "flex-start", gap: 12 }}>
              <div>
                <span className="card-title">{t("dashboard.explorerWatchlist", "Explorer Watchlist")}</span>
                <div className="dashboard-panel-subtitle">
                  {t("dashboard.explorerWatchlistSub", "Curated entities resolved through Arkham search and Scrapling-backed explorer coverage.")}
                </div>
              </div>
              <span className="badge badge-medium">{intelWatchlist.length || 0} {t("dashboard.loaded", "loaded")}</span>
            </div>
            <div className="card-body">
              {intelLoading && intelWatchlist.length === 0 ? (
                <div className="empty-state" style={{ padding: "20px 0" }}>
                  <div className="empty-state-title">{t("dashboard.loadingWatchlist", "Loading explorer watchlist")}</div>
                  <div className="empty-state-desc">{t("dashboard.queryingEntities", "Querying Arkham-style entities for the dashboard.")}</div>
                </div>
              ) : intelWatchlist.length > 0 ? (
                <div className="intel-watch-grid">
                  {intelWatchlist.map((item) => (
                    <button
                      key={item.id}
                      className="intel-watch-card"
                      data-source-tone={getIntelSourceTone(item.source)}
                      onClick={() => onEntitySelect?.(item.id)}
                    >
                      <div className="intel-watch-top">
                        <div className="intel-watch-brand">
                          <LogoAvatar name={item.name} symbol={item.slug} size={28} />
                          <div style={{ minWidth: 0 }}>
                            <div className="intel-watch-name">{item.name}</div>
                            <div className="intel-watch-meta">{displayIntelCategory(item.category || item.type)}</div>
                          </div>
                        </div>
                        <span className="badge badge-medium">{formatIntelSource(item.source)}</span>
                      </div>
                      <div className="intel-watch-chip-row">
                        {item.source === "pending" ? (
                          <span className="intel-watch-chip muted">{t("dashboard.awaitingMirror", "Awaiting mirror")}</span>
                        ) : (
                          <span className="intel-watch-chip">{formatIntelSource(item.source)}</span>
                        )}
                        {item.wallet_count != null && item.wallet_count > 0 && (
                          <span className="intel-watch-chip">{item.wallet_count.toLocaleString(locale)} {t("dashboard.wallets", "wallets")}</span>
                        )}
                        {!!item.chains?.length && (
                          <span className="intel-watch-chip muted">{item.chains.length} {t("dashboard.networks", "networks")}</span>
                        )}
                        {(item.chains || []).slice(0, 3).map((chain) => (
                          <span key={`${item.id}-${chain}`} className="intel-watch-chip muted">
                            {chain}
                          </span>
                        ))}
                      </div>
                      <div className="intel-watch-footer">
                        <span className="intel-watch-slug">{item.slug}</span>
                        <span className="intel-watch-opening">{t("dashboard.openExplorer", "Open explorer ->")}</span>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="empty-state" style={{ padding: "20px 0" }}>
                  <div className="empty-state-title">{t("dashboard.noExplorerEntities", "No explorer entities loaded")}</div>
                  <div className="empty-state-desc">{t("dashboard.noExplorerEntitiesSub", "The dashboard will populate this watchlist once Arkham search responds.")}</div>
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-accent" style={{ background: "var(--green)" }} />
            <div className="card-header" style={{ alignItems: "flex-start", gap: 12 }}>
              <div>
                <span className="card-title">{t("dashboard.opportunityRadar", "Opportunity Radar")}</span>
                <div className="dashboard-panel-subtitle">
                  {t("dashboard.opportunityRadarSub", "A compact tape of current signal opportunities without opening the side panel.")}
                </div>
              </div>
            </div>
            <div className="card-body">
              <OpportunityFeed />
            </div>
          </div>
        </div>

        {/* Positions + System */}
        <div className="grid-2">
          <div className="data-table-wrapper">
            <div className="data-table-toolbar">
              <span className="data-table-title">{t("dashboard.activePositions", "Active Positions")} ({positions.length})</span>
              <span className="badge badge-medium">MT5</span>
            </div>
            {positions.length === 0 ? (
              <div className="trading-empty-panel">
                <span>{t("dashboard.executionOff", "Execution standby")}</span>
                <strong>{t("dashboard.noPositions", "No positions")}</strong>
                <em>{t("dashboard.noMt5Positions", "No active MT5 positions detected")}</em>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("dashboard.symbol", "Symbol")}</th><th>{t("dashboard.type", "Type")}</th><th>{t("dashboard.volume", "Volume")}</th><th>{t("dashboard.open", "Open")}</th><th>{t("dashboard.current", "Current")}</th><th>PnL</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map(p => (
                    <tr key={p.ticket}>
                      <td style={{ fontWeight: 600 }}>{p.symbol}</td>
                      <td><span className={`badge ${p.type === "BUY" ? "badge-bullish" : "badge-bearish"}`}>{p.type}</span></td>
                      <td className="data-table-mono">{p.volume}</td>
                      <td className="data-table-mono">{p.open_price}</td>
                      <td className="data-table-mono">{p.current_price}</td>
                      <td className="data-table-mono" style={{ color: p.profit >= 0 ? "var(--success)" : "var(--error)", fontWeight: 700 }}>
                        {p.profit >= 0 ? "+" : ""}{p.profit.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="dashboard-ops-stack">
            <div className="card dashboard-health-card">
              <div className="card-accent" />
              <div className="card-header"><span className="card-title">{t("dashboard.systemStatus", "System Status")}</span></div>
              <div className="card-body-compact">
                <div className="health-grid">
                  <div className="health-row">
                    <span>Hyperliquid WS</span>
                    <span className={`badge ${system.hyperliquid_collector?.connected ? "badge-bullish" : "badge-bearish"}`}>
                      {system.hyperliquid_collector?.connected ? t("common.connected", "CONNECTED") : t("common.offline", "OFFLINE")}
                    </span>
                  </div>
                  <div className="health-row">
                    <span>{t("dashboard.mt5Bridge", "MT5 Bridge")}</span>
                    <span className={`badge ${system.mt5_bridge?.status === "ok" ? "badge-bullish" : "badge-bearish"}`}>
                      {system.mt5_bridge?.status === "checking" ? t("common.checking", "CHECKING") : system.mt5_bridge?.status?.toUpperCase() || t("common.checking", "CHECKING")}
                    </span>
                  </div>
                  <div className="health-row">
                    <span>{t("dashboard.aggregator", "Aggregator")}</span>
                    <span className="health-age">
                      {aggregatorAge != null ? `${aggregatorAge}${t("common.secondsAgo", "s ago")}` : t("common.inactive", "Inactive")}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="dashboard-mini-grid">
              <div className="card dashboard-data-card">
                <div className="card-accent" style={{ background: "var(--green)" }} />
                <div className="card-header"><span className="card-title">{t("dashboard.dataIntegrity", "Data Integrity")}</span></div>
                <div className="card-body-compact">
                  <div className="data-integrity-grid">
                    <div>
                      <span>{t("dashboard.fundingPairs", "Funding pairs")}</span>
                      <strong>{fundingPairs.toLocaleString(locale)}</strong>
                    </div>
                    <div>
                      <span>{t("dashboard.oiMarkets", "OI markets")}</span>
                      <strong>{oiMarkets.toLocaleString(locale)}</strong>
                    </div>
                    <div>
                      <span>{t("dashboard.topMovers", "Top movers")}</span>
                      <strong>{topMovers.toLocaleString(locale)}</strong>
                    </div>
                  </div>
                </div>
              </div>

            <div className="card dashboard-data-card">
              <div className="card-accent" style={{ background: "var(--cyan)" }} />
              <div className="card-header"><span className="card-title">{t("dashboard.livePrices", "Live Prices")}</span></div>
              <div className="card-body-compact">
                <div className="mini-price-list">
                  <div>
                    <span>BTC</span>
                    <strong className={btcChange != null && btcChange < 0 ? "negative" : "positive"}>
                      {formatUsdPrice(btcPrice, locale)}
                    </strong>
                  </div>
                  <div>
                    <span>ETH</span>
                    <strong className={ethChange != null && ethChange < 0 ? "negative" : "positive"}>
                      {formatUsdPrice(ethPrice, locale)}
                    </strong>
                  </div>
                  <div>
                    <span>XAU</span>
                    <strong className={xauChange != null && xauChange < 0 ? "negative" : "positive"}>
                      {formatUsdPrice(xauPrice, locale, 2)}
                    </strong>
                  </div>
                </div>
              </div>
            </div>
              </div>
          </div>
        </div>
      </div>

      <OpportunitiesSidebar isOpen={showOpportunities} onClose={() => setShowOpportunities(false)} />
    </div>
  )
}
