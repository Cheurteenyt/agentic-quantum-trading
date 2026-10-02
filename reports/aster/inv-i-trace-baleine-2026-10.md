# INV-I — « LA TRACE DE BALEINE » (pré-enregistrement + résultats)

- **Domaine** : Aster (table `aster_tape`, `data/warehouse/klines.db` **LECTURE SEULE** mode=ro) — **famille : institutions** (première expérience de la famille au registre)
- **Date de pré-enregistrement** : 2026-10-02, AVANT tout résultat (ce bloc écrit avant l'exécution du script)
- **Gouvernance** : docs/38-gouvernance-recherche.md, tag `freeze-2026-10-02` ; registre `research/registry.yaml` vérifié (grep inv_i / institutions / baleine / whale : AUCUNE expérience antérieure sous cet id ou cette famille) → expérience GÉNUILEMENT nouvelle, pas une PARAMETER_MUTATION. Budget : **1 expérience consommée** (plafond 5/famille).
- **Script one-shot** : `scripts/studies/inv_i_trace_baleine.py` (unique exécution, aucun re-run de variante autorisé)
- **Adjacence déclarée** :
  - **H1 absorption** = agrégats `buy_ratio` (moyenne des 4 bougies 1h) aux entrées cascade — NUL 27/09 (docs/20, `h1_absorption_test.py`). Ici : **le print INDIVIDUEL**, pas un agrégat horaire.
  - **Block trades** = clusters de gros prints à seuils adaptatifs, réponse à **+30 min** — CONTEXTE fade 28/09 (docs/20 : « les prints sont un détecteur d'ABSORPTION, pas de continuation »). Ici : pas de cluster, seuil **q99 unique par symbole**, classification par la réponse de prix **à +5 min**, trade tenu **4-24 h**.
  - Le delta = le print individuel, classé par sa réponse de prix immédiate, horizon 4-24 h. Ni agrégat, ni cluster, ni fenêtre 30 min.

## 0. Vérifications d'intégrité (exécutées AVANT ce seal, écrites ici)

- **ts_ms en MILLISECONDES** : couverture 2026-07-03 06:43 UTC → 2026-10-01 23:22 UTC (90,7 j) — unité confirmée ; le script re-assert (min/max ts dans la fenêtre 2026).
- **Piège des reculs confirmé** : dans l'ordre `agg_id` (workers), **759 reculs de ts_ms sur BTC, 476 sur ETH**. Tri canonique **(ts_ms, agg_id)** obligatoire — tous les searchsorted/agrégats du script l'utilisent, jamais le tri par ts seul ni par agg_id.
- **Convention `is_buyer_maker` vérifiée contre le prix** : `is_buyer_maker=0` = taker BUY (agresseur acheteur, direction +1), `=1` = taker SELL (direction −1). Preuves : corrélation 1-min entre net flow taker signé (achats−ventes en notionnel) et variation de prix du bin = **+0,2484 (BTC) / +0,2057 (ETH)** sur ~130,5k bins valides (le flip donnerait l'exact opposé) ; et les gros prints (≥ q99 exploratif) déplacent le prix à +30 s DANS leur sens : buys **+0,5 bps (BTC) / +0,6 bps (ETH)**, sells **−0,4 / −0,4 bps** (médianes). Une vague de prints même-signe déplace bien le prix dans son sens : **convention validée et gelée**.
- Volumes : qty en unités base — q50/q90/q99/max = 0,032/0,289/1,92/156 BTC ; 0,61/6,14/51,3/4 760 ETH.

## 1. Hypothèse pré-déclarée (UNE hypothèse de classification, DEUX branches)

Une **baleine** est un print ≥ q99 des tailles de son symbole. Sa réponse de prix immédiate (+5 min) le classe, et la classe prédit le mouvement 4-24 h :

- **AVALÉ** : le print n'a pas déplacé le prix (prix à +5 min dans **±0,10 %** du prix du print) → le mur a mangé la baleine = contrepartie réelle en face → mouvement **CONTRE** le sens du print sur 4-24 h.
- **IMPACTANT** : le prix a bougé **≥ 0,30 % dans le sens** du print à +5 min → la baleine a gagné → **CONTINUATION** dans son sens sur 4-24 h.
- Les deux branches sont **UNE seule hypothèse** : le contrôle inverse (sens des classes échangé) doit être BATTU, sinon la classification ne porte rien.

## 2. Construction (une seule définition, zéro grille, jamais re-tunée)

- **Données** : `aster_tape`, BTCUSDT + ETHUSDT (11 623 115 prints), tri canonique (ts_ms, agg_id).
- **Split 60/40 chrono GLOBAL** : T_split = quantile 60 de TOUS les ts_ms poolés (un seul bornage, non arrondi). Un événement appartient au split de son ts0 ; son trade peut déborder sur l'autre split (sortie forward — aucune fuite vers le passé).
- **Seuil unique** : q99 des tailles **par symbole, calculé sur TRAIN SEULEMENT** (numpy, interpolation linéaire, non arrondi), figé, appliqué tel quel en VAL. **Zéro grille, un seul seuil par symbole.**
- **Événement** : UN print, qty ≥ q99[symbole]. Pas de déduplication, pas de filtre de rafale (les ordres découpés créent des événements corrélés : limitation déclarée, traitée par le garde-fou wallet non-chevauchant).
- **Classification à +5 min (pré-déclarée)** : p5 = prix du PREMIER print avec ts ≥ ts0+300 000 ms ; mesure valide si ce print arrive ≤ ts0+900 000 ms (10 min de tolérance), sinon événement **exclu et compté**. ratio = p5/p0 − 1. **AVALÉ** si |ratio| ≤ 0,0010 ; **IMPACTANT** si ratio×dir ≥ 0,0030 (dir = +1 taker buy, −1 taker sell) ; **tout le reste est exclu et compté** (zone morte 0,10-0,30 % même sens, ou mouvement contraire) — pas de troisième classe tradée.
- **Trade (forward-only)** : entrée **à p5** (prix de classification, observé au moment de la décision), sortie au premier print ≥ ts0+86 400 000 ms (**+24 h**, tolérance 10 min, sinon exclu et compté). **+4 h** = secondaire descriptif. ret_net = dir_trade × (sortie/entrée − 1) − **0,0018** (18 bps A/R). dir_trade : IMPACTANT → +dir ; AVALÉ → −dir. **1x, pas de levier, 0 liq par construction.**
- **Quintiles de taille** : bornes q20/q40/q60/q80 des tailles d'événements TRAIN, **par symbole** (BTC et ETH ne sont pas comparables en taille), rang appliqué tel quel en VAL.
- **Contrôle inverse** : dir_trade flippée (AVALÉ tradée dans le sens du print, IMPACTANT contre) — descriptif par branche, critère sur le poolé.

## 3. Protocole immutable

- Split 60/40 chrono global ; **1x sans levier** ; **coûts 18 bps RT** ; **n train ≥ 100 par classe** sinon « SOUS-PUISSENT » déclaré (échec de puissance ≠ réfutation) ; **BLOC STATS mensuel** obligatoire.
- **Garde-fou doctrine** : courbe **composée séquentielle** (trades composés dans l'ordre des entrées, 1x chacun, 0 liq par construction) vs **somme simple** des ret — le verdict relatif survit aux bugs, l'absolu se méfie ; + variante **non-chevauchante** descriptive (1 position à la fois, premier événement fait foi).
- Limitation déclarée : les événements d'une même rafale sont corrélés (n effectif < n brut).

## 4. Critères PASS/FAIL (écrits AVANT les résultats)

**PASS = les quatre, sans exception :**
1. **n_train ≥ 100 par classe** (AVALÉ et IMPACTANT).
2. **Espérance nette > 0 des DEUX branches en TRAIN ET en VAL** (ret net de +5 min à +24 h, 18 bps déduits) : 4 conditions.
3. **Gradient monotone** : espérance nette poolée (2 branches, sens par classe) **non décroissante Q1→Q5**, sur TRAIN **ET** VAL (bornes TRAIN appliquées telles quelles).
4. **Contrôle inverse battu** : espérance nette poolée FORWARD > espérance poolée INVERSE, sur **TRAIN ET VAL**.

**FAIL = tout le reste** → « FAIL — hypothèse réfutée », gravé au registre, budget consommé, **STOP** : pas de 2e quantile, pas d'horizon alternatif, pas de filtre de réparation. Budget = 1 expérience.

**Si PASS** : verdict CANDIDATE (famille institutions) — le test du wallet séquentiel (`scripts/stacked_portfolio.py run_stack`) reste obligatoire AVANT toute entrée dans le stack ; toute promotion resterait 1x (règle 0-liquidation : levier ≤ 100/(maxMAE+0,5)).

---

# RÉSULTATS (exécution unique du 02/10/2026)

> **Seal du pré-enregistrement** : sha256 du bloc ci-dessus, gelé AVANT exécution :
> `0deb85f1aa49eafdb1db7866dc2be9068eca6481022c8159745ee7869d3ebba3`

Note d'intégrité : deux incidents, **AUCUN seuil/critère/fenêtre/protocole touché**. (1) La 1re exécution comportait un bug de **BORNAGE** (les indices forward j5/j4/j24, portés par le tableau COMPLET ~6,2 M, étaient comparés à `len(idx)` ~65 k → fausse exclusion « fin_data » de 98,7 % des événements, 95 trades de début de tape survivants, span 0 j — auto-évident) : corrigé en comparant à `len(ts)` AVANT toute exploitation des nombres ; l'exécution corrigée est **l'exécution unique de référence**. (2) Un doute de transcription sur une ligne de sortie a déclenché une **ré-exécution bit-à-bit** du même script (zéro modification) : logs identiques octet pour octet (diff nul, `cat -A` vérifié sur les lignes C4) — le calcul gelé est inchangé, la ligne suspecte n'était qu'une corruption de lecture.

## Exécution

- **T_split = 2026-08-24 03:22:42,590 UTC** (quantile 60 des 11 623 115 ts_ms poolés, bornage non arrondi). Seuils TRAIN figés : **q99 = 1,876 BTC / 50,0 ETH** (unités base). Bornes quintiles TRAIN (tailles d'événements) : BTC 2,158/2,641/3,346/4,962 ; ETH 57,67/68,62/91,17/131,33.
- **Événements** (print ≥ q99, zéro grille) : BTC 65 635 (TRAIN 37 955) / ETH 57 413 (TRAIN 31 817) = 123 048. Exclusions : zone morte (0,10-0,30 %) 21 831 BTC / 21 053 ETH, contraire (≥ 0,30 % CONTRE la baleine) 4 940 / 6 017, gap 24 h 349 / 283, fin de donnée 2 / 0, gap 5 min 0 / 0. **Trades retenus : 68 573** (TRAIN 40 706 / VAL 27 867) — AVALÉ 57 880 (84,4 %), IMPACTANT 10 693.
- Tri canonique (ts_ms, agg_id) : reculs 759 BTC / 476 ETH confirmés à l'ordre agg_id ; assertion unité ts_ms OK ; convention is_buyer_maker celle du pré-enregistrement.

## Vérification des critères

| # | Critère (gelé) | Résultat |
|---|---|---|
| — | n_train ≥ 100 par classe | **OK** — AVALÉ 35 302, IMPACTANT 5 404 (VAL 22 578 / 5 289) : réfutation en PLEINE PUISSANCE |
| 1 | Espérance nette > 0 des DEUX branches, TRAIN ET VAL | **FAUX (3/4)** — AVALÉ TRAIN **−0,201 %** (méd −0,191, WR 44,6 %, t −13,5) ET VAL **−0,136 %** (t −9,5) ; IMPACTANT TRAIN +0,242 % (t +4,2) OK mais VAL **−0,171 %** (t −6,0) : la continuation s'INVERSE hors train |
| 2 | Gradient monotone Q1→Q5 (TRAIN ET VAL) | **FAUX** — TRAIN −0,103/−0,186/−0,127/−0,159/−0,134 % ; VAL −0,153/−0,169/−0,163/−0,127/−0,108 % : quintiles PLATS, la taille ne gradient RIEN |
| 3 | Contrôle inverse battu (TRAIN ET VAL) | **OK** (seul critère passé) — poolé TRAIN −0,142 % vs inverse −0,218 % ; VAL −0,143 % vs −0,217 % ; descriptif par branche : IMPACTANT TRAIN +0,242 vs −0,602 (porte tout l'écart), AVALÉ TRAIN −0,201 vs −0,159, VAL −0,136 vs −0,224 |

**VERDICT : FAIL — hypothèse réfutée.** Les deux branches échouent, chacune à sa manière, en pleine puissance (t de −13,5 à +4,2 sur des n de milliers) :

1. **AVALÉ** : la dérive brute 24 h dans le sens de la baleine = **+2 bps (TRAIN) / −4 bps (VAL)** — signe instable, 5-10× sous l'étalon 18 bps. Le mur qui mange la baleine n'annonce PAS de retournement contre elle : le print avalé est du bruit de découpage d'ordre, pas une contrepartie réelle localisable.
2. **IMPACTANT** : la continuation existe en TRAIN (+42 bps bruts 24 h → net +0,242 %) mais **s'évapore en VAL** (+1 bp brut → net −0,171 %) — énième inversion TRAIN/VAL de la maison (cf. exit CVD 28/09). Au secondaire +4 h, TOUT est négatif (même IMPACTANT TRAIN −0,205 %) : l'effet TRAIN se construit APRÈS 4 h, tardif et non robuste.
3. La taille du print ne porte aucun gradient (quintiles plats, les deux splits).

Budget = 1 expérience consommée, **STOP** : pas de 2e quantile, pas d'horizon alternatif, pas de filtre de réparation.

## BLOC STATS mensuel (poolé forward, 1x, 0 liq par construction)

| Mois | Split | n trades | WR | Somme simple | Composé séquentiel |
|---|---|---|---|---|---|
| 2026-07 | TRAIN | 20 909 | 45,4 % | −3 671,6 % | −100,0 % |
| 2026-08 | TRAIN | 19 797 | 45,0 % | −2 101,0 % | −100,0 % |
| 2026-08 | VAL | 6 246 | 44,5 % | −1 279,4 % | −100,0 % |
| 2026-09 | VAL | 21 621 | 46,2 % | −2 695,9 % | −100,0 % |

Global 90 j : somme simple **−9 748 %**, courbe composée séquentielle **−100 %** (DD 100 %), **4/4 lignes mois-split négatives**. **Lecture du garde-fou** : ~20 k trades/mois SE CHEVAUCHENT (chaque événement = position 1x indépendante tenue 24 h) — composer séquentiellement des signaux simultanés sur le même capital est un artefact d'accounting, pas un wallet. Le wallet RÉALISTE (non-chevauchant, 1 position à la fois, premier événement fait foi) : **TRAIN n=52, −16,3 %, WR 42,3 %, DD 22,3 % ; VAL n=38, −8,1 %, WR 50,0 %, DD 10,9 %** — négatif des deux côtés, conforme au FAIL. **0 liq partout** (1x, pas de levier — 0 par construction).

## Leçon gravée

Sur le tape Aster (BTC/ETH, 11,6 M prints, 90 j), **la trace de la baleine individuelle ne prédit rien de tradable à 4-24 h** — ni le retournement (absorption) ni la continuation ne répliquent hors train, et la taille ne gradient rien. Avec H1 (agrégats CVD, NUL 27/09) et les clusters block trades (fade +30 min, CONTEXTE 28/09), le tape ne porte l'information **ni en agrégat, ni en cluster, ni en print individuel** : le ≥ q99 est majoritairement du découpage d'ordre (les rafales créent ~84 % d'événements AVALÉ corrélés, n effectif ≪ n brut). Famille institutions : 1/5. Toute réouverture = pré-enregistrement nouveau (PARAMETER_MUTATION interdite).

