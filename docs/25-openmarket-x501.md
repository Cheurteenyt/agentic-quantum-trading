# 25 · OPENMARKET x501 — LA MISSION, LES CHIFFRES, LA DOCTRINE

> **domain: OPENMARKET** · index : [`openmarket/README.md`](openmarket/README.md) · reports : `reports/openmarket/`
>
> Créé le 30/09/2026. Doc maître du domaine OpenMarket.
> Les données : `docs/26-openmarket-donnees.md`. Les livrables : `docs/reference/openmarket-x501/`.
> Le code : `scripts/studies/x501_openmarket/`.

## LA MISSION

Partir de **100 $** sur openmarket.xyz et atteindre **50 100 $** en 12 mois
(**×501**), sous **DDmax ≤ 25 %**, capital fixe, **zéro ordre autonome**.
Doctrine = même que le registre Aster : pré-enregistrer avant de croire.

## LES CHIFFRES OFFICIELS (MC v20 — 12 000 trajectoires, SANS haircut gate)

| Scénario | Coût/côté | Médiane 12 m | P(≥ 250 $) | x501 @ 36 m |
|---|---|---|---|---|
| S0 référence | 0,0 bps | 642,0 $ | 80,1 % | 35,7 % |
| **MAKER δ=2 central** | **2,1 bps** | **468,4 $** | **73,0 %** | **21,3 %** |
| MAKER pur | 2,0 bps | 475,4 $ | 73,3 % | 21,8 % |
| MAKER stress fill 90 % | 3,0 bps | 412,9 $ | 69,8 % | 16,4 % |
| TAKER all-in | 6,1 bps | 272,7 $ | 57,2 % | 5,8 % |

**+71,8 % de médiane maker vs taker.** Fill maker δ=2 mesuré 97,9 % (méthodo reconstructible `docs/29`).

> ⚠ **Review fill (`docs/29`)** : mesure pool P1 réfute l'hypothèse d'entrée v20
> (delta réel +0,375 bps à δ=2/TTL=2, fallback adverse). Candidat v21 : médiane
> **306,2 $** (TTL=2) / **364,0 $** (TTL=6). **Officiel = v20** tant que review non validée.

## RÈGLE DES COÛTS

Chaque **+2 bps/côté ≈ −20 à −28 % de médiane 12 m**. Priorité = réduire le coût
d'exécution avant d'ajouter un signal. Seuil de promotion de filtre ≈ gain > 2 bps/côté.

## FALSIFICATIONS (portes fermées)

1. Funding z-score gate — KILL (−22 bps)
2. Flush OI — KILL (double comptage)
3. ML 11 features — KILL (AUC ~0,50)
4. Flux/funding banc local (`docs/30`) — 12/12 KILL
5. Absorption proxy klines (`docs/31`) — ABS_DEPRIORISE
6. Refs liquidité vwap/VP (`docs/32`) — famille analyse CLOSE
7–9. OI continuation / régime / U (`docs/33–35`) — falsifications + 2 candidats marginaux purge
10. LSR (`docs/36`) — 10ᵉ falsification

Détail dans chaque doc 30–36. Critère promotion scorer : AUC temporel ≥ 0,60 sur 60 j frais — jamais atteint.

## ARTEFACTS

- kScripts + QA : `scripts/studies/x501_openmarket/`
- Pouvoirs : `docs/27` (**40/53 = 75,5 %**)
- Protocole A/B : `docs/28`
- Fill maker : `docs/29`
- Baseline : `reports/openmarket/x501-baseline-2026-10-01.md`

## PIVOT 30/09

R&D prioritaire OpenMarket. Collecteurs Aster/FOMO continuent. Nouvelles études
Aster/FOMO via `docs/lab/` avec `domain:` explicite.

## RÈGLES NON NÉGOCIABLES

- Aucun ordre autonome
- Pré-enregistrement avant de croire (`docs/03`)
- Papier / preuve live avant capital réel
- On ne supprime pas — on archive avec verdict
- **domain OPENMARKET only** — pas de mélange avec the_machine
