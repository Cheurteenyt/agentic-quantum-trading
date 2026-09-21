# Aster research runners - Mode d'emploi

Derniere mise a jour: 2026-06-02.

Ce dossier contient les orchestrateurs de recherche Aster. Ils ne sont pas des
strategies de trading en eux-memes: ils selectionnent des symboles, preservent
les anciens champions, comparent des univers et deleguent les backtests au
runner principal.

## Regle de base

- Read-only marche/API.
- Aucun ordre reel.
- Aucun wallet.
- Aucun signal client.
- Ecriture autorisee seulement pour des artefacts locaux JSON/CSV/HTML.
- Ne pas utiliser un rapport de recherche comme preuve de rentabilite.

## Fichiers et roles

| Fichier | Role | Ecrit quoi |
| --- | --- | --- |
| `aster_v2_runner.py` | Orchestre exploitation + exploration + univers Aster. | Plan tagge + lance discovery si demande. |
| `priority_watchlist_backtest_runner.py` | Connecte watchlist prioritaire vers discovery. | Plan watchlist + sorties discovery taggees. |
| `dual_track_research_report.py` | Separe anciens champions et nouveaux candidats. | Rapport dual-track local. |
| `exploitation_champions_validator.py` | Revalide les anciens champions avec garde-fous. | JSON/CSV de validation. |
| `watchlist_priority_builder.py` | Construit une watchlist priorisee. | Watchlist locale. |
| `runner_health_dashboard.py` | Lit les heartbeats/runs. | Dashboard local. |
| `exchangeinfo_run_status.py` | Suit les runs enrichis exchangeInfo. | Statut local. |
| `aster_v2_ws_preflight_refresh.py` | Rafraichit qualite WS pour symboles V2. | Snapshot WS merge. |
| `aster_v2_strict_vs_large_comparator.py` | Compare large vs strict. | Comparaison locale. |
| `aster_rl_lane_policy.py` | Politique RL offline/contextual-bandit pour classer les lanes deja backtestees. | JSON/CSV/HTML de recommandations locales. |

## Contrat d'identite

Toute lane qui sort de ces runners doit garder:

`output_tag + symbol + interval + side + trigger_reference + execution_model + leverage + score_window_size + strategy_profile_key`

Si un orchestrateur perd un de ces champs, le resultat est exploratoire
seulement. Ne pas le donner a la promotion, au forward ou au truth report.

## Contrat out-of-sample

Les runners de recherche doivent favoriser les artefacts V2 qui exposent:

- `out_of_sample_status`;
- `train_*`;
- `validation_*`;
- `train_validation_split`.

Une lane avec bon train mais validation recente negative doit etre marquee
`watch` ou `rework`, jamais `promote`.

## Plan files et tags

Les plans doivent etre tagges par `output_tag`. Ne pas ecraser un plan global
avec un smoke test puis le lire comme source de verite. Si un script conserve un
fichier `*_latest.json` de compatibilite, le lire comme raccourci de debug, pas
comme decision finale.

## Recommandation de workflow

1. Construire ou rafraichir l'univers/watchlist.
2. Generer un plan tagge.
3. Lancer discovery avec `output_tag` explicite.
4. Regenerer `aster_candidate_validation_queue`.
5. Passer `aster_queue_reality_pack_validator`.
6. Lancer la politique offline RL pour classer les lanes avec les garde-fous.
7. Seulement ensuite discuter d'une lane forward.

## Politique offline RL

Commande:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.research.aster_rl_lane_policy --top-n 120
```

Commande gate avant decision:

```powershell
Set-Location D:\trading-agent\backend
python -m services.onchain.aster.research.aster_rl_lane_policy --top-n 120 --quality-gate
```

Interpretation:

- exit code `0`: au moins une lane est `clean` et promotion-ready;
- exit code non-zero: ne pas promouvoir, lire `top_watch_lanes`, `top_blocked_lanes` et `required_next_actions`;
- ce gate doit etre lance avant toute discussion de forward/paper-live/reel.

Sorties:

- `backend/services/onchain/aster/aster_rl_lane_policy_latest.json`;
- `backend/services/onchain/aster/aster_rl_lane_policy_latest.csv`;
- `docs/core-equity-aster-rl-lane-policy.html`.

Lecture:

- ce n'est pas encore un agent PPO/SAC qui trade;
- ce n'est pas un LLM ni un reseau neuronal entraine avec `torch`;
- c'est une politique offline de selection de lanes, type contextual-bandit/KNN, sans dependance ML externe;
- elle lit uniquement les artefacts locaux;
- elle penalise fortement les lanes rejetees par mark/index, microstructure, OOS ou reality pack;
- elle affiche la fraicheur des validateurs et degrade les validations stale;
- elle dedupe les recommandations par `symbol + interval + side` pour eviter les tops repetitifs.
- elle calcule maintenant un garde-fou anti-erreur par lane:
  - `mistake_guardrail_verdict`: `clean`, `watch_only`, `review_required` ou `promotion_blocked`;
  - `mistake_risk_score`: score de risque methodologique de `0` a `100`;
  - `mistake_blockers`: raisons bloquantes;
  - `required_next_actions`: actions concretes avant promotion.
- elle separe maintenant:
  - `top_recommendations`: exploitation des meilleures lanes;
  - `balanced_portfolio_recommendations`: couverture multi-actifs pour ne pas abandonner les autres univers;
  - `exploration_queue`: lanes a valider/retester sans les promouvoir.

Regle anti-erreur:

- une lane ne peut etre `promote_forward_candidate` que si `mistake_guardrail_verdict=clean`;
- les CSV `_progress_` ne peuvent plus etre promus;
- une lane sans identite complete, sans OOS, avec validateurs stale, mark/index incomplet, microstructure non verifiee, levier invalide ou PnL latent melange passe en watch/review/rework;
- le RL sert donc aussi de critique qualite: il peut reduire les faux positifs meme si cela rend la sortie moins excitante.

Regle lane vs famille:

- une `lane` est une experience atomique: `symbol + interval + side + trigger_reference + execution_model + leverage + risk_profile`;
- on utilise les lanes pour eviter de melanger des resultats incompatibles;
- une lane seule peut etre un accident statistique ou un overfit;
- la politique RL agregue donc aussi les `strategy_family_recommendations`;
- une famille robuste doit se repeter sur plusieurs symboles/timeframes avec un risque methodologique faible;
- objectif final: promouvoir des familles reproductibles, pas seulement la meilleure lane du jour.
- le ranking integre maintenant `family_support_score` et `lane_family_verdict`;
- une famille tres presente mais majoritairement bloquee devient `family_blocked`, meme si son meilleur symbole a un bon ROI;
- une promotion propre doit donc avoir deux niveaux: lane propre + famille soutenue.

Dernier smoke utile 2026-06-04 apres garde-fous anti-erreur:

- `6709` lanes lues;
- top action: `forward_watch`;
- top symbole: `HYPEUSDT`;
- `0` lane `clean` dans les artefacts actuels;
- top famille: `blocked_family`, ce qui confirme que les artefacts actuels ne suffisent pas encore a valider une famille de strategie;
- dernier smoke apres support famille: `6768` lanes lues, `HYPEUSDT` reste top lane mais `lane_family_verdict=family_blocked`;
- top HYPE reste interessant, mais bloque en watch par `out_of_sample_missing` et `exchange_filter_warning`;
- verdicts observes: beaucoup de `promotion_blocked` / `review_required`, ce qui est attendu tant que les anciens artefacts sont incomplets;
- `LABUSDT` reste visible en recherche, mais n'est pas promu par la politique car ses garde-fous stricts ne sont pas au meme niveau.
- la sortie portfolio garde aussi des majors, altcoins, memecoins, equities synthetiques et commodities quand les donnees locales le permettent.

Regle de fraicheur:

- si `mark_index`, `microstructure` ou `reality_pack` sont plus anciens que le CSV discovery de la lane, la sortie porte `validation_freshness_verdict=stale_validation_overlays`;
- une lane stale ne doit pas etre consideree comme promotion-ready sans relancer les validateurs;
- le HTML affiche le verdict global de fraicheur pour eviter les promotions basees sur des snapshots anciens.

## Anti-patterns

- Creer une nouvelle strategie sans `strategy_profile_key`.
- Melanger anciens champions et nouveaux candidats dans un seul verdict.
- Lire un `heartbeat` comme un resultat.
- Promouvoir une lane parce qu'elle est le meilleur batch local.
- Comparer `last_price/taker_market` avec `mark_price/bbo_limit` sans afficher
  cette difference.
