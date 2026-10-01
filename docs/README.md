# LA CARTE DE LECTURE DES DOCS

*Le projet = 2 livres (régime + anti-régime), une machine (the_machine.py),
des collecteurs 24/7, et un registre qui dit tout. La lecture dans l'ordre :*

## LE VIVANT (19 docs, à jour)

| Doc | Ce que c'est | Quand le lire |
|---|---|---|
| **00-CARTE** | la carte du projet entier | l'entrée, à chaque reprise |
| **25-openmarket-x501** | la mission x501 : chiffres officiels, falsifications, exécution maker, roadmap | le domaine OpenMarket (pivot 30/09) |
| **26-openmarket-donnees** | l'entrepôt om_v27 : l'audit vert, le manifest, les bandes de coûts | avant toute manipulation de data openmarket |
| **27-pouvoirs-kscript** | le registre d'exploitation : 40/53 capacités (75,5 %), vagues 1-2-3 ACTIVÉES (régime institutionnel + absorption + hygiène broker) | avant d'écrire tout nouveau kScript |
| **28-protocole-ab-x501** | le protocole A/B PRÉ-ENREGISTRÉ : 8 runs, critères figés 01/10/2026, moteur déterministe | avant et après tout run A/B des vagues 1-2 et MK6 |
| **29-fill-maker-mesure** | la chaîne de preuve maker : surface de fill δ×TTL, sélection adverse sur le pool P1, candidat v21, la boucle des compteurs `_MK` | avant de croire au fill 97,9 % ou de toucher au TTL |
| **30-flux-funding-banc-local** | le banc de test des flux dormants : flux taker natif + funding au banc, 12/12 cellules KILL, plomberie prouvée vivante | avant de proposer un filtre de flux ou de funding |
| **31-absorption-banc-evenements** | le banc d'événements de l'absorption (proxy klines) : prime de structure réfutée 0/4, la confirmation est TARDIVE, ABS_DEPRIORISE — la file de runs priorisée | avant de lancer les runs ABS ou de croire au pattern sans ordrebook |
| **32-references-banc-local** | le banc des références de liquidité : vwap de session + volume profile de la veille aux DEUX hypothèses, 55 KILL / 1 INCONCLU / 0 CANDIDAT — la famille analyse est close (7ᵉ falsification) | avant de brancher un vwap, un profil de volume, ou de croire au « benchmark institutionnel » |
| **33-oi-banc-local** | le banc de l'open interest 1h : le capital affiché testé en TÉMOIN DE CONTINUATION (capital brut + mouvement financé), 10/10 KILL sur 216 000 barres Bybit — la 8ᵉ falsification | avant de croire que « l'OI monte donc ça monte » ou de brancher l'OI dans un kScript |
| **34-oi-regime-banc-local** | le banc de l'OI en contexte de régime : le NIVEAU du capital (z-score roulant) ne conditionne ni la magnitude (H_R1 de la théorie du levier refusée) ni la direction — la 9ᵉ falsification ; le conditionnel pool P1 franchit le gate de contexte (P = 0,8192) sans promotion possible | avant de croire au « régime OI » ou de vouloir conditionner un kScript à l'OI |
| **35-openmarket-oi-ushape** | le banc de la forme en U de H_R1 : le U joint NON ÉTABLI (4/4 INCONCLU sous le gate, la composition pré-déclarée refuse), le miroir directionnel KILL 4/4 — MAIS le côté bas de la purge CANDIDAT à L2160 (AUC 0,4415/0,4454, Δ\|fwd\| +52 à +83 bps) — les 2 premiers candidats marginaux du domaine — et le pool strates \|z\| franchit le gate de contexte une 2ᵉ fois (P = 0,7381) | avant de croire au « U des extrêmes » ou de brancher le régime de purge dans un kScript |
| **22-nos-indicateurs** | LES 10 CRÉATIONS : chaque indicateur, sa règle, sa preuve | pour savoir ce qu'on possède |
| **20-registre-indicateurs** | la source de vérité des verdicts (25+ datés + les 25 réfutés) | avant de croire quoi que ce soit |
| **21-goal-performances** | le plan P1-P5 + les dates de tir + le volet institutionnel | pour savoir où on va |
| **06-data** | les 6 bases vivantes + qui écrit quoi | avant toute manipulation de data |
| **13-orchestration** | les campagnes nocturnes + les timers | pour comprendre ce qui tourne |
| **10-strategies** | les stratégies historiques (l'évolution) | le contexte des créations |
| **03-methodology** | la discipline (harnais v5, train/val, pré-enregistrement) | avant tout nouveau test |
| **04-runbook** | le runbook opérationnel | le dépannage quotidien |

## L'ARCHIVE ANNOTÉE (docs/archive/ — 13 docs, jamais oubliés)

Chaque doc archivé porte son lien « LIRE AUSSI » vers la vérité à jour — l'archive est une bibliothèque annotée, pas un cimetière :

| Doc archivé | Ce qu'il contient | La vérité à jour |
|---|---|---|
| 01-onboarding | l'onboarding de l'ère pré-refonte | docs/README + 00-CARTE |
| 02-architecture | l'architecture d'avant le deux-livres | 00-CARTE + 06-data |
| 05-data-sources | les sources de data d'avant le crack mobula | 06-data |
| 07-backtest-engine | le moteur de backtest v1-v4 | 03-methodology + le harnais v5 |
| 08-contributing | les règles de contribution d'antan | AGENTS.md + 03-methodology |
| 09-pipeline | la pipeline d'avant les timers | 13-orchestration |
| 11-campaign-real | les campagnes réelles de l'époque | 13-orchestration + reports/ |
| 12-nondirectional | les stratégies non-directionnelles | 10-strategies + 20-registre |
| 14-registre-x | le registre X de l'époque | 20-registre + x_posts.db |
| 15-plan-revenus | le plan de revenus d'août | 21-goal-performances |
| 16-inventaire-actifs | l'inventaire des actifs d'août | 06-data + 22-nos-indicateurs |
| 18-roadmap-memecoin-x | la roadmap memecoin-x | 21-goal + 22-nos-indicateurs |
| 19-liquidations-aster | la première cartographie des liquidations | 20-registre + le burst test |

**17-mmt-m5 reste EN VIVANT** (le terminal externe MMT/M5 est une infra active).
