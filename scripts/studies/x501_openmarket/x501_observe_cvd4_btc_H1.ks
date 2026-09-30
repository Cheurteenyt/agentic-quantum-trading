//@version=3
define(title="X501 Collector CVD 4 venues (BTC)", position="offchart", axis=true)

// ============================================================================
// OPÉRATION x501 — COLLECTEUR CVD MULTI-VENUES v10 (ZÉRO RISQUE, ZÉRO ORDRE)
// ============================================================================
// But : journaliser le delta acheteur/vendeur H1 du BTC sur les 4 venues
// (Binance spot, Binance perp, Bybit perp, OKX perp) — la divergence
// multi-venues est le levier d'edge v10 (B6 re-falsifiable UNIQUEMENT sur
// ces données réelles : les historiques publics Binance-only l'avaient
// rejeté faute de données). Idiome officiel cookbook « Aggregated CVD » :
// source(type="buy_sell_volume", ...), séries .buy/.sell, na-guard isnum.
// Sortie : UNE alerte par nouvelle bougie H1, message « X501CVD|...| ».
// Paramètre UI : fréquence = « une fois par clôture » (bougie fermée via [1]).
// ============================================================================

var spotBSymbol = input(name="spotBSymbol", type="string", defaultValue="BTCUSDT", label="Binance Spot Symbol")
var perpBSymbol = input(name="perpBSymbol", type="string", defaultValue="BTCUSDT", label="Binance Futures Symbol")
var perpYSymbol = input(name="perpYSymbol", type="string", defaultValue="BTCUSDT", label="Bybit Perp Symbol")
var perpOSymbol = input(name="perpOSymbol", type="string", defaultValue="BTC-USDT-SWAP", label="OKX Swap Symbol")

// ---- spine du chart (obligatoire, doc multi-source) -----------------------
timeseries chart = ohlcv(symbol=currentSymbol, exchange=currentExchange)

// ---- 4 venues --------------------------------------------------------------
timeseries spotB = source(type="buy_sell_volume", symbol=spotBSymbol, exchange="BINANCE")
timeseries perpB = source(type="buy_sell_volume", symbol=perpBSymbol, exchange="BINANCE_FUTURES")
timeseries perpY = source(type="buy_sell_volume", symbol=perpYSymbol, exchange="BYBIT")
timeseries perpO = source(type="buy_sell_volume", symbol=perpOSymbol, exchange="OKEX_SWAP")

// ---- na-guard : une venue sans données contribue zéro (cookbook) ----------
func pairDelta(b, s) { if (isnum(b) && isnum(s)) { return b - s; } return 0; }
func pairLive(b, s) { return (isnum(b) && isnum(s)) ? 1 : 0; }

var dSpot = pairDelta(spotB.buy[1], spotB.sell[1])
var dPerpB = pairDelta(perpB.buy[1], perpB.sell[1])
var dPerpY = pairDelta(perpY.buy[1], perpY.sell[1])
var dPerpO = pairDelta(perpO.buy[1], perpO.sell[1])
var liveCount = pairLive(spotB.buy[1], spotB.sell[1]) + pairLive(perpB.buy[1], perpB.sell[1]) + pairLive(perpY.buy[1], perpY.sell[1]) + pairLive(perpO.buy[1], perpO.sell[1])
var dTotal = dSpot + dPerpB + dPerpY + dPerpO
var dSpotPerp = dSpot - dPerpB

// ---- affichage -------------------------------------------------------------
static cvdTotal = 0
static cvdSpotPerp = 0
cvdTotal = cvdTotal + dTotal
cvdSpotPerp = cvdSpotPerp + dSpotPerp
plotLine(value=cvdTotal, colors=["#22d3a5"], width=2, label=["CVD 4 venues USD"], desc=["Delta acheteur-vendeur cumulé, 4 venues"])
plotLine(value=cvdSpotPerp, colors=["#ff5b7f"], width=1, label=["Spot-Perp divergence"], desc=["CVD spot Binance moins CVD perp Binance"])

// ---- journalisation : une ligne à l'ouverture de chaque nouvelle bougie ---
static lastLogged = -1
var isFresh = barIndex != lastLogged
lastLogged = barIndex
alert(message=format("X501CVD|{0}|spot={1}|perpB={2}|perpY={3}|perpO={4}|total={5}|spotperp={6}|live={7}", currentSymbol, dSpot, dPerpB, dPerpY, dPerpO, dTotal, dSpotPerp, liveCount), condition=isFresh)
