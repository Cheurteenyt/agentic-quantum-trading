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

## Verdict couverture Aster : NON

Testé par sondage `markets.tickSize(exchange, symbol)` via un script M5
(contrôles positifs : `binancef/btc/usd` = 0.1, `hyperliquid/btc/usd` = 0.1) :

| IDs testés | `aster`, `asterd`, `asterdex`, `asterf` × formats usdt/usd |
|---|---|
| Résultat | tous `null` → aucun listing Aster |

Conséquence assumée : MMT sert à **lire les flux Binance** (lieu de price
discovery des perps) comme contexte de marché ; l'exécution reste sur Aster ;
**notre stack reste l'autorité sur les données Aster** (warehouse 42 séries,
funding, liq-collector 24/7, Registre X). Sur les petites caps, prudence : les
flux Binance ne prédisent pas les divergences locale-Aster (cf. incident MEME
basis +4521 %).

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

## Workflow recommandé

1. Ouvrir M5 dans le navigateur (free).
2. Contexte macro/order-flow : layers natifs M5 (footprint, heatmap) sur
   Binance — lecture seule.
3. Nos signaux : attacher « Absorption & Sweep » (bouton indicateurs →
   scripts personnels).
4. Décision/exécution : sur **Aster uniquement**.
5. Les événements restent à corréler avec nos couches maison (funding
   extrême, liq_events, positioning Registre X) — pas encore de pont
   automatique M5 ↔ warehouse (futur).

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
