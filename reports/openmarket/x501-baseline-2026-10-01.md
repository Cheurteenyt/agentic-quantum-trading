# openmarket-x501-baseline — 01/10/2026 (édition MC v20)

Baseline de référence du domaine OpenMarket après **MC v20** (sans haircut
gate). Supplanté l'édition du 30/09 (chiffres v18 avec gate). Méthode et
doctrine : `docs/25-openmarket-x501.md` · données : `docs/26` · pouvoirs :
`docs/27-pouvoirs-kscript.md`.

## Les chiffres officiels (MC v20 : 12 000 trajectoires, 5 scénarios, 4 audits verts)

- **S0 référence certifiée** (0 bps) : médiane 642,0 $ — T0 : 641,99 $ bit à bit.
- **V1 maker δ=2 central** (2,1 bps/côté, fill 97,9 %) : médiane 12 m
  **468,4 $**, **P(≥ 250 $) = 73,0 %**, P(500) 50,4 %, P(1 250) 25,3 %.
- MAKER pur (2,0) : 475,4 $ · MAKER stress (3,0, fill 90 %) : 412,9 $.
- **V1 taker all-in** (6,1 bps/côté) : médiane 12 m **272,7 $**, P(250) 57,2 %.
- **Gain maker vs taker : +71,8 % de médiane** ; x501 complet @ 36 m :
  **21,3 % vs 5,8 %**.
- Garde-fous : 0 rupture de cap sur 60 000 trajectoires, DD max 25,0000 %
  (cap respectée au bit près), DD médian 24,93–25,00 % (ratchet calé contre
  la borne par design).

## Ce qui a changé vs l'édition 30/09 (v18)

Le haircut gate (falsifié avec les 2 autres variantes du gate précis) ne
retranche plus rien : le taker monte de 216 $ à 272,7 $ (+26 %) — le gate
coûtait ~26 % de médiane — le maker reste ~468–475 $ (−1,4 %, bruit).
La règle empirique des coûts tient : +4 bps/côté = −41,8 % de médiane
(v20), soit ≈ −20 à −28 % par tranche de +2 bps.

## Le diagnostic « pouvoirs » (nouveau, 01/10)

Audit d'exploitation du kScript (53 capacités sourcées des 78 pages de doc,
testées contre les 10 scripts) : **28/53 = 52,8 % exploité**. Le trou n'est
pas le broker (11/16) mais **la data : 1/8 sur les sources premium** —
`etf_flow/etf_holding/etf_premium_rate`, `cme_oi`, `deribit_implied_
volatility/volatility_index`, `options_oi/options_volume/skew`,
`long_short_ratio`, `binance_treasury_balance`, `ethena_positions` — et
l'orderbook natif (`maxBidAmount/maxAskAmount`) à 0. Plan d'activation en
3 vagues : `docs/27-pouvoirs-kscript.md`.

## Les 4 prochains jalons (dans l'ordre)

1. Vague 1 du registre des pouvoirs : filtre de régime institutionnel
   (ETF flow × skew × vol Deribit × CME OI) — pré-enregistré, falsifié sur
   733 j avant promotion.
2. Vague 2 : absorption orderbook native (`maxBidAmount`/`sumBids/sumAsks`).
3. Suivi de fill réel des `_MK` en papier (mkFills/mkFb/mkTOut/mkInv) puis
   preuve live 90 j (protocole v11, 4 relevés/jour).
4. Re-édition de cette baseline si une vague déplace les médianes.
