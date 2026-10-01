# 26 · OPENMARKET — LES DONNÉES (l'entrepôt om_v27)

> **domain: OPENMARKET** · index data : [`data/README.md`](data/README.md)  
> Chiffres de recherche : `docs/25-openmarket-x501.md`.

## L'ENTREPÔT (om_v27.db — local, git-ignoré)

Un entrepôt SQLite domaine x501 : **12 symboles** perp USDT de base, panel
élargi **80 symboles** en CSV `data_x501/` (git-ignoré).

| Série | Granularité | Profondeur | Notes |
|---|---|---|---|
| Klines OHLCV | 1 h | 733 j (om) / **1 092 j** (panel 80) | 0 gap panel |
| Open Interest | 1 h | 708 j+ | bancs 33–35 |
| Open Interest | 1 j | depuis 2020 | contexte régime |
| Funding Binance | 8 h | 3,4–5,5 ans | banc 30 |
| Funding Bybit | 8 h | 66 j | cohérence cross-ex seulement |
| LSR | 4 h | **~2,74 ans** (collecteur v11) | banc 36 KILL |

## AUDIT VERT (v27)

1. **226 800 doublons** purgés + index UNIQUE `(symbol, ts)`
2. Sémantique OI 1 j Bybit : timestamp = **ouverture** (pas clôture)
3. Fenêtres réelles documentées (pas d'angle mort caché)

## BANDES DE COÛTS

- Taker **6,1 bps/côté** · Maker **2 bps/côté** (δ=2)
- Aucun chiffre de perf sans bande

## ANGLES MORTS

- Funding Bybit court → pas de signal autonome
- OI 1 j pré-2024 → contexte seulement
- LSR : était 8 j → étendu et **banc-testé KILL** (`docs/36`)

## BANC-TESTÉ (requalification)

| Série / famille | Doc | Statut |
|---|---|---|
| Flux taker + funding continus | 30 | mesuré fermé (KILL) |
| Absorption proxy klines | 31 | fermé / ABS_DEPRIORISE |
| OI continuation 1h | 33 | 10/10 KILL |
| OI régime / U | 34–35 | falsifié + candidats marginaux purge |
| LSR | 36 | 10ᵉ falsification |

Re-test = hypothèse **nouvelle** pré-enregistrée au registre — pas un re-run de curiosité.

Orderbook réel (`maxBidAmount`) : juge = protocole A/B (`docs/28`), pas ces bancs klines.
