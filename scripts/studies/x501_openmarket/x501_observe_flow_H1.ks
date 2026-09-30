//@version=3
define(title="X501 Collector Flow H1 (whale/retail + carnet + funding)", position="offchart", axis=true)

// ============================================================================
// OPÉRATION x501 — COLLECTEUR D'OBSERVATION v10 (ZÉRO RISQUE, ZÉRO ORDRE)
// ============================================================================
// But : journaliser en LIVE les features que les historiques publics Binance
// ne contiennent PAS et dont dépend le prochain gain d'edge (chantier v10) :
//   1) delta WHALE (buckets >= 500K USD) et RETAIL (< 10K USD) par bougie H1
//      — source trade_volume_by_size, idiome cookbook officiel ;
//   2) déséquilibre du carnet (sumBids / sumAsks, profondeur configurable) ;
//   3) funding rate du perp du chart ;
//   4) contexte BTC D1 (ATR %, close vs EMA50) = filtre de régime moteur.
// Sortie : UNE alerte par nouvelle bougie H1, message « X501OBS|...| »
// (format pipe-friendly, un champ par métrique). Aucun strategy.* : le
// collecteur ne place AUCUN ordre, il n'ajoute aucun risque au déploiement.
// Paramètre UI openmarket : fréquence d'alerte = « une fois par clôture ».
// Journalisation sur bougie FERMÉE uniquement : toutes les séries sont
// lues avec l'index [1] (dernière bougie complète) — anti-repaint par
// construction. La détection de nouvelle bougie = comparaison de barIndex
// avec un static (idiome cookbook : static + réassignation racine).
// ============================================================================

var bookDepth = input(name="bookDepth", type="number", defaultValue=5, label="Profondeur carnet %", constraints={min: 1, max: 20, step: 1})

// ---- série principale : spine du chart (obligatoire, doc multi-source) ----
timeseries trade = ohlcv(symbol=currentSymbol, exchange=currentExchange)
timeseries tv = trade_volume_by_size(symbol=currentSymbol, exchange=currentExchange)

// ---- 1) flux whale vs retail (buckets par taille d'ordre) -----------------
var cells = tv.cells
var whaleFlow = cells.filter((c) => c[0] >= 5).map((c) => c[1] - c[2]).reduce((a, b) => a + b, 0)
var retailFlow = cells.filter((c) => c[0] <= 2).map((c) => c[1] - c[2]).reduce((a, b) => a + b, 0)
var netFlow = whaleFlow + retailFlow

// ---- 2) carnet ------------------------------------------------------------
// v13 audit : forme nommée canonique (doc data-sources : 1er argument = type,
// symbole/exchange en arguments nommés ; identiques au positionnel).
timeseries orderbookData = source(type="orderbook", symbol=currentSymbol,
                                  exchange=currentExchange)
var totalBids = sumBids(orderbookData, depthPct=bookDepth)
var totalAsks = sumAsks(orderbookData, depthPct=bookDepth)
var bookRatio = totalAsks > 0 ? totalBids / totalAsks : 1

// ---- 3) funding -----------------------------------------------------------
timeseries fr = funding_rate(symbol=currentSymbol, exchange=currentExchange)
var fundVal = fr.value[1]

// ---- 4) contexte BTC D1 (régime moteur) -----------------------------------
timeseries btc = request(symbol="BTCUSDT", timeframe="1D", exchange="BINANCE")
timeseries btcClose = btc.close
timeseries btcAtr = atr(source=btc, period=14)
timeseries btcEma = ema(source=btc.close, period=50)
var btcAtrPct = btcAtr[1] / btcClose[1] * 100
var btcTrend = btcClose[1] > btcEma[1] ? 1 : -1

// ---- affichage (contrôle visuel du collecteur) ----------------------------
static whaleCvd = 0
static retailCvd = 0
whaleCvd = whaleCvd + whaleFlow
retailCvd = retailCvd + retailFlow
plotLine(value=whaleCvd, colors=["#ab47bc"], width=2, label=["Whale CVD USD"], desc=["CVD cumulé des buckets 500K+ USD"])
plotLine(value=retailCvd, colors=["#26c6da"], width=2, label=["Retail CVD USD"], desc=["CVD cumulé des buckets < 10K USD"])

// ---- journalisation : une ligne à l'ouverture de chaque nouvelle bougie ---
// (les séries [1] correspondent alors à la bougie qui vient de se fermer).
static lastLogged = -1
var isFresh = barIndex != lastLogged
lastLogged = barIndex
alert(message=format("X501OBS|{0}|whale={1}|retail={2}|net={3}|book={4}|fund={5}|atrBTC={6}|trend={7}", currentSymbol, whaleFlow, retailFlow, netFlow, bookRatio, fundVal, btcAtrPct, btcTrend), condition=isFresh)
