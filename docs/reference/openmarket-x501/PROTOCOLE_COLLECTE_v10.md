# OPÉRATION x501 — PROTOCOLE DE COLLECTE LIVE v10 (30 jours)

## 1. Pourquoi cette collecte

La campagne v9 a clos le chantier « edge extractible des historiques publics »
: 12 leviers testés (B1-B5, B6, B7a/b, B8v1/v2, extension 79 perps, L3), 0
retenu. Le levier le plus crédible restant (B6 « Absorption CVD multi-venues »)
a été FALSIFIÉ sur des données Binance-only — il n'a jamais pu être testé sur
les données qu'il requiert (flux des autres venues). openmarket.xyz expose ces
données en natif via kScript (`source(type="buy_sell_volume")` sur 4 venues,
`trade_volume_by_size` par taille d'ordre, carnet `source("orderbook")`).
La v10 installe donc la COLLECTE : 30 jours de journalisation live avant tout
re-test, pour que le prochain verdict soit mesuré sur des données réelles et
non simulées.

## 2. Déploiement (zéro risque)

| Script | Charts | Ce qu'il journalise | Ordres |
|---|---|---|---|
| `x501_observe_flow_H1.ks` | les 40 charts du déploiement (2 premium 1h + 38 satellites 4h, TF H1) | whale/retail delta (buckets ≥500K$/<10K$), carnet 5 %, funding, ATR%BTC D1, tendance BTC D1 | AUCUN |
| `x501_observe_cvd4_btc_H1.ks` | 1 chart BTC | delta H1 par venue : Binance spot, Binance perp, Bybit perp, OKX perp (+ total, + divergence spot-perp) | AUCUN |

Procédure par chart : coller le script → créer l'alerte sur la condition du
collecteur → régler la fréquence « une fois par clôture de bougie » → router
vers le journal (webhook/e-mail de la plateforme). Aucun `strategy.*` dans les
deux scripts (vérifié par QA statique : `scripts/qa_observe_x501.py`, 13/13
contrôles par fichier) : la collecte n'interfère avec AUCUN trade du déploiement.

## 3. Format des lignes

```
X501OBS|SYMBOL|whale=…|retail=…|net=…|book=…|fund=…|atrBTC=…|trend=…
X501CVD|BTCUSDT|spot=…|perpB=…|perpY=…|perpO=…|total=…|spotperp=…|live=…
```
Chaque alerte est horodatée par la plateforme : ligne finale =
`<timestamp_iso>,<message>`. Journalisation sur bougie FERMÉE (séries lues à
l'index [1], anti-repaint par construction).

## 4. Volume attendu

- OBS : 40 charts × 24 bougies H1/jour ≈ **960 lignes/jour** (~29 000 en 30 j).
- CVD : 1 × 24 lignes/jour ≈ 720 lignes en 30 j.
- Budget disque : < 5 Mo. Aucune maintenance requise pendant 30 jours.

## 5. Exploitation (J+30) — critères figés AVANT mesure

Les deux candidats sont re-testés sur le journal live uniquement :

- **B6' (Absorption CVD multi-venues)** : signal = divergence entre le delta
  agrégé 4 venues et le prix (fenêtres 1h/3h/6h, seuils en quantiles du
  journal lui-même). PASS si E[R] > +0,15 R sur n ≥ 100 signaux et PF ≥ 1,30
  avec stabilité entre la 1re et la 2e quinzaine (écart d'E[R] < 0,10 R).
- **B9 (Whale vs Retail)** : signal = écart extreme whale/retail (quantile ≥
  0,95) en direction du flux whale, confirmé par le carnet (book > 1,1 ou <
  0,9). Mêmes seuils de PASS. En cas d'échec : REJET définitif documenté, la
  collecte continue (coût nul) pour densifier les futurs re-tests.

Si un levier PASSE, son R-multiple mesuré est injecté dans le Monte-Carlo
v10 (jambe dédiée) et l'équation de mission k* = 2,29 est recalculée. S'il
ÉCHOUE, la frontière est à nouveau documentée honnêtement : l'objectif
x501@12m exige alors soit un régime favorable (2026-like), soit des données
que même openmarket n'expose pas.

## 6. Ce qui est déjà acquis pendant la collecte

L'allocation PAT-V10-G4 (mise par jambe d'alpha : A1 main 0,05 / A3 main
0,13 / A4 main 0,13 / sat-A4 0,030 / sat-A3 0,015) est le seul levier de la
campagne à avoir PASSÉ tous les filtres (IS, OOS, dominance sur les 3 années
2024/2025/2026) : médiane 12 m ×2,3 vs allocation uniforme (262 → 606 $ à
cadence x3), courbe P(k) améliorée sur toute la plage, DD max strictement
< 25 % inchangé. Elle s'applique immédiatement au déploiement en cours —
la collecte et l'exploitation optimale avancent en parallèle.

---

## 7. ADDENDUM v14 — amendement de puissance statistique (figé AVANT toute donnée)

L'analyse de puissance monte carlo (`scripts/x501_power_v14.py`, 400 réplications
par config, seuils = quantiles du journal lui-même, grappes + régime commun AR(1))
établit que le protocole initial « 30 jours » est statistiquement insuffisant :

| Levier | Déploiement actuel, J+30 | Verdict | Amendement |
|---|---|---|---|
| B9 whale/retail | n_eff méd 86, P(≥100) = 15 % (276 lignes/j : 2 charts 1h + 38 charts 4h) | **INSUFFISANT** | **60 jours** : n_eff méd 166, P(≥100) = 100 % |
| B6' divergence CVD | 36 événements BRUTS max (720 fenêtres 1h × q=0,95) < 100 | **IMPOSSIBLE à J+30 par construction** | **CVD4 sur 4 symboles + 90 jours** : n_eff méd 261, P(≥100) = 100 % ; à 1 symbole : q=0,90 requis (n_eff 153 à 90 j, P = 100 %) |

Décisions figées (à appliquer immédiatement) :
1. **Durée de collecte : 90 jours.** J+30 = contrôle qualité du journal
   UNIQUEMENT (aucune conclusion d'edge) ; J+60 = verdict B9 conditionnel si
   n_eff ≥ 100 ; J+90 = verdicts définitifs B9 + B6'.
2. **Collecteur CVD étendu à 4 symboles** (BTC + ETH + 2 majors perps), même
   script, 4 alertes supplémentaires (budget alertes inchangé : 1 tir/barre,
   marge ×10 documentée v13).
3. **Vérification du TF effectif** : les séries du collecteur suivent le TF du
   chart (pas de `timeframe=` explicite) — 40 charts H1 (960 lignes/j) vs
   déploiement réel mixte (276 lignes/j). Si B9 doit être verdicté à J+60,
   attacher les collecteurs à des charts H1.
4. **Chaîne d'ingestion automatique** (`scripts/x501_collect_v14.py`, 7/7
   tests d'intégration PASS) : parseur X501OBS/X501CVD, validateurs sémantiques
   (net = whale+retail, total = Σ4 venues, trend ∈ {-1,1}, live ∈ 0..4),
   dédoublonnage, détection de trous, stockage JSONL + md5. La cohérence se
   valide à la précision PUBLIÉE du journal (±0,01), propriété du format.

Valeur attendue si un levier PASSE au seuil du protocole (E[R] > +0,15 R,
n ≥ 100, PF ≥ 1,30, stabilité quinzaines < 0,10 R) — Monte Carlo v14
(`scripts/x501_mc_v14.py`, noyau v11 corrélé officiel, 12 000 chemins, 0 rupture,
DD ≤ 25 % strict, SIG actif mois 4-12, régime corrélé +1, f = 0,05) :

| E[R] live | 50 signaux/mois | 85/mois | 150/mois | (baseline sans SIG : 0,07 %) |
|---|---|---|---|---|
| +0,15 R (seuil) | P(x501) 12,7 % | 26,2 % | 39,2 % | médiane 642 → 3 530 / 8 553 / 14 482 $ |
| +0,30 R (×2) | 44,6 % | 49,4 % | 78,3 % | médiane 36 781 / 45 339 / 50 616 $ |
| +0,60 R (×4) | 84,9 % | 88,1 % | 97,0 % | médiane 50 686 / 50 701 / 50 807 $ |
| +1,00 R | 90,9 % | 98,7 % | 99,6 % | médiane 50 744 / 50 817 / 50 818 $ |

Le gap de mission n'est donc plus un mur : **un edge live au SEUL seuil du
protocole multiplie P(x501@12m) par ~190 (0,07 % → 12,7-39,2 %)**. Tout dépend
désormais de ce que la collecte mesurera — verdict chiffré à J+90, sans
intervention manuelle.
