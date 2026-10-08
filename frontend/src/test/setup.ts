import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach, beforeAll } from "vitest"

// React 18 exige que les mises à jour d'état déclenchées hors de
// l'évènement utilisateur soient enveloppées dans `act()`. Sans ce
// drapeau, testing-library n'enveloppe PAS le flush des promesses, et
// `waitFor` lève « An update to <X> inside a test was not wrapped in
// act(...) ». Symptôme trompeur : le hook fonctionne réellement
// (`loading` retombe bien à `false`) mais le test échoue sur l'avertissement
// transformé en erreur.
beforeAll(() => {
  // @ts-expect-error — drapeau global React, pas typé par React 18
  globalThis.IS_REACT_ACT_ENVIRONMENT = true
})

afterEach(() => {
  cleanup()
})