import { useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import { get } from "../services/api"
import { getExplorerAddressUrl, getExplorerTokenUrl, resolveExplorerTokenChain } from "../services/explorerLinks"

interface ChainData {
  chain: string
  balance: number
  tx_count: number
  unit: string
  net_worth_usd?: number | null
  token_count?: number
  tokens_with_value?: number
  top_holdings?: TokenData[]
}

interface TokenData {
  symbol: string
  balance: number
  chain?: string
  explorer_chain?: string
  token_address?: string
  price_usd?: number | null
  value_usd?: number | null
  confidence?: string
  verified?: boolean
  rpc_symbol?: string | null
  rpc_decimals?: number | null
  rpc_total_supply?: number | null
  indexer_symbol?: string | null
  indexer_decimals?: number | null
  balance_source?: string
  metadata_source?: string
  market_source?: string
  contract_verified_on_chain?: boolean
  source_trace?: Array<{
    kind: string
    source: string
    chain: string
    ok: boolean
    detail?: string
  }>
}

interface ActivityData {
  first_seen?: string | null
  last_seen?: string | null
  tx_count?: number
  active_days?: number
  tx_per_day?: number
}

interface FlowData {
  inflow_eth?: number
  outflow_eth?: number
  net_flow_eth?: number
}

interface ConcentrationData {
  top_token_symbol?: string
  top_token_pct?: number
  concentration_score?: number
  diversity_score?: number
}

interface RiskData {
  score?: number
  level?: string
  reasons?: string[]
}

interface WalletData {
  ok: boolean
  wallet?: string
  chain?: string | null
  primary_chain?: string | null
  net_worth_usd?: number | null
  tx_count?: number
  chains?: ChainData[]
  tokens?: TokenData[]
  display_tokens?: TokenData[]
  top_holdings?: TokenData[]
  wallet_label?: string
  label_reasons?: string[]
  token_count?: number
  tokens_with_value?: number
  activity?: ActivityData
  flow?: FlowData
  concentration?: ConcentrationData
  risk_score?: RiskData
  data_quality?: {
    trusted_tokens?: number
    trusted_display_tokens?: number
    excluded_marks?: number
    notes?: string[]
  }
  error?: string
}

interface AlphaWalletProbe {
  ok: boolean
  wallet: string
  status: string
  status_label: string
  confidence: string
  reasons: string[]
  provider_health?: {
    ok: number
    total: number
    unstable?: string[]
  }
  risk_summary?: {
    blocked_rows: number
    untrusted_rows: number
    suspicious_assets?: string[]
  }
  asset_focus?: Array<{
    asset: string
    chain: string
    events: number
    amount_usd: number
  }>
  intel?: {
    source?: string
    timeframe?: string
    summary?: {
      events?: number
      chains?: string[]
      observed_flow_usd?: number
      copy_ready?: boolean
    }
    events?: Array<{
      timestamp?: string
      chain?: string
      asset?: string
      amount_usd?: number
      source?: string
      sources?: string[]
      confidence?: number
    }>
  }
}

const LABEL_INFO: Record<string, { name: string; color: string }> = {
  whale: { name: "Whale", color: "#fbbf24" },
  smart_money: { name: "Smart Money", color: "#34d399" },
  active_trader: { name: "Active Trader", color: "#60a5fa" },
  high_frequency: { name: "High Frequency", color: "#a78bfa" },
  new_wallet: { name: "New Wallet", color: "#94a3b8" },
  reviewed_wallet: { name: "Reviewed Wallet", color: "#22d3ee" },
  regular: { name: "Regular", color: "#22d3ee" },
}

const RISK_LEVELS: Record<string, string> = {
  low: "good",
  medium: "watch",
  high: "danger",
}

function formatMoney(value?: number | null): string {
  const val = Number(value || 0)
  if (!Number.isFinite(val) || val === 0) return "$0"
  if (Math.abs(val) > 1_000_000_000_000) return "Untrusted"
  if (Math.abs(val) >= 1_000_000_000) return "$" + (val / 1_000_000_000).toFixed(2) + "B"
  if (Math.abs(val) >= 1_000_000) return "$" + (val / 1_000_000).toFixed(2) + "M"
  if (Math.abs(val) >= 1_000) return "$" + (val / 1_000).toFixed(2) + "K"
  return "$" + val.toFixed(2)
}

function formatTokenAmount(value?: number | null): string {
  const val = Number(value || 0)
  if (!Number.isFinite(val) || val === 0) return "0"
  if (Math.abs(val) >= 1_000_000) return (val / 1_000_000).toFixed(2) + "M"
  if (Math.abs(val) >= 1_000) return (val / 1_000).toFixed(2) + "K"
  if (Math.abs(val) < 0.001) return val.toExponential(2)
  return val.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function shortAddress(value?: string | null): string {
  if (!value) return "-"
  if (value.length <= 14) return value
  return `${value.slice(0, 8)}...${value.slice(-6)}`
}

function chainLabel(chain?: string | null): string {
  return (chain || "ethereum").replace(/_/g, " ").toUpperCase()
}

function isSaneUsdValue(value?: number | null): boolean {
  const val = Number(value || 0)
  return Number.isFinite(val) && val >= 0 && val < 1_000_000_000_000
}

function isSaneToken(token: TokenData): boolean {
  const price = Number(token.price_usd || 0)
  const value = Number(token.value_usd || 0)
  return (!price || price <= 1_000_000) && isSaneUsdValue(value)
}

type PillTone = "good" | "watch" | "danger" | "info" | "muted"

function StatusPill({ tone, children }: { tone: PillTone; children: ReactNode }) {
  return <span className={`wallet-pill ${tone}`}>{children}</span>
}

function MetricCard({ label, value, detail, tone = "default" }: { label: string; value: string; detail?: string; tone?: string }) {
  return (
    <div className={`wallet-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <em>{detail}</em>}
    </div>
  )
}

function tokenExplorer(token: TokenData, fallbackChain: string) {
  return getExplorerTokenUrl(token.token_address, token.explorer_chain || token.chain || fallbackChain)
}

function tokenChain(token: TokenData, fallbackChain: string) {
  return resolveExplorerTokenChain(token.token_address, token.explorer_chain || token.chain || fallbackChain)
}

function sourceSummary(token: TokenData) {
  const trace = token.source_trace || []
  const ok = trace.filter((item) => item.ok).length
  const total = trace.length
  const sources = Array.from(new Set(trace.map((item) => item.source).filter(Boolean))).slice(0, 3)
  const mismatches = trace.filter((item) => item.kind === "source_mismatch").length
  if (!total) return "source trail pending"
  return `${ok}/${total} checks: ${sources.join(" + ")}${mismatches ? ` · ${mismatches} mismatch` : ""}`
}

function rpcMetaSummary(token: TokenData) {
  const parts = []
  if (token.rpc_symbol) parts.push(`symbol ${token.rpc_symbol}`)
  if (token.rpc_decimals != null) parts.push(`${token.rpc_decimals} decimals`)
  if (token.rpc_total_supply) parts.push(`supply ${formatTokenAmount(token.rpc_total_supply)}`)
  return parts.length ? `RPC metadata: ${parts.join(" · ")}` : "RPC metadata pending"
}

function probeToWalletData(wallet: string, probe: AlphaWalletProbe): WalletData {
  const chains = probe.intel?.summary?.chains?.length
    ? probe.intel.summary.chains
    : Array.from(new Set((probe.asset_focus || []).map((item) => item.chain || "ethereum")))
  const events = probe.intel?.events || []
  const seenDates = events.map((event) => event.timestamp).filter(Boolean).sort()
  const firstSeen = seenDates[0] || null
  const lastSeen = seenDates[seenDates.length - 1] || null
  const observedUsd = Number(probe.intel?.summary?.observed_flow_usd || 0)
  const topHoldings: TokenData[] = (probe.asset_focus || []).map((item) => ({
    symbol: item.asset,
    balance: item.events,
    chain: item.chain,
    explorer_chain: item.chain,
    value_usd: item.amount_usd,
    confidence: probe.confidence || "medium",
    verified: false,
    balance_source: "alpha_probe",
    metadata_source: "cielo_zerion_rpc",
    market_source: "observed_flow",
    contract_verified_on_chain: false,
    source_trace: [{
      kind: "alpha_probe",
      source: probe.intel?.source || "cielo/zerion/rpc",
      chain: item.chain,
      ok: true,
      detail: `${item.events} observed events`,
    }],
  }))
  const top = topHoldings.reduce<TokenData | undefined>(
    (best, item) => Number(item.value_usd || 0) > Number(best?.value_usd || 0) ? item : best,
    topHoldings[0],
  )
  const riskLevel = probe.status === "blocked" ? "high" : probe.status === "candidate" ? "low" : "medium"

  return {
    ok: true,
    wallet,
    primary_chain: chains[0] || "ethereum",
    net_worth_usd: observedUsd,
    tx_count: probe.intel?.summary?.events || events.length || 0,
    chains: chains.map((chain) => {
      const chainTokens = topHoldings.filter((token) => (token.chain || "ethereum") === chain)
      return {
        chain,
        balance: 0,
        tx_count: events.filter((event) => (event.chain || chain) === chain).length,
        unit: chain === "bsc" ? "BNB" : chain === "polygon" ? "MATIC" : "ETH",
        net_worth_usd: chainTokens.reduce((sum, token) => sum + Number(token.value_usd || 0), 0),
        token_count: chainTokens.length,
        tokens_with_value: chainTokens.filter((token) => Number(token.value_usd || 0) > 0).length,
        top_holdings: chainTokens,
      }
    }),
    display_tokens: topHoldings,
    top_holdings: topHoldings,
    wallet_label: probe.status === "candidate" ? "smart_money" : "reviewed_wallet",
    label_reasons: [
      `Alpha probe fallback: ${probe.status_label}`,
      ...(probe.reasons || []).slice(0, 4),
      ...(probe.provider_health?.unstable || []).map((item) => `provider issue: ${item}`),
    ],
    token_count: topHoldings.length,
    tokens_with_value: topHoldings.filter((token) => Number(token.value_usd || 0) > 0).length,
    activity: {
      first_seen: firstSeen,
      last_seen: lastSeen,
      tx_count: probe.intel?.summary?.events || events.length || 0,
      active_days: 0,
    },
    flow: {
      inflow_eth: 0,
      outflow_eth: 0,
      net_flow_eth: 0,
    },
    concentration: {
      top_token_symbol: top?.symbol,
      top_token_pct: observedUsd ? Math.min((Number(top?.value_usd || 0) / observedUsd) * 100, 100) : 0,
      diversity_score: topHoldings.length,
    },
    risk_score: {
      score: riskLevel === "high" ? 80 : riskLevel === "low" ? 20 : 55,
      level: riskLevel,
      reasons: [
        `${probe.risk_summary?.untrusted_rows || 0} suspect rows`,
        `${probe.risk_summary?.blocked_rows || 0} blocked rows`,
        ...(probe.risk_summary?.suspicious_assets || []).map((asset) => `suspicious asset: ${asset}`),
      ],
    },
    data_quality: {
      trusted_tokens: 0,
      trusted_display_tokens: 0,
      excluded_marks: probe.risk_summary?.untrusted_rows || 0,
      notes: ["On-chain portfolio route was unavailable or slow; showing Alpha evidence fallback."],
    },
  }
}

export default function WalletAnalyzer() {
  const [address, setAddress] = useState("")
  const [loading, setLoading] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [data, setData] = useState<WalletData | null>(null)
  const [error, setError] = useState("")

  useEffect(() => {
    if (!loading) {
      setElapsed(0)
      return
    }

    const startedAt = Date.now()
    const timer = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 250)

    return () => window.clearInterval(timer)
  }, [loading])

  async function analyze() {
    const wallet = address.trim()
    if (!wallet) return

    setLoading(true)
    setError("")
    setData(null)

    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 18_000)

    try {
      const res = await get<WalletData>(`/onchain/wallet/${wallet}`, { signal: controller.signal })
      if (res.ok) {
        setData(res)
      } else {
        setError(res.error || "Analysis failed")
      }
    } catch (e: any) {
      const message = e?.data?.message || e?.message || ""
      try {
        const probe = await get<AlphaWalletProbe>(`/alpha/wallet/probe/${encodeURIComponent(wallet)}?limit=20&timeframe=30d`)
        if (probe.ok) {
          setData(probeToWalletData(wallet, probe))
          setError("")
          return
        }
      } catch {
        // Fallback is best-effort; keep the original error below.
      }
      setError(message.includes("Abort") ? "On-chain route timed out after 18s and Alpha fallback failed." : message || "Network error")
    } finally {
      window.clearTimeout(timeout)
      setLoading(false)
    }
  }

  const primaryChain = data?.primary_chain || data?.chain || data?.chains?.[0]?.chain || "ethereum"
  const explorerUrl = getExplorerAddressUrl(data?.wallet, primaryChain)
  const rawTopHoldings = data?.top_holdings || []
  const rawDisplayTokens = data?.display_tokens || []
  const topHoldings = useMemo(() => rawTopHoldings.filter(isSaneToken), [rawTopHoldings])
  const displayTokens = useMemo(() => rawDisplayTokens.filter(isSaneToken), [rawDisplayTokens])
  const unsafeMarks = data?.data_quality?.excluded_marks ?? (rawDisplayTokens.length - displayTokens.length + rawTopHoldings.length - topHoldings.length)
  const verifiedTokens = displayTokens.filter((token) => token.verified).length
  const watchlistTokens = displayTokens.filter((token) => !token.verified || token.confidence !== "high").length
  const verifiedValue = displayTokens
    .filter((token) => token.verified)
    .reduce((sum, token) => sum + Number(token.value_usd || 0), 0)
  const saneChainValue = (data?.chains || [])
    .filter((chain) => isSaneUsdValue(chain.net_worth_usd))
    .reduce((sum, chain) => sum + Number(chain.net_worth_usd || 0), 0)
  const portfolioValue = isSaneUsdValue(data?.net_worth_usd)
    ? Number(data?.net_worth_usd || 0)
    : Math.max(verifiedValue, saneChainValue)
  const effectiveLabelKey = data?.wallet_label === "whale" && portfolioValue < 1_000_000 ? "reviewed_wallet" : data?.wallet_label
  const labelInfo = effectiveLabelKey ? LABEL_INFO[effectiveLabelKey] || LABEL_INFO.regular : LABEL_INFO.regular
  const trustedTopValue = Math.max(...topHoldings.map((token) => Number(token.value_usd || 0)), 0)
  const trustedTotalValue = topHoldings.reduce((sum, token) => sum + Number(token.value_usd || 0), 0)
  const trustedTopToken = topHoldings.find((token) => Number(token.value_usd || 0) === trustedTopValue)
  const concentrationSymbol = unsafeMarks && trustedTopToken ? trustedTopToken.symbol : data?.concentration?.top_token_symbol
  const concentrationPct = unsafeMarks && trustedTotalValue
    ? Math.min((trustedTopValue / trustedTotalValue) * 100, 100)
    : Math.min(data?.concentration?.top_token_pct || 0, 100)
  const netFlow = data?.flow?.net_flow_eth || 0
  const riskTone = RISK_LEVELS[data?.risk_score?.level || "medium"] || "watch"

  return (
    <div className="wallet-analyzer">
      <div className="wallet-search-shell">
        <div className="wallet-search-copy">
          <span>Wallet intelligence</span>
          <strong>Analyse a wallet without trusting fake marks.</strong>
        </div>
        <div className="wallet-search-bar">
          <input
            type="text"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && analyze()}
            placeholder="0x wallet, ENS, or tracked address..."
          />
          <button onClick={analyze} disabled={loading || !address.trim()}>
            {loading ? "Analyzing" : "Analyze"}
          </button>
        </div>
      </div>

      {loading && (
        <div className="wallet-loading-card" aria-live="polite">
          <div className="wallet-loading-orb">
            <i />
          </div>
          <div className="wallet-loading-copy">
            <span>Live wallet scan</span>
            <strong>Resolving balances, token marks and source confidence...</strong>
            <em>{elapsed < 8 ? "Querying RPC and cached providers" : elapsed < 20 ? "Validating suspicious token prices" : "Still working, this route is slow today"} / {elapsed}s</em>
          </div>
          <div className="wallet-loading-bars">
            <i />
            <i />
            <i />
          </div>
        </div>
      )}

      {error && <div className="wallet-error">{error}</div>}

      {!data && !loading && !error && (
        <div className="wallet-empty-state">
          <span>Paste a wallet to open the premium dossier.</span>
          <strong>Portfolio, source links, risk, concentration, and token confidence in one view.</strong>
        </div>
      )}

      {data && (
        <div className="wallet-dossier">
          <section className="wallet-hero-card">
            <div className="wallet-identity">
              <div className="wallet-avatar">{(data.wallet_label || "W").slice(0, 1).toUpperCase()}</div>
              <div>
                <div className="wallet-kicker">Observed wallet</div>
                <h3>{shortAddress(data.wallet)}</h3>
                <p>{data.wallet}</p>
                <div className="wallet-actions">
                  <StatusPill tone={labelInfo.name === "Whale" ? "watch" : "info"}>{labelInfo.name}</StatusPill>
                  {explorerUrl && (
                    <a href={explorerUrl} target="_blank" rel="noreferrer" className="wallet-link">
                      Open on {chainLabel(primaryChain)}
                    </a>
                  )}
                </div>
              </div>
            </div>

            <div className="wallet-networth">
              <span>Trusted net worth</span>
              <strong>{formatMoney(portfolioValue)}</strong>
              <em>Verified slice {formatMoney(verifiedValue)}</em>
            </div>
          </section>

          <section className="wallet-metric-grid">
            <MetricCard label="Data integrity" value={`${verifiedTokens}/${displayTokens.length}`} detail="verified tokens" tone={watchlistTokens ? "watch" : "good"} />
            <MetricCard label="Excluded marks" value={String(Math.max(unsafeMarks, 0))} detail="impossible prices hidden" tone={unsafeMarks ? "danger" : "good"} />
            <MetricCard label="Transactions" value={String(data.tx_count || 0)} detail={`${data.activity?.active_days || 0} active days`} />
            <MetricCard label="Chains" value={String(data.chains?.length || 0)} detail={data.chains?.map((chain) => chainLabel(chain.chain)).join(" / ") || "none"} />
            <MetricCard label="Risk score" value={data.risk_score?.score != null ? String(data.risk_score.score) : "-"} detail={data.risk_score?.level || "pending"} tone={riskTone} />
          </section>

          <section className="wallet-main-grid">
            <div className="wallet-panel wallet-portfolio-panel">
              <div className="wallet-panel-header">
                <div>
                  <span>Portfolio surface</span>
                  <strong>Balances by chain</strong>
                </div>
                <StatusPill tone="muted">{data.tokens_with_value || 0}/{data.token_count || 0} priced</StatusPill>
              </div>

              <div className="wallet-chain-list">
                {(data.chains || []).map((chain) => {
                  const chainExplorerUrl = getExplorerAddressUrl(data.wallet, chain.chain)
                  return (
                    <a
                      className="wallet-chain-row"
                      key={chain.chain}
                      href={chainExplorerUrl || undefined}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <div>
                        <span>{chainLabel(chain.chain)}</span>
                        <strong>{formatTokenAmount(chain.balance)} {chain.unit}</strong>
                      </div>
                      <div>
                        <span>{chain.tx_count || 0} tx</span>
                        <strong>{formatMoney(chain.net_worth_usd)}</strong>
                      </div>
                    </a>
                  )
                })}
              </div>
            </div>

            <div className="wallet-panel">
              <div className="wallet-panel-header">
                <div>
                  <span>Flow and behavior</span>
                  <strong>Activity profile</strong>
                </div>
                <StatusPill tone={netFlow >= 0 ? "good" : "danger"}>{netFlow >= 0 ? "net inflow" : "net outflow"}</StatusPill>
              </div>

              <div className="wallet-behavior-grid">
                <MetricCard label="First seen" value={data.activity?.first_seen || "-"} />
                <MetricCard label="Last seen" value={data.activity?.last_seen || "-"} />
                <MetricCard label="Inflow ETH" value={`+${(data.flow?.inflow_eth || 0).toFixed(4)}`} tone="good" />
                <MetricCard label="Outflow ETH" value={`-${(data.flow?.outflow_eth || 0).toFixed(4)}`} tone="danger" />
              </div>

              {data.concentration && (
                <div className="wallet-concentration">
                  <div>
                    <span>Concentration</span>
                    <strong>{concentrationSymbol || "-"} {concentrationPct.toFixed(2)}%</strong>
                  </div>
                  <div className="wallet-progress">
                    <i style={{ width: `${concentrationPct}%` }} />
                  </div>
                  <em>{unsafeMarks ? "Recomputed from trusted marks" : `Diversity score: ${data.concentration.diversity_score || 0} tokens`}</em>
                </div>
              )}
            </div>
          </section>

          {data.risk_score && (
            <section className={`wallet-risk-panel ${riskTone}`}>
              <div>
                <span>Risk read</span>
                <strong>{data.risk_score.level || "pending"} / {data.risk_score.score ?? "-"}</strong>
              </div>
              <div className="wallet-risk-reasons">
                {(data.risk_score.reasons || ["No explicit risk flags returned"]).map((reason) => (
                  <StatusPill key={reason} tone={riskTone as PillTone}>
                    {reason.replace(/_/g, " ")}
                  </StatusPill>
                ))}
              </div>
            </section>
          )}

          {topHoldings.length > 0 && (
            <section className="wallet-panel">
              <div className="wallet-panel-header">
                <div>
                  <span>Top holdings</span>
                  <strong>Zerion-style portfolio stack</strong>
                </div>
                <StatusPill tone="info">{topHoldings.length} assets</StatusPill>
              </div>

              <div className="wallet-token-table">
                {topHoldings.map((token, index) => {
                  const href = tokenExplorer(token, primaryChain)
                  const displayChain = tokenChain(token, primaryChain)
                  return (
                    <a
                      className="wallet-token-row"
                      href={href || undefined}
                      target="_blank"
                      rel="noreferrer"
                      title={href || undefined}
                      key={`${token.symbol}:${index}`}
                    >
                      <div className="wallet-token-left">
                        <span className="wallet-rank">{index + 1}</span>
                        <div>
                          <strong>{token.symbol}</strong>
                          <em>{chainLabel(displayChain)} / {formatTokenAmount(token.balance)}</em>
                          <small className="wallet-source-line">
                            {token.contract_verified_on_chain ? "RPC contract verified" : "RPC contract pending"} · {sourceSummary(token)}
                          </small>
                          <small className="wallet-source-line strong">
                            {rpcMetaSummary(token)}
                          </small>
                        </div>
                      </div>
                      <div className="wallet-token-right">
                        <strong>{formatMoney(token.value_usd)}</strong>
                        <StatusPill tone={token.verified ? "good" : token.confidence === "medium" ? "watch" : "muted"}>
                          {token.verified ? "verified" : token.confidence || "watch"}
                        </StatusPill>
                      </div>
                    </a>
                  )
                })}
              </div>
            </section>
          )}

          {displayTokens.length > 0 && (
            <section className="wallet-panel compact">
              <div className="wallet-panel-header">
                <div>
                  <span>Token confidence</span>
                  <strong>Marks kept after sanity checks</strong>
                </div>
              </div>
              <div className="wallet-confidence-strip">
                {displayTokens.slice(0, 18).map((token, index) => {
                  const href = tokenExplorer(token, primaryChain)
                  return (
                    <a href={href || undefined} target="_blank" rel="noreferrer" title={`${href || ""}\n${sourceSummary(token)}\n${rpcMetaSummary(token)}`} key={`${token.symbol}:${index}`}>
                      <strong>{token.symbol}</strong>
                      <span>{formatMoney(token.value_usd)}</span>
                      <em>{token.contract_verified_on_chain ? "rpc ok" : "rpc ?"}</em>
                    </a>
                  )
                })}
              </div>
            </section>
          )}

          {data.label_reasons && data.label_reasons.length > 0 && (
            <section className="wallet-footnotes">
              {data.label_reasons.map((reason) => (
                <span key={reason}>{reason}</span>
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  )
}
