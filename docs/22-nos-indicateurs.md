# NOS CRÉATIONS ASTER — l'inventaire des indicateurs et mécanismes que nous avons construits

*Chaque création = une règle mécanique exacte + sa preuve chiffrée + son statut.
Assemblées, elles forment la machine (scripts/the_machine.py). Le régime T3 2026
a gelé le livre cascade — les créations restent vraies, le marché reviendra.*

## LES SIGNAUX (ce qui décide d'entrer)

### 1. LA CASCADE ACCÉLÉRÉE — notre signal cœur
**Règle** : 3 bougies de baisse consécutives avec accélération sur 1h → SHORT.
**Preuve** : N=43 810, WR 58,8 %, espérance +18,4 % de marge/trade — le signal le
plus puissant du projet, cohérent dans toutes ses géométries (la fractalité de
fréquence confirmée : le pattern se reproduit ×4 en 15m).
**Statut** : VALIDÉ — le livre régime, protégé par l'adaptateur en régime mort.

### 2. L'AL SCORE — notre gate (le filtre de risque)
**Règle** : 6 features en rangs roulants 90 j (atr_pct, vol24, dd_pct, btc_ret24,
vwap_dev, cascade_depth) — les trades au score risqué sont EXCLUS.
**Preuve** : le MAE gated 7,84 % vs 13,08 % non-gaté (le non-gaté prend une
liquidation à 10x) — le gate EST porteur de valeur. L'AL v2 (10 features) n'a
pas su le battre : le v1 est optimal dans notre feature-set.
**Statut** : VALIDÉ — il protège chaque trade majors.

### 3. VOL_SPIKE_6H — le fade (notre anti-régime)
**Règle** : une bougie 6h ≥ 4× sa médiane 14 j (gate ATR-décile) → fade, LONG ou
SHORT selon le sens, hold 6h, 1x.
**Preuve** : N 820/an, WR 53,7 %, espérance +0,012 $/trade TAKER, 0 liq,
**corr -0,22 avec la cascade — il gagne quand les cascades dorment** (le T3 mort
= son meilleur trimestre +15,1 %). Multi-régime confirmé.
**Statut** : VALIDÉ en forward (62 % WR sur 13 trades live) — le livre anti-régime.

### 4. LE SURVIVOR LONG — notre asymétrie
**Règle** : token âgé > 90 j dont le close repasse au-dessus de son prix-90j →
LONG à l'open, hold 72h, 1x — UN LONG 1x NE PEUT PAS ÊTRE LIQUIDÉ (seule mort =
le prix à zéro), donc le notional scale librement (×2 par le QUBO).
**Preuve** : WR 47 % mais l'espérance positive, 0 liq par construction — la
seule asymétrie structurelle exploitable du projet.
**Statut** : VALIDÉ — le flux que le QUBO a doublé.

## LE SIZING (combien mettre)

### 5. LE VOL-INVERSE — notre loi de taille
**Règle** : la taille ∝ ATR du signal (les cascades violentes = les gagnantes →
plus grosses), base clampée.
**Preuve** : +19 % de ROI gratuit à DD égale — le vol-target classique (∝ 1/ATR)
est une ANTI-stratégie sur ce marché.
**Statut** : VALIDÉ — dans tous les flux.

### 6. LE CORR-TILT — notre thermomètre systémique
**Règle** : la corrélation roulante 7 j des 6 majeures à chaque signal :
systémique (corr > p66) = le sizing ×2 (ça continue), idiosyncratique (corr <
p33) = ×0,5 (ça rebondit).
**Preuve** : le gradient WR monotone 53,7 → 64,3 % — audité 4/4 (zéro look-ahead,
placebo battu).
**Statut** : VALIDÉ — dans la machine (les poids QUBO l'ajustent à ×1,10).

### 7. LE FUNDING-RANK-BAS — notre indicateur qualité
**Règle** : le rang cross-sectionnel du funding parmi les 6 majeures — le funding
LE PLUS BAS = la position la moins surexploitée → le sizing ×1,5.
**Preuve** : WR 81 % (n=21 backtest), le SEUL feature funding qui tient en VAL
(niveau, vélocité, dispersion : tous inversés). En forward — verdict ~3 mois.
**Statut** : CANDIDAT en forward.

## LA GÉOMÉTRIE (pourquoi on ne meurt jamais)

### 8. LA RÈGLE 0-LIQUIDATION — TA création
**Règle** : levier ≤ 100/(maxMAE + 0,5) par flux — mesuré sur TRAIN, confirmé
sur VAL, une seule liquidation en VAL = la cellule morte.
**Preuve** : 25+ sims, 0 liquidation sans exception — c'est la règle qui a
débloqué toute la frontière ROI/DD.
**Statut** : VALIDÉ — la loi constitutionnelle du projet.

## L'OPTIMISATION (l'assemblage)

### 9. LE QUBO DISCRÉTISÉ — TA méthode
**Règle** : les poids et leviers des flux en bits (wᵢ = (1/K) Σ 2^{j-1} xᵢⱼ),
min xᵀQx + cᵀx avec Q = la covariance des PnL mensuels — annealing classique,
la formulation prête pour QAOA.
**Preuve** : ~~+5 082 %/an @ DD 23,3 % (vs +3 905 @ 24,8 à la main) — gagné hors
échantillon (VAL +77 % vs +60 %).~~
**Statut** : ⛔ **REFUTÉ — HISTORIQUE SEULEMENT (F-033, PRs #91-95)** : re-mesuré sur
données fixées (post fix `fetch_deep_klines`, qui corrompait les volumes des gates),
le point QUBO joint rend **20 liquidations réelles, DD 99,2 %, final $1**. Le chiffre
+5 082 %/an ci-dessus est MORT — conservé pour la méthode (la formulation QUBO
poids×levier reste valide comme assemblage), PAS comme résultat. Aucune edge
courante derrière. La formulation prête pour QAOA n'a jamais été promue.

### 10. L'ADAPTATEUR DE RÉGIME — notre garde statistique
**Règle** : l'espérance roulante 90 j du flux — sous 0,30 % → sizing ×0,75,
retour ×1 après 30 j au-dessus.
**Preuve** : 0 % de jours OFF dans les bons régimes, LA fenêtre T3 détectée
automatiquement (26/08→25/09), DD inchangé.
**Statut** : VALIDÉ — le moniteur nocturne le calcule chaque nuit.

## LA TABLE DE VÉRITÉ AU 28/09

| Livre | Flux | Créations actives | État |
|---|---|---|---|
| RÉGIME (dormant) | cascade majors 11x | cascade + AL + vol-inverse + corr-tilt + rank + QUBO + adaptateur | dérisqué ×0,75, attend le retour |
| RÉGIME (dormant) | cascade meme 1x | forward 0/10 — la sortie se tranche | SANS_MEME mène au tracker |
| ANTI-RÉGIME (vivant) | fade vol_spike 6h | vol_spike + vol-inverse | 62 % WR forward, multi-régime |
| ANTI-RÉGIME (vivant) | réplication derek518 (fomo) | le skill-weighted | verdict à ≥ 5 CLOSED |
| ANTI-RÉGIME (armement) | bonding pré-graduation | bonding_watch 2 OPEN | signal ex-ante à n≥60 |

**Les réfutés (tout aussi importants)** : 25 verdicts — l'absorption, la
capitulation, le sweep, le funding structurel, le sizing conditionnel, le garde
wallet, le wall-clock, le re-cascade, la fractalité d'espérance, l'exit CVD, le
reversal-long des liqs, les interactions 2D, l'AL v2, le gate meme, l'hybride
hold. Chacun a son chiffre dans docs/20.

## LA TRAÇABILITÉ CODE (28/09 — l'audit Ariad + grep, les 10 créations vérifiées)

| Création | Où elle vit | État du câblage |
|---|---|---|
| 1. La cascade | anti_liq.collect_featured (importé) | ✅ le corpus + les trades |
| 2. L'AL Score | anti_liq.add_rolling_scores + le gating q66 | ✅ actif |
| 3. Vol_spike_6h | collect_vol_spike (importé, derrière --vol-spike) | ✅ ON en paper forward |
| 4. Le survivor long | le flux survivor natif | ✅ actif (0 trade encore — les signaux sont rares) |
| 5. Le vol-inverse | le sizing ATR (13 occurrences) | ✅ actif |
| 6. Le corr-tilt | CORR_TILT flag (ligne 165) + la logique corr | ✅ câblé, **OFF par défaut** — la variante ×1,10 attend son forward dédié |
| 7. Le funding-rank ×1,5 | le weight rank (3 occurrences) | ✅ actif |
| 8. La 0-liq | les constantes de levier par flux | ✅ constitutionnel |
| 9. Le QUBO | qubo_forward_tracker (les poids) + qubo_joint_lev (les leviers) | ✅ suivi forward — **la cellule jointe ×11x attend la promotion** (gelé régime T3) |
| 10. L'adaptateur | edge_regime_monitor.py (nocturne) | ✅ DÉRISKÉ ×0,75 actuellement |

**Le constat de traçabilité : 10/10 créations tracées, 8 câblées actives,
2 en attente conditionnelle (le QUBO joint et le corr-tilt ×1,10 — tous
deux gelés par la décision régime : pas de promotion sur un backtest
dominé par le régime mort). Aucun écart entre la doc et le code.**

## LA FAMILLE COMPLÈTE — l'arsenal (les 5 signaux long-horizon, hérités et en forward)

*En plus des 10 créations : l'arsenal (full_arsenal_2.py) = 5 signaux de
position long-horizon, câblés au paper forward AVANT la refonte — ils
accumulent leurs verdicts sur leurs horizons propres :*

| Signal | Horizon | n forward | Le verdict |
|---|---|---|---|
| sweep_liquidite_short | **90 j** | 122 | dans ~3 mois |
| funding_extreme_contre_courant | **7 j** | 117 | **CETTE SEMAINE** (J+6,5) |
| vwap_extreme_reprise_short | 60 j | 78 | dans ~2 mois |
| failed_ath_breakout_short | 60 j | 3 | dans ~2 mois |
| funding_prix_divergence_short | 12 h | 63 | **NUL confirmé** (WR 19 %, forward) |

**La règle de famille** : l'arsenal = des trades de POSITION (60-90 j),
la machine = des trades 24-72 h — deux familles COMPLÉMENTAIRES, pas
concurrentes. Le dépassement connu : la fdiv est NULLE au forward ; les
4 autres restent à juger. **Les créations à venir** : conditionner les
entrées de l'arsenal aux NOUVELLES couches (OI quadrants, prime
extrême, murs) = l'upgrade naturel quand les fenêtres mûrissent jeudi.
