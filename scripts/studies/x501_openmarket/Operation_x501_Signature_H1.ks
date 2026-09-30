//@version=3
// ============================================================================
// OPÉRATION x501 — SETUP SIGNATURE « CONTINUATION DE TENDANCE + FLUX »
// Version H1 — à exécuter sur un CHART 1h (ex. BINANCE_FUTURES:BTCUSDT)
// ============================================================================
// Logique (chapitre 4 du plan) :
//   1. Structure   : tendance établie — close > EMA50 H4 ET close > EMA50 D1
//                    (inversé pour les shorts) + force ADX H4 >= seuil
//   2. Zone H4     : repli du prix dans l'EMA21 H4 (support dynamique),
//                    avec purge de liquidations récente (confluence cluster)
//   3. Déclencheur : CVD (delta cumulé USD) croise au-dessus de son EMA
//                    pendant une bougie haussière = absorption des vendeurs
//   4. Stop        : sous le swing bas récent, marge de sécurité au-delà des
//                    chiffres ronds, distance encadrée (min/max %)
//   5. Sizing      : Taille = Risque($) / Distance au stop  (chapitre 5),
//                    plafonnée par le levier effectif max
//   6. Sorties     : TP1 à 1,5R (moitié, stop à BE) — TP2 à 2,5R (quart) —
//                    runner sous les plus bas récents (trail)
//   7. Filtres     : funding extrême contre la position = pas d'entrée
//   8. Coupe-circuits : -8% (jour), -15% (semaine), -25% (absolu, arrêt)
// ----------------------------------------------------------------------------
// FRAIS : maker 0,018% / taker 0,045% (Binance VIP0), slippage 2 bps,
//         funding réel ("data"), marge isolée, levier nominal 10x.
//         Le levier nominal ne fait que libérer de la marge : le risque réel
//         vient de la formule de sizing, jamais du curseur de levier.
// ----------------------------------------------------------------------------
// DOCUMENT ÉDUCATIF — ne constitue pas un conseil en investissement.
// ============================================================================

strategy(title="Operation x501 - Swing Signature (H1)", position="onchart", axis=true,
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

// Groupe Structure & zone (D1/H4)
var h4TrendLen   = input(name="h4TrendLen", type="int", defaultValue=50, label="EMA tendance H4",            constraints={min: 10, max: 200, step: 1}, group="Structure & zone");
var d1TrendLen   = input(name="d1TrendLen", type="int", defaultValue=50, label="EMA tendance D1",            constraints={min: 10, max: 200, step: 1}, group="Structure & zone");
var zoneLen      = input(name="zoneLen", type="int", defaultValue=21,   label="EMA zone H4 (repli)",        constraints={min: 5, max: 100, step: 1}, group="Structure & zone");
var adxMin       = input(name="adxMin", type="number", defaultValue=18,  label="ADX H4 min",                 constraints={min: 5, max: 40, step: 1}, group="Structure & zone");
var pullbackWin  = input(name="pullbackWin", type="int", defaultValue=24, label="Fenêtre swing (barres)",     constraints={min: 5, max: 96, step: 1}, group="Structure & zone");
var stopBufPct   = input(name="stopBufPct", type="number", defaultValue=0.35, label="Marge sous le swing (%)",  constraints={min: 0.05, max: 2, step: 0.05}, group="Structure & zone");

// Groupe Flux & déclencheur (H1)
var cvdEmaLen    = input(name="cvdEmaLen", type="int", defaultValue=21,  label="EMA du CVD",                 constraints={min: 5, max: 100, step: 1}, group="Flux & déclencheur");
var liqMaLen     = input(name="liqMaLen", type="int", defaultValue=168,  label="Moyenne liquidations (barres)", constraints={min: 24, max: 720, step: 24}, group="Flux & déclencheur");
var liqMult      = input(name="liqMult", type="number", defaultValue=4,   label="Seuil purge (x moyenne)",    constraints={min: 1.5, max: 10, step: 0.5}, group="Flux & déclencheur");
var flushAgeMax  = input(name="flushAgeMax", type="int", defaultValue=24, label="Purge valable N barres",     constraints={min: 0, max: 96, step: 1}, group="Flux & déclencheur");
var requireFlush = input(name="requireFlush", type="boolean", defaultValue=true, label="Exiger la purge de liquidations", group="Flux & déclencheur");
var fundMax      = input(name="fundMax", type="number", defaultValue=0.0005, label="Funding max (0,0005 = 0,05 %)", constraints={min: 0, max: 0.002, step: 0.0001}, group="Flux & déclencheur");

// Groupe Gestion & sorties
var tp1R         = input(name="tp1R", type="number", defaultValue=1.5,  label="TP1 (R)",                    constraints={min: 0.5, max: 5, step: 0.25}, group="Gestion & sorties");
var tp2R         = input(name="tp2R", type="number", defaultValue=2.5,  label="TP2 (R)",                    constraints={min: 1, max: 8, step: 0.25}, group="Gestion & sorties");
var tp1Pct       = input(name="tp1Pct", type="number", defaultValue=50, label="TP1 : % de la position",     constraints={min: 10, max: 90, step: 5}, group="Gestion & sorties");
var tp2Pct       = input(name="tp2Pct", type="number", defaultValue=25, label="TP2 : % de la position",     constraints={min: 5, max: 50, step: 5}, group="Gestion & sorties");
var trailLen     = input(name="trailLen", type="int", defaultValue=24,   label="Trail : fenêtre swing (barres)", constraints={min: 6, max: 96, step: 1}, group="Gestion & sorties");
var trailBufPct  = input(name="trailBufPct", type="number", defaultValue=0.5, label="Trail : marge (%)",       constraints={min: 0, max: 3, step: 0.1}, group="Gestion & sorties");
var useTrendExit = input(name="useTrendExit", type="boolean", defaultValue=true, label="Sortie si retournement D1", group="Gestion & sorties");

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
timeseries liq   = source("liquidations", symbol=currentSymbol, exchange=currentExchange);

// Timeframes supérieurs CONFIRMÉS (sans repaint) : H4 pour la zone, D1 pour le régime
timeseries h4    = htf(source=trade, timeframe="4h");
timeseries d1    = htf(source=trade, timeframe="1D");

// ---------------------------- INDICATEURS -----------------------------------
timeseries emaH4Trend = ema(source=h4.close, period=h4TrendLen);
timeseries emaH4Zone  = ema(source=h4.close, period=zoneLen);
timeseries emaD1Trend = ema(source=d1.close, period=d1TrendLen);
[adxH4, diPlusH4, diMinusH4] = adx(source=h4, period=14);

timeseries liqTotal = liq.buy + liq.sell;
var liqMa = sma(source=liqTotal, period=liqMaLen);

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
persist flushAge   = 9999; // barres depuis la dernière purge de liquidations
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
// 1. Régime : tendance H4 + D1 alignées, force de tendance suffisante
var regimeLong  = h4.close > emaH4Trend && d1.close > emaD1Trend && adxH4 > adxMin;
var regimeShort = h4.close < emaH4Trend && d1.close < emaD1Trend && adxH4 > adxMin;

// 2. Zone de repli H4 : le prix revient toucher l'EMA21 H4
var zoneTouchLong  = trade.low <= emaH4Zone;
var zoneTouchShort = trade.high >= emaH4Zone;

// Confluence cluster de liquidations : purge récente (le levier des autres
// s'est fait purger dans la zone — proxy kScript de la carte des liquidations)
var flushNow = 0;
if (!isna(liqMa) && liqTotal > liqMult * liqMa) {
  flushNow = 1;
}
if (flushNow == 1) {
  flushAge = 0;
} else {
  flushAge = flushAge + 1;
}
var flushOk = flushAge <= flushAgeMax;
var confluenceOk = requireFlush == false || flushOk;

// 3. Déclencheur H1 : le CVD se retourne dans le sens du trade, bougie d'appui
var cvdUp    = crossover(cvd, cvdEma);
var cvdDown  = crossunder(cvd, cvdEma);
var bullBar  = trade.close > trade.open;
var bearBar  = trade.close < trade.open;

// Filtre funding : un financement extrême contre la position annule l'edge
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

  // Retournement de structure D1 contre la position : sortie défensive
  if (useTrendExit == true && side == 1 && d1.close < emaD1Trend) {
    strategy.closeAll(comment="Retournement D1");
  }
  if (useTrendExit == true && side == -1 && d1.close > emaD1Trend) {
    strategy.closeAll(comment="Retournement D1");
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
// LONG : tendance haussière + repli dans la zone H4 + purge récente +
//        CVD qui se retourne à la hausse sur bougie haussière
var longSignal = flat && regimeLong && zoneTouchLong && confluenceOk &&
    cvdUp && bullBar && fundingOkLong && breakersOk;
var shortSignal = flat && regimeShort && zoneTouchShort && confluenceOk &&
    cvdDown && bearBar && fundingOkShort && breakersOk && allowShorts == true;

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
      strategy.entry("L", "long", qty=qtyL, comment="x501 long");
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
      strategy.entry("S", "short", qty=qtyS, comment="x501 short");
    }
  }
}

// ------------------------------- AFFICHAGE ----------------------------------
plotLine(value=emaH4Trend, width=2, colors=["#2d7ab3"], label=["EMA H4 50"], desc=["Régime de tendance H4"]);
plotLine(value=emaH4Zone, width=1, colors=["#7fb3d9"], label=["EMA H4 21"], desc=["Zone de repli H4"]);
plotLine(value=emaD1Trend, width=2, colors=["#0a1628"], label=["EMA D1 50"], desc=["Régime de tendance D1"]);

var longMk  = longSignal ? trade.low : na;
var shortMk = shortSignal ? trade.high : na;
var flushMk = flushNow == 1 ? trade.low : na;
plotShape(value=longMk, shape="triangle", width=10, colors=["#16a34a"], label=["Long"], desc=["Signal long x501"]);
plotShape(value=shortMk, shape="triangle", width=10, colors=["#dc2626"], label=["Short"], desc=["Signal short x501"]);
plotShape(value=flushMk, shape="circle", width=7, colors=["#f59e0b"], label=["Purge"], desc=["Purge de liquidations (confluence)"]);
