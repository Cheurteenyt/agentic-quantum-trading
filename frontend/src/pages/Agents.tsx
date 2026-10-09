import { useEffect, useState } from "react"

import { Card } from "../components/Card"
import { useIntelFeed } from "../hooks"
import { apiUrl } from "../services/api"

const API = apiUrl("/agents")

const fieldStyle = {
  width: "100%",
  background: "var(--bg-input)",
  border: "1px solid var(--border-2)",
  borderRadius: "var(--r-sm)",
  color: "var(--text-1)",
  padding: "10px 12px",
  fontSize: 12,
}

function formatUnixTimestamp(value?: number): string {
  if (!value) {
    return "—"
  }

  const timestamp = value > 1_000_000_000_000 ? value : value * 1000
  return new Date(timestamp).toLocaleString()
}

function formatInvestigationOutput(output: unknown): string {
  if (output == null) {
    return "No structured output yet."
  }

  if (typeof output === "string") {
    return output.length > 280 ? `${output.slice(0, 280)}…` : output
  }

  try {
    const text = JSON.stringify(output)
    return text.length > 280 ? `${text.slice(0, 280)}…` : text
  } catch {
    return "Structured output available."
  }
}

function formatInvestigationError(error: unknown): string {
  if (!error) {
    return ""
  }

  if (typeof error === "string") {
    return error
  }

  if (typeof error === "object" && error !== null && "message" in error) {
    const message = error.message
    return typeof message === "string" ? message : "Unknown investigation error"
  }

  return "Unknown investigation error"
}

function getInvestigationBadge(status: string): string {
  if (status === "completed") {
    return "badge badge-bullish"
  }

  if (status === "failed" || status === "timeout") {
    return "badge badge-bearish"
  }

  return "badge badge-medium"
}

export default function AgentsPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null)
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [signals, setSignals] = useState<Record<string, unknown>[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState("all")
  const [intelGoal, setIntelGoal] = useState("Scrape the title and a short summary of example.com")
  const [intelUrl, setIntelUrl] = useState("https://example.com")
  const [intelTimeout, setIntelTimeout] = useState("20")

  const {
    investigations,
    active: activeInvestigations,
    completed: completedInvestigations,
    failed: failedInvestigations,
    loading: intelLoading,
    error: intelError,
    startInvestigation,
    refetch: refetchIntel,
  } = useIntelFeed({ refreshInterval: 5000 })

  useEffect(() => {
    refresh()
    const interval = window.setInterval(refresh, 5000)
    return () => window.clearInterval(interval)
  }, [])

  const refresh = async () => {
    try {
      // FIX ronde 8 : sans check res.ok, une 401/500 (gate admin actif,
      // backend éteint) retournait le payload d'erreur JSON {detail:...} →
      // running=false → badge « INACTIF » et « No signals » ALORS QUE
      // l'agent tournait — l'erreur réseau seule déclenchait le catch.
      const [agentStatus, signalStats, signalFeed] = await Promise.all([
        fetch(`${API}/status`).then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status} /status`)
          return r.json()
        }),
        fetch(`${API}/signals/stats`).then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status} /signals/stats`)
          return r.json()
        }),
        fetch(`${API}/signals?limit=20`).then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status} /signals`)
          return r.json()
        }),
      ])

      setStatus(agentStatus)
      setStats(signalStats)
      setSignals(signalFeed.signals || [])
      setRunning(Boolean(agentStatus.running))
      setError(null)
    } catch (error) {
      console.error("Failed to refresh agents page:", error)
      // l'état réel est INCONNU : on n'affiche ni « INACTIF » ni
      // « No signals » (les données précédentes restent à l'écran)
      setError("État indisponible — réponse du backend invalide ou refusée")
    }
  }

  const runAgent = async () => {
    await fetch(`${API}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ crypto: "BTC", symbol: "XAUUSD", live: false }),
    })
    window.setTimeout(refresh, 1000)
  }

  const stopAgent = async () => {
    await fetch(`${API}/stop`, { method: "POST" })
    window.setTimeout(refresh, 500)
  }

  const launchIntelInvestigation = async () => {
    const goal = intelGoal.trim()

    if (!goal) {
      return
    }

    await startInvestigation({
      goal,
      url: intelUrl.trim() || undefined,
      timeout: Number(intelTimeout) || 20,
    })
  }

  const actionColor = (action: string) =>
    action === "BUY" ? "badge-bullish" : action === "SELL" ? "badge-bearish" : "badge-medium"

  const filteredSignals =
    tab === "all"
      ? signals
      : signals.filter((signal) => String(signal.action || "HOLD") === tab.toUpperCase())

  return (
    <div className="anim-fade-up" style={{ padding: 16 }}>
      <div className="section-header">
        <div>
          <div className="section-title">Intel & Agents</div>
          <div className="section-subtitle">Agent monitoring, signal feed, and Firecrawl investigations</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-success btn-sm" onClick={runAgent} disabled={running}>
            ▶ Lancer
          </button>
          <button className="btn btn-danger btn-sm" onClick={stopAgent} disabled={!running}>
            ■ Stop
          </button>
        </div>
      </div>

      {error && (
        <div className="badge badge-bearish" style={{ marginBottom: 12, display: "inline-block" }} role="alert">
          {error}
        </div>
      )}

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <div className="stat-box">
          <div className="stat-box-label">Agent Status</div>
          <div
            className="stat-box-value"
            style={{
              color: error ? "var(--amber)" : running ? "var(--green)" : "var(--red)",
              fontSize: 18,
            }}
          >
            {error ? "ÉTAT INCONNU" : running ? "EN COURS" : "INACTIF"}
          </div>
        </div>
        {stats && (
          <>
            <div className="stat-box">
              <div className="stat-box-label">Total Signals</div>
              <div className="stat-box-value">{stats.total || 0}</div>
            </div>
            <div className="stat-box">
              <div className="stat-box-label">Buy</div>
              <div className="stat-box-value" style={{ color: "var(--green)" }}>
                {stats.buy || 0}
              </div>
              <div className="stat-box-delta positive">{stats.buy_pct || 0}%</div>
            </div>
            <div className="stat-box">
              <div className="stat-box-label">Sell</div>
              <div className="stat-box-value" style={{ color: "var(--red)" }}>
                {stats.sell || 0}
              </div>
              <div className="stat-box-delta negative">{stats.sell_pct || 0}%</div>
            </div>
          </>
        )}
        <div className="stat-box">
          <div className="stat-box-label">Intel Active</div>
          <div className="stat-box-value">{activeInvestigations.length}</div>
        </div>
        <div className="stat-box">
          <div className="stat-box-label">Intel Completed</div>
          <div className="stat-box-value">{completedInvestigations.length}</div>
        </div>
        <div className="stat-box">
          <div className="stat-box-label">Intel Failed</div>
          <div className="stat-box-value">{failedInvestigations.length}</div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.05fr) minmax(320px, 0.95fr)",
          gap: 16,
          marginBottom: 16,
        }}
      >
        <Card
          title="Launch Intel Investigation"
          accent="var(--blue-bright)"
          actions={
            <button className="btn btn-sm" onClick={refetchIntel}>
              Refresh
            </button>
          }
        >
          <div style={{ display: "grid", gap: 10 }}>
            <div>
              <div className="stat-box-label" style={{ marginBottom: 6 }}>
                Goal
              </div>
              <textarea
                value={intelGoal}
                onChange={(event) => setIntelGoal(event.target.value)}
                placeholder="Describe the web investigation to run"
                style={{ ...fieldStyle, minHeight: 88, resize: "vertical" }}
              />
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) 110px",
                gap: 10,
              }}
            >
              <div>
                <div className="stat-box-label" style={{ marginBottom: 6 }}>
                  Seed URL
                </div>
                <input
                  value={intelUrl}
                  onChange={(event) => setIntelUrl(event.target.value)}
                  placeholder="https://example.com"
                  style={fieldStyle}
                />
              </div>
              <div>
                <div className="stat-box-label" style={{ marginBottom: 6 }}>
                  Timeout
                </div>
                <input
                  value={intelTimeout}
                  onChange={(event) => setIntelTimeout(event.target.value)}
                  inputMode="numeric"
                  style={fieldStyle}
                />
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <button className="btn btn-primary btn-sm" onClick={launchIntelInvestigation} disabled={intelLoading}>
                {intelLoading ? "Investigation..." : "Run Intel"}
              </button>
              <div style={{ fontSize: 11, color: "var(--text-3)" }}>
                Uses the Firecrawl-backed web agent exposed by `/api/intel/investigate`.
              </div>
            </div>
            {intelError && (
              <div
                style={{
                  border: "1px solid var(--red-dim)",
                  background: "rgba(239, 68, 68, 0.08)",
                  color: "var(--red)",
                  borderRadius: "var(--r-sm)",
                  padding: "10px 12px",
                  fontSize: 11,
                }}
              >
                {intelError}
              </div>
            )}
          </div>
        </Card>

        <Card title="Intel Snapshot" accent="var(--cyan)">
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 8 }}>
              <div className="stat-box">
                <div className="stat-box-label">Active</div>
                <div className="stat-box-value">{activeInvestigations.length}</div>
              </div>
              <div className="stat-box">
                <div className="stat-box-label">Completed</div>
                <div className="stat-box-value">{completedInvestigations.length}</div>
              </div>
              <div className="stat-box">
                <div className="stat-box-label">Failed</div>
                <div className="stat-box-value">{failedInvestigations.length}</div>
              </div>
            </div>
            <div style={{ fontSize: 11, color: "var(--text-2)", lineHeight: 1.7 }}>
              <div>
                Agent runtime:{" "}
                <span style={{ color: "var(--text-1)" }}>
                  {String(status?.mode || status?.running ? "trading-agent active" : "idle")}
                </span>
              </div>
              <div>
                Last known investigations are pulled from the in-memory backend state every 5 seconds.
              </div>
              <div>
                Completed investigations expose structured payloads through the same list, so the UI can preview
                Firecrawl output directly.
              </div>
            </div>
          </div>
        </Card>
      </div>

      <div className="tab-bar">
        {["all", "buy", "sell", "hold"].map((currentTab) => (
          <button
            key={currentTab}
            className={`tab-item${tab === currentTab ? " active" : ""}`}
            onClick={() => setTab(currentTab)}
          >
            {currentTab.charAt(0).toUpperCase() + currentTab.slice(1)}
            {currentTab !== "all" && (
              <span className="tab-count">
                {signals.filter((signal) => String(signal.action || "HOLD") === currentTab.toUpperCase()).length}
              </span>
            )}
          </button>
        ))}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 0.95fr) minmax(0, 1.05fr)",
          gap: 16,
          alignItems: "start",
        }}
      >
        <Card title="Trading Signals" accent="var(--amber)">
          <div className="signal-feed">
            {filteredSignals.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">◆</div>
                <div className="empty-state-title">No signals</div>
                <div className="empty-state-desc">Lance un agent pour générer des signaux</div>
              </div>
            ) : (
              filteredSignals.map((signal, index) => (
                <div key={index} className="signal-card">
                  <div className="signal-card-row">
                    <span className={`badge ${actionColor(String(signal.action || "HOLD"))}`}>
                      {String(signal.action || "HOLD")}
                    </span>
                    <span style={{ fontWeight: 600, color: "var(--text-1)" }}>
                      {String(signal.symbol || "XAUUSD")}
                    </span>
                    <span style={{ marginLeft: "auto", fontSize: 12, color: "var(--text-2)" }}>
                      {String(signal.confidence || "low")}
                    </span>
                  </div>
                  <div className="signal-card-meta">
                    <span>
                      {signal.saved_at ? new Date(String(signal.saved_at)).toLocaleString() : "—"}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card title="Recent Intel Investigations" accent="var(--blue-bright)">
          <div className="signal-feed">
            {investigations.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon">◉</div>
                <div className="empty-state-title">No investigations yet</div>
                <div className="empty-state-desc">Lance une requête intel pour peupler cette vue.</div>
              </div>
            ) : (
              investigations.slice(0, 8).map((investigation) => (
                <div key={investigation.id} className="signal-card">
                  <div className="signal-card-row" style={{ alignItems: "flex-start" }}>
                    <span className={getInvestigationBadge(investigation.status)}>
                      {investigation.status.toUpperCase()}
                    </span>
                    <div style={{ display: "grid", gap: 4, minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: "var(--text-1)",
                          lineHeight: 1.5,
                        }}
                      >
                        {investigation.goal || "Untitled investigation"}
                      </div>
                      {investigation.url && (
                        <div
                          style={{
                            fontSize: 10,
                            color: "var(--blue-bright)",
                            wordBreak: "break-all",
                          }}
                        >
                          {investigation.url}
                        </div>
                      )}
                      <div style={{ fontSize: 11, color: "var(--text-2)", lineHeight: 1.6 }}>
                        {investigation.status === "completed"
                          ? formatInvestigationOutput(investigation.output)
                          : formatInvestigationError(investigation.error) || "Investigation in progress."}
                      </div>
                    </div>
                  </div>
                  <div className="signal-card-meta" style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                    <span>Started: {formatUnixTimestamp(investigation.startedAt)}</span>
                    <span>Completed: {formatUnixTimestamp(investigation.completedAt)}</span>
                    <span>Job: {investigation.firecrawlJobId || "—"}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
