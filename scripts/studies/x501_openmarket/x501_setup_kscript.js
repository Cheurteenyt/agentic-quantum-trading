//@version=3
// ============================================================================
// OPÉRATION x501 — SCANNER PAT HAUTE CADENCE (kScript v3, openmarket.xyz)
// ============================================================================
// Rôle : industrialiser la détection des 4 alphas gagnants du moteur v5
// (51 trades mesurés, E[R] = +0,62 R ; pool PREMIUM BTC/ETH 35 trades,
// E[R] = +0,83 R) et appliquer le sizing du Pilote Adaptatif de Trajectoire
// (MC v6 : 0 rupture sur 132 000 chemins, maxDD <= 25 % par construction).
//
// ALPHAS RÉPLIQUÉS (1:1 depuis x501_alpha_backtest.py / x501_engine_v5.py) :
//   A1 « Symbiose 4h->1h »  (chart 1h, BTC/ETH premium)  : régime 4h+D1+ADX,
//        repli dans la zone EMA21 4h, croisement CVD 1h, bougie d'appui,
//        funding < 0,05 %. Stop = swing 24 barres 1h - 0,35 %.
//   A2 « Cascade & Financement » (chart 4h, premium)     : funding extrême
//        négatif/positif, RSI4 capitulation, CVD qui absorbe, clôture au-delà
//        du close D1. Stop = extrême de purge 8 barres 4h ± 0,35 %.
//   A3 « Éruption Volatilité » (chart 4h, 16 actifs)     : squeeze BB récent
//        (largeur < 60 % de sa moyenne 30), cassure Donchian 20 précédent,
//        volume > 1,5 x moyenne 30, CVD 4h, régime D1, ADX. Stop = autre côté
//        du canal ± 0,35 %.
//   A4 « Confluence Multi-Périodes » (chart 4h, premium) : régime D1+4h+ADX,
//        SuperTrend(3,10), repli EMA21 4h, stochastique(14,3,3) qui tourne
//        depuis survente/surachat, CVD 4h. Stop = swing 6 barres 4h ± 0,35 %.
//   A6 « Re-ignition » (chart 4h, 16 actifs)             : tendance D1+4h+ADX
//        + SuperTrend, repli des 3 dernières barres 4h sur la zone EMA21 4h,
//        bougie qui clôture au-dessus du plus haut précédent avec marge
//        0,15 x ATR% 4h, volume 1,5 x, force qui accélère, CVD 4h.
//        Stop = swing 6 barres 4h ± 0,35 %.
//   (A5 désactivé comme en v5 : edge négatif mesuré sur alts.)
//
// SIZING PAT (portage direct du contrôleur Monte-Carlo ; allocation v10-G4
// re-certifiée sous bootstrap corrélé v11 : 0 rupture, DD <= 25 % par
// construction, médiane 12 m 642 $ à cadence x3) :
//   f_alpha = risk_alpha/100 x g_dd x g_pace, avec
//     g_dd   = clamp((DD_CAP - dd) / (kappa x DD_CAP), 0, 1)   [budget DD]
//     g_pace = clamp(1 + 0,6 x (1 - eq/pace), cut, boost)      [pression +68 %/mois]
//     verrou anti-rupture : f <= (DD_CAP - dd) / ((1 - dd) x 1,5) x 0,999
//     verrou de mission   : eq >= 50 100 $ -> plus aucun ordre.
//   Mise PAR ALPHA (allocation G4, jambes mesurées v8/v10/v11) :
//     A1 5 %, main-A3 13 %, main-A4 13 %, sat-A4 3 %, sat-A3 1,5 %.
//     A2/A6 hors pool mesuré -> 1 % (mode observation, edge non établi).
//   qty = min(risque$/distStop, eq x levMax/px), notional min 5 $.
//   Sorties = échelle du moteur : TP1 +1,5R (50 %), TP2 +2,5R (50 % du
//   restant = 25 % initial), stop -> break-even après TP1, puis trailing
//   24x1h (A1) / 5x4h (A2/A3/A4/A6) - 0,50 %, sorties défensives par alpha.
//   Coupe-circuits : jour -8 %, semaine -15 % (nouvelles entrées bloquées).
//
// FILTRE ALTS (v5.2) : sur tout actif autre que BTC, un long n'est pris que
//   si BTC est haussier en D1 (close > EMA50 D1) et directionnel (écart à
//   l'EMA50 D1 >= 1,0 x ATR% D1) ; les shorts exigent l'inverse.
//   -> input isAlt=true sur les 14 satellites, false sur BTC (et ETH).
//
// ADX (proxy documenté) : la doc kScript retourne adx() sous forme de tuple
//   [ADX, DI+, DI-] sans membres nommés publiés. Pour un script qui compile
//   du premier coup, la force de tendance est mesurée par le déplacement
//   normalisé NDD = |close - EMA50| / ATR14 (100 % fonctions documentées),
//   calibrable via les inputs nddGate*. La ligne adx() native est fournie
//   en commentaire pour qui veut la réactiver après vérification.
//
// DÉPLOIEMENT (scan 24/7, ~43 trades/mois visés = scénario C3 du MC) :
//   1) Charts BINANCE_FUTURES perps :
//      - Premium MAIN (isAlt=false, mises main) :
//          BTCUSDT, ETHUSDT en mode 1h (A1 actif, riskMainA1=5)
//          BTCUSDT, ETHUSDT en mode 4h (A3/A4 actifs, riskMainA3=13,
//          riskMainA4=13)
//      - Satellites 4h (isAlt=true, mises sat) : SOL, XRP, BNB, DOGE, AVAX,
//        LINK, ADA, DOT, LTC, TRX, NEAR, APT, ARB, OP
//        (A3 : riskSatA3=1,5 ; A4 : riskSatA4=3 ; A2/A6 : riskOther=1,
//        observation — hors pool mesuré).
//   2) Coller ce script dans l'éditeur (openmarket.xyz/kscript), choisir le
//      mode via l'input, lancer le Backtest (gratuit ; tier Free : 1 000
//      barres / 20 runs par jour).
//   3) Alertes : sidebar Alertes -> « alert() triggers » -> Every time ->
//      vos canaux. Le script émet un message par signal avec alpha, sens,
//      stop, taille f% et qty pour une équité simulée de 100 $ (capital de
//      l'opération) ; multipliez si votre capital réel diffère.
// ============================================================================

strategy(title="x501 Scanner PAT — Alphas v5 + sizing PAT",
         position="onchart", axis=true,
         initialCapital=100, currency="USD",
         instrument="perps", leverage=10, maintenanceMarginPercent=0.5,
         qtyType="fixed", qtyValue=1, pyramiding=1,
         makerFeePercent=0.018, takerFeePercent=0.045,
         slippageBps=2, slippageModel="fixed",
         fillModel="pessimistic", funding="data",
         onLiquidation="halt")

// ------------------------------- INPUTS -------------------------------------
var tfMode    = input(name="tfMode", type="select", defaultValue="1h",
                      options=["1h", "4h"], label="Mode (TF du chart)",
                      group="Mode")
var useA1     = input(name="useA1", type="boolean", defaultValue=true,
                      label="Alpha A1 — Symbiose 4h->1h (chart 1h)", group="Alphas")
var useA2     = input(name="useA2", type="boolean", defaultValue=true,
                      label="Alpha A2 — Cascade & Financement (chart 4h)", group="Alphas")
var useA3     = input(name="useA3", type="boolean", defaultValue=true,
                      label="Alpha A3 — Éruption Volatilité (chart 4h)", group="Alphas")
var useA4     = input(name="useA4", type="boolean", defaultValue=true,
                      label="Alpha A4 — Confluence Multi-Périodes (chart 4h)", group="Alphas")
var useA6     = input(name="useA6", type="boolean", defaultValue=true,
                      label="Alpha A6 — Re-ignition (chart 4h)", group="Alphas")

var riskMainA1 = input(name="riskMainA1", type="slider", defaultValue=5,
                       constraints={min: 0.5, max: 20, step: 0.5},
                       label="Risque main A1 % / trade (G4 : 5)",
                       group="Sizing PAT — mises par alpha (G4)")
var riskMainA3 = input(name="riskMainA3", type="slider", defaultValue=13,
                       constraints={min: 0.5, max: 20, step: 0.5},
                       label="Risque main A3 % / trade (G4 : 13)",
                       group="Sizing PAT — mises par alpha (G4)")
var riskMainA4 = input(name="riskMainA4", type="slider", defaultValue=13,
                       constraints={min: 0.5, max: 20, step: 0.5},
                       label="Risque main A4 % / trade (G4 : 13)",
                       group="Sizing PAT — mises par alpha (G4)")
var riskSatA4  = input(name="riskSatA4", type="slider", defaultValue=3,
                       constraints={min: 0.25, max: 10, step: 0.25},
                       label="Risque satellite A4 % / trade (G4 : 3)",
                       group="Sizing PAT — mises par alpha (G4)")
var riskSatA3  = input(name="riskSatA3", type="slider", defaultValue=1.5,
                       constraints={min: 0.25, max: 10, step: 0.25},
                       label="Risque satellite A3 % / trade (G4 : 1,5)",
                       group="Sizing PAT — mises par alpha (G4)")
var riskOther  = input(name="riskOther", type="slider", defaultValue=1,
                       constraints={min: 0.25, max: 10, step: 0.25},
                       label="Risque A2/A6 % (observation, hors pool mesuré)",
                       group="Sizing PAT — mises par alpha (G4)")
var kappa     = input(name="kappa", type="slider", defaultValue=1.6,
                      constraints={min: 1.0, max: 2.5, step: 0.1},
                      label="kappa (vitesse de désescalade près du DD max)",
                      group="Sizing PAT")
var ddCapPct  = input(name="ddCapPct", type="slider", defaultValue=25,
                      constraints={min: 10, max: 25, step: 1},
                      label="Drawdown max autorisé (%)", group="Sizing PAT")
var paceBoost = input(name="paceBoost", type="slider", defaultValue=1.5,
                      constraints={min: 1.0, max: 2.0, step: 0.1},
                      label="Boost risque si retard sur le rythme (x)", group="Sizing PAT")
var paceCut   = input(name="paceCut", type="slider", defaultValue=0.6,
                      constraints={min: 0.3, max: 1.0, step: 0.1},
                      label="Coupe risque si avance sur le rythme (x)", group="Sizing PAT")
var targetEq  = input(name="targetEq", type="number", defaultValue=50100,
                      label="Objectif de mission ($) — verrou à l'atteinte",
                      group="Sizing PAT")
var levMax    = input(name="levMax", type="slider", defaultValue=10,
                      constraints={min: 1, max: 10, step: 1},
                      label="Levier effectif max (x)", group="Sizing PAT")

var stopBuf   = input(name="stopBuf", type="slider", defaultValue=0.35,
                      constraints={min: 0.1, max: 1.0, step: 0.05},
                      label="Marge de stop au-delà du swing (%)", group="Exécution")
var trailBuf  = input(name="trailBuf", type="slider", defaultValue=0.5,
                      constraints={min: 0.1, max: 2.0, step: 0.1},
                      label="Marge du trailing après TP2 (%)", group="Exécution")
var atrStopFac= input(name="atrStopFac", type="slider", defaultValue=0.7,
                      constraints={min: 0.3, max: 1.5, step: 0.1},
                      label="Stop >= fac x ATR% 4h (normalisation volatilité)",
                      group="Exécution")
var dayStop   = input(name="dayStop", type="slider", defaultValue=8,
                      constraints={min: 3, max: 25, step: 1},
                      label="Coupe-circuit jour (%)", group="Exécution")
var weekStop  = input(name="weekStop", type="slider", defaultValue=15,
                      constraints={min: 5, max: 40, step: 1},
                      label="Coupe-circuit semaine (%)", group="Exécution")
var warmupBars= input(name="warmupBars", type="number", defaultValue=900,
                      label="Warmup (barres chart) — 900 en 1h Free, 300 en 4h",
                      group="Exécution")

var isAlt     = input(name="isAlt", type="boolean", defaultValue=true,
                      label="Actif satellite (filtre direction BTC en D1)",
                      group="Filtre BTC")
var chopNdd   = input(name="chopNdd", type="slider", defaultValue=1.0,
                      constraints={min: 0.3, max: 3.0, step: 0.1},
                      label="BTC directionnel : |c-EMA50|/ATR D1 >=", group="Filtre BTC")
var nddGate4  = input(name="nddGate4", type="slider", defaultValue=1.8,
                      constraints={min: 0.5, max: 4.0, step: 0.1},
                      label="Proxy ADX4h>18 : NDD 4h >=", group="Filtre BTC")
var nddGate4lo= input(name="nddGate4lo", type="slider", defaultValue=1.4,
                      constraints={min: 0.4, max: 3.0, step: 0.1},
                      label="Proxy ADX4h>15 (A3) : NDD 4h >=", group="Filtre BTC")
var nddGate4hi= input(name="nddGate4hi", type="slider", defaultValue=2.0,
                      constraints={min: 0.6, max: 4.0, step: 0.1},
                      label="Proxy ADX4h>20 (A6) : NDD 4h >=", group="Filtre BTC")

// ------------------------------ DONNÉES -------------------------------------
timeseries bars = ohlcv(symbol=currentSymbol, exchange=currentExchange)
timeseries fnd  = source("funding_rate", symbol=currentSymbol, exchange=currentExchange)
timeseries bsv  = source("buy_sell_volume", symbol=currentSymbol, exchange=currentExchange)

// CVD natif au TF du chart + ligne de signal (EMA21 en 1h / EMA14 en 4h,
// mêmes périodes que le moteur Python).
timeseries cvd     = cum(bsv.buy - bsv.sell)
timeseries cvdSig1 = ema(source=cvd, period=21)
timeseries cvdSig4 = ema(source=cvd, period=14)
var cvdSig = tfMode == "1h" ? cvdSig1 : cvdSig4

// Régimes confirmés no-repaint : 4h (pour le mode 1h) et 1d (régime D1).
timeseries h4 = htf(source=bars, timeframe="4h")
timeseries d1 = htf(source=bars, timeframe="1d")

// BTC D1 pour le filtre des satellites.
timeseries btcD1 = request("BTCUSDT", "1d", exchange=currentExchange)

// ---------------------- RÉGIME 4h (mode 1h : confirmé htf) ------------------
var c4   = tfMode == "1h" ? h4.close : bars.close
var o4   = tfMode == "1h" ? h4.open  : bars.open
var h4hi = tfMode == "1h" ? h4.high  : bars.high
var h4lo = tfMode == "1h" ? h4.low   : bars.low
timeseries e4t   = ema(source=c4, period=50)          // EMA tendance 4h
timeseries e4z   = ema(source=c4, period=21)          // EMA zone 4h
timeseries atr4  = atr(source=h4, period=14)          // ATR 4h (Wilder)
var atr4pct = isnum(atr4) && c4 > 0 ? atr4 / c4 * 100.0 : na
// Proxy ADX : déplacement normalisé NDD = |c4 - EMA50 4h| / ATR 4h.
// Ligne native équivalente (à réactiver si membres publiés) :
//   var adxD = adx(source=h4, period=14)   // -> [ADX, DI+, DI-]
var ndd4   = isnum(atr4) && atr4 > 0 ? math.abs(c4 - e4t) / atr4 : na
var regime4Up = isnum(c4) && isnum(e4t) && c4 > e4t
var regime4Dn = isnum(c4) && isnum(e4t) && c4 < e4t

// --------------------------- RÉGIME D1 (confirmé) ---------------------------
timeseries e1t    = ema(source=d1.close, period=50)   // EMA50 D1
var regime1Up = isnum(d1.close) && isnum(e1t) && d1.close > e1t
var regime1Dn = isnum(d1.close) && isnum(e1t) && d1.close < e1t

// Filtre directionnel BTC (satellites) : écart à l'EMA50 D1 >= 1,0 x ATR% D1.
timeseries btcE1    = ema(source=btcD1.close, period=50)
timeseries btcAtr1  = atr(source=btcD1, period=14)
var btcDisp = isnum(btcE1) && btcE1 > 0 && isnum(btcAtr1) && btcAtr1 > 0
              ? math.abs(btcD1.close / btcE1 - 1.0) * 100.0
              : na
var btcAtrPct = isnum(btcAtr1) && btcD1.close > 0 ? btcAtr1 / btcD1.close * 100.0 : na
var btcDir    = isnum(btcDisp) && isnum(btcAtrPct) && btcDisp >= chopNdd * btcAtrPct
var btcRegUp  = isnum(btcD1.close) && isnum(btcE1) && btcD1.close > btcE1

// --------------------------- COMPOSANTS 4h (A2/A3/A4/A6) --------------------
timeseries st4 = supertrend(factor=3, atrPeriod=10)   // .line / .direction
timeseries sto4 = stoch(periodK=14, smoothK=3, periodD=3)  // .k / .d
timeseries don4 = donchian(source=bars, period=20)    // .upper / .lower
timeseries volMa = sma(source=bars.volume, period=30)
// Largeur BB (A3) = 4 x stdev20 / sma20 = (upper - lower) / basis.
timeseries bb4  = bb(source=bars.close, period=20, mult=2)
timeseries bbw  = (bb4.upper - bb4.lower) / bb4.basis
timeseries bbwm = sma(source=bbw, period=30)
var sqz     = isnum(bbw) && isnum(bbwm) && bbwm > 0 && bbw < bbwm * 0.60
var sqzAge  = barssince(sqz)
timeseries rsi4 = rsi(source=bars.close, period=14)
timeseries purgeLo = lowest(bars.low, 8)
timeseries purgeHi = highest(bars.high, 8)
timeseries swLo6 = lowest(bars.low, 6)
timeseries swHi6 = highest(bars.high, 6)
// Fenêtres de stop/trailing A1 (24x1h) et trail 4h (5 barres) — déclarées
// au niveau racine : toute série doit se calculer à CHAQUE barre.
timeseries swLo24 = lowest(bars.low, 24)
timeseries swHi24 = highest(bars.high, 24)
timeseries trailLo5 = lowest(bars.low, 5)
timeseries trailHi5 = highest(bars.high, 5)

// ------------------------------ PAT : ÉTAT ----------------------------------
persist peak = 100.0
persist t0   = 0.0
persist lock = false          // verrou de mission
persist dayEqA = 100.0
persist dayT = 0.0
persist weekEqA = 100.0
persist weekT = 0.0

// État de position (une position nette max par chart).
persist activeId = ""
persist pendStop = na
persist pendSide = 0
persist entryPx  = na
persist stopCur  = na
persist tp1Px    = na
persist tp2Px    = na
persist tp1Done  = false
persist tp2Done  = false

var DD_CAP = ddCapPct / 100.0
var R_ABS  = 1.5              // pire perte simulable (bornes R [-1,5 ; +8])
var SAFE   = 0.999
var FUND_MAX = 0.0005         // funding trop chargé contre l'entrée (0,05 %)
var FUND_MIN = 0.0002         // financement extrême min (A2)
var FUND_CAP = 0.004          // anomalie exclue (A2)

var eq = strategy.equity()
var px = bars.close
var fr = fnd.value

// Ancres temporelles (rythme requis + coupe-circuits).
if (barIndex == 0) {
  t0 = bars.time
  dayT = bars.time
  weekT = bars.time
}
var monthsElapsed = (bars.time - t0) / 2592000000.0        // mois de 30 jours
var pace = 100.0 * math.pow(501.0, monthsElapsed / 12.0)   // rythme x501

// Contrôleur PAT (identique au Monte-Carlo v6).
var dd = peak > 0 ? (peak - eq) / peak : 0.0
var gDD = math.max(0.0, math.min(1.0, (DD_CAP - dd) / (kappa * DD_CAP)))
var gPace = math.max(paceCut, math.min(paceBoost, 1.0 + 0.6 * (1.0 - eq / pace)))
var fAbs = math.max(DD_CAP - dd, 0.0) / ((1.0 - dd) * R_ABS) * SAFE
// Mise PAT PAR ALPHA (allocation G4 ; isAlt sélectionne la jambe satellite
// pour A3/A4 ; A1 ne tourne qu'en main 1h, A2/A6 en mode observation).
var fA1 = math.min(riskMainA1 / 100.0 * gDD * gPace, fAbs)
var fA2 = math.min(riskOther / 100.0 * gDD * gPace, fAbs)
var fA3 = math.min((isAlt ? riskSatA3 : riskMainA3) / 100.0 * gDD * gPace, fAbs)
var fA4 = math.min((isAlt ? riskSatA4 : riskMainA4) / 100.0 * gDD * gPace, fAbs)
var fA6 = math.min(riskOther / 100.0 * gDD * gPace, fAbs)
var fUsed = 0.0

peak = math.max(peak, eq)
lock = lock || eq >= targetEq

// Coupe-circuits jour / semaine (nouvelles entrées seulement).
if (bars.time - dayT >= 86400000) { dayT = bars.time; dayEqA = eq }
if (bars.time - weekT >= 604800000) { weekT = bars.time; weekEqA = eq }
var dayLoss = dayEqA > 0 ? math.max(0.0, (1.0 - eq / dayEqA) * 100.0) : 0.0
var weekLoss = weekEqA > 0 ? math.max(0.0, (1.0 - eq / weekEqA) * 100.0) : 0.0
var breakersOK = dayLoss < dayStop && weekLoss < weekStop

var warmed = barIndex >= warmupBars
var flat = strategy.positionSize() == 0
var inPos = !flat
var canScan = warmed && breakersOK && !lock

// Réinitialisation de l'état quand on est à plat.
if (flat) {
  activeId = ""
  pendStop = na
  pendSide = 0
  entryPx = na
  stopCur = na
  tp1Px = na
  tp2Px = na
  tp1Done = false
  tp2Done = false
}

// ------------------- GESTION DE POSITION (échelle moteur) -------------------
if (inPos && isnum(pendStop) && isna(entryPx)) {
  // Premier barre après le fill (open suivant) : R, TPs et stop réels.
  entryPx = strategy.positionAvgPrice()
  var risk0 = math.abs(entryPx - pendStop)
  tp1Px = entryPx + pendSide * 1.5 * risk0
  tp2Px = entryPx + pendSide * 2.5 * risk0
  stopCur = pendStop
}
var sgn = pendSide
if (inPos && isnum(tp1Px)) {
  if (!tp1Done && ((sgn == 1 && bars.high >= tp1Px) || (sgn == -1 && bars.low <= tp1Px))) {
    tp1Done = true
  }
  if (tp1Done && !tp2Done && ((sgn == 1 && bars.high >= tp2Px) || (sgn == -1 && bars.low <= tp2Px))) {
    tp2Done = true
  }
  // Stop : break-even après TP1, trailing après TP2 (24x1h / 5x4h - marge).
  var stopNow = tp1Done ? entryPx : stopCur
  if (tp2Done) {
    var trail = tfMode == "1h"
                ? (sgn == 1 ? swLo24 * (1.0 - trailBuf / 100.0)
                            : swHi24 * (1.0 + trailBuf / 100.0))
                : (sgn == 1 ? trailLo5 * (1.0 - trailBuf / 100.0)
                            : trailHi5 * (1.0 + trailBuf / 100.0))
    stopNow = sgn == 1 ? math.max(stopNow, trail) : math.min(stopNow, trail)
  }
  stopCur = stopNow
  // Échelle du moteur (50 % / 25 % / 25 % du volume initial). La doc précise
  // que qtyPercent = % de la quantité CIBLÉE (« targeted quantity »), donc
  // TP2 = 25 (et non 50) pour réserver les 25 % finaux au trailing.
  // Chaque jambe n'est réémise que tant qu'elle est utile : TP1 avant son
  // service, TP2 après TP1, SL toujours (leg OCA plafonné au restant).
  if (!tp1Done) {
    strategy.exit("TP1", fromEntry=activeId, qtyPercent=50, limit=tp1Px)
  }
  if (tp1Done && !tp2Done) {
    strategy.exit("TP2", fromEntry=activeId, qtyPercent=25, limit=tp2Px)
  }
  strategy.exit("SL", fromEntry=activeId, qtyPercent=100, stop=stopCur)
}

// ---------------------- SORTIES DÉFENSIVES (par alpha) ----------------------
if (inPos && isnum(entryPx)) {
  var defLong = false
  var defShort = false
  if (activeId == "A1L" || activeId == "A1S") {
    // A1 : retournement du régime D1 (close vs EMA50 D1 confirmée).
    defLong = regime1Dn
    defShort = regime1Up
  } else if (activeId == "A4L" || activeId == "A4S") {
    defLong = st4.direction == -1
    defShort = st4.direction == 1
  } else if (activeId == "A3L" || activeId == "A3S" || activeId == "A6L" || activeId == "A6S") {
    // Éruption avortée / zone 4h perdue.
    defLong = isnum(e4z) && bars.close < e4z
    defShort = isnum(e4z) && bars.close > e4z
  } else if (activeId == "A2L" || activeId == "A2S") {
    defLong = regime1Dn
    defShort = regime1Up
  }
  if (defLong || defShort) {
    strategy.close(activeId)
  }
}

// --------------------------- FILTRE ALTS (BTC) ------------------------------
// Un satellite ne s'ouvre jamais contre le régime D1 de BTC ni en marché
// sans direction. BTC/ETH (isAlt=false) en sont exemptés.
var altOkLong  = !isAlt || (btcRegUp && btcDir)
var altOkShort = !isAlt || (!btcRegUp && btcDir)

// --------------------------- SIZING (PAT) -----------------------------------
// Garde-fous du moteur : distance au stop dans la plage de l'alpha et hors du
// bruit ATR 4h (>= fac x ATR% 4h). qty = risque$/dist, plafonné au levier.
var distGuard = 0.0
var qty = 0.0
var notionalOK = false
// (calculé dans chaque bloc alpha ci-dessous)

// ============================ SIGNAUX — MODE 1h ==============================
var sigFired = false
if (canScan && flat && tfMode == "1h" && useA1 && isnum(cvd) && isnum(cvdSig)
    && isnum(e4z) && isnum(fr)) {
  var cvdUp1 = cvd > cvdSig && cvd[1] <= cvdSig[1]
  var cvdDn1 = cvd < cvdSig && cvd[1] >= cvdSig[1]
  var bull1 = bars.close > bars.open
  var bear1 = bars.close < bars.open
  var rgOK1 = regime4Up && regime1Up && isnum(ndd4) && ndd4 > nddGate4
  var rgS1  = regime4Dn && regime1Dn && isnum(ndd4) && ndd4 > nddGate4
  // --- A1 LONG
  if (!sigFired && rgOK1 && bars.low <= e4z && cvdUp1 && bull1 && fr < FUND_MAX
      && altOkLong) {
    var stopL = swLo24 * (1.0 - stopBuf / 100.0)
    distGuard = (px - stopL) / px * 100.0
    if (distGuard >= 0.6 && distGuard <= 3.0 && isnum(atr4pct)
        && distGuard >= atrStopFac * atr4pct) {
      qty = math.min(eq * fA1 / (px - stopL), eq * levMax / px)
      if (qty * px >= 5.0) {
        notionalOK = true
        fUsed = fA1
        pendStop = stopL
        pendSide = 1
        activeId = "A1L"
        sigFired = true
        strategy.entry("A1L", "long", qty=qty)
      }
    }
  }
  // --- A1 SHORT
  if (!sigFired && rgS1 && bars.high >= e4z && cvdDn1 && bear1 && fr > -FUND_MAX
      && altOkShort) {
    var stopS = swHi24 * (1.0 + stopBuf / 100.0)
    distGuard = (stopS - px) / px * 100.0
    if (distGuard >= 0.6 && distGuard <= 3.0 && isnum(atr4pct)
        && distGuard >= atrStopFac * atr4pct) {
      qty = math.min(eq * fA1 / (stopS - px), eq * levMax / px)
      if (qty * px >= 5.0) {
        notionalOK = true
        fUsed = fA1
        pendStop = stopS
        pendSide = -1
        activeId = "A1S"
        sigFired = true
        strategy.entry("A1S", "short", qty=qty)
      }
    }
  }
}

// ============================ SIGNAUX — MODE 4h ==============================
if (canScan && flat && tfMode == "4h" && isnum(cvd) && isnum(cvdSig)
    && isnum(e4z) && isnum(fr)) {
  var cvdUp = cvd > cvdSig && cvd[1] <= cvdSig[1]
  var cvdDn = cvd < cvdSig && cvd[1] >= cvdSig[1]
  var bull = bars.close > bars.open
  var bear = bars.close < bars.open

  // ---- A2 « Cascade & Financement » (premium) ----
  if (!sigFired && useA2 && isnum(rsi4) && isnum(purgeLo) && isnum(purgeHi)
      && isnum(d1.close)) {
    var fundExtNeg = fr >= -FUND_CAP && fr <= -FUND_MIN
    var fundExtPos = fr >= FUND_MIN && fr <= FUND_CAP
    // LONG : purge + financement extrêmement négatif + RSI capitulation.
    if (fundExtNeg && rsi4 < 32 && cvdUp && bull && bars.close > d1.close
        && fr < FUND_MAX && altOkLong) {
      var stopA2L = purgeLo * (1.0 - stopBuf / 100.0)
      distGuard = (px - stopA2L) / px * 100.0
      if (distGuard >= 0.6 && distGuard <= 4.0 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA2 / (px - stopA2L), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA2
          pendStop = stopA2L; pendSide = 1; activeId = "A2L"; sigFired = true
          strategy.entry("A2L", "long", qty=qty)
        }
      }
    }
    // SHORT miroir.
    if (!sigFired && fundExtPos && rsi4 > 68 && cvdDn && bear
        && bars.close < d1.close && fr > -FUND_MAX && altOkShort) {
      var stopA2S = purgeHi * (1.0 + stopBuf / 100.0)
      distGuard = (stopA2S - px) / px * 100.0
      if (distGuard >= 0.6 && distGuard <= 4.0 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA2 / (stopA2S - px), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA2
          pendStop = stopA2S; pendSide = -1; activeId = "A2S"; sigFired = true
          strategy.entry("A2S", "short", qty=qty)
        }
      }
    }
  }

  // ---- A3 « Éruption Volatilité » (16 actifs) ----
  if (!sigFired && useA3 && isnum(sqzAge) && isnum(volMa) && volMa > 0
      && isnum(don4.upper) && isnum(don4.lower)) {
    var volOK = bars.volume > 1.5 * volMa
    var eruptUp = bars.close > don4.upper[1]
    var eruptDn = bars.close < don4.lower[1]
    // LONG : squeeze récent + cassure du canal haut + volume + CVD + régime D1.
    if (eruptUp && sqzAge <= 8 && volOK && cvdUp && regime1Up && isnum(ndd4)
        && ndd4 > nddGate4lo && fr < FUND_MAX && altOkLong) {
      var stopA3L = don4.lower * (1.0 - stopBuf / 100.0)
      distGuard = (px - stopA3L) / px * 100.0
      if (distGuard >= 0.8 && distGuard <= 5.0 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA3 / (px - stopA3L), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA3
          pendStop = stopA3L; pendSide = 1; activeId = "A3L"; sigFired = true
          strategy.entry("A3L", "long", qty=qty)
        }
      }
    }
    // SHORT miroir.
    if (!sigFired && eruptDn && sqzAge <= 8 && volOK && cvdDn && regime1Dn
        && isnum(ndd4) && ndd4 > nddGate4lo && fr > -FUND_MAX && altOkShort) {
      var stopA3S = don4.upper * (1.0 + stopBuf / 100.0)
      distGuard = (stopA3S - px) / px * 100.0
      if (distGuard >= 0.8 && distGuard <= 5.0 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA3 / (stopA3S - px), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA3
          pendStop = stopA3S; pendSide = -1; activeId = "A3S"; sigFired = true
          strategy.entry("A3S", "short", qty=qty)
        }
      }
    }
  }

  // ---- A4 « Confluence Multi-Périodes » (premium) ----
  if (!sigFired && useA4 && isnum(sto4.k) && isnum(sto4.d) && isnum(sto4.k[1])
      && isnum(sto4.d[1]) && isnum(swLo6) && isnum(swHi6)) {
    var turnUp = sto4.k[1] <= sto4.d[1] && sto4.k > sto4.d && sto4.d[1] < 30
    var turnDn = sto4.k[1] >= sto4.d[1] && sto4.k < sto4.d && sto4.d[1] > 70
    var pull4L = bars.low <= e4z
    var pull4S = bars.high >= e4z
    // LONG : régime 3 échelles + SuperTrend long + repli zone + stoch qui tourne.
    if (regime4Up && regime1Up && isnum(ndd4) && ndd4 > nddGate4
        && st4.direction == 1 && pull4L && turnUp && cvdUp && fr < FUND_MAX
        && altOkLong) {
      var stopA4L = swLo6 * (1.0 - stopBuf / 100.0)
      distGuard = (px - stopA4L) / px * 100.0
      if (distGuard >= 0.6 && distGuard <= 3.0 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA4 / (px - stopA4L), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA4
          pendStop = stopA4L; pendSide = 1; activeId = "A4L"; sigFired = true
          strategy.entry("A4L", "long", qty=qty)
        }
      }
    }
    // SHORT miroir.
    if (!sigFired && regime4Dn && regime1Dn && isnum(ndd4) && ndd4 > nddGate4
        && st4.direction == -1 && pull4S && turnDn && cvdDn && fr > -FUND_MAX
        && altOkShort) {
      var stopA4S = swHi6 * (1.0 + stopBuf / 100.0)
      distGuard = (stopA4S - px) / px * 100.0
      if (distGuard >= 0.6 && distGuard <= 3.0 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA4 / (stopA4S - px), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA4
          pendStop = stopA4S; pendSide = -1; activeId = "A4S"; sigFired = true
          strategy.entry("A4S", "short", qty=qty)
        }
      }
    }
  }

  // ---- A6 « Re-ignition » (16 actifs) ----
  if (!sigFired && useA6 && isnum(volMa) && volMa > 0 && isnum(swLo6)
      && isnum(swHi6) && isnum(atr4pct) && barIndex >= 4) {
    var volOK6 = bars.volume > 1.5 * volMa
    var nddRising = isnum(ndd4) && isnum(ndd4[2]) && ndd4 > ndd4[2]
    // Repli récent : une clôture 4h des 3 barres précédentes a traversé la zone.
    var pull6L = (isnum(c4[1]) && isnum(e4z[1]) && c4[1] < e4z[1])
                 || (isnum(c4[2]) && isnum(e4z[2]) && c4[2] < e4z[2])
                 || (isnum(c4[3]) && isnum(e4z[3]) && c4[3] < e4z[3])
    var pull6S = (isnum(c4[1]) && isnum(e4z[1]) && c4[1] > e4z[1])
                 || (isnum(c4[2]) && isnum(e4z[2]) && c4[2] > e4z[2])
                 || (isnum(c4[3]) && isnum(e4z[3]) && c4[3] > e4z[3])
    var marg6 = 0.15 * atr4pct / 100.0
    // LONG : ré-ignition au-dessus du plus haut 4h précédent (marge ATR).
    if (regime1Up && regime4Up && isnum(ndd4) && ndd4 > nddGate4hi
        && st4.direction == 1 && c4 > h4hi[1] * (1.0 + marg6) && pull6L
        && volOK6 && nddRising && cvdUp && bull && fr < FUND_MAX && altOkLong) {
      var stopA6L = swLo6 * (1.0 - stopBuf / 100.0)
      distGuard = (px - stopA6L) / px * 100.0
      if (distGuard >= 0.6 && distGuard <= 3.5 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA6 / (px - stopA6L), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA6
          pendStop = stopA6L; pendSide = 1; activeId = "A6L"; sigFired = true
          strategy.entry("A6L", "long", qty=qty)
        }
      }
    }
    // SHORT miroir.
    if (!sigFired && regime1Dn && regime4Dn && isnum(ndd4) && ndd4 > nddGate4hi
        && st4.direction == -1 && c4 < h4lo[1] * (1.0 - marg6) && pull6S
        && volOK6 && nddRising && cvdDn && bear && fr > -FUND_MAX && altOkShort) {
      var stopA6S = swHi6 * (1.0 + stopBuf / 100.0)
      distGuard = (stopA6S - px) / px * 100.0
      if (distGuard >= 0.6 && distGuard <= 3.5 && isnum(atr4pct)
          && distGuard >= atrStopFac * atr4pct) {
        qty = math.min(eq * fA6 / (stopA6S - px), eq * levMax / px)
        if (qty * px >= 5.0) {
          fUsed = fA6
          pendStop = stopA6S; pendSide = -1; activeId = "A6S"; sigFired = true
          strategy.entry("A6S", "short", qty=qty)
        }
      }
    }
  }
}

// --------------------------- VERROU DE MISSION ------------------------------
if (lock && !flat) {
  strategy.closeAll()
}

// --------------------- ALERTES (niveau racine, idiome officiel) ------------
// Déclencheurs « alert() triggers » du menu Alertes : un message par signal
// (alpha, sens, stop, f% PAT) + un message de fin de mission.
alert(message=format("x501 {0} {1} @ {2} | stop {3} | f={4}%",
                     activeId, currentSymbol, px, pendStop, fUsed * 100.0),
      condition=sigFired)
alert(message=format("x501 MISSION ACCOMPLIE : {0} $ — trading arrêté (verrou)",
                     eq),
      condition=lock && eq >= targetEq)
alertcondition(sigFired && pendSide == 1, "x501 Signal LONG",
               "x501 : signal long détecté")
alertcondition(sigFired && pendSide == -1, "x501 Signal SHORT",
               "x501 : signal short détecté")

// -------------------------------- PLOTS -------------------------------------
plotLine(value=e4z, width=1, colors=["#2d7ab3"], label=["Zone EMA21 4h"],
         desc=["Zone de repli 4h (alphas v5)"])
plotLine(value=e1t, width=1, colors=["#8a5fbf"], label=["EMA50 D1"],
         desc=["Régime quotidien confirmé (no-repaint)"])
plotShape(value=sigFired && pendSide == 1 ? bars.low : na, shape="triangle",
          location="belowBar", colors=["#16a34a"], width=3, label=["Signal long"],
          desc=["Signal alpha x501"])
plotShape(value=sigFired && pendSide == -1 ? bars.high : na, shape="triangle",
          location="aboveBar", colors=["#dc2626"], width=3, label=["Signal short"],
          desc=["Signal alpha x501"])
