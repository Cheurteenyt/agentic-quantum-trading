with open("D:/trading-agent/frontend/src/pages/AlphaLab.tsx", "r", encoding="utf-8") as f:
    c = f.read()

# Fix: add padding wrapper around WalletAnalyzer
old = "          <WalletAnalyzer />"
new = "          <div style={{ padding: '16px 20px' }}>\n            <WalletAnalyzer />\n          </div>"

c = c.replace(old, new)

with open("D:/trading-agent/frontend/src/pages/AlphaLab.tsx", "w", encoding="utf-8") as f:
    f.write(c)
print("Added padding wrapper")

