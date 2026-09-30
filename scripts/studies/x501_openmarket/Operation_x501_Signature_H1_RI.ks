//@version=3
// ============================================================================
// OPÉRATION x501 — SIGNATURE H1 « RÉGIME INSTITUTIONNEL » (VAGUE 1, docs/27)
// Version H1-RI — à exécuter sur un CHART 1h (ex. BINANCE_FUTURES:BTCUSDT)
// ============================================================================
// CE QUI CHANGE vs Signature_H1.ks : un FILTRE DE RÉGIME INSTITUTIONNEL
// composite branché sur 5 sources premium GRATUITES (TradingView les facture) :
//   1. etf_flow                   — la demande ETF spot BTC (cumul 3 j)
//   2. cme_oi                     — le positionnement CME (institutions)
//   3. deribit_volatility_index   — le DVOL (régime de volatilité)
//   4. skew (delta 25)            — la dérive du skew options 1 semaine
//   5. long_short_ratio           — le LSR top traders (contrarian)
// Budget sources : 4 (Signature) + 5 (premium) = 9 <= 10 slots pondérés.
//
// HYPOTHÈSE PRÉ-ENREGISTRÉE (falsifiable, avant tout backtest) :
//   les entrées de la Signature H1 prises quand le score institutionnel
//   RI confirme le sens (RI >= +0,10 en long, <= -0,10 en short) ont un
//   meilleur couple gain médian / DD que les mêmes entrées sans filtre.
//   Le test = A/B useRiFilter true vs false, même moteur, même data.
//   Critère de promotion : la version filtrée ne perd pas de gain médian
//   ET réduit le drawdown ou le nombre de trades perdants. Sinon KILL.
//
// DISCIPLINE NO-REPAINT (le piège n°1 des sources à cadence lente) :
//   etf_flow / cme_oi / skew sont DAILY. Sur un chart 1h l'engine
//   forward-fille la valeur du jour EN COURS — la lire telle quelle revient
//   à connaître le flux final du jour dès 00h (look-ahead). Donc :
//   - on projette chaque flux lent sur le bucket quotidien COMPLÉTÉ
//     (htf(..., "1D")) et on ne lit JAMAIS la barre [0] (jour en formation),
//     on lit [1] et avant (jours clos).
//   - le DVOL est un index continu (quasi-tick) : lecture [0] sans risque.
//   - long_short_ratio n'a PAS de membre .time (doc data-sources) : les 3
//     membres sont des snapshots — lecture [0], score nzé à 0 si absent.
//   - le skew s'épelle `onemonth` SANS underscore (doc data-sources).
//
// FAIL-OPEN (pré-enregistré) : si moins de riMinSources flux répondent
//   (symbole sans data premium), le filtre devient TRANSPARENT — le backtest
//   mesure alors "aucun effet" et non "tout bloqué". Un symbole sans data
//   premium n'est pas pénalisé, il n'est simplement pas filtré.
//
// Le reste du moteur est la Signature H1 INCHANGÉE (structure H4/D1, zone
// EMA21, purge de liquidations, déclencheur CVD, sizing risque fixe, TP1/TP2/
// runner, coupe-circuits -8/-15/-25 %) : la comparabilité A/B est totale.
// ----------------------------------------------------------------------------
// FRAIS : maker 0,018 % / taker 0,045 % (Binance VIP0), slippage 2 bps,
//         funding réel ("data"), marge isolée, levier nominal 10x.
// DOCUMENT ÉDUCATIF — ne constitue pas un conseil en investissement.
// ============================================================================

strategy(title="Operation x501 - Signature H1 RI (régime institutionnel)", position="onchart", axis=true,
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
var minStopPct   = input(name="minStopPct", type="number", defaultValue=0.6, label="Stop min (% du prix)",       constraints={min: 0.2, max: 5, step: 0.1}, group="Risque & palier");
var maxStopPct   = input(name="maxStopPct", type="number", defaultValue=3,   label="Stop max (% du prix)",       constraints={min: 0.5, max: 8, step: 0.25}, group="Risque & palier");
var minNotional  = input(name="minNotional", type="number", defaultValue=5,  label="Notionnel min (USD)",        constraints={min: 1, max: 100, step: 1}, group="Risque & palier");

// Groupe Structure & zone (identique Signature H1)
var h4TrendLen   = input(name="h4TrendLen", type="int", defaultValue=50, label="EMA tendance H4",            constraints={min: 10, max: 200, step: 1}, group="Structure & zone");
var d1TrendLen   = input(name="d1TrendLen", type="int", defaultValue=50, label="EMA tendance D1",            constraints={min: 10, max: 200, step: 1}, group="Structure & zone");
var zoneLen      = input(name="zoneLen", type="int", defaultValue=21,   label="EMA zone H4 (repli)",        constraints={min: 5, max: 100, step: 1}, group="Structure & zone");
var adxMin       = input(name="adxMin", type="number", defaultValue=18,  label="ADX H4 min",                 constraints={min: 5, max: 40, step: 1}, group="Structure & zone");
var pullbackWin  = input(name="pullbackWin", type="int", defaultValue=24, label="Fenêtre swing (barres)",     constraints={min: 5, max: 96, step: 1}, group="Structure & zone");
var stopBufPct   = input(name="stopBufPct", type="number", defaultValue=0.35, label="Marge sous le swing (%)",  constraints={min: 0.05, max: 2, step: 0.05}, group="Structure & zone");

// Groupe Flux & déclencheur (identique Signature H1)
var cvdEmaLen    = input(name="cvdEmaLen", type="int", defaultValue=21,  label="EMA du CVD",                 constraints={min: 5, max: 100, step: 1}, group="Flux & déclencheur");
var liqMaLen     = input(name="liqMaLen", type="int", defaultValue=168,  label="Moyenne liquidations (barres)", constraints={min: 24, max: 720, step: 24}, group="Flux & déclencheur");
var liqMult      = input(name="liqMult", type="number", defaultValue=4,   label="Seuil purge (x moyenne)",    constraints={min: 1.5, max: 10, step: 0.5}, group="Flux & déclencheur");
var flushAgeMax  = input(name="flushAgeMax", type="int", defaultValue=24, label="Purge valable N barres",     constraints={min: 0, max: 96, step: 1}, group="Flux & déclencheur");
var requireFlush = input(name="requireFlush", type="boolean", defaultValue=true, label="Exiger la purge de liquidations", group="Flux & déclencheur");
var fundMax      = input(name="fundMax", type="number", defaultValue=0.0005, label="Funding max (0,0005 = 0,05 %)", constraints={min: 0, max: 0.002, step: 0.0001}, group="Flux & déclencheur");

// Groupe RÉGIME INSTITUTIONNEL (le nouveau bloc de la vague 1)
var useRiFilter  = input(name="useRiFilter", type="boolean", defaultValue=true, label="Activer le filtre RI (A/B)", group="Régime institutionnel");
var riMin        = input(name="riMin", type="number", defaultValue=0.10, label="Seuil RI (échelle -1..+1)", constraints={min: 0.0, max: 0.6, step: 0.05}, group="Régime institutionnel");
var riMinSources = input(name="riMinSources", type="int", defaultValue=3,  label="Flux min. vivants (fail-open)", constraints={min: 1, max: 5, step: 1}, group="Régime institutionnel");
var etfSymbol    = input(name="etfSymbol", type="string", defaultValue="BTC", label="Symbole ETF (etf_flow)", group="Régime institutionnel");
var skewDelta    = input(name="skewDelta", type="int", defaultValue=25,   label="Delta du skew",             constraints={min: 10, max: 50, step: 5}, group="Régime institutionnel");
var etfK         = input(name="etfK", type="number", defaultValue=1.0,  label="ETF : seuil en sigma",      constraints={min: 0.2, max: 3, step: 0.1}, group="Régime institutionnel");
var cmeScale     = input(name="cmeScale", type="number", defaultValue=0.03, label="CME : 1 point = +3 % OI 3j", constraints={min: 0.005, max: 0.2, step: 0.005}, group="Régime institutionnel");
var volScale     = input(name="volScale", type="number", defaultValue=0.10, label="DVOL : 1 point = ±10 % vs MM", constraints={min: 0.02, max: 0.5, step: 0.01}, group="Régime institutionnel");
var skewScale    = input(name="skewScale", type="number", defaultValue=0.02, label="Skew : 1 point = dérive 0,02", constraints={min: 0.002, max: 0.1, step: 0.002}, group="Régime institutionnel");
var lsrScale     = input(name="lsrScale", type="number", defaultValue=0.20, label="LSR : 1 point = écart 0,2 à 1", constraints={min: 0.05, max: 1, step: 0.05}, group="Régime institutionnel");

// Groupe Gestion & sorties (identique Signature H1)
var tp1R         = input(name="tp1R", type="number", defaultValue=1.5,  label="TP1 (R)",                    constraints={min: 0.5, max: 5, step: 0.25}, group="Gestion & sorties");
var tp2R         = input(name="tp2R", type="number", defaultValue=2.5,  label="TP2 (R)",                    constraints={min: 1, max: 8, step: 0.25}, group="Gestion & sorties");
var tp1Pct       = input(name="tp1Pct", type="number", defaultValue=50, label="TP1 : % de la position",     constraints={min: 10, max: 90, step: 5}, group="Gestion & sorties");
var tp2Pct       = input(name="tp2Pct", type="number", defaultValue=25, label="TP2 : % de la position",     constraints={min: 5, max: 50, step: 5}, group="Gestion & sorties");
var trailLen     = input(name="trailLen", type="int", defaultValue=24,   label="Trail : fenêtre swing (barres)", constraints={min: 6, max: 96, step: 1}, group="Gestion & sorties");
var trailBufPct  = input(name="trailBufPct", type="number", defaultValue=0.5, label="Trail : marge (%)",       constraints={min: 0, max: 3, step: 0.1}, group="Gestion & sorties");
var useTrendExit = input(name="useTrendExit", type="boolean", defaultValue=true, label="Sortie si retournement D1", group="Gestion & sorties");

// Groupe Coupe-circuits (identique Signature H1)
var killDD       = input(name="killDD", type="number", defaultValue=25,   label="Drawdown absolu max (%)",    constraints={min: 5, max: 50, step: 1}, group="Coupe-circuits");
var dailyStop    = input(name="dailyStop", type="number", defaultValue=8,  label="Perte jour : stop (%)",      constraints={min: 2, max: 25, step: 1}, group="Coupe-circuits");
var weeklyStop   = input(name="weeklyStop", type="number", defaultValue=15, label="Perte semaine : stop (%)",  constraints={min: 5, max: 50, step: 1}, group="Coupe-circuits");

// Groupe Divers (identique Signature H1)
var allowShorts  = input(name="allowShorts", type="boolean", defaultValue=true, label="Autoriser les shorts", group="Divers");

// ------------------------------- SOURCES ------------------------------------
timeseries trade = ohlcv(symbol=currentSymbol, exchange=currentExchange);
timeseries bsv   = buy_sell_volume(symbol=currentSymbol, exchange=currentExchange, currency="USD");
timeseries fund  = source("funding_rate", symbol=currentSymbol, exchange=currentExchange);
timeseries liq   = source("liquidations", symbol=currentSymbol, exchange=currentExchange);

// --- Les 5 flux institutionnels (VAGUE 1, docs/27) ---
timeseries etfFlow = source("etf_flow", symbol=etfSymbol);
timeseries cme     = source("cme_oi", coin=currentCoin);
timeseries dvol    = source("deribit_volatility_index", coin=currentCoin);
timeseries skw     = source("skew", coin=currentCoin, delta=skewDelta);
timeseries lsr     = source("long_short_ratio", symbol=currentSymbol, exchange=currentExchange);

// Timeframes supérieurs CONFIRMÉS (sans repaint)
timeseries h4    = htf(source=trade, timeframe="4h");
timeseries d1    = htf(source=trade, timeframe="1D");

// Buckets quotidiens complétés des flux lents (no-repaint, voir en-tête)
timeseries etfD  = htf(source=etfFlow, timeframe="1D");
timeseries cmeD  = htf(source=cme, timeframe="1D");
timeseries skwD  = htf(source=skw, timeframe="1D");

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

// ------------------- RÉGIME INSTITUTIONNEL (score RI) -----------------------
// Chaque composante est écrêtée à [-1, +1] ; poids ÉGAUX figés dans le code
// (pré-enregistrement dur — aucun tuning par input). Les échelles ne servent
// qu'à adapter la normalisation, pas à chercher un edge.

// 1. ETF : cumul 3 j des flux complétés, en sigma de sa distribution 60 j
var etf3    = etfD.value[1] + etfD.value[2] + etfD.value[3];
var etfSig  = stdev(source=etfD.value, period=60);
var s_etf_r = etf3 / math.max(etfSig * etfK, 1e-9);
var s_etf   = nz(math.max(-1, math.min(1, s_etf_r)), 0);

// 2. CME : variation d'OI 3 j x signe du prix 3 j (institutions qui ajoutent
//    des positions DANS le sens du marché)
var cmeR    = cmeD.close[1] / cmeD.close[4] - 1;
var pxR     = d1.close[1] / d1.close[4] - 1;
var s_cme_r = cmeR / cmeScale * math.sign(pxR);
var s_cme   = nz(math.max(-1, math.min(1, s_cme_r)), 0);

// 3. DVOL : volatilité sous sa moyenne 30 j = compression favorable (+),
//    spike = stress (-). Index continu, lecture [0] sans look-ahead.
var volRat  = dvol.close / ema(source=dvol.close, period=30) - 1;
var s_vol_r = -volRat / volScale;
var s_vol   = nz(math.max(-1, math.min(1, s_vol_r)), 0);

// 4. Skew : dérive du skew 1W sur 5 buckets quotidiens complétés.
//    Hypothèse pré-enregistrée : skew qui monte = demande directionnelle
//    haussière du marché des options (+). La falsification tranche.
var skwDr    = skwD.one_week[1] - skwD.one_week[6];
var s_skew_r = skwDr / skewScale;
var s_skew   = nz(math.max(-1, math.min(1, s_skew_r)), 0);

// 5. LSR top traders : contrarian (foule longue = pénalité). PAS de .time.
var lsrNow  = nz(lsr.top_trader_position[0], 1);
var s_lsr_r = (1 - lsrNow) / lsrScale;
var s_lsr   = nz(math.max(-1, math.min(1, s_lsr_r)), 0);

// Score composite (poids égaux 1/5) + disponibilité (fail-open)
var riRaw   = (s_etf + s_cme + s_vol + s_skew + s_lsr) / 5;
var nOk     = 0;
if (!isna(etf3))  { nOk = nOk + 1; }
if (!isna(cmeR))  { nOk = nOk + 1; }
if (!isna(volRat)) { nOk = nOk + 1; }
if (!isna(skwDr)) { nOk = nOk + 1; }
if (!isna(lsr.top_trader_position[0])) { nOk = nOk + 1; }
var riReady = nOk >= riMinSources;
var riScore = isna(riRaw) ? 0 : riRaw;

// Filtres : transparent si désactivé OU si les flux sont indisponibles
var riLongOk  = useRiFilter == false || riReady == false || riScore >= riMin;
var riShortOk = useRiFilter == false || riReady == false || riScore <= -riMin;

// ------------------------- ÉTAT PERSISTANT ----------------------------------
persist peakEq     = 0;
persist halted     = 0;
persist dayAnchor  = 0;
persist dayAnchorEq = 0;
persist weekAnchor = 0;
persist weekAnchorEq = 0;
persist flushAge   = 9999;
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

// --------------------------- DÉTECTION SETUP --------------------------------
// 1. Régime de tendance (identique Signature H1)
var regimeLong  = h4.close > emaH4Trend && d1.close > emaD1Trend && adxH4 > adxMin;
var regimeShort = h4.close < emaH4Trend && d1.close < emaD1Trend && adxH4 > adxMin;

// 2. Zone de repli H4
var zoneTouchLong  = trade.low <= emaH4Zone;
var zoneTouchShort = trade.high >= emaH4Zone;

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

// 3. Déclencheur H1
var cvdUp    = crossover(cvd, cvdEma);
var cvdDown  = crossunder(cvd, cvdEma);
var bullBar  = trade.close > trade.open;
var bearBar  = trade.close < trade.open;

var fundingOkLong  = fund.value < fundMax;
var fundingOkShort = fund.value > -fundMax;

var breakersOk = halted == 0 && dayLossPct < dailyStop && weekLossPct < weeklyStop;

var swingLow  = lowest(source=trade.low, period=pullbackWin);
var swingHigh = highest(source=trade.high, period=pullbackWin);

// ----------------------- GESTION DE POSITION OUVERTE ------------------------
var entryId = side == 1 ? "L" : "S";
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

  if (useTrendExit == true && side == 1 && d1.close < emaD1Trend) {
    strategy.closeAll(comment="Retournement D1");
  }
  if (useTrendExit == true && side == -1 && d1.close > emaD1Trend) {
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
// Les seules différences vs Signature H1 : && riLongOk / && riShortOk
var longSignal = flat && regimeLong && zoneTouchLong && confluenceOk &&
    cvdUp && bullBar && fundingOkLong && breakersOk && riLongOk;
var shortSignal = flat && regimeShort && zoneTouchShort && confluenceOk &&
    cvdDown && bearBar && fundingOkShort && breakersOk && allowShorts == true && riShortOk;

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
      strategy.entry("L", "long", qty=qtyL, comment="x501 RI long");
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
      strategy.entry("S", "short", qty=qtyS, comment="x501 RI short");
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
plotShape(value=longMk, shape="triangle", width=10, colors=["#16a34a"], label=["Long"], desc=["Signal long x501 RI"]);
plotShape(value=shortMk, shape="triangle", width=10, colors=["#dc2626"], label=["Short"], desc=["Signal short x501 RI"]);
plotShape(value=flushMk, shape="circle", width=7, colors=["#f59e0b"], label=["Purge"], desc=["Purge de liquidations (confluence)"]);

// Le score RI et ses seuils (visible sur le chart, 3 lignes)
plotLine(value=riScore, width=2, colors=["#7c3aed"], label=["RI"], desc=["Régime institutionnel -1..+1"]);
plotLine(value=riMin, width=1, colors=["#94a3b8"], label=["RI seuil"], desc=["Seuil d'acceptation RI"]);
plotLine(value=-riMin, width=1, colors=["#94a3b8"], label=["RI -seuil"], desc=["Seuil d'acceptation RI (short)"]);

// Alerte : le RI change de quadrant (passage haussier <-> baissier)
var riFlip = crossover(riScore, 0) || crossunder(riScore, 0);
alert("x501 RI : le régime institutionnel change de signe", riFlip);
