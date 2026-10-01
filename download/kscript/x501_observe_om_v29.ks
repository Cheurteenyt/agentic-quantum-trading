//@version=3
define(title="X501 Observe OM v29 (structure + regime + OI + funding, gratuit)", position="offchart", axis=true)

// ============================================================================
// OPÉRATION x501 — COLLECTEUR D'OBSERVATION v29 (PR #2 volet 1, ZÉRO ORDRE)
// ============================================================================
// Réponse à la critique « outils gratuits > TradingView non exploités » :
// ce collecteur rend lisible sur le graphe openmarket — SANS aucun
// abonnement, SANS indicateur tiers — la couche de contexte om_v27 mesurée
// côté Python (x501_signaux_om_v29.py, verdicts gravés) :
//   S3 structure      : position dans le range 90 j (pos90, %) + compression
//                       range30/range90 (comp, %) — lecture D1, indépendante
//                       du timeframe du chart ;
//   S4 régime vol     : ATR% D1 rapporté à sa moyenne 90 j (regime, x) ;
//   S2 impulsion OI   : delta OI 24h (doi, %) croisé au rendement prix 24h
//                       (r24, %) -> quadrant (source open_interest native) ;
//   S1 carry funding  : taux annualisé (fund, %/an).
// VERDICTS v29 (walk-forward chrono global, leçons v26/v27 gravées) :
//   S1 KILL / S3 KILL -> AFFICHAGE SEULEMENT (aucune décision) ;
//   S2 ADVISORY (dispersion 28,1 bps en test : flush +9,9 vs tendance -18,2)
//      -> observé pour accumuler la preuve temporelle 4x/j, NON bloquant ;
//   S4 DIAG (183/469 trades, T1+ / T3- tendance in-sample non actionnable).
// Journalisation sur bougie FERMÉE uniquement : toutes les séries sont lues
// avec l'index [1] (anti-repaint par construction). Aucun strategy.* : le
// collecteur ne place AUCUN ordre, il n'ajoute aucun risque au déploiement.
// A charger en H1 (lecture OI 24h = barres [1] vs [25]).
// ============================================================================

var rangeDays = input(name="rangeDays", type="number", defaultValue=90, label="Fenêtre structure (jours)", constraints={min: 30, max: 180, step: 5})

// ---- série principale : spine du chart (obligatoire, doc multi-source) ----
timeseries trade = ohlcv(symbol=currentSymbol, exchange=currentExchange)

// ---- S3 + S4 : structure et régime calculés en D1 (indépendant du chart) --
timeseries d1 = request(symbol=currentSymbol, timeframe="1D", exchange=currentExchange)
var loR = lowest(source=d1.low, period=rangeDays)[1]
var hiR = highest(source=d1.high, period=rangeDays)[1]
var lo30 = lowest(source=d1.low, period=30)[1]
var hi30 = highest(source=d1.high, period=30)[1]
var d1Atr = atr(source=d1, period=14)
var d1AtrPct = d1Atr[1] / d1.close[1] * 100
var d1AtrPctAvg = sma(source=d1Atr / d1.close * 100, period=rangeDays)[1]
var pos90 = hiR > loR ? (d1.close[1] - loR) / (hiR - loR) * 100 : na
var comp = hiR > loR ? (hi30 - lo30) / (hiR - loR) * 100 : na
var regime = isnum(d1AtrPctAvg) && d1AtrPctAvg > 0 ? d1AtrPct / d1AtrPctAvg : na

// ---- S2 : impulsion OI x prix (24 barres H1 = 24 h) ------------------------
timeseries oi = source("open_interest", symbol=currentSymbol, exchange=currentExchange)
var doi24 = isnum(oi[1]) && isnum(oi[25]) && oi[25] > 0 ? (oi[1] / oi[25] - 1) * 100 : na
var r24 = trade.close[1] / trade.close[25] * 100 - 100
// quadrants om_v27 : OI+p+ tendance_L (pire en test -18,2 bps) | OI+p- pression_S
//                    OI-p+ squeeze | OI-p- flush (meilleur en test +9,9 bps)
var quadCd = !isnum(doi24) ? 0 : doi24 > 0 && r24 > 0 ? 1 : doi24 > 0 && r24 <= 0 ? 2 : doi24 <= 0 && r24 > 0 ? 3 : 4

// ---- S1 : carry funding annualisé (KILL v29 — affichage diagnostique) ------
timeseries fr = funding_rate(symbol=currentSymbol, exchange=currentExchange)
var fundAnn = fr.value[1] * 3 * 365 * 100

// ---- affichage : pos90 (0-100) comme ligne principale ----------------------
plotLine(value=pos90, colors=["#42a5f5"], width=2, label=["Position range 90j %"], desc=["S3a (KILL v29, affichage) : position du close D1 dans le range 90j"])
plotLine(value=comp, colors=["#ffa726"], width=1, label=["Compression range %"], desc=["S3b (KILL v29, affichage) : range 30j / range 90j"])

// ---- journalisation : une ligne à l'ouverture de chaque nouvelle bougie ----
static lastLogged = -1
var isFresh = barIndex != lastLogged
lastLogged = barIndex
alert(message=format("X501OM|{0}|pos90={1}|comp={2}|regime={3}|doi24={4}|r24={5}|quad={6}|fundAnn={7}", currentSymbol, pos90, comp, regime, doi24, r24, quadCd, fundAnn), condition=isFresh)
