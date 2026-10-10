> ⚖️ **SÉPARATION DES ÈRES (06/10)** : ce document conserve l'historique des
> indicateurs et de la Machine legacy. **La vérité opérationnelle courante
> des expériences Research OS est `research/registry.yaml` +
> `research/runs/`** (protocol-v2, moteur v14 à causalité verrouillée).
> Les chiffres legacy ci-dessous se lisent comme des leçons, pas comme des
> edges exploitables — plusieurs moteurs successifs portaient des bugs
> d'unité et un look-ahead découverts depuis.

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
> → garde wallet DD → QUBO joint poids×levier (~~le record +5 082 %~~ —
> ⛔ MORT, cf. F-033 : 20 liqs / DD 99,2 % / final $1) →
> H2bis/H3bis capitulation+sweep → TAIL survivor au sizing réel → hold
> étendu + carte hold survivor.

## VALIDÉS (la frontière)

| Indicateur / stratégie | Script | Chiffres (100 $, 1 an, maker) | Verdict |
|---|---|---|---|
| **CANDIDAT QUALITÉ : cascade ∩ funding-rank-BAS** (le symbole au funding le plus bas des 6 majeures à l'instant du signal) | testé inline 25/09, à câbler au paper forward | **WR 81,0 % (n=21), DD 5,4 %, 0 liq**, +106 %/an — la spec du user (80 % WR / peu de DD / 0 liq) TOUCHÉE ; mécanisme : les shorts déjà entassés + le prix tombe quand même = offre réelle, pas de la foule | CANDIDAT — N=21, tercile post-hoc, le forward 2×/jour juge (~2 trades/mois) |
| **LA MACHINE — cascade gated 10x, 0 liq par construction, DEUX knobs (marge + sizing vol-inverse)** | `anti_liq.py` + `portfolio_sim.py` + `stacked_portfolio.py` | ~~SIZING VOL-INVERSE (base 24 %) : +1 498 %/an @ DD 27,8 %, 0 liq~~ — +19 % vs le fixed à DD égale. L'échelle : base 30 % → +2 655 %/an @ DD 34,7 %, record mois +100,2 % · base 60 % équivalents — WR 57,3 %, 3 mois négatifs *(état d'époque, 2 flux — l'état courant 4 flux et les 3 configs forward : docs/21-goal-performances.md, 27/09)* | **⛔ REFUTÉ — HISTORIQUE SEULEMENT (F-034, PR #95)** : la FAMILLE CASCADE est morte sur données fixées — cascade_10x majors **−0,058 %/event, 15 liqs**, cascade_meme −0,428 %/event. Le chiffre +1 498 %/an ci-contre est BARRÉ : re-mesuré, il ne tient plus (fetch_deep_klines corrompait les volumes des gates — cf. F-033). Ne PAS citer comme edge courante ; conservé pour la méthode (size ∝ ATR restait un fait descriptif de l'époque). |
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
6. **Le modèle de liquidation est une approximation au 1er palier (issue #212).**
   `liq_move_for(sym, lev) = 100/lev − maintMarginPercent(sym)` ; le pourcentage vient
   d'`exchangeInfo` et décrit le **premier bracket**. Aster liquide par **paliers de notionnel**
   (`leverageBrackets` avec `cum`) : au-delà, la marge requise monte, donc la liquidation réelle
   arrive **plus tôt** que la formule — le biais est **optimiste à fort notionnel**, jamais
   prudent. La donnée manque (endpoint **signé**, `-1102` sans clé API wallet). Conséquence :
   ne pas appeler ce chiffre « la valeur réelle », et **ne pas en tirer une conclusion de risque
   sur des notionnels élevés**. À faible notionnel les deux coïncident.


---

> **Les vagues datées** (l'historique complet des études, 27/09 → aujourd'hui, ~900 lignes) : `docs/21-vagues-registre.md`.
> Ce fichier garde l'état VIVANT — frontière, candidats, verdicts, collecteurs, leçons (B6, audit Sonnet 5.5 : la lisibilité par un agent).

