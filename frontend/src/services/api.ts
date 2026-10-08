/**
 * Base API configuration and interceptors
 */

function resolveBaseUrl(): string {
  const runtimeBase =
    typeof window !== "undefined" ? String((window as any).__HERMES_API_BASE__ || "").trim() : ""
  const envBase = String(import.meta.env.VITE_API_BASE_URL || "").trim()
  const rawBase = runtimeBase || envBase || `http://${window.location.hostname}:8000`
  // Le test `n'accole jamais /api deux fois` a trouvé le défaut : on
  // normalisait les slashs FINALS mais pas un `/api` final. Une base
  // configurée à `https://core.example/api` (ce qu'on écrit spontanément,
  // l'API étant déjà dans le nom) produisait `…/api/api/health` — un 404
  // silencieux sur TOUTES les requêtes, sans erreur visible.
  const sansSlash = rawBase.replace(/\/+$/, "")
  const dejaAvecApi = /\/api$/i.test(sansSlash)
  return dejaAvecApi ? sansSlash : `${sansSlash}/api`
}

const BASE_URL = resolveBaseUrl()

/**
 * Racine de l'API SANS le `/api` — pour construire des URLs qui ne
 * passent pas par `request()` (WebSocket, chemins non-`/api`).
 *
 * Issue #208 : 17 fichiers construisaient eux-mêmes
 * `http://${window.location.hostname}:8000/...`, en contournant
 * `resolveBaseUrl()`. Trois conséquences, toutes silencieuses :
 *
 *   1. `credentials: "include"` absent → le cookie `core_access`
 *      (HttpOnly) n'est pas envoyé en cross-origin (5173 → 8000) →
 *      401 sur `/api/search`, `/api/market/opportunities`…
 *   2. `http:` en dur → mixed content dès que le site est en HTTPS.
 *   3. la CSP `connect-src 'self' http://127.0.0.1:* http://localhost:*`
 *      refuse toute autre origine.
 *
 * Corriger le résolveur ne changeait RIEN pour ces 17 fichiers : c'est
 * l'invariant « calculé mais pas appliqué », déjà vu ailleurs.
 */
export const API_ROOT = BASE_URL.replace(/\/api$/, "")

/** Racine du WebSocket, protocole déduit de celui de la page. */
export const WS_ROOT = (() => {
  const u = new URL(API_ROOT)
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:"
  return u.toString().replace(/\/+$/, "")
})()

/** `GET`/`POST`/… avec les credentials par défaut — pour l'UI. */
export function apiUrl(path: string): string {
  if (!path) return BASE_URL
  return `${BASE_URL}${path.startsWith("/") ? path : `/${path}`}`
}

/** URL absolue d'un chemin qui n'est PAS sous `/api` (santé, WS, …). */
export function rootUrl(path: string): string {
  if (!path) return API_ROOT
  return `${API_ROOT}${path.startsWith("/") ? path : `/${path}`}`
}

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
