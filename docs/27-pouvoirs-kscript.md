# 27 · POUVOIRS kScript — LE REGISTRE D'EXPLOITATION

> Créé le 01/10/2026. Réponse chiffrée au diagnostic : « tu as des outils
> puissants gratuits par rapport à TradingView, tu n'exploites aucun pouvoir ».
> Méthode reproductible : `scripts/studies/x501_openmarket/x501_exploit_audit.py`
> (chaque capacité sourcée des 78 pages de doc scrapée, testée contre nos 10 scripts).

## LE VERDICT GLOBAL

**28/53 capacités exploitées = 52,8 %** — sur les 53 pouvoirs du langage
identifiés dans la doc officielle (quick-reference + 78 pages), nos 9
kScripts + le scanner en utilisent 28. Le cœur broker perps est bien
exploité (11/16 : `instrument="perps"`, `leverage`, `makerFeePercent`/
`takerFeePercent`, `funding="data"`, `onLiquidation`, `pyramiding`,
`slippageModel`, `closeAll`, getters d'équité — 8/10 scripts), les alertes
et la lib TA aussi. **Le trou est la data** : la famille « sources
premium » est à **1/8**, l'orderbook à 1/3, les sorties broker avancées à
0. Détail par famille :

| Famille | Exploité | Verdict |
|---|---|---|
| alertes | 2/2 | complet |
| données (sources/TF) | 7/9 | bon |
| broker (exécution) | 11/16 | bon, sorties avancées à 0 |
| analyse (TA/CVD/sessions) | 3/5 | acceptable |
| orderbook (depth native) | 1/3 | **le pattern gagnant d'Aster, dormant** |
| sources premium (institutionnelles) | 1/8 | **le scandale** |
| langage (collections/loops/libraries) | 2/8 | dette de style, pas d'edge |
| visu | 1/2 | mineur |

## LES 7 FLUX INSTITUTIONNELS GRATUITS (0 usage — TradingView les facture)

La page `core-concepts/data-sources` liste les flux que `source()` charge
directement dans un kScript, sans API externe, sans clé, inclus dans le
backtester gratuit. Nos scripts n'en consomment que 3 (`funding_rate`,
`liquidations`, `open_interest`) + `buy_sell_volume` dans 1 script. Les 7
restants :

1. **`etf_flow` / `etf_holding` / `etf_premium_rate`** — la pression ETF
   BTC/ETH au quotidien : le moteur du régime 2024-2026, absent de nos
   filtres de régime.
2. **`cme_oi`** — l'open interest CME : les institutionnels, notre meilleur
   proxy de « smart money » structurel.
3. **`deribit_implied_volatility` / `deribit_volatility_index`** — le VIX
   crypto : le régime de vol que le regime_filter cherche à deviner depuis
   les bougies.
4. **`options_open_interest` / `options_volume` / `skew`** — le skew
   d'options : la position du marché sur la direction, en avance sur le
   spot.
5. **`long_short_ratio`** — le LSR : on en avait collecté 8 jours à la main
   (angle mort documenté dans `docs/26-openmarket-donnees.md`)… il est
   NATIF. L'angle mort disparaît.
6. **`binance_treasury_balance`** — la trésorerie Binance : pression
   structurelle d'échange.
7. **`ethena_positions`** — le carry USDe : le flux de financement
   structurel.

## L'ORDERBOOK NATIF (le pattern qui a rapporté sur Aster)

Sur Aster, la data premium qui a fait la différence était le carnet
d'ordres : `depth.db` (54 M bins, 30 s, 15 symboles), `wall_detector.py`,
`aster_absorption.py`. kScript embarque la même couche **en natif** :
`sumBids`/`sumAsks` (pression par profondeur `depthPct`), et surtout
`maxBidAmount`/`maxAskAmount` — **la détection des baleines dans le
carnet, une ligne, dans le backtest**. Usage actuel : `sumBids/sumAsks`
dans 1 script sur 10, les max/min amounts nulle part. C'est la vague 2 du
plan ci-dessous.

## LES 4 SORTIES BROKER DORMANTES (broker 16 − 11)

`strategy.exit(profit=/loss=)` (brackets 1 ligne), **`trailPoints=`/
`trailOffset=`** (trailing stop NATIF — le `_MK` code sa sortie à la main),
`ocaName=` (brackets OCA), `strategy.cancelAll()`, et les stats natives
`strategy.maxDrawdown()`/`closedTradeCount()` (les rapports de preuve live
re-calculent à la main ce que le broker simulé fournit).

## LE PLAN D'ACTIVATION (3 vagues, ordre d'impact sur la médiane)

**Vague 1 — le régime institutionnel (impact max, effort min).** Un filtre
de régime composite branché sur les sources premium : ETF flow (3 j) ×
skew options × vol Deribit × CME OI. Testé comme le régime BTC du domaine
Aster (le quadrant à éviter/à chercher), pré-enregistré, falsifié sur 733 j
de klines avant promotion. Chaque −X % de trades perdus dans le mauvais
régime vaut, à la règle des coûts (`docs/25`), plusieurs bps/côté.

**Vague 2 — l'absorption native.** `maxBidAmount/maxAskAmount` +
`sumBids/sumAsks` à depthPct 1–5 % : l'alpha absorption (le mur qui tient =
soutien) testé en one-shot `scripts/studies/`, avec la même discipline que
la vague 1. Sur Aster, c'est la famille qui a produit l'AL Score et le
profil qualité (WR 81 %, DD 5,4 %).

**Vague 3 — l'hygiène d'exécution.** `trailPoints` dans les `_MK` (sortie
native, moins de code, moins de bugs), `ocaName` pour les brackets,
`strategy.maxDrawdown()` dans les rapports, `cancelAll` à l'invalidation.
Aucun edge espéré ici — de la robustesse et de la lisibilité, qui réduisent
le risque de bug du harnais (la leçon T7 d'Aster).

La règle de promotion ne change pas d'un iota : tout candidat passe par le
backtest pré-enregistré (méthode `docs/03-methodology.md`), le registre
(`docs/20-registre-indicateurs.md`) reçoit le verdict chiffré, et le papier
forward reste le juge. Exploiter les pouvoirs ne veut PAS dire croire plus
vite — ça veut dire tester plus de portes, avec la même clé.
