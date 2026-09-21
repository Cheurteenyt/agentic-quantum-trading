import { useState, useEffect, useRef } from "react"
import { Card, Btn, LiveStatus } from "../components"

const API_V = `http://${window.location.hostname}:8000/api/vision`
const API_D = `http://${window.location.hostname}:8000/api/desktop`
const API_M = `http://${window.location.hostname}:8000/api/market`

function LogLine({ msg, ts, type = "info" }: { msg: string; ts: string; type?: "info" | "success" | "error" }) {
  return (
    <div className="log-line">
      <span className="log-line-ts">{ts}</span>
      <span className={`log-line-msg ${type}`}>{msg}</span>
    </div>
  )
}

function SMCBadge({ value, label }: { value: boolean; label: string }) {
  return (
    <div className="smc-badge-row">
      <span className={`smc-badge-dot ${value ? "on" : "off"}`}>{value ? "●" : "○"}</span>
      <span className={`smc-badge-text ${value ? "on" : "off"}`}>{label}</span>
    </div>
  )
}

function DirectionBadge({ direction }: { direction: string }) {
  return <span className={`direction-badge ${direction}`}>{direction}</span>
}

function ConfidenceBar({ level }: { level: string }) {
  const pct = level === "high" ? 100 : level === "medium" ? 60 : 25
  const color = level === "high" ? "var(--success)" : level === "medium" ? "var(--warning)" : "var(--error)"
  return (
    <div className="confidence-row">
      <div className="progress-bar" style={{ flex: 1 }}>
        <div className="progress-fill blue" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="confidence-label">{level} ({pct}%)</span>
    </div>
  )
}

function DataBoxValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="data-box-value-row">
      <span className="data-box-value-label">{label}</span>
      <span className="data-box-value-val">{value}</span>
    </div>
  )
}

export default function VisionPage() {
  const [instrument, setInstrument] = useState("XAUUSD")
  const [timeframe, setTimeframe] = useState("5m")
  const [notes, setNotes] = useState("")
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const [nt8Status, setNt8Status] = useState<any>(null)
  const [autoCapture, setAutoCapture] = useState(false)
  const [log, setLog] = useState<Array<{ msg: string; ts: string; type: string }>>([])
  const [liveMode, setLiveMode] = useState(false)
  const [dataBox, setDataBox] = useState<Record<string, string>>({})
  const [dataBoxLoading, setDataBoxLoading] = useState(false)
  const [agentMode, setAgentMode] = useState(false)
  const [agentInstruction, setAgentInstruction] = useState("")
  const [agentRunning, setAgentRunning] = useState(false)
  const [agentSteps, setAgentSteps] = useState<any[]>([])
  const [agentResult, setAgentResult] = useState<string>("")

  const INSTRUMENTS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "GC"]
  const TIMEFRAMES  = ["1m", "3m", "5m", "15m", "1H", "4H", "1D"]
  const logRef = useRef<HTMLDivElement>(null)

  const addLog = (msg: string, type: "info" | "success" | "error" = "info") => {
    const ts = new Date().toLocaleTimeString()
    setLog(prev => [{ msg, ts, type }, ...prev.slice(0, 99)])
  }

  useEffect(() => { loadHistory(); checkMCPStatus() }, [])
  useEffect(() => { if (!liveMode) return; const t = setInterval(() => doScreenshot(), 5000); return () => clearInterval(t) }, [liveMode])
  useEffect(() => { if (!autoCapture) return; const t = setInterval(() => doScreenshot(), 10000); return () => clearInterval(t) }, [autoCapture])

  const checkMCPStatus = async () => {
    try {
      const r = await fetch(`${API_D}/status`); const d = await r.json(); setNt8Status(d)
      addLog(`windows-mcp: ${d.windows_mcp ? `connecté (${d.tools_count} outils)` : "non connecté"}`, d.windows_mcp ? "success" : "error")
    } catch { addLog("Backend non disponible", "error") }
  }

  const loadHistory = async () => {
    try { const r = await fetch(`${API_V}/history?limit=20`); const d = await r.json(); setHistory(d.history || []) } catch {}
  }

  const doScreenshot = async () => {
    try {
      const r = await fetch(`${API_D}/screenshot`, { method: "POST" }); const d = await r.json()
      if (d.success && d.image) { setScreenshot(`data:image/jpeg;base64,${d.image}`); return true }
      addLog(`Screenshot échoué: ${d.error || "inconnu"}`, "error"); return false
    } catch (e) { addLog(`Erreur screenshot: ${e}`, "error"); return false }
  }

  const sendShortcut = async (keys: string) => {
    try {
      await fetch(`${API_D}/keyboard`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "shortcut", keys }) })
      addLog(`Shortcut envoyé: ${keys}`, "success")
    } catch (e) { addLog(`Erreur shortcut: ${e}`, "error") }
  }

  const fetchDataBox = async () => {
    setDataBoxLoading(true); addLog("Lecture Data Box NT8...")
    try {
      const r = await fetch(`${API_D}/ninjatrader/data-box`); const d = await r.json()
      if (d.success) { setDataBox(d.data.indicators || {}); addLog(`Data Box: ${Object.keys(d.data.indicators || {}).length} valeurs`, "success") }
      else addLog("Data Box vide ou erreur", "error")
    } catch (e) { addLog(`Erreur data box: ${e}`, "error") }
    setDataBoxLoading(false)
  }

  const runFullAnalysis = async () => {
    setLoading(true); addLog("Analyse complète...")
    try {
      const scOk = await doScreenshot()
      if (!scOk) { addLog("Annulé — screenshot échoué", "error"); setLoading(false); return }
      await fetchDataBox()
      const aR = await fetch(`${API_V}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ instrument, timeframe, notes }) })
      const aD = await aR.json()
      setResult(aD.error ? aD : aD)
      addLog(`Analyse terminée`, "success")
      loadHistory()
    } catch (e) { addLog(`Erreur critique: ${e}`, "error"); setResult({ error: String(e) }) }
    setLoading(false)
  }

  const mcpOk = nt8Status?.windows_mcp === true
  const analysis = result?.analysis || {}
  const setup = analysis.setup || {}
  const struct = analysis.structure || {}
  const flow = analysis.order_flow || {}
  const smc = analysis.smc || {}

  return (
    <div className="anim-fade-up vision-page">
      <div className="card" style={{ marginBottom: "var(--space-md)" }}>
        <div className="card-body-compact vision-status-row">
          <LiveStatus connected={mcpOk} label={mcpOk ? "windows-mcp" : "MCP déconnecté"} />
          <LiveStatus connected={liveMode} label={liveMode ? "LIVE 5s" : "LIVE OFF"} size="sm" />
          <div className="vision-status-actions">
            <Btn onClick={() => setLiveMode(!liveMode)} variant={liveMode ? "success" : "default"} disabled={!mcpOk} size="sm">
              {liveMode ? "● LIVE" : "○ LIVE"}
            </Btn>
            <Btn onClick={doScreenshot} variant="primary" disabled={loading || !mcpOk} size="sm">Screenshot</Btn>
            <Btn onClick={runFullAnalysis} variant="primary" disabled={loading || !mcpOk} size="sm">Analyse complète</Btn>
          </div>
        </div>
      </div>

      <div className="vision-grid">
        <div className="vision-col">
          <Card title="Contrôle NT8" accent="var(--success)">
            <div className="vision-col" style={{ gap: 4 }}>
              <div className="vision-section-label">Raccourcis</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                <Btn onClick={() => sendShortcut("F5")} disabled={!mcpOk} size="sm">F5</Btn>
                <Btn onClick={() => sendShortcut("Escape")} disabled={!mcpOk} size="sm">Esc</Btn>
                <Btn onClick={() => sendShortcut("Add")} disabled={!mcpOk} size="sm">+ Zoom</Btn>
                <Btn onClick={() => sendShortcut("Subtract")} disabled={!mcpOk} size="sm">- Zoom</Btn>
              </div>
            </div>
          </Card>

          <Card title="Journal" accent="var(--text-muted)">
            <div ref={logRef} style={{ height: 160, overflowY: "auto" }}>
              {log.length === 0
                ? <div className="empty-state" style={{ padding: "16px 0" }}><div className="empty-state-desc">Aucune action</div></div>
                : log.map((l, i) => <LogLine key={i} msg={l.msg} ts={l.ts} type={l.type as any} />)
              }
            </div>
          </Card>
        </div>

        <div className="vision-col">
          <Card title="Chart NinjaTrader 8" accent="var(--brand-blue)">
            {screenshot
              ? <div className="vision-screenshot-wrap"><img src={screenshot} alt="NT8" className="vision-screenshot-img" /></div>
              : <div className="empty-state" style={{ height: 350 }}>
                  <div className="empty-state-icon">◎</div>
                  <div className="empty-state-title">{mcpOk ? "Clique Screenshot" : "windows-mcp requis"}</div>
                </div>
            }
          </Card>

          {result && (
            <Card title="Signal SMC" accent={setup.direction === "LONG" ? "var(--success)" : setup.direction === "SHORT" ? "var(--error)" : "var(--warning)"}>
              <div className="signal-result-row">
                <DirectionBadge direction={setup.direction || "NONE"} />
                {setup.confidence && <ConfidenceBar level={setup.confidence} />}
              </div>
              {setup.reasoning && <div className="signal-reasoning">{setup.reasoning}</div>}
            </Card>
          )}
        </div>

        <div className="vision-col">
          <Card title="Paramètres" accent="var(--brand-purple)">
            <div className="vision-col" style={{ gap: 10 }}>
              <div>
                <div className="vision-section-label">Instrument</div>
                <select value={instrument} onChange={e => setInstrument(e.target.value)} className="vision-input">
                  {INSTRUMENTS.map(i => <option key={i} value={i}>{i}</option>)}
                </select>
              </div>
              <div>
                <div className="vision-section-label">Timeframe</div>
                <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                  {TIMEFRAMES.map(t => (
                    <Btn key={t} onClick={() => setTimeframe(t)} variant={t === timeframe ? "primary" : "default"} size="sm">{t}</Btn>
                  ))}
                </div>
              </div>
              <div>
                <div className="vision-section-label">Notes</div>
                <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3} placeholder="Contexte..." className="vision-input" style={{ resize: "vertical", fontSize: 11 }} />
              </div>
              <Btn onClick={runFullAnalysis} variant="primary" disabled={loading || !mcpOk} loading={loading}>◎ Analyser</Btn>
            </div>
          </Card>

          <Card title="Data Box NT8" accent="var(--success)">
            {Object.keys(dataBox).length === 0
              ? <div style={{ color: "var(--text-muted)", fontSize: 11, textAlign: "center", padding: "8px 0" }}>Clique Refresh</div>
              : <div>{Object.entries(dataBox).map(([k, v]) => <DataBoxValue key={k} label={k.toUpperCase()} value={v} />)}</div>
            }
          </Card>
        </div>
      </div>
    </div>
  )
}
