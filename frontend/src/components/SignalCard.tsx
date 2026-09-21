export type SignalType = "whale" | "listing" | "funding" | "anomaly" | "intel"
export type SignalPriority = "critical" | "high" | "medium" | "low"

interface SignalCardProps {
  id: string
  type: SignalType
  priority: SignalPriority
  title: string
  description?: string
  symbol?: string
  timestamp?: number
  onDismiss?: (id: string) => void
}

const TYPE_CONFIG: Record<SignalType, { label: string; badge: string; icon: string }> = {
  whale:    { label: "WHALE",   badge: "badge-whale",    icon: "◎" },
  listing:  { label: "LISTING", badge: "badge-bullish",  icon: "◆" },
  funding:  { label: "FUNDING", badge: "badge-high",     icon: "⚡" },
  anomaly:  { label: "ANOMALY", badge: "badge-critical", icon: "⚠" },
  intel:    { label: "INTEL",   badge: "badge-medium",   icon: "◉" },
}

const PRIORITY_BORDER: Record<SignalPriority, string> = {
  critical: "badge-critical",
  high: "badge-high",
  medium: "badge-medium",
  low: "badge-low",
}

/**
 * SignalCard — ARK Intelligence signal with priority border and type badge
 */
export function SignalCard({
  id,
  type,
  priority,
  title,
  description,
  symbol,
  timestamp,
  onDismiss,
}: SignalCardProps) {
  const config = TYPE_CONFIG[type]

  const formatTime = (ts: number) => {
    const diff = Date.now() - ts
    if (diff < 60000) return "Just now"
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
    return new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="signal-card">
      <div className="signal-card-row">
        <span className={`badge ${config.badge}`}>
          {config.icon} {config.label}
        </span>
        <span className="signal-card-title">
          {title}
        </span>
        {symbol && <span className="badge badge-medium">{symbol}</span>}
        <span className={`badge ${PRIORITY_BORDER[priority]}`}>
          {priority.toUpperCase()}
        </span>
        {onDismiss && (
          <button className="btn btn-ghost btn-sm signal-card-dismiss" onClick={() => onDismiss(id)}>
            ✕
          </button>
        )}
      </div>

      {description && (
        <div className="signal-card-meta signal-card-desc">
          {description}
        </div>
      )}

      <div className="signal-card-meta">
        {timestamp && <span>{formatTime(timestamp)}</span>}
        <span className="signal-card-type-label">{type}</span>
      </div>
    </div>
  )
}
