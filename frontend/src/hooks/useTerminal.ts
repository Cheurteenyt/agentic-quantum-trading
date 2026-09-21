import { useState, useCallback, useRef, useEffect } from "react"

export interface TerminalLine {
  id: string
  timestamp: number
  type: "info" | "error" | "warning" | "success" | "command"
  content: string
}

interface UseTerminalOptions {
  maxLines?: number
  autoScroll?: boolean
}

/**
 * useTerminal — Log buffer + execution de commandes en temps réel
 */
export function useTerminal({ maxLines = 500, autoScroll = true }: UseTerminalOptions = {}) {
  const [lines, setLines] = useState<TerminalLine[]>([])
  const [isExecuting, setIsExecuting] = useState(false)
  const [connected, setConnected] = useState(false)
  
  // Auto-scroll refs
  const scrollRef = useRef<HTMLDivElement>(null)
  const lastLengthRef = useRef(0)

  // Scroll au bottom quand nouveau log (si enabled)
  useEffect(() => {
    if (autoScroll && scrollRef.current && lines.length !== lastLengthRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      lastLengthRef.current = lines.length
    }
  }, [lines, autoScroll])

  // Connecter aux logs WebSocket si dispo
  useEffect(() => {
    let ws: WebSocket | null = null
    
    try {
      ws = new WebSocket(`ws://${window.location.hostname}:8000/ws/logs`)
      
      ws.onopen = () => {
        setConnected(true)
      }
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          addLog(data.type || "info", data.content || String(data))
        } catch (err) {
          addLog("info", event.data)
        }
      }
      
      ws.onerror = () => setConnected(false)
      ws.onclose = () => setConnected(false)
    } catch (err) {
      console.error("Failed to connect to logs WS:", err)
    }

    return () => ws?.close()
  }, [])

  const addLog = useCallback((type: TerminalLine["type"], content: string) => {
    setLines(prev => {
      const newLines = [...prev, {
        id: Date.now().toString() + Math.random().toString(36).slice(2),
        timestamp: Date.now(),
        type,
        content,
      }]

      // Limit size
      if (newLines.length > maxLines) {
        return newLines.slice(newLines.length - maxLines)
      }
      
      return newLines
    })
  }, [maxLines])

  const executeCommand = useCallback(async (command: string): Promise<boolean> => {
    setIsExecuting(true)
    
    // Afficher la commande en cours d'exécution
    addLog("command", `$ ${command}`)

    try {
      const res = await fetch(`http://${window.location.hostname}:8000/api/terminal/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      })

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      const data = await res.json()
      addLog("success", data.output || "Command executed successfully")
      return true
    } catch (err: any) {
      addLog("error", `Error: ${err.message || String(err)}`)
      return false
    } finally {
      setIsExecuting(false)
    }
  }, [addLog])

  const clearLogs = useCallback(() => {
    setLines([])
  }, [])

  const formatTime = (ts: number) => {
    return new Date(ts).toLocaleTimeString('fr-FR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const getColor = (type: TerminalLine["type"]) => {
    switch(type) {
      case "error": return "var(--red)"
      case "warning": return "var(--amber)"
      case "success": return "var(--green)"
      case "command": return "var(--cyan)"
      default: return "var(--text-2)"
    }
  }

  return {
    lines,
    isExecuting,
    connected,
    executeCommand,
    addLog,
    clearLogs,
    scrollRef,
    formatTime,
    getColor,
  }
}
