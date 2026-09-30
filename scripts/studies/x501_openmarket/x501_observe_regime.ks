//@version=3
// ============================================================================
// OPÉRATION x501 — OBSERVE « RÉGIME INSTITUTIONNEL » (VAGUE 1, docs/27)
// Indicateur pur (PAS de strategy) — à exécuter sur un chart 1h ou 4h.
// ============================================================================
// RÔLE : vérifier sur CHAQUE symbole du domaine que les 7 flux institutionnels
// gratuits répondent, et les tracer avec le score RI — avant de laisser le
// filtre RI (Signature_H1_RI.ks) toucher aux entrées. Un flux qui reste à na
// ici = la composante est morte sur ce symbole = le fail-open du filtre la
// neutralisera — PRÉ-ENREGISTRÉ (docs/27).
//
// Sources (8 premium + spine = 9 slots <= 10) :
//   etf_flow, etf_holding, cme_oi, deribit_volatility_index, skew (delta 25),
//   long_short_ratio, binance_treasury_balance, options_open_interest.
//
// NO-REPAINT : les flux lents (daily) sont lus via htf(..., "1D") sur les
// buckets complétés [1] et avant — jamais le bucket [0] en formation.
// long_short_ratio n'a PAS de membre .time (doc data-sources) : les 3 membres
// sont des snapshots, lecture [0] directe. Le skew s'épelle `onemonth`.
//
// alert() : changement de signe du RI (le quadrant institutionnel bascule).
// DOCUMENT ÉDUCATIF — ne constitue pas un conseil en investissement.
// ============================================================================

define(title="Operation x501 - Observe Regime Institutionnel", position="offchart", axis=true);

// ----------------------------- PARAMÈTRES ----------------------------------
var etfSymbol   = input(name="etfSymbol", type="string", defaultValue="BTC", label="Symbole ETF", group="Sources premium");
var skewDelta   = input(name="skewDelta", type="int", defaultValue=25, label="Delta du skew", constraints={min: 10, max: 50, step: 5}, group="Sources premium");
var optExchange = input(name="optExchange", type="string", defaultValue="DERIBIT", label="Exchange des options", group="Sources premium");
var showRaw     = input(name="showRaw", type="boolean", defaultValue=false, label="Tracer les composantes brutes", group="Affichage");

// ------------------------------- SOURCES ------------------------------------
timeseries trade    = ohlcv(symbol=currentSymbol, exchange=currentExchange);
timeseries etfFlow  = source("etf_flow", symbol=etfSymbol);
timeseries etfHold  = source("etf_holding", symbol=etfSymbol);
timeseries cme      = source("cme_oi", coin=currentCoin);
timeseries dvol     = source("deribit_volatility_index", coin=currentCoin);
timeseries skw      = source("skew", coin=currentCoin, delta=skewDelta);
timeseries lsr      = source("long_short_ratio", symbol=currentSymbol, exchange=currentExchange);
timeseries treasury = source("binance_treasury_balance", asset=currentCoin);
timeseries optOI    = source("options_open_interest", coin=currentCoin, exchange=optExchange);

// Buckets quotidiens complétés (no-repaint)
timeseries etfD = htf(source=etfFlow, timeframe="1D");
timeseries cmeD = htf(source=cme, timeframe="1D");
timeseries skwD = htf(source=skw, timeframe="1D");

// ---------------------------- SCORE RI (même formule que la version RI) ----
var etf3    = etfD.value[1] + etfD.value[2] + etfD.value[3];
var etfSig  = stdev(source=etfD.value, period=60);
var s_etf_r = etf3 / math.max(etfSig, 1e-9);
var s_etf   = nz(math.max(-1, math.min(1, s_etf_r)), 0);

var cmeR    = cmeD.close[1] / cmeD.close[4] - 1;
var pxR     = trade.close / trade.close[72] - 1;   // ~3 jours de barres 1h
var s_cme_r = cmeR / 0.03 * math.sign(pxR);
var s_cme   = nz(math.max(-1, math.min(1, s_cme_r)), 0);

var volRat  = dvol.close / ema(source=dvol.close, period=30) - 1;
var s_vol_r = -volRat / 0.10;
var s_vol   = nz(math.max(-1, math.min(1, s_vol_r)), 0);

var skwDr    = skwD.one_week[1] - skwD.one_week[6];
var s_skew_r = skwDr / 0.02;
var s_skew   = nz(math.max(-1, math.min(1, s_skew_r)), 0);

var lsrNow  = nz(lsr.top_trader_position[0], 1);
var s_lsr_r = (1 - lsrNow) / 0.20;
var s_lsr   = nz(math.max(-1, math.min(1, s_lsr_r)), 0);

var riScore = (s_etf + s_cme + s_vol + s_skew + s_lsr) / 5;

// Disponibilité des flux (le verdict par symbole)
var nOk = 0;
if (!isna(etf3))  { nOk = nOk + 1; }
if (!isna(cmeR))  { nOk = nOk + 1; }
if (!isna(volRat)) { nOk = nOk + 1; }
if (!isna(skwDr)) { nOk = nOk + 1; }
if (!isna(lsr.top_trader_position[0])) { nOk = nOk + 1; }

// ------------------------------- AFFICHAGE ----------------------------------
// Le score RI et ses deux seuils de référence (+/- 0,10 = défaut du filtre)
plotLine(value=riScore, width=2, colors=["#7c3aed"], label=["RI"], desc=["Score régime institutionnel -1..+1"]);
plotLine(value=0.10, width=1, colors=["#16a34a"], label=["Seuil long"], desc=["RI >= +0,10 : longs autorisés"]);
plotLine(value=-0.10, width=1, colors=["#dc2626"], label=["Seuil short"], desc=["RI <= -0,10 : shorts autorisés"]);
plotLine(value=0, width=1, colors=["#94a3b8"], label=["Zéro"], desc=["Neutre"]);

// Composantes brutes (diagnostic, off par défaut)
if (showRaw == true) {
  plotLine(value=s_etf, width=1, colors=["#1d4ed8"], label=["s ETF"], desc=["Composante ETF flow"]);
  plotLine(value=s_cme, width=1, colors=["#4f46e5"], label=["s CME"], desc=["Composante CME OI"]);
  plotLine(value=s_vol, width=1, colors=["#9333ea"], label=["s DVOL"], desc=["Composante volatilité"]);
  plotLine(value=s_skew, width=1, colors=["#be123c"], label=["s Skew"], desc=["Composante skew options"]);
  plotLine(value=s_lsr, width=1, colors=["#9d174d"], label=["s LSR"], desc=["Composante LSR contrarian"]);
  plotLine(value=dvol.close, width=1, colors=["#0f766e"], label=["DVOL"], desc=["Deribit volatility index"]);
  plotLine(value=lsr.top_trader_position[0], width=1, colors=["#374151"], label=["LSR top pos"], desc=["Long/short ratio top traders"]);
  plotLine(value=cmeD.close, width=1, colors=["#4338ca"], label=["CME OI"], desc=["Open interest CME (bucket 1D complété)"]);
  plotLine(value=etfD.value[1], width=1, colors=["#65a30d"], label=["ETF flow J-1"], desc=["Flux ETF du dernier jour complété"]);
  plotLine(value=skwD.one_week[1], width=1, colors=["#be123c"], label=["Skew 1W J-1"], desc=["Skew options 1 semaine (bucket complété)"]);
  plotLine(value=optOI.calls[1], width=1, colors=["#16a34a"], label=["Options calls"], desc=["OI options calls (bucket complété)"]);
  plotLine(value=optOI.puts[1], width=1, colors=["#dc2626"], label=["Options puts"], desc=["OI options puts (bucket complété)"]);
  plotLine(value=treasury.value, width=1, colors=["#0d9488"], label=["Trésorerie"], desc=["Binance treasury balance"]);
  plotLine(value=etfHold.value, width=1, colors=["#a16207"], label=["ETF holding"], desc=["ETF holdings cumulés"]);
}

// Tableau de bord : le verdict de disponibilité en un coup d'œil
plotTable(data=[
  ["flux", "vivant"],
  ["etf_flow", isna(etfD.value[1]) ? "NON" : "oui"],
  ["cme_oi", isna(cmeD.close[1]) ? "NON" : "oui"],
  ["dvol", isna(dvol.close) ? "NON" : "oui"],
  ["skew", isna(skwD.one_week[1]) ? "NON" : "oui"],
  ["long_short_ratio", isna(lsr.top_trader_position[0]) ? "NON" : "oui"],
  ["treasury", isna(treasury.value) ? "NON" : "oui"],
  ["options_oi", isna(optOI.calls[1]) ? "NON" : "oui"],
  ["score RI", "" + riScore],
  ["flux vivants", "" + nOk + " / 5"]
], position="top_right");

// Alerte : bascule de quadrant institutionnel
var riFlip = crossover(riScore, 0) || crossunder(riScore, 0);
alert("x501 Observe : le régime institutionnel change de signe", riFlip);
