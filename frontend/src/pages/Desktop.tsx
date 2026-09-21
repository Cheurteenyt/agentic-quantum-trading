import { useState, useEffect } from "react"

const API = `http://${window.location.hostname}:8000/api/desktop`

export default function DesktopPage() {
  const [status, setStatus] = useState<any>(null)
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [autoCapture, setAutoCapture] = useState(false)
  const [log, setLog] = useState<Array<{ msg: string; ts: string; type: string }>>([])

  const addLog = (msg: string, type: "info" | "success" | "error" = "info") => {
    const ts = new Date().toLocaleTimeString()
    setLog(prev => [{ msg, ts, type }, ...prev.slice(0, 49)])
  }

  useEffect(() => {
    fetch(`${API}/status`).then(r => r.json()).then(d => {
      setStatus(d)
      addLog(`windows-mcp: ${d.windows_mcp ? `connecté (${d.tools_count} outils)` : "non connecté"}`, d.windows_mcp ? "success" : "error")
    }).catch(() => addLog("Backend non disponible", "error"))
  }, [])

  useEffect(() => {
    if (!autoCapture) return
    const t = setInterval(() => doScreenshot(), 10000)
    return () => clearInterval(t)
  }, [autoCapture])

  const doScreenshot = async () => {
    setLoading(true)
    try {
      const r = await fetch(`${API}/screenshot`, { method: "POST" })
      const d = await r.json()
      if (d.success && d.image) {
        setScreenshot(`data:image/jpeg;base64,${d.image}`)
        addLog(`Screenshot capturé`, "success")
      } else addLog(`Erreur: ${d.error || "inconnu"}`, "error")
    } catch (e) { addLog(`Erreur: ${e}`, "error") }
    setLoading(false)
  }

  const mcp_ok = status?.windows_mcp === true

  return (
    <div className="anim-fade-up" style={{ padding: 16 }}>
      <div className="card" style={{ marginBottom: "var(--space-md)" }}>
        <div className="card-body-compact" style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap" }}>
          <div className={`live-status${mcp_ok ? "" : " offline"}`}>
            <span className={`live-dot ${mcp_ok ? "connected" : "disconnected"}`} />
            <span>{mcp_ok ? "windows-mcp connecté" : "windows-mcp déconnecté"}</span>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button className="btn btn-primary btn-sm" onClick={doScreenshot} disabled={loading}>Screenshot</button>
            <button className={`btn btn-sm ${autoCapture ? "btn-danger" : "btn-default"}`} onClick={() => setAutoCapture(!autoCapture)} disabled={!mcp_ok}>
              {autoCapture ? "Stop Auto" : "Auto 10s"}
            </button>
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ gridTemplateColumns: "340px 1fr" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-md)" }}>
          <div className="card">
            <div className="card-header"><span className="card-title">Journal</span></div>
            <div className="card-body-compact" style={{ maxHeight: 300, overflowY: "auto" }}>
              {log.length === 0
                ? <div className="empty-state" style={{ padding: "20px" }}><div className="empty-state-desc">Aucune action</div></div>
                : log.map((l, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, padding: "3px 0", borderBottom: "1px solid var(--border-light)", fontSize: 11 }}>
                    <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 10 }}>{l.ts}</span>
                    <span style={{ color: l.type === "success" ? "var(--success)" : l.type === "error" ? "var(--error)" : "var(--text-secondary)" }}>{l.msg}</span>
                  </div>
                ))
              }
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-accent" />
          <div className="card-header"><span className="card-title">Preview écran Windows</span></div>
          <div className="card-body">
            {screenshot ? (
              <div>
                <img src={screenshot} alt="Screenshot" style={{ width: "100%", borderRadius: "var(--r-md)", border: "1px solid var(--border)", display: "block" }} />
              </div>
            ) : (
              <div className="empty-state">
                <div className="empty-state-icon">⬡</div>
                <div className="empty-state-title">{mcp_ok ? "Clique Screenshot pour capturer" : "windows-mcp requis"}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
