import { useEffect, useState } from "react"
import { apiUrl } from "../services/api"

type InvestigationStatus = "pending" | "running" | "completed" | "failed" | "timeout"

interface InvestigationApiItem {
  id: string
  goal?: string
  url?: string | null
  status?: string
  output?: unknown
  error?: unknown
  started_at?: number
  completed_at?: number
  firecrawl_job_id?: string | null
}

export interface Investigation {
  id: string
  goal: string
  url?: string | null
  status: InvestigationStatus
  output?: unknown
  error?: unknown
  startedAt?: number
  completedAt?: number
  firecrawlJobId?: string | null
}

interface StartInvestigationParams {
  goal: string
  url?: string
  timeout?: number
}

interface UseIntelFeedOptions {
  autoRefresh?: boolean
  refreshInterval?: number
}

const API = apiUrl("/intel")

function normalizeStatus(status?: string): InvestigationStatus {
  switch (status) {
    case "running":
    case "completed":
    case "failed":
    case "timeout":
      return status
    default:
      return "pending"
  }
}

function normalizeInvestigation(item: InvestigationApiItem): Investigation {
  return {
    id: item.id,
    goal: item.goal || "",
    url: item.url || null,
    status: normalizeStatus(item.status),
    output: item.output,
    error: item.error,
    startedAt: item.started_at,
    completedAt: item.completed_at,
    firecrawlJobId: item.firecrawl_job_id || null,
  }
}

/**
 * useIntelFeed — Stream les investigations web-agent Firecrawl
 */
export function useIntelFeed({ autoRefresh = true, refreshInterval = 10000 }: UseIntelFeedOptions = {}) {
  const [investigations, setInvestigations] = useState<Investigation[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchInvestigations = async () => {
    try {
      const res = await fetch(`${API}/investigations/active`)

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      const data = (await res.json()) as InvestigationApiItem[]
      setInvestigations(data.map(normalizeInvestigation).reverse())
      setError(null)
    } catch (err) {
      console.error("Failed to fetch investigations:", err)
      setError(err instanceof Error ? err.message : "Unknown intel error")
    }
  }

  const startInvestigation = async ({
    goal,
    url,
    timeout = 30,
  }: StartInvestigationParams): Promise<string | null> => {
    setLoading(true)

    try {
      const res = await fetch(`${API}/investigate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal,
          url: url || undefined,
          timeout,
        }),
      })

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`)
      }

      const data = (await res.json()) as { id?: string }
      await fetchInvestigations()
      return data.id || null
    } catch (err) {
      console.error("Failed to start investigation:", err)
      setError(err instanceof Error ? err.message : "Unknown intel error")
      return null
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchInvestigations()

    if (!autoRefresh) {
      return
    }

    const interval = window.setInterval(fetchInvestigations, refreshInterval)
    return () => window.clearInterval(interval)
  }, [autoRefresh, refreshInterval])

  const active = investigations.filter(
    (investigation) => investigation.status === "running" || investigation.status === "pending",
  )
  const completed = investigations.filter((investigation) => investigation.status === "completed")
  const failed = investigations.filter(
    (investigation) => investigation.status === "failed" || investigation.status === "timeout",
  )

  return {
    investigations,
    active,
    completed,
    failed,
    loading,
    error,
    startInvestigation,
    refetch: fetchInvestigations,
  }
}
