import { useState, useEffect, useCallback } from "react"
import type { SignalType, SignalPriority } from "../components/SignalCard"

export interface Signal {
  id: string
  type: SignalType
  priority: SignalPriority
  title: string
  description?: string
  symbol?: string
  timestamp: number
  acknowledged?: boolean
}

interface UseSignalsOptions {
  autoRefresh?: boolean
  refreshInterval?: number
}

/**
 * useSignals — Fetch + filtre les signals trading avec pagination
 */
export function useSignals({ autoRefresh = true, refreshInterval = 30000 }: UseSignalsOptions = {}) {
  const [signals, setSignals] = useState<Signal[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Categorisation counts
  const counts = {
    all: signals.length,
    critical: signals.filter(s => s.priority === "critical").length,
    whales: signals.filter(s => s.type === "whale").length,
    listings: signals.filter(s => s.type === "listing").length,
  }

  const fetchSignals = async () => {
    try {
      setLoading(true)
      const res = await fetch(`http://${window.location.hostname}:8000/api/market/signals`)
      
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      
      const data = await res.json()
      setSignals(data.signals || [])
      setError(null)
    } catch (err: any) {
      console.error("Failed to fetch signals:", err)
      setError(err.message || "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSignals()

    if (autoRefresh) {
      const interval = setInterval(fetchSignals, refreshInterval)
      return () => clearInterval(interval)
    }
  }, [autoRefresh, refreshInterval])

  // Dismiss un signal (marquer comme lu)
  const dismissSignal = useCallback(async (id: string) => {
    setSignals(prev => prev.filter(s => s.id !== id))
    
    try {
      await fetch(`http://${window.location.hostname}:8000/api/market/signals/${id}`, {
        method: "DELETE",
      })
    } catch (err) {
      console.error("Failed to dismiss signal:", err)
    }
  }, [])

  // Acknowledge un signal
  const acknowledgeSignal = useCallback(async (id: string) => {
    setSignals(prev => prev.map(s => 
      s.id === id ? { ...s, acknowledged: true } : s
    ))

    try {
      await fetch(`http://${window.location.hostname}:8000/api/market/signals/${id}/ack`, {
        method: "POST",
      })
    } catch (err) {
      console.error("Failed to acknowledge signal:", err)
    }
  }, [])

  // Filter by type/priority
  const filterByType = useCallback((type: SignalType) => {
    return signals.filter(s => s.type === type)
  }, [signals])

  const filterByPriority = useCallback((priority: SignalPriority) => {
    return signals.filter(s => s.priority === priority)
  }, [signals])

  // Tri par priorité puis timestamp
  const sorted = [...signals].sort((a, b) => {
    const priorityDiff = a.priority.localeCompare(b.priority)
    if (priorityDiff !== 0) return priorityDiff
    return b.timestamp - a.timestamp
  })

  return {
    signals: sorted,
    counts,
    loading,
    error,
    dismissSignal,
    acknowledgeSignal,
    filterByType,
    filterByPriority,
    refetch: fetchSignals,
  }
}
