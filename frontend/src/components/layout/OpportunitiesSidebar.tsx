import { OpportunityFeed } from "../OpportunityFeed"

// =========================================================
// OPPORTUNITIES SIDEBAR — Slide-in panel right side
// =========================================================

interface OpportunitiesSidebarProps {
  isOpen: boolean
  onClose: () => void
}

export function OpportunitiesSidebar({ isOpen, onClose }: OpportunitiesSidebarProps) {
  if (!isOpen) return null

  return (
    <div className="opportunities-sidebar">
      <button className="sidebar-close" onClick={onClose} aria-label="Close opportunities">
        ✕
      </button>
      <div style={{ padding: "14px 14px 8px", borderBottom: "1px solid var(--border-light)" }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-muted)", letterSpacing: 1, textTransform: "uppercase" }}>
          ◎ Opportunities
        </span>
      </div>
      <div className="sidebar-content">
        <OpportunityFeed />
      </div>
    </div>
  )
}
