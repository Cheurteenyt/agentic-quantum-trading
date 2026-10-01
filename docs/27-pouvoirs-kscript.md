# 27 · POUVOIRS kScript — LE REGISTRE D'EXPLOITATION

> **domain: OPENMARKET** · index : [`openmarket/README.md`](openmarket/README.md)
>
> Créé le 01/10/2026. Réponse chiffrée au diagnostic : outils kScript sous-exploités.
> Méthode : `scripts/studies/x501_openmarket/x501_exploit_audit.py`

## LE VERDICT GLOBAL (canonique)

**40/53 capacités exploitées = 75,5 %** après vagues 1–3 (régime institutionnel +
absorption + hygiène broker).  
Avant vagues : 28/53 (52,8 %) → 36/53 (67,9 %) après vagues 1–2 → **40/53** après vague 3.

| Famille | État |
|---|---|
| alertes | complet |
| données (sources/TF) | bon |
| broker (exécution) | 15/16 (1 refus par design : `profit=/loss=` en ticks) |
| analyse (TA/CVD/sessions) | **CLOSE** après bancs locaux (docs 30–36) |
| orderbook | mur maxBid/maxAsk activé vague 2 |
| sources premium | 7/8 (reste ethena_positions sans use case) |
| langage / visu | dette de style, pas d'edge |

## Vagues d'activation

| Vague | Contenu | Statut |
|---|---|---|
| 1 | Filtre régime institutionnel (ETF/CME/DVOL/skew/LSR) + observe | ACTIVÉE — scripts RI |
| 2 | Absorption native maxBid/maxAsk + sumBids/sumAsks | ACTIVÉE |
| 3 | trailPoints / ocaName / cancelAll / stats natives | ACTIVÉE (défaut trail off = MC v20 bit-à-bit) |

Discipline : no-repaint `htf(...,"1D")[1]` sur flux daily ; fail-open si < 3 composantes RI.

## Bancs locaux (falsification — ne pas retester à l'identique)

| Doc | Famille | Résultat synthétique |
|---|---|---|
| 30 | flux / funding | KILL massif |
| 31 | absorption événements | ABS_DEPRIORISE |
| 32 | vwap / volume profile | famille analyse CLOSE |
| 33–35 | OI continuation / régime / U | falsifications + 2 candidats marginaux purge |
| 36 | LSR contrarian | 10ᵉ falsification |

Détail : chaque doc 30–36. Protocole A/B : `docs/28`. Fill maker : `docs/29`.

## Cases restantes (décisions datées, pas de trou d'ignorance)

| pouvoir | état |
|---|---|
| `strategy.exit profit=/loss=` | refusé par design |
| `ethena_positions` | sans use case |
| `ltf()` / `minBidAmount` | sans data locale falsifiable |
| collections / loops / libraries | dette de style |

## Frontière

Ce registre est **OPENMARKET only**. Ne pas brancher ces kScripts dans `the_machine`.
Code : `scripts/studies/x501_openmarket/` uniquement.
