//@version=3
// ============================================================================
// OPÉRATION x501 — ABSORPTION ORDERBOOK NATIVE (VAGUE 2, docs/27)
// Version H1 — à exécuter sur un CHART 1h (ex. BINANCE_FUTURES:BTCUSDT)
// ============================================================================
// LE PATTERN (celui qui a produit l'AL Score d'Aster — WR 81 %, DD 5,4 %) :
//   un mur d'ordres géant apparaît dans le carnet à côté du prix
//   (maxBidAmount / maxAskAmount dans une fenêtre de profondeur serrée),
//   une attaque de takers le frappe (vague de sell ou de buy), le prix
//   TIENT (bougie de reprise, écrasement intrabar contenu) et le flux net
//   bascule dans le sens du mur = les agresseurs ont été ABSORBÉS par un
//   limit buyer/seller institutionnel. Le mur qui tient = soutien.
//
// HYPOTHÈSE PRÉ-ENREGISTRÉE (falsifiable, avant tout backtest) :
//   les entrées « mur + attaque absorbée + reprise de flux » ont un gain
//   médian par trade supérieur à celui des entrées flux seules, à coûts
//   maker/taker réels. Critère de promotion : le pattern ajoute du gain
//   médian sans dégrader le DD ; sinon KILL (même clé que partout).
//
// LES 3 FONCTIONS NATIVES EXPLOITÉES (0 usage dans nos 10 scripts avant
// cette vague — doc functions/orderbook) :
//   maxBidAmount(source=book, depthPct) — le PLUS GROS ordre bid dans la
//     fenêtre de profondeur : la détection de baleine, une ligne.
//   maxAskAmount(source=book, depthPct) — le miroir côté vendeurs.
//   sumBids/sumAsks — la pression de profondeur totale (usage secondaire :
//     le déséquilibre de carnet en filtre de confirmation).
//
// LIMITE CONNUE ET ASSUMÉE (docs/27, honnêteté pré-enregistrée) :
//   la profondeur d'historique orderbook en backtest est limitée (la doc
//   donne ~1 semaine à 1m, des mois à 1h/1d pour la tape par taille). Le
//   backtest du pattern absorption est donc une falsification initiale sur
//   la fenêtre DISPONIBLE — pas une preuve 733 j. La vraie validation = le
//   papier forward (protocole v11) qui compte les murs/signaux en direct.
//
// SOURCES : ohlcv (spine) + orderbook + buy_sell_volume = 3 slots <= 10.
//   L'orderbook est array-celled : on ne lit PAS bids/asks directement,
//   on passe la série aux fonctions natives sumBids/maxBidAmount/etc.
//
// Le squelette (sizing risque fixe, TP1/TP2/runner, coupe-circuits
// -8/-15/-25 %, funding extrême interdit) est la Signature H1 INCHANGÉE :
// la comparabilité entre patterns du domaine est totale.
// ----------------------------------------------------------------------------
// FRAIS : maker 0,018 % / taker 0,045 % (Binance VIP0), slippage 2 bps,
//         funding réel ("data"), marge isolée, levier nominal 10x.
// DOCUMENT ÉDUCATIF — ne constitue pas un conseil en investissement.
// ============================================================================

strategy(title="Operation x501 - Absorption Orderbook (H1)", position="onchart", axis=true,
    initialCapital=100, currency="USD",
    instrument="perps", leverage=10, maintenanceMarginPercent=0.5,
    makerFeePercent=0.018, takerFeePercent=0.045,
    funding="data", onLiquidation="continue",
    slippageBps=2, fillModel="pessimistic",
    qtyType="fixed", qtyValue=1, pyramiding=1);

// ----------------------------- PARAMÈTRES ----------------------------------
// Groupe Risque & palier (identique Signature H1)
var riskPct      = input(name="riskPct", type="number", defaultValue=4,    label="Risque par trade (%)",        constraints={min: 0.5, max: 6, step: 0.25}, group="Risque & palier");
var maxEffLev    = input(name="maxEffLev", type="number", defaultValue=10,  label="Levier effectif max",         constraints={min: 1, max: 20, step: 0.5}, group="Risque & palier");
var minStopPct   = input(name="minStopPct", type="number", defaultValue=0.5, label="Stop min (% du prix)",       constraints={min: 0.2, max: 5, step: 0.1}, group="Risque & palier");
var maxStopPct   = input(name="maxStopPct", type="number", defaultValue=3,   label="Stop max (% du prix)",       constraints={min: 0.5, max: 8, step: 0.25}, group="Risque & palier");
var minNotional  = input(name="minNotional", type="number", defaultValue=5,  label="Notionnel min (USD)",        constraints={min: 1, max: 100, step: 1}, group="Risque & palier");

// Groupe MUR & ABSORPTION (le nouveau bloc de la vague 2)
var wallDepth    = input(name="wallDepth", type="number", defaultValue=1,   label="Profondeur du mur (%)",      constraints={min: 0.5, max: 10, step: 0.5}, group="Mur & absorption");
var wallMult     = input(name="wallMult", type="number", defaultValue=3,   label="Mur : x sa moyenne N barres", constraints={min: 1.5, max: 10, step: 0.5}, group="Mur & absorption");
var wallWin      = input(name="wallWin", type="int", defaultValue=200,     label="Fenêtre de référence du mur", constraints={min: 50, max: 500, step: 10}, group="Mur & absorption");
var atkMult      = input(name="atkMult", type="number", defaultValue=2,   label="Attaque : x volume moyen N", constraints={min: 1.2, max: 6, step: 0.2}, group="Mur & absorption");
var atkWin       = input(name="atkWin", type="int", defaultValue=100,     label="Fenêtre de volume de référence", constraints={min: 24, max: 300, step: 4}, group="Mur & absorption");
var maxDefPct    = input(name="maxDefPct", type="number", defaultValue=0.8, label="Écrasement intrabar max (%)", constraints={min: 0.1, max: 3, step: 0.1}, group="Mur & absorption");
var flowLen      = input(name="flowLen", type="int", defaultValue=6,      label="EMA du flux net (barres)",   constraints={min: 3, max: 24, step: 1}, group="Mur & absorption");
var imbMin       = input(name="imbMin", type="number", defaultValue=1.2,  label="Déséquilibre carnet min",    constraints={min: 1, max: 3, step: 0.1}, group="Mur & absorption");
var wallBufPct   = input(name="wallBufPct", type="number", defaultValue=0.35, label="Marge sous le bas récent (%)", constraints={min: 0.05, max: 2, step: 0.05}, group="Mur & absorption");
var stopWin      = input(name="stopWin", type="int", defaultValue=3,      label="Fenêtre du stop (barres)",   constraints={min: 2, max: 12, step: 1}, group="Mur & absorption");

// Groupe Flux (funding, comme la Signature H1)
var fundMax      = input(name="fundMax", type="number", defaultValue=0.0005, label="Funding max (0,0005 = 0,05 %)", constraints={min: 0, max: 0.002, step: 0.0001}, group="Flux");

// Groupe Gestion & sorties (identique Signature H1)
var tp1R         = input(name="tp1R", type="number", defaultValue=1.5,  label="TP1 (R)",                    constraints={min: 0.5, max: 5, step: 0.25}, group="Gestion & sorties");
var tp2R         = input(name="tp2R", type="number", defaultValue=2.5,  label="TP2 (R)",                    constraints={min: 1, max: 8, step: 0.25}, group="Gestion & sorties");
var tp1Pct       = input(name="tp1Pct", type="number", defaultValue=50, label="TP1 : % de la position",     constraints={min: 10, max: 90, step: 5}, group="Gestion & sorties");
var tp2Pct       = input(name="tp2Pct", type="number", defaultValue=25, label="TP2 : % de la position",     constraints={min: 5, max: 50, step: 5}, group="Gestion & sorties");
var trailLen     = input(name="trailLen", type="int", defaultValue=24,   label="Trail : fenêtre swing (barres)", constraints={min: 6, max: 96, step: 1}, group="Gestion & sorties");
var trailBufPct  = input(name="trailBufPct", type="number", defaultValue=0.5, label="Trail : marge (%)",       constraints={min: 0, max: 3, step: 0.1}, group="Gestion & sorties");
var useTrendExit = input(name="useTrendExit", type="boolean", defaultValue=false, label="Sortie si retournement D1", group="Gestion & sorties");

// Groupe Coupe-circuits (identique Signature H1)
var killDD       = input(name="killDD", type="number", defaultValue=25,   label="Drawdown absolu max (%)",    constraints={min: 5, max: 50, step: 1}, group="Coupe-circuits");
var dailyStop    = input(name="dailyStop", type="number", defaultValue=8,  label="Perte jour : stop (%)",      constraints={min: 2, max: 25, step: 1}, group="Coupe-circuits");
var weeklyStop   = input(name="weeklyStop", type="number", defaultValue=15, label="Perte semaine : stop (%)",  constraints={min: 5, max: 50, step: 1}, group="Coupe-circuits");

// Groupe Divers
var allowShorts  = input(name="allowShorts", type="boolean", defaultValue=true, label="Autoriser les shorts", group="Divers");

// ------------------------------- SOURCES ------------------------------------
timeseries trade = ohlcv(symbol=currentSymbol, exchange=currentExchange);
timeseries book  = source("orderbook", symbol=currentSymbol, exchange=currentExchange);
timeseries bsv   = buy_sell_volume(symbol=currentSymbol, exchange=currentExchange, currency="USD");
timeseries fund  = source("funding_rate", symbol=currentSymbol, exchange=currentExchange);

// Régime D1 confirmé (no-repaint) pour la sortie défensive optionnelle
timeseries d1    = htf(source=trade, timeframe="1D");
timeseries emaD1Ref = ema(source=d1.close, period=50);

// ---------------------------- INDICATEURS -----------------------------------
// Les 4 fonctions natives de la vague 2 — LA détection de baleines
var wallBid  = maxBidAmount(source=book, depthPct=wallDepth);
var wallAsk  = maxAskAmount(source=book, depthPct=wallDepth);
var bidDepth = sumBids(source=book, depthPct=wallDepth);
var askDepth = sumAsks(source=book, depthPct=wallDepth);

// Niveaux typiques des plus gros ordres (le mur = un outlier de son histoire)
var bidTyp = sma(source=wallBid, period=wallWin);
var askTyp = sma(source=wallAsk, period=wallWin);

// Pression de profondeur : le déséquilibre du carnet dans la fenêtre du mur
var imb     = bidDepth / math.max(askDepth, 1e-9);
var imbRev  = askDepth / math.max(bidDepth, 1e-9);

// L'attaque : une vague de takers dans la barre
var sellTyp = sma(source=bsv.sell, period=atkWin);
var buyTyp  = sma(source=bsv.buy, period=atkWin);

// Le flux net bascule (l'absorption se voit dans le delta exécuté)
timeseries netFlow = bsv.buy - bsv.sell;
timeseries flowEma = ema(source=netFlow, period=flowLen);

// ------------------------- ÉTAT PERSISTANT ----------------------------------
persist peakEq     = 0;
persist halted     = 0;
persist dayAnchor  = 0;
persist dayAnchorEq = 0;
persist weekAnchor = 0;
persist weekAnchorEq = 0;
persist side       = 0;
persist planQty    = 0;
persist planStop   = 0;
persist planEntry  = 0;
persist fillDone   = 0;
persist tp1Done    = 0;
persist tp2Done    = 0;
persist trailStop  = 0;

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

var flat = strategy.positionSize() == 0;
if (halted == 1 && flat == false) {
  strategy.closeAll(comment="Coupe-circuit -25%");
}

// --------------------------- DÉTECTION PATTERN ------------------------------
// LONG : un mur bid géant + une attaque vendeuse + le prix tient + le flux
//        net remonte + le carnet est penché côté bid.
var wallBidBig  = wallBid >= wallMult * bidTyp;
var sellAttack  = bsv.sell >= atkMult * sellTyp;
var heldLong    = trade.close >= trade.open &&
    (trade.open - trade.low) / math.max(trade.open, 1e-9) * 100 <= maxDefPct;
var flowLong    = flowEma > 0;
var imbLong     = imb >= imbMin;
var fundingOkL  = fund.value < fundMax;

// SHORT : le miroir — mur ask géant + attaque acheteuse absorbée
var wallAskBig  = wallAsk >= wallMult * askTyp;
var buyAttack   = bsv.buy >= atkMult * buyTyp;
var heldShort   = trade.close <= trade.open &&
    (trade.high - trade.open) / math.max(trade.open, 1e-9) * 100 <= maxDefPct;
var flowShort   = flowEma < 0;
var imbShort    = imbRev >= imbMin;
var fundingOkS  = fund.value > -fundMax;

var breakersOk = halted == 0 && dayLossPct < dailyStop && weekLossPct < weeklyStop;

// Niveaux de stop : le bas/haut récent de la fenêtre courte
var stopLow  = lowest(source=trade.low, period=stopWin);
var stopHigh = highest(source=trade.high, period=stopWin);

// ----------------------- GESTION DE POSITION OUVERTE ------------------------
var entryId = side == 1 ? "LA" : "SA";
if (flat == false) {
  if (fillDone == 0) {
    planEntry = strategy.positionAvgPrice();
    fillDone = 1;
  }
  var riskPx = side == 1 ? planEntry - planStop : planStop - planEntry;
  var tp1Px  = side == 1 ? planEntry + tp1R * riskPx : planEntry - tp1R * riskPx;
  var tp2Px  = side == 1 ? planEntry + tp2R * riskPx : planEntry - tp2R * riskPx;

  if (tp1Done == 0 && ((side == 1 && trade.high >= tp1Px) || (side == -1 && trade.low <= tp1Px))) {
    tp1Done = 1;
  }
  if (tp2Done == 0 && ((side == 1 && trade.high >= tp2Px) || (side == -1 && trade.low <= tp2Px))) {
    tp2Done = 1;
  }

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

  if (useTrendExit == true && side == 1 && d1.close < emaD1Ref) {
    strategy.closeAll(comment="Retournement D1");
  }
  if (useTrendExit == true && side == -1 && d1.close > emaD1Ref) {
    strategy.closeAll(comment="Retournement D1");
  }
} else {
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
var longSignal = flat && wallBidBig && sellAttack && heldLong && flowLong &&
    imbLong && fundingOkL && breakersOk;
var shortSignal = flat && wallAskBig && buyAttack && heldShort && flowShort &&
    imbShort && fundingOkS && breakersOk && allowShorts == true;

if (longSignal) {
  var stopL  = stopLow * (1 - wallBufPct / 100);
  var distL  = trade.close - stopL;
  var distLpct = distL / trade.close * 100;
  if (distLpct >= minStopPct && distLpct <= maxStopPct) {
    var riskUsdL = eq * riskPct / 100;
    var qtyL = math.min(riskUsdL / distL, eq * maxEffLev / trade.close);
    if (qtyL * trade.close >= minNotional) {
      planQty = qtyL;
      planStop = stopL;
      side = 1;
      strategy.entry("LA", "long", qty=qtyL, comment="x501 absorption long");
    }
  }
}
if (shortSignal) {
  var stopS  = stopHigh * (1 + wallBufPct / 100);
  var distS  = stopS - trade.close;
  var distSpct = distS / trade.close * 100;
  if (distSpct >= minStopPct && distSpct <= maxStopPct) {
    var riskUsdS = eq * riskPct / 100;
    var qtyS = math.min(riskUsdS / distS, eq * maxEffLev / trade.close);
    if (qtyS * trade.close >= minNotional) {
      planQty = qtyS;
      planStop = stopS;
      side = -1;
      strategy.entry("SA", "short", qty=qtyS, comment="x501 absorption short");
    }
  }
}

// ------------------------------- AFFICHAGE ----------------------------------
var longMk  = longSignal ? trade.low : na;
var shortMk = shortSignal ? trade.high : na;
plotShape(value=longMk, shape="triangle", width=10, colors=["#16a34a"], label=["Absorption long"], desc=["Mur bid + attaque absorbée"]);
plotShape(value=shortMk, shape="triangle", width=10, colors=["#dc2626"], label=["Absorption short"], desc=["Mur ask + attaque absorbée"]);

// Le plus gros ordre du carnet (les baleines) en overlay de diagnostic
plotLine(value=wallBid, width=1, colors=["#16a34a"], label=["Max bid"], desc=["Plus gros ordre bid dans la profondeur"]);
plotLine(value=wallAsk, width=1, colors=["#dc2626"], label=["Max ask"], desc=["Plus gros ordre ask dans la profondeur"]);

// Alerte : un mur géant apparaît près du prix (suivi papier du pattern)
var wallEvent = crossover(wallBid, wallMult * bidTyp) || crossover(wallAsk, wallMult * askTyp);
alert("x501 Absorption : un mur géant vient d'apparaître dans le carnet", wallEvent);
