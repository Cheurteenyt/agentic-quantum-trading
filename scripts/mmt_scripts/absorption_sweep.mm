script "Absorption & Sweep"

data chart = subscribe(data.ohlcv)

input (
  len = input.int(50, title: "Delta baseline (bars)", min: 10, max: 300)
  thrMult = input.float(2.0, title: "Delta extreme (x baseline)", min: 1.0, max: 6.0)
  maxBodyFrac = input.float(0.4, title: "Max body/range for absorption", min: 0.05, max: 1.0)
  sweepLen = input.int(20, title: "Sweep lookback (bars)", min: 5, max: 200)
  showBg = input.bool(true, title: "Background tint on absorption")
)

pane deltaPane = pane(title: "Delta", height: 0.25)

plot (
  deltaH = plot.histogram(title: "Delta", on: deltaPane)
  absBull = plot.marker(title: "Absorption buy", shape: shape.up, color: color.up, offset: -1, anchor: anchor.bottom)
  absBear = plot.marker(title: "Absorption sell", shape: shape.down, color: color.down, offset: -1, anchor: anchor.top)
  sweepBull = plot.marker(title: "Sweep low", shape: shape.plus, color: color.up, offset: -1, anchor: anchor.bottom)
  sweepBear = plot.marker(title: "Sweep high", shape: shape.plus, color: color.down, offset: -1, anchor: anchor.top)
  absBg = plot.bg(title: "Absorption")
)

state (
  absDeltas = rolling<float>(len)
  sweepLows = rolling<float>(sweepLen)
  sweepHighs = rolling<float>(sweepLen)
)

alert absorption = alert(title: "Absorption bar", onClose: true)

on chart.close {
  let bv = chart.buyVolume
  let sv = chart.sellVolume
  let o = chart.open
  let c = chart.close
  let h = chart.high
  let l = chart.low
  deltaH.plot(bv != null && sv != null ? bv - sv : null)
  if bv != null && sv != null && o != null && c != null && h != null && l != null {
    let delta = bv - sv
    let rng = h - l
    absDeltas.push(math.abs(delta))
    let base = absDeltas.avg()
    if absDeltas.len >= len && rng > 0 && base != null && base > 0 {
      let extreme = math.abs(delta) >= thrMult * base
      let bodyFrac = math.abs(c - o) / rng
      let bullAbs = extreme && delta < 0 && bodyFrac <= maxBodyFrac && c >= o
      let bearAbs = extreme && delta > 0 && bodyFrac <= maxBodyFrac && c <= o
      let prevLow = sweepLows.min()
      let prevHigh = sweepHighs.max()
      sweepLows.push(l)
      sweepHighs.push(h)
      let atr = chart.atr(14)
      let depthOk = atr != null && atr > 0
      let sweepUp = depthOk && sweepLows.len >= sweepLen && prevLow != null && prevLow - l >= 0.15 * atr && c > prevLow && (c - l) / rng >= 0.6
      let sweepDn = depthOk && sweepHighs.len >= sweepLen && prevHigh != null && h - prevHigh >= 0.15 * atr && c < prevHigh && (h - c) / rng >= 0.6
      if bullAbs {
        absBull.plot(14)
      }
      if bearAbs {
        absBear.plot(14)
      }
      if sweepUp {
        sweepBull.plot(32)
      }
      if sweepDn {
        sweepBear.plot(32)
      }
      if showBg && (bullAbs || bearAbs) {
        absBg.plot(color: bullAbs ? color.withAlpha(color.up, 26) : color.withAlpha(color.down, 26))
      }
      if bullAbs || bearAbs {
        absorption.trigger()
      }
    }
  }
}
