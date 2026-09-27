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
| funding_divergence +12h, confluence +24h (composants du stack) | `stacked_portfolio.py` | Réhabilitées post-fix (quasi-plates -1,8/-4,5 %, DD 5-6 %) — leur valeur = la décorrélation ; paper forward 2×/jour |
| LIQ-STORM (tempêtes de liquidations) | `liq_storm.py` | Descriptif ; ratio long/short 2,0× ; backtest à 3-4 semaines |
| whale_flow × prix (flux skill-weighted) | `whale_flow.py` | J+14 ≈ 8/10 |

## NULS (fermés, avec la preuve)

| Piste | Chiffre qui la ferme | Date |
|---|---|---|
| Sorties anticipées TOUTES (1re verte, trailing 1/1,5/2,5 %) | monotone : trail 1 % -46 % → 24h fixe +197 % — chaque sortie sur rebond abandonne le drift | 25/09 |
| EXTENSIONS des gagnants (48h/72h si gagne) | $297 → $250-$235 : le bounce de jours 2-3 à 20x mange le drift supplémentaire — 24h pile est l'optimum total | 25/09 |
| Squeeze haussier (miroir de la cascade) | wallet $6,34, WR 44,9 %, détruit le stack | 25/09 |
| Exit première verte (épuisement) | hold moyen 1,8 h, -5 % vs +197 % — les bounces sont micro, le drift domine à 24h | 25/09 |
| Cascade × funding percentile | NUL même série profonde ; l'inverse gagne = anti-signal | 25/09 |
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

## 27/09 — session parallèle (3 agents Aster) : vol_spike PASS, flux meme affaibli, autopsie des mois

| Verdict | Détail | Catégorie |
|---|---|---|
| **vol_spike_6h** (fade du range ≥ 4× médiane 14j, gate ATR, 1x, hold 6h) | N 820/an (68/mois), WR 53,7 %, espérance +0,012 $/trade TAKER, 0 liq, **corr cascade -0,22 = anti-corrélé**, remplit les mois creux (juil +0,88, août +4,20, sept +1,45 $) | **CANDIDAT** — câbler au paper forward nocturne (sizing vol-inverse), croiser fill-rate maker × depth à J+14 |
| funding_sat (queue du funding 8h/24h) | positif NEET maker seulement (+0,005/+0,010 $), corr +0,07-0,15 | CONTEXTE — thin, maker-only |
| dd_cross 24h/72h (traversées de carte à 1x) | espérance négative, le 72h attrape le squeeze LAB, < 10 trades/mois | **NUL** — confirme la monétisation non-triviale de la transition de carte |
| vol_spike_12h | espérance négative taker | **NUL** — seul le 6h tient |
| **Carte hold × levier memecoins** (cascade meme, réplication exacte the_machine 2 022 evts) | MAE explose 96→224→260→538 % (6h→72h) — sub-1x requis dès 24h pour 0-liq ; le 1x actuel esquive les 3 tueurs/an PAR CHANCE ; **VAL négative 3 cellules/4 (24h : train +8,8 % → val -5,8 %), l'edge s'est évaporé depuis juin 2026** | **DÉGRADÉ** — ne PAS lever ; réduction/gate régime à étudier ; re-carto après 1 mois de fraîcheur |
| **Autopsie des mois négatifs** (n=1 strict : 2026-01 -5,5 % ; faibles : 07/09 +7,5 %) | séparateurs : fund7 (d +0,98, le mois négatif = 3e funding le plus haut de l'année), fresh-peak au 1er du mois (d -0,72) ; **corr7 NE sépare PAS** (hypothèse naïve rejetée) | PROFIL indicatif n=1 — hypothèse fund7 ≥ p75 (~0,0039 %/8h) pour la sonde P3 en octobre, PAS un gate |

Rapports : reports/p5-frequency-streams-2026-09-27.md, reports/carte-hold-levier-memes-2026-09-27.md, reports/autopsie-mois-negatifs-2026-09-27.md.

## 27/09 — lifecycle v2 sur le corpus profond (backfill mobula : 386k bougies, 34 tokens, 1h→avr 2024)

| Verdict | Détail | Catégorie |
|---|---|---|
| **Sortie mécanique temps fixe** (hold 24-72h à la naissance, launches n=20, entree=close 1re bougie non plate) | hold24h médian 1,60x WR 65 % / hold72h médian 1,47x WR 65 % moyenne 47x ≥2x 45 % / pire trade 0,007x (rug AAPL) — les 3 fixes dominent trailing -35 % (méd 0,99x WR 45 %) et -50 % du pic (méd 0,98x WR 40 %) ; le trailing ne sert qu'à plafonner le pire (0,043x vs 0,007x) | **CANDIDAT** — l'hypothèse v1 « tenir ~2 jours puis sortir mécaniquement » CONFIRMÉE ; 72h maximise la queue droite, 24h le médian/WR ; passer run_stack avant tout câblage |
| Trailing/drawdown comme sortie principale sur launches | médian ~1,0x, WR 37-45 % : les dips de 35-50 % dès la 1re heure font sortir avant le pump | **CONTEXTE** — utilisation possible en garde anti-rug (plafonne le pire cas), pas comme sortie d'EV |
| Lifecycle v2 corpus profond (launches n=13, ≥14 j) | pic médian 15,1x (ensemble 10,8x vs 3,18x v1), ≥2x 84 %, pic ≤72h 30 %, give-back médian 83 %, survie 13/13 actifs ; cohorte post-juin pic méd 14,0x / pré-juin 3,4x | **CONTEXTE** — métriques de référence ; multiples = bornes HAUTES (survivorship : morts-nés absents, entrée à la 1re minute = délai collector non modélisé) |
| Données mobula | AMBA 1m/15m : cassure d'unité (bougies ~1566 $ vs 0,0012 $) → 65 bougies jetées ; WETH 1h : 6 mèches non soutenues (high 13210 vs ~3100) réparées ; 7STOCK : 2 bougies seulement, print à 4,65e-12 $ | **NUL** (telles quelles) — nettoyer avant tout backtest 1m/15m mobula : filtre voisin-based dans scripts/fomo_lifecycle_v2.py |

Rapport : reports/fomo-lifecycle-v2-2026-09-27.md (script : scripts/fomo_lifecycle_v2.py). v1 (corpus court) re-catégorisé : ses métriques 15m sous-estimaient les pumps <15 min (AMBA 1,14x → 92,9x) et bornaient le délai au pic (51,5h → 871,5h).
