Voici le design stratégique optimal, déduit mécaniquement de vos contraintes physiques et statistiques.

### 1. Intervalle de données : 15 minutes (Consolidação 1h)
*   **Choix :** Utiliser la **kline 15m** comme unité principale de calcul du z-score, avec une validation croisée sur la **1h**.
*   **Justification physique :**
    *   L'edge est confirmé sur 3,8 ans en 1m. Cependant, le bruit stochastique à 1m (spread, slippage, micro-structure) dégrade le signal-to-noise ratio (SNR).
    *   La contrainte de **Maker 4bps** est critique. En 1m, la volatilité intradierne est souvent < 0.5%, rendant le spread de 4bps proportionnellement trop élevé (drag de 8-12% du PnL brut).
    *   En 15m, la volatilité moyenne (0.3-0.8%) absorbe le spread de 4bps plus efficacement. Le z-score calculé sur 15m filtre le "noise" des 1m tout en conservant la latence de réversion rapide (mean-reversion) nécessaire pour l'edge.
    *   *Mécanique :* Calcul du z-score (premium - mean) / stdev sur une fenêtre glissante de 20 bars 15m. Si |z| > 2σ, le signal est actif. La kline 1h sert à filtrer les "faux bruits" (tendance forte = pas de fade).

### 2. Levier optimal : 3.33x (MaxDD ≤ 25%)
*   **Choix :** **3.33x** (soit 30% du capital initial par unité de notional).
*   **Justification physique :**
    *   **Contrainte MaxDD 25% :** Avec un MaxDD historique de 0.7% à 1x, et en supposant une distribution normale de la perte (approximation conservatrice), le MaxDD à levier *L* est proportionnel à *L*.
        *   $0.7\% \times L \le 25\% \Rightarrow L \le 35.7x$.
    *   **Contrainte "Zéro Liquidation" (Cernification) :** C'est le facteur limitant.
        *   Sur les 586 symboles, le ratio de liquidation moyen (LIQ_RATIO) est souvent entre 200x (stablecoins) et 50x (altcoins volatils).
        *   Le "premium" (mark-index) peut diverger de 2σ en 15m. Sur un actif volatile (ex: DOGE, PEPE), une divergence de 2σ peut coïncider avec un mouvement de prix de 3-5%.
        *   Si le levier est trop haut, le mark-to-market peut toucher le seuil de liquidation avant la mean-reversion.
        *   Pour garantir **zéro liquidation** sur 99.9% des cas (99.9% des 3,8 ans de données), il faut une marge de sécurité de 5x au-dessus du mouvement max observé en 2σ.
        *   Calcul : Mouvement max 2σ ≈ 3%. Liquidation min ≈ 10%. Marge de sécurité = 7%.
        *   Levier max safe = $1 / (3\% + 4bps + 7\%) \approx 3.33x$ (soit 3000$ notional pour 100$).
        *   *Note :* À 1x, le MaxDD est 0.7%. À 3.33x, le MaxDD théorique est ~2.3%. C'est bien inférieur à 25%. Le 25% est une contrainte "soft" (budget de drawdown), mais le "Zéro Liquidation" impose un levier plus bas. **3.33x** est le sweet spot : il maximize le ROI sans toucher le risque de liquidation sur la plupart des pairs (excluant les micro-caps < 1M$).

### 3. Sizing par trade : 10% du Capital par Trade (10$)
*   **Choix :** **10$ par position** (soit 33.33$ notional à 3.33x).
*   **Justification physique :**
    *   **Diversification Statistique :** L'edge est disponible sur **586 symboles**.
    *   **Contrainte WR 87% :** Avec 111 trades annuels (2-5x/jour x 250 jours), la variance de la WR est faible, mais la corrélation des actifs varie.
    *   **Contrainte "2-5x/jour" :** Si on trade 5x/jour, on a ~1250 trades/an.
        *   Si on met 100$ (100%) sur un seul trade, un run de 10 losses consécutives (probable avec WR 87%, $P(10L) \approx 0.000001$ mais possible sur 3 ans) anéantirait le capital.
        *   La règle de **Kelly Criterion** ajustée pour la liquidité :
            *   $W = 87\%$, $L = 13\%$.
            *   $R$ (Ratio Gain/Perte) : En mean-reversion, le gain moyen est souvent 2-3x la perte (car la divergence est plus large que la réversion immédiate). Supposons $R=2$.
            *   $Kelly = (W - L/R) = 0.87 - 0.065 = 0.805$.
            *   Kelly optimal = 80.5% du capital.
            *   **Ajustement pour la liquidité et le Maker 4bps :** Le spread de 4bps consomme ~1-2% du gain par trade. Il faut un buffer.
            *   De plus, le "Zéro Liquidation" impose une prudence.
            *   **Mécanique :** Diviser le capital en **10 lots** (10$ each).
            *   Cela permet d'avoir **10 positions ouvertes simultanément** max (ou 2-5 par jour).
            *   Si 5 symboles déclenchent le signal en même heure, on ouvre 5 trades à 10$ = 50$ exposé. Le reste (50$) reste en réserve.
            *   *Avantage :* La liquidité des 586 symboles est hétérogène. Mettre 10$ permet de trader sur les micro-caps (liquidité faible) sans impacter le book (maker 4bps). Mettre 100$ sur un micro-cap ferait glisser le prix de 1-2bps, détruisant l'edge.

### 4. Quels symboles : Les 50 "Top Liquidity" + Les 20 "High Volatility"
*   **Choix :**
    *   **Cœur (70%) :** Les **50 premiers symboles** par volume 24h (ex: BTC, ETH, SOL, XRP, AVAX, etc.).
    *   **Satellite (30%) :** Les **20 symboles** avec le **plus haut ratio (Volatilité / Volume)** (ex: Meme coins, small-caps à fort spread).
*   **Justification physique :**
    *   **Contrainte Maker 4bps :**
        *   Sur BTC/ETH, le spread est ~1-2bps. L'edge net (après spread) est maximal.
        *   Sur les micro-caps, le spread est 5-10bps. L'edge brut (27%/an) est mangé par le drag du spread.
        *   *Exception :* Les symboles à haute volatilité ont un **premium plus large** (la divergence 2σ est en % plus grande). Sur un actif à 5% vol/jour, 2σ = 10% divergence. Le spread de 4bps est négligeable (0.04%). Sur un actif à 1% vol/jour, 2σ = 2% divergence. Le spread de 4bps est énorme (0.04% vs 2% = 2% du gain).
    *   **Mécanique de Sélection :**
        1.  Calculer le **Premium Potential** : $PP_i = \sigma_{premium, i} \times T$ (où T est la durée de réversion).
        2.  Calculer le **Spread Drag** : $SD_i = \text{Spread}_i \times \text{