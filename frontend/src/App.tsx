import { useEffect, useState } from "react"
import { WSProvider, useMarket } from "./contexts/WSContext"
import Sidebar from "./components/layout/Sidebar"
import TopBar from "./components/layout/TopBar"
import EntityDetail from "./components/layout/EntityDetail"
import ArkhamEntityPage from "./components/layout/ArkhamEntityPage"
import DashboardPage from "./pages/Dashboard"
import ChatPage from "./pages/Chat"
import DesktopPage from "./pages/Desktop"
import VisionPage from "./pages/Vision"
import AgentsPage from "./pages/Agents"
import TerminalPage from "./pages/Terminal"
import AlphaLabPage from "./pages/AlphaLab"
import { LanguageProvider } from "./i18n"
import { get, post } from "./services/api"

// =========================================================
// PAGE MAP
// =========================================================
const PAGES: Record<string, React.ComponentType<any>> = {
  dashboard: DashboardPage,
  chat:      ChatPage,
  desktop:   DesktopPage,
  vision:    VisionPage,
  agents:    AgentsPage,
  terminal:  TerminalPage,
  alpha:     AlphaLabPage,
}

const pageFromPath = () => {
  const firstSegment = window.location.pathname.split("/").filter(Boolean)[0]
  return firstSegment && PAGES[firstSegment] ? firstSegment : "dashboard"
}

type SecurityStatus = {
  access_gate: "enabled" | "local-open"
  authenticated?: boolean
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "ready" | "locked">("checking")
  const [token, setToken] = useState("")
  const [error, setError] = useState("")

  useEffect(() => {
    let mounted = true

    async function checkAccess() {
      try {
        const params = new URLSearchParams(window.location.search)
        if (params.has("access_token")) {
          params.delete("access_token")
          const nextSearch = params.toString()
          window.history.replaceState({}, "", `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}${window.location.hash}`)
          if (mounted) {
            setError("Token URL refuse par securite. Entre le token client manuellement.")
            setState("locked")
          }
          return
        }

        const status = await get<SecurityStatus>("/security/status")
        if (!mounted) return
        setState(status.access_gate === "enabled" && !status.authenticated ? "locked" : "ready")
      } catch {
        if (mounted) setState("locked")
      }
    }

    void checkAccess()
    return () => { mounted = false }
  }, [])

  const login = async (event: React.FormEvent) => {
    event.preventDefault()
    setError("")
    try {
      await post("/security/login", { token: token.trim() })
      setState("ready")
      setToken("")
    } catch {
      setError("Token invalide ou session refusee.")
    }
  }

  if (state === "checking") {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "#02060d", color: "#8fb7ff", fontFamily: "monospace" }}>
        Core Equity security check...
      </div>
    )
  }

  if (state === "locked") {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", background: "radial-gradient(circle at 50% 0%, rgba(0,122,255,.22), transparent 36%), #02060d", color: "#f5f8ff", fontFamily: "monospace", padding: 24 }}>
        <form onSubmit={login} style={{ width: "min(440px, 100%)", border: "1px solid rgba(43,133,255,.45)", borderRadius: 18, padding: 28, background: "rgba(8,16,31,.92)", boxShadow: "0 20px 80px rgba(0,0,0,.42)" }}>
          <div style={{ color: "#00d6a3", fontSize: 11, letterSpacing: ".16em", textTransform: "uppercase", marginBottom: 12 }}>Core Client Access</div>
          <h1 style={{ margin: 0, fontSize: 28 }}>Core Equity Alpha Lab</h1>
          <p style={{ color: "#7790b8", lineHeight: 1.6, margin: "12px 0 22px" }}>Acces reserve. Entre le token client pour ouvrir les donnees, RPC et modules de copie wallet.</p>
          <input
            value={token}
            onChange={(event) => setToken(event.target.value)}
            type="password"
            autoFocus
            placeholder="Core access token"
            style={{ width: "100%", boxSizing: "border-box", border: "1px solid rgba(70,126,210,.55)", borderRadius: 12, padding: "13px 14px", background: "#050a14", color: "#f5f8ff", outline: "none", fontFamily: "monospace" }}
          />
          {error && <div style={{ color: "#ff5d6c", marginTop: 12, fontSize: 12 }}>{error}</div>}
          <button type="submit" style={{ width: "100%", marginTop: 16, border: 0, borderRadius: 12, padding: "13px 14px", background: "linear-gradient(135deg, #1682ff, #00d6a3)", color: "#00111c", fontWeight: 800, cursor: "pointer", fontFamily: "monospace" }}>
            Unlock private session
          </button>
        </form>
      </div>
    )
  }

  return <>{children}</>
}

// =========================================================
// APP CONTENT — composes Sidebar + TopBar + Page + Overlays
// =========================================================
function AppContent() {
  const [active, setActive] = useState(pageFromPath)
  const [prevActive, setPrev] = useState("dashboard")
  const [entityDetailId, setEntityDetailId] = useState<string | null>(null)
  const [arkhamPageId, setArkhamPageId] = useState<string | null>(null)
  const { connected } = useMarket()
  const Page = PAGES[active] || DashboardPage

  useEffect(() => {
    const handlePopState = () => {
      setActive(pageFromPath())
      setArkhamPageId(null)
      setEntityDetailId(null)
    }
    window.addEventListener("popstate", handlePopState)
    return () => window.removeEventListener("popstate", handlePopState)
  }, [])

  const handleNav = (id: string) => {
    setPrev(active)
    setActive(id)
    setArkhamPageId(null)
    setEntityDetailId(null)
    const nextPath = id === "dashboard" ? "/" : `/${id}`
    if (window.location.pathname !== nextPath) {
      window.history.pushState({}, "", nextPath)
    }
  }

  const handleArkhamPageOpen = (entityId: string) => {
    setArkhamPageId(entityId)
    setEntityDetailId(null)
  }

  const toExplorerEntityId = (entityId: string): string | null => {
    if (
      entityId.startsWith("token_") ||
      entityId.startsWith("cg_") ||
      entityId.startsWith("hl_") ||
      entityId.startsWith("xau_") ||
      entityId.startsWith("arkham_") ||
      entityId.startsWith("addr_") ||
      entityId.startsWith("0x")
    ) {
      return entityId
    }

    if (entityId.startsWith("entity_")) {
      const raw = entityId.replace(/^entity_/i, "").trim()
      if (!raw) {
        return null
      }
      return `arkham_${raw.toLowerCase()}`
    }

    if (entityId.startsWith("funding_") || entityId.startsWith("gainer_")) {
      const raw = entityId
        .replace(/^funding_/i, "")
        .replace(/^gainer_/i, "")
        .replace(/USDT$/i, "")
        .replace(/USD$/i, "")
        .replace(/PERP$/i, "")
        .replace(/[^a-zA-Z0-9]/g, "")
        .toUpperCase()

      if (!raw) {
        return null
      }

      if (raw === "XAU" || raw === "GOLD") {
        return "xau_usd"
      }

      return `hl_${raw}`
    }

    return null
  }

  const handleEntitySelect = (entityId: string) => {
    const explorerEntityId = toExplorerEntityId(entityId)
    if (explorerEntityId) {
      setArkhamPageId(explorerEntityId)
      setEntityDetailId(null)
      return
    }

    setEntityDetailId(entityId)
  }

  const handleArkhamPageClose = () => { setArkhamPageId(null) }
  const handleEntityDetailClose = () => { setEntityDetailId(null) }

  return (
    <div className="app-shell">
      <Sidebar
        active={arkhamPageId ? prevActive : active}
        onNavigate={handleNav}
        connected={connected}
      />
      <div className="app-main">
        <TopBar
          page={arkhamPageId ? "entity" : active}
          onEntitySelect={handleEntitySelect}
          onArkhamPageOpen={handleArkhamPageOpen}
        />
        <main key={active} style={{ flex: 1, overflow: "auto", position: "relative" }}>
          <Page onEntitySelect={handleEntitySelect} />
          <EntityDetail entityId={entityDetailId} onClose={handleEntityDetailClose} />
        </main>
      </div>
      <ArkhamEntityPage entityId={arkhamPageId} onClose={handleArkhamPageClose} />
    </div>
  )
}

export default function App() {
  return (
    <LanguageProvider>
      <AuthGate>
        <WSProvider>
          <AppContent />
        </WSProvider>
      </AuthGate>
    </LanguageProvider>
  )
}
