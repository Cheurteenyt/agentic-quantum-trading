interface LiveStatusProps {
  connected: boolean
  label?: string
  size?: "sm" | "md" | "lg"
}

/**
 * LiveStatus — ARK Intelligence connected/disconnected indicator with pulse
 */
export function LiveStatus({ connected, label, size = "md" }: LiveStatusProps) {
  const sizeClass = size !== "md" ? `live-status-${size}` : ""
  return (
    <div className={`live-status ${sizeClass}`}>
      <span className={`live-dot ${connected ? "connected" : "disconnected"}`} />
      <span className={`live-status-label ${connected ? "live-label-on" : "live-label-off"} ${sizeClass}`}>
        {label || (connected ? "LIVE" : "OFFLINE")}
      </span>
    </div>
  )
}
