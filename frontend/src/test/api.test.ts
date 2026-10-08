/**
 * Tests de la couche API — le SEUL pan du dépôt qui n'avait aucun oracle.
 *
 * 42 fichiers TS/TSX, 0 test. Or c'est là que se logent deux défauts que le
 * backend ne peut pas voir :
 *
 *   1. `api.ts` centralise l'URL de base (`__HERMES_API_BASE__` puis
 *      `VITE_API_BASE_URL`, repli sur le hostname). Mais **16 fichiers le
 *      contournent** avec un `http://${window.location.hostname}:8000` en
 *      dur : corriger le résolveur est sans effet sur eux.
 *   2. `useMarketData` ne sortait jamais de l'état `loading` quand la
 *      réponse HTTP n'était pas `ok` — un 401 (cookie absent) ou un 500
 *      laissait l'interface tourner indéfiniment, sans message.
 *
 * L'URL de base est une constante de MODULE (calculée à l'import), donc
 * chaque cas passe par `vi.resetModules()` + import dynamique.
 */
import { describe, it, expect, vi, afterEach } from "vitest"

function stubWindow(hostname: string, runtime?: string) {
  vi.stubGlobal("window", {
    ...window,
    location: { ...window.location, hostname },
  })
  if (runtime !== undefined) (window as any).__HERMES_API_BASE__ = runtime
}

function urlAppelee(): string {
  const mock = globalThis.fetch as unknown as { mock: { calls: any[][] } }
  return mock.mock.calls[0][0] as string
}

async function recharger(hostname: string, runtime?: string) {
  vi.resetModules()
  stubWindow(hostname, runtime)
  return await import("../services/api")
}

describe("couche API — URL de base et hiérarchie de résolution", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    delete (window as any).__HERMES_API_BASE__
  })

  it("le runtime __HERMES_API_BASE__ prime sur le hostname", async () => {
    const api = await recharger("example.com", "https://core.example")
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })))
    await api.apiRequest.get("/health")
    expect(urlAppelee()).toBe("https://core.example/api/health")
  })

  it("retire les slashs terminaux avant de poser /api", async () => {
    const api = await recharger("example.com", "https://core.example///")
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })))
    await api.apiRequest.get("/health")
    expect(urlAppelee()).toBe("https://core.example/api/health")
  })

  it("replie sur le hostname quand rien n'est configuré", async () => {
    const api = await recharger("localhost")
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })))
    await api.apiRequest.get("/health")
    expect(urlAppelee()).toBe("http://localhost:8000/api/health")
  })

  it("n'accole jamais /api deux fois si la base en finit déjà par /api", async () => {
    const api = await recharger("localhost", "https://core.example/api")
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })))
    await api.apiRequest.get("/health")
    expect(urlAppelee()).not.toContain("/api/api")
  })
})

describe("couche API — le statut HTTP n'est jamais confondu avec des données", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    delete (window as any).__HERMES_API_BASE__
  })

  it("lève ApiServiceError avec le statut et la charge utile", async () => {
    const api = await recharger("localhost")
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "Nope" }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )
    await expect(api.apiRequest.get("/anything")).rejects.toThrow(
      api.ApiServiceError,
    )
  })

  it("un 401 est rejeté, pas traité comme un succès", async () => {
    const api = await recharger("localhost")
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ detail: "token" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )
    let leve = false
    try {
      await api.apiRequest.get("/market/prices")
    } catch {
      leve = true
    }
    expect(leve, "un 401 doit être rejeté, pas renvoyé comme des données").toBe(
      true,
    )
  })
})

/**
 * Le second défaut : `useMarketData` ne sortait pas de `loading`.
 * Un 401 (cookie de session absent) ou un 500 laissait l'interface
 * tourner indéfiniment, sans message — indiscernable d'un backend lent.
 */
describe("useMarketData — sortie d'état loading", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("retombe loading même quand la réponse HTTP n'est pas ok", async () => {
    const { renderHook, act } = await import("@testing-library/react")
    vi.resetModules()
    const { useMarketData } = await import("../hooks/useMarketData")

    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 401 })))
    vi.stubGlobal(
      "setInterval",
      vi.fn(() => 0 as unknown as ReturnType<typeof setInterval>),
    )
    vi.spyOn(console, "error").mockImplementation(() => {})

    const { result } = renderHook(() => useMarketData())
    // `waitFor` n'est PAS fiable ici : la mise a jour d'etat provient
    // d'une promesse resolue hors du rendu, donc `waitFor` ne la voit pas
    // (il expire alors que `loading` EST bien retombé — vérifié). On
    // enveloppe le flush dans `act`, qui est le mécanisme prévu.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    expect(result.current.loading, "un 401 ne doit pas figer l'interface").toBe(
      false,
    )
  })

  it("retombe loading sur une exception réseau", async () => {
    const { renderHook, act } = await import("@testing-library/react")
    vi.resetModules()
    const { useMarketData } = await import("../hooks/useMarketData")

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down")
      }),
    )
    vi.stubGlobal(
      "setInterval",
      vi.fn(() => 0 as unknown as ReturnType<typeof setInterval>),
    )
    vi.spyOn(console, "error").mockImplementation(() => {})

    const { result } = renderHook(() => useMarketData())
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0))
    })
    expect(result.current.loading).toBe(false)
  })
})
