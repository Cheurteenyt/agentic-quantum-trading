/**
 * r7 — deux défauts du dashboard vérifiés mécaniquement :
 *
 * 1. Le tri des signaux utilisait `localeCompare` — un tri ALPHABÉTIQUE
 *    ("critical" < "high" < "low" < "medium") : un signal LOW passait
 *    devant un MEDIUM sur le board. Le rang est métier, pas
 *    lexicographique.
 *
 * 2. WSContext : le cleanup appelait `close()` — qui déclenche
 *    `onclose` — qui re-programmait `setTimeout(connect, 3000)` jamais
 *    annulé. Après un démontage (navigation SPA, HMR, StrictMode
 *    double-mount), un WebSocket zombie était recréé toutes les 3 s sur
 *    un composant mort, indéfiniment.
 */
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest"
import { render } from "@testing-library/react"
import React from "react"
import { sortSignals } from "../hooks/useSignals"
import { WSProvider } from "../contexts/WSContext"
import type { Signal } from "../hooks/useSignals"

function sig(prio: Signal["priority"], ts: number, id: string): Signal {
  return { id, type: "whale", priority: prio, title: id, timestamp: ts }
}

class FakeWS {
  static instances: FakeWS[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  constructor(public url: string) {
    FakeWS.instances.push(this)
  }
  close() {
    this.onclose?.()
  }
}

beforeEach(() => {
  FakeWS.instances = []
  vi.stubGlobal("WebSocket", FakeWS as unknown as typeof WebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("sortSignals — le rang de priorité est métier", () => {
  it("medium passe devant low (l'ordre alphabétique disait l'inverse)", () => {
    const out = sortSignals([sig("low", 1, "a"), sig("medium", 2, "b")])
    expect(out.map(s => s.id)).toEqual(["b", "a"])
  })

  it("critical d'abord, low dernier", () => {
    const out = sortSignals([
      sig("low", 9, "l"),
      sig("critical", 9, "c"),
      sig("medium", 9, "m"),
      sig("high", 9, "h"),
    ])
    expect(out.map(s => s.priority)).toEqual(["critical", "high", "medium", "low"])
  })

  it("même priorité : le plus récent d'abord", () => {
    const out = sortSignals([
      sig("high", 100, "ancien"),
      sig("high", 200, "recent"),
    ])
    expect(out.map(s => s.id)).toEqual(["recent", "ancien"])
  })

  it("ne mute pas la liste d'entrée", () => {
    const base = [sig("low", 1, "a"), sig("critical", 2, "b")]
    sortSignals(base)
    expect(base.map(s => s.id)).toEqual(["a", "b"])
  })
})

describe("WSContext — plus de reconnexion zombie après unmount", () => {
  it("montage : une seule connexion", () => {
    vi.useFakeTimers()
    render(React.createElement(WSProvider, null, React.createElement("div")))
    expect(FakeWS.instances).toHaveLength(1)
  })

  it("unmount : aucun WebSocket zombie à 3 s", () => {
    vi.useFakeTimers()
    const { unmount } = render(
      React.createElement(WSProvider, null, React.createElement("div")))
    expect(FakeWS.instances).toHaveLength(1)
    unmount()                       // close() -> onclose() -> (bug : retry)
    vi.advanceTimersByTime(3000)
    vi.advanceTimersByTime(9000)
    expect(FakeWS.instances).toHaveLength(1)
  })

  it("circuit nominal inchangé : hors unmount, la reconnexion à 3 s marche", () => {
    vi.useFakeTimers()
    render(React.createElement(WSProvider, null, React.createElement("div")))
    expect(FakeWS.instances).toHaveLength(1)
    FakeWS.instances[0].onclose?.()   // perte de connexion (pas un unmount)
    vi.advanceTimersByTime(3000)
    expect(FakeWS.instances).toHaveLength(2)
  })
})
