import { useState, useEffect, useCallback } from "react"
import { useMarket } from "../../contexts/WSContext"
import { apiUrl } from "../../services/api"

// =========================================================
// ENTITY PAGE — Arkham Intelligence-style full-page view
// Accessible only from TopBar search results
// =========================================================

const API = apiUrl("")

const TYPE_COLORS: Record<string, string> = {
  token: "var(--blue-bright)",
  entity: "var(--purple)",
  funding: "var(--amber)",
  gainer: "var(--green)",
  arkham_entity: "var(--cyan)",
  arkham_label: "var(--cyan)",
}

const TYPE_LABELS: Record<string, string> = {
  token: "TOKEN",
  entity: "ENTITY",
  funding: "FUNDING",
  gainer: "TOP GAINER",
  arkham_entity: "ARKHAM ENTITY",
  arkham_label: "ARKHAM LABEL",
}

const TAB_COLORS: Record<string, string> = {
  overview: "var(--blue-bright)",
  holdings: "var(--purple)",
  transactions: "var(--green)",
  related: "var(--cyan)",
}

interface EntityData {
  id: string; type: string; name: string; label: string
  price?: number | string; balance?: string; source?: string
  address?: string; snapshot?: Record<string, any>
  funding_data?: Record<string, any>; arkham_data?: Record<string, any>
}

interface ArkhamEntityData {
  entity?: Record<string, any>; wallets_count?: number
  wallets?: any[]; flow?: Record<string, any>
}

interface Transaction {
  hash: string; from: string; to: string
  amount: string; token: string; time: string; type?: string
}

interface Holder {
  address: string; label?: string; balance: string; pct: number
}

interface EntityPageProps {
  entityId: string
  onBack: () => void
}

// ── Helpers ──

function truncAddr(addr: string, head = 6, tail = 4): string {
  if (!addr || addr.length <= head + tail + 3) return addr
  return `${addr.slice(0, head)}...${addr.slice(-tail)}`
}

function fmtUsd(v: number | string | undefined): string {
  if (v == null) return "—"
  const n = typeof v === "string" ? parseFloat(v) : v
  if (isNaN(n)) return String(v)
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(2)}K`
  return `$${n.toFixed(2)}`
}

function timeAgo(ts: string): string {
  if (!ts) return "—"
  const d = new Date(ts).getTime()
  if (isNaN(d)) return ts
  const s = Math.floor((Date.now() - d) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

// ── Skeleton ──

function Skeleton({ w = "100%", h = 14, r = 4 }: { w?: string; h?: number; r?: number }) {
  return (
    <div style={{
      width: w, height: h, borderRadius: r,
      background: "linear-gradient(90deg, var(--bg-card-2) 25%, var(--bg-hover) 50%, var(--bg-card-2) 75%)",
      backgroundSize: "200% 100%",
      animation: "shimmer 1.5s ease-in-out infinite",
    }} />
  )
}

function SkeletonCard() {
  return (
    <div style={{ padding: 16, background: "var(--bg-card)", borderRadius: "var(--r-md)", border: "1px solid var(--border)" }}>
      <Skeleton w="40%" h={10} />
      <div style={{ height: 8 }} />
      <Skeleton w="70%" h={18} />
    </div>
  )
}

// ── Copy Button ──

function Copyable({ text, style }: { text: string; style?: React.CSSProperties }) {
  const [copied, setCopied] = useState(false)
  const copy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }, [text])
  return (
    <span
      onClick={copy}
      style={{
        fontFamily: "var(--font-mono)", fontSize: 11, color: copied ? "var(--green)" : "var(--text-2)",
        cursor: "pointer", transition: "color 0.2s",
        ...style,
      }}
      title={text}
    >
      {copied ? "Copied" : truncAddr(text)}
    </span>
  )
}

// ── Main Component ──

export default function EntityPage({ entityId, onBack }: EntityPageProps) {
  const [entity, setEntity] = useState<EntityData | null>(null)
  const [arkhamData, setArkhamData] = useState<ArkhamEntityData | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [holders, setHolders] = useState<Holder[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<"overview" | "holdings" | "transactions" | "related">("overview")

  // Fetch all data
  useEffect(() => {
    let cancelled = false
    setLoading(true)

    async function load() {
      try {
        const baseRes = await fetch(`${API}/entity/${encodeURIComponent(entityId)}`)
        const base = baseRes.ok ? await baseRes.json() : null
        if (!base || base.error || cancelled) { setLoading(false); return }
        setEntity(base)

        const isArkham = base.type?.startsWith("arkham_") || base.address
        if (isArkham) {
          const arkhamSlug = base.id.replace(/^(arkham_|hl_)/, "")
          const [aRes, tRes, hRes] = await Promise.allSettled([
            fetch(`${API}/arkham/entity/${encodeURIComponent(arkhamSlug)}`).then(r => r.ok ? r.json() : null),
            base.address
              ? fetch(`${API}/arkham/transactions/${encodeURIComponent(base.address)}`).then(r => r.ok ? r.json() : null)
              : Promise.resolve(null),
            base.address
              ? fetch(`${API}/arkham/token-holders/${encodeURIComponent(base.address)}`).then(r => r.ok ? r.json() : null)
              : Promise.resolve(null),
          ])
          if (!cancelled) {
            if (aRes.status === "fulfilled" && aRes.value) setArkhamData(aRes.value)
            if (tRes.status === "fulfilled" && tRes.value?.transactions) setTransactions(tRes.value.transactions)
            if (hRes.status === "fulfilled" && hRes.value?.holders) setHolders(hRes.value.holders)
          }
        }
      } catch { /* silent */ }
      if (!cancelled) setLoading(false)
    }
    load()
    return () => { cancelled = true }
  }, [entityId])

  const accent = entity ? TYPE_COLORS[entity.type] || "var(--blue-bright)" : "var(--blue-bright)"
  const typeLabel = entity ? TYPE_LABELS[entity.type] || entity.type?.toUpperCase() || "ENTITY" : "LOADING"

  const holdings: { token: string; symbol: string; balance: string; value: number; pct: number }[] =
    arkhamData?.entity?.holdings || entity?.arkham_data?.holdings || []

  const related: { name: string; slug: string; type: string }[] =
    arkhamData?.entity?.related || entity?.arkham_data?.related_entities || []

  return (
    <div style={{
      minHeight: "100%", padding: "0 24px 40px",
      animation: "fadeUp 0.5s var(--ease-out) both",
    }}>
      {/* Back Button */}
      <button
        onClick={onBack}
        className="nav-item"
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          background: "transparent", border: "1px solid var(--border)",
          borderRadius: "var(--r-sm)", padding: "6px 14px",
          color: "var(--text-2)", fontSize: 12, cursor: "pointer",
          fontFamily: "var(--font-mono)", marginTop: 16,
          transition: "all 0.2s var(--ease-out)",
        }}
      >
        <span style={{ fontSize: 14 }}>←</span> Back
      </button>

      {/* HEADER */}
      <div style={{
        marginTop: 20, padding: "28px 32px",
        background: `linear-gradient(135deg, var(--bg-card) 0%, var(--bg-card-2) 100%)`,
        borderRadius: "var(--r-lg)", border: "1px solid var(--border)",
        position: "relative", overflow: "hidden",
      }}>
        <div style={{
          position: "absolute", top: 0, left: 0, right: 0, height: 2,
          background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
        }} />
        <div style={{
          position: "absolute", top: 0, left: 40, width: 200, height: 120,
          background: accent, filter: "blur(80px)", opacity: 0.06,
          pointerEvents: "none",
        }} />

        {loading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <Skeleton w="120px" h={12} />
            <Skeleton w="280px" h={28} />
          </div>
        ) : (
          <div style={{ position: "relative", zIndex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
              <span style={{
                fontSize: 10, fontWeight: 700, letterSpacing: 1.5,
                color: accent, textTransform: "uppercase",
                padding: "3px 10px", borderRadius: 4,
                background: `${accent}15`, border: `1px solid ${accent}30`,
              }}>
                {typeLabel}
              </span>
              {entity?.source && (
                <span style={{
                  fontSize: 9, fontWeight: 600, color: "var(--text-3)",
                  padding: "2px 8px", borderRadius: 4,
                  background: "var(--bg-hover)", letterSpacing: 0.5,
                }}>
                  {entity.source.toUpperCase()}
                </span>
              )}
            </div>

            <div style={{
              fontFamily: "var(--font-display)", fontSize: 28, fontWeight: 700,
              color: "var(--text-1)", letterSpacing: -0.5, lineHeight: 1.2,
            }}>
              {entity?.label || entity?.name || entityId}
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 10, flexWrap: "wrap" }}>
              {entity?.price != null && (
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 600,
                  color: "var(--text-1)", fontVariantNumeric: "tabular-nums",
                }}>
                  {typeof entity.price === "number" ? `$${entity.price.toLocaleString()}` : entity.price}
                </span>
              )}
              {entity?.balance && (
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 500,
                  color: "var(--text-2)",
                }}>
                  {entity.balance}
                </span>
              )}
              {entity?.address && (
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: "auto" }}>
                  <span style={{ fontSize: 10, color: "var(--text-3)" }}>ADDR</span>
                  <Copyable text={entity.address} style={{ fontSize: 11 }} />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* OVERVIEW CARDS ROW */}
      <div style={{
        display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: 12, marginTop: 16,
      }}>
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : (
          [
            { label: "Market Cap", value: fmtUsd(entity?.arkham_data?.market_cap || entity?.snapshot?.market_cap) },
            { label: "24h Volume", value: fmtUsd(entity?.arkham_data?.volume_24h || entity?.snapshot?.volume_24h) },
            { label: "Holders", value: String(holders.length || arkhamData?.wallets_count || entity?.arkham_data?.holders_count || "—") },
            { label: "Transactions", value: String(transactions.length || entity?.arkham_data?.tx_count || "—") },
          ].map((c, i) => (
            <div
              key={c.label}
              className="card-interactive"
              style={{
                padding: "16px 18px", background: "var(--bg-card)",
                borderRadius: "var(--r-md)", border: "1px solid var(--border)",
                animation: `stagger 0.45s var(--ease-out) both`,
                animationDelay: `${i * 0.06}s`,
              }}
            >
              <div style={{ fontSize: 10, color: "var(--text-3)", fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", marginBottom: 6 }}>
                {c.label}
              </div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600,
                color: "var(--text-1)", fontVariantNumeric: "tabular-nums",
              }}>
                {c.value}
              </div>
            </div>
          ))
        )}
      </div>

      {/* TABS */}
      <div style={{
        display: "flex", gap: 0, marginTop: 24,
        borderBottom: "1px solid var(--border)",
      }}>
        {(["overview", "holdings", "transactions", "related"] as const).map(t => {
          const active = tab === t
          return (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: "none", border: "none", cursor: "pointer",
                padding: "10px 20px", position: "relative",
                fontSize: 12, fontWeight: active ? 600 : 400,
                color: active ? TAB_COLORS[t] : "var(--text-3)",
                fontFamily: "var(--font-mono)", letterSpacing: 0.5,
                textTransform: "uppercase",
                transition: "color 0.2s var(--ease-out)",
              }}
            >
              {t}
              {active && (
                <div style={{
                  position: "absolute", bottom: -1, left: 0, right: 0,
                  height: 2, borderRadius: "2px 2px 0 0",
                  background: TAB_COLORS[t],
                  boxShadow: `0 0 8px ${TAB_COLORS[t]}60`,
                  animation: "stagger 0.3s var(--ease-spring) both",
                }} />
              )}
            </button>
          )
        })}
      </div>

      {/* TAB CONTENT */}
      <div style={{ marginTop: 20, animation: "fadeUp 0.35s var(--ease-out) both", minHeight: 300 }}>

        {/* OVERVIEW TAB */}
        {tab === "overview" && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {entity?.snapshot && (
              <div style={{
                padding: 20, background: "var(--bg-card)",
                borderRadius: "var(--r-md)", border: "1px solid var(--border)",
              }}>
                <div style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", marginBottom: 14 }}>
                  Live Snapshot
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
                  {entity.snapshot.px != null && (
                    <div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>Price</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, color: "var(--text-1)" }}>
                        ${Math.round(entity.snapshot.px).toLocaleString()}
                      </div>
                    </div>
                  )}
                  {entity.snapshot.cvd != null && (
                    <div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>CVD</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, color: "var(--text-1)" }}>
                        {(entity.snapshot.cvd as number).toLocaleString()}
                      </div>
                    </div>
                  )}
                  {entity.snapshot.metrics && (
                    <>
                      <div>
                        <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>Buy Vol (100)</div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, color: "var(--green)" }}>
                          {(entity.snapshot.metrics.buy_vol_100 as number)?.toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>Sell Vol (100)</div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, color: "var(--red)" }}>
                          {(entity.snapshot.metrics.sell_vol_100 as number)?.toLocaleString()}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>OB Imbalance</div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, color: "var(--text-1)" }}>
                          {((entity.snapshot.metrics.ob_imbalance_5 as number || 0) * 100).toFixed(1)}%
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            {entity?.funding_data && (
              <div style={{
                padding: 20, background: "var(--bg-card)",
                borderRadius: "var(--r-md)", border: "1px solid var(--border)",
              }}>
                <div style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", marginBottom: 14 }}>
                  Funding Rates
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {Object.entries(entity.funding_data).map(([exchange, info]: [string, any]) => {
                    const rate = info.rate ?? info.funding_rate ?? 0
                    return (
                      <div key={exchange} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 12, color: "var(--text-2)", fontWeight: 500 }}>{exchange}</span>
                        <span style={{
                          fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600,
                          color: rate >= 0 ? "var(--green)" : "var(--red)",
                        }}>
                          {rate >= 0 ? "+" : ""}{(rate * 100).toFixed(4)}%
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {entity?.arkham_data && (
              <div style={{
                padding: 20, background: "var(--bg-card)",
                borderRadius: "var(--r-md)", border: "1px solid var(--border)",
                borderTop: `2px solid var(--cyan)`,
              }}>
                <div style={{ fontSize: 11, color: "var(--cyan)", fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", marginBottom: 14 }}>
                  Arkham Intelligence
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
                  {entity.arkham_data.name && (
                    <div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>Name</div>
                      <div style={{ fontSize: 13, color: "var(--text-1)", fontWeight: 500 }}>{entity.arkham_data.name}</div>
                    </div>
                  )}
                  {entity.arkham_data.label && (
                    <div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>Label</div>
                      <div style={{ fontSize: 13, color: "var(--text-1)", fontWeight: 500 }}>{entity.arkham_data.label}</div>
                    </div>
                  )}
                  {entity.arkham_data.total_value && (
                    <div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>Total Value</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600, color: "var(--text-1)" }}>
                        {entity.arkham_data.total_value}
                      </div>
                    </div>
                  )}
                  {entity.arkham_data.address && (
                    <div>
                      <div style={{ fontSize: 10, color: "var(--text-3)", marginBottom: 2 }}>Address</div>
                      <Copyable text={entity.arkham_data.address} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {arkhamData?.wallets && arkhamData.wallets.length > 0 && (
              <div style={{
                padding: 20, background: "var(--bg-card)",
                borderRadius: "var(--r-md)", border: "1px solid var(--border)",
              }}>
                <div style={{ fontSize: 11, color: "var(--text-3)", fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", marginBottom: 14 }}>
                  Identified Wallets ({arkhamData.wallets_count || arkhamData.wallets.length})
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {arkhamData.wallets.slice(0, 10).map((w: any, i: number) => (
                    <div key={i} style={{
                      display: "flex", alignItems: "center", gap: 10,
                      padding: "6px 10px", borderRadius: "var(--r-sm)",
                      background: i % 2 === 0 ? "transparent" : "var(--bg-hover)",
                    }}>
                      {w.chain && (
                        <span style={{
                          fontSize: 9, fontWeight: 700, color: "var(--text-3)",
                          padding: "1px 6px", borderRadius: 3,
                          background: "var(--bg-active)", letterSpacing: 0.5,
                          textTransform: "uppercase",
                        }}>
                          {w.chain}
                        </span>
                      )}
                      <Copyable text={w.address || ""} />
                      {w.label && (
                        <span style={{ fontSize: 11, color: "var(--cyan)", fontWeight: 500 }}>{w.label}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {!entity?.snapshot && !entity?.funding_data && !entity?.arkham_data && !arkhamData?.wallets && !loading && (
              <div style={{
                padding: 40, textAlign: "center", color: "var(--text-3)",
                background: "var(--bg-card)", borderRadius: "var(--r-md)", border: "1px solid var(--border)",
              }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>◈</div>
                <div style={{ fontSize: 13 }}>No detailed overview data available for this entity</div>
              </div>
            )}
          </div>
        )}

        {/* HOLDINGS TAB */}
        {tab === "holdings" && (
          holdings.length > 0 ? (
            <div style={{
              background: "var(--bg-card)", borderRadius: "var(--r-md)",
              border: "1px solid var(--border)", overflow: "hidden",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-2)" }}>
                    {["Token", "Balance", "Value", "Allocation"].map(h => (
                      <th key={h} style={{
                        padding: "10px 16px", fontSize: 10, fontWeight: 600,
                        color: "var(--text-3)", textAlign: "left",
                        letterSpacing: 1, textTransform: "uppercase",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {holdings.map((h, i) => {
                    const barColor = [
                      "var(--blue-bright)", "var(--purple)", "var(--cyan)",
                      "var(--green)", "var(--amber)", "var(--red)",
                    ][i % 6]
                    return (
                      <tr key={i} style={{
                        borderBottom: "1px solid var(--border)",
                        transition: "background 0.15s",
                        cursor: "default",
                      }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                      >
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{
                              width: 24, height: 24, borderRadius: "50%",
                              background: `${barColor}20`, border: `1px solid ${barColor}40`,
                              display: "flex", alignItems: "center", justifyContent: "center",
                              fontSize: 10, fontWeight: 700, color: barColor,
                            }}>
                              {(h.symbol || h.token || "?").slice(0, 2)}
                            </div>
                            <div>
                              <div style={{ fontSize: 12, fontWeight: 600, color: "var(--text-1)" }}>{h.token || h.symbol}</div>
                              <div style={{ fontSize: 10, color: "var(--text-3)" }}>{h.symbol}</div>
                            </div>
                          </div>
                        </td>
                        <td style={{
                          padding: "12px 16px", fontFamily: "var(--font-mono)",
                          fontSize: 12, color: "var(--text-2)",
                        }}>{h.balance}</td>
                        <td style={{
                          padding: "12px 16px", fontFamily: "var(--font-mono)",
                          fontSize: 12, fontWeight: 600, color: "var(--text-1)",
                        }}>{fmtUsd(h.value)}</td>
                        <td style={{ padding: "12px 16px", width: 200 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{
                              flex: 1, height: 6, borderRadius: 3,
                              background: "var(--bg-hover)", overflow: "hidden",
                            }}>
                              <div style={{
                                width: `${Math.min(h.pct || 0, 100)}%`, height: "100%",
                                borderRadius: 3, background: barColor,
                                animation: "barFill 0.8s var(--ease-out) both",
                                animationDelay: `${i * 0.05}s`,
                                boxShadow: `0 0 8px ${barColor}40`,
                              }} />
                            </div>
                            <span style={{
                              fontFamily: "var(--font-mono)", fontSize: 11,
                              fontWeight: 600, color: "var(--text-2)", minWidth: 40,
                              fontVariantNumeric: "tabular-nums",
                            }}>
                              {(h.pct || 0).toFixed(1)}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{
              padding: 40, textAlign: "center", color: "var(--text-3)",
              background: "var(--bg-card)", borderRadius: "var(--r-md)", border: "1px solid var(--border)",
            }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>⬡</div>
              <div style={{ fontSize: 13 }}>No holdings data available</div>
              <div style={{ fontSize: 11, marginTop: 4, color: "var(--text-4)" }}>Holdings are shown for Arkham-identified entities with portfolio data</div>
            </div>
          )
        )}

        {/* TRANSACTIONS TAB */}
        {tab === "transactions" && (
          transactions.length > 0 ? (
            <div style={{
              background: "var(--bg-card)", borderRadius: "var(--r-md)",
              border: "1px solid var(--border)", overflow: "hidden",
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-2)" }}>
                    {["Hash", "From", "To", "Amount", "Token", "Time"].map(h => (
                      <th key={h} style={{
                        padding: "10px 14px", fontSize: 10, fontWeight: 600,
                        color: "var(--text-3)", textAlign: "left",
                        letterSpacing: 1, textTransform: "uppercase",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {transactions.slice(0, 25).map((tx, i) => {
                    const isOut = entity?.address && tx.from?.toLowerCase() === entity.address.toLowerCase()
                    return (
                      <tr key={i} style={{
                        borderBottom: "1px solid var(--border)",
                        transition: "background 0.15s",
                      }}
                        onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")}
                        onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                      >
                        <td style={{ padding: "10px 14px" }}>
                          <Copyable text={tx.hash} style={{ fontSize: 10 }} />
                        </td>
                        <td style={{ padding: "10px 14px" }}>
                          <Copyable text={tx.from} style={{ color: isOut ? "var(--red)" : "var(--text-2)" }} />
                        </td>
                        <td style={{ padding: "10px 14px" }}>
                          <Copyable text={tx.to} style={{ color: !isOut ? "var(--green)" : "var(--text-2)" }} />
                        </td>
                        <td style={{
                          padding: "10px 14px", fontFamily: "var(--font-mono)",
                          fontSize: 12, fontWeight: 600,
                          color: isOut ? "var(--red)" : "var(--green)",
                          fontVariantNumeric: "tabular-nums",
                        }}>
                          {isOut ? "-" : "+"}{tx.amount}
                        </td>
                        <td style={{
                          padding: "10px 14px", fontSize: 11, fontWeight: 600,
                          color: "var(--blue-bright)",
                        }}>{tx.token}</td>
                        <td style={{
                          padding: "10px 14px", fontSize: 11,
                          color: "var(--text-3)", fontVariantNumeric: "tabular-nums",
                          whiteSpace: "nowrap",
                        }}>{timeAgo(tx.time)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{
              padding: 40, textAlign: "center", color: "var(--text-3)",
              background: "var(--bg-card)", borderRadius: "var(--r-md)", border: "1px solid var(--border)",
            }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>◉</div>
              <div style={{ fontSize: 13 }}>No transaction data available</div>
              <div style={{ fontSize: 11, marginTop: 4, color: "var(--text-4)" }}>Transactions are shown for entities with on-chain activity</div>
            </div>
          )
        )}

        {/* RELATED ENTITIES TAB */}
        {tab === "related" && (
          related.length > 0 ? (
            <div style={{
              display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12,
            }}>
              {related.map((r, i) => (
                <div
                  key={i}
                  className="card-interactive"
                  style={{
                    padding: "16px 18px", background: "var(--bg-card)",
                    borderRadius: "var(--r-md)", border: "1px solid var(--border)",
                    cursor: "pointer",
                    animation: `stagger 0.4s var(--ease-out) both`,
                    animationDelay: `${i * 0.04}s`,
                  }}
                >
                  <div style={{
                    fontSize: 9, fontWeight: 700, letterSpacing: 1, marginBottom: 6,
                    color: TYPE_COLORS[r.type] || "var(--cyan)",
                    textTransform: "uppercase",
                  }}>
                    {TYPE_LABELS[r.type] || r.type?.toUpperCase() || "ENTITY"}
                  </div>
                  <div style={{
                    fontSize: 13, fontWeight: 600, color: "var(--text-1)",
                    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                  }}>
                    {r.name}
                  </div>
                  {r.slug && (
                    <div style={{ fontSize: 10, color: "var(--text-3)", marginTop: 4, fontFamily: "var(--font-mono)" }}>
                      {truncAddr(r.slug, 20, 0)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{
              padding: 40, textAlign: "center", color: "var(--text-3)",
              background: "var(--bg-card)", borderRadius: "var(--r-md)", border: "1px solid var(--border)",
            }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>◆</div>
              <div style={{ fontSize: 13 }}>No related entities found</div>
              <div style={{ fontSize: 11, marginTop: 4, color: "var(--text-4)" }}>Related entities share the same label group or organization</div>
            </div>
          )
        )}
      </div>
    </div>
  )
}
