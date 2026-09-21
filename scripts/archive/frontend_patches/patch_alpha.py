with open("D:/trading-agent/frontend/src/pages/AlphaLab.tsx", "r", encoding="utf-8") as f:
    c = f.read()

# Add import
if "WalletAnalyzer" not in c:
    c = c.replace(
        'import { getExplorerAddressUrl, getExplorerTxUrl } from "../services/explorerLinks"',
        'import { getExplorerAddressUrl, getExplorerTxUrl } from "../services/explorerLinks"\nimport WalletAnalyzer from "../components/WalletAnalyzer"'
    )

# Add WalletAnalyzer section after hero section
hero_end = """      </section>

      <section className="alpha-metric-grid">"""

wallet_section = """      </section>

      {/* Wallet Analyzer */}
      <section className="alpha-grid">
        <div className="alpha-panel alpha-panel-large">
          <div className="alpha-panel-header">
            <div>
              <div className="alpha-panel-title">Wallet Analyzer</div>
              <div className="alpha-panel-subtitle">On-chain wallet analysis across BSC, ETH, and Solana. Balance, transactions, swaps, volume, and smart labels.</div>
            </div>
          </div>
          <WalletAnalyzer />
        </div>
      </section>

      <section className="alpha-metric-grid">"""

c = c.replace(hero_end, wallet_section)

with open("D:/trading-agent/frontend/src/pages/AlphaLab.tsx", "w", encoding="utf-8") as f:
    f.write(c)

print("AlphaLab.tsx patched")

