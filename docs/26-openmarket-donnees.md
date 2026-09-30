# 26 · OPENMARKET — LES DONNÉES (l'entrepôt om_v27)

> Créé le 30/09/2026. Ce que le domaine x501 a pour matière première, ce qui
> a été audité, ce qui manque. Les chiffres de recherche : `docs/25-openmarket-x501.md`.

## L'ENTREPÔT (om_v27.db — local, git-ignoré)

Un seul entrepôt SQLite pour tout le domaine : **12 symboles perp USDT,
~560 000 points**, structuré en 6 familles de séries. La convention est la
même que pour le domaine Aster (`docs/06-data.md`) : la base ne rentre PAS
dans git (volume + binaire), seuls le schéma, l'audit et les manifestes
sont versionnés — tout backtest cité dans les docs doit rester reproductible
depuis les sources publiques listées ci-dessous.

| Série | Granularité | Profondeur | Points |
|---|---|---|---|
| Klines OHLCV | 1 h | 733 jours | 211 200 |
| Open Interest | 1 h | 708 jours | 204 000 |
| Open Interest | 1 j | depuis 2020 | — |
| Funding (Binance) | 8 h | 3,4–5,5 ans | 65 799 |
| Funding (Bybit) | 8 h | 66 jours | — |
| Long/Short Ratio | 4 h | 8 jours | — |

Mise à jour du manifest CSV (re-collecte v16/v17 du 01/10) : le répertoire
`data_x501/` couvre désormais **80 symboles**, klines 1h sur **1 092 jours**
(01/10/2023 → 27/10/2026, 26 208 barres par symbole, **0 gap** sur le panel
complet) et funding 8h assorti — c'est la fenêtre qu'a consommée le banc de
test des flux dormants (`docs/30`).

## L'AUDIT VERT (ce qui a été purgé et verrouillé)

L'audit v27 a rendu l'entrepôt **vert** en trois corrections définitives.
Premier point, les doublons : **226 800 lignes dupliquées purgées**
(fusions de backfills partiels qui réinséraient des fenêtres déjà présentes)
et verrouillage structurel par un **index UNIQUE `(symbol, ts)`** — une
réinsertion en double est désormais impossible au niveau du schéma, pas
seulement détectée après coup. Deuxième point, la sémantique : l'OI 1 j
Bybit avait son timestamp interprété comme la **clôture** du jour alors
qu'il marque l'**ouverture** — corrigé, faute de quoi tout alignement
funding×OI×prix à la journée était décalé d'une barre. Troisième point,
la couverture : chaque série a sa fenêtre réelle documentée (le tableau
ci-dessus), y compris les angles morts assumés.

## LE MANIFEST CSV (la reproductibilité)

Les sources brutes sont ré-exportées en CSV plats (klines 1 h + funding par
symbole) dans le répertoire de travail local `data_x501/` (git-ignoré, même
politique que les entrepôts du domaine Aster). Le principe : chaque chiffre
des docs 25/26 doit pouvoir être recalculé depuis (a) l'entrepôt local ou
(b) une re-téléchargement depuis les sources publiques (openmarket.xyz,
Binance, Bybit) avec les fenêtres exactes listées ici. Les 2 CSV de trades
de backtest (BTC/ETH) embarqués dans `scripts/studies/x501_openmarket/`
servent d'exemples de format de sortie du harnais.

## LES BANDES DE COÛTS (la convention anti-optimisme)

Toute simulation du domaine utilise des bandes de coûts explicites et
symétriques : **taker 6,1 bps/côté** (frais + slippage mesurés) et
**maker 2 bps/côté** (limite δ=2, fills 97,9 %). Aucun chiffre de
performance n'est cité sans sa bande — la règle empirique v18 (−2 bps/côté
≈ +25 % de médiane) rend toute omission de bande immédiatement trompeuse.
Le stress V5 (215,7 $ de médiane) est la bande pessimiste de référence :
gaps, slippage défavorable et fills dégradés en même temps.

## CE QUI MANQUE (les angles morts assumés)

Trois séries sont trop courtes pour conclure et le sont documentées comme
telles : le **LSR 4 h (8 jours)** ne permet aucun test de gate — il est
collecté pour plus tard, pas exploité ; le **funding Bybit (66 j)** ne sert
qu'au contrôle de cohérence cross-exchange du funding Binance, pas à un
signal autonome ; et l'**OI 1 j pré-2024** sert au contexte de régime
(densités, percentiles de vie) mais pas à des backtests intraday. Toute
proposition de signal qui repose sur ces séries courtes est invalide par
construction jusqu'à extension de la collecte — c'est exactement le même
statut que les données fomo pré-crack dans `docs/06-data.md` : on collecte,
on ne conclut pas.

## CE QUI EST BANC-TESTÉ (requalification du 01/10, `docs/30`)

Deux familles de séries qui dormaient ont passé le banc de test local et en
sortent **fermées comme filtres continus** : le **flux taker natif des
klines** (`taker_buy_quote_volume` — 6/6 cellules KILL) et le **funding
Binance multi-années** (6/6 KILL) — grille pré-déclarée, plomberie prouvée
vivante par le test d'altération de la QA, re-exécution bit à bit. Le statut
de ces séries change : elles ne sont plus « dormantes » mais **mesurées et
fermées** — tout re-test exige un pré-enregistrement explicite d'une
hypothèse nouvelle au registre (`docs/20`), pas un re-run de curiosité.
La collecte continue : les fenêtres se rallongent, l'entrepôt reste la
matière première des prochains bancs (OI 1h en tête).

**Vague 6 (`docs/31`)** : la même série `taker_buy_quote_volume` a servi de
matière première au banc d'ÉVÉNEMENTS de l'absorption (mur volume / attaque
/ tenue / reprise en proxy klines) — prime de structure réfutée 0/4, la
série reste **mesurée et fermée** aux deux niveaux (filtre continu ET
structure événementielle klines). Le champ orderbook réel (`maxBidAmount`)
n'est PAS couvert par ces bancs : son juge reste le run ABS du protocole
A/B (`docs/28`), désormais en queue de file.
