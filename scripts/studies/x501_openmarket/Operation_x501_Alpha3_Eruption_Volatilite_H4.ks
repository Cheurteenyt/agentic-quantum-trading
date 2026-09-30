//@version=3
// ============================================================================
// OPÉRATION x501 — ALPHA 3 « ÉRUPTION DE VOLATILITÉ » (breakout perps)
// Version H4 — à exécuter sur un CHART 4h (ex. BINANCE_FUTURES:ETHUSDT)
// ============================================================================
// RÔLE DANS LE MOTEUR MULTI-ALPHA (programme 12 mois) :
//   La volatilité crypto est cyclique : compression -> éruption -> expansion.
//   L'Alpha 3 exploite la transition squeeze -> éruption, le régime où les
//   mouvements sont les plus directs (faible contre-mouvement, R le plus
//   élevé). Il complète la Signature (continuation) et l'Alpha 2 (cascade).
//
// Logique (breakout sur expansion) :
//   1. Compression   : largeur de Bollinger < squeezeFac % de sa propre
//                      moyenne sur squeezeLen barres = marché comprimé
//   2. Mémoire       : une compression doit être survenue réellement
//                      (barssince <= squeezeAgeMax)
//   3. Éruption      : close franchit le canal de breakLen barres précédent
//                      (plus haut / plus bas exclu de la bougie courante)
//   4. Confirmation  : volume > volMult x sa moyenne + CVD dans le sens +
//                      régime D1 aligné + force ADX suffisante
//   5. Financement   : funding extrême contre la position = pas d'entrée
//   6. Stop          : au-delà du bord opposé du canal, marge complémentaire,
//                      distance encadrée (min/max %)
//   7. Sizing        : Taille = Risque($) / Distance au stop, plafonnée par
//                      le levier effectif max (chapitre 5 du plan)
//   8. Sorties       : TP1 à 1,5R (moitié, stop à BE) — TP2 à 2,5R (quart) —
//                      runner sous les extrêmes récents (trail)
//   9. Sortie défensive : clôture qui repasse sous/sur l'EMA21 4h = l'éruption
//                      a échoué, on sort avant le stop
//  10. Coupe-circuits : -8% (jour), -15% (semaine), -25% (absolu, arrêt)
// ----------------------------------------------------------------------------
// FRAIS : maker 0,018% / taker 0,045% (Binance VIP0), slippage 2 bps,
//         funding réel ("data"), marge isolée, levier nominal 10x.
// ----------------------------------------------------------------------------
// DOCUMENT ÉDUCATIF — ne constitue pas un conseil en investissement.
// ============================================================================

strategy(title="Operation x501 - Alpha 3 Eruption de Volatilite (H4)", position="onchart", axis=true,
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
var minStopPct   = input(name="minStopPct", type="number", defaultValue=0.8, label="Stop min (% du prix)",       constraints={min: 0.2, max: 5, step: 0.1}, group="Risque & palier");
var maxStopPct   = input(name="maxStopPct", type="number", defaultValue=5,   label="Stop max (% du prix)",       constraints={min: 0.5, max: 10, step: 0.25}, group="Risque & palier");
var minNotional  = input(name="minNotional", type="number", defaultValue=5,  label="Notionnel min (USD)",        constraints={min: 1, max: 100, step: 1}, group="Risque & palier");

// Groupe Squeeze & canal
var bbLen        = input(name="bbLen", type="int", defaultValue=20,       label="Bollinger : période",         constraints={min: 10, max: 60, step: 1}, group="Squeeze & canal");
var bbMult       = input(name="bbMult", type="number", defaultValue=2,    label="Bollinger : multiplicateur",  constraints={min: 1, max: 4, step: 0.25}, group="Squeeze & canal");
var squeezeLen   = input(name="squeezeLen", type="int", defaultValue=30,   label="Moyenne de la largeur BB",    constraints={min: 10, max: 120, step: 5}, group="Squeeze & canal");
var squeezeFac   = input(name="squeezeFac", type="number", defaultValue=60, label="Squeeze : % de la largeur moyenne", constraints={min: 20, max: 95, step: 5}, group="Squeeze & canal");
var squeezeAgeMax= input(name="squeezeAgeMax", type="int", defaultValue=8,  label="Compression valable N barres", constraints={min: 1, max: 30, step: 1}, group="Squeeze & canal");
var breakLen     = input(name="breakLen", type="int", defaultValue=20,     label="Canal d'éruption (barres)",   constraints={min: 8, max: 60, step: 1}, group="Squeeze & canal");

// Groupe Volume & flux
var volMaLen     = input(name="volMaLen", type="int", defaultValue=30,     label="Moyenne du volume (barres)",  constraints={min: 5, max: 120, step: 5}, group="Volume & flux");
var volMult      = input(name="volMult", type="number", defaultValue=1.5,  label="Volume : x moyenne",          constraints={min: 1, max: 5, step: 0.25}, group="Volume & flux");
var cvdEmaLen    = input(name="cvdEmaLen", type="int", defaultValue=14,    label="EMA du CVD",                  constraints={min: 5, max: 100, step: 1}, group="Volume & flux");
var fundMax      = input(name="fundMax", type="number", defaultValue=0.0005, label="Funding max (0,05 %)",      constraints={min: 0, max: 0.002, step: 0.0001}, group="Volume & flux");

// Groupe Régime
var d1TrendLen   = input(name="d1TrendLen", type="int", defaultValue=50,   label="EMA tendance D1",             constraints={min: 10, max: 200, step: 1}, group="Régime");
var zoneLen      = input(name="zoneLen", type="int", defaultValue=21,      label="EMA défensive 4h",            constraints={min: 5, max: 100, step: 1}, group="Régime");
var adxMin       = input(name="adxMin", type="number", defaultValue=15,   label="ADX 4h min",                  constraints={min: 5, max: 40, step: 1}, group="Régime");
var stopBufPct   = input(name="stopBufPct", type="number", defaultValue=0.35, label="Marge au-delà du canal (%)", constraints={min: 0.05, max: 2, step: 0.05}, group="Régime");

// Groupe Gestion & sorties
var tp1R         = input(name="tp1R", type="number", defaultValue=1.5,  label="TP1 (R)",                    constraints={min: 0.5, max: 5, step: 0.25}, group="Gestion & sorties");
var tp2R         = input(name="tp2R", type="number", defaultValue=2.5,  label="TP2 (R)",                    constraints={min: 1, max: 8, step: 0.25}, group="Gestion & sorties");
var tp1Pct       = input(name="tp1Pct", type="number", defaultValue=50, label="TP1 : % de la position",     constraints={min: 10, max: 90, step: 5}, group="Gestion & sorties");
var tp2Pct       = input(name="tp2Pct", type="number", defaultValue=25, label="TP2 : % de la position",     constraints={min: 5, max: 50, step: 5}, group="Gestion & sorties");
var trailLen     = input(name="trailLen", type="int", defaultValue=5,    label="Trail : fenêtre swing (barres)", constraints={min: 3, max: 24, step: 1}, group="Gestion & sorties");
var trailBufPct  = input(name="trailBufPct", type="number", defaultValue=0.5, label="Trail : marge (%)",       constraints={min: 0, max: 3, step: 0.1}, group="Gestion & sorties");
var useZoneExit  = input(name="useZoneExit", type="boolean", defaultValue=true, label="Sortie si retour sous EMA21", group="Gestion & sorties");

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

// D1 CONFIRMÉ (sans repaint) pour le régime de tendance
timeseries d1    = htf(source=trade, timeframe="1D");

// ---------------------------- INDICATEURS -----------------------------------
var bands = bb(source=trade.close, period=bbLen, mult=bbMult);
timeseries bbWidth = (bands.upper - bands.lower) / bands.basis;
var bbMa = sma(source=bbWidth, period=squeezeLen);

var donHi = highest(source=trade.high, period=breakLen);
var donLo = lowest(source=trade.low, period=breakLen);

var volMa = sma(source=trade.volume, period=volMaLen);

timeseries netFlow = bsv.buy - bsv.sell;
timeseries cvd     = cum(netFlow);
timeseries cvdEma  = ema(source=cvd, period=cvdEmaLen);

timeseries emaD1Trend = ema(source=d1.close, period=d1TrendLen);
timeseries emaZone    = ema(source=trade.close, period=zoneLen);
[adxH4, diPlusH4, diMinusH4] = adx(source=trade, period=14);

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
// 1. Compression : largeur de Bollinger sous x % de sa propre moyenne
var squeezeNow = !isna(bbMa) && bbWidth < bbMa * squeezeFac / 100;

// 2. Mémoire : la compression doit dater d'au plus N barres
var squeezeRecent = barssince(squeezeNow) <= squeezeAgeMax;

// 3. Éruption : franchissement du canal précédent (bougie courante exclue)
var eruptUp   = trade.close > donHi[1];
var eruptDown = trade.close < donLo[1];

// 4. Confirmations
var volOk  = trade.volume > volMult * volMa;
var cvdOkL = cvd > cvdEma;
var cvdOkS = cvd < cvdEma;
var regimeLong  = trade.close > emaD1Trend;
var regimeShort = trade.close < emaD1Trend;
var adxOk  = adxH4 > adxMin;

// 5. Filtre funding : un financement extrême contre la position annule l'edge
var fundingOkLong  = fund.value < fundMax;
var fundingOkShort = fund.value > -fundMax;

// Verrous d'entrée
var breakersOk = halted == 0 && dayLossPct < dailyStop && weekLossPct < weeklyStop;

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

  // Éruption avortée : la clôture repasse de l'autre côté de l'EMA21 4h
  if (useZoneExit == true && side == 1 && trade.close < emaZone) {
    strategy.closeAll(comment="Éruption avortée");
  }
  if (useZoneExit == true && side == -1 && trade.close > emaZone) {
    strategy.closeAll(comment="Éruption avortée");
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
// LONG : compression récente + clôture au-dessus du canal + volume et CVD
//        confirmants + régime D1 haussier
var longSignal = flat && eruptUp && squeezeRecent && volOk && cvdOkL &&
    regimeLong && adxOk && fundingOkLong && breakersOk;
var shortSignal = flat && eruptDown && squeezeRecent && volOk && cvdOkS &&
    regimeShort && adxOk && fundingOkShort && breakersOk && allowShorts == true;

if (longSignal) {
  var stopL  = donLo * (1 - stopBufPct / 100);
  var distL  = trade.close - stopL;
  var distLpct = distL / trade.close * 100;
  if (distLpct >= minStopPct && distLpct <= maxStopPct) {
    var riskUsdL = eq * riskPct / 100;
    var qtyL = math.min(riskUsdL / distL, eq * maxEffLev / trade.close);
    if (qtyL * trade.close >= minNotional) {
      planQty = qtyL;
      planStop = stopL;
      side = 1;
      strategy.entry("L", "long", qty=qtyL, comment="x501 A3 long");
    }
  }
}
if (shortSignal) {
  var stopS  = donHi * (1 + stopBufPct / 100);
  var distS  = stopS - trade.close;
  var distSpct = distS / trade.close * 100;
  if (distSpct >= minStopPct && distSpct <= maxStopPct) {
    var riskUsdS = eq * riskPct / 100;
    var qtyS = math.min(riskUsdS / distS, eq * maxEffLev / trade.close);
    if (qtyS * trade.close >= minNotional) {
      planQty = qtyS;
      planStop = stopS;
      side = -1;
      strategy.entry("S", "short", qty=qtyS, comment="x501 A3 short");
    }
  }
}

// ------------------------------- AFFICHAGE ----------------------------------
plotLine(value=emaD1Trend, width=2, colors=["#0a1628"], label=["EMA D1 50"], desc=["Régime de tendance D1"]);
plotLine(value=emaZone, width=1, colors=["#7fb3d9"], label=["EMA 4h 21"], desc=["Zone défensive 4h"]);

var longMk  = longSignal ? trade.low : na;
var shortMk = shortSignal ? trade.high : na;
var sqzMk   = squeezeNow ? trade.high : na;
plotShape(value=longMk, shape="triangle", width=10, colors=["#16a34a"], label=["A3 Long"], desc=["Alpha 3 : éruption haussière"]);
plotShape(value=shortMk, shape="triangle", width=10, colors=["#dc2626"], label=["A3 Short"], desc=["Alpha 3 : éruption baissière"]);
plotShape(value=sqzMk, shape="diamond", width=7, colors=["#f59e0b"], label=["Squeeze"], desc=["Compression de volatilité"]);
