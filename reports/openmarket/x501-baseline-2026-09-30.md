# openmarket-x501-baseline — 30/09/2026 (ÉDITION SUPPLANTÉE)

> **Lue le 01/10 ? Aller à `openmarket-x501-baseline-2026-10-01.md`** (MC v20,
> sans haircut gate — les chiffres ci-dessous sont l'édition v18, conservée
> pour la trace). On ne supprime pas, on re-catégorise.

Baseline de référence du domaine OpenMarket au jour de son intégration dans
le repo. Chiffres figés ici = l'état officiel avant MC v20 (prochaine mise
à jour programmée). Méthode et doctrine : `docs/25-openmarket-x501.md`,
données : `docs/26-openmarket-donnees.md`.

## Les chiffres officiels (MC v18, 12 000 trajectoires)

- **V1 taker** (6,1 bps/côté) : médiane 12 m **216 $**.
- **V1 maker** (δ=2, 2 bps/côté, fill 97,9 %) : médiane 12 m **475 $**,
  **P(≥ 250 $) = 80 %** — plan de référence.
- V2 : **1 012 $** (92,5 %) · V3 : **2 353 $** (98,7 %, DD mesuré 22,09 %).
- V4 = borne sup théorique 38 991 $ (**pas un plan**) · V5 stress : **215,7 $**.
- Cible ×501 complète : **96,5 % des trajectoires à 36 mois**.
- Règle empirique v18 : **−2 bps de coût/côté ≈ +25 % de médiane**.

## Les portes falsifiées (état définitif)

- funding z-score < −1,5 (blocage SHORT) : **−22,0 bps** → KILL.
- flush OI (ΔOI 6 h ≤ −4,5 %, dédup 24 h) : **+0,1/+0,2 bps**
  (5 576 events bruts / +46,1 bps = double comptage) → KILL.
- ML 11 features : **AUC 0,4994** (tri global par ts) ; plis roulants
  0,483 / 0,533 / 0,488 / 0,471 ; le 0,56–0,57 initial était un split
  inter-symboles → promotion annulée. Critère de promotion : AUC ≥ 0,60
  sur 60 j frais, jamais atteint.

## L'état du code (vérifié à l'intégration)

- 9 kScripts + scanner : QA générale **PASS**, scanner **PASS** (49
  contrôles), maker **PASS** (M1–M15), observation **PASS** (13/fichier).
- Entrepôt om_v27 : audit vert (226 800 doublons purgés, index UNIQUE
  `(symbol, ts)`, sémantique OI 1 j Bybit corrigée).

## Les 4 prochains jalons (dans l'ordre)

1. MC v20 — 12 000 trajectoires V1 **sans haircut gate**, bandes
   {taker 6,1 ; maker 2} → cette baseline est re-éditée.
2. Suivi de fill réel des `_MK` en papier (compteurs mkFills/mkFb/mkTOut/mkInv).
3. Preuve live 90 j (protocole v11, 4 relevés/jour).
4. Re-édition de cette baseline + table des docs 25 si MC v20 déplace les médianes.
