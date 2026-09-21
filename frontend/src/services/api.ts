/**
 * Base API configuration and interceptors
 */

function resolveBaseUrl(): string {
  const runtimeBase =
    typeof window !== "undefined" ? String((window as any).__HERMES_API_BASE__ || "").trim() : ""
  const envBase = String(import.meta.env.VITE_API_BASE_URL || "").trim()
  const rawBase = runtimeBase || envBase || `http://${window.location.hostname}:8000`
  return `${rawBase.replace(/\/+$/, "")}/api`
}

const BASE_URL = resolveBaseUrl()

interface RequestConfig extends RequestInit {
  requiresAuth?: boolean
}

export class ApiServiceError extends Error {
  status: number
  data: any

  constructor(message: string, status: number, data: any) {
    super(message)
    this.name = "ApiServiceError"
    this.status = status
    this.data = data
  }
}

/**
 * Generic request handler with error handling
 */
async function request<T>(endpoint: string, config?: RequestConfig): Promise<T> {
  const url = `${BASE_URL}${endpoint}`
  
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...config?.headers,
  }

  try {
    const res = await fetch(url, {
      ...config,
      headers,
      credentials: config?.credentials || "include",
    })

    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}))
      throw new ApiServiceError(
        errorData.message || `HTTP ${res.status}`,
        res.status,
        errorData
      )
    }

    // Handle empty responses
    const contentType = res.headers.get("content-type")
    if (!contentType || !contentType.includes("application/json")) {
      return "" as T
    }

    return await res.json()
  } catch (err) {
    if (err instanceof ApiServiceError) {
      throw err
    }
    throw new ApiServiceError(
      "Network error",
      0,
      { message: String(err) }
    )
  }
}

// Export base request for specific services
export const apiRequest = {
  get: <T>(endpoint: string, init?: RequestConfig) => 
    request<T>(endpoint, { ...init, method: "GET" }),
  
  post: <T>(endpoint: string, body?: any, init?: RequestConfig) => 
    request<T>(endpoint, { 
      ...init, 
      method: "POST", 
      body: JSON.stringify(body) 
    }),
  
  put: <T>(endpoint: string, body?: any, init?: RequestConfig) => 
    request<T>(endpoint, { 
      ...init, 
      method: "PUT", 
      body: JSON.stringify(body) 
    }),
  
  delete: <T>(endpoint: string, init?: RequestConfig) => 
    request<T>(endpoint, { ...init, method: "DELETE" }),
}

// Convenience exports
export const { get, post, put, del } = {
  get: apiRequest.get,
  post: apiRequest.post,
  put: apiRequest.put,
  del: apiRequest.delete,
}
