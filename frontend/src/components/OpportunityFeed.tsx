import { useEffect, useState } from "react"
import { useMarket } from "../contexts/WSContext"
import { apiUrl } from "../services/api"

interface Opportunity {
  type: string
  symbol: string
  details: unknown
  severity: string
  timestamp?: number
}

const SEVERITY_COLORS: Record<string, string> = {
  critical: "var(--red)",
  high: "var(--amber)",
  medium: "var(--blue-bright)",
  low: "var(--text-3)",
}

const SEVERITY_LABELS: Record<string, string> = {
  critical: "Critical",
  high: "High",
  medium: "Watch",
  low: "Monitor",
}

// FIX ronde 8 : le merge préfixait les nouveaux items sans jamais re-trier —
// après le 2e poll, un signal low fraîchement arrivé s'affichait au rang 01
// au-dessus d'un critical, avec le badge rank + « N live signals » qui
// présentaient ce pseudo-classement comme un classement métier. Même ordre
// que le backend (main.py : severity DESC, |avg_funding| DESC).
const SEVERITY_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 }

export function sortOpportunities(rows: Opportunity[]): Opportunity[] {
  const fundingAbs = (o: Opportunity): number => {
    const details = o.details as { avg_funding?: unknown } | null
    const n = Number(details?.avg_funding)
    return Number.isFinite(n) ? Math.abs(n) : 0
  }
  return [...rows].sort((a, b) => {
    const rankA = SEVERITY_RANK[String(a.severity).toLowerCase()] ?? 0
    const rankB = SEVERITY_RANK[String(b.severity).toLowerCase()] ?? 0
    if (rankA !== rankB) return rankB - rankA
    return fundingAbs(b) - fundingAbs(a)
  })
}

const getOpportunityTone = (opportunity: Opportunity): string => {
  const type = `${opportunity.type || ""}`.toLowerCase()
  const severity = `${opportunity.severity || ""}`.toLowerCase()
  if (severity === "critical" || type.includes("short")) return "risk"
  if (severity === "high" || type.includes("squeeze")) return "hot"
  if (type.includes("long") || type.includes("inflow")) return "long"
  return "neutral"
}

const formatSignedPercent = (value: unknown, digits = 4): string | null => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return null
  const signed = numeric >= 0 ? "+" : ""
  return `${signed}${numeric.toFixed(digits)}%`
}

const formatOpportunityDetails = (details: unknown): string => {
  if (typeof details === "string") return details
  if (details == null) return ""
  if (Array.isArray(details)) {
    return details.map((item) => formatOpportunityDetails(item)).filter(Boolean).join(" | ")
  }
  if (typeof details === "object") {
    const data = details as Record<string, unknown>
    const summary = [
      data.avg_funding != null ? `Avg ${formatSignedPercent(Number(data.avg_funding) * 100)}` : null,
      data.binance_funding != null ? `Binance ${formatSignedPercent(Number(data.binance_funding) * 100)}` : null,
      data.bybit_funding != null ? `Bybit ${formatSignedPercent(Number(data.bybit_funding) * 100)}` : null,
      data.oi_delta_pct != null ? `OI ${formatSignedPercent(data.oi_delta_pct, 1)}` : null,
    ].filter(Boolean)

    if (summary.length > 0) return summary.join(" | ")

    try {
      return JSON.stringify(data)
    } catch {
      return String(details)
    }
  }
  return String(details)
}

const getOpportunityMetrics = (details: unknown): Array<{ label: string; value: string }> => {
  if (!details || typeof details !== "object" || Array.isArray(details)) return []
  const data = details as Record<string, unknown>
  return [
    data.avg_funding != null ? { label: "Avg", value: formatSignedPercent(Number(data.avg_funding) * 100) || "-" } : null,
    data.binance_funding != null ? { label: "Binance", value: formatSignedPercent(Number(data.binance_funding) * 100) || "-" } : null,
    data.bybit_funding != null ? { label: "Bybit", value: formatSignedPercent(Number(data.bybit_funding) * 100) || "-" } : null,
    data.oi_delta_pct != null ? { label: "OI delta", value: formatSignedPercent(data.oi_delta_pct, 1) || "-" } : null,
  ].filter(Boolean) as Array<{ label: string; value: string }>
}

const formatAge = (timestamp?: number): string => {
  if (!timestamp) return "live"
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - timestamp))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  return `${Math.floor(minutes / 60)}h`
}

export function OpportunityFeed() {
  const { data } = useMarket()
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])

  useEffect(() => {
    if (data?.opportunities && Array.isArray(data.opportunities)) {
      setOpportunities(data.opportunities.slice(0, 20))
    }
  }, [data])

  useEffect(() => {
    const fetchOpps = async () => {
      try {
        const host = window.location.hostname
        const response = await fetch(apiUrl("/market/opportunities?limit=10"))
        if (!response.ok) return
        const payload = await response.json()
        if (!payload.opportunities?.length) return
        setOpportunities((prev) => {
          const ids = new Set(prev.map((item) => `${item.type}_${item.symbol}`))
          const fresh = payload.opportunities.filter((item: Opportunity) => !ids.has(`${item.type}_${item.symbol}`))
          return sortOpportunities([...fresh, ...prev]).slice(0, 20)
        })
      } catch {}
    }

    void fetchOpps()
    const timer = window.setInterval(() => {
      void fetchOpps()
    }, 30000)

    return () => window.clearInterval(timer)
  }, [])

  if (opportunities.length === 0) {
    return (
      <div className="opportunity-empty">
        <div className="opportunity-empty-ring" />
        <div>
          <strong>No live opportunities</strong>
          <span>The radar will light up when funding, OI or flow signals cross thresholds.</span>
        </div>
      </div>
    )
  }

  return (
    <div className="opportunity-radar-feed">
      <div className="opportunity-radar-summary">
        <span>{opportunities.length} live signals</span>
        <em>Auto-refresh 30s</em>
      </div>

      {opportunities.slice(0, 8).map((opportunity, index) => {
        const metrics = getOpportunityMetrics(opportunity.details)
        const details = metrics.length ? "" : formatOpportunityDetails(opportunity.details)
        const tone = getOpportunityTone(opportunity)

        return (
          <button
            key={`${opportunity.type}_${opportunity.symbol}_${index}`}
            className={`opportunity-signal-card tone-${tone}`}
            type="button"
          >
            <div className="opportunity-signal-main">
              <div className="opportunity-symbol-block">
                <span className="opportunity-rank">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{opportunity.symbol}</strong>
                  <em>{formatAge(opportunity.timestamp)} ago</em>
                </div>
              </div>
              <div className="opportunity-signal-badges">
                <span
                  className="opportunity-severity"
                  style={{ color: SEVERITY_COLORS[opportunity.severity] || "var(--text-3)" }}
                >
                  {SEVERITY_LABELS[opportunity.severity] || opportunity.severity || "Signal"}
                </span>
                <span>{opportunity.type?.replace(/_/g, " ")}</span>
              </div>
            </div>

            {metrics.length > 0 ? (
              <div className="opportunity-metric-grid">
                {metrics.map((metric) => (
                  <div key={`${opportunity.symbol}-${metric.label}`}>
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </div>
                ))}
              </div>
            ) : details ? (
              <div className="opportunity-signal-details">{details}</div>
            ) : null}

            <div className="opportunity-confidence">
              <span />
            </div>
          </button>
        )
      })}

      {opportunities.length > 8 && (
        <div className="opportunity-radar-more">
          +{opportunities.length - 8} more signals in the live tape
        </div>
      )}
    </div>
  )
}
