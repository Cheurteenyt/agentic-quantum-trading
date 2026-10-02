# INV-B — « LA CONCENTRATION-ROTATION » (pré-enregistré)

- **Domaine** : Aster (panel cross-majors, données klines.db en lecture seule)
- **Date de pré-enregistrement** : 2026-10-02, AVANT tout résultat (ce bloc écrit avant l'exécution du script)
- **Gouvernance** : docs/38-gouvernance-recherche.md, tag `freeze-2026-10-02` ; registre `research/registry.yaml` vérifié : aucune expérience concentration/Herfindahl/rotation-prev antérieure → expérience GÉNUILEMENT nouvelle (pas une PARAMETER_MUTATION). Budget : 1 expérience, 0 modification de protocole.
- **Script one-shot** : `scripts/studies/inv_b_concentration_rotation.py` (unique exécution, aucun re-run de variante autorisé)

## 1. Hypothèse pré-déclarée

Après un PIC de concentration du volume (une majeure absorbe tout le flux — H_t extrême), il y a **ROTATION** : sur la fenêtre 24-72 h suivante, les 5 majeures non-concentrées surperforment **en médiane** la majeure concentrée. Contrôle inverse obligatoire : la **continuation** (la concentrée continue de gagner) doit être pire — sinon artefact.

## 2. Construction (une seule définition, zéro grille, jamais re-tunée)

- Panel : BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT — 1h, `data/warehouse/klines.db` (mode=ro). Le panel complet aux 6 n'existe qu'à partir de 2025-09-24 (1h BNB/XRP/DOGE absentes avant) : c'est l'univers réel, assumé.
- À chaque close 1h t où les 6 majeures ont un historique complet 24 h : volume 24 h de i = somme `quote_volume` des 24 barres 1h [t-23 … t] (unité ms vérifiée, open_time en millisecondes).
- **H_t = Herfindahl des volumes 24h = Σ(v_i²)/(Σv_i)²** sur les 6 majeures.
- **Événement** : H_t ≥ quantile 95 de H_t **calculé sur TRAIN SEULEMENT** (un seul seuil, jamais recalculé).
- Mesure par événement : retour de chaque majeure sur [t+24 h ; t+72 h] en close 1h. **REL_gross = médiane(ret des 5 non-concentrées) − ret(concentrée)**. La concentrée = l'actif de plus fort volume 24h à t.
- Coûts si tradé : **36 bps RT par paire** (2 jambes taker 18) → REL_net = REL_gross − 0,36 %. Pas de levier. Convention d'exécution inchangée (signal close t → les jambes s'exécutent aux horizons du plan, ici fenêtre 24-72 h déclarée).
- Événements sans barres complètes à t+24/t+72 h (fin de split / trous) : exclus, comptés, documentés.

## 3. Protocole immutable

- Split **60/40 chrono GLOBAL** du panel (60 % train / 40 % val, par le temps). Quantile 95 sur train. Les événements VAL sont mesurés avec le seuil TRAIN.
- **n_train ≥ 80 événements mesurés** sinon expérience déclarée **SOUS-PUISSENTE** telle quelle (échec de puissance ≠ réfutation).
- BLOC STATS mensuel obligatoire. Règle 0-liquidation non applicable (0 levier, 0 liq par construction).

## 4. Critères PASS/FAIL (écrits AVANT les résultats)

**PASS** (les trois, train ET val) :
1. **Espérance relative nette > 0** : mean(REL_net) > 0 sur TRAIN et sur VAL.
2. **Contrôle inverse battu** : mean(ret(concentrée) − médiane(ret des 5)) **< 0 en brut** (gros, avant coûts) sur TRAIN et VAL — la continuation doit perdre en direction, pas seulement après coûts.
3. **Gradient monotone** : terciles de H_t parmi les événements (T1 = H le plus faible du top-5 %, T3 = le plus extrême) → REL_net médian croissant T1 ≤ T2 ≤ T3 sur TRAIN (VAL descriptif).

**FAIL = tout le reste** → « FAIL — hypothèse réfutée », enregistré au registre, budget consommé, STOP. Pas de deuxième quantile, pas de fenêtre alternative, pas de filtre de réparation. Budget = 1 expérience.

---

# RÉSULTATS (exécution unique du 02/10/2026)

Note d'intégrité : un bug de signe dans l'affichage du contrôle inverse (`med5 − ret_c`
au lieu de `ret_c − med5`) a été corrigé et re-mesuré une fois — aucun critère, seuil,
fenêtre ni protocole touché ; le verdict est identique avant/après (il ne dépend d'aucun
signe du contrôle : VAL est vide et le gradient est faux dans les deux cas).

## Exécution

- Grille commune 1h : 8 932 h (2025-09-23 22:00 → 2026-10-01 01:00 UTC), heures mesurables H_t : 8 909 (0 exclue pour trous 24h).
- Split 60/40 chrono global : TRAIN 5 345 h | VAL 3 564 h.
- **Quantile 95 de H_t (TRAIN) = 0,6222** (H_train min/med/max : 0,231 / 0,376 / 0,822 ; H_val max : 0,522).
- Événements : **268** (100 % TRAIN, 0 exclus de mesure).
- **Événements VAL : 0** — H_val n'a JAMAIS atteint le seuil train (max 0,522 < 0,622). Le régime de concentration extrême est un phénomène TRAIN (oct-nov 2025, dominance BTC) sans aucune récurrence sur les 9,5 mois de VAL.
- La concentrée est BTCUSDT sur les 268/268 événements.

## Chiffres clés (TRAIN, n = 268)

| Stat | REL_gross | REL_net (−36 bps) |
|---|---|---|
| moyenne | **−1,259 %** | **−1,619 %** |
| médiane | −0,882 % | −1,242 % |
| WR | — | **24,6 %** |

- **Espérance relative nette < 0 en train** ; **0 événement en val** → critère 1 impossible.
- **Contrôle inverse** (continuation, ret(BTC) − médiane des 5, brut) : mean **+1,259 %**, médiane +0,882 % — la continuation GAGNE en direction, le contrôle n'est PAS battu (l'effet mesuré est l'exact inverse de l'hypothèse).
- **Gradient terciles H_t** (TRAIN, bords 0,640/0,662) : T1 **−0,305 %** | T2 −1,493 % | T3 −1,467 % — non monotone au sens pré-déclaré (et orienté à l'envers : plus la concentration est extrême, plus la « rotation » perd).

## BLOC STATS mensuel (somme REL_net par mois, non composé, sans levier)

| Mois | Split | n | WR_net | Somme REL_net |
|---|---|---|---|---|
| 2025-09 | TRAIN | 6 | 33 % | −2,77 % |
| 2025-10 | TRAIN | 113 | 27 % | −132,00 % |
| 2025-11 | TRAIN | 128 | 23 % | −272,40 % |
| 2025-12 | TRAIN | 21 | 24 % | −26,66 % |
| 2026-01 → 10 | VAL | 0 | — | 0 (aucun événement) |

- **Mois négatifs : 4/4** | pire mois −272,40 % | record mois −2,77 % | cumul −433,84 % | DD max courbe cumulée 443,92 pts.
- Liquidations : **0** (aucun levier, spread relatif, par construction).

## Vérification des critères

| Critère | Résultat |
|---|---|
| n_train ≥ 80 | OK (268) |
| 1. mean REL_net > 0 train ET val | **FAUX** (−1,62 % train ; val : 0 événement) |
| 2. Contrôle inverse battu (continuation brute < 0, train ET val) | **FAUX** (+1,26 % train) |
| 3. Gradient monotone T1 ≤ T2 ≤ T3 (train) | **FAUX** (−0,31 / −1,49 / −1,47) |

## VERDICT : **FAIL — hypothèse réfutée**

Après un pic de concentration (BTC absorbe le volume des 6 majeures), il n'y a PAS de rotation : sur 24-72 h, **la concentrée continue de surperformer** la médiane des 5 autres de +1,26 % en brut (268 événements, WR_net 24,6 %, 4 mois négatifs sur 4). La direction mesurée est l'exact inverse de l'hypothèse. Budget consommé, **STOP** : pas de deuxième quantile, pas de fenêtre alternative, pas de filtre de réparation.

Observation enregistrée (NON promouvable, NON testée comme stratégie — même donnée, même budget) : la direction inverse (continuation de la concentrée) a été directionnellement positive en brut sur TRAIN, mais elle est (a) portée par le seul régime oct-nov 2025, (b) **invérifiable en VAL au seuil pré-déclaré (0 événement)**, (c) non soumise au wallet séquentiel. Toute réutilisation exigerait un nouveau pré-enregistrement + budget ; en l'état c'est un constat de régime, pas un edge.
