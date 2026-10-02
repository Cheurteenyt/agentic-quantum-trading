# INV-D « L'ASYMÉTRIE DE VITESSE » — PRÉ-ENREGISTREMENT (02/10/2026, AVANT toute mesure)

Statut : **EXPERIMENTAL** — gouvernance docs/38, tag `freeze-2026-10-02`.
Budget : 1 expérience consommée (famille `temps-structure`, 4ᵉ INV de la semaine ;
anti-doublon vérifié : docs/20 ne connaît que la capitulation PRIX H2bis
« min des 24 closes + pente CVD » (NUL) et la déviation relative z24 (INV-A,
REJETÉE) — A_t est une statistique de TEMPS sans magnitude ni CVD, hypothèse
jamais testée). Ce fichier est scellé (sha256) AVANT l'exécution du one-shot ;
les résultats sont appendus APRÈS, sans retouche du pré-enregistrement.

## La construction (jamais existée)

Pour chaque close 1h de chaque symbole du panel 6 majeures (BTC, ETH, SOL, BNB,
XRP, DOGE — `data/warehouse/klines.db`, table `klines`, `interval='1h'`,
Lecture SEULE, `open_time` en MILLISECONDES — unité vérifiée) :

- Fenêtre glissante 24h = les 24 closes {t−24, …, t−1} (la fenêtre passée,
  bougie courante exclue).
- **A_t = (nombre de closes de la fenêtre strictement au-dessus de close_t) / 24.**
  Fraction de la fenêtre passée AU-DESSUS du prix courant = mesure du CHEMIN
  temporel, indépendante de la magnitude du rendement. A_t = 0 ⇔ le prix clôture
  sous les 24 closes = capitulation PAR LE TEMPS. A_t ∈ [0, 1], sans unité de prix.
- **Événement = A_t ≤ q10(A), le quantile 10 calculé sur TRAIN SEULEMENT** (un
  seul seuil, zéro grille : le quantile est calibré une fois sur le train poolé
  du panel, appliqué inchangé au val).
- Split **60/40 chrono GLOBAL** : ts_split = min_ts + 0.60 × (max_ts − min_ts)
  du panel 1h entier (tous symboles confondus). Décalage d'exécution :
  signal close t → entrée open t+1 (convention maison).
- Trade : **LONG 1x, sans levier** (0 liquidation par construction), coûts
  **18 bps RT** (net = (1+brut)×(1−0.0018)−1, le même pour le short du contrôle).
  Trois horizons mesurés depuis la MÊME entrée : sortie au close t+24, t+48,
  t+72 (barre exacte ; si absente, première barre suivante ≤ +3h, sinon
  événement abandonné et compté).
- **Contrôle inverse obligatoire** : au MÊME événement, la continuation
  (SHORT = parier qu'extrême bas → ça continue de baisser) doit être PIRE que le
  long, sinon artefact. Le miroir A_t ≥ q90(A) (quantile 90, même calibration
  train unique) est mesuré en **CONTEXTE descriptif seulement**, hors pass/fail.

## L'hypothèse falsifiable (pré-déclarée)

La capitulation par le temps (A extrême bas) est suivie d'un **REBOND** :
espérance forward nette 24-72h POSITIVE, sans condition de magnitude.
Le gradient doit être porté par le CHEMIN (déciles de A), pas par un artefact
de queue.

## PASS/FAIL écrits AVANT (budget = 1 expérience, aucun re-test)

- n train ≥ 100 événements, sinon « sous-puissant, non tranchable » déclaré tel
  quel (échec de puissance, PAS un FAIL de l'hypothèse).
- **PASS (les 3 à la fois)** :
  1. espérance nette (moyenne des 3 horizons 24/48/72) > 0 en TRAIN **ET** en VAL ;
  2. contrôle inverse battu : net_short < net_long en TRAIN **ET** en VAL ;
  3. gradient monotone : espérance nette 24h par décile de A (bornes calibrées
     train) NON-CROISSANTE du décile 1 au décile 10 (tolérance : une seule
     inversion adjacente), décile 1 = maximum, en TRAIN **ET** en VAL.
- **FAIL = tout le reste** — « FAIL — hypothèse réfutée », gravé au registre,
  STOP. Pas de deuxième quantile, pas de fenêtre alternative, pas de filtre
  réparateur.
- **BLOC STATS mensuel obligatoire** (réalisation « tradeable » : 1 position
  ouverte max par symbole, premier-arrivé, trade 24h) : trades, WR net, liqs,
  cumul net sur notionnel fixe 1x, ROI/an, DD, pire/record mois, mois négatifs.
  L'espérance du pass/fail est mesurée sur TOUS les événements (overlap assumé,
  significativité gonflée — déclaré) ; le bloc mensualisé sur premier-arrivé.
- Garde-fou composé-des-mois vs final mentionné sur toute lecture de cumul.

## Note honnête sur le panel (constatée AVANT mesure, par les seules métadonnées)

Le panel klines est PLUS LONG que prévu : BTC/ETH/SOL ≈ 5 ans (2021-09 → 2026-09),
BNB/XRP/DOGE ≈ 1 an (2025-09 → 2026-09). Le split 60/40 global (~2024-09) place
donc BNB/XRP/DOGE ENTIÈREMENT en VAL : le seuil q10 train est calibré sur
BTC/ETH/SOL (seules données train du panel), et le taux d'événements de
BNB/XRP/DOGE en val peut s'écarter de 10 % — écart rapporté tel quel, non corrigé.

<!-- SEAL: sha256 de ce fichier à l'instant du scellement (avant toute exécution) -->

---

# RÉSULTATS (02/10/2026, appendus après le sceau — pré-enregistrement ci-dessus INCHANGÉ)

Exécution : `scripts/studies/inv_d_asymetrie_vitesse.py` (one-shot, klines.db mode=ro),
run du 02/10/2026, re-run déterministe identique. Seal du pré-enregistrement :
`sha256 b73bc5d30da139963620645888e632c84a65c152b4decc0cdc847c36f6f11898`
(hashé sur le fichier AVANT toute exécution ; tout ce qui précède la ligne
`RÉSULTATS` est le pré-enregistrement).

## Calibration (train seulement, un seul seuil)

- Panel 1h : 2021-09-01 06:00 → 2026-10-01 23:00 ; SPLIT 60/40 GLOBAL = **2024-09-19 06:36**.
  160 030 points valides (432 abandonnés : forward incomplet au-delà de +3h).
- A_train n = 79 809 (BTC/ETH/SOL uniquement — voir note panel) ; **q10 = 0.0417**,
  q90 = 0.9583, moy = 0.4991. Bornes déciles train : 0.0417 / 0.125 / 0.2083 / 0.3333 /
  0.5 / 0.6667 / 0.7917 / 0.875 / 0.9583.
- Honnêteté panel (pré-déclarée) : BNB/XRP/DOGE (début 2025-09) sont 100 % en VAL,
  0 train. Leurs taux d'événements val : BNB 16.6 %, XRP 13.7 %, DOGE 13.8 % —
  et BTC/ETH/SOL val 15.8/15.8/16.6 % : le q10 pré-déclaré tombe dans l'ATOME
  A_t = 1/24 (A_t est discret, multiples de 1/24) ⇒ taux ~15 % au lieu de 10 %.
  Seuil appliqué tel quel (aucun re-calage autorisé).
- Événements : **train 11 903 / val 12 526** — n >> 100, expérience PUISSANTE
  (pas de « sous-puissant, non tranchable » à déclarer).

## Les 3 critères PASS (tous ÉCHOUÉS)

1. **Espérance nette bloc 24-72h > 0 train ET val — ÉCHOUÉ.**
   Train : h24 −19.3 bps (WR 42.3 %), h48 +3.2, h72 +30.4 → bloc **+4.8 bps net**
   (brut +22.8 bps : tout l'edge brut est mangé par 18 bps RT).
   Val : h24 −3.4 (WR 45.3 %), h48 +6.3, h72 **−7.0** → bloc **−1.4 bps net**
   (brut +16.6). Le rebond h72 du train (+30.4 bps) MEURT en val (−7.0) : mirage
   de régime. Aucun horizon n'est nettement positif en val.
2. **Contrôle inverse battu (long > short) train ET val — ÉCHOUÉ.**
   Train h24 : long −19.3 bps < short −16.7 bps → à 24h, la CONTINUATION gagne
   en train (le rebond n'existe pas). Long > short seulement à h48/h72 train et
   aux 3 horizons val — le critère exigeait les DEUX splits, non acquis.
3. **Gradient déciles monotone (d1 max, ≤ 1 inversion) train ET val — ÉCHOUÉ.**
   Train : 6 inversions adjacentes, d1 = PIRE décile (−0.174 %) — le sens est
   INVERSÉ (extrême bas = pire, continuation, pas rebond). Val : 4 inversions,
   d1 = −0.057 % au milieu du classement. TOUS les déciles sont négatifs net 24h
   dans les deux splits : la statistique de chemin A_t ne PORTE AUCUNE direction.

## Miroir A ≥ q90 (contexte descriptif, hors pass/fail)

Long net : train −6.7/−15.8/−17.3 bps (bloc −13.3), val −16.7/−17.5/+2.5 (bloc
−10.6). Pas de fade exploitable non plus : les DEUX extrêmes du chemin temporel
perdent net aux deux splits. Le temps-passé-au-dessus est un mesureur de régime,
pas un signal de rebond.

## BLOC STATS mensuel (premier-arrivé, LONG 1x 24h, notionnel fixe, 0 liq par construction)

- 3 598 trades premier-arrivé (vs 24 429 événements bruts), WR net **43.9 %**.
- Cumul **−279.35 %** notionnel fixe sur 61 mois, **ROI/an ≈ −55.1 %**,
  DD **512 %** (curve cumulée notionnel fixe), record mois 2026-08 **+113.1 %**,
  pire mois 2025-11 **−144.6 %**, **34/61 mois négatifs**.
- Garde-fou composé-des-mois vs final : cumul des mois = cumul total par
  construction (notionnel fixe, aucun écart) — ici le RELATIF et l'ABSOLU
  concordent : catastrophique des deux lectures. Aucune dérive d'unité (ts en ms
  vérifié, les 3 symboles 5 ans dominent les stats mensuelles comme prévu).

## VERDICT

**FAIL — hypothèse réfutée.** La capitulation PAR LE TEMPS n'est pas suivie d'un
rebond : espérance nette val négative, contrôle continuation non battu en train,
gradient absent (voire inversé). La leçon constructive : une statistique de
CHEMIN sans magnitude ne encode pas la direction future des majeures 1h — les
deux queues de A_t sont mortes après coûts. Gravé au registre (REJECTED) et à
docs/20. Budget = 1 expérience, CONSOMMÉ, **STOP** : pas de deuxième quantile,
pas de fenêtre alternative, pas de filtre réparateur. Toute réutilisation de A_t
= nouveau pré-enregistrement + nouveau budget.
