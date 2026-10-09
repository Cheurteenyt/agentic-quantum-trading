/**
 * Ronde 8 — fausses infos d'API (front).
 *
 * - sortOpportunities : le merge préfixait les nouveaux items sans re-tri —
 *   après le 2e poll, un signal low fraîchement arrivé s'affichait au
 *   rang 01 au-dessus d'un critical (badge rank + « N live signals »
 *   menteurs). Même ordre que le backend (severity DESC, |avg_funding| DESC).
 * - Oracles source : Agents.tsx (res.ok ×3 + « ÉTAT INCONNU ») et
 *   AlphaLab.tsx (plus de prix fabriqué || 0.5).
 */
import { describe, it, expect } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"
import { sortOpportunities } from "../components/OpportunityFeed"

const opp = (severity: string, symbol: string, avgFunding?: number) => ({
  type: "funding",
  symbol,
  severity,
  details: avgFunding === undefined ? {} : { avg_funding: avgFunding },
})

describe("sortOpportunities — le rang affiché est un vrai classement", () => {
  it("le scénario exact du bug : critical préexistant reste en tête quand un low frais arrive", () => {
    const prev = [opp("critical", "BTCUSDT", 0.002)]
    const fresh = [opp("low", "PEPEUSDT", 0.0001)]
    const merged = sortOpportunities([...fresh, ...prev])
    expect(merged[0].symbol).toBe("BTCUSDT")
    expect(merged[1].symbol).toBe("PEPEUSDT")
  })

  it("ordre backend reproduit : severity DESC puis |avg_funding| DESC", () => {
    const rows = [
      opp("low", "A", 0.9),
      opp("medium", "B", 0.1),
      opp("high", "C", 0.0),
      opp("critical", "D", 0.0),
      opp("medium", "E", 0.5),
      opp("high", "F", 0.3),
    ]
    expect(sortOpportunities(rows).map((r) => r.symbol)).toEqual(["D", "F", "C", "E", "B", "A"])
  })

  it("details sans avg_funding : pas de crash, tie-break neutre", () => {
    const rows = [opp("high", "A"), opp("high", "B")]
    const sorted = sortOpportunities(rows)
    expect(sorted.map((r) => r.symbol).sort()).toEqual(["A", "B"])
  })

  it("sévérité inconnue/absente : rang 0, jamais devant une sévérité connue", () => {
    const rows = [opp("critical", "BTC"), opp("", "X"), opp("low", "L")]
    expect(sortOpportunities(rows)[0].symbol).toBe("BTC")
    expect(sortOpportunities(rows)[2].symbol).toBe("X")
  })

  it("ne mute pas l'entrée (copie triée)", () => {
    const rows = [opp("low", "A"), opp("critical", "B")]
    sortOpportunities(rows)
    expect(rows[0].symbol).toBe("A")
  })
})

describe("oracles source — l'état faux ne peut pas revenir en silence", () => {
  const read = (p: string) => readFileSync(join(process.cwd(), "src", p), "utf-8")

  it("Agents.tsx : 3 checks res.ok + badge ÉTAT INCONNU", () => {
    const src = read("pages/Agents.tsx")
    expect(src.match(/if \(!r\.ok\)/g)?.length).toBe(3)
    expect(src).toContain("ÉTAT INCONNU")
  })

  it("AlphaLab.tsx : plus de prix d'entrée fabriqué", () => {
    const src = read("pages/AlphaLab.tsx")
    expect(src).not.toContain("|| 0.5")
    expect(src).toContain("simulation impossible")
  })

  it("OpportunityFeed.tsx : le merge passe par le tri", () => {
    const src = read("components/OpportunityFeed.tsx")
    expect(src).toContain("sortOpportunities([...fresh, ...prev])")
  })
})
