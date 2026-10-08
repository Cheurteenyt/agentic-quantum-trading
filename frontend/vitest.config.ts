import { defineConfig } from "vitest/config"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Le CI doit être VERT ou ROUGE, jamais « skippé ». Un test qui ne
    // tourne pas est un oracle absent, pas un oracle vert.
    passWithNoTests: false,
  },
})
