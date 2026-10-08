import { useState, useEffect } from "react"
import { apiUrl } from "../../services/api"

// =========================================================
// ENTITY DETAIL — Slide-in panel (ARK-style)
// =========================================================

interface EntityData {
  id: string
  type: string
  name: string
  label: string
  price?: number | string
  balance?: string
  source?: string
  snapshot?: Record<string, any>
  funding_data?: Record<string, any>
}

interface EntityDetailProps {
  entityId: string | null
  onClose: () => void
}

export default function EntityDetail({ entityId, onClose }: EntityDetailProps) {
  const [entity, setEntity] = useState<EntityData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!entityId) { setEntity(null); return }
    setLoading(true)
    const host = window.location.hostname
    fetch(apiUrl(`/entity/${encodeURIComponent(entityId)}`))
      .then(r => r.ok ? r.json() : null)
      .then(data => { setEntity(data && !data.error ? data : null) })
      .catch(() => setEntity(null))
      .finally(() => setLoading(false))
  }, [entityId])

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  if (!entityId) return null

  const TYPE_COLORS: Record<string, string> = {
    token: "var(--brand-blue)",
    entity: "var(--brand-purple)",
    funding: "var(--warning)",
    gainer: "var(--success)",
  }
  const accentColor = entity ? TYPE_COLORS[entity.type] || "var(--brand-blue)" : "var(--brand-blue)"

  return (
    <div className="entity-detail-overlay" onClick={onClose}>
      <div className="entity-detail-panel" onClick={e => e.stopPropagation()}>
        <div className="entity-detail-accent" style={{ background: accentColor }} />
        <div className="entity-detail-header">
          <div>
            <div className="entity-detail-type" style={{ color: accentColor }}>
              {entity?.type?.toUpperCase() || "..."}
            </div>
            <div className="entity-detail-name">{entity?.label || entity?.name || entityId}</div>
          </div>
          <button className="entity-detail-close" onClick={onClose}>✕</button>
        </div>

        {loading && <div className="entity-detail-loading">Loading...</div>}

        {entity && !loading && (
          <>
            <div className="entity-detail-section">
              <div className="entity-detail-row">
                <span className="entity-detail-key">ID</span>
                <span className="entity-detail-val entity-detail-mono">{entity.id}</span>
              </div>
              <div className="entity-detail-row">
                <span className="entity-detail-key">Source</span>
                <span className="entity-detail-val">{entity.source || "—"}</span>
              </div>
              {entity.price != null && (
                <div className="entity-detail-row">
                  <span className="entity-detail-key">Price</span>
                  <span className="entity-detail-val entity-detail-price">
                    {typeof entity.price === "number" ? `$${entity.price.toLocaleString()}` : entity.price}
                  </span>
                </div>
              )}
              {entity.balance && (
                <div className="entity-detail-row">
                  <span className="entity-detail-key">Balance</span>
                  <span className="entity-detail-val">{entity.balance}</span>
                </div>
              )}
            </div>

            {entity.snapshot && (
              <div className="entity-detail-section">
                <div className="entity-detail-section-title">Live Snapshot</div>
                <div className="entity-detail-row">
                  <span className="entity-detail-key">Price</span>
                  <span className="entity-detail-val entity-detail-price">
                    ${Math.round(entity.snapshot.px || 0).toLocaleString()}
                  </span>
                </div>
                <div className="entity-detail-row">
                  <span className="entity-detail-key">CVD</span>
                  <span className="entity-detail-val">{(entity.snapshot.cvd || 0).toLocaleString()}</span>
                </div>
                {entity.snapshot.metrics && (
                  <>
                    <div className="entity-detail-row">
                      <span className="entity-detail-key">Buy Vol (100)</span>
                      <span className="entity-detail-val" style={{ color: "var(--success)" }}>
                        {entity.snapshot.metrics.buy_vol_100?.toLocaleString()}
                      </span>
                    </div>
                    <div className="entity-detail-row">
                      <span className="entity-detail-key">Sell Vol (100)</span>
                      <span className="entity-detail-val" style={{ color: "var(--error)" }}>
                        {entity.snapshot.metrics.sell_vol_100?.toLocaleString()}
                      </span>
                    </div>
                    <div className="entity-detail-row">
                      <span className="entity-detail-key">OB Imbalance</span>
                      <span className="entity-detail-val">
                        {((entity.snapshot.metrics.ob_imbalance_5 || 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                  </>
                )}
              </div>
            )}

            {entity.funding_data && (
              <div className="entity-detail-section">
                <div className="entity-detail-section-title">Funding Rates</div>
                {Object.entries(entity.funding_data).map(([exchange, info]: [string, any]) => (
                  <div className="entity-detail-row" key={exchange}>
                    <span className="entity-detail-key">{exchange}</span>
                    <span className="entity-detail-val" style={{
                      color: (info.rate ?? info.funding_rate ?? 0) >= 0 ? "var(--success)" : "var(--error)"
                    }}>
                      {((info.rate ?? info.funding_rate ?? 0) * 100).toFixed(4)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
