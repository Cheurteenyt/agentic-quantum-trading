//@version=3
// ============================================================================
// OPÉRATION x501 — ALPHA 4 « CONFLUENCE MULTI-PÉRIODES » (tendance profonde)
// Version H4 — à exécuter sur un CHART 4h (ex. BINANCE_FUTURES:BTCUSDT)
// ============================================================================
// RÔLE DANS LE MOTEUR MULTI-ALPHA (programme 12 mois) :
//   L'Alpha 1 (Signature) exige une purge de liquidations pour entrer : il
//   rate les tendances propres qui replient sans cascade. L'Alpha 4 couvre ce
//   trou : pullback dans une tendance confirmée par TROIS horizons (D1, H4,
//   oscillateur H4) et par l'open interest — sans condition de purge.
//
// Logique (confluence 3 horizons) :
//   1. Horizon D1    : close > EMA50 D1 (régime de fond haussier, inversé
//                      pour les shorts)
//   2. Horizon H4    : SuperTrend directionnel (st.direction = +/-1) + prix
//                      au-dessus/dessous de l'EMA50 4h + force ADX >= seuil
//   3. Zone          : repli du prix dans l'EMA21 4h (support dynamique)
//   4. Déclencheur   : stochastique 4h qui sort de survente (k croise d sous
//                      le seuil) = reprise du trend après respiration
//   5. Open interest : OI au-dessus de sa moyenne = nouvelles positions dans
//                      le sens de la tendance (mouvement sain, optionnel)
//   6. Flux          : CVD au-dessus/dessous de son EMA (confirmation)
//   7. Financement   : funding extrême contre la position = pas d'entrée
//   8. Stop          : sous le swing bas récent, marge complémentaire,
//                      distance encadrée (min/max %)
//   9. Sizing        : Taille = Risque($) / Distance au stop, plafonnée par
//                      le levier effectif max (chapitre 5 du plan)
//  10. Sorties       : TP1 à 1,5R (moitié, stop à BE) — TP2 à 2,5R (quart) —
//                      runner sous les extrêmes récents (trail)
//  11. Sortie défensive : flip du SuperTrend 4h contre la position
//  12. Coupe-circuits : -8% (jour), -15% (semaine), -25% (absolu, arrêt)
// ----------------------------------------------------------------------------
// FRAIS : maker 0,018% / taker 0,045% (Binance VIP0), slippage 2 bps,
//         funding réel ("data"), marge isolée, levier nominal 10x.
// ----------------------------------------------------------------------------
// DOCUMENT ÉDUCATIF — ne constitue pas un conseil en investissement.
// ============================================================================

strategy(title="Operation x501 - Alpha 4 Confluence Multi-Periodes (H4)", position="onchart", axis=true,
    initialCapital=100, currency="USD",
    instrument="perps", leverage=10, maintenanceMarginPercent=0.5,
    makerFeePercent=0.018, takerFeePercent=0.045,
    funding="data", onLiquidation="continue",
    slippageBps=2, fillModel="pessimistic",
    qtyType="fixed", qtyValue=1, pyramiding=1);

// ----------------------------- PARAMÈTRES ----------------------------------
// Groupe Risque & palier (chapitre 5)
var riskPct      = input(name="riskPct", type="number", defaultValue=4,    label="Risque par trade (%)",        constraints={min: 0.5, max: 6, step: 0.25}, group="Risque & palier");
var maxEffLev    = input(name="maxEffLev", type="number", defaultValue=10,  label="Levier effectif max",         constraints={min: 1, max: 20, step: 0.5}, group="Risque & palier");
var minStopPct   = input(name="minStopPct", type="number", defaultValue=0.6, label="Stop min (% du prix)",       constraints={min: 0.2, max: 5, step: 0.1}, group="Risque & palier");
var maxStopPct   = input(name="maxStopPct", type="number", defaultValue=3,   label="Stop max (% du prix)",       constraints={min: 0.5, max: 8, step: 0.25}, group="Risque & palier");
var minNotional  = input(name="minNotional", type="number", defaultValue=5,  label="Notionnel min (USD)",        constraints={min: 1, max: 100, step: 1}, group="Risque & palier");

// Groupe Régime & structure
var d1TrendLen   = input(name="d1TrendLen", type="int", defaultValue=50,   label="EMA tendance D1",             constraints={min: 10, max: 200, step: 1}, group="Régime & structure");
var h4TrendLen   = input(name="h4TrendLen", type="int", defaultValue=50,   label="EMA tendance 4h (chart)",     constraints={min: 10, max: 200, step: 1}, group="Régime & structure");
var zoneLen      = input(name="zoneLen", type="int", defaultValue=21,      label="EMA zone 4h (repli)",         constraints={min: 5, max: 100, step: 1}, group="Régime & structure");
var adxMin       = input(name="adxMin", type="number", defaultValue=18,   label="ADX 4h min",                  constraints={min: 5, max: 40, step: 1}, group="Régime & structure");
var pullbackWin  = input(name="pullbackWin", type="int", defaultValue=6,   label="Fenêtre swing (barres)",      constraints={min: 3, max: 48, step: 1}, group="Régime & structure");
var stopBufPct   = input(name="stopBufPct", type="number", defaultValue=0.35, label="Marge sous le swing (%)",  constraints={min: 0.05, max: 2, step: 0.05}, group="Régime & structure");

// Groupe SuperTrend & stochastique
var stFactor     = input(name="stFactor", type="number", defaultValue=3,   label="SuperTrend : facteur ATR",    constraints={min: 1, max: 6, step: 0.25}, group="SuperTrend & stochastique");
var stAtrPeriod  = input(name="stAtrPeriod", type="int", defaultValue=10,  label="SuperTrend : période ATR",    constraints={min: 5, max: 30, step: 1}, group="SuperTrend & stochastique");
var stochK       = input(name="stochK", type="int", defaultValue=14,       label="Stochastique : %K",           constraints={min: 5, max: 40, step: 1}, group="SuperTrend & stochastique");
var stochSm      = input(name="stochSm", type="int", defaultValue=3,        label="Stochastique : lissage %K",   constraints={min: 1, max: 10, step: 1}, group="SuperTrend & stochastique");
var stochD       = input(name="stochD", type="int", defaultValue=3,        label="Stochastique : %D",           constraints={min: 1, max: 10, step: 1}, group="SuperTrend & stochastique");
var stochOs      = input(name="stochOs", type="number", defaultValue=25,  label="Stochastique : zone survente", constraints={min: 5, max: 40, step: 1}, group="SuperTrend & stochastique");
var stochOb      = input(name="stochOb", type="number", defaultValue=75,  label="Stochastique : zone surachat", constraints={min: 60, max: 95, step: 1}, group="SuperTrend & stochastique");

// Groupe Flux & open interest
var oiMaLen      = input(name="oiMaLen", type="int", defaultValue=30,      label="Moyenne open interest (barres)", constraints={min: 5, max: 120, step: 5}, group="Flux & open interest");
var requireOi    = input(name="requireOi", type="boolean", defaultValue=false, label="Exiger OI > moyenne",   group="Flux & open interest");
var cvdEmaLen    = input(name="cvdEmaLen", type="int", defaultValue=14,    label="EMA du CVD",                  constraints={min: 5, max: 100, step: 1}, group="Flux & open interest");
var fundMax      = input(name="fundMax", type="number", defaultValue=0.0005, label="Funding max (0,05 %)",      constraints={min: 0, max: 0.002, step: 0.0001}, group="Flux & open interest");

// Groupe Gestion & sorties
var tp1R         = input(name="tp1R", type="number", defaultValue=1.5,  label="TP1 (R)",                    constraints={min: 0.5, max: 5, step: 0.25}, group="Gestion & sorties");
var tp2R         = input(name="tp2R", type="number", defaultValue=2.5,  label="TP2 (R)",                    constraints={min: 1, max: 8, step: 0.25}, group="Gestion & sorties");
var tp1Pct       = input(name="tp1Pct", type="number", defaultValue=50, label="TP1 : % de la position",     constraints={min: 10, max: 90, step: 5}, group="Gestion & sorties");
var tp2Pct       = input(name="tp2Pct", type="number", defaultValue=25, label="TP2 : % de la position",     constraints={min: 5, max: 50, step: 5}, group="Gestion & sorties");
var trailLen     = input(name="trailLen", type="int", defaultValue=5,    label="Trail : fenêtre swing (barres)", constraints={min: 3, max: 24, step: 1}, group="Gestion & sorties");
var trailBufPct  = input(name="trailBufPct", type="number", defaultValue=0.5, label="Trail : marge (%)",       constraints={min: 0, max: 3, step: 0.1}, group="Gestion & sorties");
var useTrendExit = input(name="useTrendExit", type="boolean", defaultValue=true, label="Sortie si flip SuperTrend", group="Gestion & sorties");

// Groupe Coupe-circuits (chapitre 6)
var killDD       = input(name="killDD", type="number", defaultValue=25,   label="Drawdown absolu max (%)",    constraints={min: 5, max: 50, step: 1}, group="Coupe-circuits");
var dailyStop    = input(name="dailyStop", type="number", defaultValue=8,  label="Perte jour : stop (%)",      constraints={min: 2, max: 25, step: 1}, group="Coupe-circuits");
var weeklyStop   = input(name="weeklyStop", type="number", defaultValue=15, label="Perte semaine : stop (%)",  constraints={min: 5, max: 50, step: 1}, group="Coupe-circuits");

// Groupe Divers
var allowShorts  = input(name="allowShorts", type="boolean", defaultValue=true, label="Autoriser les shorts", group="Divers");

// ------------------------------- SOURCES ------------------------------------
timeseries trade = ohlcv(symbol=currentSymbol, exchange=currentExchange);
timeseries bsv   = buy_sell_volume(symbol=currentSymbol, exchange=currentExchange, currency="USD");
timeseries fund  = source("funding_rate", symbol=currentSymbol, exchange=currentExchange);
timeseries oi    = source("open_interest", symbol=currentSymbol, exchange=currentExchange);

// D1 CONFIRMÉ (sans repaint) pour le régime de fond
timeseries d1    = htf(source=trade, timeframe="1D");

// ---------------------------- INDICATEURS -----------------------------------
// SuperTrend 4h (lit les OHLCV du chart implicitement) : .line = stop suiveur,
// .direction = +1 tendance haussière, -1 tendance baissière
var st   = supertrend(factor=stFactor, atrPeriod=stAtrPeriod);
var stUp = st.direction == 1;
var stDn = st.direction == -1;

[adxH4, diPlusH4, diMinusH4] = adx(source=trade, period=14);
timeseries emaH4Trend = ema(source=trade.close, period=h4TrendLen);
timeseries emaH4Zone  = ema(source=trade.close, period=zoneLen);
timeseries emaD1Trend = ema(source=d1.close, period=d1TrendLen);

var stochR = stoch(periodK=stochK, smoothK=stochSm, periodD=stochD);
var stochTurnUp = crossover(stochR.k, stochR.d) && stochR.d[1] < stochOs;
var stochTurnDn = crossunder(stochR.k, stochR.d) && stochR.d[1] > stochOb;

var oiMa = sma(source=oi.close, period=oiMaLen);
var oiOk = requireOi == false || oi.close > oiMa;

timeseries netFlow = bsv.buy - bsv.sell;
timeseries cvd     = cum(netFlow);
timeseries cvdEma  = ema(source=cvd, period=cvdEmaLen);

// ------------------------- ÉTAT PERSISTANT ----------------------------------
persist peakEq     = 0;   // sommet d'équité (drawdown absolu)
persist halted     = 0;   // 1 = coupe-circuit -25% atteint, plan terminé
persist dayAnchor  = 0;   // horodatage de l'ancre du jour (UTC)
persist dayAnchorEq = 0;  // équité à l'ancre du jour
persist weekAnchor = 0;   // horodatage de l'ancre de la semaine
persist weekAnchorEq = 0; // équité à l'ancre de la semaine
persist side       = 0;   // 1 = long, -1 = short, 0 = plat
persist planQty    = 0;   // taille prévue (unités de base)
persist planStop   = 0;   // prix du stop initial
persist planEntry  = 0;   // prix d'entrée réel (moyenne au remplissage)
persist fillDone   = 0;   // 1 = entrée exécutée et enregistrée
persist tp1Done    = 0;   // 1 = TP1 touché (stop passé à BE)
persist tp2Done    = 0;   // 1 = TP2 touché (runner en trail)
persist trailStop  = 0;   // stop suiveur du runner

// ---------------------- COUPE-CIRCUITS & ÉQUITÉ -----------------------------
var eq = strategy.equity();
if (isFirst) {
  peakEq = eq;
  dayAnchor = time();
  dayAnchorEq = eq;
  weekAnchor = time();
  weekAnchorEq = eq;
}
peakEq = math.max(peakEq, eq);
var ddPct = peakEq > 0 ? (1 - eq / peakEq) * 100 : 0;
if (ddPct >= killDD) {
  halted = 1;
}

// Ancres jour / semaine : perte jour >= 8% ou semaine >= 15% = pas d'entrée
if (time() - dayAnchor >= 86400000) {
  dayAnchor = time();
  dayAnchorEq = eq;
}
var dayLossPct = dayAnchorEq > 0 ? math.max(0, (1 - eq / dayAnchorEq) * 100) : 0;
if (time() - weekAnchor >= 604800000) {
  weekAnchor = time();
  weekAnchorEq = eq;
}
var weekLossPct = weekAnchorEq > 0 ? math.max(0, (1 - eq / weekAnchorEq) * 100) : 0;

// Le -25% absolu ferme tout et met fin au plan (pas de nouvelle entrée)
var flat = strategy.positionSize() == 0;
if (halted == 1 && flat == false) {
  strategy.closeAll(comment="Coupe-circuit -25%");
}

// --------------------------- DÉTECTION SETUP --------------------------------
// 1. Horizons D1 + H4 : régime de fond, direction SuperTrend, force ADX
var regimeLong  = trade.close > emaH4Trend && d1.close > emaD1Trend && adxH4 > adxMin;
var regimeShort = trade.close < emaH4Trend && d1.close < emaD1Trend && adxH4 > adxMin;

// 2. Zone de repli 4h : le prix revient toucher l'EMA21 4h
var zoneTouchLong  = trade.low <= emaH4Zone;
var zoneTouchShort = trade.high >= emaH4Zone;

// 3. Open interest : nouvelles positions dans le sens du mouvement
var oiHealthy = oiOk;

// 4. Flux et financement
var cvdOkL = cvd > cvdEma;
var cvdOkS = cvd < cvdEma;
var fundingOkLong  = fund.value < fundMax;
var fundingOkShort = fund.value > -fundMax;

// Verrous d'entrée
var breakersOk = halted == 0 && dayLossPct < dailyStop && weekLossPct < weeklyStop;

// Niveaux techniques
var swingLow  = lowest(source=trade.low, period=pullbackWin);
var swingHigh = highest(source=trade.high, period=pullbackWin);

// ----------------------- GESTION DE POSITION OUVERTE ------------------------
var entryId = side == 1 ? "L" : "S";
if (flat == false) {
  // Première barre avec position : figer le prix d'entrée réel
  if (fillDone == 0) {
    planEntry = strategy.positionAvgPrice();
    fillDone = 1;
  }
  var riskPx = side == 1 ? planEntry - planStop : planStop - planEntry;
  var tp1Px  = side == 1 ? planEntry + tp1R * riskPx : planEntry - tp1R * riskPx;
  var tp2Px  = side == 1 ? planEntry + tp2R * riskPx : planEntry - tp2R * riskPx;

  // Suivi des paliers touchés
  if (tp1Done == 0 && ((side == 1 && trade.high >= tp1Px) || (side == -1 && trade.low <= tp1Px))) {
    tp1Done = 1;
  }
  if (tp2Done == 0 && ((side == 1 && trade.high >= tp2Px) || (side == -1 && trade.low <= tp2Px))) {
    tp2Done = 1;
  }

  // Stop courant : initial -> BE après TP1 -> trail du runner après TP2
  var stopNow = planStop;
  if (tp1Done == 1) {
    stopNow = planEntry;
  }
  var runPct = 100 - tp1Pct - tp2Pct;
  if (tp2Done == 1) {
    var trailRaw = side == 1 ? lowest(source=trade.low, period=trailLen) * (1 - trailBufPct / 100)
                             : highest(source=trade.high, period=trailLen) * (1 + trailBufPct / 100);
    if (side == 1) {
      trailStop = math.max(stopNow, trailRaw);
    } else {
      trailStop = math.min(stopNow, trailRaw);
    }
    stopNow = trailStop;
  }

  // Bracket : TP1 (moitié) + TP2 (quart) + runner — le stop est commun
  if (tp1Done == 0) {
    strategy.exit("TP1", fromEntry=entryId, qty=planQty * tp1Pct / 100, limit=tp1Px, stop=stopNow);
    strategy.exit("TP2", fromEntry=entryId, qty=planQty * tp2Pct / 100, limit=tp2Px, stop=stopNow);
    strategy.exit("RUN", fromEntry=entryId, qty=planQty * runPct / 100, stop=stopNow);
  }
  if (tp1Done == 1 && tp2Done == 0) {
    strategy.exit("TP2", fromEntry=entryId, qty=planQty * tp2Pct / 100, limit=tp2Px, stop=stopNow);
    strategy.exit("RUN", fromEntry=entryId, qty=planQty * runPct / 100, stop=stopNow);
  }
  if (tp2Done == 1) {
    strategy.exit("RUN", fromEntry=entryId, qty=planQty * runPct / 100, stop=stopNow);
  }

  // Flip du SuperTrend 4h contre la position : sortie défensive
  if (useTrendExit == true && side == 1 && stDn) {
    strategy.closeAll(comment="Flip SuperTrend");
  }
  if (useTrendExit == true && side == -1 && stUp) {
    strategy.closeAll(comment="Flip SuperTrend");
  }
} else {
  // Plat : réinitialisation de l'état du plan
  fillDone = 0;
  tp1Done = 0;
  tp2Done = 0;
  side = 0;
  planQty = 0;
  planStop = 0;
  planEntry = 0;
  trailStop = 0;
}

// ------------------------------- ENTRÉES ------------------------------------
// LONG : confluence D1 haussier + SuperTrend haussier + repli EMA21 +
//        stochastique qui sort de survente + OI sain + CVD haussier
var longSignal = flat && regimeLong && stUp && zoneTouchLong && stochTurnUp &&
    oiHealthy && cvdOkL && fundingOkLong && breakersOk;
var shortSignal = flat && regimeShort && stDn && zoneTouchShort && stochTurnDn &&
    oiHealthy && cvdOkS && fundingOkShort && breakersOk && allowShorts == true;

if (longSignal) {
  var stopL  = swingLow * (1 - stopBufPct / 100);
  var distL  = trade.close - stopL;
  var distLpct = distL / trade.close * 100;
  if (distLpct >= minStopPct && distLpct <= maxStopPct) {
    var riskUsdL = eq * riskPct / 100;
    var qtyL = math.min(riskUsdL / distL, eq * maxEffLev / trade.close);
    if (qtyL * trade.close >= minNotional) {
      planQty = qtyL;
      planStop = stopL;
      side = 1;
      strategy.entry("L", "long", qty=qtyL, comment="x501 A4 long");
    }
  }
}
if (shortSignal) {
  var stopS  = swingHigh * (1 + stopBufPct / 100);
  var distS  = stopS - trade.close;
  var distSpct = distS / trade.close * 100;
  if (distSpct >= minStopPct && distSpct <= maxStopPct) {
    var riskUsdS = eq * riskPct / 100;
    var qtyS = math.min(riskUsdS / distS, eq * maxEffLev / trade.close);
    if (qtyS * trade.close >= minNotional) {
      planQty = qtyS;
      planStop = stopS;
      side = -1;
      strategy.entry("S", "short", qty=qtyS, comment="x501 A4 short");
    }
  }
}

// ------------------------------- AFFICHAGE ----------------------------------
plotLine(value=emaH4Trend, width=2, colors=["#2d7ab3"], label=["EMA 4h 50"], desc=["Régime de tendance 4h"]);
plotLine(value=emaH4Zone, width=1, colors=["#7fb3d9"], label=["EMA 4h 21"], desc=["Zone de repli 4h"]);
plotLine(value=emaD1Trend, width=2, colors=["#0a1628"], label=["EMA D1 50"], desc=["Régime de tendance D1"]);

var longMk  = longSignal ? trade.low : na;
var shortMk = shortSignal ? trade.high : na;
plotShape(value=longMk, shape="triangle", width=10, colors=["#16a34a"], label=["A4 Long"], desc=["Alpha 4 : confluence multi-périodes"]);
plotShape(value=shortMk, shape="triangle", width=10, colors=["#dc2626"], label=["A4 Short"], desc=["Alpha 4 : confluence multi-périodes"]);
