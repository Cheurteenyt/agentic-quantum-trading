script "CVD Divergence"

data (
  chart = subscribe(data.ohlcv)
  cvd = subscribe(data.cvd)
)

input (
  len = input.int(30, title: "Fenetre divergence (barres)", min: 10, max: 200)
  showBg = input.bool(true, title: "Fond sur divergence")
)

plot (
  bull = plot.marker(title: "Divergence haussiere", shape: shape.up, color: color.up, offset: -1, anchor: anchor.bottom)
  bear = plot.marker(title: "Divergence baissiere", shape: shape.down, color: color.down, offset: -1, anchor: anchor.top)
  bg = plot.bg(title: "Divergence")
)

alert divAlert = alert(title: "CVD divergence", onClose: true)

on chart.close {
  let c = cvd.close
  if c != null {
    let priceNewLow = chart.low <= ta.lowest(chart.low, len)
    let cvdNewLow = c <= ta.lowest(cvd.close, len)
    let priceNewHigh = chart.high >= ta.highest(chart.high, len)
    let cvdNewHigh = c >= ta.highest(cvd.close, len)
    let bullDiv = priceNewLow && !cvdNewLow
    let bearDiv = priceNewHigh && !cvdNewHigh
    if bullDiv {
      bull.plot(14)
    }
    if bearDiv {
      bear.plot(14)
    }
    if showBg && (bullDiv || bearDiv) {
      bg.plot(color: bullDiv ? color.withAlpha(color.up, 22) : color.withAlpha(color.down, 22))
    }
    if bullDiv || bearDiv {
      divAlert.trigger()
    }
  }
}
