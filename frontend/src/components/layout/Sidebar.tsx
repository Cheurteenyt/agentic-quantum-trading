import type { ReactNode } from "react"
import LogoAvatar from "../LogoAvatar"
import { useLanguage } from "../../i18n"

const Icon = ({ children }: { children: ReactNode }) => (
  <svg className="sidebar-glyph" viewBox="0 0 24 24" aria-hidden="true">
    {children}
  </svg>
)

const NAV_ITEMS = [
  {
    id: "alpha",
    label: "Alpha Lab",
    labelKey: "nav.alpha",
    icon: (
      <Icon>
        <path d="M12 3.2 19.7 7.6v8.8L12 20.8l-7.7-4.4V7.6L12 3.2Z" />
        <path d="m8.1 14.9 3.9-7 3.9 7M9.7 12.3h4.6" />
      </Icon>
    ),
  },
  {
    id: "dashboard",
    label: "Markets",
    labelKey: "nav.markets",
    icon: (
      <Icon>
        <path d="M5 18V8M12 18V5M19 18v-7" />
        <path d="M3.5 18.5h17" />
      </Icon>
    ),
  },
  {
    id: "agents",
    label: "Agents",
    labelKey: "nav.agents",
    icon: (
      <Icon>
        <path d="M12 4v4M12 16v4M4 12h4M16 12h4" />
        <circle cx="12" cy="12" r="3.2" />
        <circle cx="5" cy="5" r="1.4" />
        <circle cx="19" cy="5" r="1.4" />
        <circle cx="5" cy="19" r="1.4" />
        <circle cx="19" cy="19" r="1.4" />
      </Icon>
    ),
  },
  {
    id: "vision",
    label: "Vision",
    labelKey: "nav.vision",
    icon: (
      <Icon>
        <path d="M3.7 12s3-5.1 8.3-5.1S20.3 12 20.3 12s-3 5.1-8.3 5.1S3.7 12 3.7 12Z" />
        <circle cx="12" cy="12" r="2.4" />
      </Icon>
    ),
  },
  {
    id: "desktop",
    label: "Control",
    labelKey: "nav.control",
    icon: (
      <Icon>
        <path d="M5 6.5h14v9H5z" />
        <path d="M9 19h6M12 15.5V19" />
      </Icon>
    ),
  },
  {
    id: "chat",
    label: "Chat",
    labelKey: "nav.chat",
    icon: (
      <Icon>
        <path d="M5 6.5h14v8.8H9.2L5 18.5v-12Z" />
        <path d="M8.5 10h7M8.5 12.7h4.6" />
      </Icon>
    ),
  },
  {
    id: "terminal",
    label: "Terminal",
    labelKey: "nav.terminal",
    icon: (
      <Icon>
        <path d="m6 8 4 4-4 4M12.5 16h5.5" />
      </Icon>
    ),
  },
]

interface SidebarProps {
  active: string
  onNavigate: (id: string) => void
  connected: boolean
}

export default function Sidebar({ active, onNavigate, connected }: SidebarProps) {
  const { t } = useLanguage()

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <LogoAvatar name="Core Equity" symbol="hermes" size={28} title="Core Equity" />
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV_ITEMS.map(item => (
          <button
            key={item.id}
            className={`sidebar-item${active === item.id ? " active" : ""}`}
            onClick={() => onNavigate(item.id)}
            title={t(item.labelKey, item.label)}
          >
            <span className="sidebar-item-icon">{item.icon}</span>
            <span className="sidebar-item-label">{t(item.labelKey, item.label)}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-divider" />

      <div className="sidebar-footer">
        <button className="sidebar-item" style={{ cursor: "default" }} title={connected ? "Connected" : "Disconnected"}>
          <span className="sidebar-item-icon">
            <span className={`live-dot ${connected ? "connected" : "disconnected"}`} />
          </span>
        </button>
      </div>
    </aside>
  )
}
