export type OpportunityDirection = "LONG" | "SHORT" | "NEUTRAL"
export type OpportunityPriority = "critical" | "high" | "medium" | "low"
export type OpportunityStatus = "active" | "expired" | "closed"

interface OpportunityCardProps {
  id: string
  type: string
  symbol: string
  direction: OpportunityDirection
  confidence: number
  priority: OpportunityPriority
  setup: string
  details?: Record<string, any>
  timestamp?: number
  status?: OpportunityStatus
  onDismiss?: (id: string) => void
  expanded?: boolean
  onToggleExpand?: (id: string) => void
}

const DIRECTION_CONFIG: Record<OpportunityDirection, { label: string; color: string }> = {
  LONG:   { label: "LONG",   color: "#00ff88" },
  SHORT:  { label: "SHORT",  color: "#ff4444" },
  NEUTRAL: { label: "NEUTRAL", color: "#999999" },
}

const PRIORITY_BORDER: Record<OpportunityPriority, string> = {
  critical: "border-left-critical",
  high: "border-left-high",
  medium: "border-left-medium",
  low: "border-left-low",
}

const TYPE_LABELS: Record<string, string> = {
  momentum: "MOMENTUM",
  mean_reversion: "MEAN REVERSION",
  breakout: "BREAKOUT",
  whale_accumulation: "WHALE",
  funding_arb: "FUNDING",
  cross_exchange: "ARBITRAGE",
}

/**
 * OpportunityCard — ARK Intelligence opportunity card with confidence bar and direction indicator
 */
export function OpportunityCard({
  id,
  type,
  symbol,
  direction,
  confidence,
  priority,
  setup,
  details,
  timestamp,
  status = "active",
  onDismiss,
  expanded,
  onToggleExpand,
}: OpportunityCardProps) {
  const dirConfig = DIRECTION_CONFIG[direction] || DIRECTION_CONFIG.NEUTRAL
  const typeLabel = TYPE_LABELS[type] || type.toUpperCase()

  const formatTime = (ts: number) => {
    const diff = Date.now() - ts
    if (diff < 60000) return "Just now"
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    return new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  }

  const isActive = status === "active"

  return (
    <div className={`opportunity-card ${PRIORITY_BORDER[priority]} ${!isActive ? 'opportunity-inactive' : ''} ${expanded ? 'expanded' : ''}`}>
      {/* Header row */}
      <div className="opp-header">
        <span className="opp-type-badge">{typeLabel}</span>
        <span className="opp-symbol">{symbol}</span>
        <span 
          className="opp-direction" 
          style={{ color: dirConfig.color }}
        >
          {dirConfig.label}
        </span>
        <span className="opp-confidence-badge">
          {confidence >= 90 ? '◎' : confidence >= 75 ? '◉' : '○'} {Math.round(confidence)}%
        </span>
        {onDismiss && (
          <button className="btn btn-ghost btn-sm opp-dismiss" onClick={() => onDismiss(id)}>
            ✕
          </button>
        )}
      </div>

      {/* Setup description */}
      {setup && (
        <div className="opp-setup">{setup}</div>
      )}

      {/* Confidence bar */}
      <div className="opp-confidence-row">
        <div className="opp-confidence-bar">
          <div 
            className="opp-confidence-fill" 
            style={{ width: `${Math.min(confidence, 100)}%`, backgroundColor: getConfidenceColor(confidence) }}
          />
        </div>
        <span className="opp-ts">{timestamp ? formatTime(timestamp) : '--'}</span>
      </div>

      {/* Expandable details */}
      {expanded && details && (
        <div className="opp-details">
          {Object.entries(details).map(([key, val]) => (
            <div key={key} className="opp-detail-row">
              <span className="opp-detail-label">{formatDetailLabel(key)}</span>
              <span className="opp-detail-value">{formatDetailValue(val, key)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Expand toggle */}
      {details && !expanded && (
        <button className="btn btn-link btn-xs opp-expand-btn" onClick={() => onToggleExpand?.(id)}>
          Voir détails ▾
        </button>
      )}
    </div>
  )
}

function getConfidenceColor(conf: number): string {
  if (conf >= 90) return "#00ff88" // success
  if (conf >= 75) return "#4488ff" // brand blue
  if (conf >= 60) return "#ffaa00" // warning
  return "#ff4444" // error
}

function formatDetailLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

function formatDetailValue(val: any, key: string): string {
  if (typeof val === 'number') {
    if (val > -1 && val < 1 && keyIncludesPercentages(key)) return `${(val * 100).toFixed(2)}%`
    return val.toFixed ? val.toFixed(4) : String(val)
  }
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  return String(val)
}

function keyIncludesPercentages(key: string): boolean {
  return ['ratio', 'change', 'imbal', 'funding'].some(k => key.includes(k))
}
