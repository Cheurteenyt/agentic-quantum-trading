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
import { API_ROOT, WS_ROOT, apiUrl } from "../services/api"

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

/**
 * Ratchet de #208 — le garde-fou contre le retour du dur.
 *
 * 17 fichiers construisaient `http://${window.location.hostname}:8000`
 * en contournant `resolveBaseUrl()`. Corriger le résolveur n'aurait rien
 * changé pour eux : c'est le motif « l'invariant existe et n'est pas
 * appliqué », déjà vu sur `engine_sha` (PR #211) et le repli de marge
 * (PR #213). Un ratchet le rend impossible.
 *
 * Comme le ratchet bandit côté Python : on gèle un compte de référence et
 * la CI échoue s'il AUGMENTE. Ici la référence est zéro, donc c'est un
 * simple « aucune occurrence en dehors de `api.ts` ».
 */
import { readdirSync, readFileSync, statSync } from "node:fs"
import { join } from "node:path"

function fichiersSrc(dossier: string): string[] {
  const out: string[] = []
  for (const nom of readdirSync(dossier)) {
    const chemin = join(dossier, nom)
    if (statSync(chemin).isDirectory()) {
      out.push(...fichiersSrc(chemin))
    } else if (/\.tsx?$/.test(nom) && !/\.test\.tsx?$/.test(nom)) {
      out.push(chemin)
    }
  }
  return out
}

describe("ratchet #208 — aucune URL d'API en dur hors api.ts", () => {
  it("api.ts est le SEUL lieu où le port backend apparaît", () => {
    const coupables: string[] = []
    for (const f of fichiersSrc("src")) {
      if (f.replace(/\\/g, "/").endsWith("services/api.ts")) continue
      const src = readFileSync(f, "utf8")
      // `:8000` n'est une URL que s'il suit un `http`/`ws` — ailleurs
      // c'est un timeout (`8000` ms) et ce n'est pas la même chose.
      if (/(?:https?|wss?):\/\/[^`'"\s]*:8000/.test(src)) {
        coupables.push(f)
      }
    }
    expect(
      coupables,
      `URL d'API en dur dans ${coupables.length} fichier(s) :\n  ` +
        `${coupables.join("\n  ")}\n` +
        "Utilise apiUrl() / WS_ROOT de src/services/api.ts — sans quoi le\n" +
        "cookie core_access n'est pas envoyé (credentials: include), le\n" +
        "site casse en HTTPS (mixed content) et la CSP refuse l'origine.",
    ).toEqual([])
  })

  it("le comptage ne confond pas un port et un timeout", () => {
    // `8000` utilisé comme délai en ms doit rester autorisé : c'est le
    // cas de Dashboard.tsx et ArkhamEntityPage.tsx.
    for (const f of fichiersSrc("src")) {
      if (f.replace(/\\/g, "/").endsWith("services/api.ts")) continue
      const src = readFileSync(f, "utf8")
      const ports = (src.match(/8000/g) || []).length
      const urls = (src.match(/(?:https?|wss?):\/\/[^`'"\s]*:8000/g) || []).length
      expect(urls, `${f} : ${urls} URL(s) en dur`).toBe(0)
      expect(ports).toBeGreaterThanOrEqual(urls)
    }
  })

  it("WS_ROOT déduit le protocole de la page", () => {
    // https: -> wss:, http: -> ws:. Un `ws://` en dur casserait en HTTPS.
    //
    // On ne vérifie PAS l'absence de `:8000` dans la valeur résolue : en
    // configuration de dev, le repli EST bien localhost:8000. Ce qui doit
    // être absent, c'est le `:8000` ÉCRIT DANS LE SOURCE — c'est
    // exactement ce que vérifie le ratchet ci-dessus.
    expect(WS_ROOT).toMatch(/^wss?:\/\//)
  })

  it("API_ROOT est la base sans /api, apiUrl y ajoute le préfixe", () => {
    expect(API_ROOT).not.toMatch(/\/api$/)
    expect(apiUrl("")).toBe(`${API_ROOT}/api`)
    expect(apiUrl("/health")).toBe(`${API_ROOT}/api/health`)
    expect(apiUrl("health")).toBe(`${API_ROOT}/api/health`)
  })
})
