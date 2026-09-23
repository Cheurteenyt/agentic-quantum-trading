# 18 — Roadmap Memecoin × X.com × Aster (la vraie vague)

Date : 2026-09-23 (nuit 3). Remplace l'approche « BTC long/short de petits
comptes » du registre et l'attente passive de 4 semaines. Deux constats de
l'utilisateur qui fondent cette roadmap : (1) le legacy a backtesté des lanes
long-only sur small-caps — jamais la dynamique memecoin × social ; (2) les
memecoins sont démocratisés sur X.com (cf. fomo.family) et **Aster liste leurs
perps** : MEME, BOME, WIF, PNUT, MOODENG, NEIRO, TURBO, PENGU, NOT, DOGS,
TRUMP, FARTCOIN, CATE (~13 vérifiées TRADING sur 567 perps ; PEPE n'y est
PAS — tout cashtag dont le perp n'existe pas sur Aster est exclu d'office).

## La thèse

Le cycle memecoin vit sur X.com (les callers créent la vague), se joue sur
les launches (four.meme, fomo.family), et **se trade sur Aster en perps** avec
des extrêmes de funding que personne ne traque systématiquement (MEME +88 %/an
flaggé, basis +4521 % mesuré). Personne ne construit le pont
**X.com → Aster perps** avec des données propriétaires. C'est le projet.

## PILIER A — Registre X v2 : memecoin-first

- **A1. Recherches memecoins** — fait ce soir : le passage de 14h00 tourne sur
  `$MEME $BOME $PEPE $WIF $MOODENG $PNUT` ; la nuit garde majors + $ASTER.
  Rotation à élargir (TURBO, PENGU, NOT, DOGS, TRUMP, FARTCOIN, CATE) avec un
  sélecteur rotatif quand le parsing suit.
- **A2. Parser v3 « memecoin »** — tickers nus sans `$` (BOME, pepe…),
  patterns `CA: 0x…` (launches BSC), vocabulaire (ape, 100x, entry, MC).
  Garde-fous anti-faux-positifs obligatoires (leçon EGLD) + tests.
- **A3. fomo.family** — sonder la surface publique du leaderboard top traders
  (2,5 M de traders revendiqués) : extraire QUI appelle quoi, intégrer ces
  comptes à la watchlist X. **On n'y trade JAMAIS** (contrainte dure) — c'est
  un annuaire de track records, pas un lieu d'exécution.
- **A4. Verdicts memecoin complets** — klines perp Aster par cashtag
  rencontré (fetch on-demand), **frais réels par symbole** du legacy
  (`taker_fee_bps_for_symbol`), et **gate de collectionnabilité** : un call
  sur un memecoin à spread 257 bps (MEME, mesuré) n'est PAS tradable — le
  registre le flag `incollectionnable` au lieu de scorer du vent.
- **A5. Klines on-demand** — fetch automatique des klines des symboles
  apparaissant dans les calls (14 memecoins fetchés ce soir : 3000 bougies
  chacun).

## PILIER B — Le legacy comme arme (pas comme musée)

Ce que le legacy a VRAIMENT fait : lanes long-only 15m-5h sur small-caps et
stock-perps, microstructure + mark/index + frais réels, forward strict. Son
verdict : champion paper (LAB ROI 48 %/PF 3) **non rentable en forward
strict**. Ce qu'il n'a JAMAIS testé : la vague sociale memecoin. Ce qu'on
réutilise TEL QUEL :

- **B1. Les validateurs microstructure/mark-index deviennent le GATE du
  registre memecoin** (module existant : `aster_microstructure_replay_validator`,
  spread top-10, seuil 20 bps). Un call non collectionnable n'entre pas dans
  les stats.
- **B2. Ré-test des champions legacy (LAB 3h/5h, HYPE long) avec les NOUVELLES
  couches comme filtres d'entrée** (flow_events, liq_events, depth) — sur
  données fraîches, MAINTENANT, pas dans 4 semaines.
- **B3. Backtest « funding wave » memecoin** — les 59 séries de funding ont
  déjà MEME/BOME/PEPE/WIF : corriger extrêmes de funding × vélocité X
  (`x_mentions`) × rendements. La donnée existe déjà.

## PILIER C — Zéro attente passive

- **C1. Rapport nocturne « Memecoin Pulse »** (nouvelle étape de campagne) —
  par memecoin Aster : vélocité X du jour, funding annualisé, liquidations
  captées, spread/collectionnabilité, calls du registre. Une page de faits
  chaque nuit.
- **C2. Backtest de la vélocité** dès que N jours suffisent (x_mentions
  s'accumule depuis le 21/09) — règle pré-enregistrée inchangée (N ≥ 10,
  win rate ≥ 55 %, sinon bruit et on le dit).
- **C3. Ledger paper des « ondes d'appel »** — quand vélocité X + funding
  extrême + collectionnable convergent, le signal est pris EN PAPER
  automatiquement chaque nuit (jamais réel sans validation). Le track record
  se construit en live pendant qu'on code la suite.

## Phases et jalons

| Phase | Contenu | Quand |
|---|---|---|
| 1 | klines memecoins (fait), recherches memecoin à 14h (fait), gate microstructure au registre | ce soir |
| 2 | parser v3 + tests, klines on-demand, Memecoin Pulse nocturne | 48 h |
| 3 | sonde fomo.family, verdicts memecoin complets, ré-test champions × couches flow, paper ledger des ondes | semaine 1 |
| 4 | backtests vélocité/positioning/funding-wave, verdict pré-enregistré | quand N suffit |

## Contraintes permanentes (non négociables)

1. Trading 100 % Aster — fomo.family et tout le reste ne sont que de la DATA.
2. Free only — aucun abonnement, aucune clé payante.
3. Aucun ordre réel sans validation utilisateur à chaque porte.
4. La règle pré-enregistrée (N ≥ 10, 55 %) s'applique à tout nouveau signal.

## Verdict du backtest absorption/sweep (23/09, nuit) — BRUIT CLASSÉ

`scripts/backtest_absorption.py` : 22 symboles × ~3000 bougies 1h, ~2 400
événements, règles EXACTES de l'indicateur, coûts 8 bps, split 70/30, règle
pré-enregistrée. Résultat : 224 bruit, 235 insuffisants, 63 « prometteurs »
en apparence — **mais ZÉRO combinaison confirmée train + val** (N val ≥ 10).
Les 63 sont les survivants aléatoires prédits par l'avertissement de
multiplicité.

Conséquences (acceptées avant de chercher ailleurs) :
1. Absorption & Sweep reste un outil VISUEL/contexte dans le terminal — PAS
   un signal directionnel autonome. Ne plus jamais le présenter comme edge.
2. Le paper ledger des ondes (C3) ne se construira PAS sur le flow seul :
   le moteur de la thèse est la couche SOCIALE (vélocité X, calls du
   registre) que personne d'autre ne systématise — le flow reste contexte.
3. Troisième grand résultat nul du projet (lab 36 372 combos, funding
   extrême, absorption/sweep). La règle pré-enregistrée tient : c'est ce
   qui distingue ce projet de la majority des « stratégies » qui ne se
   testent jamais contre elles-mêmes.

## Couche fomo.family (23/09 nuit) — LA mine de track records

Login utilisateur effectué dans le navigateur in-app → minage direct :

- **Leaderboard** : 150 traders × 3 fenêtres (24h/7j/30j) capturés —
  `data/fomo/leaderboard-*.json`. 281 traders uniques, **35 constants**
  (PnL > 0 sur les 3 fenêtres). @unipcs : +$14,6 M/30j (258+ trades/24h).
- **Clans** (équipes) : Fantom Troupe +$3,9 M/24h, Troupe KZ, Risk On…
- **Profil type** : 2K trades, top 5 trades (PnL/%), positions ouvertes avec
  contrats par chaîne (solana/ethereum/bnb/robinhood), **thèses postées**
  (signal social interne à fomo).
- **Pont X.com** : les handles fomo sont des handles X → les 12 meilleurs
  constants sont dans la watchlist du registre (`fomo_top`) et dans les
  récoltes (22 profils). Le registre score leurs CALLS ; fomo prouve leur
  PnL. L'union des deux preuves = la watchlist la plus forte du projet.
- **Pivot d'exécution (volonté utilisateur)** : fomo acceptable comme
  plateforme pour les coins absents d'Aster — exécution MANUELLE par
  l'utilisateur uniquement, jamais d'ordre autonome (règle inchangée).
- **Procédure de minage** (repeatable en session) : navigateur in-app →
  fomo.family/leaderboard → extraire 24H/7D/30D via evaluate (regex sur
  innerText, exclure DizzyOnlyClam = compte utilisateur) → écrire
  data/fomo/leaderboard-*.json → analyse de constance → mise à jour
  watchlist. Les PnL clans sont affichés en K/M (normaliser au parsing).

### Minage des positions (23/09 très tard) — limite documentée

Les profils fomo virtualisent leurs listes : seules les positions RENDERED
apparaissent dans le DOM/ARIA (0xAvast : 2 visibles / 37 déclarées). Le
minage complet demandera une passe d'interaction (cliquer l'onglet
Positions, scroll incrémental dans le conteneur). Ce qui est déjà acquis :
- unipcs tient des **RWA tokenisés** (SPYX = S&P 500, MSFTX = Microsoft
  sur Solana) — les top traders memecoin diversifient ;
- positions déclarées des 6 constants minés : unipcs 99, AvgJoesCrypto 51,
  ogle 42, 0xAvast 37, frogmanhaha 32, Salem 29 ;
- le filtre DOM des positions réelles est identifié (parents à classes
  vides, hors sidebar `A.block.rounded-lg` / discovery `grid-transition` /
  footer) — à réutiliser.

### Harvest headless fomo (23/09, 02h30) — blocage connu et contournement

`scripts/fomo_harvest.py` (login/status/positions/leaderboard) fonctionne :
le login headed est détecté (preuve POSITIVE : bouton nav Leaderboard,
l'absence de Login seule est un faux positif de rendu) et le profil
patchright persiste (cookies Privy vérifiés). MAIS le chargement du compte
en mode **headless pur** est bloqué (« Couldn't load your account » après
4 retries — anti-fingerprint Privy/Statsig côté fomo). Contournement
retenu : **headed sous Xvfb** (serveur X virtuel — fingerprint réel,
invisible) ; `xorg-server-xvfb` à installer par l'utilisateur
(`sudo pacman -S xorg-server-xvfb`) puis `xvfb-run` dans l'unité systemd.
En attendant : minage interactif en session (éprouvé, 714 positions).
