# 17 — MMT / M5 : terminal order-flow externe + MCP

Date : 2026-09-22. Statut : branché et validé. Champ d'application : **analyse
seulement** — le trading reste 100 % Aster (contrainte permanente).

## Ce que c'est

[MMT](https://app.mmt.gg/) (produit terminal : **M5**) = terminal d'order-flow
crypto dans le navigateur : footprint, heatmaps, CVD, DOM, volume profile,
TPO, VWAP sur 20+ exchanges. Le plan **free** est réel sans limite de temps
(2 charts, 5 layers/chart, 2500 barres d'historique). Pas d'abonnement pris —
contrainte respectée.

Il expose un **serveur MCP natif** (40 outils, pas 16 comme annoncé sur leur
page marketing) : pilotage du terminal (layouts, widgets, layers, drawings,
watchlist, alertes) + moteur de **scripts d'indicateurs** (« scripting v3 »)
créés/édités headless avec diagnostics de compilation.

## Verdict fiabilité du MCP

- **Fiable, périmètre borné par design** : pas d'ordres, pas de signaux, clés
  de trading séparées, tokens nommés/scopés/révocables (hashés côté MMT).
- Pipeline testée de bout en bout : handshake JSON-RPC → `tools/list` →
  `tools/call` → readback des valeurs de plots. Aucune incohérence.
- Deux réserves honnêtes : produit jeune (changelog quasi quotidien → les
  outils peuvent évoluer), et `chart_set_market` ne valide pas les paramètres
  (il accepte n'importe quel exchange — seul le chargement de données fait foi).
- Le token vit dans `~/.zcode/cli/config.json` (HORS du repo git). Révocable
  depuis le terminal M5 si doute.

## Verdict couverture Aster : NON (enquête exhaustive)

Quatre preuves indépendantes convergent :
1. **Sonde `markets.tickSize`** via scripts M5 — 10 IDs candidats testés
   (`aster`, `asterd`, `asterdex`, `asterf`, `asterusd`, `asterperp`,
   `aster_dex` × formats btc/usdt, btc/usd, btc) : tous `null`. Contrôles
   positifs : `binancef/btc/usd` = 0.1, `hyperliquid/btc/usd` = 0.1.
2. **Code de l'app** (88 chunks SvelteKit téléchargés et greppés) : zéro
   référence Aster (les seules occurrences « aster » sont le mot « master »).
3. **Homepage** : 9 exchanges nommés sur « 20+ », pas d'Aster ; focus
   Hyperliquid (position maps, API dédiée).
4. `chart_set_market` n'a accepté aucun marché Aster avec données.

Conséquence assumée : MMT sert à **lire les flux Binance** (lieu de price
discovery des perps) comme contexte de marché ; l'exécution reste sur Aster ;
**notre stack reste l'autorité sur les données Aster** (warehouse 42 séries,
funding, liq-collector 24/7, Registre X). Sur les petites caps, prudence : les
flux Binance ne prédisent pas les divergences locale-Aster (cf. incident MEME
basis +4521 %). Rappel de l'utilisateur (23/09) : « sur aster les charts sont
pas les même par rapport à un autre exchange » — tout signal lu sur Binance
n'est qu'un CONTEXTE, jamais la vérité d'exécution.

## L'alternative native Aster : scripts/aster_absorption.py

L'API Aster (`fapi.asterdex.com/fapi/v1/klines`) expose le **volume taker buy
par bougie** (colonne 9) → delta acheteur/vendeur calculable sur les VRAIS
prix du lieu d'exécution. `scripts/aster_absorption.py` applique EXACTEMENT
les règles de l'indicateur MMT aux klines Aster :

    .venv/bin/python scripts/aster_absorption.py --symbol BTCUSDT,ETHUSDT,ASTERUSDT --interval 30m --last 14

- absorption : |Δ| ≥ 2× baseline (50 bougies) + corps ≤ 40 % du range +
  clôture à contre-sens du delta
- sweep : perforation du plus-bas/plus-haut 20 bougies ≥ 0.15 ATR(14) +
  reclaim (close dans les 40 % opposés du range)
- 10 tests unittest (`tests/test_aster_absorption.py`) verrouillent la logique
  (suite projet : 595 verts).

Premier run (23/09) : ASTERUSDT 09-22 03:00 sweep_low à 2.80 ATR de profondeur
(stop hunt), puis série d'absorptions vendeuses 0.72–0.74 avant le rebond.
C'est ce flux qui fait autorité — l'indicateur MMT sur Binance reste le
contexte visuel.

## Ce qui est branché

- **MCP `m5`** dans `~/.zcode/cli/config.json` (scope user) — connecté à
  l'ouverture de session ZCode tant que M5 est ouvert dans un onglet navigateur.
- **Indicateur « Absorption & Sweep »** (script M5 `ea89baa8-...-026b3fc20009`,
  rev 5, source locale : `scripts/mmt_scripts/absorption_sweep.mm`), attaché à
  un chart BTC/USD Binance 30m :
  - **Absorption** : |Δ| ≥ 2× baseline (moyenne mobile des |Δ| sur `len`
    bougies) MAIS corps ≤ 40 % du range et clôture à contre-sens du delta →
    marqueur + tint de fond + alerte terminal (`onClose`).
  - **Sweep** : perforation du plus-bas/plus-haut 20 bougies d'au moins
    15 % ATR(14) puis reclaim en clôture (close dans les 40 % opposés du
    range) → marqueur `+`.
  - Histogramme **Delta** (buyVolume − sellVolume) en sous-pane.
  - Tous les plots du handler `close` portent `offset: -1` (les plots close
    sont horodatés à la bougie suivante — vérifié empiriquement).
- **Vérifié** : logique contrôlée à la main sur 7/7 signaux réels (candles
  Binance relues via `chart_get_candles` avec split buy/sell) ; fréquence
  ~6 % de bougies signalées sur 200 (sain, pas du bruit).

## Organisation d'ensemble : deux stations, un pont, une accumulation

### Station CONTEXTE — MMT free (Binance, lecture seule)

Leurs 266 indicateurs communautaires + footprint/heatmaps natifs restent
attachables en deux clics sur les charts Binance. Notre « Absorption & Sweep »
M5 y vit aussi. Rôle : vision macro de l'order-flow du lieu de price
discovery — JAMAIS une vérité d'exécution.

### Station VÉRITÉ — notre stack sur données Aster natives

- `scripts/aster_absorption.py --record` : mêmes signaux, vrais prix Aster,
  accumulation dans `flow_events` (klines.db, PK composite = idempotent, la
  signature de params sépare les familles de seuils).
- `scripts/basis_guard.py --record` : divergence Aster↔Binance mesurée par
  symbole, snapshot en `basis_snapshots`, alerte si |basis| ≥ 0.5 % —
  l'avertissement « les charts ne sont pas les mêmes » est devenu une mesure.
- Les deux tournent chaque nuit dans la campagne systemd (étapes 18-19) —
  dans 2-4 semaines : backtest `flow_events` avec la règle pré-enregistrée
  habituelle (N ≥ 10, winrate ≥ 55 %, sinon classé bruit comme le funding).

### Le pont : reprendre la LOGIQUE des indicateurs MMT vers Aster

Impossible d'importer un indicateur MMT (moteur fermé, leurs exchanges
seulement). MAIS `script_fork` fourke tout script publié à source visible →
on lit la logique → on la ré-implémente en Python sur données Aster, avec
tests (exactement le chemin fait pour Absorption & Sweep). MMT devient une
**bibliothèque gratuite d'idées de trading** :

1. Repérer un indicateur qui parle dans le catalogue MMT (UI, bouton
   indicateurs → communauté)
2. Me donner son nom → je le fourke via MCP et je lis sa source
3. Portage Python natif Aster + tests + accumulation nocturne
4. Backtest dans 2-4 semaines avec la règle pré-enregistrée

### Heatmap et positioning MAISON (équivalents natifs Aster, 23/09)

Le catalogue public MMT (mmt.gg/indicators) expose 24 indicateurs publiés —
slugs + IDs extraits vers /tmp (référence : `aggregated-ob-imbalance`,
`net-positioning-v2`, `naked-poc-tpoc-single-prints`, `key-levels-v2-4`,
`the-oracle`…). MAIS les IDs de la vitrine ne sont pas des IDs M5 :
`script_get`/`script_fork` sur ces UUID renvoient 404, et la source lisible
exige la session app. Procédure de portage (quand M5 est ouvert) :
ouvrir l'indicateur dans l'UI MMT → bouton Fork → le fork apparaît dans
notre `script_list` → je lis la source via MCP et je porte.

En attendant, les DEUX concepts phares ont déjà leurs équivalents natifs :

- **Heatmap de liquidité maison** : `scripts/depth_collector.py` (systemd
  `aster-depth-collector.service`, 24/7, Restart=always) échantillonne le
  carnet Aster (500 niveaux, bacs 0.01 % du mid) dans `depth.db` (rétention
  30 j). `scripts/depth_heatmap.py` rend le PDF vectoriel
  (`reports/depth-heatmap-<sym>-<date>.pdf`, fond blanc/encre navy) — étape
  nocturne 21. Première heatmap exploitable après ~12 h d'accumulation.
- **Positioning proxy** : Aster n'expose PAS les ratios long/short de Binance
  (endpoints `/futures/data/*` = 404 déguisé) — `scripts/flow_snapshot.py`
  (étape nocturne 20) capture donc Open Interest + delta taker 30m dans
  `flow_snapshots` : la lecture « la foule se renforce-t-elle ? » sur données
  Aster natives.

### Workflow recommandé

1. Ouvrir M5 dans le navigateur (free).
2. Contexte macro/order-flow : layers natifs M5 (footprint, heatmap) sur
   Binance — lecture seule.
3. Nos signaux : attacher « Absorption & Sweep » (bouton indicateurs →
   scripts personnels).
4. Décision/exécution : sur **Aster uniquement**, en vérifiant
   `basis_guard` si le symbole est petit.
5. Les événements absorption/sweep Aster s'accumulent automatiquement
   (`flow_events`) — corrélation future avec funding extrême, liq_events et
   positioning du Registre X.

## Pièges connus (notes pour la prochaine session)

- `script_check` AVANT tout save ; lire `result.diagnostics` après chaque
  écriture ; un 409 « revision conflict » = relire `script_get` et repartir
  de la révision courante.
- `markets.tickSize` interdit en `setup` (S002) — l'appeler dans un handler.
- `plot.histogram` n'a pas de paramètre `offset` (seuls line/marker/point…).
- `plot.bg.plot` exige l'argument nommé `color:`.
- `script_get_plot_values` renvoie les ~50 derniers points TRACÉS par série
  (pas les bougies) — les fréquences de signaux se calculent sur la fenêtre
  candles correspondante, pas sur le compte brut.
- Capture d'écran `chart_screenshot` : timeout si l'onglet est en
  arrière-plan (Chrome throttle) — mettre l'onglet M5 au premier plan.
