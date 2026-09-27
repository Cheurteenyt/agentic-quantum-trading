# 20 — Registre des indicateurs & stratégies

**La règle de gestion** : chaque indicateur a UN statut (VALIDÉ / CANDIDAT /
CONTEXTE / NUL), un script, une date de verdict et des chiffres. Tout verdict
passe par la chaîne complète : backtest pré-enregistré → baseline anti-dérive →
train/val par le temps → wallet séquentiel → CONTRÔLE INVERSE → BLOC STATS.
Après tout fix d'échelle ou d'unité, les ABSOLUS sont re-mesurés (les relatifs
tiennent). On ne supprime jamais : on re-catégorise.

Dernière re-mesure globale : **25/09 soir, après le fix d'unité ts_ms (ns)**.
Les chiffres ci-dessous sont les chiffres corrigés.

## VALIDÉS (la frontière)

| Indicateur / stratégie | Script | Chiffres (100 $, 1 an, maker) | Verdict |
|---|---|---|---|
| **CANDIDAT QUALITÉ : cascade ∩ funding-rank-BAS** (le symbole au funding le plus bas des 6 majeures à l'instant du signal) | testé inline 25/09, à câbler au paper forward | **WR 81,0 % (n=21), DD 5,4 %, 0 liq**, +106 %/an — la spec du user (80 % WR / peu de DD / 0 liq) TOUCHÉE ; mécanisme : les shorts déjà entassés + le prix tombe quand même = offre réelle, pas de la foule | CANDIDAT — N=21, tercile post-hoc, le forward 2×/jour juge (~2 trades/mois) |
| **LA MACHINE — cascade gated 10x, 0 liq par construction, DEUX knobs (marge + sizing vol-inverse)** | `anti_liq.py` + `portfolio_sim.py` + `stacked_portfolio.py` | **SIZING VOL-INVERSE (base 24 %) : +1 498 %/an @ DD 27,8 %, 0 liq** — +19 % vs le fixed à DD égale. L'échelle : base 30 % → +2 655 %/an @ DD 34,7 %, record mois **+100,2 %** · base 60 % équivalents — WR 57,3 %, 3 mois négatifs | **LA frontière** — size ∝ ATR : les cascades à haute volatilité sont les gagnantes (loi vol_haute confirmée 3×) ; le sizing standard (∝ 1/ATR) est REFUTÉ ici (ratio 12,9 vs 53,9) |
| **La dimension sizing** | `stacked_portfolio.py` (size_fn à état : balance, dd) | vol-target standard ∝ 1/ATR : ratio 12,9 (réfuté) ; dd-throttle : coupe les rattrapages gagnants, ratio 6,5 (réfuté) | Le montant investi PAR trade est une dimension d'edge, pas un détail |
| **Cascade accélérée short 10x + AL gate (sizing fixe)** | `anti_liq.py` + `portfolio_sim.py` | fixed 30 % : +1 258 %/an @ DD 28,1 %, 0 liq, record +76,8 % | La référence sans sizing dynamique |
| **AL Score** (anti-liquidation, rangs roulants 90j, 6 features) | `anti_liq.py` | gradient monotone 4,1→19,9 % de liqs ; le gate exclut les monstres MAE 13 % | Le garde mécanique du 0-liq |
| Confluence exacte v5 (accel + vwap 3σ) | `confluence_exact.py` | MAE max 52,8 % → levier mécanique **1x** ; seule à 1x : +3,1 % @ DD 5,5 %, WR 65,5 % | CONTEXTE — hors machine 10x |
| Flux lents (fdiv 12h + conf) | `stacked_portfolio.py` | MAE max 53-56 % → levier mécanique **1x** ; à taille utile ils dragent le noyau | CONTEXTE — retraités par l'audit mécanique |

## CANDIDATS (forward en cours — le paper forward tranche)

| Composant | Script | État |
|---|---|---|
| confluence +24h (composante restante du stack, forward encore ouvert) | `stacked_portfolio.py` | Réhabilitée post-fix (quasi-plate, DD 5-6 %) — valeur = la décorrélation ; paper forward 2×/jour tranche (fdiv, l'autre composante, est passée NUL le 27/09 — voir NULS) |
| **Frontière tilt × meme** (multiplicateur tilt corr p66/p33 ×1,10 + notional meme ×0,5 sur la config codifiée) | `tilt_frontier.py` | +2 710 %/an @ DD 27,2 %, 0 liq, 1 mois nég, record +77,5 %, pire -3,8 % ; garde-fous OK sur 23 points ; **CANDIDAT** — câblage au paper forward avant promotion VALIDÉ (la config codifiée +2 653 % @ 24,8 % reste la référence jusqu'au verdict) |
| LIQ-STORM (tempêtes de liquidations) | `liq_storm.py` | Descriptif ; ratio long/short 2,0× ; backtest à 3-4 semaines |
| whale_flow × prix (flux skill-weighted) | `whale_flow.py` | J+14 ≈ 8/10 |

## NULS (fermés, avec la preuve)

| Piste | Chiffre qui la ferme | Date |
|---|---|---|
| **funding_divergence +12h (short continuation)** — DÉGRADÉ du CANDIDAT | Forward (paper, 63 fermés) : **WR 19,0 % (12/63), -3,12 %/trade, cumulé -196,7 %** vs backtest WR net 43,4 % (VAL temporelle 39,1 %, -0,84 %/trade) — binomial exact p = **4,3e-05**, Welch t = -3,9 : dégradation RÉELLE, pas le bruit d'un petit N ; déjà net-négatif en backtest à taker (-0,39 %/trade) — re-catégorisé, PAS supprimé (l'entrée historique reste ci-dessus et au registre du 26/09) | 27/09 |
| Sorties anticipées TOUTES (1re verte, trailing 1/1,5/2,5 %) | monotone : trail 1 % -46 % → 24h fixe +197 % — chaque sortie sur rebond abandonne le drift | 25/09 |
| EXTENSIONS des gagnants (48h/72h si gagne) | $297 → $250-$235 : le bounce de jours 2-3 à 20x mange le drift supplémentaire — 24h pile est l'optimum total | 25/09 |
| Squeeze haussier (miroir de la cascade) | wallet $6,34, WR 44,9 %, détruit le stack | 25/09 |
| Exit première verte (épuisement) | hold moyen 1,8 h, -5 % vs +197 % — les bounces sont micro, le drift domine à 24h | 25/09 |
| Cascade × funding percentile | NUL même série profonde ; l'inverse gagne = anti-signal | 25/09 |
| **STRUCTURE funding (velocity 8h/24h, dispersion cross-section, level)** — `funding_dimension_study.py` | gradient map ex-ante sur 165 cascades gated (train 115/val 50, seuils TRAIN) : dispersion INVERSE (TRAIN T3 +10,8 → VAL T3 −0,3, non-monotone), velocity_8h garde sa direction d'espérance (VAL T1 +5,9 → T3 +1,6, liqs 17 % en T3 VAL) mais rate la barre pré-enregistrée (gap WR VAL < 5 pts, buckets n=12-20), level INVERSE (confirme fund7). Sizing ×{0.75,1,1.25} funding_rank : $2 916 vs baseline $4 005 (contrôle inverse $5 361 = chance de chemin, ambigu → non-adoptable) ; diagnostic velocity : $3 173, échoue aussi | 27/09 |
| 20x taker (directionnel) | frais 5,6 % marge/RT ; -60 %/an | 24/09 |
| Memecoins à 20x | 26-43 % liquidés = loterie, même avec AL Score | 24/09 |
| Foule X (calls publics) | WR 50 % pile, inverse symétrique | 23/09 |
| Indicateurs classiques (RSI/MACD/Donchian/…) | 0 confirmé sur 403 combos | 23/09 |
| Funding dump (règlements chauds) | le prix MONTE après — mythe | 24/09 |
| Gate baissier obligatoire | +1,9 pt seulement (~2σ) — garder le gate anti-massacre en contexte | 24/09 |

## CONTEXTES (outils de lecture, pas des signaux)

- **Carte de cycle de vie** (âge × drawdown, `backtest_lifecycle.py`) : 30-90j/20-50 % SHORT 65,4 % ; 0-7j/près-ATH LONG 55,5 %.
- **L'inversion de carte** : sur les MAJEURES, la cascade fiable part PRÈS de l'ATH (dd ≤ 41 % : 62,3 % WR) — l'inverse des memecoins (dd 20-50 %). Variante conservatrice « T1 only » : +80 %/an @ DD 10,2 %, 4 liqs.
- **Baseline blind** (short 1h→90j 41,8→71 % ; blind long majeures 24h = drift quasi nul -0,08 %/trade).
- **Régime BTC** (`regime_filter.py`) : quadrant haussier/vol_haute = massacre 28,5 % WR (~4,7σ) — à éviter, pas à gate.
- **LCS composite** (≥75 → 55,4 % short 24h) : gradient validé, usage filtre.

## COLLECTEURS (la matière première)

| Série | Collector | Couverture |
|---|---|---|
| funding_history (profonde ✓) | `funding_history_collector.py` | 71 symboles, 2023→aujourd'hui, +52 222 records le 25/09 |
| liq_events (forceOrder 24/7) | `liq_collector.py` | depuis 21/09 — backtest mi-octobre |
| depth.db (carnet 15 symboles) | `depth_collector.py` | 1 Go — ré-éval maker à J+14 |
| paper_trades (le juge) | `paper_forward.py` 2×/jour | 8 candidats v5, ledger cumulatif |
| ticks fomo 24/7 | `fomo_tick_collector.py` | 1m agrégée des ticks, rotation pages, watchdog |

### durcissement data fomo 26-27/09

- **Filtre QUOTE_MINTS** : SOL wrappé / WETH Wormhole / cbBTC / stables n'étaient pas des tokens fomo et polluaient la DB (purgés, filtrés à la source + flock anti-orphan dans le tick collector).
- **Bug GT 1h** : l'URL `ohlcv/minute?aggregate=60` est invalide (GT n'accepte que 1/5/15 sur minute) → mapping `_TF` {1m,5m,15m→minute, 1h/4h→hour, 1d→day} ; bootstrap 1h en cours.
- **Backfill master durci** : arrêt systemd VÉRIFIÉ avant la fenêtre exclusive + top-up sélectif (tokens frais <2h skippés → les prochaines passes durent 1-3 min au lieu de 30).

## Les gisements datés

- **Mi-octobre** : backtest des tempêtes de liquidations.
- **~6/10** : depth.db en coûts maker-only (la porte micro-structure du 20x).
- **~8/10** : corrélation whale_flow d'hier × prix d'aujourd'hui.
- **Chaque nuit 03h01** : la machine (63+ étapes) + paper_forward aussi à 14h00.

## Leçons gravées

1. Les verdicts RELATIFS survivent aux bugs d'unité partagés ; les ABSOLUS non.
2. Un pattern long-horizon n'est pas une stratégie levée — le chemin décide.
3. La première verte / le re-break / le squeeze : chaque rebond micro est un faux signal de fin.
4. Le maker (GTX) n'est pas une option — c'est la condition d'existence du 20x.
5. Cross-check deux implémentations indépendantes sur les mêmes événements avant de croire un chiffre.

## 27/09 — la frontière tilt × meme (tilt_frontier.py) + les preuves forward meme/fdiv

| Verdict | Détail | Catégorie |
|---|---|---|
| **Frontière du multiplicateur tilt** (corr p66/p33 v4 INCHANGÉS sur 70 % train, seul le multiplicateur bouge, meme ∈ {1, 0.5, 0}) | 23 points, TOUS 0 liq, garde-fous composé/PnL OK partout. Baseline reproduite à l'identique (+2 653 % @ 24,8). Tilt ×0,5 (INVERSE : booster corr bas) = TOXIQUE (+1 850 % @ DD 35,3 %). Sommet ≤ 28 % DD : **×1,10 → +2 779 % @ 27,2 %** ; ×1,2 saute à 29,7 %, ×1,5-2,0 = 30,9 %. Le chemin codifié ×2/×0,5 donne +4 006 % @ 30,9 %, 0 mois nég — l'audit cité +8 560 % @ 34,8 % n'est réproductible par AUCUNE variante (sans plafond : DD 49,5 %) : chiffre non archivé, le chiffrage tilt_frontier fait foi | FRONTIÈRE — point final recommandé **tilt ×1,10 + meme ×0,5 : +2 710 %/an @ DD 27,2 %, 1 mois nég, record +77,5 %, pire -3,8 %, 0 liq** (si DD ≤ 25 strict : tilt ×0 + meme ×0,5 = +2 587 % @ 24,7 %) |
| **Réduction meme (preuve forward)** | machine_cascade_meme forward : **9 fermés, 0 gagnant, -48,8 % cumulé** (22→25/09) vs backtest WR 51,4 % → P(0/9) = **0,0015** — significatif, confirme le DÉGRADÉ (edge mort depuis juin). Backtest : ×0,5 coûte 66 pts/an et garde 1 mois nég ; ×0,0 coûte 184 pts ET AJOUTE un mois négatif (2) — l'année backtest contient l'edge pré-juin → **×0,5 recommandé, ×0 refusé en l'état** | RÉDUCTION APPLIQUÉE AU CANDIDAT |
| **fdiv : N suffisant, dégradation significative** | binomial p = 4,3e-05 (<< 0,01) sur 63 trades : ce n'est PAS le bruit d'un petit N. La VAL temporelle du backtest déclinait déjà (WR 39,1 %, -0,84 %/trade) ; le forward la prolonge (-3,12 %/trade). fdiv → **NUL** (re-catégorisé, preuve datée) | NUL (dégradé du CANDIDAT) |

Rapport : reports/tilt-frontier-meme-2026-09-27.md (script : scripts/tilt_frontier.py — n'importe QUE les briques, the_machine.py intact).

## 27/09 — session parallèle (3 agents Aster) : vol_spike PASS, flux meme affaibli, autopsie des mois

| Verdict | Détail | Catégorie |
|---|---|---|
| **vol_spike_6h** (fade du range ≥ 4× médiane 14j, gate ATR, 1x, hold 6h) | N 820/an (68/mois), WR 53,7 %, espérance +0,012 $/trade TAKER, 0 liq, **corr cascade -0,22 = anti-corrélé**, remplit les mois creux (juil +0,88, août +4,20, sept +1,45 $) | **CANDIDAT** — câbler au paper forward nocturne (sizing vol-inverse), croiser fill-rate maker × depth à J+14 |
| funding_sat (queue du funding 8h/24h) | positif NEET maker seulement (+0,005/+0,010 $), corr +0,07-0,15 | CONTEXTE — thin, maker-only |
| dd_cross 24h/72h (traversées de carte à 1x) | espérance négative, le 72h attrape le squeeze LAB, < 10 trades/mois | **NUL** — confirme la monétisation non-triviale de la transition de carte |
| vol_spike_12h | espérance négative taker | **NUL** — seul le 6h tient |
| **Carte hold × levier memecoins** (cascade meme, réplication exacte the_machine 2 022 evts) | MAE explose 96→224→260→538 % (6h→72h) — sub-1x requis dès 24h pour 0-liq ; le 1x actuel esquive les 3 tueurs/an PAR CHANCE ; **VAL négative 3 cellules/4 (24h : train +8,8 % → val -5,8 %), l'edge s'est évaporé depuis juin 2026** | **DÉGRADÉ** — ne PAS lever ; réduction/gate régime à étudier ; re-carto après 1 mois de fraîcheur |
| **Autopsie des mois négatifs** (n=1 strict : 2026-01 -5,5 % ; faibles : 07/09 +7,5 %) | séparateurs : fund7 (d +0,98, le mois négatif = 3e funding le plus haut de l'année), fresh-peak au 1er du mois (d -0,72) ; **corr7 NE sépare PAS** (hypothèse naïve rejetée) | PROFIL indicatif n=1 — hypothèse fund7 ≥ p75 (~0,0039 %/8h) pour la sonde P3 en octobre, PAS un gate |

| **vol_spike_meme** (extension de vol_spike_6h à l'univers memecoin, seuils p5 intouchés) | N 809/an (67/mois), WR 53,3 %, espérance +0,009 $ taker / +0,022 $ maker, MAE max 6h 94,7 % (p99 40 %) → lev sûr 1,05x, **0 liq** wallet séquentiel ; **corr cascade_meme -0,50, majors -0,35 = décorrelé des DEUX cascades** (pas un doublon, chevauchement détention 30 %) ; TRAIN 53,0 % → VAL 54,0 %, VAL renforce ; MAJEURS = ~1 % du flux global (809/820) : **vol_spike_6h EST un flux memecoin** | **CANDIDAT (confirmé)** — pas de créneau stack séparé : c'est le même flux que le vol_spike_6h déjà câblé ; précision d'univers pour le paper forward et les poids QUBO |

Rapports : reports/p5-frequency-streams-2026-09-27.md, reports/carte-hold-levier-memes-2026-09-27.md, reports/autopsie-mois-negatifs-2026-09-27.md, reports/volspike-meme-2026-09-27.md.

## 27/09 — lifecycle v2 sur le corpus profond (backfill mobula : 386k bougies, 34 tokens, 1h→avr 2024)

| Verdict | Détail | Catégorie |
|---|---|---|
| **Sortie mécanique temps fixe** (hold 24-72h à la naissance, launches n=20, entree=close 1re bougie non plate) | hold24h médian 1,60x WR 65 % / hold72h médian 1,47x WR 65 % moyenne 47x ≥2x 45 % / pire trade 0,007x (rug AAPL) — les 3 fixes dominent trailing -35 % (méd 0,99x WR 45 %) et -50 % du pic (méd 0,98x WR 40 %) ; le trailing ne sert qu'à plafonner le pire (0,043x vs 0,007x) | **CANDIDAT** — l'hypothèse v1 « tenir ~2 jours puis sortir mécaniquement » CONFIRMÉE ; 72h maximise la queue droite, 24h le médian/WR ; passer run_stack avant tout câblage |
| Trailing/drawdown comme sortie principale sur launches | médian ~1,0x, WR 37-45 % : les dips de 35-50 % dès la 1re heure font sortir avant le pump | **CONTEXTE** — utilisation possible en garde anti-rug (plafonne le pire cas), pas comme sortie d'EV |
| Lifecycle v2 corpus profond (launches n=13, ≥14 j) | pic médian 15,1x (ensemble 10,8x vs 3,18x v1), ≥2x 84 %, pic ≤72h 30 %, give-back médian 83 %, survie 13/13 actifs ; cohorte post-juin pic méd 14,0x / pré-juin 3,4x | **CONTEXTE** — métriques de référence ; multiples = bornes HAUTES (survivorship : morts-nés absents, entrée à la 1re minute = délai collector non modélisé) |
| Données mobula | AMBA 1m/15m : cassure d'unité (bougies ~1566 $ vs 0,0012 $) → 65 bougies jetées ; WETH 1h : 6 mèches non soutenues (high 13210 vs ~3100) réparées ; 7STOCK : 2 bougies seulement, print à 4,65e-12 $ | **NUL** (telles quelles) — nettoyer avant tout backtest 1m/15m mobula : filtre voisin-based dans scripts/fomo_lifecycle_v2.py |

Rapport : reports/fomo-lifecycle-v2-2026-09-27.md (script : scripts/fomo_lifecycle_v2.py). v1 (corpus court) re-catégorisé : ses métriques 15m sous-estimaient les pumps <15 min (AMBA 1,14x → 92,9x) et bornaient le délai au pic (51,5h → 871,5h).

## 27/09 — H1 absorption (buy_ratio) : FAIL strict, aucun sizing branché (h1_absorption_test.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **buy_ratio** (taker_buy_volume/volume, moyenne des 4 bougies 1h avant le signal cascade) — H1 pré-enregistrée dans flow-audit-2026-09-27 AVANT le backfill CVD | Corpus 230 events majors (collect_featured + add_rolling_scores, sélection sim, hold 24h ; le 165 historique a grossi avec la data), split 70/30 PAR LE TEMPS (161/69), coupures quartiles TRAIN 0.477/0.492/0.502 — dispersion minuscule : la moyenne 4 barres lave les spikes d'absorption. MAE moyen Q1→Q4 TRAIN **1.98/1.88/1.93/1.96** (plat, Spearman −0.05 : ne tient MÊME PAS en TRAIN) ; VAL **2.69/1.93/0.92/1.69** (Spearman −0.209, hint INVERSE non pré-enregistré, n=8–28/cellule). Liq @9.5 % : 0/161 TRAIN, 1/69 VAL. Espérance marge @10x maker TRAIN : Q4 +0.2 vs Q2 +9.0. Machine 4 flux NON branchée (sizing ×0.75/1.0/1.25 refusé — pas de gradient) | **NUL** — H1 close ; le hint inverse va au CONTEXTE de H2 (divergence delta), jamais en gate |

Rapport : reports/h1-absorption-2026-09-27.md (script : scripts/h1_absorption_test.py — the_machine.py intact, klines.db lecture-seule).

## 27/09 — H2 divergence delta + H3 sweep volumique : FAIL tous les deux, aucun sizing branché (h2_h3_cvd_test.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **pente_cvd** (régression linéaire du delta cumulé 2×taker_buy−vol sur les 6 bougies 1h avant l'entrée, normalisée par le vol moyen × flag nouveau-bas = close signal = min des 24 closes) — H2 pré-enregistrée dans flow-audit-2026-09-27 | Même corpus 230 events majors, split 70/30 par le temps (161/69), zone morte ≈0 = q33 des \|pentes\| TRAIN (0,0131). Ordre de danger déclaré : (0,nég)<(0,≈0)<(1,nég)<(1,≈0)<(0,pos)<(1,pos). MAE TRAIN le long de l'ordre **1.77/1.50/2.48/2.53/1.85/1.87** (NON monotone dès le 2e maillon), VAL **1.99/1.51/3.10/1.42/1.57/1.93** (NON). Cellule divergence (NL=1×pos) : n=3 TRAIN / 7 VAL — trop vide pour trancher ; Spearman pente×MAE −0.087 tr / −0.123 va (sens inverse du déclaré). Machine 4 flux NON branchée | **NUL** — H2 close ; hint post-hoc H2bis (nouveau-bas × pente CVD < −dz = capitulation → MAE haut : TRAIN 2.48 %/exp −0.9 n=30, VAL 3.10 %/1 liq/WR 33.3 %/exp −17.8 n=12) = **CONTEXTE**, à pré-enregistrer avant re-test |
| **sweep_vol** (low d'une des 6 bougies avant l'entrée casse le plus-bas des 48h avec volume >2× sa moyenne 20) — H3 pré-enregistrée dans flow-audit-2026-09-27 | Même corpus ; outcome = max(high 4-12h post-entrée) − entrée. Buckets bounce no-sweep→2-3×→3-5×→≥5× : TRAIN **0.97/1.62/1.08/−0.39** (NON monotone, la queue ≥5× est NÉGATIVE), VAL **1.15/0.98/2.77/1.03** (NON). n buckets 3-5×/≥5× = 3-4/split — sous-puissant ET direction instable | **NUL** — H3 close ; hint post-hoc H3bis (sweep ≥2× → MAE 24h du short : TRAIN 2.66 vs 1.84 %, VAL 3.00 vs 1.84 %, espérance VAL sweep négative −27.3/−13.7/−6.6) = **CONTEXTE**, à pré-enregistrer avant re-test |

Rapport : reports/h2-h3-cvd-2026-09-27.md (script : scripts/h2_h3_cvd_test.py — the_machine.py intact, klines.db 1h lecture-seule, backfill 15m non touché). Leçon confirmée : la dynamique (pente/divergence) bat la moyenne, mais la FORME prédite à l'avance reste la seule publiable — les 2 hints inversés attendent leur pré-enregistrement.

## 27/09 très tard — QUBO des poids (CANDIDAT) + wall-clock (CONTEXTE)

| Verdict | Détail | Catégorie |
|---|---|---|
| **QUBO discrétisé des poids** (Markowitz discretisé, m=3 bits/flux, Q = covariance des PnL mensuels TRAIN, annealing classique — la formulation se branche telle quelle sur QAOA ; QAE/QITE = pricing d'options = pas notre marché) | poids trouvés [majors 0,857, meme 0,857, survivor 2,0, vol_spike 1,143] ; annealing = grille exhaustive convergents 14/14 λ ; choix TRAIN uniquement (μ,Σ 9 mois, split 10/06/26) ; **VAL : +77,1 % vs main +59,9 % — hors échantillon gagné** ; **FULL : $4 639 (+4 539 %/an @ DD 23,4 %, 0 liq, 1 nég) vs $4 005 (+3 905 @ 24,8)** — +634 pts à DD PLUS BAS ; trade-off : record +78,7 % (< cible 80 %), pire mois -14,4 % | **CANDIDAT** — paper-forward 2-4 semaines des poids QUBO en parallèle de la config main avant promotion ; m=4 bits ensuite |
| wall-clock des cascades (l'heure d'entrée UTC, buckets 4h) | rho rangs TRAIN→VAL 0,60 mais incohérent entre années (rho -0,10 — le gradient TRAIN = un artefact du régime 2025) ; la fenêtre funding ±1h : signe qui bascule ; ±28 pts de WR détectables/bucket, aucun p<0,10 | **CONTEXTE** — le hint H2/H3 est enterré |

Rapports : reports/qubo-sizing-2026-09-27.md, reports/wallclock-cascades-2026-09-27.md.

## 27/09 nuit — garde drawdown du WALLET (désengagement prop-firm) : NUL, 0/12 cellules (wallet_dd_guard.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **garde wallet DD** (taille ×r quand DD wallet > S, retour sous S/2 hystérésis — 6 cellules S∈{10,15,20}/r∈{0.5,0.75}, 2 configs machine+QUBO, split 10/06/26) | Baselines reproduites bit-exact ($4 004,94 / $4 639,13). Coût de garde NÉGATIF sur 12/12 : les trades taillés sont des GAGNANTS (le rebond) — ex machine S=10/r=0.5 : 450 trades (33 %) taillés, +$521 réalisés vs +$1 042 pleine taille = -$521 manqués ; wallet FULL -19,6 % à -71,4 % vs contrôle. Pire mois DÉGRADÉ en TRAIN 11/12 (le garde coupe aussi les gagnants intra-mois du mois rouge : machine -10,1 → -10,6/-15,6) ; DD machine jamais amélioré (24,8 % partout — le DD est creusé par les entrées PRÉ-seuil) ; QUBO DD 23,4→21,2 mais ROI -31 à -61 %. 0 liq partout (invariant aux tailles, vérifié) | **NUL** — la mécanique est close au niveau WALLET (après sizing conditionnel cher et dd_cross nul) : le PnL de la machine est right-skewed, couper en drawdown coupe le rebond. Reste non testé : ré-engagement par PALIERS (r accru quand DD < S/2), garde sur DD inhérent au flux (pas au wallet) |

Rapport : reports/wallet-dd-guard-2026-09-27.md (script : scripts/wallet_dd_guard.py — briques importées de the_machine/stacked_portfolio/qubo_sizing, aucun fichier officiel édité, klines.db lecture-seule).

## 27/09 nuit — QUBO joint poids×levier (CANDIDAT, le meilleur point du projet) + garde wallet (NUL)

| Verdict | Détail | Catégorie |
|---|---|---|
| **QUBO JOINT poids×levier** — LA donnée : MAE max TRAIN par flux — majors 7,66 % → plafond **12,26x** (tournait à 10x) ; meme 223,68 % → 0,45x brut mais les 2 events ≥ 99,5 % ne passent jamais au sizer (busy-skip) → 1x tient fragile ; survivor intuable (LONG 1x) ; **vol_spike MAE 94,68 % (p99 49 %) → plafond 1,05x — l'hypothèse « entrée = extrême → MAE petit » est RÉFUTÉE** | cellule gagnante **w = [0.857, 0.857, 2.0, 0.857] × lev = [11x, 1x, 1x, 1x]** ; annealing = grille 16 384 états sur 14 λ ; TRAIN $2 175 @ 23,3 ; VAL +75,1 % @ 18,6, 0 liq ; **FULL $5 182 = +5 082 %/an @ DD 23,3 %, 0 liq, record +83,7 % (≥ cible 80 %), pire -13,4 %, 1 nég/12** vs poids seul $4 639 @ 23,4 vs main $4 005 @ 24,8 | **CANDIDAT — ⚠️ marge MAE majors VAL 7,84 % vs seuil 8,59 % (11x) = 9 % de tête seulement — en surveillance permanente** ; paper-forward avec les autres variantes |
| garde drawdown wallet-level (prop-firm : taille ×r quand le wallet est à -S % du sommet, hystérésis S/2) | **NUL 12/12 cellules** — le coût de garde est négatif : les trades taillés sont les GAGNANTS du rebond (-$521 manqués sur une cellule, 33 % des trades taillés) ; le pire mois DÉGRADÉ 11/12 ; cohérent avec la loi d'exécution (le rebond après DD = là où l'edge vit) ; seul le QUBO gagnait 2,2 pts de DD au prix de -31 à -61 % de ROI | **NUL** — le ré-engagement par paliers reste non testé (à pré-enregistrer) |

Rapports : reports/qubo-joint-lev-2026-09-27.md, reports/wallet-dd-guard-2026-09-27.md.

## 27/09 fin — H2bis capitulation + H3bis sweep : pré-enregistrés puis testés — NUL / CONTEXTE, aucun sizing branché (capitulation_sweep_test.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **capitulation** (close signal = min des 24 closes ET pente CVD 6h ≤ p25 des pentes TRAIN, seuil figé −0.0415) — H2bis pré-enregistrée dans le docstring du script AVANT tout calcul | Même corpus 230 events majors (CVD 1h 100 % couvert), split 70/30 par le temps (161/69). Gradient déclaré sain < nv-bas doux < capitulation : MAE TRAIN **1.70/2.27/3.26** (monotone OUI), VAL **1.75/2.55/2.43** (NON — la capitulation VAL retombe sous le nv-bas doux). Capitulation vs reste : TRAIN MAE 3.26 vs 1.85, exp −8.9 vs +6.6 (n 10/151) ; VAL 2.43 vs 1.92, exp −8.7 vs −1.1 (n 9/60). Binomial vs médiane reste TRAIN (1.41) : 7/10 (p=0.344) / 5/9 (p=1.000) — rien. Machine NON branchée | **NUL** — le hint n=30/12 (seuil dz 0.0131 du test H2) ne survit pas au seuil p25 pré-enregistré : n tombe à 10/9 et le gradient VAL casse ; espérance VAL dégradée ne suffit pas, le critère était le gradient |
| **sweep_vol → MAE du short** (low d'une des 6 bougies avant l'entrée casse le min 48h avec volume >2× sa moyenne 20) — H3bis pré-enregistrée dans le docstring AVANT tout calcul | Même corpus, split 161/69. Gradient binaire no_sweep < sweep : MAE TRAIN **1.84→2.66** (mono OUI), VAL **1.84→3.00** (mono OUI) ; exp VAL sweep **−16.6 vs +0.1** → PASS stat pré-enregistré. MAIS binomial vs médiane no-sweep TRAIN (1.57) : 9/19 (p=1.000) / 5/9 (p=1.000) — l'effet vit dans les queues, pas le corps. Buckets 2-3×/3-5×/≥5× : n=3-4/queue, sous-puissance confirmée. Machine ×0.75 sur sweep : **$3,739.04 (+3 639 %/an, DD 21.7 %, 0 liq, pire −10.1 %, 1 nég, record +100.3 %)** vs baseline répliquée au centime $4,004.94 (+3 905 %/an, DD 24.8 %, pire −10.1 %) — DD amélioré, ROI ≥ 90 % OK, mais **pire mois NON amélioré** → critère pré-enregistré FAIL | **CONTEXTE** — le seul des 4 hints H1-H3bis dont le gradient MAE se réplique TRAIN+VAL, mais effet de queue (binomial p=1.0) et aucun gain sur le pire mois ; ré-évaluable avec un critère de queue pré-enregistré (P(MAE>9.5 %) liq-adjacent), JAMAIS en gate |

Rapport : reports/capitulation-sweep-2026-09-27.md (script : scripts/capitulation_sweep_test.py — the_machine.py intact, klines.db lecture-seule). Baseline 4 flux répliquée identique ($4 004,94) = harnais fidèle ; garde-fou composé-des-mois 0.000 % OK sur les 2 runs.
