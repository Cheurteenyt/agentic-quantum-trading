import { useEffect, useRef, useState } from "react"

const API_HOST = window.location.port === "5173" ? `${window.location.hostname}:8000` : window.location.host
const API = `${window.location.protocol}//${API_HOST}/api/chat`

interface Message {
  id: number
  role: "user" | "assistant"
  content: string
  ts: Date
  model?: string
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([{
    id: 0,
    role: "assistant",
    content: "Core Equity en ligne. Je surveille XAUUSD et BTC. Que veux-tu analyser ?",
    ts: new Date(),
    model: "Qwen3.5-9B-local",
  }])
  const [input, setInput] = useState("")
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const nextId = useRef(1)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [messages])

  const sendMessage = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput("")
    setMessages(prev => [...prev, { id: nextId.current++, role: "user", content: text, ts: new Date() }])
    setLoading(true)
    try {
      const r = await fetch(`${API}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: text, session_id: sessionId }),
      })
      const d = await r.json()
      if (d.session_id) setSessionId(d.session_id)
      setMessages(prev => [...prev, {
        id: nextId.current++,
        role: "assistant",
        content: d.response || "...",
        ts: new Date(),
        model: d.model || "Qwen3.5-9B-local",
      }])
    } catch {
      setMessages(prev => [...prev, {
        id: nextId.current++,
        role: "assistant",
        content: "Erreur - verifie que le backend et llama-server tournent.",
        ts: new Date(),
      }])
    }
    setLoading(false)
  }

  const modelLabel = (m?: string) =>
    m?.includes("GLM") ? "Cloud - GLM-5.1" : m?.includes("Qwen") ? "Local - Qwen3.5-9B" : "Core"

  const modelColor = (m?: string) =>
    m?.includes("GLM") ? "var(--brand-purple)" : m?.includes("error") ? "var(--error)" : "var(--brand-blue)"

  const resetSession = () => {
    setMessages([{
      id: 0,
      role: "assistant",
      content: "Nouvelle session. Que veux-tu analyser ?",
      ts: new Date(),
      model: "Qwen3.5-9B-local",
    }])
    setSessionId(null)
    nextId.current = 1
  }

  return (
    <div className="chat-container anim-fade-up" style={{ height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 0 12px 0" }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)", fontWeight: 600, letterSpacing: 1, textTransform: "uppercase" }}>
          Core Equity Chat
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {sessionId && <span style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>session {sessionId.slice(-6)}</span>}
          <button className="btn btn-ghost btn-sm" onClick={resetSession}>+ New</button>
        </div>
      </div>
      <div className="chat-messages">
        {messages.map(msg => (
          <div key={msg.id} className={`chat-msg ${msg.role === "user" ? "chat-msg-user" : "chat-msg-assistant"}`}>
            {msg.role === "assistant" && (
              <div style={{ fontSize: 10, marginBottom: 4, fontWeight: 700, color: modelColor(msg.model), letterSpacing: 0.5, textTransform: "uppercase" }}>
                {modelLabel(msg.model)}
              </div>
            )}
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{msg.content}</div>
            <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6, textAlign: "right" }}>
              {msg.ts.toLocaleTimeString()}
            </div>
          </div>
        ))}
        {loading && (
          <div className="chat-msg chat-msg-assistant" style={{ color: "var(--brand-blue)" }}>
            Core reflechit...
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-bar">
        <input
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage()}
          placeholder="Demande a Core Equity..."
          disabled={loading}
        />
        <button className="btn btn-primary btn-sm" onClick={sendMessage} disabled={loading || !input.trim()}>
          Envoyer
        </button>
      </div>
    </div>
  )
}
