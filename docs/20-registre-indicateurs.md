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

**LE MINEUR ALERTS PROPRE (29/09 — le parse validé après le restart)** : les alertes baleines parsées proprement — 13 alertes/13 minutes : **bigbabba DISTRIBUE PAID (4 ventes $11-17K en 1 min ≈ $60K) et ACCUMULE HOOKED (3 achats $1-2K)** = la rotation institutionnelle visible ; sonder_crypto take-profit ZC ×2 (après le ▲1 938 %) ; pointfarmcap achète STONK $2K. LE STOCKAGE : alerts_parsed.json + les séries. LE MINEUR RÉSIDENT : le prochain wire (le loop 5 min sur la fenêtre loggée → les signaux en continu).

## 01/10 — openmarket x501 : les 3 tests A/B PRÉ-ENREGISTRÉS des vagues 1-2 (docs/27-28, moteur x501_verdict_ab.py)

**Le contexte** : les vagues 1-2 du plan d'exploitation kScript sont activées (le filtre de régime institutionnel RI = les 5 composantes premium ETF flow/CME OI/DVOL/skew/LSR ; le pattern absorption orderbook = mur/attaque/tenue/reprise en fonctions natives). AVANT tout run, les critères de promotion/kill sont figés dans `docs/28-protocole-ab-x501.md` et appliqués par le moteur déterministe (`x501_verdict_ab.py`, bootstrap 10 000, seed 501) — personne ne décide après coup. La config officielle du domaine (MC v20, baseline 2026-10-01) reste intouchable tant que le verdict n'est pas PROMOTION.

| test (symbole 1h) | jambe A (contrôle) | jambe B (traitement) | critère PRÉ-ENREGISTRÉ de promotion | statut |
|---|---|---|---|---|
| RI-BTC (BTCUSDT) | Signature H1 | Signature H1 + filtre RI (seuil ±0,10, poids égaux figés) | n_B ≥ 20 ET P(bootstrap méd_B > méd_A) ≥ 0,70 ET Δméd ≥ +0,10 R ET maxDD_B ≤ maxDD_A + 2,0 R | **PRÉ-ENREGISTRÉ 01/10/2026 — verdict à l'export des CSV** |
| RI-ETH (ETHUSDT) | Signature H1 | idem | idem | **PRÉ-ENREGISTRÉ 01/10/2026 — verdict à l'export des CSV** |
| ABS-BTC/ETH (BTCUSDT, ETHUSDT) | Signature H1 | Absorption H1 (mur ≥ 3× moy 200, attaque ≥ 2×, tenue ≤ 0,8 %, reprise ≥ 1,2) | idem avec N_MIN = 12 (profondeur orderbook limitée en backtest — falsification initiale, tout PROMOTION reste CANDIDAT au papier forward) | **PRÉ-ENREGISTRÉ 01/10/2026 — verdict à l'export des CSV** |

**Les verdicts intermédiaires impossible à manquer** (pré-enregistrés) : `n_B ≥ 97 % de n_A` = DATA_ABSENTE (le filtre n'a rien filtré, fail-open — problème de data, pas verdict de signal) ; `P ≤ 0,40` avec n_B ≥ 10 = KILL (anti-signal, entrée NUL avec les chiffres) ; sinon INCONCLU — **et le cas attendu est INCONCLU** : les CSV de référence portent 16 trades (BTC) / 15 (ETH), donc n_B < 20 presque à coup sûr avec le RI actif. La règle est écrite AVANT : fenêtre élargie et re-run, JAMAIS de promotion sous N_MIN — pas même quand le bootstrap sourit (la démo du moteur sur les CSV existants l'illustre : P = 0,9358 mais n_B = 15 → INCONCLU imposé). La vague 3 (hygiène broker : trail natif, ocaName, cancelAll, rapport natif) est active dans les `_MK` avec useNativeTrail=false par défaut — la référence MC v20 reste bit-à-bit.

## 01/10 — openmarket x501 : le banc de test local KILLE les filtres continus de flux taker et de funding (vague 5, docs/30, x501_flux_local.py)

**Le pré-enregistrement AVANT la mesure** : grille figée dans l'en-tête du script AVANT tout chiffre — 12 cellules de panel (flux taker : D = 2·tbqv/qv − 1, EMA L ∈ {6, 24, 72} barres ; funding : moyenne K ∈ {9, 21, 90} paiements 8h ; horizons H ∈ {24, 72} barres open→open), hypothèses gravées (flux = CONTINUATION attendue, funding = CONTRARIAN attendu), verdict mécanique au critère AUC du domaine (IC 95 % bootstrap 1 000 par journées seed 501 contient 0,5 et |AUC−0,5| < 0,02 = KILL ; exclut 0,5 avec |AUC−0,5| ≥ 0,05 et sens confirmé = CANDIDAT au re-test 60 j frais).

| cellule (panel 80 symboles × 1 092 j = 2 053 975 barres, 0 gap) | AUC | IC 95 % | delta médian | verdict |
|---|---|---|---|---|
| flux L6/L24/L72 × H24/H72 (6 cellules) | 0,5008 – 0,5038 | tous contiennent 0,5 | +9,3 à +31,9 bps | **KILL ×6** |
| funding K9/K21/K90 × H24/H72 (6 cellules) | 0,4956 – 0,5103 | tous contiennent 0,5 | −21,7 à +46,7 bps | **KILL ×6** |
| pool P1 : flux L24 (469 entrées, CONTEXTE in-sample) | — | — | delta méd +0,089 R, P = 0,686 | **INCONCLU** (< 0,70 et < +0,10 R) |
| pool P1 : funding K21 (CONTEXTE) | — | — | delta méd −0,096 R, P = 0,359 | **INCONCLU** |

**La plomberie est prouvée vivante** (le point qui fait la valeur du KILL) : le test d'altération de la QA — décaler le score d'une barre vers l'avant (look-ahead) fait DÉCOLLER l'AUC (BTC 0,5306 vs 0,5079 strict ; sur le rendement intrabar de la même barre : **BTC 0,6103 / ETH 0,6065**) — le flux taker contient de l'information, le harnais la voit, et le verdict strict ~0,5 est donc réel. AUC par symbole sur 8 liquides ≈ 0,5 (0,4978/0,5022/0,5009) : le pooling ne dilue rien. Re-exécution bit à bit.

**Statut : KILL des filtres continus** (le niveau EMA du flux, la moyenne du funding — 5e falsification fermée du domaine après fz, flush OI, ML). **NON réfuté** : le pattern absorption ÉVÉNEMENTIEL de la vague 2 (mur/attaque/tenue/reprise à 4 conditions ordonnées — le champ orderbook n'a pas d'équivalent klines) — son juge reste le protocole A/B docs/28. Re-test interdit sans pré-enregistrement explicite d'une hypothèse nouvelle.

## 01/10 — openmarket x501 : le banc d'ÉVÉNEMENTS de l'absorption réfute la prime de structure en proxy klines + priorise la file de runs (vague 6, docs/31, x501_abs_events_local.py)

**Le pré-enregistrement AVANT la mesure** : le pattern absorption de la vague 2 (mur / attaque / tenue / reprise, 4 conditions ordonnées) transposé klines avec les invariants réels (tbqv ≤ qv, D ∈ [−1, 1]) — décision à l'OPEN de T (mur T−3 : volume ≥ 3× SMA200 ; attaque T−2 : vague taker directionnelle ≥ 2× SMA100 ; tenue T−1 : l'extrême tient à 0,8 % ; reprise T−1 : EMA(D, 6) bascule côté mur), 3 définitions IMBRIQUÉES pré-déclarées (E1 = attaque seule ; E2 = + tenue + reprise ; E3 = + mur), 3 × 2 directions × 2 horizons = 12 cellules au critère AUC du domaine (Mann-Whitney événement vs non-événement, IC 95 % bootstrap journées seed 501, seuils inchangés) + 4 cellules de PRIME DE STRUCTURE (delta médianes E3 − E1, bootstrap 10 000 ; JUSTIFIE : IC exclut 0 ET delta ≥ +6 bps ET n_E3 ≥ 12) + projection pool P1 (CONTEXTE) + règle de lecture de la masse d'ex-aequo pré-déclarée (médiane 0,0 avec ≥ 50 % de zéros = NON_INTERPRETABLE).

| cellule (80 symboles × 2 053 975 barres 1h, 01/10/2023 → 27/10/2026, 0 gap) | n events | AUC / delta | verdict |
|---|---|---|---|
| LONG E1 attaque seule, H24 / H72 | 219 068 / 218 649 | AUC 0,5114 / 0,5172, Δ +10,9 / +34,1 bps | **INCONCLU ×2** (IC H72 exclut 0,5, séparation 0,0172 < 0,05) |
| LONG E2 structure sans mur, H24 / H72 | 45 155 / 45 106 | AUC 0,5033 / 0,5052, Δ −11,1 / −12,9 bps | **KILL ×2** |
| LONG E3 complet, H24 / H72 | 11 018 / 11 004 | AUC 0,4943 / 0,4957, Δ −26,4 / −38,3 bps | **KILL ×2** |
| SHORT E1/E2/E3, H24/H72 (6 cellules) | 215k / 141k / 64k | AUC 0,4767 – 0,4886, Δ −10,1 à −34,0 bps | **CONTEXTE ×6** (anti-signal : le mur perd) |
| PRIME de structure E3 − E1, LONG H24 / H72 | 11 018 | Δ −26,4 bps (P = 0,069) / −54,2 bps (P = 0,038) | **ABS_DEPRIORISE ×2** (la structure SOUSTRAIT) |
| PRIME de structure, SHORT H24 / H72 | 63 586 / 63 369 | Δ +0,0 (IC [0, 0]) — 62,7 % de zéros exacts | **NON_INTERPRETABLE ×2** (médiane dans la masse des liens) → ABS_DEPRIORISE |
| pool P1 (CONTEXTE in-sample) | 12/469 matchés | Δ +0,13 R, P = 0,652 | **INCONCLU** (< gate 0,70) |

**La lecture mécanique** : l'AUC LONG descend en cascade E1 → E2 → E3 (0,5114 → 0,5033 → 0,4943 à H24) — **chaque condition de confirmation DÉGRADE le signal** : le rebond se joue DANS la barre de tenue, à l'open de décision l'absorption est déjà payée (la structure est TARDIVE, pas fausse). Côté SHORT, toutes les cellules < 0,5 : les attaques acheteuses « absorbées » précèdent la CONTINUATION haussière — la dynamique traverse le mur (l'asymétrie breakout du pool P1 et la leçon registre Aster confirmées). Le proxy klines du mur (volume ≥ 3× SMA200 sans contexte carnet) sélectionne la plaine illiquide : 62,7 % des E3 SHORT ont un rendement forward EXACTEMENT nul contre 18,9 % des E1. La QA (9 familles, 62 contrôles, 0 échec) teste le détecteur sur séries synthétiques (chaque condition violée isolément), le nesting E3 ⊆ E2 ⊆ E1 sur données réelles, le zéro look-ahead par mutation des barres futures, et la re-exécution bit à bit (7 535 octets). Les événements existent sur les symboles des runs (BTC 278 E3 LONG / 351 SHORT, ETH 204 / 334) : le run ABS ne sera pas DATA_ABSENTE.

**Statut : KILL de l'ombre klines du pattern absorption** (la 6e falsification du domaine) + **DÉCISION de priorisation pré-déclarée : ABS_DEPRIORISE** — les runs 3-4 (ABS) du protocole docs/28 passent EN QUEUE de file (ordre recommandé : RI → MK6 → TRAIL → ABS). **NON réfuté** : le pattern ORDERBOOK réel (maxBidAmount) — son juge reste le protocole, renforcé par le contraste : un PROMOTION sur ABS là où l'ombre klines est morte prouverait la valeur UNIQUE du champ carnet. Les 3 définitions E1/E2/E3 sont closes en klines — aucune variante sans champ orderbook ne rentre dans un kScript.

## 01/10 — openmarket x501 : le banc des RÉFÉRENCES DE LIQUIDITÉ ferme vwap et volume profile aux deux hypothèses (vague 7, docs/32, x501_refs_local.py)

**Le pré-enregistrement AVANT la mesure** : les 2 derniers pouvoirs d'analyse réels du registre docs/27 (vwap, volume profile — 0 script depuis le début, les briques payantes de TradingView) passés au banc local AVANT tout run plateforme. Convention temps stricte des vagues 5-6 (décision à l'open de T, barres ≤ T−1) ; VWAP de session ancré 00h UTC (tp = (h+l+c)/3, pondération quote_volume, reset journalier, évalué à T−1) ; volume profile de la veille (le jour D−1 COMPLET : allocation uniforme de chaque barre 1h sur [low, high], 48 bins, VPOC ex-aequo → le bin le plus bas, value area 70 % par expansion gourmande ex-aequo → le dessous). Grille PRÉ-DÉCLARÉE de 28 cellules : V1 aimant vwap (mean-reversion, seuils 0/0,5 %/1 %) × 12, V2 cross vwap (continuation) × 4, P1 aimant VPOC × 4, P2 rejet value area × 4, P3 breakout value area × 4 — P2 et P3 conditionnent les MÊMES événements avec des attentes OPPOSÉES (le litige mean-reversion vs breakout tranché par la donnée). Robustesses pré-déclarées : panel LIQUIDE8, focus BTC/ETH, AUC par symbole. Critère AUC du domaine inchangé (IC 95 % bootstrap 1 000 journées seed 501, réduction 50 k) + règle d'ex-aequo (≥ 50 % de zéros flaggés = NON_INTERPRETABLE). Pool P1 en CONTEXTE (F1 mauvais côté vwap, F2 hors value area, flags sur open(T) — la colonne entry du pool = open×(1 + side×2 bps), l'entrée 2 bps adverse, convention vague 4 re-vérifiée 469/469).

| cellule (80 symboles × 1 092 j = 2 048 055 décisions, 0 gap, 288 s) | AUC (min–max) | verdict |
|---|---|---|
| panel POOL80 (28 cellules) | 0,4864 – 0,5136 (médiane 0,5039) | **27 KILL + 1 INCONCLU** (V1 s=1 % LONG H24, IC [0,50001 ; 0,5297], séparation 0,013 < 0,05) |
| panel LIQUIDE8 (28 cellules) | 0,4851 – 0,5149 (médiane 0,5037) | **28 KILL** |
| P2 rejet VA LONG H72 (le meilleur delta) | AUC 0,5136, Δ +44,4 bps | **KILL** (IC contient 0,5 — la queue, pas une séparation de rangs) |
| P3 breakout SHORT H72 (miroir exact de P2) | AUC 0,4864, Δ −44,4 bps | **KILL** (mêmes événements, attente opposée — ni rejet ni continuation) |
| pool P1 : F1 mauvais côté vwap | 343/126, ΔR −0,581, P = 0,42 | **INCONCLU** (sous le gate — jamais une promotion in-sample) |
| pool P1 : F2 hors value area | 116/353, ΔR +0,148, P = 0,52 | **INCONCLU** |

**La lecture mécanique** : aucune famille ne surnage, aucun symbole ne surnage (max ≈ 0,528 isolé) ; le delta médian le plus flatteur (+44,4 bps) vient de la queue des distributions et non d'une séparation de rangs — un delta sans AUC n'est pas un plan (la leçon des fallbacks de docs/29 répétée). La QA (39 contrôles, 0 échec) prouve la plomberie VIVANTE : le détecteur voit une aimantation plantée (AUC 0,911) et une continuation plantée (AUC 0,929) ; le zéro look-ahead est prouvé par mutation des barres futures — y compris la tentation la plus subtile : le profil de la journée EN COURS n'entre jamais dans la décision, la veille seule ; re-exécution bit à bit (digest 6af839e09c6136e8…).

**Statut : KILL de vwap et volume profile** (les deux hypothèses, les deux panels) — **la 7ᵉ falsification du domaine** (fz, flush OI, ML, hypothèse fill maker docs/29, flux/funding, absorption-proxy, vwap + volume profile). La famille analyse de docs/27 est CLOSE : `ltf()` et `minBid/minAskAmount` restent documentés SANS data locale équivalente, le langage et la visu restent de la dette de style. Re-test interdit sans pré-enregistrement explicite d'une hypothèse nouvelle.

## 01/10 — openmarket x501 : le banc de l'OPEN INTEREST 1h ferme le capital affiché aux deux hypothèses de continuation (vague 8, docs/33, x501_oi_local.py)

**Le pré-enregistrement AVANT la mesure** : l'OI 1h — la matière première désignée par docs/26 (« OI 1h en tête ») — testée en TÉMOIN DE CONTINUATION (l'hypothèse inverse du flush OI déjà tué) sur les 12 symboles om_v27, klines ET OI du MÊME exchange (Bybit v5, la sémantique d'exécution du domaine, zéro cross-exchange dans le panel). Grille PRÉ-DÉCLARÉE de 10 cellules : Étude A « capital brut » (score = ΔOI%_L = 100×(OI[t−1]/OI[t−1−L]−1), L ∈ {24, 72, 168} × H ∈ {24, 72}, dichotomie médiane) ; Étude B « mouvement financé » (score = signe(r_L) × ΔOI%_L, cible ALIGNÉE fwd × signe(r_L), L ∈ {24, 72} × H ∈ {24, 72}) ; pool P1 en CONTEXTE. Convention temps stricte transposée de la correction v27 : le snapshot hh:00 marque l'OUVERTURE de sa fenêtre, à l'open de T le dernier snapshot connu est (T−1):00 — le snapshot simultané n'est JAMAIS lu ; existence PILE exigée (0 fill-forward). Critère AUC du domaine inchangé (IC 95 % bootstrap 1 000 journées seed 501, réduction 50 k).

| cellule (12 symboles × 749 j = 216 000 barres, 0 gap, 0 doublon, 0 snapshot absent) | AUC (min–max) | delta médian | verdict |
|---|---|---|---|
| A capital brut, L ∈ {24,72,168} × H ∈ {24,72} (6 cellules) | 0,4917 – 0,5006 | −19,7 à +5,7 bps | **KILL ×6** |
| B mouvement financé, L ∈ {24,72} × H ∈ {24,72} (4 cellules) | 0,4936 – 0,5019 | −9,5 à +9,2 bps | **KILL ×4** |
| pool P1 ΔOI% 24h (186/469 entrées, CONTEXTE in-sample + cross-exchange L2) | — | +0,281 R, P = 0,660 (IC [−1,02, +1,23]) | **INCONCLU** (< gate 0,70) |

**La lecture mécanique** : le capital affiché ne prédit pas la direction — ni brut (H_OI1), ni conditionné au quadrant prix (H_OI2) ; les deltas descriptifs restent sous l'étalon 12,2 bps aller-retour taker (un delta sans AUC n'est pas un plan). C'est le même verdict que les trois autres familles de positionnement (flux taker, funding, absorption-proxy) : sur perps USDT 1h, les témoins de positionnement ne portent pas d'edge directionnel exploitable à nos horizons. La QA (47 contrôles, 0 échec) prouve la plomberie vivante : le détecteur (OI planté corrélé au forward → AUC 0,66 CANDIDAT), le cas nul (KILL), le zéro look-ahead par mutation multiplicative+additive des snapshots futurs (scores passés bit à bit), la re-exécution bit à bit de l'étude complète (digest b4b55400b05a69d1…), le pool 469/469 (entry = open×(1 + side×2 bps), convention vague 4).

**Statut : KILL de l'OI 1h en signal continu et en quadrant** — **la 8ᵉ falsification du domaine** (fz, flush OI, ML, hypothèse fill maker docs/29, flux/funding, absorption-proxy, vwap + volume profile, OI 1h). **NON réfuté (hors périmètre du banc)** : l'OI en événement de liquidation real-time (flux websocket des liquidations — autre mécanique, autre data), l'OI 1 j pré-2024 en contexte de régime, le LSR 4 h (8 jours de data, statut « collecté pour plus tard »). Re-test interdit sans pré-enregistrement explicite d'une hypothèse nouvelle.

## 01/10 — openmarket x501 : le banc de l'OI en CONTEXTE DE RÉGIME ferme le mécanisme marginal et documente le conditionnel (vague 9, docs/34, x501_oi_regime_local.py)

**Le pré-enregistrement AVANT la mesure** : la case laissée ouverte par la vague 8 (« l'OI 1 j pré-2024 en contexte de régime », docs/33) — le NIVEAU du capital (z-score roulant de l'OI, par opposition au FLUX ΔOI déjà tué) testé comme conditionneur de la distribution des rendements futurs sur les 12 symboles om_v27 (même collecte versionnée vague 8, Bybit v5, 216 000 barres × 749 j, 0 gap, 0 snapshot absent). Grille PRÉ-DÉCLARÉE de 8 cellules + pool : Étude A « magnitude » (H_R1, la seule hypothèse que la théorie du levier pré-dit : capital haut → |fwd_H| plus grand, MONOTONE ; score = z_L(OI[t−1]), L ∈ {720, 2160} × H ∈ {24, 72}, sens attendu +1) ; Étude B « niveau → direction » (AUCUNE hypothèse pré-déclarée, sens = 0 — toute séparation = CONTEXTE par définition) ; pool P1 en CONTEXTE (z_720 au t_in, split médian, bootstrap diff de médianes 10 000). Convention temps stricte vague 8 inchangée (snapshot simultané JAMAIS lu, existence PILE, 0 fill-forward) ; cas dégénéré pré-déclaré (std → 0 → décision invalidée) ; critère AUC du domaine inchangé.

| cellule (12 symboles × 749 j = 216 000 barres) | AUC (min–max) | delta médian | verdict |
|---|---|---|---|
| A magnitude z_L(OI) → \|fwd\|, L ∈ {720,2160} × H ∈ {24,72} (4 cellules) | 0,5028 – 0,5150 | +6,8 à +24,7 bps | **KILL ×3 + INCONCLU ×1** |
| B niveau z_L(OI) → fwd signé (sens = 0, aucune hypothèse), 4 cellules | 0,5014 – 0,5152 | −0,2 à +20,9 bps | **KILL ×4** |
| pool P1 z_720 (181/469 entrées, CONTEXTE in-sample + cross-exchange L4) | — | +0,469 R, P = 0,8192 (IC [−0,90, +1,35]) | **CONTEXTE — franchit le gate 0,70** |

**La lecture mécanique** : H_R1 (la théorie du levier : plus de capital affiché → plus de grands mouvements) est REFUSÉE au critère du domaine — 3 KILL + 1 INCONCLU, le seul IC qui exclut 0,5 (L720_H72, AUC 0,5150) est 3,3× sous le gate CANDIDAT 0,05 ; le test directionnel sans hypothèse est 4/4 KILL, cohérent avec la vague 8 (le flux ne finance pas une direction, le niveau non plus). Le conditionnel existe dans la donnée : sur les 181 entrées du pool P1 du panel, le régime OI-haut sépare +0,469 R de médiane (WR 52,2 % vs 45,1 %) avec P = 0,8192 ≥ 0,70 — le PREMIER contexte des bancs locaux qui franchit le gate mécanique — mais trois garde-fous pré-déclarés : in-sample (le pool est déjà une sélection), cross-exchange (entrées Binance × OI Bybit), IC contenant largement 0. Le contraste marginal (AUC ≈ 0,51 partout) vs conditionnel est la leçon vague 6 à l'envers : le régime ne dit rien en marginal et se montre éventuellement en interaction avec un événement directionnel — le rôle exact d'un filtre de contexte, jamais d'un signal. Ce résultat AUTORISE : l'entrée du filtre « régime OI » dans la liste des candidats au protocole A/B (docs/28) sans toucher à la priorisation de la file (RI → MK6 → TRAIL → ABS). Il N'AUTORISE PAS : toute promotion des chiffres C, tout re-test sans pré-enregistrement. La QA (63 contrôles, 0 échec) prouve la plomberie vivante : détecteur monotone (niveau planté dans la magnitude, décalage vague 8 → AUC > 0,55 CANDIDAT ; la même plomberie décolle sur le signé), cas nul KILL, zéro look-ahead par mutation multiplicative+additive des snapshots ET des barres futures, snapshot simultané jamais lu par sa barre (test segmenté), rolling_z en unitaires (cas à la main L=3, boucle naïve, amorçage, NaN propagé, fenêtre plate → NaN — bug réel corrigé : les erreurs float de var = s2/L − m² produisaient ±inf, seuil relatif 1e-6 gravé), sens = 0 ne promeut jamais, pool 469/469 (convention vague 4), re-exécution bit à bit (digest bf0b77ac6a74d8be…).

**Statut : KILL de l'OI en régime marginal (magnitude monotone + direction) — la 9ᵉ falsification du domaine** (fz, flush OI, ML, hypothèse fill maker docs/29, flux/funding, absorption-proxy, vwap + volume profile, OI 1h, OI-régime) — **5ᵉ verdict symétrique des familles de positionnement** (flux taker, funding, absorption-proxy, OI-flux, OI-niveau). **CONTEXTE documenté, NON PROMU** : le conditionnel pool P1 (P = 0,8192) — à trancher uniquement par un run A/B dédié si le user le décide. **NON réfuté (hors périmètre)** : l'OI en événement de liquidation real-time (websocket, autre mécanique), la forme en U de H_R1 (limite L8 : la dichotomie médiane ne capte que le monotone — extension exigerait un pré-enregistrement), le LSR 4 h (8 jours de data). Re-test interdit sans pré-enregistrement explicite d'une hypothèse nouvelle.

## 01/10 — openmarket x501 : le banc de la FORME EN U — les 2 premiers CANDIDATS marginaux du domaine (vague 10, docs/35, x501_oi_ushape_local.py)

**Le pré-enregistrement AVANT la mesure** : la case explicitement ouverte par la vague 9 (limite L8 — la dichotomie médiane ne capte que le monotone) — la FORME concurrente de la théorie du levier, pré-enregistrée le 01/10/2026 AVANT toute cellule regardée : la volatilité est maximale aux DEUX EXTRÊMES du régime (capital très haut → cascades ; capital très bas → re-pricing volatil post-purge), le centre est calme — la forme en U. Grille PRÉ-DÉCLARÉE de 12 cellules + pool : Étude A1 « le U joint » (score = |z_L(OI[t−1])|, centre pré-déclaré à 0, cible |fwd_H|, sens +1, L ∈ {720, 2160} × H ∈ {24, 72}) ; Étude A2 « le côté bas seul » (le DISCRIMINANT : sous-échantillon z < 0, sens attendu −1 — le monotone H_R1 prédit l'opposé) ; Étude B « miroir directionnel » (|z| → fwd signé, sens = 0) ; Étude C pool P1 en strates |z_720| (extrêmes = quantile 80 %, centre = le reste, bootstrap diff de médianes 10 000). COMPOSITION PRÉ-DÉCLARÉE : U VIVANT ⇔ A1 CANDIDAT(+1) ET A2 CANDIDAT(−1) même cellule ; KILL-U si A2 sort AUC > 0,5 hors IC ; sinon NON ÉTABLI. Convention temps stricte vagues 8/9 inchangée ; critère AUC du domaine inchangé ; panel 12 symboles om_v27 inchangé (Bybit, 216 000 barres × 749 j, 0 doublon, 0 gap, 0 snapshot absent).

| cellule (12 symboles × 749 j = 216 000 barres) | AUC (min–max) | delta médian | verdict |
|---|---|---|---|
| A1 le U joint \|z_L\| → \|fwd\| (4 cellules) | 0,5149 – 0,5350 | +20,4 à +44,5 bps | **INCONCLU ×4** (IC excluent 0,5 mais tous sous le gate 0,05) |
| A2 côté bas seul z<0 → \|fwd\|, sens −1 (4 cellules) | 0,4415 – 0,4915 | −14,0 à **−82,8** bps | **2 KILL (L720) + 2 CANDIDAT (L2160)** |
| composition du U (pré-déclarée, 4 cellules) | — | — | **U NON ÉTABLI ×4** |
| B miroir directionnel \|z\| → fwd signé (sens = 0, 4 cellules) | 0,4831 – 0,4954 | −5,2 à −27,6 bps | **KILL ×4** |
| pool P1 strates \|z_720\| ≥ q80 (37 extrêmes vs 144 centre, CONTEXTE) | — | +0,934 R, P = 0,7381 (IC [−1,03, +1,44]) | **CONTEXTE — franchit le gate 0,70 (2ᵉ fois)** |

**La lecture mécanique** : le U joint n'est PAS établi au critère du domaine (l'IC exclut 0,5 sur les 4 cellules — une séparation existe — mais 1,5–3,5 pts d'AUC, tous sous le gate CANDIDAT 0,05 ; la composition pré-déclarée la refuse). MAIS le DISCRIMINANT décolle : à L = 90 j, les z TRÈS négatifs (l'extrême bas de l'OI) portent un |fwd| médian +52 à +83 bps plus grand que les z négatifs modérés (AUC 0,4415 / 0,4454, IC excluant franchement 0,5, sens −1 confirmé) — **les 2 premiers CANDIDATS marginaux du domaine en 10 vagues**, et le delta de magnitude dépasse l'étalon 12,2 bps A/R taker. La cohérence théorique est exacte : la falsification n°2 (flush OI) était tuée en DIRECTION — ici on mesure la MAGNITUDE post-purge : l'extrême bas prédit l'AMPLITUDE, jamais le sens (miroir directionnel 4/4 KILL). L'asymétrie est la découverte : côté haut faible (vague 9 : AUC 0,5028–0,5150), côté bas fort (vague 10 : AUC 0,4415–0,4454) — pas un U symétrique, un régime de purge unilatéral. Le conditionnel existe des DEUX côtés : split médian OI-haut (vague 9, P = 0,8192) et extrêmes |z| (vague 10, P = 0,7381) franchissent tous deux le gate de contexte (garde-fous inchangés : in-sample, cross-exchange, n_extr = 37, IC contenant largement 0). La QA (79 contrôles, 0 échec, 1 skip déclaré : data Binance absente de la machine) prouve la plomberie vivante : le détecteur du U planté (A1 CANDIDAT + A2 CANDIDAT → U VIVANT), le détecteur MONOTONE refusé par la composition (A2 sens opposé → KILL-U même si A1 décolle — le banc distingue les deux formes), le cas nul KILL, la composition en 7 branches unitaires, le zéro look-ahead par mutation multiplicative+additive des snapshots ET des barres futures (scores signés ET |z| bit à bit), le snapshot simultané jamais lu, re-exécution bit à bit (digest 3f9fb7781eaeb401…).

**Statut : le U joint NON ÉTABLI — le comptage des falsifications RESTE à 9** (fz, flush OI, ML, hypothèse fill maker docs/29, flux/funding, absorption-proxy, vwap + volume profile, OI 1h, OI-régime) ; le miroir directionnel re-ferme la famille directionnelle (KILL ×4). **CANDIDATS (jamais promotion, la voie = protocole A/B docs/28)** : le côté bas de la purge à L2160 (AUC 0,4415 / 0,4454 — premiers candidats marginaux du domaine) et le contexte pool strates |z| (P = 0,7381 — 2ᵉ contexte au-dessus du gate) — sans toucher à la priorisation de la file (RI → MK6 → TRAIL → ABS). **NON réfuté (hors périmètre)** : l'OI en événement de liquidation real-time (websocket), le LSR 4 h (8 jours), un centre de U décalé ≠ 0 (pré-enregistrement propre requis), les strates quintiles strictes. Re-test interdit sans pré-enregistrement explicite d'une hypothèse nouvelle.

## 01/10 — openmarket x501 : le banc du LSR ferme la dernière source premium — la 10ᵉ falsification (vague 11, docs/36, x501_lsr_local.py)

**Le pré-enregistrement AVANT la mesure** : la dernière source premium du filtre RI (composante n°5 « LSR top traders contrarian », docs/27) mise au banc — le collecteur versionné `x501_collect_lsr_v11.py` (Bybit v5 public, endpoint `/v5/market/account-ratio`, pagination `cursor` fonctionnelle — le paramètre `interval` n'existe pas, mesuré ; règle anti-partiel pré-enregistrée : ligne T > now − 3P droppée, la sonde `lsr_probe_v11` a mesuré que la fenêtre en cours est publiée pendant sa fenêtre) porte le LSR de 8 j intestables à **72 000 lignes 4h + 13 200 lignes 1d, 12 symboles, fenêtre commune 2024-01-05 → 2026-09-30 (~2,74 ans), 0 doublon, 0 gap, 0 valeur hors domaine**. Grille PRÉ-DÉCLARÉE de 13 cellules : Étude A contrarian NIVEAU (z_L(buyRatio 4h) → fwd signé, sens −1, l'hypothèse du filtre RI : la foule longue pré-cède la baisse) ; Étude B FLUX du positionnement (la bascule des comptes, ΔbuyRatio → fwd signé, sens −1 — discrimination exacte avec la vague 8 qui mesurait le flux du CAPITAL) ; Étude C réplication 1d (la profondeur séculaire du même endpoint) ; Étude D pool P1 CONTEXTE (z_180 au t_in, dernière ligne close par searchsorted, split médian, bootstrap 10 000). Convention temps stricte vagues 8/9/10 transposée (la ligne pile à l'open JAMAIS lue — règle de consommation sûre sous les deux interprétations d'estampillage) ; critère AUC du domaine inchangé ; 48 snap absents (queue de fenêtre, refroidissement anti-partiel, prouvé par la QA S8.4).

| cellule (12 symboles × ~2,74 ans = 72 000 barres 4h + 13 200 lignes 1d) | AUC (min–max) | delta médian | verdict |
|---|---|---|---|
| A contrarian niveau z_L(buyRatio 4h) → fwd signé, sens −1 (4 cellules) | 0,4863 – 0,4920 | −2,4 à −20,3 bps | **KILL ×4** |
| B flux du positionnement ΔbuyRatio → fwd signé, sens −1 (4 cellules) | 0,4758 – 0,4919 | −1,7 à −52,7 bps | **KILL ×2 + INCONCLU ×2** (D42 : IC excluent 0,5 mais 2–3× sous le gate 0,05) |
| C réplication 1d z_L(buyRatio 1d) → fwd signé, sens −1 (4 cellules) | 0,4883 – 0,5054 | −22,1 à +11,7 bps | **KILL ×4** |
| D pool P1 z_180 contrarian (n = 239/469, CONTEXTE in-sample + cross-exchange L4) | — | ΔR −0,315, P(Δ<0) = 0,8009 | **CONTEXTE — franchit le gate de contexte dans le sens contrarian pré-déclaré (jamais promotion)** |

**La lecture mécanique** : le contrarian NIVEAU — le cœur de la composante RI — est KILL 4/4 sur le panel 4h ET 4/4 sur la réplication 1d (tous les IC contiennent 0,5) ; le flux 1 j est KILL ; le flux 7 j laisse une trace directionnelle réelle (2 IC excluant 0,5, delta H18 −52,7 bps au-dessus de l'étalon 12,2) mais 2–3× sous le gate CANDIDAT — un delta sans AUC n'est pas un plan (leçon vague 7). La cohérence de DIRECTION est documentée : 10/12 cellules panel ont un AUC < 0,5 (sens contrarian pré-déclaré) et le pool P1 sépare dans le MÊME sens (les entrées faites foule longue perdent −0,315 R, P(Δ<0) = 0,8009 ≥ gate) — mais la direction qui se montre partout sans jamais franchir le gate d'amplitude n'est PAS un signal. La convention de signe du gate pool (écrite pour un sens +1 aux vagues 9/10, transposée au sens −1 de la famille) est une ambiguïté du pré-enregistrement ASSUMÉE — leçon enregistrée : graver le sens du gate pool explicitement. Le n = 239 (vs 181 vague 9) s'explique par la règle searchsorted (dernière ligne close consommée, sans exigence d'alignement pile avec une open kline — même garantie zéro look-ahead, prouvée QA S7). La QA (49 contrôles, 0 échec) prouve la plomberie vivante : détecteur contrarian planté sur pipeline synthétique complet en 3 runs (4h planté → étude A CANDIDAT, 1d nul du même run → jamais CANDIDAT ; 1d planté → étude C CANDIDAT ; tout nul → rien), zéro look-ahead par mutation multiplicative+additive des lignes LSR ET des opens klines (scores passés bit à bit, contrôle inverse : muter le passé change le futur), ligne simultanée jamais lue (test segmenté), 4 branches du verdict en unitaire (KILL par multisets identiques → AUC pile 0,5), pool 469/469 + règle searchsorted, audit de collecte (cutoffs anti-partiel, grille pile, domaine (0,1)), re-exécution bit à bit (digest c8478385f7fce150…).

**Statut : KILL du LSR contrarian niveau (4/4 + réplication 4/4), KILL du flux 1 j, INCONCLU sous le gate pour le flux 7 j — LA 10ᵉ FALSIFICATION DU DOMAINE** (fz, flush OI, ML, hypothèse fill maker docs/29, flux/funding, absorption-proxy, vwap + volume profile, OI 1h, OI-régime, LSR). **Le comptage des CANDIDATS marginaux reste à 2** (vague 10, côté bas de la purge). **CONTEXTE documenté, NON PROMU** : le conditionnel pool P1 contrarian (P = 0,8009) — 3ᵉ contraste conditionnel au-dessus du gate de contexte — à trancher uniquement par un run A/B dédié si le user le décide. La composante RI reste câblée telle quelle (fail-open pré-enregistré) : le banc teste la FAMILLE (LSR tous comptes Bybit, limite L1), pas l'instrument exact (« top traders » Binance, 30 j d'historique max — pas de profondeur exploitable). **NON fermé (hors périmètre)** : la forme en U du LSR (pré-enregistrement propre requis, leçon vague 10), le LSR notionnel (buyRatio compte des comptes, limite L9), l'OI en événement de liquidation real-time (websocket, pas d'historique — la liste des NON FERMÉ data locales se réduit à cette seule case). Re-test interdit sans pré-enregistrement explicite d'une hypothèse nouvelle.
## 30/09 — L'ÉTUDE DEEP P2 (4 ans, 12 séries, équité corrigée) : ré-catégorisation des familles + le 1er gate mécanisme-validé

| Verdict | Détail | Catégorie |
|---|---|---|
| **Momentum 1h** (lane continue, majors + extension 12 séries) | majors 0/45, extension 0/180 en lane continue (gates campagne honnêtes, sharpe OOS corrigés) ; les cellules vivantes = le cycle 2023-2024 SEULEMENT (bull_2024H1 5/9) et **0/9 en 2025-2026** (bull 2021-H2, bear, période connue) ; l'extension deep 0/12 — l'edge était un cycle, détecté APRÈS coup | **CONTEXTE** — edge de cycle 2023-2024, mort 2025-2026 (0/12 deep) ; ré-armement PAR détection de régime, jamais une lane permanente |
| **Mean reversion** | WR invariant 42 % sur toutes les périodes/univers, RR inversé (les pertes > les gains) + frais taker = NUL structurel en taker ; seule échappatoire = l'exécution MAKER (le spread travail pour nous) | **CONTEXTE** — NUL en taker ; la piste maker reste ouverte, à pré-enregistrer avant re-test |
| **Breakout deep 1h** | NUL en lane continue 1h sur les 4 ans ; seul signe de vie : la fenêtre alts 2026-04→ (re-détection de vol, 6/12) = un régime, pas une lane | **NUL (deep 1h)** — ré-armable par détection de vol 2026 sur alts |
| **Funding carry (unhedged)** | NUL partout SAUF bear (l'accident d'implémentation du régime court) ; le fix comptable (funding accrue barre à barre) a tué les sharpe biaisés — carry ETH 0,43 → −0,08 | **NUL** — le portage short bear reste la seule exception (exposition constante, T7§2) |
| **Vol harvesting** | l'artefact microstructure (le fix du harnais l'a effacé) | **NUL** |
| **Fade de funding RÉEL élevé (memes)** | sur funding RÉEL mesuré par symbole (l'artefact T7 disparaît) : 4/12 en 2025→2026-03, MOODENG +45 %/a DD 6 %, LTC +40 %/a DD 15 % — mais sharpe OOS 0,46 sous le gate campagne | **CANDIDAT phase-2** — le mécanisme P3 (le fade de la foule long) validé indépendamment du backtest |
| **LA SONDE P3 — le lien crowding-long CONFIRMÉ sur N=61 (58 shorts, 29 fermés)** | 50/61 (90 %) activés à fund7 > 0, **32/61 (52 %) à fund7 > 0,5 bps/8h** (unité vérifiée : COUNT(fund7 > 0,005) sur paper_trades = 32 = la reproduction exacte, fund7 en %/8h) ; outcome des fermés par bucket : fund7 négatif → hit 44 %, ret méd −0,7 % (la foule déjà short = pas de carburant) ; fund7 ≥ 0,5 → hit 50 %, ret méd +2,0 % ; manie > 1 bp → hit 100 % (n=6). machine_cascade_meme méd +0,80 bps, sweep_liquidite_short méd +0,66 bps | **LE MÉCANISME VALIDÉ** — le carburant de la cascade EST le funding positif élevé |
| **LE GATE fund7 > 0,5 bps/8h sur les shorts cascade/sweep — PRÉ-ENREGISTRÉ au forward le 30/09/2026** | câblé dans `paper_forward.py` (`fund7_gate_pass`, seuil GATE_FUND7_MIN_PCT = 0,005 %/8h, famille constant GATE_FUND7_SIGNALS = machine_cascade_meme n=23 + sweep_liquidite_short n=31) ; **vol_spike EXCLU** (fund7 méd −0,04 bps, pire famille — le gate les tuerait à tort) ; majors/deep_fast/cascade_funding_rank_low hors sonde = non gate-d ; les 32 ouverts tranchent à 90 j, le gate n'agit qu'aux activations futures ; skip loggé `[gate-fund7]` + compteur/taux dans le résumé de run ; simulation rétrospective sur la sonde : 24/61 skips (39 %). Tests : tests/test_paper_forward_gate.py (seuil 0,003 → skip, 0,008 → passe, borne ≤, chaîne d'unité fund7_at sur SQLite /tmp) | **PRÉ-ENREGISTRÉ** — le 1er filtre mécanisme-validé OOS de la sonde ; verdict au forward à 90 j (le taux de skip = la métrique du gate) |

Rapports : reports/aster_deep_regimes_p2.md (script : scripts/mechanism_probe.py — fund7_at, klines.db lecture-seule ; gate : scripts/paper_forward.py).

## 30/09 — T13 : le GATE d'exposition vol_spike par régime détecté — le trou n°1 était le vol_spike À 6,8 pts de DD, pas au-delà (aster_volspike_gate.py)

| Verdict | Détail | Catégorie |
|---|---|---|
| **Gate vol_spike par régime détecté** (GA = OFF en bear détecté ; GB = OFF en bear ET en chop, le chop opérationnalisé par la BANDE MORTE de l'hystérésis elle-même \|close/SMA−1\| < 3 % — la règle du détecteur T10/T11, AUCUN nouveau paramètre ; causal det[i−1], la convention du gate momentum T9) | Comparaison APPARIÉE même run (BASE = T11 V2 re-simulé, hérédité exacte $146.42/DD 32.5) : BASE $146.42 (+7.8 %/an, DD 32.5, 36m−) → **GA $184.68 (+12.8 %/an, DD 26.2, 28m−)** → **GB $185.60 (+12.9 %/an, DD 25.7, 23m−, pire −12.9 %/record +43.0 %, 0 liq, garde-fous OK)** ; témoin GB1 (ON = bull confirmé seul) $189.70 (+13.4 %/an, DD 26.2) = borne de sensibilité. vol_spike : −19.2$ → **+19.5$** (7287 → 2465 events, 1612 → 588 trades wallet) ; **VAL −3.5 % → +18.7 %** (DD VAL 15.6, 0 liq). Le vol_spike PAR RÉGIME : PERD en bear détecté (bear_2022 −4.4$ → 0t) et en connu (−24.2$ → +11.3$), PAYE en bull (recovery_2023 +5.1$ et bull_2024H1 +2.7$ conservés — le vol_spike paye bien en bull, le gate ne coupe que les perdants) | **CANDIDAT** — le gate paie sur TOUTES les colonnes (DD −6.8 pts, NET +5.1 pts/an, mois− 36 → 23, VAL renforcée, 0 liq) ; MAIS la cible DD ≤ 25 % n'est PAS atteinte (GB 25.7 %) : **le trou n°1 n'est PAS le vol_spike seul** — le porteur restant du DD = le CARRY SHORT HYSTÉRÉSIS en fenêtre connue (tous les top pertes GB : whipsaws 2024-08-06 −15.1$, 2025-04-07 −14.7$, 2023-08-20 −10.1$ à SZ_CARRY 25 % × 2x, pire mois −12.9 % = 2025-04) ; l'étape suivante = le SIZING du carry par régime (pas un 2e gate, pas un re-calibrage de h) |

Rapports : reports/aster_volspike_gate.md (script : scripts/studies/aster_volspike_gate.py — pattern verbatim T9/T10/T11, klines.db lecture-seule).
origin/main
origin/main

## 01/10 — T16 : LA GRANULARITÉ 15m PROFONDE (178 k barres × 3 majors, 2021-2026) — le verdict intraday

| Verdict | Détail | Catégorie |
|---|---|---|
| Les 6 familles à 15m profond | momentum 875t·17 %·−27 %·DD63·17m− (connu) ; mean_reversion WR 47 %·−40 % ; breakout −21 % ; funding_carry −33 % — 0 lane PASS aux gates honnêtes, sharpe OOS ≤ 0,04 hors artefacts | **NUL intraday** — aucun edge régime-indépendant à 15m dans les 6 familles |
| La comparaison 1h→15m | l'edge momentum 1h (+55/+56/+61 % recov/bull24/chop) S'EFFONDRE à 15m (+7/−42/−14) : trades ×3-4 = ~4,5 pts de frais sur 5 ans + le whipsaw | **CONTEXTE** — l'edge momentum était un edge d'HORIZON (1h), pas du marché |
| Les invariances inter-horizons | mean_reversion : WR invariant 43-59 % à 15m comme 38-52 % à 1h (structurel) mais PnL tué par RR+frais aux deux ; funding_carry bear +39→+23 % (le même accident du short passif) | **CONTEXTE** — confirmé multi-horizons |
| L'orientation intraday | le forward intraday (les signaux 15m du tape) n'a AUCUNE base dans les 6 familles OHLCV — sa base est ailleurs : le carnet réel 1m (le depth engine), l'ordre-flow/CVD, le pont fomo | **DOCTRINE** — la quête intraday bascule du OHLCV vers l'ordre-flow |

Rapports : reports/aster_15m_regimes.md (script : scripts/studies/aster_15m_regimes.py — configs REF T7, le harnais corrigé b825da9, DB ro).
origin/main
origin/main
origin/main
origin/main

## 01/10 — T17 : LE CVD DU TAPE (5,65 M prints BTC/ETH, 45 j) — NUL comme signal, la matière sub-minute reste

| Verdict | Détail | Catégorie |
|---|---|---|
| Le tape REPRODUIT les bougies : corr ΔCVD 1m = 0,9999/1,0000 BTC/ETH, l'écart de volume journalier méd 0,0000 % | les bougies 1m fapi et aster_tape viennent du MÊME flux de trades — le CVD tape ≡ le CVD klines à 6 décimales | **aster_tape = CONTEXTE** (la matière ordre-flow, pas un signal) |
| Les features tape (dcvd 15m/1h/4h, aggressivité, vitesse) : 32 tests déclarés, 1/32 promo brute (= le bruit H0 attendu), **0/32 après la re-vérification mécanique** (AUC TR ≥ 0,55 + le signe TR→VA stable) ; les sharpe ±5-13 à AUC ≈ 0,5 = l'artefact de queues grasses + toujours-long déguisé | la discipline x501 (l'AUC temporel ≥ 0,60) appliquée et respectée — la seule cellule ≥ 0,60 rejetée mécaniquement | **NUL** — les features CVD/agressivité 1h-4h n'ont pas d'information prédictive que les bougies ne donnent pas |
| La valeur conservée du tape : la granularité SUB-MINUTE pour les études d'absorption événementielles (le déséquilibre intra-bougie, l'absorption au bid/ask — le style vague 2 x501) | l'archive 45 j s'étend par tranches (J-90/180/365, les coûts chiffrés) | **MATIÈRE** — phase 2 |

Rapports : reports/aster_cvd_tape.md (script : scripts/archive_studies/aster_cvd_tape.py — 32 tests déclarés, le re-verdict mécanique, DB ro).

## 01/10 — T18 : L'ABSORPTION ÉVÉNEMENTIELLE sub-minute (les événements ±1 %/5 min, BTC/ETH, 45 j) — NUL comme signal, le fait descriptif : les extrêmes sont des PURGES

| Verdict | Détail | Catégorie |
|---|---|---|
| 116 événements (BTC 33, ETH 83) — le flux dans le mouvement : PURGE 71-89 % (le flux agressif continue DANS le sens du mouvement sur les 60 s finales et s'épuise), l'absorption franche 11-29 % minoritaire | les mouvements s'achèvent sur une impulsion qui s'épuise, pas sur une foule qui absorbe — le fait descriptif robuste (à 0,5 % aussi : purge 69-81 %, n=729) | **FAIT DESCRIPTIF** — la lecture microstructure du token home |
| La prédiction (le signature à l'extrême → le retour 30 min) : 13 tests × 2 passes, 0/26 après re-vérification mécanique (les hints train 0,60-0,69 S'INVERSENT en VAL — le contrôle inverse naturel passé) ; à n VAL 14-19, ~4/13 brutes = le taux de faux positifs attendu | les bougies 1m portent déjà toute l'information — le flux intra-minute n'ajoute rien de mesurable | **NUL** — la lignée tape-signal close aux deux niveaux (le régime T17, l'événement T18) |
| aster_tape re-catégorisé : CONTEXTE confirmé — la valeur résiduelle = le diagnostic d'exécution (la latence, les spreads, le slippage), pas la prédiction | l'archive 45 j s'étend par tranches si une étude d'exécution l'exige | **CONTEXTE** — confirmé |

Rapports : reports/aster_absorption_tape.md (script : scripts/archive_studies/aster_absorption_tape.py — 126 lignes, les tables événement × signature × outcome train/val des 2 passes).

## 01/10 — LES DÉCISIONS DU COORDINATEUR (suite T8, la chaîne T1-T13)

| Verdict | Détail | Catégorie |
|---|---|---|
| cascade majors 10x | la machine codifiée = un artefact de la fenêtre 2025-2026 (T8 : liquidée dans 6/7 régimes deep, le wallet mort fin 2023 ; le gate AL inerte sur 3 majors) ; le levier sûr mesuré 4,3x (bear) → 8,3x (bull24) | **CONTEXTE** — le 10x n'est pas transférable hors fenêtre haussière |
| L'asservissement du levier | levier cascade majors effectif = 4x sur le cycle, 10x seulement si le moniteur MAE 6 majors reste < 9,5 % (l'état mae_state.json écrit au nocturne, lu par paper_forward et le tracker ; l'état absent/périmé = 4x, le défaut sûr) | **PRÉ-ENREGISTRÉ** (01/10) — le forward juge |
| La cible 60-70 %/mois | observée UNIQUEMENT dans la fenêtre haussière majors 2025-2026 — re-qualifiée : la cible sur le cycle complet = la robustesse (0-liq à 4x, un ROI positif en bear), le forward tranche la fenêtre | **RE-QUALIFIÉE** — docs/21 mis à jour |

L'étude : scripts/studies/aster_machine_deep_regimes.py + reports/aster_machine_deep_regimes.md (le backfill 9,1 M bougies 2021-2026, docs/24).
origin/main
origin/main
origin/main
