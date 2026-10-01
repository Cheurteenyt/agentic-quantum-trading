# 28 · OPENMARKET — LE PROTOCOLE A/B PRÉ-ENREGISTRÉ (vagues 1-2)

> Créé le 01/10/2026, AVANT tout run A/B — c'est l'objet même du document :
> les critères sont figés ici, le moteur applique, personne ne décide après
> coup. Moteur : `scripts/studies/x501_openmarket/x501_verdict_ab.py`
> (stdlib pure, bootstrap déterministe seed 501). Registre des verdicts :
> `docs/20-registre-indicateurs.md`. Ce protocole évalue les vagues 1-2 du
> plan d'exploitation (`docs/27-pouvoirs-kscript.md`) : le filtre de régime
> institutionnel (RI) et le pattern absorption orderbook.
> **Priorisation (vague 6, `docs/31`) : la file de runs recommandée est
> RI (1-2) → MK6 (7-8) → TRAIL (5-6) → ABS (3-4)** — le banc d'événements
> en proxy klines a réfuté la prime de structure de l'ombre klines du
> pattern (0/4 cellules, la confirmation est tardive) : l'ABS reste au
> protocole (le juge de l'ordrebook ne change pas) mais passe EN QUEUE —
> avec un rôle renforcé : un verdict ABS positif là où l'ombre klines est
> morte prouverait la valeur UNIQUE du champ carnet.
origin/main
origin/main
origin/main
origin/main

## LA RÈGLE (une phrase)

Aucune des deux nouveautés ne touche la config officielle (MC v20, baseline
2026-10-01) tant que ce protocole n'a pas produit un verdict PROMOTION ;
KILL ou INCONCLU laissent la référence intacte et le registre tranchera.

## LES 8 RUNS (le testeur kScript, exports « trades » CSV)

| # | test | jambe A (contrôle) | jambe B (traitement) | symbole | N_MIN |
|---|---|---|---|---|---|
| 1 | RI-BTC | `Operation_x501_Signature_H1` | `Operation_x501_Signature_H1_RI` | BTCUSDT 1h | 20 |
| 2 | RI-ETH | idem | idem | ETHUSDT 1h | 20 |
| 3 | ABS-BTC | `Operation_x501_Signature_H1` | `Operation_x501_Absorption_H1` | BTCUSDT 1h | 12 |
| 4 | ABS-ETH | idem | idem | ETHUSDT 1h | 12 |
| 5 | TRAIL-BTC (optionnel, vague 3) | `_MK` useNativeTrail=false | `_MK` useNativeTrail=true | BTCUSDT 1h | 20 |
| 6 | TRAIL-ETH (optionnel, vague 3) | idem | idem | ETHUSDT 1h | 20 |
| 7 | MK6-BTC (extension du 01/10/2026, docs/29 § 7) | `_MK` makerTTL=2 | `_MK` makerTTL=6 | BTCUSDT 1h | 20 |
| 8 | MK6-ETH (extension du 01/10/2026) | idem | idem | ETHUSDT 1h | 20 |

> **Extension MK6 (pré-enregistrée le 01/10/2026, source : docs/29)** : la mesure
> du fill maker sur le pool P1 montre que le TTL=2 laisse 6,18 % des signaux
> tomber dans le fallback taker à −88,6 bps de delta, écrasant l'avantage maker
> à +0,375 bps (vs +2,897 bps à TTL=6). Le TTL=6 est donc un **candidat
> pré-enregistré**, mais la mesure historique ne peut pas dire si l'edge du
> signal survit à 6 h d'attente (limite L6 de docs/29) : ces deux runs
> répondent. Critères inchangés ; convention CSV `ab_x501_BTCUSDT_mk6_off/on.csv`.
>
> **Priorisation vague 6 (pré-enregistrée le 01/10/2026, source : docs/31)** :
> le banc d'événements en proxy klines réfute la prime de structure de
> l'ombre klines du pattern absorption (E3 vs E1 : −26,4/−54,2 bps LONG,
> CONTEXTE SHORT, 0/4 cellules justifiées) — les runs 3-4 (ABS) restent au
> protocole mais passent EN QUEUE de file. Ordre recommandé : **RI (1-2) →
> MK6 (7-8) → TRAIL (5-6) → ABS (3-4)**. Le N_MIN = 12 de l'ABS est
> inchangé, et son rôle est précisé : un PROMOTION sur ABS alors que le
> proxy klines est mort = preuve par contraste que le champ orderbook porte
> une information unique (à valider en papier v11 comme tout PROMOTION).
origin/main
origin/main
origin/main
origin/main

**Discipline de run** : même fenêtre temporelle et mêmes inputs pour les
deux jambes d'un même test (seul le filtre / le pattern change) ; les 8 flux
premium vérifiés vivants au préalable via `x501_observe_regime.ks`
(« flux vivants >= 3 / 5 » obligatoire, sinon le run ne sert à rien — le
moteur le détecterait en DATA_ABSENTE) ; les CSV déposés dans
`scripts/studies/x501_openmarket/ab/` avec la convention
`ab_x501_<symbole>_<setup>_<on|off>.csv` (ex. `ab_x501_BTCUSDT_ri_on.csv`),
un CSV = un bras ; puis :

```bash
python3 x501_verdict_ab.py ab_x501_BTCUSDT_ri_off.csv ab_x501_BTCUSDT_ri_on.csv --label "RI-BTC"
```

## LES CRITÈRES (figés le 01/10/2026 — identiques au moteur, au bit près)

Les jambes sont comparées sur l'unité R (le CSV l'exporte déjà), jamais sur
le PnL brut qui dépend de la taille. Quatre verdicts possibles, évalués
DANS CET ORDRE (le premier qui s'applique tranche) :

1. **DATA_ABSENTE** — `n_B >= 97 % de n_A` : le « filtre » n'a filtré
   aucune entrée, la data premium était absente (fail-open pré-enregistré
   dans les scripts). Ce verdict n'est NI un succès NI un échec du signal :
   c'est un problème de data, à corriger et re-run.
2. **PROMOTION** — `n_B >= N_MIN` ET `P(méd_B > méd_A) >= 0,70` (bootstrap
   10 000, seed 501) ET `méd_B - méd_A >= +0,10 R` ET
   `maxDD_B <= maxDD_A + 2,0 R`. Les quatre conditions à la fois : le gain
   médian, la probabilité, la taille d'échantillon et le coût en drawdown.
3. **KILL** — `P <= 0,40` ET `n_B >= 10` : le traitement est un anti-signal
   (ou un bruit coûteux). Entrée NUL au registre, chiffres à l'appui.
4. **INCONCLU** — tout le reste. Le plus probable au premier run : les CSV
   de référence portent 16 trades (BTC) et 15 (ETH) sur la fenêtre courante,
   donc `n_B < 20` presque à coup sûr avec le filtre RI actif. Pré-enregistré
   et assumé : **élargir la fenêtre temporelle et re-run, JAMAIS de
   promotion en dessous de N_MIN** — pas même quand le bootstrap sourit.

Métriques descriptives imprimées par le moteur (n, médiane, moyenne, WR,
somme R, maxDD en R composé, Welch t en ddl de Welch) : lecture seule, le
verdict ne repose QUE sur les critères ci-dessus. **N_MIN = 20** pour les
tests RI et TRAIL (défaut du moteur), **N_MIN = 12** pour ABS (profondeur
orderbook limitée) — l'option `--n-min` existe pour ça et rien d'autre.

## LES PIÈGES PRÉ-ENREGISTRÉS (écrits ici AVANT les runs)

- **Le fail-open du RI** (déjà câblé dans les scripts) : moins de 3 des 5
  composantes vivantes = filtre transparent. Le moteur le trahit
  immédiatement (verdict 1). C'est le comportement voulu : un filtre
  silencieux qui « marche » sans data serait une illusion.
- **La saturation ETF** : l'agrégation `htf()` d'un flux daily en sigma 60 j
  peut ressortir ~24× la valeur plateforme si le membre `.value` cumule le
  bucket. Écrit AVANT le run dans `docs/27` : si la composante sature, le
  filtre devient tout-ou-rien et le verdict le montrera (n_B effondré ou
  DATA_ABSENTE). Remède : corriger la projection, re-run, pas de patch
  silencieux.
- **La profondeur orderbook en backtest** (~1 semaine à 1m, des mois à 1h
  selon la doc plateforme) : le test ABS est une falsification initiale sur
  la fenêtre DISPONIBLE, jamais une preuve 733 j — d'où `N_MIN = 12` et la
  règle : tout PROMOTION du run 3-4 reste un CANDIDAT à valider au papier
  forward (protocole v11), pas une config officielle.
- **Le piège OCA** (vague 3, déjà gravé dans les `_MK`) : `ocaName` = « quand
  l'un remplit, les autres s'annulent ». L'échelle TP1/TP2/RUN porte donc un
  groupe NOMMÉ PAR TRANCHE et ne partagera JAMAIS un même groupe — un TP1
  rempli ne doit pas tuer le runner.
- **Le trail natif** (vague 3, défaut false) : la référence MC v20 reste
  bit-à-bit tant que le run 5-6 n'a pas tranché ; le trail natif ratatine
  intrabar (fidélité), la piste manuelle continue de vivre en plancher.
- **Le refus des ticks** : `strategy.exit profit=/loss=` (distances en ticks
  de l'API) reste délibérément DORMANT — dépendant de la taille de tick du
  symbole, notre échelle calcule des prix absolus depuis la distance de stop
  réelle. Famille broker : 15/16, la case refusée est documentée, pas oubliée.

## APRÈS LE VERDICT (la boucle registre)

| verdict | conséquence |
|---|---|
| PROMOTION | entrée CANDIDAT à `docs/20` + câblage au paper forward 2×/jour (le forward reste le juge) |
| KILL | entrée NUL à `docs/20` avec les chiffres ; le script reste archivé, la famille exploite quand même la capacité |
| INCONCLU | observation continue ; fenêtre élargie ou accumulation au forward |
| DATA_ABSENTE | réparer la data (observe), re-run, aucun verdict de signal |

Le taux d'exploitation attendu après vague 3 : **40/53 = 75,5 %**
(sources premium 7/8, orderbook 2/3, broker 15/16 — la case refusée par
design étant documentée ci-dessus).
