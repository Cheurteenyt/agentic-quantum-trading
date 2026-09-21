interface TickerProps {
  label: string
  value: string | number
  change?: number
  color?: string
  size?: "sm" | "md" | "lg"
}

/**
 * Ticker — ARK Intelligence price display with change indicator
 */
export function Ticker({ label, value, change, color, size = "md" }: TickerProps) {
  const changeClass = change !== undefined
    ? change > 0 ? "positive" : change < 0 ? "negative" : ""
    : ""

  const sizeClass = size !== "md" ? `ticker-chip-${size}` : ""

  return (
    <div className={`ticker-chip ${sizeClass}`}>
      <span className="ticker-chip-name">{label}</span>
      <span className={`ticker-chip-price${color ? " ticker-chip-price-dynamic" : ""}`}
        {...(color ? { style: { color } } : {})}>{value}</span>
      {change !== undefined && (
        <span className={`ticker-chip-change ${changeClass}`}>
          {change > 0 && "+"}{change.toFixed(2)}%
        </span>
      )}
    </div>
  )
}
