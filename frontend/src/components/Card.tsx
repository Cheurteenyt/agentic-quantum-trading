import { CSSProperties } from "react"

interface CardProps {
  title: string
  children: React.ReactNode
  accent?: string
  actions?: React.ReactNode
  className?: string
  style?: CSSProperties
}

/**
 * Card — ARK Intelligence panel with accent line, header, body
 */
export function Card({ title, children, accent, actions, className, style }: CardProps) {
  return (
    <div className={`card${className ? ` ${className}` : ""}`} style={style}>
      {accent && <div className="card-accent" style={accent !== "var(--brand-gradient)" ? { background: accent } : undefined} />}
      <div className="card-header">
        <div className="card-title">{title}</div>
        {actions && <div>{actions}</div>}
      </div>
      <div className="card-body">{children}</div>
    </div>
  )
}
