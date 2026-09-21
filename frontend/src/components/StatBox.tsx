import { CSSProperties } from "react"

interface StatBoxProps {
  label: string
  value: string | number
  delta?: number
  deltaLabel?: string
  size?: "sm" | "md" | "lg"
  style?: CSSProperties
}

/**
 * StatBox — ARK Intelligence metric with label, value, optional delta
 */
export function StatBox({ label, value, delta, deltaLabel, size = "md", style }: StatBoxProps) {
  const deltaColor = delta !== undefined
    ? delta > 0 ? "positive" : delta < 0 ? "negative" : ""
    : ""

  return (
    <div className="stat-box" style={style}>
      <div className="stat-box-label">{label}</div>
      <div className="stat-box-value">{value}</div>
      {delta !== undefined && (
        <div className={`stat-box-delta ${deltaColor}`}>
          {delta > 0 && "▲"}
          {delta < 0 && "▼"}
          {Math.abs(delta)}{deltaLabel || ""}
        </div>
      )}
    </div>
  )
}
