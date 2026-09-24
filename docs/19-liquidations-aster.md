# Mécanique des LIQUIDATIONS sur Aster — étude du 24/09/2026

> Sources : doc officielle V3 (api-docs, 7 000 lignes) + exchangeInfo public +
> notre harnais v5. Tout est vérifié empiriquement sauf mention contraire.

## 1. Comment Aster liquide vraiment (formule réelle)

Liquidation quand la marge restante ≤ marge de maintenance :

```
mouvement adverse qui liquide = 100/levier − maintMarginPercent   (en %)
```

- `maintMarginPercent` **par symbole**, public dans exchangeInfo (607 symboles
  extraits → `klines.db:liq_params`) ;
- Exemple PONSUSDT : maint 16,66 %, requiredMargin 33,33 % → **levier max 3x**,
  liquidation à **100/3 − 16,66 = 16,67 %** adverse ;
- BTC : maint 2,5 %, levier max 20x → liquidation à 100/20 − 2,5 = 2,5 % adverse ;
- Les paliers fins (brackets par notional avec `cum`) : `GET /fapi/v3/leverageBrackets`
  — **USER_DATA, signature obligatoire** (testé : erreur -1102 sans signature).

## 2. Les paramètres qui changent tout (réels, publics)

| Symbole | Levier max | Maint % | LiquidationFee | marketTakeBound |
|---|---|---|---|---|
| PONSUSDT | **3x** | 16,66 | **2,5 %** | **10 %** |
| CATEUSDT | **3x** | 16,66 | 2,5 % | 10 % |
| MEMEUSDT | **3x** | 16,66 | 2,5 % | 10 % |
| ASTERUSDT | 4x | 12,5 | 2,5 % | 5 % |
| BTCUSDT | 20x | 2,5 | 2,5 % | 2 % |
| WIFUSDT | 20x | 2,5 | 2,5 % | 10 % |

Deux bombes dans ces chiffres :
1. **Nos memecoins vedettes sont plafonnés à 3x** — toute stratégie qui
   implique plus n'existe pas ;
2. `liquidationFee 2,5 %` : se faire liquider coûte la marge + 2,5 %.

## 3. Ce que ça change dans NOS backtests (mesuré, pas théorique)

La table de liquidation du harnais utilise maintenant ces paramètres réels
(seuil = 100/L − maint, levier plafonné par symbole, dénominateur = trades
réellement tradeables à ce levier) :

- **funding_prix_divergence_short +12h : 2,1 % de liquidation à 3x, 0 % à
  5x/10x** — un trade de 12h n'a pas le temps d'excursionner à -16 % ;
- funding_extreme +7j : 3 % à 3x, 5 % à 5x, 26 % à 10x — tradeable en 3-5x ;
- **les shorts tenus 30-90 jours : 27-50 % de liquidation DÈS 3x** — morts en
  pratique, même au-dessus du drift. Le short 90 jours n'est pas une
  stratégie, c'est une loterie directionnelle avec une poudre au bout.

## 4. Pièges de données découverts dans la doc

- **Les trades du fonds d'assurance et de l'ADL ne figurent PAS dans les
  trades/klines** → pendant les cascades, nos données de volume
  sous-comptent l'activité réelle ;
- `marketTakeBound` (10 % sur PONS) : un ordre marché ne peut pas dévier de
  plus de 10 % du mark **par ordre** — les pires trades de nos backtests
  (-11 000 %) sont des enchaînements de bougies, pas un seul gap ;
- **ADL quantile** (`GET /fapi/v3/adlQuantile`, USER_DATA) : 0-4 par position —
  le risque de délevage automatique de TON compte sera trackable quand la
  clé privée sera en place ;
- Les flux de liquidation (`!forceOrder@arr`) ne poussent qu'1 snapshot par
  seconde par symbole — notre collecteur sous-compte les cascades ultra-rapides.

## 5. Ce qui reste à faire (quand la clé privée API wallet sera fournie)

1. `leverageBrackets` réels par symbole (paliers fins, au-delà du 1er bracket) ;
2. `adlQuantile` de notre compte → tracking du risque de délevage ;
3. Solde et positions réels dans le radar ;
4. Backtest des cascades de liquidation quand `liq_events` aura ~3 semaines.

## 6. Notre modèle dans le harnais (implémenté)

```
liqué(levier L, symbole s) si |excursion adverse| ≥ 100/L − maintMarginPercent(s)
L plafonné à max_leverage(s) ; sinon le trade n'est pas tradeable à L
```
Validé sur données synthétiques par le selftest du harnais à chaque run.
