import { ReactNode } from "react"

// =========================================================
// SHARED UI COMPONENTS — Card, Btn, LiveStatus
// =========================================================

/* ── Card ── */
interface CardProps {
  title?: string
  accent?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}

export function Card({ title, accent, actions, children, className }: CardProps) {
  return (
    <div className={`card${className ? ` ${className}` : ""}`}>
      {accent && <div className="card-accent" style={{ background: accent }} />}
      {(title || actions) && (
        <div className="card-header">
          {title && <span className="card-title">{title}</span>}
          {actions}
        </div>
      )}
      <div className="card-body-compact">{children}</div>
    </div>
  )
}

/* ── Btn ── */
interface BtnProps {
  children: ReactNode
  onClick?: () => void
  variant?: "primary" | "success" | "danger" | "default" | "ghost"
  size?: "sm" | "md"
  disabled?: boolean
  loading?: boolean
  className?: string
  style?: React.CSSProperties
}

export function Btn({
  children, onClick, variant = "default", size = "md",
  disabled = false, loading = false, className, style,
}: BtnProps) {
  return (
    <button
      className={`btn btn-${variant}${size === "sm" ? " btn-sm" : ""}${className ? ` ${className}` : ""}`}
      onClick={onClick}
      disabled={disabled || loading}
      style={style}
    >
      {loading ? "◉" : children}
    </button>
  )
}

/* ── LiveStatus ── */
interface LiveStatusProps {
  connected: boolean
  label: string
  size?: "sm" | "md"
}

export function LiveStatus({ connected, label, size = "md" }: LiveStatusProps) {
  return (
    <div className={`live-status${connected ? "" : " offline"}`}
      style={size === "sm" ? { padding: "1px 5px", fontSize: 8 } : undefined}
    >
      <span className={`live-dot ${connected ? "connected" : "disconnected"}`} />
      <span>{label}</span>
    </div>
  )
}
