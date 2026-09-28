# 20 — Registre des indicateurs & stratégies

**La règle de gestion** : chaque indicateur a UN statut (VALIDÉ / CANDIDAT /
CONTEXTE / NUL), un script, une date de verdict et des chiffres. Tout verdict
passe par la chaîne complète : backtest pré-enregistré → baseline anti-dérive →
train/val par le temps → wallet séquentiel → CONTRÔLE INVERSE → BLOC STATS.
Après tout fix d'échelle ou d'unité, les ABSOLUS sont re-mesurés (les relatifs
tiennent). On ne supprime jamais : on re-catégorise.

Dernière re-mesure globale : **25/09 soir, après le fix d'unité ts_ms (ns)**.
Les chiffres ci-dessous sont les chiffres corrigés. (Les entrées du 27/09
ci-dessous sont cohérentes avec cette re-mesure ; le résumé d'état :
`docs/21-goal-performances.md`.)

> **28/09 — ARCHIVAGE** : les scripts d'études closes vivent désormais dans
> `scripts/archive_studies/` (un en-tête `# ARCHIVÉ (28/09)` + le verdict dans
> `scripts/README.md` §7). Les noms de scripts cités ci-dessous
> (`h1_absorption_test.py`, `h2_h3_cvd_test.py`, `capitulation_sweep_test.py`,
> `wallclock_cascades.py`, `recascade_study.py`, `funding_dimension_study.py`,
> `wallet_dd_guard.py`, `tail_machine_confirm.py`, `funding_hold_surv_map.py`,
> `hybrid_hold_test.py`, `cascade_fractal_test.py`, `carte_meme_hold.py`,
> `conditional_sizing.py`, `qubo_per_symbol.py`, `autopsie_mois_negatifs.py`,
> `swaps_forward_study.py`, `derek_replication_test.py`,
> `fomo_lifecycle_study.py`, `fomo_launch_study.py`, `tilt_volspike_test.py`,
> `whale_attention_test.py`) y pointent désormais.

> **Index du 27/09** — la journée la plus dense du registre : 19+ verdicts
> consommés (16 nuls/contextes, 3 candidats), alimentée par 6+ agents.
> Ordre des entrées : tilt × meme (frontière) → session parallèle Aster
> (vol_spike, carte hold meme, autopsie, volspike_meme) → lifecycle v2
> mobula → H1 absorption → H2/H3 CVD → QUBO poids + wall-clock + re-cascade
> → garde wallet DD → **QUBO joint poids×levier (le record +5 082 %)** →
> H2bis/H3bis capitulation+sweep → TAIL survivor au sizing réel → hold
> étendu + carte hold survivor.

## VALIDÉS (la frontière)

| Indicateur / stratégie | Script | Chiffres (100 $, 1 an, maker) | Verdict |
|---|---|---|---|
| **CANDIDAT QUALITÉ : cascade ∩ funding-rank-BAS** (le symbole au funding le plus bas des 6 majeures à l'instant du signal) | testé inline 25/09, à câbler au paper forward | **WR 81,0 % (n=21), DD 5,4 %, 0 liq**, +106 %/an — la spec du user (80 % WR / peu de DD / 0 liq) TOUCHÉE ; mécanisme : les shorts déjà entassés + le prix tombe quand même = offre réelle, pas de la foule | CANDIDAT — N=21, tercile post-hoc, le forward 2×/jour juge (~2 trades/mois) |
| **LA MACHINE — cascade gated 10x, 0 liq par construction, DEUX knobs (marge + sizing vol-inverse)** | `anti_liq.py` + `portfolio_sim.py` + `stacked_portfolio.py` | **SIZING VOL-INVERSE (base 24 %) : +1 498 %/an @ DD 27,8 %, 0 liq** — +19 % vs le fixed à DD égale. L'échelle : base 30 % → +2 655 %/an @ DD 34,7 %, record mois **+100,2 %** · base 60 % équivalents — WR 57,3 %, 3 mois négatifs *(état d'époque, 2 flux — l'état courant 4 flux et les 3 configs forward : docs/21-goal-performances.md, 27/09)* | **LA frontière** — size ∝ ATR : les cascades à haute volatilité sont les gagnantes (loi vol_haute confirmée 3×) ; le sizing standard (∝ 1/ATR) est REFUTÉ ici (ratio 12,9 vs 53,9) |
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
| **fdiv : N suffisant, dégradation significative** | binomial p = 4,3e-05 (<< 0,01) sur 63 trades : ce n'est PAS le bruit d'un petit N. La VAL temporelle du backtest déclinait déjà (WR 39,1 %, -0,84 %/trade) ; le forward la prolonge (-3,12 %/trade). fdiv → **NUL** (re-catégorisé, preuve datée) — même verdict que la ligne fdiv de la table NULS ci-dessus (les deux entrées restent, datées) | NUL (dégradé du CANDIDAT) |

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
| **re-cascade des cascades** (le 2e feu cascade du même symbole ≤ 7j — tag ex-ante sur les feux BRUTS, 7j lookback) | Corpus 230 events : 1er feu 7 % (15), re-feu <24h 26 % (59), re-feu 1-7j 68 % (156) — les re-feux sont MAJORITAIRES (93 %) ; gap médian 40h, Δ prix médian +0,48 %. Gradient jugé : re-feu <24h VAL inversé (+10,8→-2,3), spread EV 0,9 pt, années non jugables → **pas de run machine**. Lecture binaire hors barre : 1er feu PIRE partout (TRAIN -3,9 vs +6,3 ; VAL -5,2 vs -2,0 ; 2025 -10,0 vs +9,3 ; 2026 -1,4 vs +1,8 — Δ +3,2 à +19,3 pts, p two-prop 0,059 brut) mais n=15 total (détection ±44 pts), sous la barre n≥15 : hint sous-puissant, pas un candidat. Compte des feux 1/2/3+ non monotone (2 feux = le creux VAL -10,9) | **CONTEXTE** — le 2e feu n'est NI continuation premium NI épuisement mesurable ; le hint « 1er feu pire » (l'inverse du failed_ATH) revit seulement si le corpus double |

Rapports : reports/qubo-sizing-2026-09-27.md, reports/wallclock-cascades-2026-09-27.md, reports/recascade-2026-09-27.md (scripts/recascade_study.py).

## 27/09 nuit — garde drawdown du WALLET (désengagement prop-firm) : NUL, 0/12 cellules (wallet_dd_guard.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **garde wallet DD** (taille ×r quand DD wallet > S, retour sous S/2 hystérésis — 6 cellules S∈{10,15,20}/r∈{0.5,0.75}, 2 configs machine+QUBO, split 10/06/26) | Baselines reproduites bit-exact ($4 004,94 / $4 639,13). Coût de garde NÉGATIF sur 12/12 : les trades taillés sont des GAGNANTS (le rebond) — ex machine S=10/r=0.5 : 450 trades (33 %) taillés, +$521 réalisés vs +$1 042 pleine taille = -$521 manqués ; wallet FULL -19,6 % à -71,4 % vs contrôle. Pire mois DÉGRADÉ en TRAIN 11/12 (le garde coupe aussi les gagnants intra-mois du mois rouge : machine -10,1 → -10,6/-15,6) ; DD machine jamais amélioré (24,8 % partout — le DD est creusé par les entrées PRÉ-seuil) ; QUBO DD 23,4→21,2 mais ROI -31 à -61 %. 0 liq partout (invariant aux tailles, vérifié) | **NUL** — la mécanique est close au niveau WALLET (après sizing conditionnel cher et dd_cross nul) : le PnL de la machine est right-skewed, couper en drawdown coupe le rebond. Reste non testé : ré-engagement par PALIERS (r accru quand DD < S/2), garde sur DD inhérent au flux (pas au wallet) |

Rapport : reports/wallet-dd-guard-2026-09-27.md (script : scripts/wallet_dd_guard.py — briques importées de the_machine/stacked_portfolio/qubo_sizing, aucun fichier officiel édité, klines.db lecture-seule).

## 27/09 nuit — QUBO joint poids×levier (CANDIDAT, le meilleur point du projet) + garde wallet (NUL)

| Verdict | Détail | Catégorie |
|---|---|---|
| **QUBO JOINT poids×levier** — LA donnée : MAE max TRAIN par flux — majors 7,66 % → plafond **12,26x** (tournait à 10x) ; meme 223,68 % → 0,45x brut mais les 2 events ≥ 99,5 % ne passent jamais au sizer (busy-skip) → 1x tient fragile ; survivor intuable (LONG 1x) ; **vol_spike MAE 94,68 % (p99 49 %) → plafond 1,05x — l'hypothèse « entrée = extrême → MAE petit » est RÉFUTÉE** | cellule gagnante **w = [0.857, 0.857, 2.0, 0.857] × lev = [11x, 1x, 1x, 1x]** ; annealing = grille 16 384 états sur 14 λ ; TRAIN $2 175 @ 23,3 ; VAL +75,1 % @ 18,6, 0 liq ; **FULL $5 182 = +5 082 %/an @ DD 23,3 %, 0 liq, record +83,7 % (≥ cible 80 %), pire -13,4 %, 1 nég/12** vs poids seul $4 639 @ 23,4 vs main $4 005 @ 24,8 | **CANDIDAT — ⚠️ marge MAE majors VAL 7,84 % vs seuil 8,59 % (11x) = 9 % de tête seulement — en surveillance permanente** ; paper-forward avec les autres variantes |
| garde drawdown wallet-level (prop-firm : taille ×r quand le wallet est à -S % du sommet, hystérésis S/2) | **NUL 12/12 cellules** — le coût de garde est négatif : les trades taillés sont les GAGNANTS du rebond (-$521 manqués sur une cellule, 33 % des trades taillés) ; le pire mois DÉGRADÉ 11/12 ; cohérent avec la loi d'exécution (le rebond après DD = là où l'edge vit) ; seul le QUBO gagnait 2,2 pts de DD au prix de -31 à -61 % de ROI *(même étude que la section « garde drawdown du WALLET » ci-dessus — doublon daté conservé, on ne découarte pas)* | **NUL** — le ré-engagement par paliers reste non testé (à pré-enregistrer) |

Rapports : reports/qubo-joint-lev-2026-09-27.md, reports/wallet-dd-guard-2026-09-27.md.

## 27/09 fin — H2bis capitulation + H3bis sweep : pré-enregistrés puis testés — NUL / CONTEXTE, aucun sizing branché (capitulation_sweep_test.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **capitulation** (close signal = min des 24 closes ET pente CVD 6h ≤ p25 des pentes TRAIN, seuil figé −0.0415) — H2bis pré-enregistrée dans le docstring du script AVANT tout calcul | Même corpus 230 events majors (CVD 1h 100 % couvert), split 70/30 par le temps (161/69). Gradient déclaré sain < nv-bas doux < capitulation : MAE TRAIN **1.70/2.27/3.26** (monotone OUI), VAL **1.75/2.55/2.43** (NON — la capitulation VAL retombe sous le nv-bas doux). Capitulation vs reste : TRAIN MAE 3.26 vs 1.85, exp −8.9 vs +6.6 (n 10/151) ; VAL 2.43 vs 1.92, exp −8.7 vs −1.1 (n 9/60). Binomial vs médiane reste TRAIN (1.41) : 7/10 (p=0.344) / 5/9 (p=1.000) — rien. Machine NON branchée | **NUL** — le hint n=30/12 (seuil dz 0.0131 du test H2) ne survit pas au seuil p25 pré-enregistré : n tombe à 10/9 et le gradient VAL casse ; espérance VAL dégradée ne suffit pas, le critère était le gradient |
| **sweep_vol → MAE du short** (low d'une des 6 bougies avant l'entrée casse le min 48h avec volume >2× sa moyenne 20) — H3bis pré-enregistrée dans le docstring AVANT tout calcul | Même corpus, split 161/69. Gradient binaire no_sweep < sweep : MAE TRAIN **1.84→2.66** (mono OUI), VAL **1.84→3.00** (mono OUI) ; exp VAL sweep **−16.6 vs +0.1** → PASS stat pré-enregistré. MAIS binomial vs médiane no-sweep TRAIN (1.57) : 9/19 (p=1.000) / 5/9 (p=1.000) — l'effet vit dans les queues, pas le corps. Buckets 2-3×/3-5×/≥5× : n=3-4/queue, sous-puissance confirmée. Machine ×0.75 sur sweep : **$3,739.04 (+3 639 %/an, DD 21.7 %, 0 liq, pire −10.1 %, 1 nég, record +100.3 %)** vs baseline répliquée au centime $4,004.94 (+3 905 %/an, DD 24.8 %, pire −10.1 %) — DD amélioré, ROI ≥ 90 % OK, mais **pire mois NON amélioré** → critère pré-enregistré FAIL | **CONTEXTE** — le seul des 4 hints H1-H3bis dont le gradient MAE se réplique TRAIN+VAL, mais effet de queue (binomial p=1.0) et aucun gain sur le pire mois ; ré-évaluable avec un critère de queue pré-enregistré (P(MAE>9.5 %) liq-adjacent), JAMAIS en gate |

Rapport : reports/capitulation-sweep-2026-09-27.md (script : scripts/capitulation_sweep_test.py — the_machine.py intact, klines.db lecture-seule). Baseline 4 flux répliquée identique ($4 004,94) = harnais fidèle ; garde-fou composé-des-mois 0.000 % OK sur les 2 runs.

## 27/09 fin — la TAIL du survivor au SIZING MACHINE RÉEL : FAIL au critère pré-enregistré (tail_machine_confirm.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **TAIL du survivor** (les 156 events ATR > p90=2,90 % jetés par le gate du flux survivor, ajoutés en 5e flux au wallet 4 flux --vol-spike au notional machine 0,20·K = 0,178 — convention exacte the_machine.py, créneau distinct 1 slot run_stack ; sensibilité ×0,5 = 0,089) | Flat 5 % (survivor-meme 27/09) : WR 61,9 %, +0,386 $/trade, corr < 0,3, 2 rugs — CANDIDAT avec réserve de concentration (top 3 = +18,14 $ sur +16,23 $). Au sizing machine, baseline $4,004.94 répliquée bit-exact (écart $0,004) : **+TAIL 0,20·K $6,349.58 (+6 250 %/an) MAIS DD 33,9 % (> 24,8) et 2 mois négatifs (2026-07 -19,3 %) vs 1** ; +TAIL 0,10·K $5,173.81 (+5 074 %/an) @ DD 24,8 % mais toujours 2 mois négatifs (-5,1 %) → critère pré-enregistré (ROI ≥ ET DD ≤ ET nég ≤ ET 0 liq) **FAIL aux DEUX doses**. Concentration : les 3 gros = 3 trades LABUSDT (27+30/05, 02/07) portent +1 558 $ sur +560 $ de contribution TAIL (278 %) — le delta wallet apparent (+2 344 $) est du compounding TRAIN ; sans eux le wallet $4,757 mais **DD 38,8 %, pire mois -25,9 %** → edge hors top-3 NON confirmé. TRAIN/VAL sur l'ajout : TRAIN 109 evts WR 53,2 % ex +6,14 %/not Δ +3 594 $ vs **VAL 47 evts WR 31,9 % ex -8,80 %/not Δ -378 $** — l'ajout détruit de la valeur sur VAL. 0 liq partout, garde-fous composé-des-mois 0,000 % OK | **CONTEXTE** (ré-catégorisé de CANDIDAT) — l'espérance flat +0,386 $/trade est une queue de régime TRAIN (mai-juin 2026, les ×520 LAB) : au sizing machine elle échoue au critère wallet ET au temps ; le gate ATR p90 du survivor est CONFIRMÉ porteur de valeur, ne PAS l'assouplir ; ré-évaluable seulement sur un futur régime tail-friendly pré-enregistré AVANT |

Rapport : reports/tail-machine-confirm-2026-09-27.md (script : scripts/tail_machine_confirm.py — briques importées de qubo_sizing/survivor_meme_test/the_machine, aucun fichier officiel édité, klines.db lecture-seule).

## 27/09 nuit — hold étendu funding-conditionnel (NUL) + carte hold survivor (72h confirmé) (funding_hold_surv_map.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **hold étendu funding-conditionnel** (cascade majors gated 165/230, décision à t+24h : carry 24h ≥ p75 TRAIN ET gagnant à 24h → étendre 36/48h ; carry C1 booking harnais 0,110 % de marge / C2 réel sommé 0,154 % ; split 115/50 par le temps, loop réplique run_stack bit-identique $164,76 écart $0,0000) | Gradient NON monotone : TRAIN Q5 (carry max) = Δpnl méd **-23,0 %** de marge, WR 25 % (les gagnants à carry extrême sont squeeze-prone) ; VAL dispersé (N=3-11/cellule). Loi des gagnants : VAL Δret post-24h médian **+0,02 %** — drift nul, le rebond est déjà capté par le hold 24h. ÉCHELLE : le carry p75 = ~50-100× plus petit que le bruit de rebond (±2-14 % de marge) — **le carry ne paie pas l'extension même à 10x**. Wallets VAL : EXT36 +7,2 %/DD 5,2, EXT48 C1 +6,9 %/5,2, EXT48 réel +8,5 %/**5,7** vs baseline +8,0 %/**4,5** — 0 liq partout, mais le critère pré-enregistré (ROI ≥ ET DD ≤ ET nég ≤ ET liq ≤) échoue 3/3. Au sizing machine : EXT48 $854 DD 26,4 % vs baseline $1 244 DD 24,7 % | **NUL** — la 3e dimension de la famille exit (le carry) est close : le hold 24h fixe reste l'optimum ; à ré-évaluer seulement si le levier cascade monte (le carry scale avec le levier) |
| **carte hold du survivor** (signal verbatim répliqué bit-identique à collect_arsenal, 1 554 events, gate ATR p90 2,90 % figé ; holds 48/72/96/120h, LONG 1x intuable, ensemble commun 1 358 events appariés) | Espérance appariée MONTE avec le hold : +0,032 / +0,052 / +0,074 / **+0,102** $ (le drift long bat le funding payé) mais le créneau 1 slot fait tomber N/an 10→4 : ROI/an **+11,0 / +15,7 / +13,9 / +9,6 %**, DD 2,1 / 2,1 / 1,7 / 3,0 %, 0 liq et 0 rug partout (MAE max ~31 %, pire trade -28,8 %). 96h : meilleure WR wallet (52,4 % vs 47,1 %) mais ROI inférieur. Corr max avec les 4 flux : survivor 72h self 1,00, autres ≤ 0,70. TRAIN/VAL : VAL 72h +9,76 $ vs 96h +12,03 $ (bruit, N=29/21) | **NUL (changement)** — 72h CONFIRMÉ point de tangence fréquence × espérance ; la carte est le garde-fou anti-dérive du hold survivor (ne jamais l'étendre sans re-test) |

Rapport : reports/funding-hold-survivor-2026-09-27.md (script : scripts/funding_hold_surv_map.py — briques importées de anti_liq/stacked_portfolio/p5_frequency_test/full_arsenal_2, aucun fichier officiel édité, klines.db lecture-seule, garde-fous composé-des-mois 0,000 % sur les 8 wallets).

## 27/09 nuit — K scan (CANDIDAT à arbitrer) + univers meme (4 tier-1 câblés)

| Verdict | Détail | Catégorie |
|---|---|---|
| **K scan** (le dernier paramètre libre : le multiplicateur de taille absolu, calibré à la main 0,89) | K=0,95 sur la cellule jointe = **$6 519 (+6 419 %/an @ DD 24,9 %, 0 liq, record +90,0 %, 1 nég)** — +25,8 % de balance pour +1,6 pt DD, choisi TRAIN, confirmé VAL (DD 19,7) ; théorème d'échelle vérifié (1 356 trades identiques, 0 liq/18 runs) ; K=1,00 = +7 766 % MAIS DD 26,2 % > 25 rejeté ; trade-off : pire mois -14,3 % | **CANDIDAT** — à arbitrer : K=0,95 @ DD 24,9 % (marge 0,1 pt) vs K=0,89 @ 23,3 % |
| **Univers meme audit** | le collecteur nocturne ne découvre RIEN (11 symboles codés en dur) ; 4 tier-1 ajoutables : DRAM (+117/an, esp +0,87), PIEVERSE (+67, +2,20), VIRTUAL (+85, +1,14), MELANIA (+44, +1,82) = +313 events/an, 0 MAE fatal ; exclus à espérance négative : PEPE/USELESS/SHIB/BONK/PUMP ; 2 tickers périmés corrigés (BONKUSDT→1000BONK, FLOKIUSDT→1000FLOKI) | **CANDIDAT** — câblé au nocturne, re-juger sur VAL après 30 j |

Rapports : reports/k-scan-2026-09-27.md, reports/meme-universe-audit-2026-09-27.md.

## 27-28/09 — la couche institutionnelle fine : murs (PROTOTYPE) + gros prints (FADE) + la boucle réplication derek518 (CANDIDAT)

| Verdict | Détail | Catégorie |
|---|---|---|
| **Les murs du carnet** (détecteur de murs sur depth ~30 s, `wall_detector.py`, lecture-seule depth.db) | 169/237/116 murs BTC/ETH/ASTER (tailles 0,25-1,66 M méd) ; PULL 91-98 % vs HIT — le mur typique meurt RETIRÉ ; l'effet forward : placement ASK → **-14,2 bp à +30 min, WR 76 %** (les murs SUPPRIMENT) ; BID-HIT **+13,3 bp WR 100 %** vs BID-PULL -14,0 bp = divergence **27 bp** (HIT = continuation, PULL = faiblesse — PAS le spoofing classique) ; majors = murs éphémères spoof-like, ASTER persistant 66 % = vrai acteur | **PROTOTYPE 4,3 j NON-MATURE** — fenêtre complète, re-tir tel quel **06-07/10** |
| **Les gros prints** (collecteur block trades, `aster_blocktrades.py`, endpoint aggTrades validé, timer 15 min câblé — 145k trades scannés à la 1re passe) | 303 998 scannés → 2 040 prints (seuils adaptatifs BTC 99k/ETH 23k/SOL 2k), 3 jours bootstrap ; LA DÉCOUVERTE : les clusters de gros prints **FADENT** (BUY cluster → -0,023 % à +30 min, SELL → +0,023 %) = venue dominée makers — les prints sont un **détecteur d'ABSORPTION**, pas de continuation | **CONTEXTE** (outil de lecture du tape) — le cross prints × OI squeeze à armer dans 2 semaines |
| **swaps → forward v2** (`swaps_forward_v2.py`, re-run post-backfill mobula complet — 1 353 mints, ~6,8 M bougies) | 2 233 events : répliquer TOUTES les baleines = WR 36 % mort ; MAIS l'edge skill-weighted tient : **PASS (edge +8,4 %, t=2,65 vs baseline médiane, TRAIN +6,7 → VAL +12,3 %)** ; derek518 = le seul skill robuste (n=161, edge +38 %, méd +8,7 %, VAL +9,2 %) | **CONTEXTE** (le socle de la boucle) |
| **Réplication derek518** (`derek_replication_test.py`, wallet séquentiel) | **+88 %/26 j @ DD 6,4 %, WR 72 %** — ROBUSTE : sans le top-1 +88,4 %, sans le top-3 +76,8 % ; 0/72 anti-rug déclenché (age ≥ 7j élimine la forme pump-rug) ; **RÉSERVE : 26 jours = 1 régime** ; la règle `replication_derek` est CÂBLÉE dans `fomo_paper_forward.py` (idempotent par swap_id, ≤ 10 positions, garde anti-rug) | **CANDIDAT** — **le verdict forward à ≥ 5 CLOSED** |

Rapports : reports/wall-detector-2026-09-27.md, reports/blocktrades-2026-09-27.md, reports/swaps-forward-v2-2026-09-27.md, reports/derek-replication-2026-09-27.md, reports/derek-wiring-2026-09-27.md (scripts : scripts/wall_detector.py — depth.db lecture-seule ; scripts/fomo_paper_forward.py édité pour la règle replication_derek).

## 28/09 — hold hybride 24h/72h conditionné au swap baleine (NUL) — suite lifecycle v3

| Verdict | Détail | Catégorie |
|---|---|---|
| **hold hybride** (entrée à la naissance = close 1re bougie non plate, hold 24h par défaut ; extension 72h SI un swap baleine ≥ $10k côté BUY a eu lieu dans [entrée, entrée+24h] ; décision ex-ante à t+24h, lag 1h testé ; N=1246, ancres v3 reproduites 1.44x/63 %/pire 0.020x) | Déclencheur quasi muet : **21/1246 étendus (1,7 %)** — seuls 99 mints ont un BUY ≥ $10k, 21/136 de la cohorte v3 >10k$ seulement (cohorte définie EX-POST : max sur vie entière, tous côtés). Sur les 21 étendus, l'extension est tendance NÉGATIVE : 8 mieux / 13 pire (p binomial 0,38), hold24h méd 12,15x → 72h 6,86x ; médiane corpus inchangée 1,44x, moyenne 10,14 → 10,05x. Sensibilité tous côtés (33 étendus) : 10/23, p=0,035 — significativement PIRE. hold72h pur reste derrière partout (1,19x, WR 59 %, pire 0,011x). Wallet spot 5 %/1 créneau (taker 0,09 %+slippage 0,5 %/côté, DD 19,5 %, 0 liq spot) : l'hybride est SOUS le baseline ($1,39e11 vs $2,21e11 cap 10x — montants absolus fantaisistes, survivorship ; seul l'ordre relatif vaut, garde-fou composé-des-mois : record mois +87 265 %) | **NUL** — la doctrine hold24h tient ; l'edge v3 de la cohorte >10k$ était ex-post, non capturable ex-ante à t+24h. La piste baleine ≥ $10k$ reste ouverte UNIQUEMENT en détection temps réel (flux swaps-fresh, cf. replication_derek déjà câblée), à re-tester si le backfill swaps couvre plus de mints |

Rapport : reports/hybrid-hold-2026-09-28.md (script : scripts/hybrid_hold_test.py — briques importées de lifecycle_v3_scale.py, fomo.db + fomo_swaps.db lecture-seule, ts swaps = SECONDS vérifié).

## 28/09 — test de FRACTALITÉ du cascade (15m/30m vs champion 1h/24h) — NUL

| Verdict | Détail | Catégorie |
|---|---|---|
| **cascade accéléré sur TF-court** (définition EXACTE anti_liq.py — 3 bougies de baisse + accélération \|r\| — transposée aux barres 15m/30m, entrée open t+1, MAE highs, séquentiel global, taker 0,18 % RT, split 70/30 temps, levier 0-liq TRAIN, 1 touché VAL = morte ; 30m = resample exact du 15m natif ; univers BTC/ETH/SOL/DOGE pleine année — BNB 31 j, XRP absent) | **Fréquence fractale OUI : 745/379/183 événements brut/symbole/an (15m/30m/1h) = 4,07×/2,08× — le pattern SE REPRODUIT. Edge NON : edge net TRAIN négatif PARTOUT (15m/1h −0,173, 15m/2h −0,167, 15m/4h −0,140, 30m/1h −0,152, 30m/2h −0,156, 30m/4h −0,115, 1h/1h −0,106, 1h/2h −0,060 vs mur 0,18 % RT ; 1h/4h +0,058 TR mais VAL −0,316) — ret brut ≈ 0,0 % en hold 1-4h vs +0,53 % à 24h : le rebond post-cascade est un phénomène d'échelle JOUR, pas heures. MAE 15m/1h max TRAIN 6,38 % (p95 1,38) → plafond 14,5x — le levier montait, l'espérance ne suit pas. Baseline même-code 1h/24h NON-gatée : 236 trades/an (wallclock 230 ✓), ret +0,53 %, mais 1 MAE VAL 13,08 % ≥ plafond 8,61 % → le champion officiel tient à 10x GRÂCE au gate AL (MAE gated 7,84 %), le gate est PORTEUR | **NUL** (cascade TF-court, mur des coûts) — 0 cellule vivante, aucun run wallet, rien au stack ; le champion 1h/24h gaté reste le seul flux cascade ; la fractalité de fréquence NE vaut PAS fractalité d'espérance |

Rapport : reports/cascade-fractal-2026-09-28.md (script : scripts/cascade_fractal_test.py — klines.db lecture-seule, 15m natif 187k bougies, funding_history as-of).

## 28/09 soir — les deux composites : AL v2 FAIL, gate meme FAIL (le gate v1 est optimal dans notre feature-set)

| Verdict | Détail | Catégorie |
|---|---|---|
| AL Score v2 (les 10 features pré-validées, rangs roulants) | **FAIL** — aucune feature ne bat le gate v1 en VAL (AUC v1 0,639 vs v2 0,503-0,648) ; LA LEÇON : les directions validées sur les GATED s'INVERSENT sur l'univers complet (fresh-peak) — un gate ne retient qu'une feature dont le gradient tient LÀ où il opère ; le re-gating d'essai ré-admettait l'event MAE 13,08 % → 1 LIQUIDATION | **NUL** — le gate v1 (6 features, p66) reste officiel ; re-tenter à n VAL ×2 |
| Gate meme (9 features, 2 022 events) | **FAIL** — 0/9 feature monotone (U inversés, inversions VAL) ; les 3 mortels (MAE 224/109/106 %) isolables par AUCUNE feature ex-ante ; et le verdict de fond : **le flux meme est MORT quoi qu'il arrive** (espérance TRAIN +0,009 → VAL -0,018 $/trade, WR 52,9→47,0 % — l'edge évaporé depuis juin ne revient pas) | **NUL** — la décision meme = au user (réduction ×0 vs garder en loterie décorrelante à 0,857) |

## 28/09 nuit — la breadth transversale aux entrées cascade : gradient OUI, sizing NON

| Verdict | Détail | Catégorie |
|---|---|---|
| Breadth % des 6 majeures (ret 24h négatif, closes 1h ≤ entry, ex-ante) aux 165 events cascade gated | **Gradient COHÉRENT** : Δespérance hi-lo TRAIN +3.02 / VAL +5.39 %/marge, bucket bas = pire des deux splits (VAL 0-33 : -0.03 ≈ 0) ; ⟂ corr7 (r=-0.10), résiduel positif 5/6 cellules terciles corr7 ; journées breadth 100 % : n=34, WR 58.8 %, +6.81 (réels, pas miracles). MAIS le sizing ×0.75/×1.0/×1.25 sur machine 4 flux vol-spike : $3,757 vs baseline $4,004.94, DD 31.7 % (> 25 %) → FAIL ; variante mid ×1.25 : $3,967, DD 24.8 % → ROI < baseline, FAIL. Le ×0.75 ampute des trades à espérance positive, le ×1.25 gonfle le bucket au MAE max 7.66 % | **CONTEXTE** — marqueur descriptif de régime (diagnostic), JAMAIS un multiplicateur de sizing ; le corr-tilt 168h reste le seul module systémique du machine |
| Breadth v2 : nb autres majeures en DD 24h ≥ 3 % | **INCOHÉRENT** — Δ hi-lo TRAIN -2.16 / VAL -1.31 (gradient inverse, faible, n VAL 3+ = 4) | **NUL** |

Rapport : reports/breadth-cascade-2026-09-28.md (script : scripts/breadth_cascade_test.py — klines.db lecture-seule, réplique machine bit-exacte $4,004.94).

## 28/09 — l'exit informé par le flux (CVD 1h pendant la détention) : le bounce ne s'annonce pas

| Verdict | Détail | Catégorie |
|---|---|---|
| Flag CVD détention (delta buy_ratio = 2 dernières bougies 1h vs 2 pré-entrée, h ∈ {2,4,8,12}, seuil choisi sur TRAIN) sur les 165 cascade gated (hold 24h, TRAIN 115 / VAL 50) | **INVERSION TRAIN/VAL systématique** : Δespérance flag-non-flag TRAIN -10.37 / -5.80 / -3.95 / -1.09 pt mais VAL +9.88 / +1.24 / +3.89 / +3.39 pt (h=2/4/8/12) — le gradient TRAIN ne tient JAMAIS en VAL ; à h=2 les flaggés VAL sont même les MEILLEURS (WR 85.7 %, +11.97 %/marge, subs-MAE 1.05 % vs 1.48 %) ; spearman(delta, ret24) VAL ≈ 0 partout (-0.01 / +0.08 / +0.03 / -0.08). Phase B (machine 4 flux) non lancée — critère pré-enregistré « Δesp ≤ -1.0 pt TRAIN ET VAL » jamais rempli | **NUL** — le retour du taker buy ratio 1h ne précède PAS le bounce en hors-échantillon ; l'exit 24h fixe reste l'optimum de la famille exit ; seule piste résiduelle honnête : CVD 15m intra-bougie, coût data élevé, à ne rouvrir que si n ×2 |

## 28/09 tard — forensique du régime (le caractère du T3) + exit CVD (NUL)

| Verdict | Détail | Catégorie |
|---|---|---|
| **Forensique du régime T3** | le caractère = une GRIND-UP ROTATION, pas de l'apathie : corr7 0,82→0,76 (-1,33σ), breadth 51→45 %, **funding ×2,4** ; vol/volume/DD inchangés (la vol était déjà basse en Q2 qui faisait +0,75 %) ; la bascule BRUTALE (la semaine 28/06→04/07, au sommet du régime herd-down) ; **AUCUN précurseur persistant** (« vol basse → dérisquer » réfutée par mai) ; le levier = raccourcir la fenêtre de l'adaptateur (les franchissements 30 j détectent le 07/07, 5-7 semaines avant le 90 j) | **CONTEXTE** — la signature funding↑+corr7↓+breadth↓ = pré-enregistrée, aucune récurrence en 4 ans |
| Exit CVD (le flux pendant la détention) | **FAIL** — le flag (le retour du taker buy à 2-12h) prédit le bounce sur TRAIN (-10,4 pts à 2h) mais **s'INVERSE en VAL** (+9,9) ; Spearman ≈ 0 ; les seuils sur-ajustés, le mécanisme ne tient pas hors-échantillon | **NUL** — le 24h fixe reste l'optimum de la famille exit (prix ET flux battus) |

| Adaptateur fenêtre 30 j | **MORT** — 348/365 jours OFF (95 % du temps désengagé, y compris les bons trimestres à +0,75/+0,96 %) : la fenêtre courte contient 3-5 trades, l'espérance oscille sous le seuil en continu ; le lead de 5-7 semaines de la forensique ne survit pas au bruit | **NUL** — le 90 j reste LA fenêtre |

## 28/09 nuit — le portefeuille des survivants (le régime T3 porté à DD 3,4 %)

| Verdict | Détail | Catégorie |
|---|---|---|
| **Portefeuille survivants** (fade vol_spike + réplication derek518, la fenêtre commune 26 j) | $100 → **$124,07 (+24,1 %/26 j) @ DD 3,4 %, 0 liq, 0 mois négatif**, 91 trades ; le fade = **multi-régime confirmé** (Q4'25 +19,2 / Q1'26 -4,2 / Q2'26 +2,9 / **Q3'26 +15,1 % — le régime mort est son MEILLEUR trimestre**) ; corr PnL fade×derek **-0,28** = diversification réelle ; l'apport derek +16,64 $ (vs +7,4 % pure-fade) | **CANDIDAT conditionnel** — derek sous-puissant mono-slot (7/72 captés, top-3 = 99 %) : le paper tranche, pas le backtest |

## 28/09 très tard — les lectures précoces Aster (OI + liquidations)

| Verdict | Détail | Catégorie |
|---|---|---|
| **OI lecture structurelle** (2 j, 15 min) | la géographie surprend : l'OI Aster est dominé par les MEMECOINS (NEIRO 470 M, PEPE 187 M, DOGS 135 M — BTC/ETH hors top 10) ; la corrélation instantanée ΔOI×Δprix 15 min = **0,000 en moyenne** (le positionnement ne bouge pas avec le prix à cette échelle ; LAB -0,42 et DOGS -0,35 = les symboles à squeezes) | **CONTEXTE** — le tir H4/H5 (fenêtre 90 min, jeudi) reste le test décisif |
| **Bursts de liquidations → rebond** (6 j, 81 bursts ≥3 SELL/1h ≥ $20k) | **L'INVERSE de l'hypothèse d'épuisement** : post-burst -0,18 %/+1h, -0,29 %/+4h (WR 39 %) — les ventes forcées CONTINUENT de nourrir la chute (cohérent corr-tilt : systémique = ça continue) ; hint : ≥8 SELL (n=17) → -0,016 % = les extrêmes commencent à épuiser | **CONTEXTE** — n=6 j, le reversal-long est réfuté sur cet échantillon ; re-test à 14 j |

**PRÉ-LECTURE OI à 3 j (358 fenêtres complètes 90+90 min)** : H5 (OI↓+prix↓, n=42) → le drift suivant le MOINS négatif (-0,073 %/-0,171 % vs les chutes neutres -0,358 %) = la direction d'épuisement des flush se dessine tôt ; H4 (OI↑+prix↓, n=42) → -0,281 % (moins négatif que neutre — le sens OPPOSÉ au pré-enregistré « continuation », n trop mince pour conclure) ; tout mean-revert vers le bas dans ce régime (le contrôle hausses -0,374 %). **PRÉVIEW, PAS VERDICT** — le tir complet (5 j + train/val) reste jeudi.

## 28/09 nuit — l'univers macro/synthétique d'Aster découvert et cartographié (CONTEXTE — veille)

| Verdict | Détail | Catégorie |
|---|---|---|
| **L'univers macro/synthétique** (587 perps listés sur Aster, 27 macro+equity fetchés : l'or XAU, l'argent XAG, le pétrole CL/BZ, SPX, NVDA, GOOGL, AAPL, TSLA, MSFT, MSTR, COIN...) | **DÉCORRÉLÉS comme promis** : CL vs BTC -0,19, les équités vs NEIRO ≤ +0,28 (hors MSTR +0,83 / COIN +0,74 / CRCL +0,69 = crypto déguisée, exclus) ; MAIS **la liquidité tue** : le meilleur (CL) = 0,47 M$/bougie 1h, les équités mortes < 0,03 M (AAPL/MSFT/SPX = zéro volume) ; le signal tendance naïf : 12/13 mois négatifs au composite | **CONTEXTE — VEILLE** : le collecteur premium étendu à CL/XAU/XAG/NVDA, aucun trade avant > 1 M$/bougie ; la liquidité d'Aster macro = le déclencheur à surveiller |

## 29/09 — L'ANATOMIE PROFONDE DU FADE : le « multi-régime certain » n'existe pas (la vérité du harnais complet)

| Verdict | Détail | Catégorie |
|---|---|---|
| Anatomie des échecs fade (5 128 events, 6 features, train/val strict) | **zéro feature ne sépare les perdants** (tous \|ρ\| ≤ 0,06 — BTC, l'âge, le financement, le multiplicateur, le CVD d'absorption (réfuté au niveau fade aussi), le symbole) ; les pertes s'accumulent sur LAB/TRUMP/H (descriptif, pas filtrable) | CONTEXTE |
| **LA DÉCOUVERTE CENTRALE** : la contingence du fade | les perdants ne « continuent » PAS après 2h — le drift 2h→6h des buckets perdants ≈ **zéro** : la continuation se joue DANS les 2 premières heures, ensuite le trade = de l'argent mort à queue grasse (le meilleur trade du corpus : +55,66 %) | CONTEXTE — la mécanique du fade est un événement instantané, pas une tendance |
| Exit conditionnel côté perte (8 cellules) | **TOUTES FAIL** — couper tôt convertit les pertes flottantes en pertes réalisées ET rate la queue haute (-0,38 %/trade) ; la queue se réduit (-44,7→-37,5) mais le prix est excessif | **NUL** |
| **LE FADE RÉEL** (le harnais complet, 847 trades) | WR 53,6 %, **ratio G/P 0,93** (le 0,47 du forward n=13 = du bruit d'échantillon !), +5,6 %/an @ DD 7,3 %, **5 mois négatifs/12, Q1'26 -0,18 %** = le critère multi-régime ÉCHOUE au bloc complet | **RE-CATÉGORISÉ : le fade = un petit edge positif, PAS l'edge multi-régime certain** |

**LA CONSÉQUENCE STRATÉGIQUE** : le « record absolu et certain » n'existe
pas encore dans notre inventaire — le fade est fin (+5,6 %/an), les
cascades sont régime-mortes, derek a 26 jours, le bonding s'arme. La
certitude viendra de : le forward (derek/bonding), les tirs d'octobre,
et le retour du régime cascade. La discipline vient de prouver qu'elle
préfère la vérité au confort : elle a démonté notre propre « edge
multi-régime confirmé ».

**LA DEMI-VIE DE L'EDGE DEREK518 (28/09 nuit — la découverte qui redéfinit la priorité)** : le ret 24h de ses 85 achats ≥ $5k selon le délai d'entrée — **+1h : +21,2 %/+20,3 % → +24h : +7,8 %/+3,7 % = l'edge décroît 5× en 24 h** (même cohorte n=85 partout, décroissance monotone = mécanique : le marché copie derek en quelques heures). IMPLICATIONS : (1) l'étude v2 (+18,8 %/trade à l'entrée ~1h) mesurait la version CONSERVATRICE — l'edge temps réel est supérieur ; (2) la détection HOURLY (swaps-fresh) + la passe 15 min = une latence ~1h15 = on capture déjà le palier +1h ✓ mais le gain temps réel (détection en minutes via le flux Alerts du WS) = le palier supérieur non mesuré ; (3) la demi-vie COURT = l'edge est une COURSE : la détection temps réel de derek = l'infrastructure prioritaire du livre anti-régime.

**PRÉ-LECTURE OI à 3,5 j (390 fenêtres — le recount du soir)** : les quadrants SE SÉPARENT — **H5 (OI↓+prix↓, n=46) : le drift suivant +0,156 % (méd +0,065) vs les chutes neutres -0,286 % = +0,44 pts** → l'épuisement des flush CONFIRME sa direction ; **H4 (OI↑+prix↓, n=45) : +0,012 % ≈ plat vs -0,286 % neutre = +0,30 pts — le sens OPPOSÉ au pré-enregistré** (les shorts qui pilent n'accentuent pas la chute : l'OI qui monte dans une chute = peut-être les acheteurs de dip) ; la hiérarchie complète : H5 > H4 > neutre. n=45-46/quadrant, le tir complet (train/val) reste jeudi — mais la structure émerge visiblement.

## 29/09 — LE SCAN DES PARAMÈTRES DU CASCADE : la variante profonde-rapide (CANDIDAT n°1 Aster)

| Verdict | Détail | Catégorie |
|---|---|---|
| **Le scan des paramètres du cascade** (18 combinaisons : n bougies {2,3,4} × accélération {stricte, lag} × profondeur {0, 1,5, 3 %}, non-recouvrant 24h, train/val 70/30) | LE GRADIENT DE PROFONDEUR EST MONOTONE ET TENU EN VAL : plus le flush est profond, meilleur le short — la pépite : **2 bougies accélérées avec -3 % cumulé (n=161 TR/+1,583 %, n=21 VAL/+1,054 %) = 7× l'espérance VALIDÉE de la config actuelle** (+0,148 %), pendant le régime mort ; le mode d'accélération : indifférent (strict = lag) ; n=4 : mort en VAL | **CANDIDAT n°1** — les réserves : n VAL=21, le MAE 24h non mesuré (le plafond 0-liq), l'interaction avec le gate AL non testée, le multiple-comparisons (18 combos — mais le gradient monotone des deux côtés = pas un pic isolé) |

**LE SCORECARD QUALITÉ DES DONNÉES (28/09 — l'audit complet des 7 couches)** :
VERT — klines 1h : 0 trou, 0 bougie aberrante sur 36 symboles ; CVD 15m : 100 % ;
fomo_ohlcv : 1 354 mints/6,8 M bougies, 0 prix ≤ 0 ; paper : 0 incohérence ;
swaps : 0 doublon ; depth/block_trades : à la minute.
À CONNAÎTRE — (1) oi_history : 777 trous > 16 min sur 30 symboles (~14 % de
manques intermittents, le max 188 min) → le tir H4/H5 doit TOLÉRER 1 snapshot
manquant (l'interpolation) ; (2) funding_history : 12 extrêmes LEGIT (MSTR -2,00
%/8h en avril, MEME -1,98 % le 06/09) = les événements de foule extrême des
synthétiques — un futur indicateur (le funding extrême = le marqueur de
retournement de la foule sur les synthétiques).

**LA CORRECTION D'UNITÉS DES SYNTHÉTIQUES (29/09) : le champ volume des
klines synthétiques (XAU en onces, CL en barils, les équités en parts)
N'EST PAS le volume USD — close×volume sur-surfait ×2 400 (XAU
« 1 404 M$/h » vs le RÉEL ticker/24hr quoteVolume = **14,0 M$/24h**).
LA MESURE FIABLE DE LIQUIDITÉ = ticker/24hr quoteVolume (le champ API).
LES TIERS CORRIGÉS : T1 (≥ 1 M$/24h) = 45 symboles — l'or 14 M, le
pétrole 9,7 M, l'argent 5,2 M en font partie. **LA NUANCE CAPITALE :
à la taille du user ($100-1000/position), l'or et le pétrole sur Aster
sont EXÉCUTABLES manuellement** — le verdict « liquidité insuffisante »
s'applique au backtest machine (10 %/trade composé), PAS à l'exécution
manuelle du user. Le livre macro manuel = possible dès maintenant,
l'étude du signal tendance (EMA 48h) reste CONTEXTE (n à consolider).**

**LA VALIDATION RUN_STACK DE LA VARIANTE (29/09 — le harnais complet, les ts ns convertis après le piège classique)** : la profonde-rapide 7,5x (10 %) = **$167,65 (+60 %/an environ) @ DD 8,6 %, WR 70 %, 0 liq, 4 mois négatifs/13** — un flux défensif RÉEL (la VAL-survie confirmée au wallet), PAS un record. À 5 % : DD 4,3 %. À 5x : DD 5,7 %. LA LECTURE : l'espérance par trade ×7 ne compense pas la fréquence ÷4,5 au wallet — la variante = un COMPLÉMENT de diversification (son entry timing diffère de la 3-bougies), pas un remplaçant. LE TEST MANQUANT : le COMBINÉ machine + variante (la corrélation des PnL dira si l'ajout améliore le profil complet). Le record reste +5 082/+6 419 (le joint QUBO), gelé régime T3.

**LE COMBINÉ MACHINE + PROFONDE-RAPIDE (le test final du candidat n°1)** : +13,8 % sur la machine seule au même DD (+0,8 pt) — **MAIS la corrélation des PnL mensuels = +0,894** : la profonde-rapide est le MÊME trade que la machine (shorter les mêmes majeures les mêmes jours), pas une diversification. L'ajout est marginal (l'entry-timing différent + la fréquence ajoutée), pas structurel. **LA CLÔTURE DU CANDIDAT : la profonde-rapide = un ajout marginal de même famille (+13,8 % au combiné), le record reste le joint QUBO gelé régime T3** — les couches d'octobre (les 5 + le premium) = les seules sources d'un edge structurellement nouveau.

**L'EXPANSION D'UNIVERS DU CASCADE PROFONDE-RAPIDE (535 symboles testés, 8 961 events — le test conclusif de l'expansion)** : L'EDGE NE GÉNÉRALISE PAS — T1 (liquide ≥ 1 M$/24h) : 922 events, **-1,77 %** WR 47 % ; T2 : -0,94 % ; **T3+ (illiquide) : +0,20 % WR 54 %** — l'edge existe SEULEMENT sur les microcaps illiquides où le slippage mange tout (le playground des manipulateurs, pas le nôtre). La leçon structurante : l'edge cascade des majeures/memes liquides = une propriété de CES marchés, pas une loi universelle — l'expansion d'univers ne multiplie pas l'edge, elle le DILUE. LE RECORD RESTE : le joint QUBO (+5 082/+6 419 %/an backtest, gelé régime T3), les verdicts forward en accumulation.

**LE SPOT ASTER (29/09 — la vérification de la thèse « suivre les institutions exactes »)** : le marché spot V3 existe (sapi.asterdex.com/api/v1, 254 paires) MAIS **la liquidité est trop fine pour le wallet-tracking** : le top = ASTER 2,76 M$/24h, BTC 1,0 M, le reste < 0,5 M ; aucun macro/equity au spot ; ≥ 1 M$/24h : 2 paires seulement. LA SYNTHÈSE STRUCTURELLE de la thèse « suivre les institutions exactes = gagner » : (1) **PROUVÉ sur fomo** (derek518, +18,8 %/trade, l'acteur visible et skillé) ; (2) **STRUCTURELLEMENT BLOQUÉ sur Aster perps** (les acteurs anonymes — seules les ombres : les murs défendus, l'OI H4, testés jeudi) ; (3) **TROP FIN sur Aster spot** (2,76 M$/jour au top — le build wallet-tracking ne se justifie pas à cette taille). Le suivi exact des institutions vit sur fomo, pas sur Aster — sur Aster, ce sont les PATTERNS d'ombres (jeudi).

**LE GATE SUR LA PROFONDE-RAPIDE : NUIT (la fin de la chaîne de validation)** : le gate AL p60 sur les events profonds — TRAIN gardé +1,39 % vs raw +1,47 %, VAL gardé +0,43 % vs raw +0,74 % — le gate RETIRE de la valeur ; et les quintiles S'INVERSENT (Q5 le score le plus risqué = les MEILLEURS rets : +3,12 TR/+1,44 VAL — les cascades violentes à haut score = les rebonds les plus forts). LA LEÇON CONFIRMÉE : les directions des features s'inversent entre univers (la 3e démonstration) — un gate ne se transfère JAMAIS à un univers voisin. LA FICHE FINALE DE LA PROFONDE-RAPIDE : raw sans gate, 7,5x max (MAE 12,04 %), +60 %/an @ DD 8,6 % standalone, +13,8 % au combiné (corr +0,894 même famille) — un flux défensif fin, complet et caractérisé.

**LE RE-FIRE DES MURS À 7 J (le doublement d'échantillon)** : le signal ASK-placement → le prix MONTE tient en VAL (+14,8 bp TR WR 76 % / **+23,7 bp VAL WR 77 %, n=13**) — cohérent avec le prototype ; le BID-placement → la CHUTE tient aussi (-15 bp, WR 20-29 %). LA LECTURE AFFINÉE : **les murs ne défendent pas — ils marquent les zones que le côté agressif CONSOMME** (l'inverse du spoofing classique : le mur posé = le niveau que le marché traverse). LA PERSISTANCE confirmée à 7 j : BTC 0 %, ETH 1 % (les spoofeurs éphémères), **ASTER 65 % (les acteurs réels sur son propre token)**. Le tir final 14 j jeudi : le n VAL 13 → 30+ décidera de la tradabilité.

**LE RE-TEST PRINTS À 7 J : l'effet INSTABLE (le signe flippé)** : les clusters BUY (n=63) → **+0,044 % WR 71 %** à 30 min — l'INVERSE du fade de 3 jours (-0,023 %) ; SELL → +0,030 % WR 63 %. L'effet des prints change de signe selon la semaine (le régime churn) — PAS de signal stable, la couche reste la DATA (les prints s'accumulent), le re-fire 14 j jeudi. La leçon : un effet qui flippe de signe entre 3 j et 7 j = jamais candidate sans stabilité multi-semaines.

**LE MUR D'AUTH FOMO (29/09 — le mystère à résoudre en séance dédiée)** : le login frais de ce soir produit des tokens Privy **valides, non-expirés, du bon format** — et prod-api les rejette avec "Unexpected error in JWT authentication middleware" (401). Le même fetch marchait il y a 2 jours (les 22 captures auth + les swaps 200 OK). Les testés et éliminés : l'expiration (le token valide 49 min), le kid/format (le header décodé), les headers complets de la capture (le template intégré, même 401), les cookies (transférés), l'origine (fomo.family). **LA CONSÉQUENCE : derek_watch et swaps-fresh sont BLOQUÉS tant que le mur d'auth tient — l'app du user fonctionne (il navigue), mais les fetchs des collecteurs ne passent plus.** Les pistes restantes : le fingerprint du navigateur de l'ancien daemon (Cloudflare lie la session au device ?), la rotation des clés Privy côté API, le cookie de session spécifique. L'edge derek518 (+18,8 %/trade, la demi-vie 5×) : LE PRIZE qui justifie la séance d'auth dédiée.

**LA VALIDATION MACHINE COMPLÈTE du combiné (le financement inclus — le +13,8 % CONFIRMÉ dans le cadre officiel)** : machine $265,60/DD 12,8 → COMBINÉ $302,32/DD 13,6 (+13,8 %, DD +0,8 pt), 0 liq, 3 mois nég — le même delta que dans le cadre simplifié = l'amélioration est ROBUSTE au financement. **LA PROMOTION : la profonde-rapide entre dans le paper tracking de la machine (le flux deep_fast 7,5x à côté du machine_11x) — le forward décide de la promotion v5.** L'état : le combiné = la meilleure config connue du projet dans ce cadre, l'adaptateur protège le régime mort, les couches d'octobre apportent le prochain edge.

**L'INCIDENT BAN CLOUDFLARE FOMO (29/09 ~21h UTC) : NOTRE IP EST FLAGGÉE
sur TOUT le domaine fomo (le site + prod-api + mobula = 403 depuis
python ET les navigateurs) — la conséquence de la collecte agressive
(~10k appels mobula/24h + le polling swaps horaire + les tests
répétés). IMPACT : la collecte fomo EN PAUSE totale (les swaps, l'ohlcv,
les positions), le navigateur du user bloqué aussi (le même IP).
NON-IMPACTÉ : TOUTE la collecte Aster (fapi.asterdex.com = l'autre
domaine — l'OI, le premium, les prints, les klines, le depth tournent).
LE RECOVERY : le flag Cloudflare se lève seul (10 min à 24 h), LE
SONDAGE S'ARRÊTE (chaque sonde risque de prolonger), le re-test = à la
prochaine séance. LA RÈGLE DÉFINITIVE : les cadences soutenables dès le
jour 1 sur toute nouvelle API — le topup sélectif, le pacing, le
scorecard qualité — et JAMAIS de backfill massif sans la fenêtre de
tolérance du fournisseur. Les gardes Aster : non-impactés, la
semaine de tirs continue.**

**LE DEREK_WATCH PAR DOM — LA SOLUTION DÉFINITIVE SANS API (29/09)** : le profil derek518 navigué dans la fenêtre de login loggée → **LE DOM CONTIENT TOUT** : 142 trades, les positions ouvertes (BP $14,115, neet ▲62,97 %, NASTY ▲775 %), les swaps récents parsés (12 du DOM : les achats MUSEBOOK ≥ $8,4 k ×4, le buy $14,8 k, les ventes TRUE ×2). **LE SIGNAL LIVE : les achats MUSEBOOK accumulés (5 buys, 0 sell récent — l'accumulation en cours sur un token à 34 M MC)**. LA SOLUTION DÉFINITIVE au mur d'auth : **le mining DOM du profil dans la fenêtre loggée — zéro API, zéro auth, zéro ban possible (le DOM de son propre navigateur)** — le pattern whale_radar appliqué au derek_watch. Le pipeline : la navigation profil → le parse des swaps → les signaux ≥ $5k → les paper trades. Les limitations honnêtes : les âges relatifs (3d/5d = les buckets, pas les timestamps exacts), la fréquence (le profil visite = 1×/passe).

**LES ALERTES BALEINES EN LIVE PAR DOM (29/09 — la thèse du user qui fonctionne)** : l'onglet Alerts de la fenêtre loggée → **14 alertes des 8 dernières minutes parsées** (la structure parfaite : handle/action/âge/token/montant/MC en chaîne de 8 lignes) : sonder_crypto VEND ZC $4,8K ×2 (3-5 min — le profit-taking après le ▲1 938 %), **pointfarmcap achète STONK $2K (5 min)**, **bigbabba DISTRIBUE PAID ×6 ($11-27K chacune ≈ $108K total !) et tourne sur HOOKED $2K ×2 (MC $1,3M — la rotation vers le small cap)**. **L'INDICATEUR INSTITUTIONNEL LIVE : les distributions massives (PAID $108K) + les rotations (HOOKED) = les signaux qui suivent les acteurs VISIBLES — sans API, sans ban possible (le DOM de la session loggée)**. Le stockage : data/fomo/alerts_live.json (le flux cumulé avec la déduplication). Le prochain build : le mineur Alerts résident 5 min + les règles de signal (la distribution = vendre/éviter, la rotation = suivre).
