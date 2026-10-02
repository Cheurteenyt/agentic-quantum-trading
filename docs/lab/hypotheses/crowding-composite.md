# crowding-composite — LE COMPOSITE CROWDING (pré-enregistrement Rail A)

> Pré-enregistré le 2026-10-02, AVANT tout calcul de score, AVANT tout test.
> Gouvernance : docs/38-gouvernance-recherche.md (tag freeze-2026-10-02), §61 —
> « le composite crowding (fresh/crowded/late) — pré-enregistré AVANT tout test,
> budget consommé, une variable à la fois ». C'est une CRÉATION de machinerie :
> aucun verdict ici, aucune métrique de performance regardée à ce jour.

```text
domain:         ASTER
horizon:        H-MULTI (conditionneur d'état pour les flux 1h existants)
window:         TEST VERROUILLÉ 2026-10-30 → 2027-01-30 (fenêtre pré-déclarée,
                jamais réutilisée entre générations ; split chrono 70/30 interne)
hypothesis:     voir ci-dessous (H-CROWD-1)
why_not_textbook: composite POSITIONNEMENT (funding + OI + premium mark/index +
                volume dirigé + densité de liquidations) — aucun TA textbook ;
                état de marché ex-ante, jamais un signal directionnel
death_criteria: FAIL si C1–C4 non tenus à la date de test → famille gravée,
                STOP, aucune re-pondération ; NUL-couverture si à 2026-10-30
                l'OI bulk < 30 j ou n < seuils → UN report daté au registre,
                jamais une série de reports
baseline:       les flux machine inchangés (cascade gated AL p66, vol_spike 6h)
                rejoués sans conditionneur ; contrôle inverse = gater l'inverse
N_min:          60 entrées/état comparé en TRAIN, 30 en VAL
param_critique: le score composite C et ses seuils T_CROWD=0.50 / T_LATE=0.80
                (gelés ci-dessous, zéro grille)
```

## H-CROWD-1 (hypothèse falsifiable, formulation verrouillée)

> **Les entrées des flux machine 1h existants (cascade gated AL p66 et
> vol_spike_6h, convention harnais : entrée open t+1, sortie au plan du signal,
> 1x, coûts 18 bps RT) exécutées alors que l'état de crowding ex-ante du
> symbole est LATE ou EXHAUSTED ont une espérance nette 24–72 h STRICTEMENT
> INFÉRIEURE à celle des mêmes entrées en état FRESH, aux deux splits (TRAIN
> et VAL), et chaque état LATE / EXHAUSTED est séparément SOUS le base-rate
> inconditionnel du flux.**

Mécanisme : une foule positionnée tardivement (funding élevé, OI en
acceleration déjà mûre, premium étiré, volume dirigé extrême) n'a plus de
carburant — les entrées dans le sens du crowd mangent la sortie de la foule ;
un flush avéré (OI en décrue forte + liquidations denses) = la sortie EST en
cours. En état FRESH, le positioning n'est pas encore extrême et les flux
conservent leur edge structurel.

## Définition figée du composite (AVANT tout test — aucun chiffre regardé)

Score continu C ∈ [−1, +1] par symbole et par heure (au close de la bougie 1h ;
positif = foule LONGUE crowdée, négatif = foule SHORT crowdée). Chaque
composante est OPTIONNELLE (absente si la donnée manque) et le score se
normalise sur les composantes PRÉSENTES (moyenne simple). Moins de 2
composantes présentes → état UNKNOWN (jamais scoré).

| composante | définition figée | mapping [−1,+1] |
|---|---|---|
| z-funding (niveau) | z du dernier funding rate vs moyenne/écart-type des obs du symbole sur 30 j glissants (≥ 30 obs) | `clip(z/3, −1, 1)` |
| ΔOI % (vitesse) | variation % de l'OI entre 2 snapshots du MÊME source séparés de 3–5 h (priorité `oi_history`, sinon `oi_history_bulk`) sur 4 h | `clip(d_oi_pct/1.5, −1, 1)` |
| premium z (mark vs index) | z du dernier `premium_pct` vs 7 j glissants du symbole (≥ 500 obs) | `clip(z/3, −1, 1)` |
| volume relatif 24h | vol24h (somme quote_volume 1h) / médiane des 30 sommes quotidiennes des 31 j précédents (≥ 20 j), SIGNÉ par `sign(ret 24h)` | `clip(log2(vol_rel)/2, −1, 1) × sign(ret24h)` |
| densité liq 24h | pression nette `(notional longs liquidés − notional shorts liquidés)/(total + ε)` sur 24 h, convention Binance fapi forceOrder (`SELL` ⇒ LONG liquidé, `BUY` ⇒ SHORT liquidé) | `clip(−pression_nette, −1, 1)` |

États discrets (figés, symétriques en |C|) :

| état | règle figée |
|---|---|
| FRESH | \|C\| < 0.50 |
| CROWDED | 0.50 ≤ \|C\| < 0.80 |
| LATE | \|C\| ≥ 0.80 |
| EXHAUSTED | flush avéré : densité liq 24 h ≥ 0.5 % de l'OI notionnel courant **ET** ΔOI 4 h ≤ −1.0 % (override, prioritaire) |
| UNKNOWN | < 2 composantes présentes |

Unités (pièges vérifiés au run du 02/10, pattern `oi_quadrant_test.py`) :
`ts_ms` klines.db en MILLISECONDES (auto-détection ≥ 13 digits partout, y
compris `liq_events.event_time` détecté ms sur la donnée actuelle) ;
`oi_history.open_interest` = unités de BASE (notional = oi × prix) ;
`oi_history_bulk.open_interest` = NOTIONAL USD ×2 — **vérifié au run : médiane
bulk/(base×prix) = 2.000 sur 39 symboles appariés** (conversion ÷2 vs base
confirmée) ; funding cadence MIXTE (1 h pour la plupart des symboles depuis
2026-08, 4 h pour ASTERUSDT) → z-funding toujours TIME-BASED (30 j), jamais
par comptage fixe.

## Critères PASS / FAIL (écrits AVANT tout test — tous requis)

Split chrono 70/30 global DANS la fenêtre verrouillée 2026-10-30 → 2027-01-30
(TRAIN = 60 premiers jours, VAL = 30 derniers) ; population = entrées des deux
flux machine sur la fenêtre ; état ex-ante lu au close de l'heure du signal ;
les données d'avant le 30/10 sont INTERDITES au test (OI bulk < 30 j).

- **C1** : espérance nette (LATE ∪ EXHAUSTED) < espérance nette (FRESH), écart
  ≥ 18 bps RT (l'étalon de coût — un écart sous les coûts n'est pas
  actionnable), aux DEUX splits.
- **C2 (règle PAR ÉTAT, leçon INV-H)** : LATE et EXHAUSTED, CHACUN séparément,
  sous le base-rate inconditionnel du flux (espérance de toutes les entrées de
  la fenêtre, pas la moyenne des autres états) — un prédicteur dégénéré
  « toujours l'état majoritaire » doit échouer ici, aux deux splits.
- **C3** : gradient FRESH > CROWDED > LATE monotone en TRAIN (descriptif en VAL).
- **C4** : n ≥ 60/état comparé en TRAIN et n ≥ 30/état en VAL.
- **Contrôle inverse obligatoire** : gater l'INVERSE (ne garder que
  LATE/EXHAUSTED) doit être pire que ne rien filtrer, aux deux splits — sinon
  l'effet est un artefact de base-rate/régime.
- **Garde-fou composé-des-mois vs final** (leçon des verdicts ABSOLUS) : le
  bloc mensuel du flux conditionné doit dominer le flux nu sur la majorité des
  mois, pas seulement en cumul.

FAIL = un seul critère manquant → « FAIL — hypothèse réfutée », gravé au
registre, budget consommé, STOP. Aucune re-pondération, aucun 2e seuil.

## Prior déclaré (honnêteté)

**NÉGATIF.** Les composites ont DÉJÀ inversé dans ce projet :
`al_score_v2_composite` REJECTED 28/09 (« les directions GATED s'inversent sur
l'univers complet ») ; les directionnels train→val s'inversent
systématiquement (INV-A, INV-K, INV-L, INV-M). Attente honnête : FAIL probable.
La valeur de la primitive est descriptive (état de marché affichable) MÊME en
cas de FAIL — mais un FAIL ferme la famille crowding 1/5.

## Adjacences déclarées (registre 41 entrées vérifié le 02/10)

- `al_score_v2_composite` (composite, REJECTED) : construit prix/momentum —
  ici POSITIONNEMENT funding/OI/premium/volume/liq, construit distinct.
- Famille funding-structure FAIL : le funding y est UNE composante parmi cinq
  d'un conditionneur, JAMAIS un signal autonome.
- Famille cascade FERMÉE (15+ verdicts) : le flux cascade sert de VÉHICULE de
  test, il n'est PAS re-testé — c'est son conditionneur qui l'est.
- `oi_quadrant_h4h5` (EXPERIMENTAL) : événements de quadrant 90 min, pas un
  état roulant horaire — complémentaire, non réutilisé.

## Interdictions

1. **UNE variable** : l'état du composite. Aucune re-pondération des composantes
   après coup, aucun 2e seuil T_CROWD/T_LATE, aucune autre fenêtre — toute
   variante = PARAMETER_MUTATION (nouveau pré-enregistrement + budget).
2. Le composite n'est **PAS un signal autonome** — conditionneur d'état pour les
   flux existants uniquement (SENS=0).
3. Aucune stat de performance avant le 2026-10-30 : la primitive tourne en mode
   SMOKE (couverture) d'ici là ; le test ne commence pas avant.
4. Un seul domaine (ASTER) dans tout BLOC STATS ; jamais FOMO/X mélangés.
5. Date de test verrouillée : **2026-10-30** (OI bulk atteint 30 j : 645
   symboles ; 2.5 j au 02/10). Un report unique est possible si la collecte
   casse, daté au registre — jamais une série.

## Couverture au 02/10/2026 (constat SMOKE, aucune stat de résultat)

À remplir par le run SMOKE — voir `reports/aster/crowding_coverage_*.csv`.
Verdict de couverture : test possible au 30/10 SI la collecte OI bulk tient le
rythme (2.5 j → 30 j requis).

## AMENDEMENTS PRE-TEST (02/10/2026 — red-team du modèle local Bonsai, AVANT toute mesure)

Le red-team (modèle local, medium thinking) a identifié 6 failles dont 2 actionnables avant le tir du 30/10 :

1. **Stratification par flux (paradoxe de Simpson)** : les 2 flux n'ont pas la même espérance intrinsèque et les états peuvent corréler avec la composition (plus de fades vol_spike en FRESH, plus de cascades gated en LATE). **AMENDEMENT : l'effet d'état se juge DANS chaque flux séparément (cascade gated d'un côté, vol_spike de l'autre) — jamais en pooled. Le critère C1-C4 s'applique par flux.**
2. **Incohérence temporelle du composite** : le funding (cycle 8h, lent) et l'OI/premium (rapides) mesurent des échelles de temps incompatibles — l'état LATE confond saturation historique et crowding instantané. **AMENDEMENT : le tir principal tourne avec le composite COMPLET, plus une variante de robustesse SANS la composante funding (4 composantes) — l'hypothèse ne survit que si les deux versions concordent.**

Les 4 autres failles du red-team (décalage temporel funding/OI en look-ahead, base-rate corrélé à la vol, les 2 suivantes tronquées) : documentées dans /tmp/hikari_redteam.txt, non actionnables avant le tir ou couvertes par les règles existantes (z-scores sur fenêtres passées = pas de look-ahead).

Ces amendements sont datés AVANT le 30/10 — le tir jugera la version amendée. Aucune autre modification ne sera acceptée après le tir.
