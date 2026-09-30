//@version=3
// ============================================================================
// OPÉRATION x501 — ALPHA 2 « CASCADE & FINANCEMENT » (contrarian perps)
// Version H4 — à exécuter sur un CHART 4h (ex. BINANCE_FUTURES:BTCUSDT)
// ============================================================================
// RÔLE DANS LE MOTEUR MULTI-ALPHA (programme 12 mois) :
//   Alpha 1 (Signature) trade la continuation de tendance. L'Alpha 2 couvre le
//   régime opposé — les cascades de liquidations — afin de porter la cadence
//   du portefeuille vers 20-40 trades/mois (configuration optimale C5).
//
// Logique (contrarian sur excès) :
//   1. Régime de fond : close > EMA50 D1 (longs) / close < EMA50 D1 (shorts)
//   2. Capitulation   : cascade de liquidations — liq.sell (ou liq.buy) >
//                       x N leur moyenne = le camp adverse est purgé
//   3. Financement    : funding extrême contre la foule (<= -fundMin pour un
//                       long) mais sous fundCap (anomalie systémique exclue)
//   4. Oscillateur    : RSI 4h en zone de capitulation (< rsiOs / > rsiOb)
//   5. Déclencheur    : CVD croise dans le sens du trade + bougie d'appui
//   6. Stop           : au-delà de l'extrême de la fenêtre de purge, marge
//                       complémentaire, distance encadrée (min/max %)
//   7. Sizing         : Taille = Risque($) / Distance au stop, plafonnée par
//                       le levier effectif max (chapitre 5 du plan)
//   8. Sorties        : TP1 à 1,5R (moitié, stop à BE) — TP2 à 2,5R (quart) —
//                       runner sous les extrêmes récents (trail)
//   9. Coupe-circuits : -8% (jour), -15% (semaine), -25% (absolu, arrêt)
// ----------------------------------------------------------------------------
// FRAIS : maker 0,018% / taker 0,045% (Binance VIP0), slippage 2 bps,
//         funding réel ("data"), marge isolée, levier nominal 10x.
// ----------------------------------------------------------------------------
// DOCUMENT ÉDUCATIF — ne constitue pas un conseil en investissement.
// ============================================================================

strategy(title="Operation x501 - Alpha 2 Cascade et Financement (H4)", position="onchart", axis=true,
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
var maxStopPct   = input(name="maxStopPct", type="number", defaultValue=4,   label="Stop max (% du prix)",       constraints={min: 0.5, max: 10, step: 0.25}, group="Risque & palier");
var minNotional  = input(name="minNotional", type="number", defaultValue=5,  label="Notionnel min (USD)",        constraints={min: 1, max: 100, step: 1}, group="Risque & palier");

// Groupe Régime & capitulation
var d1TrendLen   = input(name="d1TrendLen", type="int", defaultValue=50, label="EMA tendance D1",             constraints={min: 10, max: 200, step: 1}, group="Régime & capitulation");
var rsiLen       = input(name="rsiLen", type="int", defaultValue=14,      label="RSI 4h : période",            constraints={min: 5, max: 50, step: 1}, group="Régime & capitulation");
var rsiOsLevel   = input(name="rsiOsLevel", type="number", defaultValue=32, label="RSI survente (longs)",      constraints={min: 10, max: 45, step: 1}, group="Régime & capitulation");
var rsiObLevel   = input(name="rsiObLevel", type="number", defaultValue=68, label="RSI surachat (shorts)",     constraints={min: 55, max: 90, step: 1}, group="Régime & capitulation");
var purgeWin     = input(name="purgeWin", type="int", defaultValue=8,     label="Fenêtre extrême purge (barres)", constraints={min: 3, max: 48, step: 1}, group="Régime & capitulation");
var stopBufPct   = input(name="stopBufPct", type="number", defaultValue=0.35, label="Marge au-delà de l'extrême (%)", constraints={min: 0.05, max: 2, step: 0.05}, group="Régime & capitulation");

// Groupe Cascade & financement
var liqMaLen     = input(name="liqMaLen", type="int", defaultValue=42,    label="Moyenne liquidations (barres)", constraints={min: 12, max: 180, step: 6}, group="Cascade & financement");
var liqMult      = input(name="liqMult", type="number", defaultValue=4,   label="Seuil cascade (x moyenne)",   constraints={min: 1.5, max: 10, step: 0.5}, group="Cascade & financement");
var flushAgeMax  = input(name="flushAgeMax", type="int", defaultValue=6,   label="Cascade valable N barres",    constraints={min: 0, max: 24, step: 1}, group="Cascade & financement");
var fundMin      = input(name="fundMin", type="number", defaultValue=0.0002, label="Financement extrême min (0,02 %)", constraints={min: 0, max: 0.002, step: 0.0001}, group="Cascade & financement");
var fundCap      = input(name="fundCap", type="number", defaultValue=0.004, label="Financement anomalie max (0,4 %)", constraints={min: 0.0005, max: 0.01, step: 0.0005}, group="Cascade & financement");

// Groupe Flux & déclencheur
var cvdEmaLen    = input(name="cvdEmaLen", type="int", defaultValue=14,  label="EMA du CVD",                  constraints={min: 5, max: 100, step: 1}, group="Flux & déclencheur");

// Groupe Gestion & sorties
var tp1R         = input(name="tp1R", type="number", defaultValue=1.5,  label="TP1 (R)",                    constraints={min: 0.5, max: 5, step: 0.25}, group="Gestion & sorties");
var tp2R         = input(name="tp2R", type="number", defaultValue=2.5,  label="TP2 (R)",                    constraints={min: 1, max: 8, step: 0.25}, group="Gestion & sorties");
var tp1Pct       = input(name="tp1Pct", type="number", defaultValue=50, label="TP1 : % de la position",     constraints={min: 10, max: 90, step: 5}, group="Gestion & sorties");
var tp2Pct       = input(name="tp2Pct", type="number", defaultValue=25, label="TP2 : % de la position",     constraints={min: 5, max: 50, step: 5}, group="Gestion & sorties");
var trailLen     = input(name="trailLen", type="int", defaultValue=5,    label="Trail : fenêtre swing (barres)", constraints={min: 3, max: 24, step: 1}, group="Gestion & sorties");
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

// D1 CONFIRMÉ (sans repaint) pour le régime de fond
timeseries d1    = htf(source=trade, timeframe="1D");

// ---------------------------- INDICATEURS -----------------------------------
timeseries emaD1Trend = ema(source=d1.close, period=d1TrendLen);
timeseries rsi4h      = rsi(source=trade.close, period=rsiLen);

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
persist flushAge   = 9999; // barres depuis la dernière cascade de liquidations
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
// 1. Cascades de liquidations : le camp adverse est purgé en masse
var flushSell = !isna(liqMa) && liq.sell > liqMult * liqMa;
var flushBuy  = !isna(liqMa) && liq.buy > liqMult * liqMa;
if (flushSell || flushBuy) {
  flushAge = 0;
} else {
  flushAge = flushAge + 1;
}
var flushOk = flushAge <= flushAgeMax;

// 2. Financement extrême contre la foule, mais hors anomalie systémique
var fundExtNeg = fund.value <= -fundMin && fund.value >= -fundCap;
var fundExtPos = fund.value >= fundMin && fund.value <= fundCap;

// 3. Capitulation sur l'oscillateur
var rsiOsOk = rsi4h < rsiOsLevel;
var rsiObOk = rsi4h > rsiObLevel;

// 4. Régime de fond : on achète la peur dans une tendance haussière (et inverse)
var regimeLong  = trade.close > emaD1Trend;
var regimeShort = trade.close < emaD1Trend;

// 5. Déclencheur : le CVD absorbe le camp purgé + bougie d'appui
var cvdUp   = crossover(cvd, cvdEma);
var cvdDown = crossunder(cvd, cvdEma);
var bullBar = trade.close > trade.open;
var bearBar = trade.close < trade.open;

// Verrous d'entrée
var breakersOk = halted == 0 && dayLossPct < dailyStop && weekLossPct < weeklyStop;

// Extrêmes de la fenêtre de purge (référence du stop)
var purgeLow  = lowest(source=trade.low, period=purgeWin);
var purgeHigh = highest(source=trade.high, period=purgeWin);

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

  // Retournement de fond D1 contre la position : sortie défensive
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
// LONG : tendance de fond haussière + cascade de ventes forcées + funding
//        extrême négatif + RSI en capitulation + CVD qui absorbe à la hausse
var longSignal = flat && regimeLong && flushOk && fundExtNeg && rsiOsOk &&
    cvdUp && bullBar && breakersOk;
var shortSignal = flat && regimeShort && flushOk && fundExtPos && rsiObOk &&
    cvdDown && bearBar && breakersOk && allowShorts == true;

if (longSignal) {
  var stopL  = purgeLow * (1 - stopBufPct / 100);
  var distL  = trade.close - stopL;
  var distLpct = distL / trade.close * 100;
  if (distLpct >= minStopPct && distLpct <= maxStopPct) {
    var riskUsdL = eq * riskPct / 100;
    var qtyL = math.min(riskUsdL / distL, eq * maxEffLev / trade.close);
    if (qtyL * trade.close >= minNotional) {
      planQty = qtyL;
      planStop = stopL;
      side = 1;
      strategy.entry("L", "long", qty=qtyL, comment="x501 A2 long");
    }
  }
}
if (shortSignal) {
  var stopS  = purgeHigh * (1 + stopBufPct / 100);
  var distS  = stopS - trade.close;
  var distSpct = distS / trade.close * 100;
  if (distSpct >= minStopPct && distSpct <= maxStopPct) {
    var riskUsdS = eq * riskPct / 100;
    var qtyS = math.min(riskUsdS / distS, eq * maxEffLev / trade.close);
    if (qtyS * trade.close >= minNotional) {
      planQty = qtyS;
      planStop = stopS;
      side = -1;
      strategy.entry("S", "short", qty=qtyS, comment="x501 A2 short");
    }
  }
}

// ------------------------------- AFFICHAGE ----------------------------------
plotLine(value=emaD1Trend, width=2, colors=["#0a1628"], label=["EMA D1 50"], desc=["Régime de fond D1"]);
plotLine(value=liqMa, width=1, colors=["#7fb3d9"], label=["Moy. liquidations"], desc=["Niveau de référence des cascades"]);

var longMk  = longSignal ? trade.low : na;
var shortMk = shortSignal ? trade.high : na;
var flushMk = (flushSell || flushBuy) ? trade.low : na;
plotShape(value=longMk, shape="triangle", width=10, colors=["#16a34a"], label=["A2 Long"], desc=["Alpha 2 : entrée sur cascade"]);
plotShape(value=shortMk, shape="triangle", width=10, colors=["#dc2626"], label=["A2 Short"], desc=["Alpha 2 : entrée sur cascade"]);
plotShape(value=flushMk, shape="circle", width=7, colors=["#f59e0b"], label=["Cascade"], desc=["Cascade de liquidations détectée"]);
